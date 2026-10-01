# ERNow Boston

**For urgent, non-life-threatening visits: find the ER that gets you seen and home fastest, not just the closest, in about 15 seconds.**

Boston's ERs differ by hours in a way that persists year to year. ERNow uses that to point you to the ER most likely to get you seen fastest, not just the closest, in seconds, using public data alone.

Today people search "ER near me" and go to the closest one, with no information about the ED itself. From 90% of Boston locations, that isn't the ER that would get them seen and home fastest. Hospitals don't publish live waits, but ERNow doesn't need them to help: a hospital's ED time predicts next year's with R² 0.93 across 4,000+ U.S. hospitals. ERNow assembles CMS, CHIA, the CDC, the Weather Service, and road routing into one screen, labels every number by source and period, and is built so live hospital data can plug in the day it exists.

[Try ERNow Boston](https://ernowboston.streamlit.app/)

> ERNow is not a live hospital queue and not medical advice. In an emergency, call 911 or go to the nearest emergency department. Never pass a closer ER because of an ERNow estimate.

## Why it works without live data

Boston's EDs differ by hours, and those differences are structural: size, staffing, how many admitted patients board in the ED, and case mix change slowly. Across 4,246 U.S. hospitals, a hospital's ED time predicts next year's with **R² 0.93**, and annual public data alone picked the **actual fastest local ER 83% of the time** the following year (versus 24% by chance). Like knowing which restaurant on your block is usually packed, you don't need a live feed to make a much better choice than "closest." What ERNow can't see is a usually fast ED having a bad night; that's why it shows tested ranges, labels everything "typical, not live," and is built to plug in live data the day hospitals publish it.

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
| Choosing an ER matters | Median ED visit time in Boston ranges from **3h 28m (Tufts) to 5h 36m (BIDMC): a 2h 8m gap** | CMS OP-18b, period ending Sep 2025 |
| Official data arrives late | CMS ED data is published **9–12 months** after the period it describes ends | Computed across 6 CMS releases |
| Long ED stays are growing | Massachusetts ED visits lasting over 4 hours rose from **~33% to ~44%** (Jul–Sep 2019 vs 2025) | CHIA, reported by the Boston Globe, May 2026 |
| The closest ER is usually not the fastest | For urgent, non-life-threatening visits, a different ER had the shortest drive + typical visit from **90%** of 1,977 Boston locations, typically **~1h 16m** shorter for ~5 min more driving. Holds at **73–90%** from gridlock to free-flowing traffic | `boston_choice_analysis.py` |
| It takes many lookups to compare | Gathering ED times and drive times for 6 hospitals manually takes **12 separate lookups across 2 websites**; ERNow takes one screen | See `TIMING_TEST.md` |
| The method scales | The same pipeline covers the **4,081 U.S. hospitals** that report ED times; Boston is the first city deployed | CMS Hospital Compare archives |

## Decision time (measured)

<!-- DECISION_TIME:START -->
- **ERNow vs the usual search** ("ER near me", pick the closest): **15 s in ERNow vs 45 s**, and ERNow also shows the likely fastest ER (1 participant). The quick search only finds the closest ER, which isn't the fastest overall from 90% of Boston locations (typically ~1h 16m longer in the ED for a non-emergency).
- **Information ERNow assembles:** gathering the same facts by hand (6 ED times + 6 drive times) took 6 min 21 s (1 participant).

Timed with `python timing_test.py` (protocol in `TIMING_TEST.md`).
<!-- DECISION_TIME:END -->

## The model

ERNow forecasts each hospital's next-period **CMS OP-18b**: the median time discharged patients spend in the ED from arrival to departure. The model is trained and tested on **every U.S. hospital** in six CMS Hospital Compare releases (2021–2026), then applied to Boston's six.

`6 CMS releases → national panel (4,246 hospitals, 19,884 hospital-periods) → model comparison → tested 80% ranges → ranking test → Boston forecasts + peers → ERNow`

**Validation is chronological.** Models train on earlier releases, are selected on the next release, and are scored once on the latest release (4,017 held-out hospitals). A learned model must beat Persistence by 2% on validation to be promoted.

| Model | Validation MAE | Test MAE | Test R² |
|---|---|---|---|
| Persistence baseline (last reported value) | 11.8 min | 9.4 min | 0.931 |
| Partial pooling (shrink toward state & peer averages) | 11.6 min | 9.3 min | 0.934 |
| Gradient boosting | 12.6 min | 10.2 min | 0.924 |
| Ridge regression | 12.7 min | 10.5 min | 0.922 |

**Result:** even with 19,884 rows, Persistence was hard to beat. The best challenger improved validation error by 1.6%, short of the 2% bar, so ERNow keeps Persistence. The finding is useful in itself: a hospital's ED performance is highly persistent year to year, which is why last year's public number is already informative.

**Tested 80% ranges.** Regime-adaptive conformalized quantile regression: gradient-boosted 10th/90th percentiles, calibrated on the prior release, then scaled by how much hospitals changed in the latest release (known at prediction time). Static conformal ranges over-covered (88%) because volatility differs year to year; the adaptive version, chosen on an earlier held-out year (**83%**), covered **85%** on the final test year (target 80%) with a median width of **34 minutes**. The old fixed band (0.65×–1.55×) was **4× wider** (134 minutes).

**How sure are these numbers?** Bootstrap with 2,000 resamples on the final test year: fastest-pick accuracy **83% (95% CI 78–87%)**, range coverage **85% (83–86%)**. The best challenger's edge over Persistence is statistically real but about **8 seconds** per hospital on a 3–5 hour visit, and it missed the 2% bar on validation, so Persistence stays.

**Does the ranking hold?** On the test release, the forecast ranked hospitals with a rank correlation of **0.97** nationally and **0.86** within local areas (293 counties with 3+ hospitals). It picked the actual fastest ER in the area **83%** of the time, versus **24%** by chance. Boston backtest: rank correlation 1.00 and the fastest hospital predicted correctly.

**Ablation.** Adding other ED measures, hospital characteristics, and geography to gradient boosting did not beat Persistence on the test release, and ERNow reports that instead of shipping a more complex model that does not help.

**No hand-set adjustments.** Every number on an ER card is public data or a model output tested on held-out hospitals.

**Also in the app:** permutation-importance drivers, who waits longest (by ED volume and ownership; longer ED visits go with more patients leaving before being seen, rank correlation 0.56), peer comparison (each Boston hospital vs its 25 most similar U.S. hospitals, matched on volume, type, ownership, star rating, and case complexity: heart-attack and stroke volume, cardiac surgery, inpatient volume), unusual-change flags, and a "chance it's the fastest" simulation (4,000 scenarios from each tested range plus your drive time).

## What the app shows

- **Your two best options:** the closest ER and the ER likely to be fastest overall, side by side with the same three facts (drive, typical ED visit, drive + visit), plus how much time the faster one saves counting the extra drive both ways
- **All 6 Boston ERs**, sorted by closest (default) or fastest overall, each with:
  - typical ED visit (arrival to leaving) with a tested range, and how it compares with 25 similar U.S. hospitals
  - drive time, drive + typical visit, chance it's the fastest (4,000 simulated trips), and how often patients left before being seen (CMS OP-22, 2024)
- One-tap directions; Boston context (weather, respiratory illness, events) shown but never used to adjust a number
- Methodology and Forecast Model views with every result, in plain language first

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

- **Respiratory-surge forecast:** replace the fixed illness adjustment with a 1–2 week forecast of Massachusetts respiratory ED share, with tested accuracy.
- **More cities:** the national model already covers every U.S. hospital; the next step is the city layer.
- **Live hospital data:** if hospitals publish current waits, ERNow's cards can switch from typical to live.

## Stack

Python · Streamlit · scikit-learn · pandas · NumPy · CMS · CHIA · CDC · National Weather Service · OpenStreetMap · OSRM

© 2026 Ishaan Narasimhan. All rights reserved.
