import os
import sys
import datetime
import logging
import shutil
import bz2
import time
import argparse
from ftplib import FTP, error_perm

import s3fs
import numpy as np
import xarray as xr
import pandas as pd
from satpy import Scene
from pyresample import create_area_def

# --- Configuration ---
LOCAL_BASE_DIR = "/mnt/AizatDrive/himawari_data"
LOG_FILE = "himawari_production.log"

# JAXA FTP (Aerosol L3)
FTP_HOST = "ftp.ptree.jaxa.jp"
FTP_USER = "aizatSalam_gmail.com"
FTP_PASS = "SP+wari8"
BASE_REMOTE_PATH_L3 = "/pub/himawari/L3/ARP/" 

# AWS Configuration
AWS_BUCKET_H8 = "noaa-himawari8"
AWS_BUCKET_H9 = "noaa-himawari9"
TARGET_SEGMENT = "S0510"  # Segment 5 covers Malaysia

# Transition Date (H8 -> H9)
TRANSITION_DATE = datetime.date(2022, 12, 13)

# Malaysia Area Definition
AREA_ID = "malaysia_crop"
PROJ_DICT = {'proj': 'longlat', 'datum': 'WGS84'}
AREA_EXTENT = (99.0, 0.0, 120.0, 8.0) 
AREA_SHAPE = (800, 2100) 
area_def = create_area_def(AREA_ID, PROJ_DICT, area_extent=AREA_EXTENT, shape=AREA_SHAPE)

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger()

