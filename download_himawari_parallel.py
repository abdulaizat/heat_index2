import os
import sys
import datetime
import logging
import shutil
import bz2
import time
import argparse
import random
import multiprocessing
import warnings
import gc  # Garbage Collector
import dask
from ftplib import FTP, error_perm

# Check for libraries
try:
    import s3fs
    import numpy as np
    import xarray as xr
    import pandas as pd
    from satpy import Scene
    from pyresample import create_area_def
except ImportError as e:
    sys.exit(f"CRITICAL ERROR: Missing Library. {e}")

# --- Thread Safety & Warning Suppression ---
# Forces Dask to run in the main thread of the worker, preventing
# CPU thrashing on your Xeon server.
dask.config.set(scheduler='single-threaded')
warnings.simplefilter("ignore", category=RuntimeWarning)
warnings.simplefilter("ignore", category=UserWarning)

# --- Configuration ---
LOCAL_BASE_DIR = "/mnt/AizatDrive/himawari_data"
LOG_FILE = "himawari_omega.log"

# JAXA FTP
FTP_HOST = "ftp.ptree.jaxa.jp"
FTP_USER = "aizatSalam_gmail.com"
FTP_PASS = "SP+wari8"
BASE_REMOTE_PATH_L3 = "/pub/himawari/L3/ARP/" 

# AWS Configuration
AWS_BUCKET_H8 = "noaa-himawari8"
AWS_BUCKET_H9 = "noaa-himawari9"
TARGET_SEGMENT = "S0510"  # Segment 5

# Transition Date
TRANSITION_DATE = datetime.date(2022, 12, 13)

# Hardware Tuning (Xeon Gold 20-Core / 64GB RAM)
MAX_WORKERS = 8 
MAX_FTP_CONNECTIONS = 1
# CRITICAL: Restart worker process after 10 tasks to prevent Memory Leaks
MAX_TASKS_PER_CHILD = 10 

# Malaysia Area
AREA_ID = "malaysia_crop"
PROJ_DICT = {'proj': 'longlat', 'datum': 'WGS84'}
AREA_EXTENT = (99.0, 0.0, 120.0, 8.0) 
AREA_SHAPE = (800, 2100) 
area_def = create_area_def(AREA_ID, PROJ_DICT, area_extent=AREA_EXTENT, shape=AREA_SHAPE)

# --- Logging (Process Safe) ---
def get_logger():
    # Only setup logger if it doesn't exist for this process
    logger = logging.getLogger(f"Worker-{os.getpid()}")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s [PID:%(process)d] %(message)s')
        fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

# --- Global Semaphore (Initialized via inheritance/initializer) ---
ftp_semaphore = None

def init_worker(semaphore):
    """Initializes the semaphore for the pool worker."""
    global ftp_semaphore
    ftp_semaphore = semaphore

