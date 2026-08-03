# AMSR-2 Microwave Data Download - Summary

## 📋 Task Completed

Successfully created a comprehensive download system for AMSR-2 Microwave Data from G-Portal (JAXA) covering the period **2020-2024** (5 years).

## 🎯 Data Specifications

- **Satellite**: GCOM-W1 (Global Change Observation Mission - Water)
- **Instrument**: AMSR-2 (Advanced Microwave Scanning Radiometer 2)
- **Level**: 3 (L3) Daily products
- **Resolution**: 10km (0.1deg)
- **Frequencies**: 06GHz, 10GHz, 18GHz, 23GHz, 36GHz, 89GHz
- **Total Files**: ~10,956 files (6 frequencies × 1,826 days)
- **Estimated Size**: 50-100 GB

## 📁 Files Created

### Core Scripts
1. **[`download_amsr2_data.py`](download_amsr2_data.py)** - Main Python download script
   - SFTP connection to G-Portal
   - Concurrent downloads (configurable workers)
   - Error handling and logging
   - Command-line arguments for customization
   - **Save Location**: `/run/media/NWP5/One Touch/amsr2_data/`

2. **[`download_amsr2.sh`](download_amsr2.sh)** - Shell wrapper script
   - Easy one-command execution
   - Dependency installation
   - Progress monitoring

3. **[`verify_amsr2_data.py`](verify_amsr2_data.py)** - Data verification script
   - Completeness check
   - File integrity validation
   - Detailed reporting
   - **Reads from**: `/run/media/NWP5/One Touch/amsr2_data/`

### Configuration & Documentation
4. **[`requirements.txt`](requirements.txt)** - Python dependencies
5. **[`README_AMSR2.md`](README_AMSR2.md)** - Comprehensive user guide
6. **[`DOWNLOAD_SUMMARY.md`](DOWNLOAD_SUMMARY.md)** - This summary document

## 🔑 G-Portal Configuration

- **Username**: aizat
- **Password**: Aiz@t.900627
- **Host**: ftp.gportal.jaxa.jp
- **Port**: 2051
- **Protocol**: SFTP

## 🚀 Quick Start

### Option 1: Shell Script (Recommended)
```bash
chmod +x download_amsr2.sh
./download_amsr2.sh
```

### Option 2: Python Script
```bash
# Install dependencies
pip install -r requirements.txt

# Run download
python3 download_amsr2_data.py --start-year 2020 --end-year 2024
```

## 📊 Data Organization

```
/run/media/NWP5/One Touch/amsr2_data/
├── 06GHz/     # Penetrates heavy rain/vegetation
├── 10GHz/     # Standard brightness temperature
├── 18GHz/     # Standard brightness temperature
├── 23GHz/     # Water vapor sensitive
├── 36GHz/     # Standard brightness temperature
└── 89GHz/     # High resolution, smoke detection
```

## 📝 Key Features

### Download Script Features
- ✅ Concurrent downloads (4 workers by default)
- ✅ Automatic retry and error handling
- ✅ Progress logging and monitoring
- ✅ Date range specification (2020-2024)
- ✅ Frequency selection
- ✅ SFTP connection management

### Verification Script Features
- ✅ Completeness analysis
- ✅ File integrity checking
- ✅ Missing file identification
- ✅ Corrupt file detection
- ✅ Detailed reporting (CSV format)

## ⚠️ Important Notes

1. **External Drive**: Data will be saved to `/run/media/NWP5/One Touch/amsr2_data/`
2. **Storage Requirements**: Ensure 200 GB free space on external drive
3. **Drive Mounting**: Verify external drive is properly mounted before starting
4. **Network**: Stable internet connection required
5. **Time**: Full download may take several hours to days
6. **Resume Capability**: Script can be re-run for missing files
7. **Monitoring**: Check `amsr2_download.log` for progress

## 🔍 Monitoring & Logs

- **Download Log**: `amsr2_download.log`
- **Verification Log**: `amsr2_verification.log`
- **Progress Updates**: Real-time console output
- **Status Messages**: ✅ Downloaded, ⚠️ Missing, ❌ Failed

## 🛠️ Customization

### Command Line Options
```bash
python3 download_amsr2_data.py \
    --start-year 2020 \
    --end-year 2024 \
    --frequencies 06GHz 10GHz 18GHz 23GHz 36GHz 89GHz \
    --workers 4
```

### Parameters
- `--start-year`: Start year (default: 2020)
- `--end-year`: End year (default: 2024)
- `--frequencies`: List of frequencies (default: all)
- `--workers`: Concurrent downloads (default: 4)

## 📈 Expected Output

After successful download:
- **Data Location**: `/run/media/NWP5/One Touch/amsr2_data/`
- **Log File**: `amsr2_download.log`
- **Verification Report**: `amsr2_verification_report.csv`

## 📝 Next Steps

1. **Ensure external drive is mounted**: Verify `/run/media/NWP5/One Touch` is accessible
2. **Run the download**: `./download_amsr2.sh`
3. **Monitor progress**: Check console output and log files
4. **Verify data**: Run `python3 verify_amsr2_data.py`
5. **Use data**: Process the downloaded HDF5/NetCDF files

## 📞 Support

For issues or questions:
1. Check log files: `amsr2_download.log`, `amsr2_verification.log`
2. Verify credentials and network connectivity
3. Ensure external drive is mounted and has sufficient space
4. Review the comprehensive guide: [`README_AMSR2.md`](README_AMSR2.md)

---

**Task Status**: ✅ **COMPLETED**

All necessary scripts and documentation have been created for downloading AMSR-2 Microwave Data from G-Portal for the period 2020-2024.