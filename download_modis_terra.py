
import earthaccess
import os
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("download_modis.log"),
        logging.StreamHandler()
    ]
)

# Configuration
USERNAME = "abdulaizat"
PASSWORD = "Gr7$ndkL!p2e"
DOWNLOAD_ROOT = "/mnt/AizatDrive"
MOD11A1_DIR = os.path.join(DOWNLOAD_ROOT, "MOD11A1")
MOD13A2_DIR = os.path.join(DOWNLOAD_ROOT, "MOD13A2")

# Temporal Range
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
        auth = earthaccess.login(strategy="interactive", persist=True) 
        # Note: If environment variables are not set, 'interactive' might prompt. 
        # Since we have credentials, we can also try setting env vars or passing them if supported,
        # but earthaccess.login usually looks for env vars or .netrc.
        # Given the user provided creds, let's set them in env vars for this session to be safe.
        os.environ["EARTHDATA_USERNAME"] = USERNAME
        os.environ["EARTHDATA_PASSWORD"] = PASSWORD
        auth = earthaccess.login(strategy="environment") # Use environment variables
    except Exception as e:
        logging.error(f"Authentication failed: {e}")
        return

    if not auth.authenticated:
        logging.error("Failed to authenticate. Please check credentials.")
        return

    logging.info("Authentication successful.")

    # 2. Download MOD11A1 (Daily LST)
    # Function to download by year to prevent hanging on large granule lists
    def download_by_year(short_name, version, target_dir, start_year=2020, end_year=2024):
        for year in range(start_year, end_year + 1):
            year_start = f"{year}-01-01"
            year_end = f"{year}-12-31"
            logging.info(f"Processing {short_name} for Year: {year} ({year_start} to {year_end})...")
            
            try:
                results = earthaccess.search_data(
                    short_name=short_name,
                    version=version,
                    bounding_box=BOUNDING_BOX,
                    temporal=(year_start, year_end)
                )
                
                if results:
                    logging.info(f"Found {len(results)} granules for {short_name} in {year}.")
                    # Create year-specific subfolder (optional, but keeps things tidy, user just wanted Modis folders so maybe keep root)
                    # User requested /mnt/AizatDrive/MOD11A1, so we keep that.
                    
                    # Ensure directory exists
                    os.makedirs(target_dir, exist_ok=True)
                    
                    logging.info(f"Starting download for {year}...")
                    earthaccess.download(
                        results,
                        local_path=target_dir,
                        threads=8
                    )
                    logging.info(f"Completed download for {short_name} Year {year}.")
                else:
                    logging.warning(f"No granules found for {short_name} in {year}.")
            
            except Exception as e:
                logging.error(f"Error downloading {short_name} for {year}: {e}")

    # 2. Download MOD11A1 (Daily LST) - Chunked by Year
    download_by_year("MOD11A1", "061", MOD11A1_DIR, 2020, 2024)

    # 3. Download MOD13A2 (16-Day Vegetation) - Chunked by Year
    download_by_year("MOD13A2", "061", MOD13A2_DIR, 2020, 2024)

if __name__ == "__main__":
    main()
