#!/usr/bin/env python3
"""
AMSR-2 Data Verification Script
Checks the completeness and integrity of downloaded AMSR-2 data
Target Region: Malaysia (Domain: 7.8°N, 99.3°E, 0.6°N, 119.8°E)
"""

import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import h5py
import logging

# Import configuration
from amsr2_config import (
    LOCAL_BASE_DIR, FREQUENCIES, display_domain_info
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('amsr2_verification.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_date_range(start_year: int, end_year: int):
    """Generate all dates from start_year to end_year."""
    dates = []
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)
    
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)
    
    return dates


def check_file_integrity(file_path: Path) -> bool:
    """Check if a file is readable and has valid content."""
    try:
        if file_path.suffix == '.h5':
            with h5py.File(file_path, 'r') as f:
                # Basic check: can we open the file?
                pass
        return True
    except Exception as e:
        logger.warning(f"File integrity check failed for {file_path}: {e}")
        return False


def verify_data():
    """Main verification function."""
    # Display domain information
    display_domain_info()
    
    logger.info("🔍 Starting AMSR-2 Data Verification")
    
    # Generate expected dates
    dates = get_date_range(2020, 2024)
    logger.info(f"Expected {len(dates)} days of data (2020-2024)")
    
    # Track results
    missing_files = []
    corrupt_files = []
    total_expected = 0
    total_found = 0
    
    # Check each frequency and date
    for freq in FREQUENCIES:
        logger.info(f"Checking frequency: {freq}")
        freq_path = Path(LOCAL_BASE_DIR) / freq
        
        if not freq_path.exists():
            logger.warning(f"❌ Frequency directory missing: {freq_path}")
            continue
        
        for date in dates:
            year = date.year
            month = date.month
            day = date.day
            
            date_path = freq_path / f"{year:04d}" / f"{month:02d}" / f"{year:04d}{month:02d}{day:02d}"
            
            # Look for data files
            data_files = list(date_path.glob("*.h5")) + list(date_path.glob("*.nc"))
            
            if not data_files:
                missing_files.append((date, freq))
                total_expected += 1
            else:
                total_found += len(data_files)
                total_expected += 1
                
                # Check file integrity
                for file_path in data_files:
                    if not check_file_integrity(file_path):
                        corrupt_files.append((date, freq, file_path))
    
    # Report results
    logger.info("\n" + "="*60)
    logger.info("📊 VERIFICATION RESULTS")
    logger.info("="*60)
    
    logger.info(f"Expected files: {total_expected}")
    logger.info(f"Found files: {total_found}")
    logger.info(f"Missing files: {len(missing_files)}")
    logger.info(f"Corrupt files: {len(corrupt_files)}")
    
    if missing_files:
        logger.warning(f"\n❌ Missing {len(missing_files)} files:")
        for date, freq in missing_files[:10]:  # Show first 10
            logger.warning(f"  - {date.strftime('%Y-%m-%d')} at {freq}")
        if len(missing_files) > 10:
            logger.warning(f"  ... and {len(missing_files) - 10} more")
    
    if corrupt_files:
        logger.error(f"\n💥 Found {len(corrupt_files)} corrupt files:")
        for date, freq, path in corrupt_files:
            logger.error(f"  - {date.strftime('%Y-%m-%d')} at {freq}: {path}")
    
    # Calculate completeness
    completeness = (total_found / total_expected) * 100 if total_expected > 0 else 0
    logger.info(f"\n📈 Overall completeness: {completeness:.1f}%")
    
    if completeness >= 95:
        logger.info("✅ Data appears to be mostly complete!")
    elif completeness >= 80:
        logger.warning("⚠️  Data has some missing files")
    else:
        logger.error("❌ Data is significantly incomplete")
    
    # Save detailed report
    if missing_files or corrupt_files:
        report_df = pd.DataFrame({
            'date': [d.strftime('%Y-%m-%d') for d, _ in missing_files],
            'frequency': [f for _, f in missing_files],
            'status': ['missing'] * len(missing_files)
        })
        
        corrupt_df = pd.DataFrame({
            'date': [d.strftime('%Y-%m-%d') for d, f, _ in corrupt_files],
            'frequency': [f for _, f, _ in corrupt_files],
            'status': ['corrupt'] * len(corrupt_files),
            'file_path': [str(p) for _, _, p in corrupt_files]
        })
        
        report = pd.concat([report_df, corrupt_df], ignore_index=True)
        report.to_csv('amsr2_verification_report.csv', index=False)
        logger.info(f"📄 Detailed report saved to: amsr2_verification_report.csv")
    
    return completeness


if __name__ == "__main__":
    completeness = verify_data()
    sys.exit(0 if completeness > 80 else 1)