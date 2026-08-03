import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from process_drivers import artifact_paths, parse_bsiso_pc_lines, process_bsiso, process_iod


class BsisoDriverTests(unittest.TestCase):
    def test_parse_bsiso_pc_lines_prefers_file_phase_and_amplitude(self) -> None:
        lines = [
            "2025 07 01 0.50 -0.25 8 0.5590\n",
            "2025 07 02 -0.10 0.20\n",
        ]

        df = parse_bsiso_pc_lines(lines)

        self.assertEqual(2, len(df))
        self.assertEqual(8, int(df.iloc[0]["Phase"]))
        self.assertAlmostEqual(0.5590, float(df.iloc[0]["Amplitude"]), places=4)
        self.assertGreater(float(df.iloc[1]["Amplitude"]), 0.0)

    def test_parse_bsiso_pc_lines_accepts_apcc_monitoring_layout(self) -> None:
        lines = [
            "2025 121 -0.401 -0.116 -1.475 -0.020 0.418 1.475\n",
            "2025 122 -0.444 -0.172 -1.536 0.099 0.476 1.539\n",
        ]

        df = parse_bsiso_pc_lines(lines)

        self.assertEqual(2, len(df))
        self.assertEqual("2025-05-01", df.iloc[0]["Date"].date().isoformat())
        self.assertAlmostEqual(0.418, float(df.iloc[0]["Amplitude"]), places=3)
        self.assertTrue(1 <= int(df.iloc[0]["Phase"]) <= 8)

    def test_process_bsiso_treats_full_apcc_season_as_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_file = root / "bsiso_index_norm_ly.data"
            output_dir = root / "processed"

            rows = [" YEAR  DAY  BSISO1-1 BSISO1-2 BSISO2-1 BSISO2-2 BSISO1  BSISO2"]
            start = datetime(2025, 5, 1)
            for offset in range(184):
                current = start + timedelta(days=offset)
                rows.append(
                    f"  2025 {current.timetuple().tm_yday:03d}  0.500  0.250  -0.300  0.200  0.559  0.361"
                )

            raw_file.write_text("\n".join(rows) + "\n", encoding="utf-8")

            record = process_bsiso(input_file=str(raw_file), output_dir=str(output_dir))
            paths = artifact_paths("bsiso", str(output_dir))

            self.assertEqual("complete", record["status"])
            self.assertTrue(paths["complete_csv"].exists())
            self.assertFalse(paths["partial_csv"].exists())
            self.assertTrue(paths["metadata_json"].exists())

            metadata = json.loads(paths["metadata_json"].read_text(encoding="utf-8"))
            self.assertEqual("complete", metadata["status"])
            self.assertEqual("2025-05-01", metadata["target_start_date"])
            self.assertEqual("2025-10-31", metadata["target_end_date"])
            self.assertEqual(str(paths["complete_csv"]), metadata["output_file"])

    def test_process_iod_writes_partial_until_last_contiguous_valid_month(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_file = root / "iod_dmi_season.txt"
            output_dir = root / "processed"

            raw_file.write_text(
                "\n".join(
                    [
                        "Data sources for indices:",
                        "Year Month WTIO SETIO DMI",
                        "2024 NDJ 0.10 0.00 0.10",
                        "2025 DJF 0.20 0.00 0.20",
                        "2025 JFM 0.30 0.00 0.30",
                        "2025 FMA 0.40 0.00 0.40",
                        "2025 MAM 0.50 0.00 0.50",
                        "2025 AMJ NaN NaN NaN",
                        "2025 MJJ NaN NaN NaN",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            record = process_iod(input_file=str(raw_file), output_dir=str(output_dir))
            paths = artifact_paths("iod", str(output_dir))

            self.assertEqual("partial", record["status"])
            self.assertEqual("2025-04-30", record["valid_through"])
            self.assertTrue(paths["partial_csv"].exists())
            self.assertFalse(paths["complete_csv"].exists())


if __name__ == "__main__":
    unittest.main()
