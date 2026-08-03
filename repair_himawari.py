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
import gc
import dask
import pandas as pd
from ftplib import FTP, error_perm

try:
    import s3fs
    import numpy as np
    import xarray as xr
    from satpy import Scene
    from pyresample import create_area_def
except ImportError:
    pass

# --- Configuration ---
LOCAL_BASE_DIR = "/mnt/AizatDrive/himawari_data"
AUDIT_REPORT = "himawari_audit_report.csv"
LOG_FILE = "himawari_repair.log"

# Credentials
FTP_HOST = "ftp.ptree.jaxa.jp"
FTP_USER = "aizatSalam_gmail.com"
FTP_PASS = "SP+wari8"
BASE_REMOTE_PATH_L3 = "/pub/himawari/L3/ARP/" 
AWS_BUCKET_H8 = "noaa-himawari8"
AWS_BUCKET_H9 = "noaa-himawari9"
TARGET_SEGMENT = "S0510"
TRANSITION_DATE = datetime.date(2022, 12, 13)

# Tuning
MAX_WORKERS = 8 # Lower for repair to ensure stability
MAX_FTP_CONNECTIONS = 3

# Area Def
AREA_ID = "malaysia_crop"
PROJ_DICT = {'proj': 'longlat', 'datum': 'WGS84'}
AREA_EXTENT = (99.0, 0.0, 120.0, 8.0) 
AREA_SHAPE = (800, 2100) 
area_def = create_area_def(AREA_ID, PROJ_DICT, area_extent=AREA_EXTENT, shape=AREA_SHAPE)

# --- Thread Safety ---
dask.config.set(scheduler='single-threaded')
warnings.simplefilter("ignore")

# --- Logging ---
def get_logger():
    logger = logging.getLogger(f"Worker-{os.getpid()}")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s [PID:%(process)d] %(message)s')
        fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

# --- Semaphore ---
ftp_semaphore = None
def init_worker(semaphore):
    global ftp_semaphore
    ftp_semaphore = semaphore

