# AMSR-2 Microwave Data Download Guide

This repository contains scripts to download AMSR-2 (Advanced Microwave Scanning Radiometer 2) data from JAXA's G-Portal for the period 2020-2024.

## Domain Configuration

**Target Region**: Malaysia
**Domain Coordinates**: [7.8°N, 99.3°E, 0.6°N, 119.8°E]
**Coverage**: 7.2°N-S, 20.5°E-W (147.6 square degrees)
**Area**: Covers Malaysian territory including Peninsular Malaysia, Sabah, Sarawak, and surrounding maritime zones

## Data Description

**Satellite**: GCOM-W1 (Global Change Observation Mission - Water)  
**Instrument**: AMSR-2 (Advanced Microwave Scanning Radiometer 2)  
**Level**: 3 (L3) Daily products  
**Resolution**: 10km (0.1deg)  

### Frequencies Downloaded

1. **06GHz** - Penetrates heavy rain/vegetation
2. **10GHz** - Standard brightness temperature
3. **18GHz** - Standard brightness temperature
4. **23GHz** - Water vapor sensitive
5. **36GHz** - Standard brightness temperature
6. **89GHz** - High resolution, scatters on smoke (crucial for haze detection)

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Download Script
```bash
chmod +x download_amsr2.sh
./download_amsr2.sh
```

### 3. Alternative: Run Python Script Directly
```bash
python3 download_amsr2_data.py --start-year 2020 --end-year 2024
```

## Configuration

### G-Portal Credentials
- **Username**: aizat
- **Password**: Aiz@t.900627
- **Host**: ftp.gportal.jaxa.jp
- **Port**: 2051
- **Protocol**: SFTP

### Customization Options

You can customize the download using command-line arguments:

```bash
python3 download_amsr2_data.py \
    --start-year 2020 \
    --end-year 2024 \
    --frequencies 06GHz 10GHz 18GHz 23GHz 36GHz 89GHz \
    --workers 4
```

**Available Options:**
- `--start-year`: Start year (default: 2020)
- `--end-year`: End year (default: 2024)
- `--frequencies`: List of frequencies to download (default: all)
- `--workers`: Number of concurrent downloads (default: 4)

## Data Structure

The downloaded data will be organized as follows:

```
/run/media/NWP5/One Touch/amsr2_data/
├── 06GHz/
│   ├── 2020/
│   │   ├── 01/
│   │   │   ├── 20200101/
│   │   │   │   ├── AMSR2_L3_TB_20200101_06GHz_0.1deg.h5
│   │   │   │   └── ...
│   │   │   ├── 20200102/
│   │   │   └── ...
│   │   └── ...
│   └── ...
├── 10GHz/
├── 18GHz/
├── 23GHz/
├── 36GHz/
└── 89GHz/
```

## File Formats

AMSR-2 data is typically provided in:
- **HDF5** (.h5 files)
- **NetCDF** (.nc files)

## Monitoring Download Progress

- **Log File**: `amsr2_download.log`
- **Console Output**: Real-time progress updates
- **Status Messages**: 
  - ✅ Downloaded files
  - ⚠️ Missing files for specific dates
  - ❌ Failed downloads

## Estimated Data Volume

For 5 years (2020-2024) with 6 frequencies:
- **Total Days**: 1,826 days
- **Total Files**: ~10,956 files (6 frequencies × 1,826 days)
- **Estimated Size**: 50-100 GB (depending on compression)

## Troubleshooting

### Connection Issues
- Verify internet connection
- Check G-Portal credentials
- Ensure SFTP port 2051 is accessible

### Download Failures
- Check available disk space
- Verify write permissions in `/run/media/NWP5/One Touch/`
- Review `amsr2_download.log` for specific errors

### Slow Downloads
- Reduce `--workers` parameter
- Check network bandwidth
- Consider downloading during off-peak hours

## Notes

1. **Data Access**: Requires valid G-Portal account credentials
2. **Storage**: Ensure sufficient disk space (recommended: 200 GB free)
3. **Time**: Full download may take several hours to days depending on connection
4. **Resume**: Script can be re-run to download missing files

## Support

For issues or questions:
1. Check the log file: `amsr2_download.log`
2. Verify credentials and network connectivity
3. Ensure sufficient disk space and permissions