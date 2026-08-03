import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from process_drivers import TARGET_YEAR, artifact_paths

PROC_DIR = "/mnt/AizatDrive/global_drivers/processed"
DRIVERS = ("mjo", "enso", "iod", "bsiso")


def load_metadata(name: str) -> dict[str, object] | None:
    metadata_path = artifact_paths(name, PROC_DIR)["metadata_json"]
    if not metadata_path.exists():
        return None
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def expected_range_for(metadata: dict[str, object], allow_partial: bool) -> pd.DatetimeIndex | None:
    if metadata["status"] == "complete":
        return pd.date_range(metadata["target_start_date"], metadata["target_end_date"], freq="D")
    if allow_partial and metadata["status"] == "partial":
        valid_from = metadata.get("valid_from")
        valid_through = metadata.get("valid_through")
        if valid_from and valid_through:
            return pd.date_range(valid_from, valid_through, freq="D")
    return None


def validate_dataset(name: str, allow_partial: bool) -> bool:
    metadata = load_metadata(name)
    label = name.upper()
    print(f"\n{'=' * 20} Validating {label} {'=' * 20}")

    if metadata is None:
        print(f"❌ CRITICAL: Metadata file not found for {label}")
        return False

    status = str(metadata["status"])
    print(
        f"Status: {status} | coverage={metadata['coverage_pct']}% | "
        f"source_last_observation_date={metadata.get('source_last_observation_date')}"
    )
    for note in metadata.get("notes", []):
        print(f"  - {note}")

    if status != "complete" and not (allow_partial and status == "partial"):
        print("❌ Strict validation requires a complete dataset.")
        return False

    output_file = metadata.get("output_file")
    if not output_file:
        print("❌ CRITICAL: Metadata does not point to an output file.")
        return False

    path = Path(str(output_file))
    if not path.exists():
        print(f"❌ CRITICAL: Output file not found: {path}")
        return False

    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception as exc:
        print(f"❌ CRITICAL: Unreadable CSV: {exc}")
        return False

    expected_range = expected_range_for(metadata, allow_partial)
    if expected_range is None:
        print("❌ CRITICAL: No expected range could be derived from metadata.")
        return False

    missing_dates = expected_range.difference(df.index)
    if len(missing_dates) == 0:
        print(f"✅ Temporal Coverage: Complete ({len(expected_range)} days)")
    else:
        print(f"❌ Temporal Coverage: {len(missing_dates)} missing days")
        print(f"  - First missing: {missing_dates[0].date()}")
        print(f"  - Last missing: {missing_dates[-1].date()}")
        return False

    null_count = int(df.isnull().sum().sum())
    if null_count == 0:
        print("✅ Null Checks: Clean (0 NaNs)")
    else:
        print(f"❌ Null Checks: FAILED ({null_count} NaNs found)")
        print(df.isnull().sum())
        return False

    if label in {"MJO", "BSISO"}:
        invalid_phase = df[(df["Phase"] < 1) | (df["Phase"] > 8)]
        if not invalid_phase.empty:
            print(f"❌ Logic: Found {len(invalid_phase)} rows with invalid Phase")
            return False
        negative_amp = df[df["Amplitude"] < 0]
        if not negative_amp.empty:
            print(f"❌ Logic: Found {len(negative_amp)} rows with negative Amplitude")
            return False
    elif label == "ENSO":
        extreme = df[(df["ANOM"] > 5) | (df["ANOM"] < -5)]
        if not extreme.empty:
            print(f"⚠️ Logic: Found {len(extreme)} extreme ENSO anomalies")
    elif label == "IOD":
        extreme = df[(df["DMI"] > 4) | (df["DMI"] < -4)]
        if not extreme.empty:
            print(f"⚠️ Logic: Found {len(extreme)} extreme IOD values")

    print("✅ Physical/Logical Checks: Passed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate processed climate-driver outputs.")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Treat partial datasets as valid if their metadata and file contents are internally consistent.",
    )
    args = parser.parse_args()

    print("Starting Robust Data Validation...")
    results = {name.upper(): validate_dataset(name, args.allow_partial) for name in DRIVERS}

    print("\n" + "=" * 50)
    print("FINAL VALIDATION REPORT")
    print("=" * 50)
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED / INCOMPLETE"
        if not passed:
            all_passed = False
        print(f"{name:5}: {status}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
