#!/usr/bin/env python3
"""Keep the root Sync Quad agent instruction files identical."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

TARGET_FILENAMES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md")
DEFAULT_TEXT = """# heat_index2 Agent Instructions

IMPORTANT:
- Before code edits run `bash scripts/check_arch_staleness.sh pre`.
- After code edits run `bash scripts/check_arch_staleness.sh post`.
- Before long or parallel runs run `bash scripts/resource_profile.sh <phase>`.

Keep this file short. Put detailed guidance in generated docs instead of here.

Start here:
- `.harness/context/CURRENT_CONTEXT.md` for the current repo snapshot, session delta, and hot files.
- `.harness/context/HARNESS_GUARDRAILS.md` for safety, git, rollback, dependency, and debugging-loop rules.
- `docs/agents/SYSTEM_FLOWS.md` for the curated end-to-end domain map.
- `.harness/context/SCRIPT_CATALOG.md` for script families and entrypoints.
- `.harness/context/DEBUG_LEARNINGS.md` for recent failure patterns mined from logs.

Repo rules:
- This repo is a Malaysia weather and air-quality data workspace built around station ingest, climate drivers, and satellite download and audit pipelines.
- Preserve existing external mount paths unless the task explicitly changes storage layout.
- Inspect the matching `download_*`, `audit_*`, and `repair_*` scripts together before changing pipeline logic.
- Reuse existing scripts and stdlib tooling before adding dependencies.
- `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and `ANTIGRAVITY.md` are intentionally identical. Edit any one only if the same content should be mirrored to all four by `check_arch_staleness.sh`.
"""


def ensure_newline(text: str) -> str:
    return text.rstrip() + "\n"


def read_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def choose_source(root: Path) -> tuple[str, str]:
    existing = [root / name for name in TARGET_FILENAMES if (root / name).exists()]
    if existing:
        newest = max(existing, key=lambda path: path.stat().st_mtime_ns)
        content = ensure_newline(read_if_exists(newest))
        if content.strip():
            return newest.name, content
    return "default_template", ensure_newline(DEFAULT_TEXT)


def sync_agent_docs(root: Path) -> dict[str, object]:
    source_name, content = choose_source(root)
    written: list[str] = []

    for name in TARGET_FILENAMES:
        path = root / name
        if read_if_exists(path) != content:
            path.write_text(content, encoding="utf-8")
        written.append(name)

    state_dir = root / ".harness" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "source": source_name,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "targets": list(TARGET_FILENAMES),
        "sha1": hashlib.sha1(content.encode("utf-8")).hexdigest(),
    }
    rendered_state = json.dumps(state, indent=2, sort_keys=True) + "\n"
    (state_dir / "quad_agent_sync.json").write_text(rendered_state, encoding="utf-8")
    (state_dir / "tri_agent_sync.json").write_text(rendered_state, encoding="utf-8")
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    state = sync_agent_docs(args.root.resolve())
    print(
        f"Synced Sync Quad agent docs from {state['source']} to "
        f"{', '.join(state['targets'])}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
