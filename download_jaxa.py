import requests
import os
import time
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse

# --- 1. CONFIGURATION ---
# JAXA G-Portal Credentials
JAXA_USER = "aizat"
JAXA_PASS = "Aiz@t.900627"

# Search Parameters
FEDEO_SEARCH_URL = "https://fedeo.ceos.org/collections/datasets/items"
BBOX = "99.3,0.6,119.8,7.8"  # West, South, East, North
START_DATE = "2020-01-01T00:00:00Z"
END_DATE =   "2024-12-31T23:59:59Z"

# Collections to download
collections = {
    "23GHz": "GCOM-W_AMSR2_L3_T23_1day_0.1deg",
    "89GHz": "GCOM-W_AMSR2_L3_T89_1day_0.1deg",
    "SMC":   "GCOM-W_AMSR2_L3_SMC_1day_0.1deg"
}

BASE_DIR = "./malaysia_amsr2_jaxa_fedeo"

# --- 2. FUNCTIONS ---

def get_download_url_from_feature(feature):
    """Extracts the data download link from the GeoJSON feature."""
    # Method A: Look in 'assets' (STAC/GeoJSON standard)
    assets = feature.get('assets', {})
    for key, asset in assets.items():
        if 'data' in asset.get('roles', []) or key == 'data':
            return asset['href']
            
    # Method B: Look in 'links' (older OpenSearch style)
    links = feature.get('links', [])
    for link in links:
        if link.get('rel') == 'enclosure' or link.get('rel') == 'data':
            return link.get('href')
            
    # Fallback: check properties for a direct link
    return feature.get('properties', {}).get('productUrl')

def download_file(url, folder, session):
    filename = url.split('/')[-1].split('?')[0] 
    local_path = os.path.join(folder, filename)
    
    if os.path.exists(local_path):
        print(f"  Skipping (exists): {filename}")
        return

    print(f"  Downloading: {filename}")
    
    # Check if this is a JAXA link requiring auth
    auth = None
    if "jaxa.jp" in urlparse(url).netloc:
        auth = HTTPBasicAuth(JAXA_USER, JAXA_PASS)
        
    try:
        # Stream download
        with session.get(url, auth=auth, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print(f"  Error downloading {filename}: {e}")

# --- 3. MAIN EXECUTION ---

session = requests.Session()

for name, parent_id in collections.items():
    print(f"\n--- Processing Collection: {name} ({parent_id}) ---")
    
    folder = os.path.join(BASE_DIR, name)
    os.makedirs(folder, exist_ok=True)
    
    start_index = 0
    items_per_page = 50 
    
    while True:
        params = {
            "httpAccept": "application/geo+json",
            "parentIdentifier": parent_id,
            "bbox": BBOX,
            "datetime": f"{START_DATE}/{END_DATE}",
            "startRecord": start_index,
            "limit": items_per_page
        }
        
        try:
            r = session.get(FEDEO_SEARCH_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            
            features = data.get('features', [])
            if not features:
                print("  No more results found.")
                break
                
            print(f"  Page starting at {start_index}: Found {len(features)} items.")
            
            for feature in features:
                dl_url = get_download_url_from_feature(feature)
                if dl_url:
                    download_file(dl_url, folder, session)
            
            total_results = data.get('totalResults')
            start_index += len(features)
            
            if (total_results and start_index >= total_results) or len(features) < items_per_page:
                break
                
        except Exception as e:
            print(f"  Search Error on index {start_index}: {e}")
            break

print("\n[JAXA/FedEO] All downloads complete.")