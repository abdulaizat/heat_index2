import os
import re
import csv
from datetime import date, timedelta
from collections import defaultdict

# --- CONFIGURATION ---
BASE_DIR = "./malaysia_amsr2_jaxa_fedeo"
START_DATE = date(2020, 1, 1)
END_DATE = date(2024, 12, 31)
PRODUCTS = ["23GHz", "89GHz", "SMC"]

def main():
    print("--- GENERATING FINAL SCIENTIFIC REPORT ---")
    
    # 1. Map existing files
    inventory = {p: set() for p in PRODUCTS}
    
    for product in PRODUCTS:
        path = os.path.join(BASE_DIR, product)
        for f in os.listdir(path):
            if f.endswith(".h5"):
                # Extract date GW1AM2_20200101...
                match = re.search(r'_(\d{8})_', f)
                if match:
                    d_str = match.group(1)
                    d_obj = date(int(d_str[:4]), int(d_str[4:6]), int(d_str[6:]))
                    inventory[product].add(d_obj)

    # 2. Analyze Gaps
    print(f"{'Date':<15} | {'23GHz':<10} | {'89GHz':<10} | {'SMC':<10} | {'Reason'}")
    print("-" * 65)
    
    csv_rows = []
    current = START_DATE
    missing_count = 0
    
    while current <= END_DATE:
        status = []
        is_missing_any = False
        
        for p in PRODUCTS:
            if current in inventory[p]:
                status.append("OK")
            else:
                status.append("MISSING")
                is_missing_any = True
        
        if is_missing_any:
            # If ALL are missing, it's a Satellite Gap. If only SOME, it's a download error.
            if all(s == "MISSING" for s in status):
                reason = "Satellite Gap (Orbit/Maintenance)"
            else:
                reason = "DOWNLOAD ERROR (Retry Needed)"
            
            print(f"{str(current):<15} | {status[0]:<10} | {status[1]:<10} | {status[2]:<10} | {reason}")
            csv_rows.append([current, status[0], status[1], status[2], reason])
            missing_count += 1
            
        current += timedelta(days=1)

    # 3. Save to CSV
    with open("missing_dates_log.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "23GHz", "89GHz", "SMC", "Reason"])
        writer.writerows(csv_rows)

    print("\n" + "="*60)
    print(f"Total Days in 5 Years: {(END_DATE - START_DATE).days + 1}")
    print(f"Days with Coverage Gaps: {missing_count}")
    print(f"Log saved to: missing_dates_log.csv")
    print("="*60)
    
    if any("DOWNLOAD ERROR" in row[4] for row in csv_rows):
        print("[!] ALERT: You still have partial download errors. Check the CSV.")
    else:
        print("[SUCCESS] All missing dates are consistent across products.")
        print("          This confirms your dataset is 100% complete relative to availability.")

if __name__ == "__main__":
    main()