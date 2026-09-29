# ERNow Boston — ML Emergency Department Forecasting

I built ERNow Boston to make comparing emergency departments faster when people may not have time to search across multiple sources. It turns fragmented hospital, public-health, machine-learning, and routing data into one location-aware forecast so users can compare Boston ER access in seconds.

Hopefully you never need to use it, but I think a resource like this should exist. I plan to keep improving it and would eventually like to incorporate more direct, real hospital operational data if it becomes available.

The system combines:
- **Machine-learning-based throughput forecasting** using historical CMS emergency department data
- **Feature engineering** with lagged values, calendar variables, and rolling historical averages
- **Supervised ML** with Ridge Regression and Random Forest
- **Baseline benchmarking** against a Persistence forecasting model
- **Time-aware validation** using earlier reporting periods for training and later periods for testing
- **Leakage-safe modeling** to prevent future information from entering historical features
- **Multi-source forecasting** using hospital utilization, weather, respiratory illness, major events, and routing data
- **Uncertainty-aware estimates** using bounded wait ranges instead of a single false-precision prediction
- **Location-aware ranking** using both forecasted ER conditions and travel access

## How It Works

`hospital history → feature engineering → model comparison → throughput forecast → current-condition adjustment → route access → ER comparison`

ERNow uses a validated historical model to estimate expected ER flow, then combines that signal with current hospital conditions, public-health context, and travel access.

The ML model is one component of the broader ER estimate. It does not represent a live hospital queue.

## Machine Learning

The historical modeling layer currently uses **36 hospital-period observations across 6 Boston hospitals**, covering CMS reporting periods from **2020–2025**.

Features include:
- hospital identity
- year, month, and quarter
- one-period lag
- two-period lag
- rolling three-period historical average

ERNow compares three forecasting approaches:
- Persistence baseline
- Ridge Regression
- Random Forest

Models are trained on earlier periods and evaluated on later periods rather than randomly mixing historical observations.

Performance is measured using:
- MAE
- RMSE
- R²
- hospital-level MAE

A learned model is only promoted if it improves holdout MAE over the Persistence baseline by at least 2%.

With the current dataset, the Persistence model performs best, so ERNow keeps the simpler model rather than forcing a more complex ML model into production.

## Technical Depth

Feature engineering · lag features · rolling averages · time-aware validation · holdout testing · look-ahead leakage prevention · baseline benchmarking · Ridge Regression · Random Forest · MAE · RMSE · R² · hospital-level error analysis · champion/challenger model selection · uncertainty-aware forecasting · multi-source data integration · contextual forecasting · geospatial routing

## Product Features

- Compare six major Boston emergency departments in one view
- Estimated ER wait ranges
- Location-aware hospital ranking
- Personalized road distance and travel time
- Current hospital demand-condition indicators
- Historical wait-to-provider context
- Typical ER visit-duration context
- Machine-learning-informed ER flow forecasting
- Hospital utilization and occupancy adjustments
- Weather and alert adjustments
- Respiratory illness activity adjustments
- Major Boston event adjustments
- Interactive Forecast Model view with model performance metrics
- Methodology view explaining how the forecast is constructed
- One-click directions to each hospital

## Hospitals

Massachusetts General Hospital · Brigham and Women's Hospital · Brigham and Women's Faulkner Hospital · Beth Israel Deaconess Medical Center · Boston Medical Center · Tufts Medical Center

## Data Sources

CMS hospital data · CDC respiratory illness data · National Weather Service · public event data · OpenStreetMap / OSRM

## Stack

Python · Streamlit · scikit-learn · pandas · NumPy · Requests · CMS · CDC · National Weather Service · OpenStreetMap · OSRM

[Try ERNow Boston](https://ernowboston.streamlit.app/)

> ERNow is an experimental forecasting tool, not a live hospital queue or source of medical advice. If you are experiencing an emergency, call 911 or go to the nearest appropriate emergency department.

© 2026 Ishaan Narasimhan. All rights reserved.
