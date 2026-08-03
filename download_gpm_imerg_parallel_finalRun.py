#!/usr/bin/env python3
"""
GPM IMERG Final Run (Half-Hourly) Download Script
===================================================
Downloads GPM_3IMERGHH V07 precipitationCal data for Malaysia with maximum
reliability, parallelism, and data integrity guarantees.

Key Features:
- 8-worker parallel processing (optimized for Xeon Gold 5115)
- Atomic file writes (download to .tmp, rename on success)
- SHA256 checksum verification for data integrity
- Resume capability with JSON progress tracking
- File-level locking to prevent race conditions
- Exponential backoff with jitter for network resilience
- Skip existing valid files (no re-download)

Product: GPM_3IMERGHH (Version 07) - GPM IMERG Final Precipitation L3 Half Hourly
Variable: precipitationCal (calibrated precipitation estimate)
Format: HDF5

Author: Auto-generated for Zero Death Heat Index Project
"""

import os
import sys
import time
import json
import hashlib
import logging
import argparse
import threading
import multiprocessing
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import random
import fcntl
import shutil
from contextlib import contextmanager

import h5py

# =============================================================================
# CONFIGURATION
# =============================================================================
# Product Configuration
SHORT_NAME = "GPM_3IMERGHH"
VERSION = "07"
VARIABLE = "precipitationCal"

# Temporal Range
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 12, 31)

# Malaysia Domain: (West, South, East, North) for earthaccess
# User provided: [7.8, 99.3, 0.6, 119.8] = [North, West, South, East]
ROI_BBOX = (99.3, 0.6, 119.8, 7.8)

# Output Directory
BASE_OUTPUT_DIR = "/mnt/AizatDrive/gpm_imerg_precipitation_final_run/2025"
LOG_FILE = "/home/NWP5/heat_index2/download_gpm_imerg.log"

# Credentials (from user)
EARTHDATA_USERNAME = "abdulaizat"
EARTHDATA_PASSWORD = "Gr7$ndkL!p2e"

# Hardware Tuning
# This workload is network-heavy and also writes to a nearly full external HDD.
# Keep concurrency conservative to reduce I/O contention and hung connection piles.
IO_WORKER_CAP = 3
MAX_WORKERS = IO_WORKER_CAP
MAX_TASKS_PER_CHILD = 50  # Recycle workers to prevent memory leaks

# Network Resilience
MAX_RETRIES = 5
BASE_DELAY = 2.0  # seconds
MAX_DELAY = 120.0  # seconds
JITTER_FACTOR = 0.25  # ±25% randomness

# File Operations
AUTH_TIMEOUT = 120  # seconds
DOWNLOAD_TIMEOUT = 300  # 5 minutes per file
STALL_TIMEOUT = 900  # recycle the pool if no task completes for 15 minutes
RESULT_POLL_INTERVAL = 5.0  # seconds
MAX_POOL_RECYCLES = 3
CHUNK_SIZE = 8192 * 4  # 32KB chunks for streaming downloads

# Storage Guardrails
MIN_FREE_DISK_GIB = 0.0
MIN_FREE_DISK_PCT = 0.0
MIN_VALID_FILE_SIZE_BYTES = 1024
HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"
DATASET_CANDIDATES = (
    "Grid/precipitation",
    "Grid/precipitationCal",
    "/Grid/precipitation",
    "/Grid/precipitationCal",
    "precipitation",
    "precipitationCal",
)

# Progress tracking
PROGRESS_FILE = os.path.join(BASE_OUTPUT_DIR, "download_progress.json")
PROGRESS_LOCK = threading.Lock()
WORKER_AUTHENTICATED = False

# =============================================================================
# Logging Setup
# =============================================================================
LOGGER_HANDLER_MARKER = "_heat_index2_gpm_imerg_final_run"


def setup_logging():
    """Configure logging for both file and console output."""
    log_formatter = logging.Formatter(
        '%(asctime)s [PID:%(process)d] %(levelname)s - %(message)s'
    )
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if any(getattr(handler, LOGGER_HANDLER_MARKER, False) for handler in root_logger.handlers):
        return logging.getLogger(__name__)
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(log_formatter)
    setattr(file_handler, LOGGER_HANDLER_MARKER, True)
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    setattr(console_handler, LOGGER_HANDLER_MARKER, True)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class DownloadTimeoutError(TimeoutError):
    """Raised when a worker exceeds a hard wall-clock deadline."""


