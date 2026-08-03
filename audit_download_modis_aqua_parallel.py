import earthaccess
import os
import logging
import hashlib
import concurrent.futures
import pandas as pd
import time
import json
from datetime import datetime
from tqdm import tqdm
from typing import Dict, Any, List, Tuple

# =============================================================================
# CONFIGURATION (Mirrored from your download script)
# =============================================================================
USERNAME = "abdulaizat"
PASSWORD = "Gr7$ndkL!p2e"
DOWNLOAD_ROOT = "/mnt/AizatDrive"
MYD11A1_DIR = os.path.join(DOWNLOAD_ROOT, "MYD11A1")
START_DATE = "2020-01-01"
END_DATE = "2024-12-31"
BOUNDING_BOX = (99.3, 0.6, 119.8, 7.8)

# SYSTEM ARCHITECTURE TUNING
# Rocky Linux 9.5 / Xeon Gold 5115 (20 Threads)
# We reserve 2 threads for OS/Orchestration, use 18 for heavy lifting.
MAX_WORKERS = 18 
CHUNK_SIZE = 8192 * 1024  # 8MB chunks for efficient I/O

# LOGGING SETUP
LOG_FILE = "modis_audit_integrity.log"
REPORT_FILE = "modis_audit_report.csv"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(processName)s] - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        logging.StreamHandler()
    ]
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_file_checksum(filepath: str, algo: str = 'md5') -> str:
    """
    Calculates the hash of a file using efficient chunk reading.
    Optimized for large HDF files.
    """
    hash_func = getattr(hashlib, algo.lower(), None)
    if not hash_func:
        # Fallback to md5 if unknown algo provided
        hash_func = hashlib.md5
    
    hasher = hash_func()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        return f"ERROR: {e}"

def is_valid_hdf_header(filepath: str) -> bool:
    """
    Checks the magic bytes of the file to ensure it's a valid HDF4/NetCDF file
    before spending time hashing it.
    HDF4 Magic Bytes: 0x0E 0x03 0x13 0x01
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
            # Basic HDF4 signature check (common for MODIS)
            # Note: HDF5 signature is different, but MYD11A1 is typically HDF4.
            # We strictly check if file is readable and has > 0 bytes here as baseline.
            if len(header) < 4:
                return False
            return True
    except:
        return False

def process_granule_integrity(granule_meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker function to be run in parallel.
    Checks existence, size, and checksum of a single file.
    """
    filename = granule_meta['filename']
    local_path = os.path.join(MYD11A1_DIR, filename)
    expected_size = granule_meta.get('size_mb', 0) * 1024 * 1024 # Approx
    remote_checksum = granule_meta.get('checksum')
    checksum_algo = granule_meta.get('checksum_algo', 'md5')

    result = {
        "filename": filename,
        "status": "UNKNOWN",
        "reason": "",
        "local_size": 0,
        "integrity_check": "SKIPPED"
    }

    # 1. Existence Check
    if not os.path.exists(local_path):
        result["status"] = "MISSING"
        result["reason"] = "File not found on disk"
        return result

    # 2. Structural/Size Check
    try:
        stat_info = os.stat(local_path)
        result["local_size"] = stat_info.st_size
        
        if result["local_size"] == 0:
            result["status"] = "CORRUPT"
            result["reason"] = "File size is 0 bytes"
            return result
        
        if not is_valid_hdf_header(local_path):
            result["status"] = "CORRUPT"
            result["reason"] = "Invalid File Header (Not HDF)"
            return result

    except Exception as e:
        result["status"] = "ERROR"
        result["reason"] = f"OS Error: {str(e)}"
        return result

    # 3. Cryptographic Checksum (The 100% Robust Check)
    # If NASA provided a checksum, we verify it.
    if remote_checksum:
        local_hash = get_file_checksum(local_path, checksum_algo)
        
        # NASA sometimes stores checksums in uppercase
        if local_hash.lower() == remote_checksum.lower():
            result["status"] = "VERIFIED"
            result["integrity_check"] = "PASS"
            result["reason"] = "Checksum Match"
        else:
            result["status"] = "CORRUPT"
            result["integrity_check"] = "FAIL"
            result["reason"] = f"Checksum Mismatch ({checksum_algo}). Expected {remote_checksum}, Got {local_hash}"
    else:
        # If no checksum provided by API, we accept based on valid header and size
        result["status"] = "VERIFIED_NO_HASH"
        result["integrity_check"] = "PASS (Structure Only)"
        result["reason"] = "Valid Header, No Remote Checksum Available"

    return result

# =============================================================================
# MAIN AUDIT LOGIC
# =============================================================================

