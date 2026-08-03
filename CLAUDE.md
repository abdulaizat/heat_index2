# heat_index2 Agent Instructions

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
