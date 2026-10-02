# ERNow accuracy and value-proposition roadmap

Recorded October 2, 2026. This is a research plan, not a statement that the planned models, data integrations, or patient benefits are already implemented.

## Product objective

> Find the ER that gets you seen and home fastest, not just the closest, lowering the decision time between needing one and finding a good one you can use

This has three distinct outcomes: timely first clinical evaluation, timely departure home, and a faster appropriate choice. Total travel + arrival-to-departure duration already includes the initial wait; do not add arrival-to-clinician time a second time. Model error alone cannot establish all three. An ER may have a shorter first-provider wait but a longer total stay. Define how those trade-offs will be presented and assessed; medical suitability takes priority over predicted speed. Admitted, transferred, and discharged-home visits have different outcomes and must not be pooled into a “home” prediction.

## Current evidence and missing evidence

The app predicts the next published hospital median and adds estimated driving time. Four candidate models and seven historical rolling folds are reproducible from the saved panel. Those tests do not establish individual visit duration, first-provider wait, live hospital conditions, actual trip times, or outcome benefit from choosing a different hospital. The 9-second recorded decision median is from five participants, not a controlled usability study.

CMS OP-18b's hospital aggregate is an eligible discharged-visit arrival-to-departure median. Its definition and exclusions differ from individual first-provider and discharge-home targets. See [CMS hospital dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/hospital/HOSPITAL_Data_Dictionary.pdf). The current source does not supply adequate labels for an hour-by-hour or patient-specific model.

## 1. Align outcomes and evaluation before increasing complexity

Create separate research tracks:

| Track | Prediction/decision target | Required evidence |
|---|---|---|
| Public-data benchmark, available now | Future published hospital median; lowest estimated drive + median among eligible ERs | Date-correct hospital panel and defined local candidate sets |
| Patient-duration research | Arrival to first clinician; arrival to discharge home; admission/transfer separately | Encounter timestamps, disposition, presentation and clinically reviewed eligibility |
| Current-conditions forecast | Site/arrival-time-specific distributions under current demand | Timestamped multi-hospital queue, capacity and outcome histories; validated fresh feeds |
| Decision-time benefit | Time to an appropriate, informed choice | Counterbalanced usability study with measured correctness and comprehension |

Primary benchmark metrics should include **decision regret**: observed total duration at the selected ER minus the minimum observed total among the same eligible choices. Also report shortest-total selection accuracy, pairwise ordering, MAE, median/90th-percentile error, and uncertainty coverage. Report regret for the closest-ER baseline, current forecaster, and each proposed integration on exactly the same candidate sets.

For aggregate public-data tests, regret uses observed hospital medians plus explicitly assumed or archived driving estimates; it is not patient benefit. Actual patient-counterfactual outcomes at unvisited ERs are unobserved. A prospective observational study does not automatically establish that switching hospitals caused shorter visits. Designing an outcome study requires clinical/research collaboration; begin with research or shadow evaluation.

## 2. Strengthen source provenance and chronology

- Recover original CMS archives, record checksums and actual publication dates, and rebuild the panel independently. Record measure definitions, reporting-window start/end, suppression, sample counts where available, hospital identity changes, closures and ER entrances.
- Use one hospital and one explicitly defined forecast horizon per labeled example. Flag missing releases instead of silently calling the next available row a one-release transition. Separate duplicate/overlapping reporting periods; perform sensitivity tests using non-overlapping periods where data permits.
- Distinguish the release being forecast from when its measured care occurred. A future publication can describe outcomes partly or entirely before the prediction date. Require genuinely subsequent outcome windows for claims about future care; report next-publication aggregate prediction separately.
- Train features, imputers, peer groups, scaling and calibrators only from information available at the historical decision date. Never use a post-arrival diagnosis, eventual disposition or future queue size as a pre-arrival predictor.
- Do not match current weather or annual CHIA utilization to historical targets without period-correct archived versions.
- Previous test releases have already been examined repeatedly. New experiments on them are retrospective comparisons; reserve a future release or a genuinely unexamined dataset for confirmation. Freeze the experiment protocol before seeing that confirmation outcome.

## 3. Benchmark combinations against the consumer decision

First run a bounded, reproducible comparison of:

1. Current Persistence and the three existing challengers.
2. Nonnegative convex blends with weights selected only on earlier out-of-sample predictions.
3. Regularized stacking trained on chronological out-of-sample base predictions, not in-sample fits.
4. Hospital/peer partial pooling and robust recency/trend corrections, with shrinkage for sparse hospitals.
5. State/volume-specific or volatility-aware selection only if enough independent historical evidence supports it.

Use nested chronological evaluation: earlier data for candidate fitting, an earlier validation window for weights/settings, and a later outer release for evaluation. Split by release/known availability rather than applying row-based TimeSeriesSplit indiscriminately to an irregular hospital panel. Treat future-forecasting evaluation and unseen-hospital generalization as separate questions. Keep the original model as a baseline, and account for dependence across hospitals, counties, and releases in uncertainty estimates.

[TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) explains chronological splitting and gaps; [StackingRegressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.StackingRegressor.html) warns about fitting the stacker on predictions from models trained on the same data. Explicit time-aware out-of-sample prediction construction is needed here.

