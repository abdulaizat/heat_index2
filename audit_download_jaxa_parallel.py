import os
import h5py
import re
import calendar
import concurrent.futures
from datetime import date, timedelta
from tqdm import tqdm
from collections import defaultdict

# --- CONFIGURATION ---
BASE_DIR = "/mnt/AizatDrive/malaysia_amsr2_jaxa_fedeo"
START_YEAR = 2020
END_YEAR = 2024
MAX_WORKERS = 20  # Matches your server core count

# The 3 sub-folders created by the download script
PRODUCT_FOLDERS = ["23GHz", "89GHz", "SMC"]

# --- 1. WORKER FUNCTION (Deep Verification) ---
def verify_file_integrity(file_info):
    """
    Opens file, checks HDF5 structure, extracts date.
    Args:
        file_info: tuple (product_name, full_path)
    Returns:
        tuple: (status, product_name, date_obj, filename)
    """
    product, filepath = file_info
    filename = os.path.basename(filepath)
    
    # 1. Physical Check
    if not os.path.exists(filepath):
        return ("MISSING", product, None, filename)
    
    # 2. Size Check (Empty file detection)
    if os.path.getsize(filepath) < 2048: # < 2KB is suspicious for HDF5
        return ("CORRUPT_SIZE", product, None, filename)

    # 3. Date Extraction (Regex: YYYYMMDD)
    # Matches GW1AM2_20200620_...
    match = re.search(r'_(\d{8})_', filename)
    file_date = None
    if match:
        try:
            d_str = match.group(1)
            file_date = date(int(d_str[:4]), int(d_str[4:6]), int(d_str[6:]))
        except ValueError:
            return ("INVALID_DATE_FORMAT", product, None, filename)
    else:
        return ("NO_DATE_IN_NAME", product, None, filename)

    # 4. Deep HDF5 Structure Check
    try:
        # Opening in 'r' mode reads the file header
        with h5py.File(filepath, 'r') as f:
            # Try to read the root keys. If file is truncated, this often fails.
            _ = list(f.keys())
    except OSError:
        return ("CORRUPT_HEADER", product, file_date, filename)
    except Exception as e:
        return ("CORRUPT_UNKNOWN", product, file_date, filename)

    return ("VALID", product, file_date, filename)

# --- 2. MAIN LOGIC ---
def main():
    print("="*80)
    print("  MAXIMUM ROBUSTNESS: MONTH-BY-MONTH JAXA AUDIT")
    print(f"  Scope: {START_YEAR} to {END_YEAR} | Threads: {MAX_WORKERS}")
    print("="*80)

    # A. Gather all file paths
    tasks = []
    print("[1/4] Scanning file system...")
    for product in PRODUCT_FOLDERS:
        folder_path = os.path.join(BASE_DIR, product)
        if not os.path.exists(folder_path):
            print(f"  [!] Missing folder: {folder_path}")
            continue
            
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.endswith(".h5"):
                    tasks.append((product, os.path.join(root, file)))

    if not tasks:
        print("[!] No files found. Check your directory.")
        return

    print(f"  > Found {len(tasks)} files total.")

    # B. Parallel Execution
    print(f"[2/4] Verifying HDF5 Integrity (Deep Scan)...")
    
    # Database: inventory[product][date] = count_of_files (Asc + Desc = 2 ideally)
    inventory = {p: defaultdict(int) for p in PRODUCT_FOLDERS}
    corrupt_files = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Map tasks to the executor
        results = list(tqdm(
            executor.map(verify_file_integrity, tasks), 
            total=len(tasks),
            unit="file"
        ))

    # C. Process Results
    print("[3/4] Aggregating Temporal Data...")
    for status, product, f_date, fname in results:
        if status == "VALID" and f_date:
            # We filter by year range requested
            if START_YEAR <= f_date.year <= END_YEAR:
                inventory[product][f_date] += 1
        elif "CORRUPT" in status:
            corrupt_files.append(f"[{product}] {fname} ({status})")

    # D. Month-by-Month Reporting
    print("\n" + "="*80)
    print(f"{'YEAR-MONTH':<12} | {'23GHz':<15} | {'89GHz':<15} | {'SMC':<15} | {'STATUS'}")
    print("-" * 80)

    total_months = 0
    perfect_months = 0

    # Iterate through every requested month
    for year in range(START_YEAR, END_YEAR + 1):
        for month in range(1, 13):
            total_months += 1
            
            # Determine how many days in this specific month
            _, num_days = calendar.monthrange(year, month)
            start_d = date(year, month, 1)
            end_d = date(year, month, num_days)
            
            # Check coverage for each product
            row_stats = []
            is_month_perfect = True
            
            for prod in PRODUCT_FOLDERS:
                days_found = 0
                current_d = start_d
                while current_d <= end_d:
                    # We consider the day "Covered" if we have at least 1 file (Asc or Desc)
                    if inventory[prod].get(current_d, 0) > 0:
                        days_found += 1
                    current_d += timedelta(days=1)
                
                pct = (days_found / num_days) * 100
                
                # Formatting output
                if pct == 100:
                    display_str = "OK (100%)"
                elif pct == 0:
                    display_str = "! MISSING !"
                    is_month_perfect = False
                else:
                    display_str = f"{pct:.0f}% ({days_found}/{num_days})"
                    is_month_perfect = False
                
                row_stats.append(display_str)

            # Print Row
            month_label = f"{year}-{month:02d}"
            status_icon = "✅" if is_month_perfect else "⚠️"
            if "MISSING" in row_stats[0] and "MISSING" in row_stats[1]:
                status_icon = "❌"

            print(f"{month_label:<12} | {row_stats[0]:<15} | {row_stats[1]:<15} | {row_stats[2]:<15} | {status_icon}")
            
            if is_month_perfect:
                perfect_months += 1

    # --- FINAL SUMMARY ---
    print("="*80)
    print("  FINAL INTEGRITY REPORT")
    print("="*80)
    print(f"Total Files Verified: {len(tasks)}")
    print(f"Corrupt Files:        {len(corrupt_files)}")
    print(f"Perfect Months:       {perfect_months}/{total_months}")
    
    if corrupt_files:
        print("\n[!] CRITICAL: THE FOLLOWING FILES ARE CORRUPT AND MUST BE DELETED:")
        for cf in corrupt_files:
            print(f"  -> {cf}")
            # Suggest command
            # path = cf.split(" ")[1]
            # print(f"     rm {path}")
    else:
        print("\n[OK] File structure integrity is 100%. No corruption detected.")

    if perfect_months < total_months:
        print("\n[ACTION REQUIRED] Run 'download_jaxa_monthly.py' again to fill the gaps marked with ⚠️ or ❌.")

if __name__ == "__main__":
    main()