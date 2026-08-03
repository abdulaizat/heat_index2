import earthaccess
import os
import logging
import hashlib
import csv
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from collections import Counter

# ==============================================================================
# CONFIGURATION
# ==============================================================================
USERNAME = "abdulaizat"
PASSWORD = "Gr7$ndkL!p2e"
DOWNLOAD_ROOT = "/mnt/AizatDrive"
MOD11A1_DIR = os.path.join(DOWNLOAD_ROOT, "MOD11A1")
MOD13A2_DIR = os.path.join(DOWNLOAD_ROOT, "MOD13A2")
BOUNDING_BOX = (99.3, 0.6, 119.8, 7.8)
START_DATE = "2020-01-01"
END_DATE = "2024-12-31"

# SYSTEM ARCHITECTURE OPTIMIZATION
# Your Xeon Gold 5115 has 20 Logical Processors.
# We set workers to CPU_COUNT to utilize 100% of available compute.
CPU_COUNT = os.cpu_count()  # Should be 20 on your system
CHUNK_SIZE = 1024 * 1024    # 1MB Read Buffer to reduce Disk Thrashing on /dev/sda2

LOG_FILE = f"audit_titanium_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
REPORT_FILE = f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# ==============================================================================
# LOGGING SETUP
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | PID:%(process)d | %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        logging.StreamHandler()
    ]
)

# ==============================================================================
# CORE INTEGRITY LOGIC (WORKER FUNCTION)
# ==============================================================================
def check_file_integrity(task_data):
    """
    This function runs on a separate CPU Core.
    It performs a deep forensic check of a single file.
    """
    filename = task_data['filename']
    expected_hash = task_data['expected_hash'] # From NASA Metadata
    dir_path = task_data['dir_path']
    local_path = os.path.join(dir_path, filename)
    
    result = {
        'filename': filename,
        'path': local_path,
        'status': 'UNKNOWN',
        'reason': '',
        'local_size': 0,
        'remote_checksum': expected_hash,
        'local_checksum': None,
        'processing_time': 0
    }

    start_t = time.time()

    # 1. EXISTENCE CHECK
    if not os.path.exists(local_path):
        result['status'] = 'MISSING'
        result['reason'] = 'File not found on disk'
        return result

    try:
        file_size = os.path.getsize(local_path)
        result['local_size'] = file_size

        # 2. SIZE SANITY CHECK
        if file_size < 1024:
            result['status'] = 'CORRUPT_SIZE'
            result['reason'] = 'File < 1KB (likely empty download)'
            return result

        # 3. HEADER ANALYSIS (Magic Number)
        # Check for HDF4, HDF5, or NetCDF signatures
        with open(local_path, "rb") as f:
            header = f.read(8)
            # HDF4: \x0e\x03\x13\x01 | HDF5: \x89HDF... | CDF
            is_hdf4 = header[:4] == b'\x0e\x03\x13\x01'
            is_hdf5 = header[:8] == b'\x89HDF\r\n\x1a\n'
            is_cdf = header[:3] == b'CDF'
            
            if not (is_hdf4 or is_hdf5 or is_cdf):
                result['status'] = 'CORRUPT_HEADER'
                result['reason'] = f'Invalid Binary Header: {header.hex()}'
                return result

        # 4. CRYPTOGRAPHIC HASH VERIFICATION (MD5)
        # Only proceed if NASA provided a hash to check against
        if expected_hash:
            hasher = hashlib.md5()
            with open(local_path, "rb") as f:
                # Read in 1MB chunks to optimize IO for your /dev/sda2 drive
                while chunk := f.read(CHUNK_SIZE):
                    hasher.update(chunk)
            
            local_hash = hasher.hexdigest()
            result['local_checksum'] = local_hash

            if local_hash != expected_hash:
                result['status'] = 'CORRUPT_CHECKSUM'
                result['reason'] = f'Hash Mismatch (Local:{local_hash} != Remote:{expected_hash})'
                return result
        
        # If we get here, it is PERFECT.
        result['status'] = 'VERIFIED'
        result['reason'] = 'Integrity Confirmed'

    except Exception as e:
        result['status'] = 'ERROR'
        result['reason'] = str(e)

    result['processing_time'] = time.time() - start_t
    return result

