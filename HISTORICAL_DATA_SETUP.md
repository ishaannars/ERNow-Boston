# ERNow Historical CMS Implementation

## Dataset found

Use the **CMS Hospital Compare / Provider Data Catalog hospital archives**.

The target used here is:

**CMS OP-18b — Median Time from Emergency Department Arrival to Departure for Discharged Emergency Department Patients.**

This is a real hospital-level historical outcome measure and is updated quarterly by CMS. It is **throughput duration**, not a live wait-to-provider measurement.

NBER also republishes historical Hospital Compare snapshots and lists `Timely_and_Effective_Care-Hospital` files for years back to 2016.

## Fastest setup

1. Download several Hospital archive ZIPs from:
   - CMS Hospitals archive: https://data.cms.gov/provider-data/archived-data/hospitals
   - or NBER Hospital Compare archive: https://www.nber.org/research/data/centers-medicare-medicaid-services-cms-hospital-compare-data

2. Put the ZIP files in:
   `data/cms_archives/`

3. Run:
   `python cms_history_pipeline.py`

4. It creates:
   `data/cms_op18b_history.csv`

5. Relaunch Streamlit. Model Lab automatically detects the historical dataset and switches to real chronological validation.

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
