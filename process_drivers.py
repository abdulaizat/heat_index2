import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Paths
RAW_DIR = "/mnt/AizatDrive/global_drivers/raw"
PROC_DIR = "/mnt/AizatDrive/global_drivers/processed"

# Keep all climate-driver outputs aligned to the same analysis year.
TARGET_YEAR = "2025"
START_DATE = f"{TARGET_YEAR}-01-01"
END_DATE = f"{TARGET_YEAR}-12-31"

MJO_RAW_FILE = os.path.join(RAW_DIR, "mjo_rmm.txt")
ENSO_RAW_FILE = os.path.join(RAW_DIR, "enso_oni.txt")
IOD_RAW_FILE = os.path.join(RAW_DIR, "iod_dmi_season.txt")
BSISO_RAW_FILE = os.path.join(RAW_DIR, "bsiso_index_norm_ly.data")

NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?")
SEASON_TO_MONTH = {
    "DJF": 1,
    "JFM": 2,
    "FMA": 3,
    "MAM": 4,
    "AMJ": 5,
    "MJJ": 6,
    "JJA": 7,
    "JAS": 8,
    "ASO": 9,
    "SON": 10,
    "OND": 11,
    "NDJ": 12,
}

DRIVER_CONFIG = {
    "mjo": {
        "display_name": "MJO",
        "cadence": "daily",
        "source_url": "https://www.bom.gov.au/clim_data/IDCKGEM000/rmm.74toRealtime.txt",
        "method": "published_rmm_components_plus_local_phase_amplitude",
        "source_path": MJO_RAW_FILE,
    },
    "enso": {
        "display_name": "ENSO",
        "cadence": "monthly",
        "source_url": "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
        "method": "published_monthly_oni_forward_filled_to_daily",
        "source_path": ENSO_RAW_FILE,
    },
    "iod": {
        "display_name": "IOD",
        "cadence": "monthly",
        "source_url": (
            "https://www.cpc.ncep.noaa.gov/products/international/ocean_monitoring/"
            "IODMI/mnth.ersstv5.clim19912020.dmi_season.txt"
        ),
        "method": "published_overlapping_3_month_dmi_forward_filled_to_daily",
        "source_path": IOD_RAW_FILE,
    },
    "bsiso": {
        "display_name": "BSISO",
        "cadence": "daily",
        "source_url": "https://download.apcc21.org/BSISO/BSISO.INDEX.NORM.LY.data",
        "method": "published_apcc_bsiso1_monitoring_components",
        "source_path": BSISO_RAW_FILE,
        "target_start_date": f"{TARGET_YEAR}-05-01",
        "target_end_date": f"{TARGET_YEAR}-10-31",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_proc_dir(output_dir: str = PROC_DIR) -> None:
    os.makedirs(output_dir, exist_ok=True)


def target_window(name: str) -> tuple[str, str]:
    config = DRIVER_CONFIG[name]
    return (
        str(config.get("target_start_date", START_DATE)),
        str(config.get("target_end_date", END_DATE)),
    )


def expected_index(start_date: str = START_DATE, end_date: str = END_DATE) -> pd.DatetimeIndex:
    return pd.date_range(start_date, end_date, freq="D")


def month_end(timestamp: pd.Timestamp) -> pd.Timestamp:
    return (timestamp + pd.offsets.MonthEnd(0)).normalize()


def artifact_paths(name: str, output_dir: str = PROC_DIR) -> dict[str, Path]:
    base = f"{name}_{TARGET_YEAR}"
    output_root = Path(output_dir)
    return {
        "complete_csv": output_root / f"{base}.csv",
        "partial_csv": output_root / f"{base}_partial.csv",
        "metadata_json": output_root / f"{base}.meta.json",
    }


def remove_path(path: Path) -> None:
    if path.exists():
        path.unlink()


def clear_driver_outputs(name: str, output_dir: str = PROC_DIR) -> None:
    paths = artifact_paths(name, output_dir)
    remove_path(paths["complete_csv"])
    remove_path(paths["partial_csv"])


def source_file_info(source_path: str) -> dict[str, str | None]:
    path = Path(source_path)
    if not path.exists():
        return {"exists": False, "fetched_at": None}
    return {
        "exists": True,
        "fetched_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
    }


def calculate_phase_value(pc1: float, pc2: float) -> int:
    angle = np.degrees(np.arctan2(pc2, pc1))
    if angle < 0:
        angle += 360
    return int(angle // 45) + 1 if angle < 360 else 8


def parse_bsiso_pc_lines(lines: list[str]) -> pd.DataFrame:
    rows = []

    for line in lines:
        stripped = line.strip()
        if not stripped or not stripped[0].isdigit():
            continue

        tokens = NUMBER_PATTERN.findall(stripped)
        if len(tokens) < 5:
            continue

        year = int(tokens[0])

        if len(tokens) >= 8:
            day_of_year = int(tokens[1])
            pc1 = float(tokens[2])
            pc2 = float(tokens[3])
            amplitude = float(tokens[6])

            try:
                timestamp = pd.to_datetime(f"{year}-{day_of_year:03d}", format="%Y-%j")
            except ValueError:
                continue

            phase = calculate_phase_value(pc1, pc2)
        else:
            month, day = (int(tokens[1]), int(tokens[2]))
            pc1, pc2 = float(tokens[3]), float(tokens[4])
            phase = calculate_phase_value(pc1, pc2)
            amplitude = float(np.sqrt(pc1 ** 2 + pc2 ** 2))

            if len(tokens) >= 7:
                phase_candidate = int(float(tokens[-2]))
                amplitude_candidate = float(tokens[-1])
                if 1 <= phase_candidate <= 8 and amplitude_candidate >= 0:
                    phase = phase_candidate
                    amplitude = amplitude_candidate

            try:
                timestamp = pd.Timestamp(year=year, month=month, day=day)
            except ValueError:
                continue

        rows.append(
            {
                "Date": timestamp,
                "PC1": pc1,
                "PC2": pc2,
                "Phase": phase,
                "Amplitude": amplitude,
            }
        )

    return pd.DataFrame(rows)


def contiguous_month_end(series: pd.Series, start_date: str = START_DATE) -> pd.Timestamp | None:
    current = pd.Timestamp(start_date).normalize()
    final = None

    while current in series.index and pd.notna(series.loc[current]):
        final = current
        current = current + pd.offsets.MonthBegin(1)

    return final


def build_record(
    name: str,
    output_dir: str,
    status: str,
    output_file: Path | None = None,
    row_count: int = 0,
    coverage_pct: float = 0.0,
    valid_from: str | None = None,
    valid_through: str | None = None,
    source_last_observation_date: str | None = None,
    notes: list[str] | None = None,
) -> dict[str, object]:
    config = DRIVER_CONFIG[name]
    artifacts = artifact_paths(name, output_dir)
    source_info = source_file_info(str(config["source_path"]))
    target_start_date, target_end_date = target_window(name)

    record = {
        "name": config["display_name"],
        "slug": name,
        "target_year": TARGET_YEAR,
        "status": status,
        "is_complete": status == "complete",
        "is_partial": status == "partial",
        "source_path": str(config["source_path"]),
        "source_url": config["source_url"],
        "source_cadence": config["cadence"],
        "processing_method": config["method"],
        "output_file": str(output_file) if output_file else None,
        "metadata_file": str(artifacts["metadata_json"]),
        "row_count": row_count,
        "coverage_pct": round(float(coverage_pct), 2),
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "valid_from": valid_from,
        "valid_through": valid_through,
        "source_last_observation_date": source_last_observation_date,
        "source_fetched_at": source_info["fetched_at"],
        "generated_at": utc_now(),
        "notes": notes or [],
    }
    artifacts["metadata_json"].write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def publish_frame(
    name: str,
    frame: pd.DataFrame,
    output_dir: str,
    source_last_observation_date: str | None,
    notes: list[str] | None = None,
) -> dict[str, object]:
    ensure_proc_dir(output_dir)
    clear_driver_outputs(name, output_dir)
    artifacts = artifact_paths(name, output_dir)

    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]

    if frame.empty:
        return build_record(
            name=name,
            output_dir=output_dir,
            status="missing",
            source_last_observation_date=source_last_observation_date,
            notes=notes or ["No rows were available for the requested year."],
        )

    if frame.isnull().any().any():
        return build_record(
            name=name,
            output_dir=output_dir,
            status="error",
            source_last_observation_date=source_last_observation_date,
            notes=(notes or []) + ["Output frame still contains null values."],
        )

    target_start_date, target_end_date = target_window(name)
    full_index = expected_index(target_start_date, target_end_date)
    data_index = pd.DatetimeIndex(frame.index)
    row_count = len(frame)
    coverage_pct = (row_count / len(full_index)) * 100
    valid_from = data_index.min().date().isoformat()
    valid_through = data_index.max().date().isoformat()

    is_complete = data_index.equals(full_index)
    output_file = artifacts["complete_csv"] if is_complete else artifacts["partial_csv"]
    frame.to_csv(output_file)

    return build_record(
        name=name,
        output_dir=output_dir,
        status="complete" if is_complete else "partial",
        output_file=output_file,
        row_count=row_count,
        coverage_pct=coverage_pct,
        valid_from=valid_from,
        valid_through=valid_through,
        source_last_observation_date=source_last_observation_date,
        notes=notes,
    )


def process_mjo(input_file: str = MJO_RAW_FILE, output_dir: str = PROC_DIR) -> dict[str, object]:
    print("Processing MJO from the local raw file...")
    ensure_proc_dir(output_dir)

    if not os.path.exists(input_file):
        clear_driver_outputs("mjo", output_dir)
        return build_record(
            name="mjo",
            output_dir=output_dir,
            status="missing",
            notes=[f"Missing raw source file: {input_file}"],
        )

    try:
        df = pd.read_csv(
            input_file,
            sep=r"\s+",
            skiprows=2,
            header=None,
            names=["Year", "Month", "Day", "RMM1", "RMM2", "Phase_BOM", "Amp_BOM", "Source"],
            usecols=[0, 1, 2, 3, 4],
            na_values=[1.0e36, 999],
        )
    except Exception as exc:
        clear_driver_outputs("mjo", output_dir)
        return build_record(
            name="mjo",
            output_dir=output_dir,
            status="error",
            notes=[f"Failed to parse MJO raw file: {exc}"],
        )

    df["Date"] = pd.to_datetime(df[["Year", "Month", "Day"]])
    df = df.set_index("Date").sort_index()
    source_last = df.index.max().date().isoformat() if not df.empty else None

    target = df.loc[(df.index >= START_DATE) & (df.index <= END_DATE), ["RMM1", "RMM2"]].copy()
    if target.empty:
        clear_driver_outputs("mjo", output_dir)
        return build_record(
            name="mjo",
            output_dir=output_dir,
            status="missing",
            source_last_observation_date=source_last,
            notes=[f"MJO source last observation is {source_last}; no {TARGET_YEAR} rows are available."],
        )

    daily_index = pd.date_range(target.index.min(), target.index.max(), freq="D")
    target = target.reindex(daily_index).interpolate(method="linear", limit_area="inside")
    if target[["RMM1", "RMM2"]].isnull().any().any():
        clear_driver_outputs("mjo", output_dir)
        return build_record(
            name="mjo",
            output_dir=output_dir,
            status="error",
            source_last_observation_date=source_last,
            notes=["MJO raw file contains unresolved internal gaps."],
        )

    target["Phase"] = [calculate_phase_value(r1, r2) for r1, r2 in zip(target["RMM1"], target["RMM2"])]
    target["Amplitude"] = np.sqrt(target["RMM1"] ** 2 + target["RMM2"] ** 2)
    return publish_frame(
        name="mjo",
        frame=target[["RMM1", "RMM2", "Phase", "Amplitude"]],
        output_dir=output_dir,
        source_last_observation_date=source_last,
        notes=["Processing uses the local raw file only; no live fetch occurs in the processor."],
    )


def process_enso(input_file: str = ENSO_RAW_FILE, output_dir: str = PROC_DIR) -> dict[str, object]:
    print("Processing ENSO (ONI)...")
    ensure_proc_dir(output_dir)

    if not os.path.exists(input_file):
        clear_driver_outputs("enso", output_dir)
        return build_record(
            name="enso",
            output_dir=output_dir,
            status="missing",
            notes=[f"Missing raw source file: {input_file}"],
        )

    df = pd.read_csv(input_file, sep=r"\s+")
    df["Month"] = df["SEAS"].map(SEASON_TO_MONTH)
    df["Date"] = pd.to_datetime(df["YR"].astype(str) + "-" + df["Month"].astype(str) + "-01")
    monthly = df.set_index("Date").sort_index()[["ANOM"]]
    source_last = monthly.index.max().date().isoformat() if not monthly.empty else None

    target_monthly = monthly.loc[f"{TARGET_YEAR}-01-01":f"{TARGET_YEAR}-12-01"].dropna()
    if target_monthly.empty:
        clear_driver_outputs("enso", output_dir)
        return build_record(
            name="enso",
            output_dir=output_dir,
            status="missing",
            source_last_observation_date=source_last,
            notes=[f"ENSO source last observation is {source_last}; no {TARGET_YEAR} monthly rows are available."],
        )

    last_valid_month = target_monthly.index.max()
    context = monthly.loc[f"{int(TARGET_YEAR) - 1}-12-01":last_valid_month]
    daily_index = pd.date_range(START_DATE, month_end(last_valid_month), freq="D")
    daily = context.reindex(daily_index, method="ffill")
    return publish_frame(
        name="enso",
        frame=daily,
        output_dir=output_dir,
        source_last_observation_date=source_last,
        notes=["Daily ENSO output is a forward-filled view of the monthly ONI index."],
    )


def process_iod(input_file: str = IOD_RAW_FILE, output_dir: str = PROC_DIR) -> dict[str, object]:
    print("Processing IOD (DMI)...")
    ensure_proc_dir(output_dir)

    if not os.path.exists(input_file):
        clear_driver_outputs("iod", output_dir)
        return build_record(
            name="iod",
            output_dir=output_dir,
            status="missing",
            notes=[f"Missing raw source file: {input_file}"],
        )

    with open(input_file, "r", encoding="utf-8", errors="ignore") as handle:
        lines = handle.readlines()

    rows = []
    for line in lines:
        parts = line.split()
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        season = parts[1]
        if season not in SEASON_TO_MONTH:
            continue

        try:
            year = int(parts[0])
            dmi = float(parts[4])
        except ValueError:
            continue

        rows.append(
            {
                "Year": year,
                "Month": SEASON_TO_MONTH[season],
                "DMI": np.nan if np.isnan(dmi) else dmi,
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        clear_driver_outputs("iod", output_dir)
        return build_record(
            name="iod",
            output_dir=output_dir,
            status="missing",
            notes=["IOD raw file could not be parsed."],
        )

    frame["Date"] = pd.to_datetime(frame["Year"].astype(str) + "-" + frame["Month"].astype(str) + "-01")
    monthly = frame.set_index("Date").sort_index()[["DMI"]]
    source_last = monthly.dropna().index.max().date().isoformat() if not monthly.dropna().empty else None

    target_monthly = monthly.loc[f"{TARGET_YEAR}-01-01":f"{TARGET_YEAR}-12-01", "DMI"]
    if target_monthly.dropna().empty:
        clear_driver_outputs("iod", output_dir)
        return build_record(
            name="iod",
            output_dir=output_dir,
            status="missing",
            source_last_observation_date=source_last,
            notes=[f"IOD source last valid observation is {source_last}; no usable {TARGET_YEAR} months are available."],
        )

    last_contiguous_month = contiguous_month_end(target_monthly)
    if last_contiguous_month is None:
        clear_driver_outputs("iod", output_dir)
        return build_record(
            name="iod",
            output_dir=output_dir,
            status="missing",
            source_last_observation_date=source_last,
            notes=[f"IOD source does not provide a valid January {TARGET_YEAR} month to anchor the series."],
        )

    context = monthly.loc[f"{int(TARGET_YEAR) - 1}-12-01":last_contiguous_month]
    daily_index = pd.date_range(START_DATE, month_end(last_contiguous_month), freq="D")
    daily = context.reindex(daily_index, method="ffill")
    notes = ["Daily IOD output is a forward-filled view of the CPC overlapping 3-month DMI index."]
    if last_contiguous_month.month < 12:
        notes.append(
            f"IOD source is partial for {TARGET_YEAR}; coverage stops after {month_end(last_contiguous_month).date().isoformat()}."
        )
    return publish_frame(
        name="iod",
        frame=daily,
        output_dir=output_dir,
        source_last_observation_date=source_last,
        notes=notes,
    )


def process_bsiso(input_file: str = BSISO_RAW_FILE, output_dir: str = PROC_DIR) -> dict[str, object]:
    print("Processing BSISO monitoring index...")
    ensure_proc_dir(output_dir)

    if not os.path.exists(input_file):
        clear_driver_outputs("bsiso", output_dir)
        return build_record(
            name="bsiso",
            output_dir=output_dir,
            status="missing",
            notes=[f"Missing raw source file: {input_file}"],
        )

    with open(input_file, "r", encoding="utf-8", errors="ignore") as handle:
        df = parse_bsiso_pc_lines(handle.readlines())

    source_last = df["Date"].max().date().isoformat() if not df.empty else None
    if df.empty:
        clear_driver_outputs("bsiso", output_dir)
        return build_record(
            name="bsiso",
            output_dir=output_dir,
            status="missing",
            source_last_observation_date=source_last,
            notes=["BSISO raw file could not be parsed."],
        )

    df = df.set_index("Date").sort_index()
    target_start_date, target_end_date = target_window("bsiso")
    target = df.loc[(df.index >= target_start_date) & (df.index <= target_end_date)].copy()
    if target.empty:
        clear_driver_outputs("bsiso", output_dir)
        return build_record(
            name="bsiso",
            output_dir=output_dir,
            status="missing",
            source_last_observation_date=source_last,
            notes=[f"BSISO source last observation is {source_last}; no {TARGET_YEAR} seasonal rows are available."],
        )

    daily_index = pd.date_range(target.index.min(), target.index.max(), freq="D")
    target = target.reindex(daily_index)
    if target[["PC1", "PC2", "Phase", "Amplitude"]].isnull().any().any():
        clear_driver_outputs("bsiso", output_dir)
        return build_record(
            name="bsiso",
            output_dir=output_dir,
            status="error",
            source_last_observation_date=source_last,
            notes=["BSISO raw file contains unresolved daily gaps in the target window."],
        )

    return publish_frame(
        name="bsiso",
        frame=target[["PC1", "PC2", "Phase", "Amplitude"]],
        output_dir=output_dir,
        source_last_observation_date=source_last,
        notes=[
            "BSISO processing uses the local raw file only; no live fetch occurs in the processor.",
            "APCC BSISO monitoring is a boreal-summer product; completion is evaluated on 2025-05-01 through 2025-10-31.",
            "The published APCC BSISO1 component pair is mapped onto PC1/PC2 for a consistent driver interface.",
        ],
    )


def write_driver_manifest(records: list[dict[str, object]], output_dir: str = PROC_DIR) -> Path:
    ensure_proc_dir(output_dir)
    manifest_path = Path(output_dir) / f"driver_status_{TARGET_YEAR}.json"
    summary = {
        "generated_at": utc_now(),
        "target_year": TARGET_YEAR,
        "records": records,
        "complete": [record["name"] for record in records if record["status"] == "complete"],
        "partial": [record["name"] for record in records if record["status"] == "partial"],
        "missing_or_error": [
            record["name"] for record in records if record["status"] not in {"complete", "partial"}
        ],
    }
    manifest_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def process_all_drivers(output_dir: str = PROC_DIR) -> list[dict[str, object]]:
    records = [
        process_mjo(output_dir=output_dir),
        process_enso(output_dir=output_dir),
        process_iod(output_dir=output_dir),
        process_bsiso(output_dir=output_dir),
    ]
    write_driver_manifest(records, output_dir)
    return records


if __name__ == "__main__":
    results = process_all_drivers()
    failed = [record["name"] for record in results if record["status"] != "complete"]
    if failed:
        print(f"Driver processing did not complete for: {', '.join(failed)}")
        sys.exit(1)
    print("All drivers processed successfully.")
