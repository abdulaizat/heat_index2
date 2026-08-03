# Debug Learnings

- Updated at: 2026-06-04T03:19:04.235838+00:00
- Source window: last 12 modified `.log` files, last 400 lines each.

## Recurring Patterns
- `CORRUPT: <n>` | count=12 | sources: himawari_audit.log x10, audit_download_himawari_parallel_2025.log x2
- `MISSING: <n>` | count=12 | sources: himawari_audit.log x10, audit_download_himawari_parallel_2025.log x2
- `❌ MISSING: <n>` | count=7 | sources: gpm_imerg_audit_v3.log x6, audit_gpm_imerg_parallel.log x1
- `💀 CORRUPT: <n>` | count=7 | sources: gpm_imerg_audit_v3.log x6, audit_gpm_imerg_parallel.log x1
- `RESULT: ISSUES FOUND. See report.` | count=6 | sources: himawari_audit.log x5, audit_download_himawari_parallel_2025.log x1
- `[PID:<n>] FTP Connect Error: timed out` | count=3 | sources: himawari_omega.log x3
- `[PID:<n>] INFO - Failed: <n>` | count=3 | sources: download_gpm_imerg.log x1, download_gpm_imerg_parallel_finalRun2.log x1, download_gpm_imerg_late.log x1
- `CRITICAL: No files found in directory tree!` | count=1 | sources: gpm_imerg_audit_v3.log x1
- `Corrupt Files: <n>` | count=1 | sources: audit_download_jaxa_parallel2.log x1
- `Quarantined invalid file /tmp/tmp5ohukwdw/broken.HDF5 -> /tmp/tmp5ohukwdw/broken.HDF5.corrupt.<n> (invalid_hdf5_signature)` | count=1 | sources: gpm_imerg_audit_v3.log x1
- `Quarantined invalid file /tmp/tmp8epbs268/broken.HDF5 -> /tmp/tmp8epbs268/broken.HDF5.corrupt.<n> (invalid_hdf5_signature)` | count=1 | sources: gpm_imerg_audit_v3.log x1
- `[<n>/<n>] <n>-<n>-<n> <n>:<n> -> AWS: Missing | JAXA: Busy` | count=1 | sources: download_himawari_parallel_2025.log x1
- `[PID:<n>] WARNING - Failed granules: <n>` | count=1 | sources: download_gpm_imerg_late.log x1
- `[PID:<n>] WARNING - Quarantined invalid file /tmp/tmp5ohukwdw/broken.HDF5 -> /tmp/tmp5ohukwdw/broken.HDF5.corrupt.<n> (invalid_hdf5_signature)` | count=1 | sources: download_gpm_imerg.log x1
- `[PID:<n>] WARNING - Quarantined invalid file /tmp/tmp8epbs268/broken.HDF5 -> /tmp/tmp8epbs268/broken.HDF5.corrupt.<n> (invalid_hdf5_signature)` | count=1 | sources: download_gpm_imerg.log x1

## Logs Seen
- `gpm_imerg_audit_v3.log`
- `download_gpm_imerg.log`
- `audit_gpm_imerg_parallel.log`
- `download_gpm_imerg_parallel_finalRun2.log`
- `download_himawari_parallel_2025.log`
- `himawari_omega.log`
- `audit_download_himawari_parallel_2025.log`
- `himawari_audit.log`
- `dem_verification_epsg_code.log`
- `download_gpm_imerg_parallel_lateRun.log`
- `download_gpm_imerg_late.log`
- `audit_download_jaxa_parallel2.log`
