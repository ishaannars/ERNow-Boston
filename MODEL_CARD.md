# ERNow Boston — Model Card

## Purpose
For urgent, non-life-threatening visits, help people find the Boston ER that usually gets them in and out fastest, not just the closest, in about 10 seconds, by forecasting each hospital's typical ED visit time for the next CMS period with a tested range. This works without live data because ED performance is highly persistent year to year (R² 0.93). Not a live queue and not medical advice.

## Target
Next-release CMS **OP-18b**: median minutes from ED arrival to departure for discharged patients, per hospital.

## Data
Ten CMS Hospital Compare releases (2017-10 to 2026-08), every U.S. hospital: 4,438 hospitals and 35,164 labeled hospital-periods. Inputs come only from releases available before the period being predicted.

## Features
Last and prior OP-18b, most recent change, psychiatric-patient ED time (OP-18c), left without being seen (OP-22), ED volume category, CMS star rating, hospital type, ownership, state, gap to state average, gap to peer (volume × type) average. OP-18a and OP-18d appear only in the newest release and are excluded.

## Models compared
Persistence baseline · Ridge regression (on the change) · robust partial pooling (shrinkage toward state and peer averages, least-absolute-error fit) · gradient boosting (on the change).

## Validation
Chronological: train on all earlier releases, select on the second-newest year, test once on the newest (4,017 hospitals), plus a rolling year-by-year backtest over 7 held-out years. Promotion rule: a learned model must beat Persistence MAE by 2% on validation.

## Results

Written automatically by `national_model.py`:

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

## Intended use and limits
- Describes typical ED performance for a period, published 9–12 months after it ends; it cannot see today's queue, triage, staffing, or boarding.
- OP-18b covers discharged patients only; academic and trauma centers treat sicker patients and run longer for reasons that do not mean worse care.
- Peer comparisons adjust for case complexity with public proxies (heart-attack and stroke patient volume, cardiac-surgery capability, inpatient volume), not each patient's severity.
- The cards show CMS OP-22 (left before being seen, 2024) as a crowding signal. CMS OP-20 provider wait (2019 or earlier) appears only as context on the Forecast Model page. No hand-set adjustment changes any displayed number.

## Retraining
Add a new CMS release archive to `data/cms_archives/` and run `python national_model.py`. The app reads the regenerated results.
