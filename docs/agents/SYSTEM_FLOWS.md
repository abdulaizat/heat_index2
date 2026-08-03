# System Flows

This repo is a Malaysia-focused weather, haze, and heat-index data workspace. The useful mental model is not "one app"; it is a set of acquisition, audit, and repair pipelines that feed downstream analysis.

## Domain
- Geographic focus: Malaysia station observations plus a Malaysia crop for several satellite products.
- Time focus: mostly 2020-2024 archives, with some Himawari and GPM work extending into 2025.
- End goal: maintain validated local archives for heat, haze, precipitation, soil moisture, reanalysis, and climate-driver analysis.

## End-to-End Flows
1. Surface station ingest
- Raw inputs live in `station_data/YYYY/*.xlsx|*.xls|*.csv`.
- `step1_batch_ingest.py` normalizes schema drift, fixes hour-24 timestamps, and writes `station_data/malaysia_station_data_2020_2024_clean.parquet`.
- Main risk: source spreadsheets change column names and identifier fields across years.

2. Climate-driver pipeline
- `download_drivers.sh` downloads MJO, ENSO, IOD, and BSISO source files into `/mnt/AizatDrive/global_drivers/raw`.
- Current upstreams are BOM `clim_data` for MJO RMM, NOAA CPC ONI for ENSO, NOAA CPC seasonal DMI for IOD, and APCC monitoring for BSISO.
- `process_drivers.py` reads only the local raw files and emits per-driver metadata plus a yearly manifest under `/mnt/AizatDrive/global_drivers/processed`.
- Complete datasets write `name_2025.csv`; incomplete but usable windows write `name_2025_partial.csv`; missing datasets write metadata only.
- BSISO is seasonal in the APCC monitoring source, so its 2025 completeness window is `2025-05-01` through `2025-10-31`, not the full calendar year.
- `validate_drivers.py` reads that metadata first, fails closed in strict mode, and can optionally accept partial datasets with `--allow-partial`.

3. AMSR-2 archive
- `amsr2_config.py` holds the Malaysia domain, product selection, credentials, and local archive path.
- `download_amsr2_data.py` performs threaded SFTP download with retry and atomic writes; `download_amsr2.sh` is the shell entrypoint.
- `verify_amsr2_data.py` and `test_domain.py` validate completeness, integrity, and domain config.

4. Himawari and JAXA aerosol pipeline
- `download_himawari_integrated.py` combines AWS Himawari brightness temperatures with JAXA aerosol L3 files.
- `audit_download_himawari_parallel.py`, `repair_himawari.py`, `generate_missing_report_jaxa.py`, `clean_jaxa.py`, and `download_jaxa_surgical.py` form the recovery loop.
- Critical quirk: file naming changes from `H08` to `H09` on 2022-12-13, and JAXA aerosol files are only expected for 00-09 UTC.

5. Other satellite and reanalysis families
- GPM IMERG: `download_gpm_imerg_parallel_finalRun.py`, late-run variant, and `audit_gpm_imerg_parallel.py`.
- MODIS: `download_modis_terra.py`, `download_modis_aqua.py`, plus audit, purge, and fill-gap helpers.
- SMAP: `download_smap.py`, `download_smap_parallel.py`, and `audit_download_smap.py`.
- ERA5: `download_era5_land.py`, `download_era5_pressure.py`, `download_era5_supplement.py`, and `audit_download_era5_parallel.py`.

6. Integrity loop
- The recurring pattern is `download_* -> audit/verify_* -> repair/fill/clean_* -> rerun audit`.
- Most operational state lives in local files and logs, not in a service or database.
- Before changing recovery logic, read the matching log and audit report files for that script family.

## Repo Gotchas
- Many scripts write to external mount points under `/mnt/AizatDrive` or `/run/media/NWP5/One Touch`.
- Secrets and credentials are embedded in several legacy scripts; avoid spreading them further.
- This repo has many logs and reports. Use the generated `.harness/context/DEBUG_LEARNINGS.md` and `.harness/context/SCRIPT_CATALOG.md` before broad changes.

## Harness Use
- Run `bash scripts/check_arch_staleness.sh pre` before editing.
- Run `bash scripts/check_arch_staleness.sh post` after editing.
- Keep `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and `ANTIGRAVITY.md` short; push detail into generated context docs to avoid startup bloat.
- Read `.harness/context/HARNESS_GUARDRAILS.md` when planning broad, risky, rollback, dependency, or multi-agent work.
