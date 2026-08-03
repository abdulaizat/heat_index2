#!/bin/bash

# Directory for raw data
RAW_DIR="/mnt/AizatDrive/global_drivers/raw"
mkdir -p "$RAW_DIR"

# 1. MJO (BOM)
# Requires User-Agent to avoid 403 Forbidden
# Format: Year, Month, Day, RMM1, RMM2, Phase, Amplitude, Source
echo "Downloading MJO data..."
wget --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36" \
     -O "$RAW_DIR/mjo_rmm.txt" \
     "https://www.bom.gov.au/clim_data/IDCKGEM000/rmm.74toRealtime.txt"

# 2. ENSO (NOAA ONI)
# Format: Season, Year, Total, Anom (columns repeated)
echo "Downloading ENSO (ONI) data..."
wget -O "$RAW_DIR/enso_oni.txt" \
     "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

# 3. IOD (NOAA CPC)
# Format: Year, Season, WTIO, SETIO, DMI
echo "Downloading IOD (DMI) data..."
wget -O "$RAW_DIR/iod_dmi_season.txt" \
     "https://www.cpc.ncep.noaa.gov/products/international/ocean_monitoring/IODMI/mnth.ersstv5.clim19912020.dmi_season.txt"

# 4. BSISO (APCC monitoring)
# Format: Year, Day-of-year, BSISO1-1, BSISO1-2, BSISO2-1, BSISO2-2, BSISO1, BSISO2
echo "Downloading BSISO monitoring data..."
wget --tries=3 --timeout=30 -O "$RAW_DIR/bsiso_index_norm_ly.data" \
     "https://download.apcc21.org/BSISO/BSISO.INDEX.NORM.LY.data"

echo "Download complete. Check $RAW_DIR for files."
ls -lh "$RAW_DIR"
