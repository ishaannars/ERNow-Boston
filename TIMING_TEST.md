# Decision-time test

**Easiest way:** run `python timing_test.py`. It walks you through both runs with a built-in stopwatch, saves the times, and writes the result into the README. The steps below are the same protocol, if you'd rather time it by hand.

Measures the headline claim: how long it takes to decide which Boston ER to go to, **manually vs in ERNow**.

## Setup (once)
- Pick one starting address and use it for every run (for example, your apartment).
- Use a phone stopwatch. Use a fresh browser tab for each run.
- Do the manual run first, then ERNow, so ERNow's answer can't influence the manual search.

## Two kinds of manual run

- **Full comparison (the headline):** gather the same information ERNow shows, described below.
- **Quick search:** search "ER near me" and pick, the way most people do. It's fast but only finds the closest ER, so it's reported as a separate line.

The script asks which one you're timing. If you already saved a quick search as a manual run, `python timing_test.py --mark-quick` relabels it.

## Full comparison: 12 lookups across 2 websites
Start the timer, then gather, for each of the 6 hospitals (MGH, Brigham and Women's, BWH Faulkner, BIDMC, Boston Medical Center, Tufts Medical Center):

1. **CMS Care Compare** (medicare.gov/care-compare): search the hospital, open its page, find the emergency department "median time patients spent in the ED before leaving" (6 lookups).
2. **Google Maps**: drive time from your starting address to the hospital (6 lookups).

While you're on each hospital's own website, note whether it posts a live ED wait time (yes/no).

Write the 6 ED times and 6 drive times down, decide where you'd go, then **stop the timer**.

## ERNow run
Open https://ernowboston.streamlit.app/, start the timer, enter the same starting address, decide where you'd go, **stop the timer**.

## Record
Add one line per run to `data/decision_time_results.csv`:

```
participant,method,seconds,picked_hospital
ishaan,manual,412,Tufts Medical Center
ishaan,ernow,11,Tufts Medical Center
```

Then run `python record_decision_time.py`. It writes the medians and the participant count into the README automatically. More participants make the number stronger; report the count honestly.
