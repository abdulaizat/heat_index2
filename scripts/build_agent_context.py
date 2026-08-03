#!/usr/bin/env python3
"""Build compact repo context for Sync Quad agent session refresh."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".sh",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".html",
}
CODE_SUFFIXES = {".py", ".sh"}
AGENT_DOCS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md")
LOG_KEYWORDS = re.compile(
    r"(error|warn|warning|failed|critical|traceback|missing|corrupt)",
    re.IGNORECASE,
)
TIMESTAMP_PREFIX = re.compile(
    r"^\s*\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:\s+\[[A-Z]+\])?\s*[-:]*\s*"
)
NUMBER_RE = re.compile(r"\b\d+\b")


def ensure_newline(text: str) -> str:
    return text.rstrip() + "\n"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relpath(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def is_generated_path(path: Path) -> bool:
    parts = path.parts
    return ".harness" in parts or "__pycache__" in parts


def classify_script_family(path: Path) -> str:
    stem = path.stem.lower()
    if stem.startswith("download_"):
        return "acquisition"
    if stem.startswith("audit_"):
        return "audit"
    if stem.startswith(("verify_", "validate_", "check_", "test_")):
        return "validation"
    if stem.startswith(("repair_", "fix_", "clean_", "purge_", "fill_", "generate_missing_")):
        return "repair"
    if stem.startswith(("process_", "step")):
        return "processing"
    return "utility"


def classify_file(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix == ".py":
        return "python", classify_script_family(path)
    if suffix == ".sh":
        return "shell", classify_script_family(path)
    if suffix == ".md":
        return "documentation", "docs"
    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        return "config", "config"
    if suffix == ".log":
        return "log", "logs"
    if suffix == ".csv":
        return "report", "reports"
    if suffix in {".parquet", ".xls", ".xlsx", ".nc", ".h5", ".tif"}:
        return "data", "data"
    if name.endswith(".pyc"):
        return "cache", "cache"
    return "other", "other"


def sha1_for_path(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(data).hexdigest()


def file_signature(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES and path.stat().st_size <= 1_000_000:
        return sha1_for_path(path)
    stat = path.stat()
    payload = f"{stat.st_size}:{stat.st_mtime_ns}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def fallback_description(path: Path) -> str:
    words = path.stem.replace("_", " ").replace("-", " ").strip()
    if not words:
        return "No description available."
    return words[0].upper() + words[1:]


def description_from_python(path: Path) -> str:
    try:
        module = ast.parse(path.read_text(encoding="utf-8"))
        doc = ast.get_docstring(module) or ""
        first_line = doc.strip().splitlines()[0] if doc.strip() else ""
        if first_line:
            return first_line
    except Exception:
        pass
    return fallback_description(path)


def description_from_shell(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#!"):
                    continue
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()
                break
    except Exception:
        pass
    return fallback_description(path)


def description_from_markdown(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()
    except Exception:
        pass
    return fallback_description(path)


def extract_description(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return description_from_python(path)
    if suffix == ".sh":
        return description_from_shell(path)
    if suffix == ".md":
        return description_from_markdown(path)
    return fallback_description(path)


def scan_repo(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for current_root, dirnames, filenames in os.walk(root):
        current_path = Path(current_root)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".harness", "__pycache__"}
        ]
        for filename in filenames:
            path = current_path / filename
            if is_generated_path(path):
                continue
            category, family = classify_file(path)
            stat = path.stat()
            records.append(
                {
                    "path": relpath(root, path),
                    "category": category,
                    "family": family,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "signature": file_signature(path),
                    "description": extract_description(path),
                }
            )
    return sorted(records, key=lambda item: item["path"])


def snapshot_lookup(snapshot: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not snapshot:
        return {}
    records = snapshot.get("records", [])
    return {item["path"]: item for item in records}  # type: ignore[index]


def load_snapshot(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_snapshot(path: Path, phase: str, records: list[dict[str, object]]) -> None:
    payload = {
        "version": 1,
        "phase": phase,
        "captured_at": utc_now(),
        "records": records,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compute_delta(
    previous: dict[str, object] | None,
    current_records: list[dict[str, object]],
) -> dict[str, object]:
    previous_lookup = snapshot_lookup(previous)
    current_lookup = {item["path"]: item for item in current_records}

    added = sorted(path for path in current_lookup if path not in previous_lookup)
    removed = sorted(path for path in previous_lookup if path not in current_lookup)
    changed = sorted(
        path
        for path, record in current_lookup.items()
        if path in previous_lookup and record["signature"] != previous_lookup[path]["signature"]
    )

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "comparison_captured_at": previous.get("captured_at") if previous else None,
    }


def top_level_summary(records: Iterable[dict[str, object]]) -> list[tuple[str, int, int]]:
    summary: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for record in records:
        path = str(record["path"])
        top = path.split("/", 1)[0] if "/" in path else "."
        summary[top][0] += 1
        summary[top][1] += int(record["size"])
    return sorted(
        ((name, values[0], values[1]) for name, values in summary.items()),
        key=lambda item: (-item[1], item[0]),
    )


def script_catalog(records: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        if record["category"] in {"python", "shell"}:
            grouped[str(record["family"])].append(record)
    for family in grouped.values():
        family.sort(key=lambda item: item["path"])
    return dict(sorted(grouped.items()))


def recent_code_files(records: list[dict[str, object]], limit: int = 8) -> list[dict[str, object]]:
    candidates = [
        record
        for record in records
        if record["category"] in {"python", "shell", "documentation", "config"}
    ]
    candidates.sort(key=lambda item: (float(item["mtime"]), item["path"]), reverse=True)
    return candidates[:limit]


def tail_lines(path: Path, limit: int = 400) -> list[str]:
    lines: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            lines.append(line.rstrip("\n"))
    return list(lines)


def recent_log_paths(root: Path, records: list[dict[str, object]], limit: int = 12) -> list[Path]:
    logs = [
        root / str(record["path"])
        for record in records
        if record["category"] == "log"
    ]
    logs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return logs[:limit]


def normalize_log_line(line: str) -> str:
    line = TIMESTAMP_PREFIX.sub("", line.strip())
    line = re.sub(r"\[[A-Z]+\]", "", line)
    line = NUMBER_RE.sub("<n>", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip(" -:")


def is_actionable_log_line(line: str) -> bool:
    lowered = line.lower()
    skip_markers = (
        "progress:",
        "no corruption detected",
        "perfect integrity",
        "scan complete",
    )
    return not any(marker in lowered for marker in skip_markers)


def collect_log_patterns(root: Path, records: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[Path]]:
    logs = recent_log_paths(root, records)
    patterns: dict[str, dict[str, object]] = {}

    for log_path in logs:
        try:
            for line in tail_lines(log_path):
                if not LOG_KEYWORDS.search(line):
                    continue
                if not is_actionable_log_line(line):
                    continue
                normalized = normalize_log_line(line)
                if not normalized:
                    continue
                entry = patterns.setdefault(
                    normalized,
                    {"count": 0, "sources": Counter(), "example": line.strip()},
                )
                entry["count"] = int(entry["count"]) + 1
                entry["sources"][relpath(root, log_path)] += 1  # type: ignore[index]
        except OSError:
            continue

    ranked: list[dict[str, object]] = []
    for normalized, entry in patterns.items():
        source_counter: Counter[str] = entry["sources"]  # type: ignore[assignment]
        ranked.append(
            {
                "pattern": normalized,
                "count": entry["count"],
                "sources": dict(source_counter.most_common(3)),
                "example": entry["example"],
            }
        )
    ranked.sort(key=lambda item: (-int(item["count"]), str(item["pattern"])))
    return ranked[:15], logs


def format_bytes(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def render_current_context(
    phase: str,
    records: list[dict[str, object]],
    delta: dict[str, object],
    reference_label: str,
) -> str:
    category_counts = Counter(str(record["category"]) for record in records)
    current_lookup = {str(record["path"]): record for record in records}
    family_counts = Counter(
        str(record["family"])
        for record in records
        if record["category"] in {"python", "shell"}
    )
    top_dirs = top_level_summary(records)[:8]
    hot_files = recent_code_files(records)
    recent_changes = sorted(
        list(delta["changed"]) + list(delta["added"]),
        key=lambda path: float(current_lookup.get(path, {}).get("mtime", 0.0)),
        reverse=True,
    )[:8]

    lines = [
        "# Current Context",
        "",
        f"- Updated at: {utc_now()}",
        f"- Phase: `{phase}`",
        f"- Compared against: {reference_label}",
        "",
        "## Repo Focus",
        "- Malaysia weather and air-quality workspace spanning station ingest, climate drivers, and satellite download and audit pipelines.",
        "- Most scripts target 2020-2024 archives, with some Himawari and GPM workflows extending into 2025.",
        "- New files are picked up automatically on every `check_arch_staleness.sh pre` and `post` refresh.",
        "",
        "## Snapshot",
        f"- Python scripts: {category_counts['python']}",
        f"- Shell scripts: {category_counts['shell']}",
        f"- Docs: {category_counts['documentation']}",
        f"- Logs: {category_counts['log']}",
        f"- Data and reports: {category_counts['data'] + category_counts['report']}",
        "",
        "## Script Families",
    ]
    for family, count in sorted(family_counts.items()):
        lines.append(f"- {family}: {count}")

    lines.extend(
        [
            "",
            "## Session Delta",
            f"- Added: {len(delta['added'])}",
            f"- Changed: {len(delta['changed'])}",
            f"- Removed: {len(delta['removed'])}",
        ]
    )
    if recent_changes:
        lines.append("- Most recent touched files:")
        for path in recent_changes[:8]:
            lines.append(f"  - `{path}`")
    else:
        lines.append("- No file-level changes detected against the comparison snapshot.")

    lines.extend(["", "## Hot Files"])
    for record in hot_files:
        lines.append(
            f"- `{record['path']}`: {record['description']}"
        )

    lines.extend(["", "## Top-Level Layout"])
    for name, count, size in top_dirs:
        lines.append(f"- `{name}`: {count} files, {format_bytes(size)}")

    lines.extend(
        [
            "",
        "## Read Next",
        "- `docs/agents/SYSTEM_FLOWS.md` for the curated end-to-end workflow map.",
        "- `.harness/context/HARNESS_GUARDRAILS.md` for safety, git, rollback, dependency, and debugging-loop rules.",
        "- `.harness/context/SCRIPT_CATALOG.md` for concrete script entrypoints by family.",
        "- `.harness/context/DEBUG_LEARNINGS.md` for recent failure patterns extracted from logs.",
        "- `.harness/context/SESSION_DELTA.md` for the precise file changes in this refresh window.",
        ]
    )
    return ensure_newline("\n".join(lines))


def render_script_catalog(records: list[dict[str, object]]) -> str:
    groups = script_catalog(records)
    lines = [
        "# Script Catalog",
        "",
        f"- Updated at: {utc_now()}",
        "",
    ]
    for family, items in groups.items():
        lines.append(f"## {family.title()}")
        for item in items:
            lines.append(f"- `{item['path']}`: {item['description']}")
        lines.append("")
    return ensure_newline("\n".join(lines))


def render_session_delta(
    phase: str,
    delta: dict[str, object],
    reference_label: str,
) -> str:
    lines = [
        "# Session Delta",
        "",
        f"- Updated at: {utc_now()}",
        f"- Phase: `{phase}`",
        f"- Compared against: {reference_label}",
        f"- Reference captured at: {delta.get('comparison_captured_at') or 'none'}",
        f"- Added: {len(delta['added'])}",
        f"- Changed: {len(delta['changed'])}",
        f"- Removed: {len(delta['removed'])}",
        "",
    ]
    for label in ("added", "changed", "removed"):
        values = list(delta[label])
        lines.append(f"## {label.title()}")
        if values:
            for path in values[:25]:
                lines.append(f"- `{path}`")
        else:
            lines.append("- None")
        lines.append("")
    return ensure_newline("\n".join(lines))


def render_debug_learnings(
    log_paths: list[str],
    patterns: list[dict[str, object]],
) -> str:
    lines = [
        "# Debug Learnings",
        "",
        f"- Updated at: {utc_now()}",
        "- Source window: last 12 modified `.log` files, last 400 lines each.",
        "",
        "## Recurring Patterns",
    ]
    if patterns:
        for item in patterns:
            source_list = ", ".join(
                f"{source} x{count}" for source, count in item["sources"].items()
            )
            lines.append(f"- `{item['pattern']}` | count={item['count']} | sources: {source_list}")
    else:
        lines.append("- No warning or error patterns were detected in the recent logs.")

    lines.extend(["", "## Logs Seen"])
    for path in log_paths:
        lines.append(f"- `{path}`")
    return ensure_newline("\n".join(lines))


def render_harness_guardrails() -> str:
    docs = ", ".join(f"`{name}`" for name in AGENT_DOCS)
    lines = [
        "# Harness Guardrails",
        "",
        f"- Updated at: {utc_now()}",
        "",
        "## Session Contract",
        "- Run `bash scripts/check_arch_staleness.sh pre` before code edits; it syncs root agent docs and rebuilds `.harness/context` from the current filesystem.",
        "- Run `bash scripts/check_arch_staleness.sh post` after code edits; it records the completed-session baseline used by the next fresh session.",
        "- Read `.harness/context/CURRENT_CONTEXT.md`, `.harness/context/SESSION_DELTA.md`, and relevant generated docs before broad changes.",
        "- New files from humans or any agent are discovered automatically by the next pre/post refresh.",
        "",
        "## Sync Quad Agent Docs",
        f"- Canonical root instruction files: {docs}.",
        "- The newest non-empty root instruction file is mirrored to every target during pre/post refresh.",
        "- Keep root instruction files under the short-startup rule; put detailed workflow memory in generated docs or task-specific docs.",
        "- Do not hand-edit only one root instruction file unless that change should be mirrored to all targets.",
        "",
        "## Git And Rollback",
        "- Use git for change review and rollback when `.git` is available: inspect status/diff before risky edits and prefer small commits.",
        "- Never use destructive git or filesystem commands unless the human explicitly asks for that exact operation.",
        "- If `.git` is unavailable, treat `.harness/state/*snapshot.json` as context baselines only; they are not source rollback mechanisms.",
        "- To restore a removed line or previous implementation, inspect git history first when available, then use the smallest targeted patch.",
        "",
        "## Change Safety",
        "- Preserve external mount paths under `/mnt/AizatDrive` and `/run/media/NWP5/One Touch` unless storage layout is the task.",
        "- Before changing pipeline logic, inspect the matching `download_*`, `audit_*`, and `repair_*` scripts plus their recent logs/reports.",
        "- Reuse existing scripts and Python stdlib tooling before adding dependencies; do not install plausible but unverified packages.",
        "- Do not suppress exceptions to force green runs; fix root causes or surface the failure clearly.",
        "",
        "## Resource Limits",
        "- Before long or parallel runs, run `bash scripts/resource_profile.sh <phase>`.",
        "- Keep 10-12 GiB RAM headroom and cap I/O-heavy workers at 3 on HDD-backed paths.",
        "- Prefer targeted tests and audits before broad reruns; expand only when the changed surface requires it.",
        "",
        "## Debugging Loop",
        "- Start production-error work from stack traces, logs, generated debug learnings, and the relevant pipeline family.",
        "- For support tickets without stack traces, map the user symptom to the end-to-end flow in `docs/agents/SYSTEM_FLOWS.md` before editing.",
        "- If two attempts fail with the same symptom, stop the current strategy, summarize evidence, and inspect a different layer instead of cycling patches.",
        "- Tests must assert behavior or contracts, not merely mirror the current implementation.",
    ]
    return ensure_newline("\n".join(lines))


def build_context(root: Path, phase: str) -> dict[str, object]:
    root = root.resolve()
    state_dir = root / ".harness" / "state"
    context_dir = root / ".harness" / "context"
    state_dir.mkdir(parents=True, exist_ok=True)
    context_dir.mkdir(parents=True, exist_ok=True)

    baseline_snapshot_path = state_dir / "baseline_snapshot.json"
    pre_snapshot_path = state_dir / "pre_session_snapshot.json"
    latest_snapshot_path = state_dir / "latest_snapshot.json"
    metadata_path = state_dir / "session_metadata.json"

    if phase == "pre":
        reference_snapshot = load_snapshot(baseline_snapshot_path)
        reference_label = "last completed session"
    else:
        reference_snapshot = load_snapshot(pre_snapshot_path) or load_snapshot(baseline_snapshot_path)
        reference_label = "current session start" if load_snapshot(pre_snapshot_path) else "last completed session"

    records = scan_repo(root)
    delta = compute_delta(reference_snapshot, records)
    patterns, log_paths = collect_log_patterns(root, records)
    log_paths_relative = [relpath(root, path) for path in log_paths]

    (context_dir / "CURRENT_CONTEXT.md").write_text(
        render_current_context(phase, records, delta, reference_label),
        encoding="utf-8",
    )
    (context_dir / "SCRIPT_CATALOG.md").write_text(
        render_script_catalog(records),
        encoding="utf-8",
    )
    (context_dir / "SESSION_DELTA.md").write_text(
        render_session_delta(phase, delta, reference_label),
        encoding="utf-8",
    )
    (context_dir / "DEBUG_LEARNINGS.md").write_text(
        render_debug_learnings(log_paths_relative, patterns),
        encoding="utf-8",
    )
    (context_dir / "HARNESS_GUARDRAILS.md").write_text(
        render_harness_guardrails(),
        encoding="utf-8",
    )

    save_snapshot(latest_snapshot_path, phase, records)
    if phase == "pre":
        save_snapshot(pre_snapshot_path, phase, records)
    else:
        save_snapshot(baseline_snapshot_path, phase, records)
        if pre_snapshot_path.exists():
            pre_snapshot_path.unlink()

    metadata = {
        "generated_at": utc_now(),
        "phase": phase,
        "reference_label": reference_label,
        "delta_counts": {
            "added": len(delta["added"]),
            "changed": len(delta["changed"]),
            "removed": len(delta["removed"]),
        },
        "record_counts": Counter(str(record["category"]) for record in records),
        "pattern_count": len(patterns),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--phase", choices=("pre", "post"), required=True)
    args = parser.parse_args()

    metadata = build_context(args.root, args.phase)
    counts = metadata["delta_counts"]
    print(
        "Built Sync Quad agent context "
        f"(phase={args.phase}, added={counts['added']}, "
        f"changed={counts['changed']}, removed={counts['removed']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