# ==============================================================================
# MAIN CONTROLLER
# ==============================================================================
def main():
    overall_start = time.time()
    
    # 1. AUTHENTICATE
    logging.info(f"Detected {CPU_COUNT} CPU Cores. Initializing High-Performance Audit Engine...")
    os.environ["EARTHDATA_USERNAME"] = USERNAME
    os.environ["EARTHDATA_PASSWORD"] = PASSWORD
    try:
        auth = earthaccess.login(strategy="environment")
        if not auth.authenticated:
            raise Exception("Auth Failed")
    except Exception as e:
        logging.critical("FATAL: Authentication failed.")
        return

    # 2. PREPARE REPORTING
    csv_headers = ['filename', 'status', 'reason', 'local_size', 'remote_checksum', 'local_checksum', 'path', 'processing_time']
    # Create file and write header
    with open(REPORT_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()

    audit_stats = Counter()

    # 3. DEFINE DATASETS TO AUDIT
    datasets = [
        ("MOD11A1", "061", MOD11A1_DIR),
        ("MOD13A2", "061", MOD13A2_DIR)
    ]

    for short_name, version, target_dir in datasets:
        logging.info(f"--- FETCHING METADATA FOR {short_name} ---")
        
        # Query NASA CMR for the "Source of Truth"
        try:
            granules = earthaccess.search_data(
                short_name=short_name,
                version=version,
                bounding_box=BOUNDING_BOX,
                temporal=(START_DATE, END_DATE)
            )
        except Exception as e:
            logging.error(f"Failed to fetch metadata for {short_name}: {e}")
            continue

        if not granules:
            logging.warning(f"No granules found for {short_name}")
            continue

        logging.info(f"Metadata Retrieved: {len(granules)} files expected.")
        logging.info(f"Identifying orphans in {target_dir}...")
        
        # ORPHAN DETECTION (Single threaded is fast enough for directory listing)
        expected_files = set()
        tasks = []

        # Prepare Task Data for Parallel Workers
        # We extract primitive data here to make it pickle-safe for multiprocessing
        for g in granules:
            data_links = [l for l in g.data_links() if 'http' in l]
            if not data_links:
                continue
            
            url = data_links[0]
            fname = os.path.basename(url)
            expected_files.add(fname)
            
            # Extract Checksum if available in metadata
            r_hash = None
            if 'checksum' in g.keys(): r_hash = g['checksum']
            elif 'hashes' in g.keys() and 'md5' in g['hashes']: r_hash = g['hashes']['md5']

            tasks.append({
                'filename': fname,
                'expected_hash': r_hash,
                'dir_path': target_dir
            })

        # Check for Orphans (Files on disk that shouldn't be there)
        if os.path.exists(target_dir):
            local_files = set(os.listdir(target_dir))
            # Filter for HDF files only to avoid flagging logs
            hdf_on_disk = {f for f in local_files if f.endswith(('.hdf', '.h5', '.nc'))}
            orphans = hdf_on_disk - expected_files
            
            if orphans:
                logging.warning(f"Found {len(orphans)} ORPHAN files (files not in current metadata).")
                with open(REPORT_FILE, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=csv_headers)
                    for o in orphans:
                        row = {k: '' for k in csv_headers}
                        row['filename'] = o
                        row['status'] = 'ORPHAN'
                        row['reason'] = 'File exists locally but is not in NASA manifest'
                        row['path'] = os.path.join(target_dir, o)
                        writer.writerow(row)
                        audit_stats['ORPHAN'] += 1

        # PARALLEL PROCESSING START
        logging.info(f"SPAWNING {CPU_COUNT} WORKER PROCESSES FOR DEEP INSPECTION...")
        
        with ProcessPoolExecutor(max_workers=CPU_COUNT) as executor:
            # Map tasks to the pool
            # as_completed yields futures as they finish
            future_to_file = {executor.submit(check_file_integrity, task): task['filename'] for task in tasks}
            
            completed_count = 0
            total_tasks = len(tasks)
            
            # Open CSV in append mode for real-time writing
            with open(REPORT_FILE, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=csv_headers)
                
                for future in as_completed(future_to_file):
                    fname = future_to_file[future]
                    try:
                        data = future.result()
                        writer.writerow(data)
                        
                        audit_stats[data['status']] += 1
                        completed_count += 1
                        
                        # Logging progress every 50 files
                        if completed_count % 50 == 0:
                            logging.info(f"Progress {short_name}: {completed_count}/{total_tasks} | Safe: {audit_stats['VERIFIED']} | Corrupt/Missing: {audit_stats['MISSING'] + audit_stats['CORRUPT_CHECKSUM']}")
                            
                    except Exception as exc:
                        logging.error(f"Worker crashed on {fname}: {exc}")

    # 4. FINAL SUMMARY
    duration = time.time() - overall_start
    logging.info("="*60)
    logging.info(f"AUDIT COMPLETE in {duration:.2f} seconds")
    logging.info(f"TOTAL PROCESSED: {sum(audit_stats.values())}")
    logging.info(f"VERIFIED SAFE:   {audit_stats['VERIFIED']}")
    logging.info(f"MISSING:         {audit_stats['MISSING']}")
    logging.info(f"CORRUPT CHECKSUM:{audit_stats['CORRUPT_CHECKSUM']}")
    logging.info(f"CORRUPT HEADER:  {audit_stats['CORRUPT_HEADER']}")
    logging.info(f"ORPHANS:         {audit_stats['ORPHAN']}")
    logging.info(f"Detailed CSV Report: {os.path.abspath(REPORT_FILE)}")
    logging.info("="*60)

    if audit_stats['MISSING'] > 0 or audit_stats['CORRUPT_CHECKSUM'] > 0:
        print("\n\033[91m!!! SYSTEM ALERT: DATA INTEGRITY ISSUES DETECTED !!!\033[0m")
        print("Please review the CSV report and re-run the downloader.")
    else:
        print("\n\033[92m*** SYSTEM INTEGRITY 100% VERIFIED ***\033[0m")

if __name__ == "__main__":
    # Ensure multiprocessing works correctly on Linux
    multiprocessing.set_start_method('fork')
    main()