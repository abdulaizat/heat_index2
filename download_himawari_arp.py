import ftplib
import os
import datetime
import time
import argparse
import sys
import logging
import xarray as xr

# Configuration
FTP_HOST = "ftp.ptree.jaxa.jp"
FTP_USER = "aizatSalam_gmail.com"
FTP_PASS = "SP+wari8"
BASE_REMOTE_PATH = "/pub/himawari/L2/ARP/"
LOCAL_BASE_PATH = "/mnt/AizatDrive/himawari_arp"
VERSION_SWITCH_DATE = datetime.date(2022, 9, 1)

# Malaysia Bounding Box: [North, West, South, East] = [7.8, 99.3, 0.6, 119.8]
# Note: Himawari Latitudes are typically descending (60 -> -60).
# We try slice(7.8, 0.6) for lat. If empty, we swap.
LAT_SLICE = slice(7.8, 0.6) 
LON_SLICE = slice(99.3, 119.8)

# Usage:
# python download_himawari_arp.py --start-date 2020-01-01 --end-date 2024-12-31

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("download_himawari_arp.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger()

def connect_ftp():
    """Connects to the FTP server and returns the ftplib object."""
    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        # Passive mode is usually default, but good to be explicit if issues arise.
        # ftp.set_pasv(True) 
        logger.info(f"Connected to {FTP_HOST}")
        return ftp
    except ftplib.all_errors as e:
        logger.error(f"Failed to connect to FTP: {e}")
        return None

def ensure_directory(path):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            logger.error(f"Error creating directory {path}: {e}")

def get_version_for_date(date_obj):
    """Returns the correct version string based on the date."""
    if date_obj >= VERSION_SWITCH_DATE:
        return "031"
    else:
        return "030"

def crop_and_overwrite(local_path):
    """
    Reads the NetCDF file, crops it to the Malaysia domain, 
    and overwrites the original file with the cropped version.
    """
    try:
        # Open dataset without decoding scaling/offsets to avoid casting errors during save
        # This keeps data as raw integers (short), which is safer and faster.
        with xr.open_dataset(local_path, mask_and_scale=False) as ds:
            # Check latitude orientation
            if ds.latitude[0] > ds.latitude[-1]:
                # Descending latitude (60 -> -60)
                lat_sl = slice(7.8, 0.6)
            else:
                # Ascending latitude
                lat_sl = slice(0.6, 7.8)
            
            cropped = ds.sel(latitude=lat_sl, longitude=LON_SLICE)
            
            # Use a temporary file
            temp_path = local_path + ".tmp.nc"
            cropped.to_netcdf(temp_path)
            
        # Replace original with cropped
        os.replace(temp_path, local_path)
        logger.info(f"Cropped {os.path.basename(local_path)} to Malaysia Domain.")
        return True
    except Exception as e:
        logger.error(f"Error cropping {local_path}: {e}")
        if os.path.exists(local_path + ".tmp.nc"):
             os.remove(local_path + ".tmp.nc")
        return False

def download_file(ftp, remote_path, local_path, retries=3):
    """Downloads a file with retry logic and then crops it."""
    # Check if already exists. If it does, assume it is already cropped/downloaded.
    # To be robust: If size is huge (Full Disk), re-crop. If small (Cropped), skip.
    # Full Disk ~ 5-6MB. Cropped ~ 100KB? Threshold 1MB is safe.
    THRESHOLD_SIZE = 1 * 1024 * 1024 # 1MB

    if os.path.exists(local_path):
        local_size = os.path.getsize(local_path)
        if local_size < THRESHOLD_SIZE: 
             if local_size < 1024:
                 logger.warning(f"File {os.path.basename(local_path)} is too small ({local_size} bytes). Re-downloading.")
             else:
                 logger.info(f"Skipping {os.path.basename(local_path)} (already exists and appears cropped)")
                 return True
        else:
             logger.info(f"File {os.path.basename(local_path)} exists but seems large ({local_size/1024/1024:.2f}MB). Attempting to crop directly.")
             if crop_and_overwrite(local_path):
                 return True
             else:
                 logger.warning("Direct cropping failed. Re-downloading...")

    downloaded = False
    for attempt in range(retries):
        try:
            with open(local_path, 'wb') as f:
                ftp.retrbinary('RETR ' + remote_path, f.write)
            logger.info(f"Downloaded: {remote_path}")
            downloaded = True
            break
        except ftplib.all_errors as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed to download {remote_path}: {e}")
            time.sleep(2 * (attempt + 1)) 
            
            try:
                ftp.voidcmd("NOOP")
            except:
                logger.info("Reconnecting...")
                try:
                    ftp.connect(FTP_HOST)
                    ftp.login(FTP_USER, FTP_PASS)
                except:
                    pass
    
    if downloaded:
        # Perform cropping immediately to save space
        crop_success = crop_and_overwrite(local_path)
        return crop_success
    
    return False

def process_date_range(start_date, end_date):
    ftp = connect_ftp()
    if not ftp:
        return

    current_date = start_date
    while current_date <= end_date:
        ver = get_version_for_date(current_date)
        yyyymm = current_date.strftime("%Y%m")
        dd = current_date.strftime("%d")
        
        # Local Path: /mnt/AizatDrive/himawari_arp/{YYYY}/{MM}/{DD}/
        local_day_dir = os.path.join(LOCAL_BASE_PATH, current_date.strftime("%Y"), current_date.strftime("%m"), dd)
        
        # Only 00:00 to 09:00 UTC (Daytime in Malaysia 8am-5pm)
        for hour in range(10): # 0 to 9
            hh = f"{hour:02d}"
            
            remote_dir = f"{BASE_REMOTE_PATH}{ver}/{yyyymm}/{dd}/{hh}/"
            
            # Retry loop for navigation/listing
            for retry_step in range(3):
                try:
                    ftp.cwd(remote_dir)
                    break # CWD successful
                except ftplib.error_perm as e:
                    logger.warning(f"Could not change directory to {remote_dir}: {e} (Maintenance day/missing data?)")
                    break # Perm error = probably date doesn't exist, don't retry/reconnect
                except ftplib.all_errors as e:
                    logger.warning(f"Error changing directory to {remote_dir}: {e}. Reconnecting...")
                    time.sleep(5)
                    ftp = connect_ftp()
                    if not ftp:
                        logger.error("Failed to reconnect.")
                        break
            else:
                # If loop completed without break (failed 3 times)
                continue

            try:
                files = ftp.nlst()
            except ftplib.all_errors as e:
                logger.warning(f"Could not list files in {remote_dir}: {e}. Reconnecting...")
                ftp = connect_ftp() # Try once
                if ftp:
                   try:
                       ftp.cwd(remote_dir)
                       files = ftp.nlst()
                   except:
                       continue
                else:
                   continue
            
            # Filter for Minute 00 files
            target_files = [f for f in files if f"_{hh}00_" in f and f.endswith(".nc")]

            if not target_files:
                logger.info(f"No minute 00 files found in {remote_dir}")
                continue
            
            ensure_directory(local_day_dir)

            for filename in target_files:
                local_file_path = os.path.join(local_day_dir, filename)
                remote_file_path = filename 
                
                try:
                    ftp.voidcmd("NOOP")
                except:
                     logger.info("Connection lost in loop. Reconnecting...")
                     ftp = connect_ftp()
                     if not ftp: 
                         logger.error("Could not reconnect. Exiting loop.")
                         return
                     ftp.cwd(remote_dir)

                success = download_file(ftp, remote_file_path, local_file_path)
                if not success:
                    logger.error(f"Permanent failure downloading/cropping {filename}")

        current_date += datetime.timedelta(days=1)
    
    try:
        ftp.quit()
    except:
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Himawari L2 ARP Data")
    parser.add_argument("--start-date", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="End date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    try:
        start = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
        end = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD")
        sys.exit(1)

    logger.info(f"Starting download from {start} to {end}")
    process_date_range(start, end)
    logger.info("Download process finished.")