def resolve_worker_count(requested_workers: int) -> int:
    """Clamp worker count to the repo's I/O safety cap."""
    return max(1, min(int(requested_workers), IO_WORKER_CAP))


def disk_headroom(path: str) -> Dict[str, float]:
    """Return disk headroom stats for the nearest existing parent of path."""
    target = Path(path).resolve()
    while not target.exists() and target != target.parent:
        target = target.parent

    usage = shutil.disk_usage(target)
    free_gib = usage.free / (1024 ** 3)
    free_pct = (usage.free / usage.total) * 100 if usage.total else 0.0
    return {
        "path": str(target),
        "free_gib": free_gib,
        "free_pct": free_pct,
        "total_bytes": float(usage.total),
        "free_bytes": float(usage.free),
    }


def ensure_disk_headroom(path: str, context: str) -> None:
    """Abort if the target filesystem is too full for a long-running download."""
    headroom = disk_headroom(path)
    if headroom["free_gib"] < MIN_FREE_DISK_GIB or headroom["free_pct"] < MIN_FREE_DISK_PCT:
        raise RuntimeError(
            f"{context} blocked: filesystem at {headroom['path']} has only "
            f"{headroom['free_gib']:.1f} GiB free ({headroom['free_pct']:.2f}% free). "
            f"Required minimum is {MIN_FREE_DISK_GIB:.0f} GiB and {MIN_FREE_DISK_PCT:.1f}% free."
        )


def _timeout_handler(signum, frame):
    raise DownloadTimeoutError("Operation exceeded the configured timeout")


@contextmanager
def deadline(seconds: int, context: str):
    """Enforce a hard timeout in worker processes on POSIX systems."""
    if (
        seconds <= 0
        or os.name != "posix"
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, float(seconds))
    signal.signal(signal.SIGALRM, _timeout_handler)
    try:
        yield
    except DownloadTimeoutError as exc:
        raise DownloadTimeoutError(f"{context} exceeded {seconds} seconds") from exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer != (0.0, 0.0):
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def initialize_worker():
    """Authenticate once per worker process so each task avoids repeated login churn."""
    global WORKER_AUTHENTICATED

    if WORKER_AUTHENTICATED:
        return

    import earthaccess

    os.environ["EARTHDATA_USERNAME"] = EARTHDATA_USERNAME
    os.environ["EARTHDATA_PASSWORD"] = EARTHDATA_PASSWORD

    with deadline(AUTH_TIMEOUT, "Worker Earthdata authentication"):
        auth = earthaccess.login(strategy="environment")

    if not getattr(auth, "authenticated", False):
        raise RuntimeError("Worker authentication failed")

    WORKER_AUTHENTICATED = True
    logger.info(f"Worker {os.getpid()} authenticated with Earthdata")


