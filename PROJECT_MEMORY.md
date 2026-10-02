# ERNow Boston — persistent project context

Updated October 2, 2026. This records the user's intent in this repository; it is not an account-wide ChatGPT memory.

## Authoritative value proposition

User's exact updated wording:

> Find the ER that gets you seen and home fastest, not just the closest, lowering the decision time between needing one and finding a good one you can use

The user wants the most defensible predictive accuracy achievable for this data-science project, with additional factors and model combinations when supported by evidence. Accuracy, honest validation, appropriate ER selection, and reduced decision time take precedence over model complexity. The user approved the current UI as perfect: preserve its visual design.

## What is established

The current app ranks estimated road travel plus a forecast of a hospital's published CMS OP-18b median. Four point forecasters compete; one selected model supplies the median. Conformal prediction supplies ranges; OSRM supplies routes. Peers and simulations are contextual. These are hospital-level predictions, not live waits or patient-specific treatment/discharge predictions.

All four final-test models and seven rolling historical folds were refitted from the saved panel. Persistence is selected under the original validation rule: 9.42-minute final-test MAE, R² 0.931. Partial pooling: 9.39-minute test MAE but only 1.7% validation improvement, below the 2% promotion threshold. Final hospital-median interval coverage is 84.7%, rolling coverage 55%–97%. Simulation shares remain uncalibrated. Five recorded ERNow participants had a nine-second decision median; this is not proof of patient outcome benefit.

## Direction

Use ACCURACY_ROADMAP.md as the research and evidence plan. Improve decision-focused ranking, test ensembles with chronological out-of-sample predictions, restore raw source provenance, and acquire appropriate outcomes before claiming individual or live accuracy. Do not fabricate gains, add heuristic time multipliers, average models without validation, or equate predictive hospital medians with clinical suitability. Preserve a reproducible benchmark and prospectively evaluate future releases.

## Completed ensemble experiment

`research/README.md` documents 35 convex combinations of the four base models with chronological weight selection. Five evaluated later folds: blends slightly improved county shortest-median selection but increased MAE (12.38 vs 12.26 min); Boston median MAE improved (16.33 vs 17.63 min), but the assumed-drive grid gave no ranking separation. The joint promotion gate returned Persistence for a future candidate. Production and the UI were kept unchanged. This is retrospective evidence, not proof no ensemble can ever help.

## Expanded search completed

`research/EXPANDED_RESULTS.md` documents 321 candidate configurations, including finer blends, residual stacking, robust losses, recency weighting, continuous pooling and polynomial corrections. Four clear the original 2% MAE-only validation rule (best 2.24% gain); none clears the previously declared research joint gate because validation county regret worsens. Production and UI remain unchanged. Distinguish the original MAE-only production rule from the research ranking safeguards and all-history research nominations from preceding-release validation. Larger generated prediction caches are ignored; rebuild via the research commands.