class HimawariDownloader:
    def __init__(self):
        self.fs = s3fs.S3FileSystem(anon=True)
        self.ftp = None

    def connect_ftp(self):
        for i in range(3):
            try:
                if self.ftp:
                    try:
                        self.ftp.voidcmd("NOOP")
                        return self.ftp
                    except:
                        pass
                self.ftp = FTP(FTP_HOST)
                self.ftp.login(FTP_USER, FTP_PASS)
                return self.ftp
            except Exception as e:
                logger.warning(f"FTP Connection failed (Attempt {i+1}): {e}")
                time.sleep(5)
        return None

    def get_aws_params(self, date_obj):
        if date_obj < TRANSITION_DATE:
            return "H08", AWS_BUCKET_H8
        else:
            return "H09", AWS_BUCKET_H9

    # --- HELPER: Aggressive Sanitizer for NetCDF ---
    def sanitize_and_clean_dataset(self, ds):
        """
        1. Drops problematic variables (crs, acq_time).
        2. Converts complex attributes to strings.
        """
        # 1. DROP PROBLEMATIC VARIABLES
        # 'crs' contains a python object. 'acq_time' contains datetime arrays.
        # We only want the physical data.
        drop_list = ['crs', 'acq_time', 'platform_name', 'sensor', 'orbital_parameters', 'line_acquisition_time']
        for var in drop_list:
            if var in ds.variables:
                ds = ds.drop_vars(var)
        
        # 2. SANITIZE ATTRIBUTES (Recursively)
        allowed_types = (str, int, float, np.integer, np.floating, np.ndarray, list, tuple, bytes)

        def clean_attr_dict(attrs):
            keys_to_delete = []
            for k, v in attrs.items():
                if k == 'area': # Delete Satpy Area Object
                    keys_to_delete.append(k)
                    continue
                
                if isinstance(v, (datetime.datetime, datetime.date)):
                    attrs[k] = str(v)
                    continue
                
                if not isinstance(v, allowed_types):
                    try:
                        attrs[k] = str(v)
                    except:
                        keys_to_delete.append(k)

            for k in keys_to_delete:
                del attrs[k]
        
        # Clean Global Attributes
        clean_attr_dict(ds.attrs)
        
        # Clean ALL Variables (Coords + Data)
        for var_name in ds.variables:
            clean_attr_dict(ds[var_name].attrs)
            
        return ds

    # ---------------------------------------------------------
    # PART 1: The Heat Movie (AWS - Band 13/14)
    # ---------------------------------------------------------
    def process_aws_brightness_temp(self, date_obj, hour, output_dir):
        sat_id, bucket = self.get_aws_params(date_obj)
        yyyy = date_obj.strftime("%Y")
        mm = date_obj.strftime("%m")
        dd = date_obj.strftime("%d")
        hh = f"{hour:02d}"
        
        final_nc_path = os.path.join(output_dir, f"LST_{sat_id}_{yyyy}{mm}{dd}_{hh}00_Malaysia.nc")
        
        if os.path.exists(final_nc_path) and os.path.getsize(final_nc_path) > 10000: 
            return
            
        temp_dir = os.path.join(output_dir, "temp_raw")
        os.makedirs(temp_dir, exist_ok=True)

        bands = ['B13', 'B14']
        prefix = f"{bucket}/AHI-L1b-FLDK/{yyyy}/{mm}/{dd}/{hh}00/"
        
        try:
            files = self.fs.ls(prefix)
        except Exception:
            return

        downloaded_files = []

        for band in bands:
            target_key = None
            for f in files:
                if band in f and TARGET_SEGMENT in f and f.endswith(".bz2"):
                    target_key = f
                    break
            
            if not target_key:
                continue

            filename = os.path.basename(target_key)
            local_bz2 = os.path.join(temp_dir, filename)
            local_dat = local_bz2.replace(".bz2", "")

            try:
                if not os.path.exists(local_dat):
                    logger.info(f"[AWS] Downloading Segment 5: {filename}")
                    self.fs.get(target_key, local_bz2)
                    with bz2.BZ2File(local_bz2, 'rb') as source, open(local_dat, 'wb') as dest:
                        shutil.copyfileobj(source, dest)
                    os.remove(local_bz2)
                downloaded_files.append(local_dat)
            except Exception as e:
                logger.error(f"Error AWS: {e}")

        if len(downloaded_files) == 2:
            try:
                scn = Scene(reader='ahi_hsd', filenames=downloaded_files)
                scn.load(bands)
                local_scene = scn.resample(area_def)
                ds = local_scene.to_xarray_dataset()
                
                # --- V5 FIX: DROP CRS & SANITIZE ---
                ds = ds.rename({'B13': 'T_10_4', 'B14': 'T_11_2'})
                ds = self.sanitize_and_clean_dataset(ds)
                # -----------------------------------
                
                dt_str = f"{yyyy}-{mm}-{dd} {hh}:00"
                ds = ds.expand_dims({'time': [pd.Timestamp(dt_str)]})

                ds.to_netcdf(final_nc_path, encoding={'T_10_4': {'zlib': True}, 'T_11_2': {'zlib': True}})
                logger.info(f"[SUCCESS] Saved Heat Movie Frame: {os.path.basename(final_nc_path)}")

            except Exception as e:
                logger.error(f"[Satpy] Processing failed for {dt_str}: {e}")
            finally:
                for f in downloaded_files:
                    if os.path.exists(f): os.remove(f)
                try: os.rmdir(temp_dir)
                except: pass

    # ---------------------------------------------------------
    # PART 2: The Haze Switch (JAXA - L3 Aerosol)
    # ---------------------------------------------------------
    def process_jaxa_aerosol(self, date_obj, hour, output_dir):
        if not self.connect_ftp(): return

        versions = ["031", "030"]
        yyyymm = date_obj.strftime("%Y%m")
        dd = date_obj.strftime("%d")
        hh = f"{hour:02d}"

        for ver in versions:
            remote_path = f"{BASE_REMOTE_PATH_L3}{ver}/{yyyymm}/{dd}/{hh}/"
            
            try:
                self.ftp.cwd(remote_path)
                files = self.ftp.nlst()
            except error_perm:
                continue 
            except Exception:
                self.connect_ftp()
                continue

            target_file = None
            for f in files:
                if "1H" in f and f"_{hh}00_" in f and f.endswith(".nc"):
                    target_file = f
                    break
            
            if target_file:
                local_path = os.path.join(output_dir, f"L3_{target_file}")
                
                if os.path.exists(local_path):
                    return

                logger.info(f"[JAXA L3] Downloading {target_file}")
                try:
                    with open(local_path, 'wb') as f_local:
                        self.ftp.retrbinary(f"RETR {target_file}", f_local.write)
                    
                    self.crop_jaxa_nc(local_path)
                    return 
                except Exception as e:
                    logger.error(f"JAXA Download Error: {e}")

    def crop_jaxa_nc(self, file_path):
        try:
            with xr.open_dataset(file_path) as ds:
                var_name = None
                for v in ['AOT_Merged_Mean', 'AOT_Merged', 'AOT_Mean']:
                    if v in ds:
                        var_name = v
                        break
                
                if not var_name:
                    logger.warning(f"AOT Variable not found in {file_path}")
                    return

                lat_slice = slice(8.0, 0.0)
                if ds.latitude[0] < ds.latitude[-1]: 
                    lat_slice = slice(0.0, 8.0)
                
                ds_crop = ds[[var_name]].sel(latitude=lat_slice, longitude=slice(99.0, 120.0))
                ds_crop = ds_crop.rename({var_name: 'AOT_Haze_Switch'})

                for v in ds_crop.variables:
                    ds_crop[v].encoding = {}
                
                ds_crop = self.sanitize_and_clean_dataset(ds_crop)

                temp = file_path + ".tmp.nc"
                ds_crop.to_netcdf(temp)
                ds.close()
                shutil.move(temp, file_path)
                logger.info(f"Cropped & Cleaned: {os.path.basename(file_path)}")
                
        except Exception as e:
            logger.warning(f"Could not crop JAXA file {file_path}: {e}")

    # ---------------------------------------------------------
    # MAIN LOOP
    # ---------------------------------------------------------
    def run(self, start_date, end_date):
        current = start_date
        while current <= end_date:
            logger.info(f"=== Processing {current} ===")
            
            day_dir = os.path.join(LOCAL_BASE_DIR, current.strftime("%Y"), 
                                 current.strftime("%m"), current.strftime("%d"))
            os.makedirs(day_dir, exist_ok=True)

            for hour in range(24):
                self.process_aws_brightness_temp(current, hour, day_dir)

                if 0 <= hour <= 9:
                    self.process_jaxa_aerosol(current, hour, day_dir)

            current += datetime.timedelta(days=1)
        
        if self.ftp: self.ftp.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    args = parser.parse_args()

    s = datetime.datetime.strptime(args.start, "%Y-%m-%d").date()
    e = datetime.datetime.strptime(args.end, "%Y-%m-%d").date()

    downloader = HimawariDownloader()
    downloader.run(s, e)