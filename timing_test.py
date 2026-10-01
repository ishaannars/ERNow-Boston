"""Guided decision-time test.

    python timing_test.py          run a test (stopwatch or type in your own times)
    python timing_test.py --reset       delete all saved results and restore the README placeholder
    python timing_test.py --mark-quick  relabel earlier manual runs as quick searches (closest ER only)

Times one manual comparison and one ERNow comparison, saves them to
data/decision_time_results.csv, and writes the median result into README.md.
"""
import csv
import sys
import time
from pathlib import Path

import record_decision_time

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "data" / "decision_time_results.csv"
README = ROOT / "README.md"
HEADER = ["participant", "method", "seconds", "picked_hospital"]
PLACEHOLDER = "_Not yet measured. Run `python timing_test.py` (guided stopwatch, about 10 minutes)._"
HOSPITALS = ["Massachusetts General Hospital", "Brigham and Women's Hospital", "Brigham and Women's Faulkner Hospital",
             "Beth Israel Deaconess Medical Center", "Boston Medical Center", "Tufts Medical Center"]
MIN_SECONDS = {"full": 120, "quick": 10, "ernow": 3}


def reset():
    with CSV.open("w", newline="") as f:
        csv.writer(f).writerow(HEADER)
    body = README.read_text()
    s, e = record_decision_time.START, record_decision_time.END
    i, j = body.index(s) + len(s), body.index(e)
    README.write_text(body[:i] + "\n" + PLACEHOLDER + "\n" + body[j:])
    print("Cleared all results and restored the README placeholder.")


def pick():
    for i, h in enumerate(HOSPITALS, 1):
        print(f"  {i}. {h}")
    while True:
        a = input("Which hospital did you pick? Enter 1-6: ").strip()
        if a.isdigit() and 1 <= int(a) <= 6:
            return HOSPITALS[int(a) - 1]


def flush_keys():
    """Drop extra Enter presses still in the keyboard buffer (they caused accidental stops)."""
    try:
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def fmt(sec):
    return f"{sec // 60} min {sec % 60:02d} s"


def confirm_plausible(method, sec):
    if sec >= MIN_SECONDS[method]:
        return True
    kind = {"full": "full comparison (12 lookups) usually takes several minutes",
            "quick": "quick search still includes opening the search",
            "ernow": "ERNow run should include loading the page"}[method]
    a = input(f"That was only {fmt(sec)}, but a {kind}. Keep it anyway? (y = keep, n = redo): ").strip().lower()
    return a == "y"


def stopwatch(method, label, steps):
    while True:
        print(f"\n=== {label} ===")
        for s in steps:
            print(" -", s)
        print("\nDo NOT start the task yet.")
        flush_keys()
        input("1) Press Enter to START the timer, then do the whole task.")
        t0 = time.monotonic()
        while True:
            time.sleep(0.3)
            flush_keys()
            if input("2) Timer running. When you've decided where to go, type done and press Enter: ").strip().lower() == "done":
                break
        sec = round(time.monotonic() - t0)
        print(f"Time: {fmt(sec)}")
        if confirm_plausible(method, sec):
            return sec, pick()


def typed(method, label):
    while True:
        a = input(f"\n{label}: how long did it take? Enter minutes:seconds (for example 6:45) or seconds: ").strip()
        try:
            sec = int(a.split(":")[0]) * 60 + int(a.split(":")[1]) if ":" in a else int(a)
        except ValueError:
            print("Couldn't read that. Try again, for example 6:45.")
            continue
        if confirm_plausible(method, sec):
            return sec, pick()


QUICK_STEPS = ["Search 'ER near me' (Google or Maps) the way you normally would.",
               "Skim the results and decide where you'd go."]
FULL_STEPS = ["Use the same starting address for both runs.",
                "medicare.gov/care-compare: find each of the 6 hospitals' ED 'time spent in the ED' (6 lookups).",
                "Google Maps: drive time from your address to each hospital (6 lookups).",
                "Decide where you'd go."]
ERNOW_STEPS = ["Open https://ernowboston.streamlit.app/ in a fresh tab.",
               "Allow location (or pick your area) and decide where you'd go."]


def mark_quick():
    """Relabel earlier `manual` rows as quick searches (for runs that only looked up the closest ER)."""
    rows = list(csv.reader(CSV.open()))
    n = 0
    for r in rows[1:]:
        if len(r) > 1 and r[1].strip().lower() == "manual":
            r[1] = "quick"
            n += 1
    with CSV.open("w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"Relabeled {n} run(s) as quick search.")
    record_decision_time.main()


def main():
    if "--reset" in sys.argv:
        reset()
        return
    if "--mark-quick" in sys.argv:
        mark_quick()
        return
    who = input("Participant name (or initials): ").strip() or "participant"
    print("Which manual run? 1 = quick search ('ER near me', the headline)   2 = full comparison (12 lookups)   3 = both")
    which = input("Enter 1, 2, or 3: ").strip()
    runs = {"1": ["quick"], "2": ["full"], "3": ["quick", "full"]}.get(which, ["quick"])
    do_ernow = input("Also time an ERNow run? (y/n; say n if you already recorded one): ").strip().lower() != "n"
    mode = input("Time with this script's stopwatch (1) or type in times you measured yourself (2)? Enter 1 or 2: ").strip()
    labels = {"full": ("FULL COMPARISON", FULL_STEPS), "quick": ("QUICK SEARCH", QUICK_STEPS), "ernow": ("ERNOW RUN", ERNOW_STEPS)}
    results = []
    for m in runs + (["ernow"] if do_ernow else []):
        label, steps = labels[m]
        res = typed(m, label) if mode == "2" else stopwatch(m, label, steps)
        results.append((m, res))
    new = not CSV.exists() or CSV.stat().st_size == 0
    with CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        for m, (sec, hosp) in results:
            w.writerow([who, m, sec, hosp])
    print("\nSaved. README result:")
    record_decision_time.main()
    print("\nAdd more people by running this again. Then: git add -A && git commit -m 'Decision time' && git push")


if __name__ == "__main__":
    main()
