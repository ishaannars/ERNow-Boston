# When the baseline wins: 321 models vs last year's number

**ERNow Boston** compares Boston emergency departments by how long a typical visit takes, using public
CMS data from 4,438 U.S. hospitals. This is a short write-up of the modeling decisions. Every number here
comes from a file in `data/` and is checked by `scripts/verify_claims.py` and `tests/`.

## The problem

There is no live, public wait-time feed for Boston ERs, and the closest ER is often not the quickest.
CMS publishes each hospital's median emergency visit time (OP-18b), but 9–12 months late. So the real
question is: **can last year's published numbers tell you which ER will be quickest now?**

## The forecast contest

The target is each hospital's next published median. The baseline is **Persistence**: assume it stays
the same as the last published value. Challengers included ridge regression, gradient boosting, partial
pooling toward state and peer averages, and an expanded search of 321 configurations.

The promotion rule was set first: a learned model replaces Persistence only if it is at least **2%**
more accurate on validation **and** does not make local ER choice worse.

- Final test year: Persistence error **9.42 min** (R² **0.931**) on 4,017 hospitals it never saw.
- Best challenger (partial pooling): **1.7%** better on validation, under the bar.
- Expanded search: 4 of 321 configurations beat 2% on error, but each made picking the quickest local
  ER worse, so none passed the joint rule.

**Result: Persistence ships.** Shipping it was the decision the evidence supported, and the
challengers are reported in full.

## Learned models win in turbulent years. Can we switch?

A 7-year rolling backtest showed learned models beating Persistence in the volatile 2020–2023 releases
and losing in the stable years since. So we tested a switch: use the challenger when hospital medians
moved a lot between the two most recent releases, with the threshold learned only from earlier years.

It gained **+0.3%** (95% CI −0.1% to +0.8%). Even a *perfect* year-by-year switch would gain only
**0.8%**. The turbulent-year wins are real but too small to be worth the complexity. Not promoted.

## Honest uncertainty

Each ER gets an 80% range from gradient-boosting quantile regression with conformal calibration that
adapts to recent volatility. It covered **85%** of hospital medians in the final test year, and
**55–97%** across rolling years, so the range is reported as an empirical forecast, not a guarantee.

"Chance it's quickest" comes from 4,000 simulated scenarios. Checked against 9,861 held-out
hospital-years: when it said **88%**, the ER really was quickest **89%** of the time. A correction curve
looked better in-sample but **did not improve unseen years**, so it was dropped.

## Does it help, and for whom?

- **Nationally:** in 340 counties with 3+ EDs, across 7 held-out releases, picking by forecast gave a
  **37-minute** shorter typical visit than picking any ER in the county (95% CI 35–39), and was better
  in **96%** of county-years. This excludes drive time; the Boston analysis includes it.
- **Equity:** no hospital group was flagged (rural Critical Access, government, for-profit, nonprofit,
  smallest to largest EDs). Relative error stayed within 0.94–1.07× of overall, and coverage 77–81%.

## What I'd do next

- Real hospital crowding data (HHS capacity) under the same 2% rule. Respiratory season was tested and
  did not help, even with perfect knowledge of the coming season.
- More people in the decision-time test (currently 5 per group).
- Live data the day hospitals publish it. ERNow is built so it can plug in.
