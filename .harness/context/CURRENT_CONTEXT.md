# Current Context

- Updated at: 2026-06-04T03:19:04.235189+00:00
- Phase: `post`
- Compared against: current session start

## Repo Focus
- Malaysia weather and air-quality workspace spanning station ingest, climate drivers, and satellite download and audit pipelines.
- Most scripts target 2020-2024 archives, with some Himawari and GPM workflows extending into 2025.
- New files are picked up automatically on every `check_arch_staleness.sh pre` and `post` refresh.

## Snapshot
- Python scripts: 50
- Shell scripts: 6
- Docs: 8
- Logs: 61
- Data and reports: 69

## Script Families
- acquisition: 19
- audit: 8
- processing: 2
- repair: 4
- utility: 13
- validation: 10

## Session Delta
- Added: 0
- Changed: 2
- Removed: 0
- Most recent touched files:
  - `audit_gpm_imerg_parallel.py`
  - `download_gpm_imerg_parallel_finalRun.py`

## Hot Files
- `download_gpm_imerg_parallel_finalRun.py`: GPM IMERG Final Run (Half-Hourly) Download Script
- `audit_gpm_imerg_parallel.py`: GPM IMERG Forensic Audit V3 (Variable Agnostic & Optimized)
- `tests/test_quad_agent_harness.py`: Sync Quad agent harness tests.
- `GEMINI.md`: heat_index2 Agent Instructions
- `CLAUDE.md`: heat_index2 Agent Instructions
- `ANTIGRAVITY.md`: heat_index2 Agent Instructions
- `AGENTS.md`: heat_index2 Agent Instructions
- `scripts/build_agent_context.py`: Build compact repo context for Sync Quad agent session refresh.

## Top-Level Layout
- `.`: 123 files, 44.0 MiB
- `station_data`: 61 files, 283.8 MiB
- `scripts`: 8 files, 29.7 KiB
- `tests`: 5 files, 16.1 KiB
- `docs`: 1 files, 4.1 KiB

## Read Next
- `docs/agents/SYSTEM_FLOWS.md` for the curated end-to-end workflow map.
- `.harness/context/HARNESS_GUARDRAILS.md` for safety, git, rollback, dependency, and debugging-loop rules.
- `.harness/context/SCRIPT_CATALOG.md` for concrete script entrypoints by family.
- `.harness/context/DEBUG_LEARNINGS.md` for recent failure patterns extracted from logs.
- `.harness/context/SESSION_DELTA.md` for the precise file changes in this refresh window.
