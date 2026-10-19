"""Has CMS published a newer hospital release than ERNow's latest saved one?

    python scripts/check_new_cms_release.py

Reads the CMS Provider Data Catalog entry for "Timely and Effective Care - Hospital" (dataset yv7e-xc69,
which contains OP-18b) and compares its last-modified date with the newest snapshot in
data/national_ed_panel.csv.gz. Prints NEW_RELEASE=yes/no. Never fails the build on network problems.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/yv7e-xc69"


def main():
    latest = pd.read_csv(ROOT / "data" / "national_ed_panel.csv.gz", usecols=["snapshot"])["snapshot"].max()
    try:
        meta = requests.get(URL, timeout=30, headers={"User-Agent": "ERNow-Boston release check"}).json()
        modified = str(meta.get("modified") or meta.get("issued") or "")[:10]
    except Exception as exc:
        print(f"Could not reach CMS ({exc}); try again later.")
        print("NEW_RELEASE=no")
        return
    new = bool(modified) and modified > str(latest)[:10]
    print(f"Latest saved snapshot: {latest} · CMS dataset last modified: {modified or 'unknown'}")
    print(f"NEW_RELEASE={'yes' if new else 'no'}")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"new_release={'yes' if new else 'no'}\nmodified={modified}\n")


if __name__ == "__main__":
    sys.exit(main())
