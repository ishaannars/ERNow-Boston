# When the baseline wins: 321 models vs last year's number

ERNow compares Boston ERs by how long a typical visit takes. It uses public CMS data from 4,438 U.S. hospitals. Every number here comes from a file in `data/` and is checked by `scripts/verify_claims.py` and the tests.

## The problem

Comparing Boston ERs today means checking several sources by hand, and the closest ER is often not the quickest. CMS publishes each hospital's median ED visit time (OP-18b), but about 9–12 months late. So the question was simple. Can last year's numbers tell you which ER will be quickest now?

## The contest

The baseline is Persistence, which assumes each hospital's next number equals its last one. I tested ridge regression, gradient boosting, partial pooling, and an expanded search of 321 configurations. Before testing, I set one rule. A model replaces Persistence only if it is at least 2% more accurate on validation and does not make local ER choice worse.

- Persistence had a **9.42-minute** error (R² **0.931**) on 4,017 hospitals in the final test year.
- The best challenger was **1.7%** better on validation, which is under the bar.
- In the expanded search, 4 of 321 configurations beat 2% on error. Each one made picking the quickest local ER worse, so none passed.

Persistence ships. I report every challenger in full.

## Switching models in turbulent years

Learned models beat Persistence in the volatile 2020–2023 releases and lost in the calmer years after. So I tested a switch that uses the challenger when ED times moved a lot in the latest release. The switch gained **+0.3%** (95% CI −0.1% to +0.8%). Even a perfect year-by-year switch would gain only **0.8%**. Not promoted.

## Extra factors

I tested respiratory season (CDC FluView) and hospital crowding (CDC NHSN statewide and HHS per hospital). Crowding was the strongest. It cut the gradient-boosting model's error by **6%**, but that only brought it level with Persistence. It also made the ranges **2.3%** less accurate. Respiratory season did not help even with perfect knowledge of the coming season.

## Honest ranges

Each ER gets an 80% range from gradient-boosting quantile regression with conformal calibration. It covered **85%** of hospital medians in the final test year and **55–97%** across rolling years. "Chance it's quickest" comes from 4,000 simulated trips. When it said **88%**, that ER was quickest **89%** of the time across 9,861 held-out hospital-years. A correction curve looked better in-sample but did not help on unseen years, so I dropped it.

## Does it help, and for whom?

- Across 340 counties with 3+ EDs and 7 held-out releases, picking by forecast meant a **37-minute** shorter typical visit than picking any ER in the county (95% CI 35–39). This leaves out drive time. The Boston analysis includes it.
- No hospital group was flagged in the equity audit (rural, government, for-profit, nonprofit, and every ED size). Error stayed within 0.94–1.07× of overall.

## What I'd do next

- Test extreme weather days and community factors under the same 2% rule.
- Get more people into the decision-time test (currently 5 per group).
- Plug in live hospital data when hospitals publish it.