Select for better held-out decision regret/ranking with acceptable MAE, calibration, and subgroup performance. Predeclare promotion criteria; do not loosen the existing 2% MAE rule merely to promote a preferred model. If moving from MAE to a decision-focused criterion, record that as a new protocol and evaluate it separately. Do not blend a weaker model simply to increase the model count.

## 4. Add richer features only with matching outcome data

Candidate features: arrival hour/day, holidays, recent arrivals and departures, waiting and boarding counts, staffed treatment spaces, bed availability, acuity, chief-complaint category, age group, arrival mode, respiratory demand, events and traffic. These are research candidates, not established improvements.

For pre-arrival use, only request information realistically available to the consumer. Triage acuity and staffing may require hospital feeds and cannot be assumed known. Clinically review eligibility filtering and any condition-specific advice; the app is not a diagnostic or emergency-triage model. Evaluate error and suitability across service populations, hospitals and relevant presentation groups.

Assess features by period-correct ablation on unseen dates. Prefer validated, recent and directly relevant data to additional weak proxies. Do not use demographic features or precise personal location without a justified modeling purpose and appropriate data handling; collecting sensitive inputs is not automatically necessary.

## 5. Obtain suitable encounter data

- **CHIA Massachusetts case mix:** request appropriate ED encounter data and review its field dictionary, release period, permitted use, date granularity, hospital identification and applicable access conditions. The FY25 submission guide includes registration and discharge times; confirm what the released extract actually retains. Do not assume it contains first-clinician timestamps or live queues. [CHIA access process](https://www.chiamass.gov/requesting-submitting-data/requesting-data-records/request-ma-apcd-case-mix-data/), [submission guide](https://www.chiamass.gov/assets/docs/p/case-mix/FY25-Emergency-Dept-Submission-Guide.pdf).
- **MIMIC-IV-ED:** useful for a clearly labeled BIDMC patient-duration research prototype with credentialing, training and a data-use agreement. It is one hospital, historical rather than live, and does not establish comparative accuracy across Boston. Patient-specific date shifts preserve within-patient order but prevent interpreting concurrent records from different patients as a real queue or joining those shifted dates to real weather/events. Do not assume its admission/departure fields identify time to first clinician. [Official dataset and restrictions](https://physionet.org/content/mimic-iv-ed/2.2/).
- **Hospital partnerships:** timestamped encounter outcomes and operational snapshots across multiple local ERs are needed to validate site-specific current-condition forecasts. A generic live-wait feed without matched outcome history is insufficient for full calibration or suitability claims.

No restricted datasets have been requested or downloaded, and no hospital has been contacted by this plan. Access and institutional collaborations require the user's participation and applicable permissions.

## 6. Calibrate uncertainty and decision rules

Use prediction distributions appropriate to the target and evaluate interval coverage and width across dates, hospitals and service groups. Include correlated changes across nearby hospitals and driving uncertainty in comparative simulations. Validate probability-of-being-shortest with reliability curves and proper scores on future hospital-median targets before showing calibrated probability claims. Patient-level probabilities require patient-level outcome distributions and additional validation.

Add a validated “too close to distinguish” or unavailable-data state when evidence does not support a clear winner. Test whether choosing the nearer suitable ER under a near-tie improves decision robustness. Conformal methods under temporal drift do not guarantee coverage everywhere; monitor coverage degradation explicitly.

## 7. Prove decision-time benefit

Run a preregistered, counterbalanced study using realistic non-emergency scenarios, not people whose urgent treatment could be delayed. Compare ERNow with the nearest-ER search and a full manual comparison. Define timer start/end, cold/warm load, location-permission behavior, correct service eligibility, and what counts as an informed decision. Log pseudonymous participant/run IDs, scenario, device/network category, order, measured time, chosen hospital, task success, understanding of typical-versus-live estimates and confidence. Avoid collecting raw personal addresses when synthetic scenarios suffice.

Choose sample size from a pilot/power analysis rather than an arbitrary participant target. Report median and tail decision times, paired differences with uncertainty, eligibility errors and understanding. Faster incorrect choices do not support the value proposition. Keep the original recorded five-person timings distinct from the new study.

## 8. Maintain future accuracy

Run new candidates in shadow mode, store immutable forecast timestamps and feature-availability timestamps, then score outcomes when they arrive. Monitor ranking regret, MAE, coverage, input freshness, missing routes and service changes; retain a reproducible rollback model. Track data-source continuity: CMS's CY2026 final rule schedules removal of the discharged-patient ED median and left-without-being-seen measures beginning with the CY2028 reporting period/CY2030 payment determination. This is a reason to establish other validated sources, not a claim that today's measures are already unavailable. [CMS final rule](https://www.cms.gov/newsroom/fact-sheets/calendar-year-2026-hospital-outpatient-prospective-payment-system-opps-ambulatory-surgical-center).

## Immediate next deliverables

1. Raw-source reconstruction and a versioned, availability-aware panel.
2. A separate decision-focused ensemble benchmark that does not alter consumer forecasts until evaluated.
3. A documented data-access feasibility assessment for CHIA and multi-hospital encounter outcomes.
4. A stronger decision-time study protocol and measurement schema.
5. Promote only verified gains; retain honest hospital-level claims until new targets are validated.

The current production model is not changed by this roadmap. No ensemble improvement, live-patient prediction, or clinical benefit has yet been demonstrated.
