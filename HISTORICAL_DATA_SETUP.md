# ERNow Historical CMS Implementation

## Dataset found

Use the **CMS Hospital Compare / Provider Data Catalog hospital archives**.

The target used here is:

**CMS OP-18b — Median Time from Emergency Department Arrival to Departure for Discharged Emergency Department Patients.**

This is a real hospital-level historical outcome measure and is updated quarterly by CMS. It is **throughput duration**, not a live wait-to-provider measurement. OP-18b excludes psychiatric/mental-health and transferred visits.

NBER also republishes historical Hospital Compare snapshots and lists `Timely_and_Effective_Care-Hospital` files for years back to 2016.

## Legacy pipeline setup

1. Download several Hospital archive ZIPs from:
   - CMS Hospitals archive: https://data.cms.gov/provider-data/archived-data/hospitals
   - or NBER Hospital Compare archive: https://www.nber.org/research/data/centers-medicare-medicaid-services-cms-hospital-compare-data

2. Put the ZIP files in:
   `data/cms_archives/`

3. Run:
   `python cms_history_pipeline.py`

4. It creates:
   `data/cms_op18b_history.csv`

5. This builds the legacy historical dataset; it does not update the current app forecasts. Run the national pipeline below to update current outputs.

## What the model does

For each hospital/reporting period it predicts OP-18b using:
- hospital identity
- year/month/quarter
- prior OP-18b value
- two-period lag
- leakage-safe rolling historical mean

Models:
- persistence baseline
- Ridge regression
- Random Forest

Validation:
- chronological train/test split
- MAE
- RMSE
- R²
- hospital-level MAE

This is intentionally different from claiming live ER wait prediction.

## National model (current)

The app's forecast now comes from `national_model.py`, which reads every hospital in the archives (rather than only Boston). After adding archives to `data/cms_archives/`, run:

```
python national_model.py
```

It writes `data/national_results.json`, `data/boston_forecast.csv`, and `data/national_ed_panel.csv.gz`. The archive zips themselves stay out of git.
