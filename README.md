# ERNow Boston

**Version 27** · Home-page layout and control styling update.

**For urgent, non-life-threatening visits: find the ER that gets you seen and home fastest, not just the closest, in about 10 seconds.**

Live ER wait times could be years away. ERNow brings ER transparency to Boston now: models built on 4,438 U.S. hospitals predict which ER will usually get you in and out fastest.

Today people search "ER near me" and go to the closest one, with no information about the ED itself. From 83% of Boston locations, that isn't the ER that would get them seen and home fastest. Hospitals don't publish live waits, but ERNow doesn't need them to help: a hospital's ED time predicts next year's with R² 0.93 across 4,000+ U.S. hospitals. ERNow assembles CMS, CHIA, the CDC, the Weather Service, and road routing into one screen, labels every number by source and period, and is built so live hospital data can plug in the day it exists.

[Try ERNow Boston](https://ernowboston.streamlit.app/)

> ERNow is not a live hospital queue and not medical advice. In an emergency, call 911 or go to the nearest emergency department. Never pass a closer ER because of an ERNow estimate.

## Why it works without live data

Boston's EDs differ by hours, and those differences are structural: size, staffing, how many admitted patients board in the ED, and case mix change slowly. Across 4,438 U.S. hospitals, a hospital's ED time predicts next year's with **R² 0.93**, and annual public data alone picked the **actual fastest local ER 83% of the time** the following year (versus 24% by chance). Like knowing which restaurant on your block is usually packed, you don't need a live feed to make a much better choice than "closest." What ERNow can't see is a usually fast ED having a bad night; that's why it shows tested ranges, labels everything "typical, not live," and is built to plug in live data the day hospitals publish it.

## The thesis: accelerate ER transparency the way Tesla accelerated EVs

Tesla's real achievement wasn't a faster car. It pulled a needed but slow-arriving category forward by years, in three moves: prove it works, set the standard, then scale. ER transparency is a category like that.

**Why it's slow to arrive on its own.** Hospitals have no mandate or incentive to publish live ED waits. The only public time-to-provider measure (CMS OP-20) is no longer published (its last data is from 2019 or earlier). What remains is published 9–12 months after the period it describes, and it's split across six sources nobody combines.

**1. Prove it works now.** ERNow combines CMS, CHIA, CDC, the Weather Service, event calendars, and road routing into one screen, with a forecast trained and tested on every U.S. hospital. No hospital partnership needed.

**2. Set the standard.** Every number is labeled with its source and period, no hand-set adjustment changes any displayed number, and uncertainty is shown as a tested range. The Methodology view lists exactly what hospitals would need to publish (current arrival-to-provider time, patients waiting by triage level, boarding counts, diversion status) for ERNow to go live.

**3. Show it scales.** The model already covers the 4,081 U.S. hospitals that report ED times. Boston is the first city deployed; the same pipeline works anywhere.

**What success looks like:** decision time in seconds (measured below), non-emergency patients choosing a faster ER instead of defaulting to the closest, ranges that keep their tested coverage as each new CMS release arrives, and more cities.

**The Tesla move:** ship something useful before the infrastructure exists. Tesla sold cars before charging networks were everywhere, which created the demand for them. ERNow gives a better ER choice today from public data, which makes the case for hospitals to publish live data.

**Guardrail:** ERNow is never a reason to delay care or pass a closer ER in an emergency. That rule is on every page.

## Why it matters

| Finding | Evidence | Source |
|---|---|---|
| Choosing an ER matters | Median ED visit time in Boston ranges from **2h 26m (Boston Medical Center–Brighton) to 5h 36m (BIDMC): a 3h 10m gap** | CMS OP-18b, period ending Sep 2025 |
| Official data arrives late | CMS ED data is published **9–12 months** after the period it describes ends | Computed across 10 CMS releases |
| Long ED stays are growing | Massachusetts ED visits lasting over 4 hours rose from **~33% to ~44%** (Jul–Sep 2019 vs 2025) | CHIA, reported by the Boston Globe, May 2026 |
| The closest ER is usually not the fastest | For urgent, non-life-threatening visits, a different ER had the shortest drive + typical visit from **83%** of 1,997 Boston locations, typically **~1h 38m** shorter for ~14 min more driving. Holds at **74–83%** from gridlock to free-flowing traffic | `boston_choice_analysis.py` |
| It takes many lookups to compare | Gathering ED times and drive times for every Boston ER manually takes **two lookups per hospital across 2 websites**; ERNow takes one screen | See `TIMING_TEST.md` |
| Which ERs are included | All 10 emergency departments in Boston. The 7 general EDs are compared and ranked; Mass Eye and Ear (eye and ENT only), Boston Children's (children only), and VA Boston West Roxbury (enrolled veterans only) are shown in their own section so no one is sent to an ED that can't treat them. Carney Hospital's ED closed in 2024 | CMS Hospital Compare, VA Boston |
| The method scales | The same pipeline covers the **4,081 U.S. hospitals** that report ED times; Boston is the first city deployed | CMS Hospital Compare archives |

## Decision time (measured)

<!-- DECISION_TIME:START -->
- **ERNow vs the usual search** ("ER near me", pick the closest): **9 s in ERNow (5 participants) vs 20 s for the search (5 participants)**, and ERNow also shows the usually quickest ER. The quick search only finds the closest ER, which isn't the fastest overall from 83% of Boston locations (typically ~1h 38m longer in the ED for a non-emergency).
- **Information ERNow assembles:** gathering the same facts by hand (each ER's ED time and drive time) took 6 min 21 s (1 participant).

Timed with `python timing_test.py` (protocol in `TIMING_TEST.md`).
<!-- DECISION_TIME:END -->

## The model

ERNow forecasts each hospital's next-period **CMS OP-18b**: the median time patients who are sent home spend in the ED, from arrival to leaving. Validation is chronological: models learn from earlier releases, are chosen on the next one, and are scored once on the newest one. A learned model must beat Persistence (last year's value) by 2% to be used. The numbers below are written automatically by `national_model.py`, so they always match the app.

<!-- MODEL_RESULTS:START -->
Trained and tested on **every U.S. hospital** in 10 CMS Hospital Compare releases (2017–2026): **4,438 hospitals, 35,164 hospital-periods**, then applied to Boston's general emergency departments.

**Final test year** (4,017 held-out hospitals; chosen on the year before, scored once):

| Model | Selection-year MAE | Test-year MAE | Test R² |
|---|---|---|---|
| Partial pooling (nudged toward similar hospitals) | 11.6 min | 9.4 min | 0.933 |
| Persistence (last year's value) | 11.8 min | 9.4 min | 0.931 |
| Gradient boosting | 12.6 min | 10.3 min | 0.924 |
| Ridge regression | 13.0 min | 10.7 min | 0.918 |

The best challenger, Partial pooling (nudged toward similar hospitals), was 1.7% better in the selection year, short of the 2% bar, so ERNow uses **Persistence (last year's value)**. Ranges: **85%** of 80% ranges held the true value (95% CI 84%–86%), median width 34 min. Picked the actual fastest local ER **83%** of the time (95% CI 78%–87%) vs **24%** by chance across 293 local areas.

**Year by year (rolling backtest: each year trained only on earlier years):**

| Held-out release | Persistence MAE | Best challenger MAE | ERNow's rule used | 80% range coverage | Fastest-pick |
|---|---|---|---|---|---|
| 2020-10 | 11.1 min | 10.8 min | — | 81% | 75% |
| 2021-10 | 15.9 min | 15.4 min | Ridge regression | 66% | 71% |
| 2022-07 | 12.0 min | 11.7 min | Ridge regression | 97% | 75% |
| 2023-10 | 14.5 min | 13.8 min | Gradient boosting | 55% | 74% |
| 2024-10 | 13.6 min | 13.4 min | Gradient boosting | 88% | 71% |
| 2025-11 | 11.8 min | 11.6 min | Persistence | 83% | 76% |
| 2026-08 | 9.4 min | 9.4 min | Persistence | 85% | 83% |

Run year by year, ERNow's promotion rule averaged **12.8 min** error vs **12.9 min** for always using Persistence, switching to a learned model in 4 of 6 years and doing worse in 1.
<!-- MODEL_RESULTS:END -->

**What the year-by-year test shows.** During the volatile 2020–2023 releases, when the pandemic scrambled ED operations, learned models beat Persistence by more than 2% and the ranges missed in both directions. In the three stable years since, Persistence wins and the ranges sit near their 80% target. Run year by year, ERNow's promotion rule switched to a learned model in 4 of 6 years and came out only slightly ahead of always using Persistence (12.8 vs 12.9 min). Even during upheaval, last year's public data stayed hard to beat.

**Ablation.** Adding other ED measures, hospital characteristics, and geography to gradient boosting did not beat Persistence on the final test year; ERNow reports that instead of shipping a more complex model that doesn't help.

**No hand-set adjustments.** Every number on an ER card is public data or a model output tested on held-out hospitals.

**Also in the app:** permutation-importance drivers, who waits longest (by ED volume and ownership; longer ED visits go with more patients leaving before being seen, rank correlation 0.56), peer comparison (each Boston hospital vs its 25 most similar U.S. hospitals, matched on volume, type, ownership, star rating, and case complexity: heart-attack and stroke volume, cardiac surgery, inpatient volume), unusual-change flags, and a "chance it's the fastest" simulation (4,000 scenarios from each tested range plus your drive time).

## What the app shows

- **Your best option:** the ER that usually gets you in and out fastest (drive + typical visit), with how much sooner you're typically done than at the closest ER. If the closest ER is also the quickest, it says so
- **Type of emergency:** General (default) or Eye, ear, nose, or throat, which puts Mass Eye and Ear, the specialist ED, first
- **Other Boston emergency departments:** Mass Eye and Ear, Boston Children's, and VA Boston West Roxbury, each labeled with who it serves, with drive time (and a forecast range where CMS publishes ED times)
- **Your location is remembered** for the visit, so switching pages doesn't ask again
- **Your doctors' hospital system (optional):** pick Mass General Brigham, Beth Israel Lahey Health, Boston Medical Center Health System, or Tufts Medicine to tag its ERs and see the quickest one in your system, since records follow you within a system. Ranking stays time-based
- **Insurance, answered:** every ER must treat you (EMTALA), and emergency care is billed at in-network cost-sharing even out of network (No Surprises Act), so insurance isn't a reason to skip the quickest ER
- **All 7 Boston ERs**, sorted by closest (default) or fastest overall, each with:
  - typical ED visit (arrival to leaving) with a tested range, and how it compares with 25 similar U.S. hospitals
  - drive time, drive + typical visit, chance it's the fastest (4,000 simulated trips), and how often patients left before being seen (CMS OP-22, 2024)
- One-tap directions; Boston context (weather, respiratory illness, events) shown but never used to adjust a number
- Methodology and Forecast Model views with every result, in plain language first

## Version 27: home-page controls and layout

The home page keeps its dense overview with consistent spacing, aligned ER cards, and the same Instrument Sans typography for buttons, field labels, and selections. Serif headings and key time estimates preserve the existing visual hierarchy. Cards and controls stack on smaller screens, and model footnotes wrap instead of being cut off. Navigation visibly marks the current view, card actions align, and wide result tables scroll horizontally on small screens. Missing ED-time data uses body text rather than a large time estimate. The recommendation border follows the recommended hospital when the sort order changes. Shared styling lives in `styles.css`.

- **Change location:** beside the saved location in **Your visit**. Clears the location for this session so you can use your device location again or choose a Boston area under “Location blocked? Choose a Boston area.” The location is remembered while switching views during the visit.
- **Your doctors' hospital system (optional):** grouped with **Type of emergency**, with a visible explanation below each control. Choose a system to highlight its ERs, see its quickest available option, and optionally sort that system first. **Any** compares all systems. The quickest overall recommendation remains based on drive plus typical ED visit time; this is a continuity-of-care preference, not an insurance-network filter.

## What would make this live

ERNow is built so live hospital data could plug in directly. If hospitals published current median arrival-to-provider time (hourly), patients waiting by triage level, ED boarding counts, and ambulance diversion status, ERNow could move from typical performance to current conditions.

## Data sources

CMS Hospital Compare (OP-18b, OP-18c, OP-22, ED volume, hospital characteristics) · CHIA Hospital Profiles (HFY 2024 ED visits and inpatient occupancy) · CMS OP-20 archive (2019 or earlier) · CDC Massachusetts respiratory illness · National Weather Service · Boston-area event sources · OpenStreetMap / OSRM

## Reproduce

```
pip install -r requirements.txt
# put CMS Hospital Compare archive zips in data/cms_archives/ (see HISTORICAL_DATA_SETUP.md)
python national_model.py      # builds the panel, trains, tests, writes data/national_results.json
streamlit run app.py
```

## Coming next

- **Respiratory-surge forecast:** a tested 1–2 week forecast of Massachusetts respiratory ED demand (today, weather and illness are shown as context only).
- **Calibrate "chance fastest":** check that when it says 70%, that ER really is quickest about 70% of the time.
- **Traffic-aware drive times:** today's routes exclude live traffic.
- **More cities:** the national model already covers every U.S. hospital; the next step is the city layer.
- **Live hospital data:** if hospitals publish current waits, ERNow's cards can switch from typical to live.
- **Urgent care for minor problems** and **MBTA transit times** as additional ways to decide.

## Stack

Python · Streamlit · scikit-learn · pandas · NumPy · CMS · CHIA · CDC · National Weather Service · OpenStreetMap · OSRM

© 2026 Ishaan Narasimhan. All rights reserved.