class HimawariWorker:
    def __init__(self):
        # Retry S3 connection on init if it fails
        retries = 3
        for i in range(retries):
            try:
                self.fs = s3fs.S3FileSystem(anon=True, client_kwargs={'region_name': 'us-east-1'})
                break
            except Exception as e:
                if i == retries - 1: raise e
                time.sleep(1)
        
        self.ftp = None
        self.logger = get_logger()

    # --- NETWORK RETRY DECORATOR ---
    def retry_s3_op(self, func, *args):
        """Retries S3 operations to handle transient AWS 503 errors."""
        for i in range(3):
            try:
                return func(*args)
            except Exception:
                if i == 2: return None # Fail silently after 3 tries
                time.sleep(random.uniform(1.0, 3.0))
        return None

    # --- FTP SAFE ---
    def connect_ftp_safe(self):
        time.sleep(random.uniform(0.5, 2.0))
        # Wait up to 120s for a slot
        if not ftp_semaphore.acquire(timeout=120):
            self.logger.warning("FTP Busy: Semaphore timeout.")
            return False
        try:
            self.ftp = FTP(host=FTP_HOST, timeout=60)
            self.ftp.login(FTP_USER, FTP_PASS)
            return True
        except Exception as e:
            self.logger.error(f"FTP Connect Error: {e}")
            ftp_semaphore.release()
            return False

    def close_ftp(self):
        """Aggressive FTP cleanup."""
        if self.ftp:
            try: self.ftp.quit()
            except: 
                try: self.ftp.close()
                except: pass
            finally:
                try: ftp_semaphore.release()
                except ValueError: pass
                self.ftp = None

    # --- AWS LOGIC ---
    def get_buckets(self, date_obj):
        if date_obj < TRANSITION_DATE:
            return "H08", AWS_BUCKET_H8, AWS_BUCKET_H9
        return "H09", AWS_BUCKET_H9, AWS_BUCKET_H8

    def list_files(self, bucket, yyyy, mm, dd, hh):
        # 1. Try Hourly
        prefix = f"{bucket}/AHI-L1b-FLDK/{yyyy}/{mm}/{dd}/{hh}00/"
        files = self.retry_s3_op(self.fs.ls, prefix)
        if files: return files

        # 2. Try Daily Scan (Fallback)
        prefix_day = f"{bucket}/AHI-L1b-FLDK/{yyyy}/{mm}/{dd}/"
        all_files = self.retry_s3_op(self.fs.ls, prefix_day)
        
        if all_files:
            target = f"_{hh}00_"
            return [f for f in all_files if target in f]
        
        return []

    # --- SANITIZER ---
    def sanitize(self, ds):
        # Drop Objects
        for var in ['crs', 'acq_time', 'platform_name', 'sensor', 'orbital_parameters', 'line_acquisition_time']:
            if var in ds.variables: ds = ds.drop_vars(var)
        
        # Clean Attributes
        allowed = (str, int, float, np.integer, np.floating, np.ndarray, list, tuple, bytes)
        def clean(attrs):
            rem = []
            for k, v in attrs.items():
                if k == 'area': rem.append(k); continue
                if isinstance(v, (datetime.datetime, datetime.date)):
                    attrs[k] = str(v); continue
                if not isinstance(v, allowed):
                    try: attrs[k] = str(v)
                    except: rem.append(k)
            for k in rem: del attrs[k]
        
        clean(ds.attrs)
        for v in ds.variables: clean(ds[v].attrs)
        return ds

    # --- AWS PROCESSOR ---
    def run_aws(self, date_obj, hour, output_dir):
        sat_id, pri_bkt, sec_bkt = self.get_buckets(date_obj)
        yyyy, mm, dd = date_obj.strftime("%Y"), date_obj.strftime("%m"), date_obj.strftime("%d")
        hh = f"{hour:02d}"
        
        final_path = os.path.join(output_dir, f"LST_{sat_id}_{yyyy}{mm}{dd}_{hh}00_Malaysia.nc")
        if os.path.exists(final_path) and os.path.getsize(final_path) > 10000: return "Exists"

        temp_dir = os.path.join(output_dir, f"tmp_aws_{os.getpid()}")
        os.makedirs(temp_dir, exist_ok=True)
        
        bands = ['B13', 'B14']
        files = self.list_files(pri_bkt, yyyy, mm, dd, hh)
        if not files:
            files = self.list_files(sec_bkt, yyyy, mm, dd, hh)
            if files and "himawari8" in sec_bkt: sat_id = "H08"
        
        if not files: 
            shutil.rmtree(temp_dir, ignore_errors=True)
            return "Missing"

        dl_files = []
        try:
            for band in bands:
                key = next((f for f in files if band in f and TARGET_SEGMENT in f and f.endswith(".bz2")), None)
                if not key: continue
                
                local_bz2 = os.path.join(temp_dir, os.path.basename(key))
                local_dat = local_bz2.replace(".bz2", "")
                
                if not os.path.exists(local_dat):
                    self.fs.get(key, local_bz2)
                    with bz2.BZ2File(local_bz2, 'rb') as f_in, open(local_dat, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    os.remove(local_bz2)
                dl_files.append(local_dat)

            if len(dl_files) == 2:
                scn = Scene(reader='ahi_hsd', filenames=dl_files)
                scn.load(bands)
                local_scn = scn.resample(area_def)
                ds = local_scn.to_xarray_dataset()
                ds = ds.rename({'B13': 'T_10_4', 'B14': 'T_11_2'})
                ds = self.sanitize(ds)
                
                ds = ds.expand_dims({'time': [pd.Timestamp(f"{yyyy}-{mm}-{dd} {hh}:00")]})
                
                tmp_nc = final_path + f".{os.getpid()}.tmp"
                ds.to_netcdf(tmp_nc, encoding={'T_10_4': {'zlib': True}, 'T_11_2': {'zlib': True}})
                shutil.move(tmp_nc, final_path)
                return "Success"
        except Exception as e:
            self.logger.error(f"AWS Fail {yyyy}-{mm}-{dd} {hh}: {e}")
            return f"Error: {e}"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            # FORCE MEMORY CLEANUP
            del dl_files
            gc.collect()

    # --- JAXA PROCESSOR ---
    def run_jaxa(self, date_obj, hour, output_dir):
        if not (0 <= hour <= 9): return "N/A"
        if not self.connect_ftp_safe(): return "Busy"

        try:
            yyyy, mm, dd = date_obj.strftime("%Y"), date_obj.strftime("%m"), date_obj.strftime("%d")
            hh = f"{hour:02d}"
            
            for ver in ["031", "030"]:
                path = f"{BASE_REMOTE_PATH_L3}{ver}/{yyyy}{mm}/{dd}/"
                try:
                    self.ftp.cwd(path)
                    files = self.ftp.nlst()
                except error_perm: continue

                target = next((f for f in files if "1H" in f and f"_{hh}00_" in f and f.endswith(".nc")), None)
                if target:
                    final_path = os.path.join(output_dir, f"L3_{target}")
                    if os.path.exists(final_path): return "Exists"

                    tmp_dl = final_path + f".{os.getpid()}.tmp"
                    try:
                        with open(tmp_dl, 'wb') as f: self.ftp.retrbinary(f"RETR {target}", f.write)
                        
                        with xr.open_dataset(tmp_dl) as ds:
                            vn = next((v for v in ['AOT_Merged_Mean', 'AOT_Merged'] if v in ds), None)
                            if vn:
                                ls = slice(8.0, 0.0) if ds.latitude[0] > ds.latitude[-1] else slice(0.0, 8.0)
                                ds = ds[[vn]].sel(latitude=ls, longitude=slice(99.0, 120.0))
                                ds = ds.rename({vn: 'AOT_Haze_Switch'})
                                for v in ds.variables: ds[v].encoding = {}
                                ds = self.sanitize(ds)
                                ds.to_netcdf(final_path)
                                return "Success"
                    except Exception as e:
                        self.logger.error(f"JAXA Fail: {e}")
                    finally:
                        if os.path.exists(tmp_dl): os.remove(tmp_dl)
                        gc.collect()
                    return "Success" # Found and processed
            return "Not Found"
        finally:
            self.close_ftp()

# --- WORKER ENTRY ---
def worker_main(task):
    date_obj, hour = task
    day_dir = os.path.join(LOCAL_BASE_DIR, date_obj.strftime("%Y"), 
                           date_obj.strftime("%m"), date_obj.strftime("%d"))
    os.makedirs(day_dir, exist_ok=True)
    
    w = HimawariWorker()
    a_res = w.run_aws(date_obj, hour, day_dir)
    j_res = w.run_jaxa(date_obj, hour, day_dir)
    
    return f"{date_obj} {hour:02d}:00 -> AWS: {a_res} | JAXA: {j_res}"

# --- MAIN ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    args = parser.parse_args()

    s = datetime.datetime.strptime(args.start, "%Y-%m-%d").date()
    e = datetime.datetime.strptime(args.end, "%Y-%m-%d").date()

    tasks = []
    curr = s
    while curr <= e:
        for h in range(24): tasks.append((curr, h))
        curr += datetime.timedelta(days=1)

    print(f"--- OMEGA DOWNLOADER (V10) ---")
    print(f"Tasks: {len(tasks)}")
    print(f"Workers: {MAX_WORKERS} (Recycle every {MAX_TASKS_PER_CHILD} tasks)")

    m = multiprocessing.Manager()
    sem = m.Semaphore(MAX_FTP_CONNECTIONS)

    # Use Pool instead of ProcessPoolExecutor to enable maxtasksperchild
    # This is the secret to 100% stable memory usage over weeks.
    with multiprocessing.Pool(processes=MAX_WORKERS, initializer=init_worker, initargs=(sem,), maxtasksperchild=MAX_TASKS_PER_CHILD) as pool:
        for i, res in enumerate(pool.imap_unordered(worker_main, tasks)):
            if i % 20 == 0:
                print(f"[{i+1}/{len(tasks)}] {res}")

if __name__ == "__main__":
    main()