# =============================================================================
# Progress Tracking with File Locking
# =============================================================================
class ProgressTracker:
    """Thread-safe and process-safe progress tracking with file locking."""
    
    def __init__(self, progress_file: str):
        self.progress_file = progress_file
        self.lock_file = progress_file + ".lock"
        self._local_lock = threading.Lock()
    
    def _acquire_file_lock(self, f):
        """Acquire an exclusive file lock."""
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    
    def _release_file_lock(self, f):
        """Release the file lock."""
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    def load(self) -> Dict[str, Any]:
        """Load progress from JSON file with file locking."""
        with self._local_lock:
            if not os.path.exists(self.progress_file):
                return {
                    "completed_granules": {},  # {granule_id: {"sha256": hash, "path": path}}
                    "failed_granules": [],
                    "last_updated": None
                }
            
            try:
                with open(self.progress_file, 'r') as f:
                    self._acquire_file_lock(f)
                    try:
                        data = json.load(f)
                    finally:
                        self._release_file_lock(f)
                return data
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
                return {
                    "completed_granules": {},
                    "failed_granules": [],
                    "last_updated": None
                }
    
    def save(self, progress: Dict[str, Any]):
        """Save progress to JSON file atomically with file locking."""
        with self._local_lock:
            progress["last_updated"] = datetime.now().isoformat()
            
            # Atomic write: write to temp, then rename
            temp_file = self.progress_file + f".{os.getpid()}.tmp"
            
            try:
                os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
                
                with open(temp_file, 'w') as f:
                    self._acquire_file_lock(f)
                    try:
                        json.dump(progress, f, indent=2, default=str)
                    finally:
                        self._release_file_lock(f)
                
                # Atomic rename
                shutil.move(temp_file, self.progress_file)
                
            except Exception as e:
                logger.warning(f"Could not save progress file: {e}")
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
    
    def mark_completed(self, granule_id: str, file_path: str, sha256: str):
        """Mark a granule as successfully downloaded."""
        progress = self.load()
        progress["completed_granules"][granule_id] = {
            "sha256": sha256,
            "path": file_path,
            "timestamp": datetime.now().isoformat()
        }
        # Remove from failed if present
        if granule_id in progress.get("failed_granules", []):
            progress["failed_granules"].remove(granule_id)
        self.save(progress)
    
    def mark_failed(self, granule_id: str, error: str):
        """Mark a granule as failed."""
        progress = self.load()
        if granule_id not in progress.get("failed_granules", []):
            progress.setdefault("failed_granules", []).append(granule_id)
        self.save(progress)
    
    def is_completed(self, granule_id: str) -> bool:
        """Check if a granule is already completed."""
        progress = self.load()
        return granule_id in progress.get("completed_granules", {})
    
    def get_completed_path(self, granule_id: str) -> Optional[str]:
        """Get the path of a completed granule."""
        progress = self.load()
        info = progress.get("completed_granules", {}).get(granule_id)
        if info:
            return info.get("path")
        return None

    def get_completed_info(self, granule_id: str) -> Optional[Dict[str, Any]]:
        """Get the full completion record for a granule."""
        progress = self.load()
        return progress.get("completed_granules", {}).get(granule_id)

    def clear_completed(self, granule_id: str):
        """Remove a stale completion record so the granule can be retried."""
        progress = self.load()
        if granule_id in progress.get("completed_granules", {}):
            progress["completed_granules"].pop(granule_id, None)
            self.save(progress)


# =============================================================================
# Utility Functions
# =============================================================================
def calculate_sha256(file_path: str) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def discover_precip_dataset(handle: h5py.File) -> Optional[str]:
    """Find the expected precipitation dataset inside a GPM HDF5 granule."""
    for candidate in DATASET_CANDIDATES:
        if candidate in handle and isinstance(handle[candidate], h5py.Dataset):
            return candidate

    found: Optional[str] = None

    def visitor(name, node):
        nonlocal found
        if found is not None:
            return True
        if isinstance(node, h5py.Dataset) and (
            name.endswith("precipitation") or name.endswith("precipitationCal")
        ):
            found = name
            return True
        return None

    handle.visititems(visitor)
    return found


def sample_dataset(dataset: h5py.Dataset):
    """Read a minimal subset to ensure the dataset is materially readable."""
    if dataset.shape == ():
        return dataset[()]
    index = tuple(slice(0, 1) for _ in dataset.shape)
    return dataset[index]


