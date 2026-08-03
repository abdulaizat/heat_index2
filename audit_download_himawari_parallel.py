import os
import sys
import datetime
import argparse
import logging
import multiprocessing
import pandas as pd
import xarray as xr
import glob

# --- Configuration ---
LOCAL_BASE_DIR = "/mnt/AizatDrive/himawari_data"
REPORT_FILE = "himawari_audit_report.csv"
LOG_FILE = "himawari_audit.log"

# Transition Date (Critical for Filename Logic)
TRANSITION_DATE = datetime.date(2022, 12, 13)

# Hardware Tuning
MAX_WORKERS = 16  # High CPU usage for fast reading

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger()

def get_expected_sat_id(date_obj):
    if date_obj < TRANSITION_DATE:
        return "H08"
    return "H09"

def check_file_integrity(filepath, required_vars):
    """
    Opens file, checks for corruption, verifies variables.
    Returns: (Status Code, Message)
    Status Codes: 0=Good, 1=Missing, 2=Corrupt, 3=MissingVars
    """
    if not os.path.exists(filepath):
        return 1, "File Not Found"
    
    # Check File Size (Empty file check)
    if os.path.getsize(filepath) < 1024:
        return 2, "File Empty/Too Small"

    try:
        # Deep check: Open with Xarray
        with xr.open_dataset(filepath) as ds:
            # Check for required variables
            missing = [v for v in required_vars if v not in ds.variables]
            if missing:
                return 3, f"Missing Vars: {missing}"
            
            # Optional: Check if data is not all NaN (Expensive, enables if needed)
            # if ds[required_vars[0]].isnull().all():
            #     return 4, "Data All NaN"
                
    except Exception as e:
        return 2, f"Corrupt/Unreadable: {e}"

    return 0, "OK"

def audit_hour(args):
    """
    Worker function to audit a single hour.
    """
    date_obj, hour = args
    yyyy = date_obj.strftime("%Y")
    mm = date_obj.strftime("%m")
    dd = date_obj.strftime("%d")
    hh = f"{hour:02d}"
    
    day_dir = os.path.join(LOCAL_BASE_DIR, yyyy, mm, dd)
    sat_id = get_expected_sat_id(date_obj)
    
    # --- 1. Audit AWS (Heat Movie) ---
    # Expected: LST_H0x_YYYYMMDD_HH00_Malaysia.nc
    aws_filename = f"LST_{sat_id}_{yyyy}{mm}{dd}_{hh}00_Malaysia.nc"
    aws_path = os.path.join(day_dir, aws_filename)
    
    aws_status, aws_msg = check_file_integrity(aws_path, ['T_10_4', 'T_11_2'])

    # --- 2. Audit JAXA (Haze Switch) ---
    # Only checks 00-09 UTC. Nighttime is N/A.
    jaxa_status = -1 # N/A
    jaxa_msg = "Nighttime"
    
    if 0 <= hour <= 9:
        # JAXA filenames are tricky (versions). We use glob to find the L3 file.
        # Pattern: L3_H0x_YYYYMMDD_HH00_*.nc
        search_pattern = os.path.join(day_dir, f"L3_*{yyyy}{mm}{dd}_{hh}00_*.nc")
        candidates = glob.glob(search_pattern)
        
        if not candidates:
            jaxa_status = 1
            jaxa_msg = "File Not Found"
        else:
            # Take the first match (usually only one)
            jaxa_path = candidates[0]
            jaxa_status, jaxa_msg = check_file_integrity(jaxa_path, ['AOT_Haze_Switch'])

    return {
        "Date": date_obj,
        "Hour": hour,
        "Sat_ID": sat_id,
        "AWS_Status": aws_status,
        "AWS_Msg": aws_msg,
        "JAXA_Status": jaxa_status,
        "JAXA_Msg": jaxa_msg,
        "Path_AWS": aws_path if aws_status != 1 else "",
        "Path_JAXA": candidates[0] if (0 <= hour <= 9 and candidates) else ""
    }

def main():
    parser = argparse.ArgumentParser(description="Forensic Integrity Audit")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args()

    s = datetime.datetime.strptime(args.start, "%Y-%m-%d").date()
    e = datetime.datetime.strptime(args.end, "%Y-%m-%d").date()

    # Generate Task List
    tasks = []
    current = s
    while current <= e:
        for h in range(24):
            tasks.append((current, h))
        current += datetime.timedelta(days=1)

    logger.info(f"--- STARTING OMEGA AUDIT ---")
    logger.info(f"Scanning {len(tasks)} hours of data using {MAX_WORKERS} cores.")
    
    results = []
    
    # Run Parallel Audit
    with multiprocessing.Pool(processes=MAX_WORKERS) as pool:
        for i, res in enumerate(pool.imap(audit_hour, tasks, chunksize=100)):
            results.append(res)
            if i % 1000 == 0:
                print(f"Scanned {i}/{len(tasks)} hours...", end='\r')

    print(f"\nScan Complete. Compiling Report...")
    
    # Convert to DataFrame
    df = pd.DataFrame(results)
    
    # --- STATISTICS ---
    total = len(df)
    aws_missing = len(df[df['AWS_Status'] == 1])
    aws_corrupt = len(df[df['AWS_Status'] == 2])
    aws_badvar = len(df[df['AWS_Status'] == 3])
    aws_good = len(df[df['AWS_Status'] == 0])
    
    # Filter JAXA to daytime only for stats
    jaxa_day = df[df['JAXA_Status'] != -1]
    jaxa_total = len(jaxa_day)
    jaxa_missing = len(jaxa_day[jaxa_day['JAXA_Status'] == 1])
    jaxa_corrupt = len(jaxa_day[jaxa_day['JAXA_Status'] == 2])
    jaxa_good = len(jaxa_day[jaxa_day['JAXA_Status'] == 0])

    # Log Summary
    logger.info("="*40)
    logger.info("       AUDIT SUMMARY REPORT       ")
    logger.info("="*40)
    logger.info(f"Total Hours Scanned: {total}")
    logger.info("-" * 20)
    logger.info(f"AWS (Heat Movie):")
    logger.info(f"  OK:      {aws_good} ({(aws_good/total)*100:.2f}%)")
    logger.info(f"  MISSING: {aws_missing}")
    logger.info(f"  CORRUPT: {aws_corrupt}")
    logger.info(f"  BAD VAR: {aws_badvar}")
    logger.info("-" * 20)
    logger.info(f"JAXA (Haze Switch) [Daytime Only]:")
    logger.info(f"  OK:      {jaxa_good} ({(jaxa_good/jaxa_total)*100:.2f}%)")
    logger.info(f"  MISSING: {jaxa_missing}")
    logger.info(f"  CORRUPT: {jaxa_corrupt}")
    logger.info("="*40)

    # Save CSV
    df.to_csv(REPORT_FILE, index=False)
    logger.info(f"Detailed report saved to: {REPORT_FILE}")
    
    # Check for "PERFECT SCORE"
    if aws_missing == 0 and aws_corrupt == 0 and jaxa_missing == 0 and jaxa_corrupt == 0:
        logger.info("RESULT: *** PERFECT INTEGRITY ***")
    else:
        logger.warning("RESULT: ISSUES FOUND. See report.")

if __name__ == "__main__":
    main()