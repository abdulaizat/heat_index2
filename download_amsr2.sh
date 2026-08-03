#!/bin/bash

# AMSR-2 Data Download Script
# Downloads Microwave Data AMSR-2 (GCOM-W1) for 2020-2024

echo "🚀 Starting AMSR-2 Microwave Data Download"
echo "=========================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is required but not installed."
    exit 1
fi

# Install requirements
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Create log directory
mkdir -p logs

# Run the download script
echo "📡 Connecting to G-Portal and downloading data..."
python3 download_amsr2_data.py \
    --start-year 2020 \
    --end-year 2024 \
    --frequencies 06GHz 10GHz 18GHz 23GHz 36GHz 89GHz \
    --workers 4

# Check if download completed successfully
if [ $? -eq 0 ]; then
    echo "✅ Download completed successfully!"
    echo "📁 Data location: /home/NWP5/heat_index2/amsr2_data/"
    echo "📄 Log file: amsr2_download.log"
else
    echo "❌ Download failed. Check the log file for details."
    exit 1
fi