import os
import re
from datetime import datetime, timedelta

# CONFIGURATION
DOWNLOAD_ROOT = "/mnt/AizatDrive"
MOD11A1_DIR = os.path.join(DOWNLOAD_ROOT, "MOD11A1")
MOD13A2_DIR = os.path.join(DOWNLOAD_ROOT, "MOD13A2")

START_DATE = datetime(2020, 1, 1)
END_DATE = datetime(2024, 12, 31)

def parse_modis_date(filename):
    """
    Extracts date from MODIS filename.
    Format: MOD11A1.A2020001.h28v08...
    Returns: datetime object or None
    """
    # Regex to find AYYYYDDD (Year + Julian Day)
    match = re.search(r'\.A(\d{4})(\d{3})\.', filename)
    if match:
        year = int(match.group(1))
        day_of_year = int(match.group(2))
        return datetime(year, 1, 1) + timedelta(days=day_of_year - 1)
    return None

def analyze_coverage(directory, product_name, expected_interval_days=1):
    print(f"\nAnalyzing coverage for {product_name} in {directory}...")
    
    if not os.path.exists(directory):
        print(f"Directory not found: {directory}")
        return

    files = [f for f in os.listdir(directory) if f.endswith(('.hdf', '.h5'))]
    print(f"Total Files Found: {len(files)}")

    # Map dates to file counts
    date_map = {}
    for f in files:
        dt = parse_modis_date(f)
        if dt:
            if dt not in date_map:
                date_map[dt] = []
            date_map[dt].append(f)

    # Calculate expected dates
    current = START_DATE
    missing_dates = []
    
    while current <= END_DATE:
        if current not in date_map:
            missing_dates.append(current)
        current += timedelta(days=expected_interval_days)

    # Report
    total_days = (END_DATE - START_DATE).days + 1
    expected_count = total_days // expected_interval_days
    
    coverage_pct = (len(date_map) / expected_count) * 100
    
    print(f"Unique Dates Covered: {len(date_map)} / {expected_count}")
    print(f"Coverage: {coverage_pct:.2f}%")
    
    if len(missing_dates) == 0:
        print("\033[92m[SUCCESS] Complete Temporal Coverage. No downloads needed.\033[0m")
    else:
        print(f"\033[91m[WARNING] Missing {len(missing_dates)} dates.\033[0m")
        # Print first 5 missing
        for d in missing_dates[:5]:
            print(f"  - Missing: {d.strftime('%Y-%m-%d')}")
        if len(missing_dates) > 5: print(f"  - ... and {len(missing_dates)-5} more.")

def main():
    # MOD11A1 is Daily (Interval = 1)
    analyze_coverage(MOD11A1_DIR, "MOD11A1 (Daily)", 1)
    
    # MOD13A2 is 16-Day (Interval = 16)
    # Note: Checking exact 16-day grids is complex, this checks if *any* 16-day file exists
    # For a simple check, we assume 16 days.
    # Actually, MOD13A2 dates are fixed. Let's just list count.
    analyze_coverage(MOD13A2_DIR, "MOD13A2 (16-Day)", 16)

if __name__ == "__main__":
    main()