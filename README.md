# ERNow Boston

**Compare Boston ERs in seconds, when you don't have minutes to search.**

Boston has no single place to compare emergency departments, and hospitals don't publish live wait times. The useful data already exists, but it is scattered across CMS, the state's Center for Health Information and Analysis (CHIA), the CDC, the National Weather Service, event calendars, and maps. ERNow shows what ER transparency looks like **now**, with public data alone: one screen, a forecast trained on every U.S. hospital, and every number labeled with its source and period.

[Try ERNow Boston](https://ernowboston.streamlit.app/)

> ERNow is not a live hospital queue and not medical advice. In an emergency, call 911 or go to the nearest emergency department. Never pass a closer ER because of an ERNow estimate.

## Why it matters

| Finding | Evidence | Source |
|---|---|---|
| Choosing an ER matters | Median ED visit time in Boston ranges from **3h 28m (Tufts) to 5h 36m (BIDMC): a 2h 8m gap** | CMS OP-18b, period ending Sep 2025 |
| Official data arrives late | CMS ED data is published **9–12 months** after the period it describes ends | Computed across 6 CMS releases |
| Long ED stays are growing | Massachusetts ED visits lasting over 4 hours rose from **~33% to ~44%** (Jul–Sep 2019 vs 2025) | CHIA, reported by the Boston Globe, May 2026 |
| It takes many lookups to compare | Gathering ED times and drive times for 6 hospitals manually takes **12 separate lookups across 2 websites**; ERNow takes one screen | See `TIMING_TEST.md` |
| The method scales | The same pipeline covers **4,658 U.S. hospitals**; Boston is the first city deployed | CMS Hospital Compare archives |

## Decision time (measured)

<!-- DECISION_TIME:START -->
Comparing Boston's 6 ERs took a median of **4 s manually vs 2 s in ERNow** (**2× faster**; 1 participant, timed with the protocol in `TIMING_TEST.md`). Participants picked the same hospital both ways in 1 of 1 cases.
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

**Tested 80% ranges.** Regime-adaptive conformalized quantile regression: gradient-boosted 10th/90th percentiles, calibrated on the prior release, then scaled by how much hospitals changed in the latest release (known at prediction time). Static conformal ranges over-covered (88%) because volatility differs year to year; the adaptive version, chosen on an earlier held-out year (**83%**), covered **84%** on the final test year (target 80%) with a median width of **34 minutes**. The old fixed band (0.65×–1.55×) was **4× wider** (134 minutes).

**Does the ranking hold?** On the test release, the forecast ranked hospitals with a rank correlation of **0.97** nationally and **0.86** within local areas (293 counties with 3+ hospitals). It picked the actual fastest ER in the area **83%** of the time, versus **24%** by chance. Boston backtest: rank correlation 1.00 and the fastest hospital predicted correctly.

**Ablation.** Adding other ED measures, hospital characteristics, and geography to gradient boosting did not beat Persistence on the test release, and ERNow reports that instead of shipping a more complex model that does not help.

**No hand-set adjustments.** Every number on an ER card is public data or a model output tested on held-out hospitals.

**Also in the app:** permutation-importance drivers, who waits longest (by ED volume and ownership; longer ED visits go with more patients leaving before being seen, rank correlation 0.56), peer comparison (each Boston hospital vs its 25 most similar U.S. hospitals, matched on volume, type, ownership, star rating, and case complexity: heart-attack and stroke volume, cardiac surgery, inpatient volume), unusual-change flags, and a "chance it's the fastest" simulation (4,000 scenarios from each tested range plus your drive time).

## What the app shows

- **Expected ED visit time** for each hospital, with its tested 80% range
- **Chance it's the fastest** option from your location
- **Comparison with similar U.S. hospitals**
- **Provider wait, 2019 data:** the last public CMS time-to-provider measure, shown as-is
- Personalized drive time and one-tap directions
- Boston context (weather, respiratory illness, major events), shown but never used to adjust a number
- Methodology and Forecast Model views with every result above

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
