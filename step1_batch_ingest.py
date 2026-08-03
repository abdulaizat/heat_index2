import pandas as pd
import numpy as np
import os
import glob

# --- Configuration ---
ROOT_DIR = '/home/NWP5/heat_index2/station_data'
OUTPUT_FILE = '/home/NWP5/heat_index2/station_data/malaysia_station_data_2020_2024_clean.parquet'

def clean_metmalaysia_data(df, filename):
    try:
        # 1. Clean Column Headers
        df.columns = [str(c).strip() for c in df.columns]
        
        # 2. Define Mapping (Priority: WMOINDEX -> station_id)
        col_map = {
            # Primary Identifier
            'WMOINDEX': 'station_id', 'WMO Index': 'station_id', 
            
            # Fallback for Name (optional, we keep it for reference)
            'STATION NAME': 'station_name', 'Station Name': 'station_name', 'STATION': 'station_name',
            
            # Variables
            'DRY': 'temp_obs', 'Dry Bulb': 'temp_obs', 'TEMP': 'temp_obs',
            'RH': 'rh_obs', 'Relative Humidity': 'rh_obs', 'HUMIDITY': 'rh_obs',
            
            # Date Components
            'YEAR': 'year', 'Year': 'year',
            'MTH': 'month', 'Month': 'month',
            'DAY': 'day', 'Day': 'day',
            'HOUR': 'hour', 'Hour': 'hour'
        }
        
        df = df.rename(columns=col_map)
        
        # 3. Handle Identifier Strategy
        # If 'station_id' (WMO) exists, use it. 
        # If not, but 'station_name' exists, use that as station_id.
        if 'station_id' not in df.columns and 'station_name' in df.columns:
            df['station_id'] = df['station_name']
        
        # Check requirements again
        req_cols = ['station_id', 'year', 'month', 'day', 'hour', 'temp_obs', 'rh_obs']
        missing = [c for c in req_cols if c not in df.columns]
        
        if missing:
            print(f"⚠️  Skipping {filename}: Missing {missing}. Found: {list(df.columns)}")
            return None
            
        # Select and Copy
        df = df[req_cols].copy()

        # 4. Force Numeric Types
        for col in ['year', 'month', 'day', 'hour', 'temp_obs', 'rh_obs']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Drop NaNs in critical columns
        df = df.dropna(subset=['station_id', 'year', 'month', 'day', 'hour', 'temp_obs'])

        # 5. The "Hour 24" Fix
        df['hour_adj'] = df['hour'] - 1
        df['timestamp'] = pd.to_datetime(df[['year', 'month', 'day']]) + \
                          pd.to_timedelta(df['hour_adj'], unit='h')
        df['timestamp'] = df['timestamp'] + pd.Timedelta(hours=1)
        
        # 6. Standardize Station ID to String (e.g. "48601")
        df['station_id'] = df['station_id'].astype(int).astype(str)
        
        return df[['timestamp', 'station_id', 'temp_obs', 'rh_obs']]

    except Exception as e:
        print(f"❌ Error in {filename}: {e}")
        return None

# --- Main Execution ---
all_frames = []
files_processed = 0

print(f"🚀 Starting V3 Ingestion (WMO Priority)...")

for root, dirs, files in os.walk(ROOT_DIR):
    for file in sorted(files):
        file_path = os.path.join(root, file)
        
        try:
            # Detect Format
            if file.endswith('.xlsx'):
                df_raw = pd.read_excel(file_path, engine='openpyxl')
            elif file.endswith('.xls'):
                df_raw = pd.read_excel(file_path, engine='xlrd')
            elif file.endswith('.csv'):
                df_raw = pd.read_csv(file_path)
            else:
                continue 

            df_clean = clean_metmalaysia_data(df_raw, file)
            
            if df_clean is not None:
                all_frames.append(df_clean)
                files_processed += 1
                # print(f"✅ Loaded: {file}")

        except Exception as e:
            print(f"❌ FAILED {file}: {e}")

if all_frames:
    print("\n📦 Concatenating...")
    master_df = pd.concat(all_frames, ignore_index=True)
    master_df = master_df.sort_values(['timestamp', 'station_id'])
    
    # Save
    master_df.to_parquet(OUTPUT_FILE, index=False)
    
    print(f"\n🎉 SUCCESS! Processed {files_processed} files.")
    print(f"📊 Total Rows: {len(master_df)}")
    print(f"📄 Saved to: {OUTPUT_FILE}")
else:
    print("\n⚠️ No data found.")