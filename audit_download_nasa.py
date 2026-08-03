import os
import glob
import h5py
import re
from datetime import date, timedelta
import concurrent.futures
from tqdm import tqdm

# --- CONFIGURATION ---
BASE_DIR = "/mnt/AizatDrive/malaysia_amsr2_nasa"
START_DATE = date(2020, 1, 1)
END_DATE = date(2024, 12, 31)
MAX_WORKERS = 20  # Using your server's power

# --- 1. WORKER FUNCTION ---
def verify_nasa_file(filepath):
    """
    Validates a NASA NetCDF4 file.
    Returns: (status, filename, file_date, orbit_type)
    """
    filename = os.path.basename(filepath)
    
    # A. Physical Check
    if not os.path.exists(filepath):
        return ("MISSING", filepath, None, None)
    
    file_size = os.path.getsize(filepath)
    if file_size < 1024: # < 1KB is definitely corrupt
        return ("CORRUPT_SIZE", filename, None, None)

    # B. Metadata Extraction
    # Example: LPRM-AMSR2_DS_A_SOILM3_V001_20200101.nc4
    # Detect Date (YYYYMMDD)
    date_match = re.search(r'(20[2-3][0-9][0-1][0-9][0-3][0-9])', filename)
    file_date = None
    if date_match:
        try:
            d_str = date_match.group(1)
            file_date = date(int(d_str[:4]), int(d_str[4:6]), int(d_str[6:]))
        except:
            pass
            
    # Detect Orbit (A = Ascending, D = Descending)
    orbit = "UNKNOWN"
    if "_A_" in filename or "_A." in filename:
        orbit = "ASC"
    elif "_D_" in filename or "_D." in filename:
        orbit = "DESC"

    # C. Deep Structure Check (NetCDF4 is built on HDF5)
    try:
        # We try to open the file in Read mode. 
        # If the file is truncated (half-downloaded), this throws an OSError.
        with h5py.File(filepath, 'r') as f:
            # Try to read the keys (variables) to ensure the header is good
            _ = list(f.keys())
    except OSError:
        return ("CORRUPT_HEADER", filename, file_date, orbit)
    except Exception as e:
        return ("CORRUPT_UNKNOWN", f"{filename} ({str(e)})", file_date, orbit)

    return ("VALID", filename, file_date, orbit)

# --- 2. MAIN LOGIC ---
def main():
    print("="*60)
    print("  NASA MAXIMUM INTEGRITY AUDIT (ASC/DESC CHECK)")
    print("="*60)

    # Gather files
    all_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        for file in files:
            if file.endswith(".nc4") or file.endswith(".nc"):
                all_files.append(os.path.join(root, file))

    if not all_files:
        print("[!] No NetCDF files found in directory.")
        return

    print(f"Scanning {len(all_files)} files using {MAX_WORKERS} threads...")

    # Storage for results
    results_asc = set()
    results_desc = set()
    corrupt_files = []

    # Parallel Execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        audit_results = list(tqdm(
            executor.map(verify_nasa_file, all_files), 
            total=len(all_files), 
            unit="file"
        ))

    # Processing
    for status, name, fdate, orbit in audit_results:
        if status == "VALID":
            if orbit == "ASC" and fdate:
                results_asc.add(fdate)
            elif orbit == "DESC" and fdate:
                results_desc.add(fdate)
        else:
            corrupt_files.append(f"[{status}] {name}")

    # Coverage Math
    total_days = (END_DATE - START_DATE).days + 1
    
    # Calculate Missing Dates
    missing_asc = []
    missing_desc = []
    current = START_DATE
    while current <= END_DATE:
        if current not in results_asc: missing_asc.append(current)
        if current not in results_desc: missing_desc.append(current)
        current += timedelta(days=1)

    # --- REPORT ---
    print("\n" + "="*60)
    print("  NASA AUDIT RESULTS")
    print("="*60)
    print(f"Total Files Scanned: {len(all_files)}")
    print(f"Corrupt Files:       {len(corrupt_files)}")
    
    print("-" * 30)
    print(f"ORBIT: ASCENDING (Day)  | Found: {len(results_asc)}/{total_days} days")
    print(f"Coverage: {(len(results_asc)/total_days)*100:.2f}%")
    if missing_asc:
        print(f"Missing ({len(missing_asc)}): {missing_asc[0]} ... {missing_asc[-1]}")
    
    print("-" * 30)
    print(f"ORBIT: DESCENDING (Night)| Found: {len(results_desc)}/{total_days} days")
    print(f"Coverage: {(len(results_desc)/total_days)*100:.2f}%")
    if missing_desc:
        print(f"Missing ({len(missing_desc)}): {missing_desc[0]} ... {missing_desc[-1]}")
    
    print("-" * 30)

    if corrupt_files:
        print("\n[!] CRITICAL: CORRUPT FILES FOUND")
        for f in corrupt_files:
            print(f"  - {f}")
        print("\nSolution: Delete these files and re-run download_nasa.py.")
    else:
        print("\n[OK] No file corruption detected.")

if __name__ == "__main__":
    main()