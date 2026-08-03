import requests
import os
import concurrent.futures
import csv
import uuid
import signal
import sys
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse
from tqdm import tqdm

# --- 1. CONFIGURATION ---
JAXA_USER = "aizat"
JAXA_PASS = "Aiz@t.900627"
MAX_WORKERS = 15
MIN_SIZE_BYTES = 50 * 1024  # 50KB threshold

FEDEO_SEARCH_URL = "https://fedeo.ceos.org/collections/datasets/items"
BBOX = "99.3,0.6,119.8,7.8"
BASE_DIR = "./malaysia_amsr2_jaxa_fedeo"
LOG_FILE = "missing_dates_log.csv"

# Map CSV column names to Product IDs
PRODUCT_MAP = {
    "23GHz": "GCOM-W_AMSR2_L3_T23_1day_0.1deg",
    "89GHz": "GCOM-W_AMSR2_L3_T89_1day_0.1deg",
    "SMC":   "GCOM-W_AMSR2_L3_SMC_1day_0.1deg"
}

# --- 2. ROBUST SESSION ---
def create_robust_session():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# --- 3. HELPER FUNCTIONS ---
def get_download_url_from_feature(feature):
    try:
        assets = feature.get('assets', {})
        for key, asset in assets.items():
            if 'data' in asset.get('roles', []) or key == 'data':
                return asset['href']
        links = feature.get('links', [])
        for link in links:
            if link.get('rel') == 'enclosure' or link.get('rel') == 'data':
                return link.get('href')
        return feature.get('properties', {}).get('productUrl')
    except:
        return None

def download_task_surgical(task_info):
    url, folder = task_info
    try:
        filename = url.split('/')[-1].split('?')[0]
    except:
        return f"Skipped: Invalid URL"

    local_path = os.path.join(folder, filename)

    # 1. CHECK EXISTING
    if os.path.exists(local_path):
        if os.path.getsize(local_path) > MIN_SIZE_BYTES:
            return f"Skipped (Exists): {filename}"
        else:
            try:
                os.remove(local_path)
            except: pass

    unique_id = str(uuid.uuid4())[:8]
    temp_path = f"{local_path}.{unique_id}.tmp"
    
    session = create_robust_session()
    auth = None
    if "jaxa.jp" in urlparse(url).netloc:
        auth = HTTPBasicAuth(JAXA_USER, JAXA_PASS)

    try:
        with session.get(url, auth=auth, stream=True, timeout=90) as r:
            if r.status_code == 401: return f"Auth Failed: {filename}"
            r.raise_for_status()
            
            total_size = int(r.headers.get('content-length', 0))
            
            with open(temp_path, 'wb') as f:
                downloaded_size = 0
                for chunk in r.iter_content(chunk_size=32768):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

            if downloaded_size < MIN_SIZE_BYTES:
                raise Exception(f"Too small ({downloaded_size} B)")
            
            if total_size > 0 and downloaded_size != total_size:
                raise Exception(f"Incomplete ({downloaded_size}/{total_size})")

        os.rename(temp_path, local_path)
        return None 

    except Exception as e:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass
        return f"Error {filename}: {e}"
    finally:
        session.close()

# --- 4. MAIN LOGIC ---
def main():
    print("--- JAXA SURGICAL REPAIR (Targeting Logged Gaps) ---")
    
    if not os.path.exists(LOG_FILE):
        print(f"[ERROR] {LOG_FILE} not found. Run generate_missing_report.py first!")
        return

    download_queue = set()
    session = create_robust_session()
    
    # --- STEP 1: PARSE CSV ---
    print(f"\n[Phase 1] Reading {LOG_FILE} to find targets...")
    
    targets = []
    with open(LOG_FILE, "r") as f:
        reader = csv.DictReader(f) # Expects: Date, 23GHz, 89GHz, SMC, Reason
        for row in reader:
            # We filter specifically for the failures we saw in your report
            if "DOWNLOAD ERROR" in row.get("Reason", ""):
                # Identify which specific product is missing for this day
                missing_products = []
                for col_name in ["23GHz", "89GHz", "SMC"]:
                    if row.get(col_name) == "MISSING":
                        missing_products.append(col_name)
                
                if missing_products:
                    # Append (Date, [List of Missing Products])
                    # Remove whitespace from date just in case
                    date_clean = row["Date"].strip()
                    targets.append((date_clean, missing_products))

    print(f"  > Identified {len(targets)} days with partial data.")
    print(f"  > Starting Day-by-Day Search (100% precision)...")

    # --- STEP 2: SEARCH DAY BY DAY ---
    for i, (date_str, products_needed) in enumerate(targets):
        # Format: 2020-01-26
        # Time range: start of day to end of day
        start_t = f"{date_str}T00:00:00Z"
        end_t   = f"{date_str}T23:59:59Z"
        
        print(f"  [{i+1}/{len(targets)}] Fixing {date_str}: {products_needed}...", end='\r')
        
        for prod_name in products_needed:
            parent_id = PRODUCT_MAP[prod_name]
            folder = os.path.join(BASE_DIR, prod_name)
            os.makedirs(folder, exist_ok=True)
            
            params = {
                "httpAccept": "application/geo+json",
                "parentIdentifier": parent_id,
                "bbox": BBOX,
                "datetime": f"{start_t}/{end_t}",
                "limit": 20 # Only expect ~2-4 files per day per product
            }
            
            try:
                r = session.get(FEDEO_SEARCH_URL, params=params, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    for feature in data.get('features', []):
                        dl_url = get_download_url_from_feature(feature)
                        if dl_url:
                            download_queue.add((dl_url, folder))
            except:
                pass

    final_queue = list(download_queue)
    print(f"\n\n[Phase 1 Complete] Found {len(final_queue)} files to patch.")
    
    # --- STEP 3: DOWNLOAD ---
    if not final_queue:
        print("No recoverable files found. The remaining gaps might be real satellite outages.")
        return

    print(f"\n[Phase 2] Downloading Patch...")
    
    def signal_handler(sig, frame):
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(tqdm(
            executor.map(download_task_surgical, final_queue), 
            total=len(final_queue),
            unit="file",
            smoothing=0.01
        ))

    # --- SUMMARY ---
    errors = [res for res in results if res and "Skipped" not in res]
    success = len(final_queue) - len(errors)
    
    print("\n" + "="*40)
    print("SURGICAL FIX COMPLETE")
    print(f"Files Restored: {success}")
    print(f"Errors:         {len(errors)}")
    print("="*40)
    
    if errors:
        for e in errors[:5]: print(e)

if __name__ == "__main__":
    main()