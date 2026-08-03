import json
import tempfile
import unittest
from pathlib import Path

from process_drivers import artifact_paths, process_enso, process_mjo, write_driver_manifest


class DriverStatusTests(unittest.TestCase):
    def test_process_enso_writes_complete_output_for_full_2025_months(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_file = root / "enso_oni.txt"
            output_dir = root / "processed"

            rows = ["SEAS YR TOTAL ANOM", "NDJ 2024 25.34 -0.80"]
            seasons = [
                ("DJF", -0.45),
                ("JFM", -0.40),
                ("FMA", -0.35),
                ("MAM", -0.30),
                ("AMJ", -0.20),
                ("MJJ", -0.10),
                ("JJA", 0.00),
                ("JAS", 0.10),
                ("ASO", 0.15),
                ("SON", 0.20),
                ("OND", 0.25),
                ("NDJ", 0.30),
            ]
            rows.extend(f"{season} 2025 26.00 {anom}" for season, anom in seasons)
            raw_file.write_text("\n".join(rows) + "\n", encoding="utf-8")

            record = process_enso(input_file=str(raw_file), output_dir=str(output_dir))
            paths = artifact_paths("enso", str(output_dir))

            self.assertEqual("complete", record["status"])
            self.assertTrue(paths["complete_csv"].exists())
            self.assertFalse(paths["partial_csv"].exists())

    def test_process_mjo_missing_year_writes_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_file = root / "mjo_rmm.txt"
            output_dir = root / "processed"

            raw_file.write_text(
                "\n".join(
                    [
                        "header one",
                        "header two",
                        "2024 12 30 0.1 0.2 1 0.22 source",
                        "2024 12 31 0.2 0.3 2 0.36 source",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            record = process_mjo(input_file=str(raw_file), output_dir=str(output_dir))
            paths = artifact_paths("mjo", str(output_dir))

            self.assertEqual("missing", record["status"])
            self.assertFalse(paths["complete_csv"].exists())
            self.assertFalse(paths["partial_csv"].exists())
            self.assertTrue(paths["metadata_json"].exists())

    def test_write_driver_manifest_summarizes_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            records = [
                {"name": "ENSO", "status": "complete"},
                {"name": "IOD", "status": "partial"},
                {"name": "MJO", "status": "missing"},
            ]

            manifest = write_driver_manifest(records, str(output_dir))
            payload = json.loads(manifest.read_text(encoding="utf-8"))

            self.assertEqual(["ENSO"], payload["complete"])
            self.assertEqual(["IOD"], payload["partial"])
            self.assertEqual(["MJO"], payload["missing_or_error"])


if __name__ == "__main__":
    unittest.main()
