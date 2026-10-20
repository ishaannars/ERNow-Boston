"""Download the two hospital-crowding datasets for ERNow's crowding factor test (update 42).

    python scripts/download_crowding_data.py

1. HHS "COVID-19 Reported Patient Impact and Hospital Capacity by Facility" (healthdata.gov, anag-cw7u):
   weekly, per hospital, July 2020 to May 2024 (reporting stopped being required after May 3, 2024).
   Only the few columns the test needs are pulled, page by page, instead of the slow full export.
2. CDC NHSN "Weekly Hospital Respiratory Data (HRD) Metrics by Jurisdiction" (data.cdc.gov, ua7e-t2fy):
   weekly, per state, August 2020 to now, including bed occupancy. This is the one ERNow could use live.
Saves data/hhs_facility_capacity.csv.gz and data/nhsn_state_hrd.csv.gz.
"""
import io
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
HEAD = {"User-Agent": "ERNow-Boston crowding factor test"}
HHS = "https://healthdata.gov/resource/anag-cw7u"
NHSN = "https://data.cdc.gov/resource/ua7e-t2fy"
PAGE = 50000


def get(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEAD, timeout=180)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            print(f"   retry {i + 1}/{tries}: {e}")
            time.sleep(5 * (i + 1))
    raise SystemExit(f"Could not download {url}. Check your connection and try again.")


def pick(cols, *patterns):
    for p in patterns:
        hit = [c for c in cols if all(part in c for part in p.split("&"))]
        if hit:
            return sorted(hit, key=len)[0]
    return None


def hhs():
    cols = list(get(f"{HHS}.json", {"$limit": 1}).json()[0].keys())
    keep = {
        "ccn": pick(cols, "hospital_pk"),
        "week": pick(cols, "collection_week"),
        "beds_used": pick(cols, "inpatient_beds_used_7_day_avg", "inpatient_beds_used&7_day_avg"),
        "beds": pick(cols, "inpatient_beds_7_day_avg", "inpatient_beds&7_day_avg"),
        "adult_occupied": pick(cols, "all_adult_hospital_inpatient_bed_occupied_7_day_avg"),
        "adult_beds": pick(cols, "all_adult_hospital_inpatient_beds_7_day_avg"),
        "icu_used": pick(cols, "staffed_adult_icu_bed_occupancy_7_day_avg"),
        "icu_beds": pick(cols, "total_staffed_adult_icu_beds_7_day_avg"),
    }
    missing = [k for k in ("ccn", "week", "beds_used", "beds") if not keep[k]]
    if missing:
        raise SystemExit(f"HHS columns not found: {missing}. Available: {cols[:40]}")
    keep = {k: v for k, v in keep.items() if v}
    print("HHS columns:", keep)
    parts, offset = [], 0
    while True:
        r = get(f"{HHS}.csv", {"$select": ",".join(keep.values()), "$order": f"{keep['week']},{keep['ccn']}",
                               "$limit": PAGE, "$offset": offset})
        df = pd.read_csv(io.StringIO(r.text), dtype=str)
        if df.empty:
            break
        parts.append(df)
        offset += len(df)
        print(f"   HHS rows so far: {offset:,}")
        if len(df) < PAGE:
            break
    out = pd.concat(parts).rename(columns={v: k for k, v in keep.items()})
    out.to_csv(ROOT / "data" / "hhs_facility_capacity.csv.gz", index=False)
    print(f"Saved data/hhs_facility_capacity.csv.gz ({len(out):,} rows, weeks {out['week'].min()} to {out['week'].max()})")


def nhsn():
    r = get(f"{NHSN}.csv", {"$limit": 500000})
    df = pd.read_csv(io.StringIO(r.text), dtype=str)
    df.to_csv(ROOT / "data" / "nhsn_state_hrd.csv.gz", index=False)
    occ = [c for c in df.columns if "occ" in c.lower() and "inpt" in c.lower()]
    print(f"Saved data/nhsn_state_hrd.csv.gz ({len(df):,} rows; occupancy columns: {occ[:6]})")


if __name__ == "__main__":
    (ROOT / "data").mkdir(exist_ok=True)
    which = sys.argv[1:] or ["nhsn", "hhs"]
    if "nhsn" in which:
        nhsn()
    if "hhs" in which:
        hhs()