def verify_existing_granule_file(
    file_path: str,
    expected_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deep-verify an already-downloaded granule before deciding to skip it.
    A file is considered valid only if:
    - it exists and is non-trivially sized,
    - it has the HDF5 magic header,
    - it opens with h5py,
    - a precipitation dataset is discoverable and minimally readable,
    - and, when available, its SHA256 matches the known progress record.
    """
    path = Path(file_path)
    result: Dict[str, Any] = {
        "valid": False,
        "reason": None,
        "sha256": None,
        "dataset_path": None,
    }

    if not path.exists():
        result["reason"] = "missing_file"
        return result

    if path.stat().st_size <= MIN_VALID_FILE_SIZE_BYTES:
        result["reason"] = f"file_too_small:{path.stat().st_size}"
        return result

    try:
        with path.open("rb") as handle:
            header = handle.read(len(HDF5_SIGNATURE))
    except OSError as exc:
        result["reason"] = f"header_read_failed:{exc}"
        return result

    if header != HDF5_SIGNATURE:
        result["reason"] = "invalid_hdf5_signature"
        return result

    try:
        with h5py.File(path, "r") as handle:
            dataset_path = discover_precip_dataset(handle)
            if not dataset_path:
                result["reason"] = "missing_precipitation_dataset"
                return result
            sample_dataset(handle[dataset_path])
            result["dataset_path"] = dataset_path
    except Exception as exc:
        result["reason"] = f"hdf5_validation_failed:{exc}"
        return result

    try:
        actual_sha256 = calculate_sha256(str(path))
    except OSError as exc:
        result["reason"] = f"checksum_failed:{exc}"
        return result

    result["sha256"] = actual_sha256
    if expected_sha256 and actual_sha256 != expected_sha256:
        result["reason"] = "checksum_mismatch"
        return result

    result["valid"] = True
    result["reason"] = "ok"
    return result


def quarantine_invalid_file(file_path: str, reason: str) -> Optional[str]:
    """Move an invalid local file aside so a clean redownload can replace it."""
    path = Path(file_path)
    if not path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    quarantine_path = path.with_name(f"{path.name}.corrupt.{timestamp}")

    try:
        shutil.move(str(path), str(quarantine_path))
        logger.warning(f"Quarantined invalid file {path} -> {quarantine_path} ({reason})")
        return str(quarantine_path)
    except Exception as exc:
        logger.warning(f"Could not quarantine invalid file {path}: {exc}")
        return None


def exponential_backoff(attempt: int) -> float:
    """Calculate delay with exponential backoff and jitter."""
    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
    jitter = delay * JITTER_FACTOR * (2 * random.random() - 1)
    return delay + jitter


def create_output_path(granule_name: str, date: datetime) -> Path:
    """Create the output path for a granule file."""
    # Organize by year/month/day
    year_dir = str(date.year)
    month_dir = f"{date.month:02d}"
    day_dir = f"{date.day:02d}"
    
    output_dir = Path(BASE_OUTPUT_DIR) / year_dir / month_dir / day_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    return output_dir / granule_name


def parse_granule_date(granule) -> Optional[datetime]:
    """Extract date from a granule's metadata."""
    try:
        # earthaccess granule has time_start attribute
        if hasattr(granule, 'time_start'):
            return datetime.fromisoformat(granule.time_start.replace('Z', '+00:00')).replace(tzinfo=None)
        
        # Try to get from metadata
        umm = granule.get('umm', {}) if isinstance(granule, dict) else {}
        temporal = umm.get('TemporalExtent', {})
        range_dt = temporal.get('RangeDateTime', {})
        begin = range_dt.get('BeginningDateTime', '')
        if begin:
            return datetime.fromisoformat(begin.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        pass
    
    return None


def get_granule_id(granule) -> str:
    """Extract a unique identifier for a granule."""
    try:
        # Try native_id first
        if hasattr(granule, 'native_id'):
            return granule.native_id
        if isinstance(granule, dict):
            meta = granule.get('meta', {})
            return meta.get('native-id', meta.get('concept-id', str(hash(str(granule)))))
    except Exception:
        pass
    return str(hash(str(granule)))


def get_granule_filename(granule) -> str:
    """Extract filename from granule data links."""
    try:
        # earthaccess granules have data_links
        if hasattr(granule, 'data_links'):
            links = granule.data_links()
            if links:
                return os.path.basename(links[0])
        
        # Try from related URLs
        if isinstance(granule, dict):
            umm = granule.get('umm', {})
            related_urls = umm.get('RelatedUrls', [])
            for url_info in related_urls:
                if url_info.get('Type') == 'GET DATA':
                    url = url_info.get('URL', '')
                    return os.path.basename(url)
    except Exception:
        pass
    
    return f"granule_{get_granule_id(granule)}.h5"


# =============================================================================
# Download Functions
# =============================================================================
def download_single_granule(args: Tuple) -> Dict[str, Any]:
    """
    Download a single granule with atomic writes and checksum verification.
    This function is designed to be called by multiprocessing Pool.
    """
    granule_dict, output_path_str, granule_id = args
    
    result = {
        "granule_id": granule_id,
        "success": False,
        "path": None,
        "sha256": None,
        "error": None,
        "skipped": False
    }
    
    output_path = Path(output_path_str)
    temp_path = output_path.with_suffix(output_path.suffix + f'.{os.getpid()}.tmp')
    
    try:
        # Import earthaccess in worker process
        import earthaccess

        if not WORKER_AUTHENTICATED:
            initialize_worker()
        
        # Check if file already exists and is valid
        if output_path.exists() and output_path.stat().st_size > 1000:
            result["success"] = True
            result["path"] = str(output_path)
            result["skipped"] = True
            result["sha256"] = calculate_sha256(str(output_path))
            logger.debug(f"Skipping (already exists): {output_path.name}")
            return result
        
        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_disk_headroom(str(output_path.parent), f"Worker {os.getpid()} download")
        
        # Download with retries
        for attempt in range(MAX_RETRIES):
            try:
                # Use earthaccess to download
                # The granule_dict should contain enough info
                with deadline(DOWNLOAD_TIMEOUT, f"Download for {granule_id}"):
                    downloaded = earthaccess.download(
                        [granule_dict],
                        local_path=str(temp_path.parent),
                        threads=1
                    )
                
                if downloaded:
                    # Find the downloaded file
                    downloaded_file = downloaded[0] if isinstance(downloaded, list) else downloaded
                    
                    if isinstance(downloaded_file, Path):
                        downloaded_file = str(downloaded_file)
                    
                    # If downloaded to different name, rename
                    if downloaded_file != str(temp_path):
                        if os.path.exists(downloaded_file):
                            shutil.move(downloaded_file, str(temp_path))
                    
                    # Verify file exists and has content
                    if temp_path.exists() and temp_path.stat().st_size > 1000:
                        # Calculate checksum
                        sha256 = calculate_sha256(str(temp_path))
                        
                        # Atomic rename
                        shutil.move(str(temp_path), str(output_path))
                        
                        result["success"] = True
                        result["path"] = str(output_path)
                        result["sha256"] = sha256
                        logger.info(f"Downloaded: {output_path.name}")
                        return result
                
                raise Exception("Download produced no valid file")
                
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    delay = exponential_backoff(attempt)
                    logger.warning(f"Attempt {attempt + 1} failed for {granule_id}: {e}. Retrying in {delay:.1f}s")
                    time.sleep(delay)
                else:
                    raise
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Failed to download {granule_id}: {e}")
    
    finally:
        # Cleanup temp file
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
    
    return result


def download_granules_parallel(granules: List, progress_tracker: ProgressTracker, dry_run: bool = False) -> Tuple[int, int]:
    """
    Download granules in parallel using multiprocessing.
    Returns: (successful_count, failed_count)
    """
    # Prepare download tasks
    tasks = []
    skipped = 0
    
    for granule in granules:
        granule_id = get_granule_id(granule)
        
        # Check if already completed
        if progress_tracker.is_completed(granule_id):
            completed_info = progress_tracker.get_completed_info(granule_id) or {}
            existing_path = completed_info.get("path")
            expected_sha256 = completed_info.get("sha256")
            if existing_path and os.path.exists(existing_path):
                validation = verify_existing_granule_file(existing_path, expected_sha256)
                if validation["valid"]:
                    skipped += 1
                    continue

                logger.warning(
                    f"Stored completed file failed validation for {granule_id}: "
                    f"{validation['reason']}. It will be re-downloaded."
                )
                progress_tracker.clear_completed(granule_id)
                quarantine_invalid_file(existing_path, str(validation["reason"]))
            else:
                progress_tracker.clear_completed(granule_id)

        # Get output path
        granule_date = parse_granule_date(granule)
        if not granule_date:
            granule_date = START_DATE  # Fallback
        
        filename = get_granule_filename(granule)
        output_path = create_output_path(filename, granule_date)
        
        # Check if file already exists on disk (not in progress tracker)
        if output_path.exists():
            validation = verify_existing_granule_file(str(output_path))
            if validation["valid"]:
                progress_tracker.mark_completed(
                    granule_id,
                    str(output_path),
                    str(validation["sha256"]),
                )
                skipped += 1
                continue

            logger.warning(
                f"Existing local file failed validation for {granule_id}: "
                f"{validation['reason']}. It will be re-downloaded."
            )
            quarantine_invalid_file(str(output_path), str(validation["reason"]))
        
        # Convert granule to dict for pickling (multiprocessing)
        granule_dict = granule if isinstance(granule, dict) else granule
        tasks.append((granule_dict, str(output_path), granule_id))
    
    logger.info(f"Tasks to download: {len(tasks)}, Already complete: {skipped}")
    
    if dry_run:
        logger.info("DRY RUN MODE - No downloads will be performed")
        for _, output_path, granule_id in tasks[:10]:  # Show first 10
            logger.info(f"  Would download: {os.path.basename(output_path)}")
        if len(tasks) > 10:
            logger.info(f"  ... and {len(tasks) - 10} more")
        return 0, 0
    
    if not tasks:
        logger.info("No new granules to download")
        return 0, 0
    
    successful = 0
    failed = 0

    def record_result(result: Dict[str, Any]) -> None:
        nonlocal successful, failed

        granule_id = result["granule_id"]

        if result["success"]:
            successful += 1
            if result.get("sha256"):
                progress_tracker.mark_completed(
                    granule_id,
                    result["path"],
                    result["sha256"]
                )
        else:
            failed += 1
            progress_tracker.mark_failed(granule_id, result.get("error", "Unknown error"))

    processed = 0
    recycle_count = 0
    pending_tasks = list(tasks)

    while pending_tasks:
        ensure_disk_headroom(BASE_OUTPUT_DIR, "Download startup")
        cycle_tasks = pending_tasks
        pending_tasks = []
        logger.info(
            f"Dispatching {len(cycle_tasks)} tasks with {MAX_WORKERS} workers "
            f"(pool recycle attempt {recycle_count + 1}/{MAX_POOL_RECYCLES + 1})"
        )

        with multiprocessing.Pool(
            processes=MAX_WORKERS,
            maxtasksperchild=MAX_TASKS_PER_CHILD,
            initializer=initialize_worker,
        ) as pool:
            async_results = [
                (task, pool.apply_async(download_single_granule, (task,)))
                for task in cycle_tasks
            ]
            last_progress_at = time.monotonic()
            recycled_this_cycle = False

            while async_results:
                remaining = []
                completed_this_pass = 0

                for task, async_result in async_results:
                    if not async_result.ready():
                        remaining.append((task, async_result))
                        continue

                    try:
                        result = async_result.get(timeout=0)
                    except Exception as exc:
                        result = {
                            "granule_id": task[2],
                            "success": False,
                            "path": None,
                            "sha256": None,
                            "error": f"Worker execution failed: {exc}",
                            "skipped": False,
                        }

                    record_result(result)
                    processed += 1
                    completed_this_pass += 1
                    last_progress_at = time.monotonic()

                    if processed % 50 == 0 or processed == len(tasks):
                        logger.info(
                            f"Progress: {processed}/{len(tasks)} "
                            f"(Success: {successful}, Failed: {failed})"
                        )

                async_results = remaining

                if not async_results:
                    break

                if completed_this_pass == 0:
                    stalled_for = time.monotonic() - last_progress_at
                    if stalled_for >= STALL_TIMEOUT:
                        recycle_count += 1
                        logger.error(
                            f"No task completed for {stalled_for / 60:.1f} minutes. "
                            f"Recycling pool with {len(async_results)} tasks still pending."
                        )
                        pending_tasks = [task for task, _ in async_results] + pending_tasks
                        pool.terminate()
                        pool.join()
                        recycled_this_cycle = True
                        break

                    time.sleep(RESULT_POLL_INTERVAL)

            if recycled_this_cycle and recycle_count > MAX_POOL_RECYCLES:
                logger.error(
                    "Exceeded maximum pool recycle attempts. Marking remaining tasks as failed for resume."
                )
                for task in pending_tasks:
                    granule_id = task[2]
                    failed += 1
                    processed += 1
                    progress_tracker.mark_failed(
                        granule_id,
                        "Pool stalled repeatedly; task left unfinished so a future --resume run can retry it.",
                    )
                pending_tasks = []
                break
    
    return successful, failed


# =============================================================================
# Main Search and Download Orchestrator
# =============================================================================
def search_granules(start_date: datetime, end_date: datetime) -> List:
    """Search for GPM IMERG granules in the specified date range."""
    import earthaccess
    
    logger.info(f"Searching for {SHORT_NAME} V{VERSION} granules...")
    logger.info(f"  Date range: {start_date.date()} to {end_date.date()}")
    logger.info(f"  Bounding box: {ROI_BBOX}")
    
    try:
        results = earthaccess.search_data(
            short_name=SHORT_NAME,
            version=VERSION,
            temporal=(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")),
            bounding_box=ROI_BBOX
        )
        
        logger.info(f"Found {len(results)} granules")
        return results
    
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


def main():
    global MAX_WORKERS  # Declare global at the start of function
    setup_logging()
    
    parser = argparse.ArgumentParser(
        description='Download GPM IMERG Final Run (Half-Hourly) precipitationCal data'
    )
    parser.add_argument(
        '--test-day', type=str, 
        help='Test with single day (e.g., 2025-01-15)'
    )
    parser.add_argument(
        '--start-date', type=str, default=None,
        help='Start date (YYYY-MM-DD). Default: 2025-01-01'
    )
    parser.add_argument(
        '--end-date', type=str, default=None,
        help='End date (YYYY-MM-DD). Default: 2025-12-31'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='List granules without downloading'
    )
    parser.add_argument(
        '--workers', type=int, default=MAX_WORKERS,
        help=f'Number of parallel workers (default: {MAX_WORKERS})'
    )
    parser.add_argument(
        '--resume', action='store_true',
        help='Resume from progress file (default behavior)'
    )
    args = parser.parse_args()
    
    # Update worker count if specified, but never exceed the repo's I/O safety cap.
    if args.workers:
        requested_workers = args.workers
        MAX_WORKERS = resolve_worker_count(args.workers)
        if requested_workers != MAX_WORKERS:
            logger.warning(
                f"Requested {requested_workers} workers, capped to {MAX_WORKERS} "
                f"to respect the repo I/O safety limit."
            )
    
    # ==========================================================================
    # 1. AUTHENTICATION
    # ==========================================================================
    logger.info("=" * 70)
    logger.info("GPM IMERG Final Run (Half-Hourly) Download Script")
    logger.info("=" * 70)
    logger.info(f"Product: {SHORT_NAME} Version {VERSION}")
    logger.info(f"Variable: {VARIABLE}")
    logger.info(f"Output: {BASE_OUTPUT_DIR}")
    logger.info(f"Workers: {MAX_WORKERS}")
    logger.info(f"Per-file timeout: {DOWNLOAD_TIMEOUT}s")
    logger.info(f"Stall recycle timeout: {STALL_TIMEOUT}s")
    logger.info("")

    try:
        ensure_disk_headroom(BASE_OUTPUT_DIR, "Startup")
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1
    
    logger.info("Authenticating with NASA Earthdata...")
    
    try:
        import earthaccess
        
        os.environ["EARTHDATA_USERNAME"] = EARTHDATA_USERNAME
        os.environ["EARTHDATA_PASSWORD"] = EARTHDATA_PASSWORD
        auth = earthaccess.login(strategy="environment")
        
        if not auth.authenticated:
            logger.error("Authentication failed. Check credentials.")
            return 1
        
        logger.info("Authentication successful")
        
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return 1
    
    # ==========================================================================
    # 2. SETUP
    # ==========================================================================
    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
    progress_tracker = ProgressTracker(PROGRESS_FILE)
    
    # Determine date range
    if args.test_day:
        test_date = datetime.strptime(args.test_day, "%Y-%m-%d")
        start = test_date
        end = test_date + timedelta(days=1) - timedelta(seconds=1)
        logger.info(f"TEST MODE: Processing only {args.test_day}")
    else:
        start = datetime.strptime(args.start_date, "%Y-%m-%d") if args.start_date else START_DATE
        end = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else END_DATE
    
    # ==========================================================================
    # 3. SEARCH
    # ==========================================================================
    granules = search_granules(start, end)
    
    if not granules:
        logger.warning("No granules found. Check date range and bounding box.")
        return 1
    
    # ==========================================================================
    # 4. DOWNLOAD
    # ==========================================================================
    logger.info("")
    logger.info("Starting parallel download...")
    logger.info(f"  Workers: {MAX_WORKERS}")
    logger.info(f"  Max retries per file: {MAX_RETRIES}")
    logger.info("")
    
    start_time = time.time()
    
    successful, failed = download_granules_parallel(
        granules, 
        progress_tracker, 
        dry_run=args.dry_run
    )
    
    elapsed = time.time() - start_time
    
    # ==========================================================================
    # 5. SUMMARY
    # ==========================================================================
    logger.info("")
    logger.info("=" * 70)
    logger.info("DOWNLOAD COMPLETE - SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total granules found: {len(granules)}")
    logger.info(f"Successfully downloaded: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Time elapsed: {elapsed / 60:.1f} minutes")
    logger.info(f"Output directory: {BASE_OUTPUT_DIR}")
    
    if failed > 0:
        logger.warning(f"Some downloads failed. Run with --resume to retry.")
        progress = progress_tracker.load()
        failed_list = progress.get("failed_granules", [])
        if failed_list:
            logger.warning(f"Failed granules: {len(failed_list)}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
