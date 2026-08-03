import cdsapi
import os
from calendar import monthrange

# Configuration
CDS_URL = "https://cds.climate.copernicus.eu/api"
# User ID: df9b1097-0b99-449f-9fca-f94389459f29
# API Key: 35f49dcc-3ae2-460e-9976-c15fbc81a08d
CDS_KEY = "35f49dcc-3ae2-460e-9976-c15fbc81a08d"

OUTPUT_DIR = "/mnt/AizatDrive/ERA5_Land"
DOMAIN = [7.8, 99.3, 0.6, 119.8] # North, West, South, East

VARIABLES = [
    '2m_temperature',
    '2m_dewpoint_temperature',
    'surface_pressure',
    '10m_u_component_of_wind',
    '10m_v_component_of_wind',
    'total_precipitation',
]

def main():
    if not os.path.exists(OUTPUT_DIR):
        print(f"Creating output directory: {OUTPUT_DIR}")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    client = cdsapi.Client(url=CDS_URL, key=CDS_KEY)

    years = [str(y) for y in range(2026, 2026)] # 2025
    months = [f"{m:02d}" for m in range(1, 13)]
    
    for year in years:
        for month in months:
            target_file = os.path.join(OUTPUT_DIR, f"era5_land_{year}_{month}.nc")
            
            if os.path.exists(target_file):
                print(f"File already exists, skipping: {target_file}")
                continue
                
            print(f"Downloading data for {year}-{month}...")
            
            # Days in month
            _, num_days = monthrange(int(year), int(month))
            days = [f"{d:02d}" for d in range(1, num_days + 1)]
            
            request = {
                'format': 'netcdf',
                'variable': VARIABLES,
                'year': year,
                'month': month,
                'day': days,
                'time': [f"{h:02d}:00" for h in range(24)],
                'area': DOMAIN,
            }
            
            try:
                client.retrieve('reanalysis-era5-land', request, target_file)
                print(f"Successfully downloaded: {target_file}")
            except Exception as e:
                print(f"Error downloading {year}-{month}: {e}")

if __name__ == "__main__":
    main()
