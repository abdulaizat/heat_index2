import datetime
import tempfile
import unittest
from pathlib import Path

import h5py

from audit_gpm_imerg_parallel import audit_slot, default_date_range, infer_archive_year


class AuditGpmImergParallelTests(unittest.TestCase):
    def test_infer_archive_year_from_base_dir_name(self) -> None:
        self.assertEqual(2024, infer_archive_year("/mnt/AizatDrive/gpm_imerg_precipitation_final_run/2024"))

    def test_default_date_range_uses_archive_year(self) -> None:
        self.assertEqual(
            ("2024-01-01", "2024-12-31"),
            default_date_range("/mnt/AizatDrive/gpm_imerg_precipitation_final_run/2024"),
        )

    def test_audit_slot_finds_file_under_base_year_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            base_dir = Path(tempdir) / "2024"
            target_time = datetime.datetime(2024, 1, 1, 0, 0)
            target_dir = base_dir / "2024" / "01" / "01"
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / "3B-HHR.MS.MRG.3IMERG.20240101-S000000-E002959.0000.V07B.HDF5"

            with h5py.File(file_path, "w") as handle:
                grid = handle.create_group("Grid")
                grid.create_dataset("precipitation", data=[[1.0] * 128 for _ in range(128)])

            result = audit_slot((target_time, str(base_dir), "Grid/precipitation"))

            self.assertEqual(0, result["status_code"])
            self.assertEqual(str(file_path), result["file_path"])


if __name__ == "__main__":
    unittest.main()
