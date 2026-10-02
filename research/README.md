# Chronological ensemble experiment

Completed October 2, 2026. Production forecasts and the Streamlit UI were not changed.

## Question and decision

Can combinations of ERNow's existing point forecasters improve hospital-time prediction and local ER selection?

**Decision: retain the current consumer model.** The tested blend-selection strategy slightly improved aggregate county decisions, worsened time-prediction error, and showed no Boston shortest-total ranking advantage under the stated driving assumptions. Using all historical folds to nominate a future candidate returned 100% Persistence under the predeclared joint gate. No future improvement is claimed.

This experiment tests 35 convex combinations, not every possible ensemble or a proof of globally optimal accuracy. Finer weights, stacking, richer data and different objectives remain separate experiments. The original 2% validation-MAE improvement rule was retained and supplemented by better county regret and non-worsening tie-aware shortest-median accuracy. It was not relaxed after looking at results.

## Design

- Refit all four base models across seven rolling releases (2020–2026), using only earlier labeled releases for each fit.
- Generate and save out-of-time predictions. Convex weights are 0%, 25%, 50%, 75% or 100%, sum to 100%, and are nonnegative: 35 combinations.
- Use the first two releases as weight-selection burn-in. For each subsequent release, select weights using only earlier folds, then evaluate on that later release: five evaluation folds.
- Select eligible weights by lowest mean county decision regret, then MAE. County regret is the selected hospital's observed median minus the shortest observed median in that county. Counties need at least three eligible reporting hospitals. Tied observed minima count as correct here, unlike the older strict-index selection metric.
- Average metrics equally across releases. Historical figures therefore differ from the existing single-final-release accuracy figures and must not replace those labels.
- The earlier historical releases have already been studied during project development. These are retrospective evaluations, not a new untouched test or a prospective clinical study.

## Results across five chronological evaluation folds

| Metric | Persistence | Prior-fold-selected blends |
|---|---:|---:|
| Hospital-median MAE | 12.26 min | 12.38 min |
| Mean county decision regret | 3.34 min | 2.99 min |
| Shortest county median selected, accepting ties | 76.36% | 77.30% |

The MAE increase is approximately 1.03%. Mean county regret fell by approximately 0.34 minutes; shortest-median accuracy increased by approximately 0.94 percentage points. These county metrics exclude driving and clinical suitability. The gains are not minutes saved by actual patients.

A paired county bootstrap within releases gives a conditional regret-improvement interval of approximately 0.05–0.64 minutes. It holds releases and the chosen models fixed; it does not account for all model-search uncertainty, correlated changes across counties, or uncertainty in future releases. It cannot establish general future superiority.

## Boston total-time proxy

We also evaluated all five later folds over the same 2,001 sampled points near the current seven general ERs, using observed hospital medians plus assumed driving: straight-line distance × 1.35, 18 mph, plus 3 minutes. Both Persistence and the chosen blends selected the shortest modeled total at all points in these folds.

Boston hospital-median MAE did improve: **16.33 minutes for blends versus 17.63 for Persistence**, averaged over these five releases. This is promising local evidence from seven hospitals; it was not used to select weights or to redefine the promotion gate after seeing outcomes. It does not resolve the national error trade-off or establish prospective superiority.

This test provides **no ranking separation**: one hospital's large median advantage dominates the driving differences within this grid. It does not demonstrate 100% patient accuracy, clinical appropriateness, actual traffic accuracy, or the performance of either method on a different geographic domain. Current hospital IDs and coordinates are applied retrospectively; historical service eligibility and address changes were not reconstructed.

Per-release results, Boston median errors and assumptions are in `data/ensemble_benchmark.json`.

## Reproduce and verify

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python research/ensemble_benchmark.py
# Repeat weight evaluation without refitting base models; hashes must match:
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python research/ensemble_benchmark.py --reuse
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python research/verify_ensemble_benchmark.py
```

The OOF cache and manifest record saved-panel, base-model-code and prediction-cache hashes. Verification checks all seven source target alignments, base-model errors against prior rolling results, chronological weight selection, finite/convex weights, regret and tied-minimum semantics, and Boston grid coverage.

The benchmark is separate from `national_model.py` and writes only research artifacts. `app.py`, `styles.css`, `.streamlit/config.toml`, `data/boston_forecast.csv` and `data/national_results.json` remain unchanged.