class RepairWorker:
    def __init__(self):
        for i in range(3):
            try:
                self.fs = s3fs.S3FileSystem(anon=True, client_kwargs={'region_name': 'us-east-1'})
                break
            except: time.sleep(1)
        self.ftp = None
        self.logger = get_logger()

    def connect_ftp_safe(self):
        time.sleep(random.uniform(0.5, 2.0))
        if not ftp_semaphore.acquire(timeout=60): return False
        try:
            self.ftp = FTP(host=FTP_HOST, timeout=60)
            self.ftp.login(FTP_USER, FTP_PASS)
            return True
        except:
            ftp_semaphore.release()
            return False

    def close_ftp(self):
        if self.ftp:
            try: self.ftp.quit()
            except: 
                try: self.ftp.close()
                except: pass
            finally:
                try: ftp_semaphore.release()
                except: pass
                self.ftp = None

    def get_buckets(self, date_obj):
        if date_obj < TRANSITION_DATE: return "H08", AWS_BUCKET_H8, AWS_BUCKET_H9
        return "H09", AWS_BUCKET_H9, AWS_BUCKET_H8

    def list_files(self, bucket, yyyy, mm, dd, hh):
        # Hourly check
        try:
            files = self.fs.ls(f"{bucket}/AHI-L1b-FLDK/{yyyy}/{mm}/{dd}/{hh}00/")
            if files: return files
        except: pass
        # Daily check
        try:
            all_files = self.fs.ls(f"{bucket}/AHI-L1b-FLDK/{yyyy}/{mm}/{dd}/")
            return [f for f in all_files if f"_{hh}00_" in f]
        except: return []

    def sanitize(self, ds):
        drop = ['crs', 'acq_time', 'platform_name', 'sensor', 'orbital_parameters', 'line_acquisition_time']
        for v in drop: 
            if v in ds.variables: ds = ds.drop_vars(v)
        
        allowed = (str, int, float, np.integer, np.floating, np.ndarray, list, tuple, bytes)
        def clean(attrs):
            rem = []
            for k, v in attrs.items():
                if k == 'area': rem.append(k); continue
                if isinstance(v, (datetime.datetime, datetime.date)): attrs[k] = str(v); continue
                if not isinstance(v, allowed):
                    try: attrs[k] = str(v)
                    except: rem.append(k)
            for k in rem: del attrs[k]
        clean(ds.attrs)
        for v in ds.variables: clean(ds[v].attrs)
        return ds

    def repair_aws(self, date_obj, hour, output_dir):
        sat_id, pri_bkt, sec_bkt = self.get_buckets(date_obj)
        yyyy, mm, dd = date_obj.strftime("%Y"), date_obj.strftime("%m"), date_obj.strftime("%d")
        hh = f"{hour:02d}"
        
        final_path = os.path.join(output_dir, f"LST_{sat_id}_{yyyy}{mm}{dd}_{hh}00_Malaysia.nc")
        temp_dir = os.path.join(output_dir, f"rep_aws_{os.getpid()}")
        os.makedirs(temp_dir, exist_ok=True)
        
        bands = ['B13', 'B14']
        files = self.list_files(pri_bkt, yyyy, mm, dd, hh)
        if not files:
            files = self.list_files(sec_bkt, yyyy, mm, dd, hh)
            if files and "himawari8" in sec_bkt: sat_id = "H08"
        
        if not files: 
            shutil.rmtree(temp_dir, ignore_errors=True)
            return "Still Missing (Source Unavailable)"

        dl_files = []
        try:
            for band in bands:
                key = next((f for f in files if band in f and TARGET_SEGMENT in f and f.endswith(".bz2")), None)
                if not key: continue
                local_path = os.path.join(temp_dir, os.path.basename(key).replace(".bz2", ""))
                self.fs.get(key, local_path + ".bz2")
                with bz2.BZ2File(local_path + ".bz2", 'rb') as f_in, open(local_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
                dl_files.append(local_path)

            if len(dl_files) == 2:
                scn = Scene(reader='ahi_hsd', filenames=dl_files)
                scn.load(bands)
                ds = scn.resample(area_def).to_xarray_dataset()
                ds = ds.rename({'B13': 'T_10_4', 'B14': 'T_11_2'})
                ds = self.sanitize(ds)
                ds = ds.expand_dims({'time': [pd.Timestamp(f"{yyyy}-{mm}-{dd} {hh}:00")]})
                ds.to_netcdf(final_path, encoding={'T_10_4': {'zlib': True}, 'T_11_2': {'zlib': True}})
                return "Repaired"
        except Exception as e:
            return f"Repair Failed: {e}"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            gc.collect()

    def repair_jaxa(self, date_obj, hour, output_dir):
        if not self.connect_ftp_safe(): return "FTP Busy"
        try:
            yyyy, mm, dd = date_obj.strftime("%Y"), date_obj.strftime("%m"), date_obj.strftime("%d")
            hh = f"{hour:02d}"
            
            for ver in ["031", "030"]:
                try:
                    self.ftp.cwd(f"{BASE_REMOTE_PATH_L3}{ver}/{yyyy}{mm}/{dd}/")
                    files = self.ftp.nlst()
                    target = next((f for f in files if "1H" in f and f"_{hh}00_" in f and f.endswith(".nc")), None)
                    if target:
                        final_path = os.path.join(output_dir, f"L3_{target}")
                        tmp_dl = final_path + f".{os.getpid()}.tmp"
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
                        if os.path.exists(tmp_dl): os.remove(tmp_dl)
                        return "Repaired"
                except: continue
            return "Still Missing (Not on JAXA)"
        finally:
            self.close_ftp()

def worker_task(row):
    date_str = row['Date']
    hour = int(row['Hour'])
    aws_status = row['AWS_Status']
    jaxa_status = row['JAXA_Status']
    
    date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    day_dir = os.path.join(LOCAL_BASE_DIR, date_obj.strftime("%Y"), 
                           date_obj.strftime("%m"), date_obj.strftime("%d"))
    
    w = RepairWorker()
    aws_res = "Skip"
    jaxa_res = "Skip"
    
    if aws_status != 0:
        aws_res = w.repair_aws(date_obj, hour, day_dir)
    
    if jaxa_status != 0 and jaxa_status != -1: # -1 is Nighttime
        jaxa_res = w.repair_jaxa(date_obj, hour, day_dir)
        
    return f"{date_str} {hour:02d}:00 -> AWS: {aws_res} | JAXA: {jaxa_res}"

def main():
    if not os.path.exists(AUDIT_REPORT):
        print("No audit report found!")
        return

    print("Loading Audit Report...")
    df = pd.read_csv(AUDIT_REPORT)
    
    # Filter for problems
    problems = df[(df['AWS_Status'] != 0) | ((df['JAXA_Status'] != 0) & (df['JAXA_Status'] != -1))]
    
    if len(problems) == 0:
        print("No repairs needed! 100% Integrity.")
        return

    print(f"--- STARTING SURGICAL REPAIR ---")
    print(f"Targeting {len(problems)} specific files.")
    
    tasks = [row for _, row in problems.iterrows()]
    
    m = multiprocessing.Manager()
    sem = m.Semaphore(MAX_FTP_CONNECTIONS)
    
    with multiprocessing.Pool(processes=MAX_WORKERS, initializer=init_worker, initargs=(sem,)) as pool:
        for res in pool.imap_unordered(worker_task, tasks):
            print(res)

if __name__ == "__main__":
    main()