import os
import json
import glob

# CONFIGURATION
BASE_OUTPUT_DIR = "/mnt/AizatDrive/smap_malaysia_subset_v8"
PROGRESS_FILE = os.path.join(BASE_OUTPUT_DIR, "download_progress.json")

def update_progress():
    # 1. Load existing progress
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = {"completed_months": [], "failed_months": [], "downloaded_files": []}

    original_count = len(data['completed_months'])
    
    # 2. Scan directories
    print(f"Scanning {BASE_OUTPUT_DIR}...")
    found_months = set(data['completed_months'])
    
    # Check years 2020 to 2025
    for year in range(2020, 2026):
        year_dir = os.path.join(BASE_OUTPUT_DIR, str(year))
        if not os.path.exists(year_dir):
            continue
            
        for month in range(1, 13):
            month_str = f"{month:02d}"
            month_dir = os.path.join(year_dir, month_str)
            
            if os.path.exists(month_dir):
                # Count .nc4 files
                files = glob.glob(os.path.join(month_dir, "*.nc4"))
                
                # If we have files (usually > 200 for a month, or > 28 for daily)
                # But since this is a recovery script, if we have > 0 we assume it was attempted
                if len(files) > 0:
                    key = f"{year}-{month_str}"
                    if key not in found_months:
                        print(f"  Found data for {key} ({len(files)} files) - Adding to completed list.")
                        found_months.add(key)

    # 3. Save updates
    data['completed_months'] = sorted(list(found_months))
    
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        
    print("-" * 30)
    print(f"Updated completed_months: {original_count} -> {len(data['completed_months'])}")
    print("Run download_smap.py again, and it should now skip these months.")

if __name__ == "__main__":
    update_progress()