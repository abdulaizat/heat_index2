import os
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest import mock

import h5py

from download_gpm_imerg_parallel_finalRun import (
    IO_WORKER_CAP,
    ensure_disk_headroom,
    quarantine_invalid_file,
    resolve_worker_count,
    verify_existing_granule_file,
)


DiskUsage = namedtuple("usage", ["total", "used", "free"])


class GpmImergHardeningTests(unittest.TestCase):
    def test_resolve_worker_count_caps_to_io_limit(self) -> None:
        self.assertEqual(IO_WORKER_CAP, resolve_worker_count(IO_WORKER_CAP + 5))
        self.assertEqual(1, resolve_worker_count(1))

    def test_ensure_disk_headroom_rejects_nearly_full_filesystem(self) -> None:
        with mock.patch("download_gpm_imerg_parallel_finalRun.MIN_FREE_DISK_GIB", 100.0):
            with mock.patch("download_gpm_imerg_parallel_finalRun.MIN_FREE_DISK_PCT", 2.0):
                with mock.patch(
                    "download_gpm_imerg_parallel_finalRun.shutil.disk_usage",
                    return_value=DiskUsage(total=1000, used=990, free=10),
                ):
                    with self.assertRaises(RuntimeError):
                        ensure_disk_headroom("/tmp", "Startup")

    def test_ensure_disk_headroom_accepts_healthy_filesystem(self) -> None:
        gib = 1024 ** 3
        with mock.patch(
            "download_gpm_imerg_parallel_finalRun.shutil.disk_usage",
            return_value=DiskUsage(total=500 * gib, used=300 * gib, free=200 * gib),
        ):
            ensure_disk_headroom("/tmp", "Startup")

    def test_verify_existing_granule_file_accepts_valid_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "valid.HDF5"
            with h5py.File(path, "w") as handle:
                grid = handle.create_group("Grid")
                grid.create_dataset("precipitationCal", data=[[1.0, 2.0], [3.0, 4.0]])

            result = verify_existing_granule_file(str(path))

            self.assertTrue(result["valid"])
            self.assertEqual("Grid/precipitationCal", result["dataset_path"])
            self.assertIsNotNone(result["sha256"])

    def test_verify_existing_granule_file_rejects_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "valid.HDF5"
            with h5py.File(path, "w") as handle:
                grid = handle.create_group("Grid")
                grid.create_dataset("precipitationCal", data=[[1.0]])

            result = verify_existing_granule_file(str(path), expected_sha256="deadbeef")

            self.assertFalse(result["valid"])
            self.assertEqual("checksum_mismatch", result["reason"])

    def test_quarantine_invalid_file_moves_bad_artifact_aside(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "broken.HDF5"
            path.write_bytes(b"not-an-hdf5-file" * 128)

            quarantined = quarantine_invalid_file(str(path), "invalid_hdf5_signature")

            self.assertFalse(path.exists())
            self.assertIsNotNone(quarantined)
            self.assertTrue(Path(str(quarantined)).exists())
            self.assertIn(".corrupt.", os.path.basename(str(quarantined)))


if __name__ == "__main__":
    unittest.main()
