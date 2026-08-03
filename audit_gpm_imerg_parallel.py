#!/usr/bin/env python3
"""
GPM IMERG Forensic Audit V3 (Variable Agnostic & Optimized)
===========================================================
STATUS: FIXED for V07B (Detects 'Grid/precipitation')
ARCHITECTURE: Intel Xeon Gold 5115 (16 Workers)

Updates in V3:
1. TARGET UPDATE: Prioritizes 'Grid/precipitation' based on your logs.
2. HYBRID DISCOVERY: Checks for both 'precipitation' and 'precipitationCal'.
3. INTEL OPTIMIZATION: Uses 16 cores for high-speed HDF5 decoding.

Author: Auto-generated for Zero Death Heat Index Project
"""

import os
import sys
import glob
import logging
import argparse
import datetime
import multiprocessing
from pathlib import Path
import numpy as np
import pandas as pd
import h5py
import warnings

# Suppress H5py warnings
warnings.filterwarnings("ignore")

# =============================================================================
# CONFIGURATION
# =============================================================================
DEFAULT_BASE_OUTPUT_DIR = "/mnt/AizatDrive/gpm_imerg_precipitation_final_run/2024"
REPORT_FILE = "gpm_imerg_audit_report_v3.csv"
LOG_FILE = "gpm_imerg_audit_v3.log"

# Hardware Tuning
IO_WORKER_CAP = 3
MAX_WORKERS = IO_WORKER_CAP

# =============================================================================
# LOGGING SETUP
# =============================================================================
LOGGER_HANDLER_MARKER = "_heat_index2_gpm_imerg_audit"


def setup_logging():
    """Configure audit logging without dirtying repo logs during imports."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if any(getattr(handler, LOGGER_HANDLER_MARKER, False) for handler in root_logger.handlers):
        return logging.getLogger(__name__)

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    setattr(file_handler, LOGGER_HANDLER_MARKER, True)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    setattr(console_handler, LOGGER_HANDLER_MARKER, True)
    root_logger.addHandler(console_handler)

    return logging.getLogger(__name__)


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def resolve_worker_count(requested_workers: int) -> int:
    """Clamp worker count to the repo's I/O safety cap."""
    return max(1, min(int(requested_workers), IO_WORKER_CAP))


def infer_archive_year(base_dir: str) -> int:
    """Infer the target archive year from the audit root path or its child year directory."""
    base_path = Path(base_dir)

    if base_path.name.isdigit() and len(base_path.name) == 4:
        return int(base_path.name)

    year_dirs = sorted(
        int(path.name)
        for path in base_path.iterdir()
        if path.is_dir() and path.name.isdigit() and len(path.name) == 4
    )
    if len(year_dirs) == 1:
        return year_dirs[0]

    raise ValueError(
        f"Could not infer a single archive year from {base_dir}. "
        f"Pass --start and --end explicitly."
    )


def default_date_range(base_dir: str) -> tuple[str, str]:
    """Build a calendar-year audit window from the archive root."""
    year = infer_archive_year(base_dir)
    return f"{year}-01-01", f"{year}-12-31"

# =============================================================================
# SMART AUTO-DISCOVERY
# =============================================================================
def discover_structure(sample_file):
    """
    Intelligently finds the precipitation variable.
    Priority:
    1. Grid/precipitation (Your V07B structure)
    2. Grid/precipitationCal (Standard V06/V07 structure)
    3. precipitation (Root level)
    """
    logger.info(f"Inspecting sample file: {os.path.basename(sample_file)}")
    try:
        with h5py.File(sample_file, 'r') as f:
            # Priority List based on your logs
            candidates = [
                'Grid/precipitation',          # Found in your log
                'Grid/precipitationCal',       # Old standard
                '/Grid/precipitation',
                '/Grid/precipitationCal',
                'precipitation',
                'precipitationCal'
            ]
            
            for c in candidates:
                if c in f:
                    # Double check it is a Dataset, not a Group
                    if isinstance(f[c], h5py.Dataset):
                        logger.info(f"  -> MATCH: Found variable at '{c}'")
                        return c
            
            # Deep Search if standard paths fail
            logger.warning("  -> Standard paths failed. Deep scanning...")
            found = None
            def visitor(name, node):
                nonlocal found
                # Look for any dataset ending in 'precipitation' or 'precipitationCal'
                if isinstance(node, h5py.Dataset):
                    if name.endswith("precipitation") or name.endswith("precipitationCal"):
                        found = name
                        return True
            
            f.visititems(visitor)
            
            if found:
                logger.info(f"  -> DEEP DISCOVERY: Found '{found}'")
                return found
            else:
                logger.error("  -> CRITICAL: No precipitation variable found.")
                logger.error("     Keys found:")
                f.visit(lambda n: logger.error(f"     - {n}"))
                return None
                
    except Exception as e:
        logger.error(f"  -> Inspection failed: {e}")
        return None

