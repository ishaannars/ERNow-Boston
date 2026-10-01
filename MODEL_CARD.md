# ERNow Boston — Model Card

## Purpose
For urgent, non-life-threatening visits, help people find the Boston ER likely to get them seen and home fastest, not just the closest, in about 15 seconds, by forecasting each hospital's typical ED visit time for the next CMS period with a tested range. This works without live data because ED performance is highly persistent year to year (R² 0.93). Not a live queue and not medical advice.

## Target
Next-release CMS **OP-18b**: median minutes from ED arrival to departure for discharged patients, per hospital.

## Data
Six CMS Hospital Compare releases (2021-10 to 2026-08), every U.S. hospital: 4,246 hospitals and 19,884 labeled hospital-periods. Inputs come only from releases available before the period being predicted.

## Features
Last and prior OP-18b, most recent change, psychiatric-patient ED time (OP-18c), left without being seen (OP-22), ED volume category, CMS star rating, hospital type, ownership, state, gap to state average, gap to peer (volume × type) average. OP-18a and OP-18d appear only in the newest release and are excluded.

## Models compared
Persistence baseline · Ridge regression (on the change) · robust partial pooling (shrinkage toward state and peer averages, least-absolute-error fit) · gradient boosting (on the change).

## Validation
Chronological: train on releases 1–3 → next, select on release 4 → 5, test once on release 5 → 6 (4,017 hospitals). Promotion rule: a learned model must beat Persistence MAE by 2% on validation.

## Results (test release)
- Persistence: MAE 9.4 min, R² 0.931 (selected). Best challenger (partial pooling): 1.6% better on validation, below the bar.
- 80% ranges (regime-adaptive conformalized quantile regression): 83% coverage on an earlier held-out year and 85% on the final test year (static conformal: 88%), median width 34 min (old fixed band: 134 min).
- Ranking: rank correlation 0.97 nationally, 0.86 within counties; fastest ER picked correctly 83% of the time vs 24% by chance.

- Confidence (bootstrap, 2,000 resamples): fastest-pick 95% CI 78–87%; coverage 95% CI 83–86%; best challenger's edge ~8 seconds per hospital (statistically real, practically negligible).

## Intended use and limits
- Describes typical ED performance for a period, published 9–12 months after it ends; it cannot see today's queue, triage, staffing, or boarding.
- OP-18b covers discharged patients only; academic and trauma centers treat sicker patients and run longer for reasons that do not mean worse care.
- Peer comparisons adjust for case complexity with public proxies (heart-attack and stroke patient volume, cardiac-surgery capability, inpatient volume), not each patient's severity.
- The cards show CMS OP-22 (left before being seen, 2024) as a crowding signal. CMS OP-20 provider wait (2019 or earlier) appears only as context on the Forecast Model page. No hand-set adjustment changes any displayed number.

## Retraining
Add a new CMS release archive to `data/cms_archives/` and run `python national_model.py`. The app reads the regenerated results.
