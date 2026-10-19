from pathlib import Path
from zipfile import ZipFile
import io
import re

import pandas as pd

BASE = Path(__file__).parent
ARCHIVE_DIR = BASE / "data" / "cms_archives"
OUT_PATH = BASE / "data" / "cms_op18b_history.csv"
HOSPITAL_PATH = BASE / "data" / "boston_er_data.csv"

TIMELY_PATTERN = re.compile(r"timely[_\s-]*and[_\s-]*effective[_\s-]*care.*hospital.*\.csv$", re.I)

def normalize_columns(df):
    mapping = {}
    for col in df.columns:
        key = re.sub(r"[^a-z0-9]+", " ", str(col).lower()).strip()
        mapping[key] = col
    return mapping

def parse_snapshot_date(name):
    # NBER style: hospitals_compare_202511.zip
    m = re.search(r"(20\d{2})(0[1-9]|1[0-2])", name)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    # CMS style: hospitals_11_2025.zip
    m = re.search(r"(0?[1-9]|1[0-2])[_-](20\d{2})", name)
    if m:
        return pd.Timestamp(year=int(m.group(2)), month=int(m.group(1)), day=1)
    return pd.NaT

def extract_op18b(df, archive_name):
    cols = normalize_columns(df)
    required = ["facility id", "measure id", "score"]
    if not all(k in cols for k in required):
        return pd.DataFrame()

    out = df.copy()
    out["_facility_id"] = out[cols["facility id"]].astype(str).str.zfill(6)
    out["_measure_id"] = out[cols["measure id"]].astype(str).str.upper().str.strip()
    out["_score"] = pd.to_numeric(out[cols["score"]], errors="coerce")
    out = out[out["_measure_id"].isin(["OP_18B", "OP_18b".upper()])].copy()
    out = out[out["_score"].notna()]
    if out.empty:
        return out

    for canonical, aliases in {
        "facility_name": ["facility name"],
        "reporting_start": ["start date"],
        "reporting_end": ["end date"],
    }.items():
        source = next((cols[a] for a in aliases if a in cols), None)
        out[canonical] = out[source] if source else None

    out["reporting_start"] = pd.to_datetime(out["reporting_start"], errors="coerce")
    out["reporting_end"] = pd.to_datetime(out["reporting_end"], errors="coerce")
    out["snapshot_date"] = parse_snapshot_date(archive_name)
    out["source_archive"] = archive_name

    return out[[
        "_facility_id", "facility_name", "_score",
        "reporting_start", "reporting_end",
        "snapshot_date", "source_archive"
    ]].rename(columns={
        "_facility_id": "cms_provider_id",
        "_score": "observed_wait_min",
    })

def read_archive(path):
    rows = []
    if path.suffix.lower() == ".zip":
        with ZipFile(path) as z:
            for member in z.namelist():
                if TIMELY_PATTERN.search(member.replace("\\", "/")):
                    raw = z.read(member)
                    try:
                        df = pd.read_csv(io.BytesIO(raw), dtype=str, low_memory=False)
                    except UnicodeDecodeError:
                        df = pd.read_csv(io.BytesIO(raw), dtype=str, low_memory=False, encoding="latin-1")
                    rows.append(extract_op18b(df, path.name))
    elif path.suffix.lower() == ".csv" and TIMELY_PATTERN.search(path.name):
        df = pd.read_csv(path, dtype=str, low_memory=False)
        rows.append(extract_op18b(df, path.name))
    return [r for r in rows if not r.empty]

def build_history():
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    hospitals = pd.read_csv(HOSPITAL_PATH, dtype={"cms_provider_id": str})
    hospitals["cms_provider_id"] = hospitals["cms_provider_id"].astype(str).str.zfill(6)
    hospital_map = hospitals.set_index("cms_provider_id")["hospital"].to_dict()
    wanted = set(hospital_map)

    pieces = []
    for path in sorted(ARCHIVE_DIR.iterdir()):
        if path.suffix.lower() not in {".zip", ".csv"}:
            continue
        pieces.extend(read_archive(path))

    if not pieces:
        raise SystemExit(
            "No usable CMS archive files found in data/cms_archives/. "
            "Add Hospital Compare archive ZIPs containing Timely_and_Effective_Care-Hospital.csv."
        )

    hist = pd.concat(pieces, ignore_index=True)
    hist = hist[hist["cms_provider_id"].isin(wanted)].copy()
    hist["hospital"] = hist["cms_provider_id"].map(hospital_map)

    # Prefer the actual OP-18b collection period end date as the modeling timestamp.
    hist["timestamp"] = hist["reporting_end"].fillna(hist["snapshot_date"])
    hist = hist.dropna(subset=["timestamp", "observed_wait_min", "hospital"])

    # Repeated archive snapshots can contain the same reporting period.
    hist = (
        hist.sort_values(["hospital", "timestamp", "snapshot_date"])
            .drop_duplicates(["cms_provider_id", "timestamp"], keep="last")
            .sort_values(["timestamp", "hospital"])
            .reset_index(drop=True)
    )

    hist.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(hist):,} rows to {OUT_PATH}")
    print(f"Coverage: {hist['timestamp'].min().date()} to {hist['timestamp'].max().date()}")
    print(f"Hospitals: {hist['hospital'].nunique()}")
    print(hist.groupby("hospital").size().to_string())

if __name__ == "__main__":
    build_history()
