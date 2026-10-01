"""Guided stopwatch for the decision-time test. Run:  python timing_test.py

It times one manual comparison and one ERNow comparison, saves both to
data/decision_time_results.csv, and writes the median result into README.md.
"""
import csv
import time
from pathlib import Path

import record_decision_time

CSV = Path(__file__).resolve().parent / "data" / "decision_time_results.csv"
HOSPITALS = ["Massachusetts General Hospital", "Brigham and Women's Hospital", "Brigham and Women's Faulkner Hospital",
             "Beth Israel Deaconess Medical Center", "Boston Medical Center", "Tufts Medical Center"]


def pick():
    for i, h in enumerate(HOSPITALS, 1):
        print(f"  {i}. {h}")
    while True:
        a = input("Which hospital did you pick? Enter 1-6: ").strip()
        if a.isdigit() and 1 <= int(a) <= 6:
            return HOSPITALS[int(a) - 1]


def timed(label, steps):
    print(f"\n=== {label} ===")
    for s in steps:
        print(" -", s)
    input("\nPress Enter to START the timer...")
    t0 = time.monotonic()
    input("Timer running. Press Enter the moment you've decided where to go...")
    sec = round(time.monotonic() - t0)
    print(f"Time: {sec // 60} min {sec % 60:02d} s")
    return sec, pick()


def main():
    who = input("Participant name (or initials): ").strip() or "participant"
    manual = timed("MANUAL RUN (do this first)", [
        "Use the same starting address for both runs.",
        "medicare.gov/care-compare: find each of the 6 hospitals' ED 'time spent in the ED' (6 lookups).",
        "Google Maps: drive time from your address to each hospital (6 lookups).",
        "Decide where you'd go."])
    ernow = timed("ERNOW RUN", [
        "Open https://ernowboston.streamlit.app/ in a fresh tab.",
        "Allow location (or pick your area) and decide where you'd go."])
    new = not CSV.exists() or CSV.stat().st_size == 0
    with CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["participant", "method", "seconds", "picked_hospital"])
        w.writerow([who, "manual", manual[0], manual[1]])
        w.writerow([who, "ernow", ernow[0], ernow[1]])
    print("\nSaved. README result:")
    record_decision_time.main()
    print("\nAdd more people by running this again. Then: git add -A && git commit -m 'Decision time' && git push")


if __name__ == "__main__":
    main()
