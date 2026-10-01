# Decision-time test

**Easiest way:** run `python timing_test.py`. It walks you through both runs with a built-in stopwatch, saves the times, and writes the result into the README. The steps below are the same protocol, if you'd rather time it by hand.

Measures the headline claim: ERNow gives a better ER choice (closest **and** likely fastest) faster than the usual "ER near me" search.

## Setup (once)
- Pick one starting address and use it for every run (for example, your apartment).
- Use a phone stopwatch. Use a fresh browser tab for each run.
- Do the manual run first, then ERNow, so ERNow's answer can't influence the manual search.

## Two kinds of manual run

- **Quick search (the headline):** search "ER near me" and pick, the way most people do. ERNow is compared against this, because it's what people actually do.
- **Full comparison (supporting):** gather the same information ERNow shows, described below, to show what ERNow assembles.

The script asks which one you're timing. If you already saved a quick search as a manual run, `python timing_test.py --mark-quick` relabels it.

## Full comparison: two lookups per ER across 2 websites
Start the timer, then gather, for each of Boston's 7 ERs (MGH, Brigham and Women's, BWH Faulkner, BIDMC, Boston Medical Center, Boston Medical Center–Brighton, Tufts Medical Center):

1. **CMS Care Compare** (medicare.gov/care-compare): search the hospital, open its page, find the emergency department "median time patients spent in the ED before leaving" (7 lookups).
2. **Google Maps**: drive time from your starting address to the hospital (7 lookups).

While you're on each hospital's own website, note whether it posts a live ED wait time (yes/no).

Write the 7 ED times and 7 drive times down, decide where you'd go, then **stop the timer**.

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