# =============================================================================
# AUDIT WORKER
# =============================================================================
def check_file_integrity(filepath, var_path):
    """
    Deep verification of the file.
    Status Codes:
    0 = OK
    2 = Corrupt
    3 = Structure Error
    4 = Physics Error (Negative Rain)
    5 = Warning (All Masked)
    """
    stats = {'min': np.nan, 'max': np.nan, 'mean': np.nan}
    
    try:
        # Check 1: File Size
        if os.path.getsize(filepath) < 10240:
            return 2, "File too small (<10KB)", stats

        # Check 2: Open HDF5
        with h5py.File(filepath, 'r') as f:
            if var_path not in f:
                return 3, f"Variable '{var_path}' missing", stats
            
            dset = f[var_path]
            
            # Check 3: Read Data (I/O Stress Test)
            try:
                data = dset[:]
            except Exception:
                return 2, "I/O Error reading data block", stats

            # Filter Fill Values
            # GPM fill value is often -9999.9
            fill_val = dset.attrs.get('_FillValue', -9999.9)
            
            if np.isnan(fill_val):
                mask = ~np.isnan(data)
            else:
                mask = (data != fill_val)
            
            valid_data = data[mask]
            
            # Check if all data is masked (e.g. over ocean if land-only, or just empty)
            if valid_data.size == 0:
                return 5, "All pixels are FillValue", stats
            
            # Check 4: Physics
            v_min = float(np.min(valid_data))
            v_max = float(np.max(valid_data))
            v_mean = float(np.mean(valid_data))
            
            stats = {'min': v_min, 'max': v_max, 'mean': v_mean}
            
            # GPM values should not be negative (0 is min)
            if v_min < 0:
                return 4, f"Negative Rain Detected ({v_min})", stats

    except OSError:
        return 2, "File Corrupt (HDF5 Header Invalid)", stats
    except Exception as e:
        return 2, f"Exception: {str(e)}", stats

    return 0, "OK", stats

def audit_slot(args):
    """Worker process for parallel execution."""
    target_time, base_dir, var_path = args
    
    # Directory: YYYY/MM/DD
    year = target_time.strftime("%Y")
    month = target_time.strftime("%m")
    day = target_time.strftime("%d")
    dir_path = os.path.join(base_dir, year, month, day)
    
    # Filename Matcher: *YYYYMMDD-S{HH}{MM}00*
    date_str = target_time.strftime("%Y%m%d")
    time_str = target_time.strftime("S%H%M00")
    pattern = f"*{date_str}-{time_str}*"
    
    result = {
        "timestamp": target_time.isoformat(),
        "status_code": 1,
        "status_msg": "File Not Found",
        "file_path": "",
        "val_mean": None
    }
    
    if os.path.exists(dir_path):
        full_pattern = os.path.join(dir_path, pattern)
        candidates = glob.glob(full_pattern)
        
        # Filter for valid HDF5 extensions
        valid_exts = ['.HDF5', '.h5', '.nc4']
        candidates = [c for c in candidates if any(c.endswith(ext) for ext in valid_exts)]
        
        if candidates:
            # Pick largest if duplicates exist
            target_file = max(candidates, key=os.path.getsize)
            result["file_path"] = target_file
            
            code, msg, stats = check_file_integrity(target_file, var_path)
            result["status_code"] = code
            result["status_msg"] = msg
            result["val_mean"] = stats['mean']

    return result

# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
def main():
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default=DEFAULT_BASE_OUTPUT_DIR)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--report-file", default=None)
    args = parser.parse_args()

    base_dir = args.base_dir
    if not os.path.exists(base_dir):
        logger.error(f"CRITICAL: Base directory does not exist: {base_dir}")
        return

    if args.start and args.end:
        start_str = args.start
        end_str = args.end
    else:
        start_str, end_str = default_date_range(base_dir)

    start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d")
    end_dt = datetime.datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=30)
    workers = resolve_worker_count(args.workers)
    if workers != args.workers:
        logger.warning(
            f"Requested {args.workers} workers, capped to {workers} "
            f"to respect the repo I/O safety limit."
        )

    archive_year = infer_archive_year(base_dir)
    report_file = args.report_file or f"gpm_imerg_audit_report_{archive_year}.csv"
    
    logger.info("=" * 60)
    logger.info("       GPM IMERG FORENSIC AUDIT V3 (V07B ADAPTED)       ")
    logger.info("=" * 60)
    logger.info(f"Base Dir: {base_dir}")
    logger.info(f"Audit Window: {start_dt.date()} to {end_dt.date()}")
    
    # 1. AUTO-DISCOVERY
    sample_files = glob.glob(os.path.join(base_dir, "**", "*.HDF5"), recursive=True)
    if not sample_files:
        sample_files = glob.glob(os.path.join(base_dir, "**", "*.h5"), recursive=True)
    if not sample_files:
        sample_files = glob.glob(os.path.join(base_dir, "**", "*.nc4"), recursive=True)
    
    if not sample_files:
        logger.error("CRITICAL: No files found in directory tree!")
        return
        
    discovered_path = discover_structure(sample_files[0])
    if not discovered_path:
        logger.error("ABORTING: Could not identify valid precipitation variable.")
        return

    logger.info(f"Using Target Variable: '{discovered_path}'")
    logger.info(f"Workers: {workers}")
    
    # 2. TASK GENERATION
    tasks = []
    current = start_dt
    while current <= end_dt:
        tasks.append((current, base_dir, discovered_path))
        current += datetime.timedelta(minutes=30)
    
    total_tasks = len(tasks)
    logger.info(f"Audit Scope: {total_tasks} slots")
    
    # 3. PARALLEL EXECUTION
    results = []
    logger.info("Starting Parallel Scan...")
    
    with multiprocessing.Pool(processes=workers) as pool:
        for i, res in enumerate(pool.imap(audit_slot, tasks, chunksize=50)):
            results.append(res)
            if i % 1000 == 0:
                print(f"Progress: {i}/{total_tasks} ({i/total_tasks:.1%})", end='\r')
    
    print(f"Progress: {total_tasks}/{total_tasks} (100.0%)")
    
    # 4. REPORT
    df = pd.DataFrame(results)
    
    missing = len(df[df['status_code'] == 1])
    corrupt = len(df[df['status_code'] == 2])
    struct_err = len(df[df['status_code'] == 3])
    physics_err = len(df[df['status_code'] == 4])
    ok = len(df[df['status_code'] == 0]) + len(df[df['status_code'] == 5])
    
    logger.info("\n" + "=" * 60)
    logger.info("             FINAL INTEGRITY REPORT                 ")
    logger.info("=" * 60)
    logger.info(f"Total Scanned:   {len(df)}")
    logger.info("-" * 40)
    logger.info(f"✅ OK:             {ok}")
    logger.info(f"❌ MISSING:        {missing}")
    logger.info(f"💀 CORRUPT:        {corrupt + struct_err + physics_err}")
    logger.info("=" * 60)
    
    df.to_csv(report_file, index=False)
    logger.info(f"Report saved: {report_file}")

if __name__ == "__main__":
    main()
