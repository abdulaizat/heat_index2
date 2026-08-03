#!/usr/bin/env python3
"""
AMSR-2 Microwave Data Downloader for G-Portal (JAXA)
Downloads Level 3 Daily products (10km resolution) for 2020-2024
Target Region: Malaysia (Domain: 7.8°N, 99.3°E, 0.6°N, 119.8°E)

Refactored for Robustness:
- Thread-safe session management
- Exponential backoff retries
- Atomic file writes
- Pre-flight network checks
"""

import os
import sys
import time
import logging
import threading
import socket
import paramiko
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Optional
import argparse

# Import configuration
from amsr2_config import (
    FREQUENCIES, BASE_PATH, RESOLUTION, LOCAL_BASE_DIR, MAX_WORKERS,
    GPORTAL_HOST, GPORTAL_PORT, GPORTAL_USER, GPORTAL_PASS,
    display_domain_info
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('amsr2_download.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# THREAD-LOCAL SESSION MANAGEMENT
# ------------------------------------------------------------------------------
_thread_local = threading.local()

def get_session() -> paramiko.SFTPClient:
    """
    Retrieves the SFTP client dedicated to the current thread.
    If no client exists or the connection is dead, creates a new one.
    """
    # 1. Check if a session exists in this thread's local storage
    if hasattr(_thread_local, 'sftp') and _thread_local.sftp:
        try:
            # Lightweight verification of the transport
            if _thread_local.transport.is_active():
                return _thread_local.sftp
        except Exception:
            logger.warning("Detected stale SFTP session. Reconnecting...")
            close_session()

    # 2. Establish a new session if needed
    try:
        # Create the Transport (The encrypted tunnel)
        # Ensure we use the configured port (likely 2051)
        transport = paramiko.Transport((GPORTAL_HOST, GPORTAL_PORT))
        
        # Enable KeepAlive to prevent firewall timeouts during large downloads
        transport.set_keepalive(60)
        
        # Authenticate
        transport.connect(username=GPORTAL_USER, password=GPORTAL_PASS)
        
        # Create the SFTP Client (The file transfer channel)
        sftp = paramiko.SFTPClient.from_transport(transport)
        
        # Store in thread-local storage
        _thread_local.transport = transport
        _thread_local.sftp = sftp
        
        logger.info(f"Established new SFTP session on {GPORTAL_HOST}:{GPORTAL_PORT}")
        return sftp

    except paramiko.AuthenticationException:
        logger.critical("Authentication Failed! Stopping immediately to prevent account lockout.")
        raise
    except Exception as e:
        logger.error(f"Session establishment failed: {e}")
        raise

def close_session():
    """Safely closes the current thread's SFTP session."""
    if hasattr(_thread_local, 'sftp') and _thread_local.sftp:
        try:
            _thread_local.sftp.close()
        except:
            pass
        _thread_local.sftp = None
        
    if hasattr(_thread_local, 'transport') and _thread_local.transport:
        try:
            _thread_local.transport.close()
        except:
            pass
        _thread_local.transport = None

# ------------------------------------------------------------------------------
# RESILIENCE DECORATORS
# ------------------------------------------------------------------------------
def robust_retry(max_retries=5, delay=2, backoff=2):
    """
    Decorator that retries a function upon network failures.
    Implements exponential backoff.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (socket.error, paramiko.SSHException, EOFError, OSError) as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(f"Permanent failure in {func.__name__} after {retries} attempts: {e}")
                        raise e
                    
                    logger.warning(f"Transient error in {func.__name__}: {e}. "
                                   f"Retrying in {current_delay}s... (Attempt {retries}/{max_retries})")
                    
                    # If the error was network related, force a session reset
                    close_session()
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper
    return decorator

# ------------------------------------------------------------------------------
# CORE LOGIC
# ------------------------------------------------------------------------------

def create_remote_path(date: datetime, freq: str) -> str:
    """Create the remote path for a specific date and frequency."""
    year = date.year
    month = date.month
    day = date.day
    # Format: /AMSR2/L3/L3TB/06GHz/0.1deg/2020/01/20200101/
    path = f"{BASE_PATH}/{freq}/{RESOLUTION}/{year:04d}/{month:02d}/{year:04d}{month:02d}{day:02d}/"
    return path


def create_local_path(date: datetime, freq: str) -> Path:
    """Create the local path for a specific date and frequency."""
    year = date.year
    month = date.month
    day = date.day
    
    local_path = Path(LOCAL_BASE_DIR) / freq / f"{year:04d}" / f"{month:02d}" / f"{year:04d}{month:02d}{day:02d}"
    local_path.mkdir(parents=True, exist_ok=True)
    return local_path


@robust_retry(max_retries=5)
def list_files_sftp(sftp: paramiko.SFTPClient, remote_path: str) -> List[str]:
    """List files in a remote directory with retry logic."""
    try:
        files = sftp.listdir(remote_path)
        return files
    except IOError:
        # Often occurs if directory doesn't exist
        logger.debug(f"Could not list {remote_path} (likely no data)")
        return []


@robust_retry(max_retries=5)
def download_file(sftp: paramiko.SFTPClient, remote_path: str, local_path: Path) -> bool:
    """
    Download a single file from SFTP to local path using atomic writes.
    Writes to .part file first, then renames.
    """
    if local_path.exists():
        # Skip if already exists
        return True

    temp_path = local_path.with_suffix(local_path.suffix + '.part')
    
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check remote file attributes to ensure connection is alive
        sftp.stat(remote_path)
        
        logger.info(f"Downloading: {Path(remote_path).name}")
        sftp.get(remote_path, str(temp_path))
        
        # Atomic rename
        temp_path.rename(local_path)
        logger.info(f"Saved: {local_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to download {remote_path}: {e}")
        # Clean up partial file
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        raise e  # trigger retry


def download_date_frequency(date: datetime, freq: str) -> Tuple[datetime, str, int]:
    """
    Download all files for a specific date and frequency.
    Acquires its own thread-local session.
    """
    try:
        sftp = get_session()
        
        remote_path = create_remote_path(date, freq)
        local_base = create_local_path(date, freq)
        
        # List files in remote directory
        files = list_files_sftp(sftp, remote_path)
        if not files:
            return date, freq, 0
        
        downloaded = 0
        for filename in files:
            if filename.endswith('.h5') or filename.endswith('.nc'):
                remote_file = f"{remote_path}/{filename}"
                local_file = local_base / filename
                try:
                    if download_file(sftp, remote_file, local_file):
                        downloaded += 1
                except Exception:
                     # Logged in download_file, continue to next file
                     pass
        
        if downloaded > 0:
            logger.info(f"Completed {date.strftime('%Y-%m-%d')} {freq}: {downloaded} files")
        return date, freq, downloaded

    except Exception as e:
        logger.error(f"Worker failure for {date.strftime('%Y-%m-%d')} {freq}: {e}")
        close_session() # Force reset
        return date, freq, 0


def get_date_range(start_year: int, end_year: int) -> List[datetime]:
    """Generate all dates from start_year to end_year."""
    dates = []
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)
    
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)
    
    return dates


def check_network_path():
    """
    Validates that the host and port are reachable BEFORE starting threads.
    """
    logger.info(f"Running Pre-flight check: TCP Connect to {GPORTAL_HOST}:{GPORTAL_PORT}...")
    try:
        sock = socket.create_connection((GPORTAL_HOST, GPORTAL_PORT), timeout=10)
        sock.close()
        logger.info("Pre-flight Successful: Port is reachable.")
    except socket.timeout:
        logger.critical(f"Pre-flight FAILED: Connection Timed Out to {GPORTAL_HOST}:{GPORTAL_PORT}")
        logger.critical("DIAGNOSIS: Your firewall is likely blocking outbound traffic on this port.")
        sys.exit(110)
    except ConnectionRefusedError:
        logger.critical(f"Pre-flight FAILED: Connection Refused by {GPORTAL_HOST}.")
        sys.exit(111)
    except Exception as e:
        logger.critical(f"Pre-flight FAILED: {e}")
        sys.exit(1)


def main(start_year: int = 2020, end_year: int = 2024, frequencies: List[str] = None):
    """Main download function."""
    display_domain_info()
    
    # 1. Validation
    check_network_path()
    
    if frequencies is None:
        frequencies = FREQUENCIES
    
    # Create local base directory
    Path(LOCAL_BASE_DIR).mkdir(parents=True, exist_ok=True)
    
    # 2. Task Generation
    dates = get_date_range(start_year, end_year)
    logger.info(f"Generated {len(dates)} dates from {start_year} to {end_year}")
    
    tasks = []
    for date in dates:
        for freq in frequencies:
            tasks.append((date, freq))
    
    logger.info(f"Total tasks: {len(tasks)}")
    
    # 3. Execution
    total_downloaded = 0
    # Note: We do NOT create a global SFTP connection here. 
    # Each worker thread will create its own local connection via get_session()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        futures = {executor.submit(download_date_frequency, date, freq): (date, freq) for date, freq in tasks}
        
        for future in concurrent.futures.as_completed(futures):
            date, freq = futures[future]
            try:
                _, _, count = future.result()
                total_downloaded += count
            except Exception as e:
                logger.error(f"Unhandled Exception in main loop for {date} {freq}: {e}")
    
    logger.info(f"Download completed! Total files: {total_downloaded}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Robust AMSR-2 Microwave Data Ingest')
    parser.add_argument('--start-year', type=int, default=2020, help='Start year (default: 2020)')
    parser.add_argument('--end-year', type=int, default=2024, help='End year (default: 2024)')
    parser.add_argument('--frequencies', nargs='+', default=None, 
                       help='Frequencies to download (default: all defined in config)')
    parser.add_argument('--workers', type=int, default=MAX_WORKERS, 
                       help='Number of concurrent downloads (default: From config)')
    
    args = parser.parse_args()
    
    # Update global config if needed (MAX_WORKERS)
    # Since we import MAX_WORKERS, we can't easily change the imported primitive, 
    # but we can pass it to ThreadPoolExecutor or just rely on args.
    # To strictly follow the "thread local" pattern logic, we used constants.
    # But let's override the constant for this run if provided.
    if args.workers:
        MAX_WORKERS = args.workers
        
    main(args.start_year, args.end_year, args.frequencies)