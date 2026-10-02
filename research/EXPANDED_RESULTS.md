# Expanded accuracy search — results and promotion decision

Completed October 2, 2026. The approved UI, current model outputs, and production model code are unchanged.

## Result

**Four candidates clear the original 2% validation-MAE gate. None clears the decision-focused joint gate.** The best validation error is 11.540 minutes versus 11.805 for Persistence, a 2.24% improvement, but its county decision regret worsens from 3.402 to 3.804 minutes. It would give slightly closer time estimates while making worse local shortest-median choices in validation.

The original `national_model.py` promotion rule is MAE-only. The research benchmark adds the previously declared decision safeguards: county regret must improve and tie-aware shortest-median accuracy must not worsen. Those safeguards were kept unchanged. Clearing the MAE-only rule does not establish the fuller consumer-ranking benefit.

| Candidate | Validation MAE | Gain over Persistence | Validation county regret | Shortest county median, ties accepted | Later-release MAE |
|---|---:|---:|---:|---:|---:|
| Persistence | 11.805 min | — | 3.402 min | 76.35% | 9.421 min |
| Continuous pooling | 11.540 min | 2.24% | 3.804 min | 76.01% | 9.276 min |
| Recency-weighted continuous pooling | 11.541 min | 2.24% | 3.632 min | 76.35% | 9.259 min |
| 30% Persistence / 70% original pooling | 11.563 min | 2.04% | 3.720 min | 76.01% | 9.286 min |
| 40% Persistence / 60% original pooling | 11.568 min | 2.00% | 3.632 min | 76.35% | 9.270 min |

The original pooling model used a discrete coefficient grid. Continuous variants optimize the same bounded structural/trend corrections under absolute error; the recency variant weights earlier releases with a two-release half-life. They use historical training labels only. Optimizer convergence is checked. Duration estimates in these additional variants are floored at one minute.

All four candidates also have slightly worse county regret than Persistence in the already examined later release. None is promoted. No forecast values or model-selection rules in the consumer app were changed.

## What was tested

**321 candidate configurations**, including pure-model endpoints that duplicate existing candidates:

- The four existing base models.
- Twenty additional variants: Ridge strengths, recency weighting, Huber history corrections, history/full boosting under squared/absolute loss with different leaf counts, and six robust offset/trend corrections.
- 286 convex combinations of the original four models at 10-percentage-point increments.
- Three regularized residual-stacking models trained on earlier out-of-time base predictions. During the first two burn-in folds they explicitly fall back to Persistence, since the stacker lacks adequate earlier OOF history.
- Eight further variants: continuous bounded pooling with/without a learned offset and recency weighting, full-feature Huber corrections, and regularized second-order structural/trend corrections.

This is a bounded search, not an exhaustive search over all models, data sources, features, or real-valued weights. More configurations do not imply a more accurate system.

## Validation design

All base variants are refitted on releases earlier than each evaluated release. Blend selection and stacking use only earlier out-of-time predictions. The historical panel remains retrospective, has overlapping reporting windows, and does not measure individual treatment/discharge times.

Two evaluations are deliberately separate:

1. **Rolling algorithm evaluation:** seven historical OOF folds, first two for burn-in and five subsequent evaluation folds. The expanded 313-configuration stage selected finer blends, but its average MAE was essentially unchanged: 12.259 vs 12.258 minutes for Persistence. County regret improved to 3.033 vs 3.337 minutes, and tie-aware shortest selection to 77.23% vs 76.36%. These are five-fold means, not the single-final-release results.
2. **Current production-date gate audit:** configurations are judged on the preceding Nov 2025 release, with Aug 2026 results reported separately. The current original threshold is 2% lower MAE; the research joint gate additionally requires better regret and non-worsening shortest selection. Four pass MAE-only and zero pass the joint gate.

The 313-configuration stage also nominates a 40%/20%/20%/20% blend when all seven historical folds are used as training evidence. That is a future research nomination, not a new unseen test or the winner of the current preceding-release validation. It must not be confused with production promotion.

The already examined releases were reused in expanding this search. Even a candidate that clears retrospective gates would need fresh confirmation; these figures do not prove future superiority. Scores accepting tied minima differ from the older strict-index selection metric used in production documentation.

## Limits

County ranking excludes driving and clinical suitability. Boston grid checks use assumed distance-based driving and current hospital identifiers/coordinates, not measured trips or reconstructed historical eligibility. A small error improvement in published medians is not evidence of shorter personal treatment or discharge time.

Broad search increases selection uncertainty. No threshold was lowered, no new factor was assigned an unvalidated time multiplier, and no best-fit training score was presented as a held-out result. Some old aggressive trend stress candidates yield negative durations; they perform poorly and are not selected or deployed. Future promotion must also validate physical output bounds, intervals, service eligibility and data freshness.

## Reproduce

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python research/expanded_search.py
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python research/final_accuracy_search.py
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python research/verify_expanded_search.py
```

The larger prediction caches are generated locally and ignored by Git; rebuild them with the first two commands before verification. Smaller result JSONs, code, source hashes and library versions are committed. Cache hashes change with regeneration; result JSONs written in the same run track the generated files. Small numerical differences between platforms are possible.

Verification checks source-target/cache alignment, all 321 validation and later-release scores, both gates, chronological selection, and the unchanged production decision. The existing consumer code, styling, saved forecasts and national results are also checked for zero diffs.

## What would justify another promotion attempt

The next useful steps are an independently rebuilt, availability-aware panel with more distinct reporting periods, genuinely new confirmation outcomes, and appropriate local encounter data for the eventual patient-level target. Further model experiments remain possible; this run does not show that no model can improve. It shows that the tested candidates do not yet improve both accuracy and the local decision under the retained criteria.
