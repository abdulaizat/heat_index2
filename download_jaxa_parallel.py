import requests
import os
import concurrent.futures
import time
import uuid
import calendar
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

# LOWERED THRESHOLD: 50KB (Valid SMC files are ~1.3MB)
MIN_SIZE_BYTES = 50 * 1024 

FEDEO_SEARCH_URL = "https://fedeo.ceos.org/collections/datasets/items"
BBOX = "99.3,0.6,119.8,7.8"
BASE_DIR = "./malaysia_amsr2_jaxa_fedeo"
YEARS = [2020, 2021, 2022, 2023, 2024]

collections = {
    "23GHz": "GCOM-W_AMSR2_L3_T23_1day_0.1deg",
    "89GHz": "GCOM-W_AMSR2_L3_T89_1day_0.1deg",
    "SMC":   "GCOM-W_AMSR2_L3_SMC_1day_0.1deg"
}

# --- 2. ROBUST SESSION ---
def create_robust_session():
    session = requests.Session()
    retry = Retry(total=8, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
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

def download_task_fixed(task_info):
    url, folder = task_info
    try:
        filename = url.split('/')[-1].split('?')[0]
    except:
        return f"Skipped: Invalid URL"

    local_path = os.path.join(folder, filename)

    # 1. CHECK EXISTING FILE (Resume Logic)
    if os.path.exists(local_path):
        # If it exists and is bigger than 50KB, keep it.
        if os.path.getsize(local_path) > MIN_SIZE_BYTES:
            return f"Skipped (Valid): {filename}"
        else:
            # If it's tiny (<50KB), it's garbage. Delete and redownload.
            try:
                os.remove(local_path)
            except:
                pass

    unique_id = str(uuid.uuid4())[:8]
    temp_path = f"{local_path}.{unique_id}.tmp"
    
    session = create_robust_session()
    auth = None
    if "jaxa.jp" in urlparse(url).netloc:
        auth = HTTPBasicAuth(JAXA_USER, JAXA_PASS)

    try:
        with session.get(url, auth=auth, stream=True, timeout=90) as r:
            if r.status_code == 401: return f"Auth Failed: {filename}"
            if r.status_code == 403: return f"Access Denied: {filename}"
            r.raise_for_status()
            
            total_size = int(r.headers.get('content-length', 0))
            
            with open(temp_path, 'wb') as f:
                downloaded_size = 0
                for chunk in r.iter_content(chunk_size=32768):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

            # 2. CORRECTED INTEGRITY CHECK
            if downloaded_size < MIN_SIZE_BYTES:
                raise Exception(f"File too small ({downloaded_size} bytes). HTML error?")
            
            if total_size > 0 and downloaded_size != total_size:
                raise Exception(f"Incomplete: {downloaded_size}/{total_size}")

        os.rename(temp_path, local_path)
        return None 

    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except: 
                pass
        return f"Error {filename}: {e}"
    finally:
        session.close()

# --- 4. MAIN LOGIC ---
def main():
    print(f"--- JAXA SMC REPAIR DOWNLOAD ---")
    print(f"--- Threshold Lowered to 50KB ---")
    
    download_queue = set() 
    session = create_robust_session()
    
    # --- PHASE 1: SEARCH ---
    print("\n[Phase 1] Indexing missing files...")
    
    for year in YEARS:
        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            start_date = f"{year}-{month:02d}-01T00:00:00Z"
            end_date = f"{year}-{month:02d}-{last_day:02d}T23:59:59Z"
            
            print(f"Scanning {year}-{month:02d}...", end='\r')
            
            for name, parent_id in collections.items():
                folder = os.path.join(BASE_DIR, name)
                os.makedirs(folder, exist_ok=True)
                
                start_index = 0
                items_per_page = 100
                
                while True:
                    params = {
                        "httpAccept": "application/geo+json",
                        "parentIdentifier": parent_id,
                        "bbox": BBOX,
                        "datetime": f"{start_date}/{end_date}",
                        "startRecord": start_index,
                        "limit": items_per_page
                    }
                    
                    try:
                        r = session.get(FEDEO_SEARCH_URL, params=params, timeout=30)
                        if r.status_code != 200: break 
                        data = r.json()
                        features = data.get('features', [])
                        if not features: break
                        
                        for feature in features:
                            dl_url = get_download_url_from_feature(feature)
                            if dl_url:
                                download_queue.add((dl_url, folder))
                        
                        total = data.get('totalResults')
                        start_index += len(features)
                        if (total and start_index >= total) or len(features) < items_per_page:
                            break
                    except:
                        break

    final_queue = list(download_queue)
    print(f"\n\n[Phase 1 Complete] Found {len(final_queue)} files.")
    
    # --- PHASE 2: DOWNLOAD ---
    if not final_queue: return

    print(f"\n[Phase 2] Downloading with corrected threshold...")
    
    def signal_handler(sig, frame):
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(tqdm(
            executor.map(download_task_fixed, final_queue), 
            total=len(final_queue),
            unit="file",
            smoothing=0.01
        ))

    # --- REPORT ---
    errors = [res for res in results if res and "Skipped" not in res]
    skipped = [res for res in results if res and "Skipped" in res]
    success = len(final_queue) - len(errors) - len(skipped)
    
    print("\n" + "="*40)
    print("REPAIR SUMMARY")
    print(f"Total Files:      {len(final_queue)}")
    print(f"Valid (Skipped):  {len(skipped)}")
    print(f"SMC Fixed:        {success}")
    print(f"Errors:           {len(errors)}")
    
    if errors:
        for e in errors[:5]: print(e)

if __name__ == "__main__":
    main()