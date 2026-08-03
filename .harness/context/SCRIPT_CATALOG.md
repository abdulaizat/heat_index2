# Script Catalog

- Updated at: 2026-06-04T03:19:04.235542+00:00

## Acquisition
- `download_amsr2.sh`: AMSR-2 Data Download Script
- `download_amsr2_data.py`: AMSR-2 Microwave Data Downloader for G-Portal (JAXA)
- `download_drivers.sh`: Directory for raw data
- `download_era5_land.py`: Download era5 land
- `download_era5_pressure.py`: Download era5 pressure
- `download_era5_supplement.py`: Download era5 supplement
- `download_gpm_imerg_parallel_finalRun.py`: GPM IMERG Final Run (Half-Hourly) Download Script
- `download_gpm_imerg_parallel_lateRun.py`: GPM IMERG " MODE" Downloader (Late Run 2025)
- `download_himawari_arp.py`: Download himawari arp
- `download_himawari_integrated.py`: Download himawari integrated
- `download_himawari_parallel.py`: Download himawari parallel
- `download_jaxa.py`: Download jaxa
- `download_jaxa_parallel.py`: Download jaxa parallel
- `download_jaxa_surgical.py`: Download jaxa surgical
- `download_modis_aqua.py`: Download modis aqua
- `download_modis_terra.py`: Download modis terra
- `download_nasa.py`: Download nasa
- `download_smap.py`: SMAP L4 Soil Moisture Download Script - Robust Version
- `download_smap_parallel.py`: SMAP L4 High-Performance Downloader (Xeon/Rocky Linux Optimized)

## Audit
- `audit_download_era5_parallel.py`: ================================================================================
- `audit_download_himawari_parallel.py`: Audit download himawari parallel
- `audit_download_jaxa_parallel.py`: Audit download jaxa parallel
- `audit_download_modis_aqua_parallel.py`: Audit download modis aqua parallel
- `audit_download_modis_terra_parallel.py`: Audit download modis terra parallel
- `audit_download_nasa.py`: Audit download nasa
- `audit_download_smap.py`: SMAP L4 Soil Moisture Data Integrity Audit Script
- `audit_gpm_imerg_parallel.py`: GPM IMERG Forensic Audit V3 (Variable Agnostic & Optimized)

## Processing
- `process_drivers.py`: Process drivers
- `step1_batch_ingest.py`: Step1 batch ingest

## Repair
- `clean_jaxa.py`: Clean jaxa
- `fix_progress_json.py`: Fix progress json
- `generate_missing_report_jaxa.py`: Generate missing report jaxa
- `repair_himawari.py`: Repair himawari

## Utility
- `amsr2_config.py`: AMSR-2 Configuration Module
- `dem_verification_epsg_code.py`: Dem verification epsg code
- `inspect_variables.py`: Inspect variables
- `modis_terra_check_coverage.py`: Modis terra check coverage
- `modis_terra_fill_gaps.py`: Modis terra fill gaps
- `modis_terra_purge_corrupt.py`: Modis terra purge corrupt
- `scripts/__init__.py`: Harness utilities for Sync Quad agent session refresh in heat_index2.
- `scripts/build_agent_context.py`: Build compact repo context for Sync Quad agent session refresh.
- `scripts/post_session.sh`: Post session
- `scripts/pre_session.sh`: Pre session
- `scripts/resource_profile.sh`: Resource profile
- `scripts/sync_quad_agent_docs.py`: Keep the root Sync Quad agent instruction files identical.
- `scripts/sync_tri_agent_docs.py`: Compatibility wrapper for the Sync Quad agent doc sync.

## Validation
- `check_harmony.py`: Check harmony
- `scripts/check_arch_staleness.sh`: Check arch staleness
- `test_domain.py`: AMSR-2 Domain Test Script
- `tests/test_audit_gpm_imerg_parallel.py`: Test audit gpm imerg parallel
- `tests/test_download_gpm_imerg_parallel_finalRun.py`: Test download gpm imerg parallel finalRun
- `tests/test_process_drivers_bsiso.py`: Test process drivers bsiso
- `tests/test_process_drivers_status.py`: Test process drivers status
- `tests/test_quad_agent_harness.py`: Sync Quad agent harness tests.
- `validate_drivers.py`: Validate drivers
- `verify_amsr2_data.py`: AMSR-2 Data Verification Script
