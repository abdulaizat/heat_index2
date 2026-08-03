import earthaccess
import os
import logging

# CONFIGURATION
DOWNLOAD_ROOT = "/mnt/AizatDrive"
MOD11A1_DIR = os.path.join(DOWNLOAD_ROOT, "MOD11A1")
BOUNDING_BOX = (99.3, 0.6, 119.8, 7.8)

# THE MISSING GAP DETECTED
GAP_START = "2022-10-01"
GAP_END = "2022-10-31"

logging.basicConfig(level=logging.INFO)

def main():
    logging.info("--- INITIATING TARGETED RECOVERY FOR OCT 2022 ---")
    
    auth = earthaccess.login(strategy="interactive", persist=True)
    
    # Surgical search for the missing month
    results = earthaccess.search_data(
        short_name="MOD11A1",
        version="061",
        bounding_box=BOUNDING_BOX,
        temporal=(GAP_START, GAP_END)
    )
    
    if results:
        logging.info(f"Found {len(results)} granules for the gap period.")
        earthaccess.download(results, local_path=MOD11A1_DIR)
    else:
        logging.warning("NASA archives show NO DATA for this period. It might be a sensor outage.")

if __name__ == "__main__":
    main()