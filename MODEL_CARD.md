# ERNow Boston — Model Card

## Objective
ERNow's supervised-learning layer is designed to predict emergency-department wait-to-provider time from historical hospital and contextual observations. The consumer app continues to use a transparent bounded forecasting model until a validated labeled historical dataset is large enough for out-of-time model evaluation.

## Target
`observed_wait_min` — an observed wait-to-provider value tied to a hospital and timestamp.

## Candidate features
- Hospital identity
- CMS ED throughput / visit-duration measures
- Recent reported ED volume and occupancy
- Left-before-being-seen rate when available
- Hour, day of week, month, weekend, and holiday indicators
- Weather conditions and severe-weather indicators
- Massachusetts respiratory-illness surveillance category
- Major-event indicators

Route time is intentionally excluded from the wait target model. It is combined with the wait estimate later when ERNow ranks access from the user's location.

## Models compared
- Median baseline
- Linear regression
- Ridge regression
- Random Forest regression

## Evaluation
The pipeline sorts observations by time and holds out the newest portion of the dataset. This reduces leakage from future observations into training. Reported metrics are:

- MAE (minutes)
- RMSE (minutes)
- R²

Model selection is based on holdout error, not training fit.

## Interpretability
For models that expose coefficients or feature importance, ERNow surfaces the largest drivers in the Model Lab. Importance is descriptive of the fitted model and does not establish causation.

## Current limitation
The repository does not fabricate historical wait observations. If `data/ernow_historical.csv` is absent or too small, the Model Lab reports that supervised training is not yet ready and does not display invented accuracy metrics.

## Promotion rule
A learned model should only replace the current bounded forecast after it:

1. Uses validated historical targets.
2. Beats a simple baseline on chronological holdout data.
3. Is stable across hospitals and time periods.
4. Does not rely on leakage-prone features.
5. Preserves the app's safety and uncertainty language.
