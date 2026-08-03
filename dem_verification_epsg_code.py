import rasterio

# Path to your file
file_path = "/mnt/AizatDrive/IFSAR/SEMENANJUNG 2017/DTM/GeoTIFF/AO44154.tif"

try:
    with rasterio.open(file_path) as src:
        print(f"File: {file_path}")
        print(f"CRS: {src.crs}")
        
        # Check the code
        if src.crs.to_string() == "EPSG:3375":
            print("✅ CONFIRMED: Peninsular RSO (Correct)")
        elif src.crs.to_string() == "EPSG:3376":
            print("✅ CONFIRMED: Borneo RSO (Correct)")
        else:
            print(f"⚠️  WARNING: Unexpected CRS: {src.crs}")
            
except FileNotFoundError:
    print("File not found.")
except Exception as e:
    print(f"Error: {e}")