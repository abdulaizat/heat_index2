# Harness Guardrails

- Updated at: 2026-06-04T03:19:04.236001+00:00

## Session Contract
- Run `bash scripts/check_arch_staleness.sh pre` before code edits; it syncs root agent docs and rebuilds `.harness/context` from the current filesystem.
- Run `bash scripts/check_arch_staleness.sh post` after code edits; it records the completed-session baseline used by the next fresh session.
- Read `.harness/context/CURRENT_CONTEXT.md`, `.harness/context/SESSION_DELTA.md`, and relevant generated docs before broad changes.
- New files from humans or any agent are discovered automatically by the next pre/post refresh.

## Sync Quad Agent Docs
- Canonical root instruction files: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `ANTIGRAVITY.md`.
- The newest non-empty root instruction file is mirrored to every target during pre/post refresh.
- Keep root instruction files under the short-startup rule; put detailed workflow memory in generated docs or task-specific docs.
- Do not hand-edit only one root instruction file unless that change should be mirrored to all targets.

## Git And Rollback
- Use git for change review and rollback when `.git` is available: inspect status/diff before risky edits and prefer small commits.
- Never use destructive git or filesystem commands unless the human explicitly asks for that exact operation.
- If `.git` is unavailable, treat `.harness/state/*snapshot.json` as context baselines only; they are not source rollback mechanisms.
- To restore a removed line or previous implementation, inspect git history first when available, then use the smallest targeted patch.

## Change Safety
- Preserve external mount paths under `/mnt/AizatDrive` and `/run/media/NWP5/One Touch` unless storage layout is the task.
- Before changing pipeline logic, inspect the matching `download_*`, `audit_*`, and `repair_*` scripts plus their recent logs/reports.
- Reuse existing scripts and Python stdlib tooling before adding dependencies; do not install plausible but unverified packages.
- Do not suppress exceptions to force green runs; fix root causes or surface the failure clearly.

## Resource Limits
- Before long or parallel runs, run `bash scripts/resource_profile.sh <phase>`.
- Keep 10-12 GiB RAM headroom and cap I/O-heavy workers at 3 on HDD-backed paths.
- Prefer targeted tests and audits before broad reruns; expand only when the changed surface requires it.

## Debugging Loop
- Start production-error work from stack traces, logs, generated debug learnings, and the relevant pipeline family.
- For support tickets without stack traces, map the user symptom to the end-to-end flow in `docs/agents/SYSTEM_FLOWS.md` before editing.
- If two attempts fail with the same symptom, stop the current strategy, summarize evidence, and inspect a different layer instead of cycling patches.
- Tests must assert behavior or contracts, not merely mirror the current implementation.
