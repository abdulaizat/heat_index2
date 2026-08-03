import earthaccess
import os

# --- 1. SETUP ---
# Set environment variables for authentication
os.environ["EARTHDATA_USERNAME"] = "abdulaizat"
os.environ["EARTHDATA_PASSWORD"] = "Gr7$ndkL!p2e"

# Authenticate with provided credentials
auth = earthaccess.login(strategy="environment")

# --- 2. CONFIGURATION ---
# Malaysia Bounding Box: [West, South, East, North]
bbox = (99.3, 0.6, 119.8, 7.8)
date_range = ("2020-01-01", "2024-12-31")
download_dir = "/mnt/AizatDrive/malaysia_amsr2_nasa"

os.makedirs(download_dir, exist_ok=True)

# --- 3. SEARCH & DOWNLOAD ---
datasets = [
    "LPRM_AMSR2_DS_A_SOILM3", # Ascending
    "LPRM_AMSR2_DS_D_SOILM3"  # Descending
]

for short_name in datasets:
    print(f"\n[NASA] Searching for {short_name}...")
    results = earthaccess.search_data(
        short_name=short_name,
        temporal=date_range,
        bounding_box=bbox
    )
    
    print(f"[NASA] Found {len(results)} granules. Starting download...")
    earthaccess.download(results, download_dir)

print("\n[NASA] Download Complete.")