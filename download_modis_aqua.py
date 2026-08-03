import earthaccess
import os
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("download_modis_aqua.log"),
        logging.StreamHandler()
    ]
)

# Configuration
USERNAME = "abdulaizat"
PASSWORD = "Gr7$ndkL!p2e"
DOWNLOAD_ROOT = "/mnt/AizatDrive"
MYD11A1_DIR = os.path.join(DOWNLOAD_ROOT, "MYD11A1")

# Temporal Range
# Train on 5 years of data from 2020 to 2025 (inclusive of 2024 per specific instruction, usually implies end of 2024)
# User said "2020 to 2024, for 5 years" but 2020-2024 is 5 years.
START_DATE = "2020-01-01"
END_DATE = "2024-12-31"

# Spatial Domain (Malaysia)
# User provided: [7.8, 99.3, 0.6, 119.8] # [North, West, South, East]
# earthaccess expects: (west, south, east, north)
BOUNDING_BOX = (99.3, 0.6, 119.8, 7.8)

def main():
    # 1. Authenticate
    logging.info("Authenticating with Earthdata...")
    try:
        # Set environment variables for earthaccess to use
        os.environ["EARTHDATA_USERNAME"] = USERNAME
        os.environ["EARTHDATA_PASSWORD"] = PASSWORD
        
        auth = earthaccess.login(strategy="environment")
        
        if not auth.authenticated:
            # Fallback to interactive if env fails (though it shouldn't with correct creds)
            logging.warning("Environment auth failed, trying interactive/persisted...")
            auth = earthaccess.login(strategy="interactive", persist=True)
            
    except Exception as e:
        logging.error(f"Authentication failed: {e}")
        return

    if not auth.authenticated:
        logging.error("Failed to authenticate. Please check credentials.")
        return

    logging.info("Authentication successful.")

    # 2. Download MYD11A1 (Daily LST - Aqua)
    logging.info(f"Searching for MYD11A1 (Aqua Daily LST) from {START_DATE} to {END_DATE}...")
    try:
        results_myd11 = earthaccess.search_data(
            short_name="MYD11A1",
            version="061",
            bounding_box=BOUNDING_BOX,
            temporal=(START_DATE, END_DATE)
        )
        logging.info(f"Found {len(results_myd11)} granules for MYD11A1.")
        
        if results_myd11:
            logging.info(f"Downloading MYD11A1 to {MYD11A1_DIR}...")
            os.makedirs(MYD11A1_DIR, exist_ok=True)
            
            earthaccess.download(
                results_myd11,
                local_path=MYD11A1_DIR,
                threads=8 # Adjust threads as needed
            )
            logging.info("MYD11A1 download complete.")
        else:
            logging.warning("No granules found for MYD11A1.")

    except Exception as e:
        logging.error(f"Error downloading MYD11A1: {e}")

if __name__ == "__main__":
    main()