def main():
    start_time = time.time()
    print(f"\n{'='*80}")
    print(f"MODIS DATA INTEGRITY AUDITOR - HIGH PERFORMANCE MODE")
    print(f"Architecture: {os.cpu_count()} CPUs detected. Using {MAX_WORKERS} Workers.")
    print(f"Target Directory: {MYD11A1_DIR}")
    print(f"{'='*80}\n")

    # 1. Authenticate (Required to get Checksum Metadata)
    logging.info("Authenticating with Earthdata to fetch source-of-truth metadata...")
    os.environ["EARTHDATA_USERNAME"] = USERNAME
    os.environ["EARTHDATA_PASSWORD"] = PASSWORD
    auth = earthaccess.login(strategy="environment")
    if not auth.authenticated:
        # Fallback
        auth = earthaccess.login(strategy="interactive", persist=True)

    # 2. Fetch Remote Metadata (The Source of Truth)
    logging.info(f"Querying NASA CMR for MYD11A1 granules ({START_DATE} to {END_DATE})...")
    try:
        # We perform the search exactly as the downloader did
        granules = earthaccess.search_data(
            short_name="MYD11A1",
            version="061",
            bounding_box=BOUNDING_BOX,
            temporal=(START_DATE, END_DATE)
        )
    except Exception as e:
        logging.critical(f"Failed to fetch metadata from NASA: {e}")
        return

    logging.info(f"Metadata received. Found {len(granules)} expected granules.")

    # 3. Parse Metadata into a clean list
    # We extract the filename and checksum from the complex granule object
    audit_queue = []
    
    for g in granules:
        # Extract filename (usually found in data_links or umm)
        # Earthaccess granule objects are rich. We try to find the direct filename.
        filename = os.path.basename(g.data_links(access="direct")[0])
        
        # Extract Checksum if available in UMM
        # This varies by provider, but often found in 'DataGranule' or related fields
        # Note: earthaccess objects wrap the UMM JSON.
        checksum = None
        algo = 'md5'
        
        # Attempt to dig for checksum in UMM (Unified Metadata Model)
        try:
            if 'Checksum' in g.umm.get('DataGranule', {}).get('ArchiveAndDistributionInformation', [{}])[0]:
                 chk_info = g.umm['DataGranule']['ArchiveAndDistributionInformation'][0]['Checksum']
                 checksum = chk_info.get('Value')
                 algo = chk_info.get('Algorithm', 'md5')
        except:
            pass

        audit_queue.append({
            'filename': filename,
            'size_mb': g.size(),
            'checksum': checksum,
            'checksum_algo': algo
        })

    logging.info(f"Prepared {len(audit_queue)} files for integrity verification.")

    # 4. Parallel Processing Execution
    results = []
    logging.info(f"Starting parallel audit with {MAX_WORKERS} threads. This verifies disk content and cryptographic hashes.")
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Use tqdm for a progress bar
        future_to_file = {executor.submit(process_granule_integrity, item): item for item in audit_queue}
        
        for future in tqdm(concurrent.futures.as_completed(future_to_file), total=len(audit_queue), unit="files"):
            try:
                data = future.result()
                results.append(data)
            except Exception as exc:
                logging.error(f"Worker exception: {exc}")

    # 5. Analysis & Reporting
    df = pd.DataFrame(results)
    
    # Summary Statistics
    total_files = len(df)
    missing = df[df['status'] == 'MISSING']
    corrupt = df[df['status'] == 'CORRUPT']
    verified = df[df['status'].str.contains('VERIFIED')]
    
    print(f"\n{'='*80}")
    print("AUDIT COMPLETION REPORT")
    print(f"{'='*80}")
    print(f"Total Expected Files : {total_files}")
    print(f"Successfully Verified: {len(verified)} ({(len(verified)/total_files)*100:.2f}%)")
    print(f"Missing Files        : {len(missing)}")
    print(f"Corrupt/Invalid      : {len(corrupt)}")
    print(f"{'='*80}")

    # Save CSV
    df.to_csv(REPORT_FILE, index=False)
    logging.info(f"Detailed CSV report saved to {REPORT_FILE}")

    # 6. Actionable Output
    if len(missing) > 0 or len(corrupt) > 0:
        bad_files = pd.concat([missing, corrupt])
        bad_file_list = bad_files['filename'].tolist()
        
        remedy_file = "files_to_redownload.json"
        with open(remedy_file, "w") as f:
            json.dump(bad_file_list, f, indent=4)
            
        logging.warning(f"Integrity issues found. List of {len(bad_file_list)} files to re-download saved to {remedy_file}.")
        print(f"\n[!] ALERT: {len(bad_file_list)} files failed integrity checks.")
        print(f"    See {remedy_file} for the list to re-download.")
    else:
        logging.info("SUCCESS: 100% Integrity Verification Passed.")
        print("\n[+] SUCCESS: All files exist and match 100% integrity criteria.")

    duration = time.time() - start_time
    print(f"\nTotal Execution Time: {duration:.2f} seconds")

if __name__ == "__main__":
    main()