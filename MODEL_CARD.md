# ERNow Boston — Model Card

## Purpose
Compare estimated driving time plus forecasts of hospital-level median ED visits for Boston EDs. This is historical performance, not a live queue, clinical recommendation, time to first clinician, or an individual visit forecast.

## Target and data
Next-release CMS OP-18b: median arrival-to-departure minutes for eligible discharged visits, excluding psychiatric/mental-health and transferred patients. Ten saved releases (Oct 2017–Aug 2026) contain 4,438 hospitals with 35,164 labeled release pairs. Coverage is eligible reporting hospitals, not every U.S. hospital.

## Features and models
Latest and preceding OP-18b, change, OP-18c, OP-22, ED-volume category, star rating, type, ownership, state, and gaps to state/peer means. Candidates: Persistence, Ridge on the change, robust partial pooling, and gradient boosting. Point forecasting currently uses Persistence.

## Validation
Train on earlier releases; choose on the penultimate saved transition; evaluate on the last. Promote a challenger only if validation MAE improves by at least 2%. Reporting windows can overlap and are published after the observed periods; this is a retrospective release-based evaluation. Two early panel transitions skip a release because the hospital lacks a row; neither occurs in the final test transition.

## Intervals and simulation
Regime-adaptive conformalized quantile regression targets 80% coverage of hospital medians. Empirical rolling coverage is 55–97%; adaptive scaling and temporal dependence do not provide a guarantee for each future release or hospital. Deployment refits on earlier labeled data and calibrates on the latest completed transition; coverage of the next release remains unknown.

Simulation draws independent lognormal hospital-median scenarios centered on the point forecast, with spread approximated from the log ratio of the interval bounds. Asymmetric bounds are not matched exactly. Shares are uncalibrated and are not probabilities for individual visit lengths.

## Results

Written automatically by `national_model.py`:

<!-- MODEL_RESULTS:START -->
Trained and tested on **eligible reporting U.S. hospitals** in 10 CMS Hospital Compare releases (2017–2026): **4,438 hospitals, 35,164 labeled release pairs**, then applied to Boston's general emergency departments. Targets are published hospital medians, not individual visit lengths.

**Final test release** (4,017 held-out hospitals; selected on the preceding release, scored once):

| Model | Selection-release MAE | Test-release MAE | Test R² |
|---|---|---|---|
| Partial pooling (nudged toward similar hospitals) | 11.6 min | 9.4 min | 0.933 |
| Persistence (latest reported value) | 11.8 min | 9.4 min | 0.931 |
| Gradient boosting | 12.6 min | 10.3 min | 0.924 |
| Ridge regression | 13.0 min | 10.7 min | 0.918 |

The best challenger, Partial pooling (nudged toward similar hospitals), was 1.7% better in the selection year, short of the 2% bar, so ERNow uses **Persistence (latest reported value)**. Ranges: **85%** of target-80% ranges contained the observed hospital median (95% CI 84%–86%), median width 34 min. Selected the shortest observed hospital median **83%** of the time (95% CI 78%–87%) vs **24%** by chance across 293 counties with at least three eligible hospitals; drive time excluded.

**Year by year (rolling backtest: each year trained only on earlier years):**

| Held-out release | Persistence MAE | Best challenger MAE | ERNow's rule used | Median range coverage | Persistence county pick |
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
- Observed 9.42-minute MAE and R² 0.931 describe hospital medians; they do not bound patient-level errors.
- County selection accuracy excludes driving time, clinical suitability, and patient outcomes. Rolling county-pick figures evaluate Persistence rather than the separate deployment rule.
- Proxy peers do not fully control clinical severity. Longer visits do not establish worse care.
- OP-22 refers to 2024. CHIA HFY 2024 utilization and current context do not alter forecasts or ranking.
- Route estimates use approximate coordinates, exclude traffic/parking, and omit missing routes from simulation comparisons.
- Raw archive ZIPs are absent from this checkout. See CLAIMS_AUDIT.md for verification scope.

## Retraining
Add a new CMS archive and run `python national_model.py`. Updates are manual. Run `python scripts/verify_claims.py --refit` to audit saved metrics and Boston interval bounds.
