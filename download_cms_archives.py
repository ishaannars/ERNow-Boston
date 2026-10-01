"""Download older CMS Hospital Compare archives (one release per year, 2016-2020) for the national model.

    python download_cms_archives.py

Archives are saved to data/cms_archives/ (kept out of git). Then rerun:
    python national_model.py && python boston_choice_analysis.py
"""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

OUT_DIR = Path(__file__).resolve().parent / "data" / "cms_archives"
INDEX_URLS = [
    "https://www.nber.org/research/data/centers-medicare-medicaid-services-cms-hospital-compare-data",
    "https://data.nber.org/hospital-compare/",
]
YEARS = [2016, 2017, 2018, 2019, 2020]
PREFERRED_MONTHS = ["10", "07", "12", "11", "09", "08", "04", "01"]   # one release per year, October first
HEADERS = {"User-Agent": "Mozilla/5.0 ERNow-Boston historical-data build"}


def discover():
    found = {}
    for url in INDEX_URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"Could not read {url}: {e}")
            continue
        for href in re.findall(r'href=["\']([^"\']+)["\']', r.text):
            m = re.search(r"hospitals?_?compare_?(\d{6})\.zip", href, re.I) or re.search(r"(\d{6})[^/]*\.zip$", href)
            if m:
                found.setdefault(m.group(1), urljoin(url, href))
    return found


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    found = discover()
    if not found:
        sys.exit("No archive links found. Download one Hospital Compare zip per year (2016-2020) from "
                 "https://www.nber.org/research/data/centers-medicare-medicaid-services-cms-hospital-compare-data "
                 "and save each as data/cms_archives/hospitals_compare_YYYYMM.zip")
    for year in YEARS:
        stamp = next((f"{year}{m}" for m in PREFERRED_MONTHS if f"{year}{m}" in found), None)
        if not stamp:
            print(f"{year}: no archive found, skipping")
            continue
        path = OUT_DIR / f"hospitals_compare_{stamp}.zip"
        if path.exists() and path.stat().st_size > 1_000_000:
            print(f"{year}: already have {path.name}")
            continue
        print(f"{year}: downloading {path.name} ...")
        try:
            with requests.get(found[stamp], headers=HEADERS, timeout=300, stream=True) as r:
                r.raise_for_status()
                with path.open("wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            print(f"   saved ({path.stat().st_size / 1e6:.0f} MB)")
        except requests.RequestException as e:
            print(f"   failed: {e}")
            path.unlink(missing_ok=True)
    print("\nArchives now in data/cms_archives:")
    for p in sorted(OUT_DIR.glob("hospitals_compare_*.zip")):
        print("  ", p.name)
    print("\nNext: python national_model.py && python boston_choice_analysis.py")


if __name__ == "__main__":
    main()
