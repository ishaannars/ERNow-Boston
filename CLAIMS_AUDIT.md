# Version 27 claims audit

Checked October 2, 2026. This distinguishes primary-source checks from reproduction of saved outputs.

## Verified against primary sources

- **CMS hospital values:** all eight forecast hospitals' OP-18b and OP-22 values match the official [CMS hospital dataset API](https://data.cms.gov/provider-data/api/1/datastore/query/yv7e-xc69/0). OP-18b covers Oct 2024–Sep 2025; OP-22 covers calendar 2024. Exact values and periods are in `data/source_verification.json`. The app uses saved values, not a live queue feed.
- **Measure meaning:** [CMS's hospital dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/hospital/HOSPITAL_Data_Dictionary.pdf) defines OP-18b as hospital-level median arrival-to-departure duration for eligible discharged visits, excluding psychiatric/mental-health and transferred visits. It is not time to first clinician or an individual patient's predicted duration.
- **CHIA utilization:** all six populated HFY 2024 ED-volume and inpatient-occupancy pairs match the [Hospital Profiles workbook](https://www.chiamass.gov/wp-content/uploads/docs/r/hospital-profiles/2024/FY24-Massachusetts-Hospital-Profiles-Databook.xlsx). Inpatient occupancy is not ED occupancy. Workbook SHA-256 and exact cells are saved in `data/source_verification.json`.
- **Massachusetts stays over four hours:** the [preliminary CHIA ED databook](https://www.chiamass.gov/wp-content/uploads/cmsr-edd-quarterly-databook-10-01-2019-to-3-31-2026.xlsx), sheet VI-1, gives 366,726 / 1,113,098 = **32.95%** in Oct–Dec 2019 and 505,988 / 1,148,382 = **44.06%** in Jul–Sep 2025. Counts were aggregated over hospital cohorts. The earlier Jul–Sep 2019 label was incorrect and is corrected.
- **ER locations and services:** official hospital pages confirm the ten listed departments; [Massachusetts DPH](https://www.mass.gov/resources-for-patients-and-employees-of-carney-hospital-and-nashoba-valley-medical-center) confirms Carney's Aug 31, 2024 closure. Corrected ER addresses: [BMC–Brighton](https://www.bmchealthsystem.org/bmc-brighton/patients-visitors/directions), 255 Washington St; [BMC](https://www.bmc.org/departments/emergency-medicine), 725 Albany St; [Tufts](https://www.tuftsmedicine.org/get-care/our-locations/about-tufts-medical-center/frequently-asked-questions), 860 Washington St; [BIDMC](https://bidmc.org/locations/beth-israel-deaconess-medical-center), 1 Deaconess Rd. Census address coordinates approximate these locations; other campus coordinates remain approximate. Directions use the street address.
- **Emergency care and insurance:** wording follows [CMS emergency-room rights](https://www.cms.gov/priorities/your-patient-rights/emergency-room-rights) and [CMS billing rights](https://www.cms.gov/initiatives/your-patient-rights/medical-bill-rights/know-your-medical-bill-rights). Screening/stabilization protections do not mean every service is free, every plan is covered, or a hospital system is an insurance network.

## Reproduced from saved project data

`python scripts/verify_claims.py --refit` reproduces panel counts, Persistence errors and R², county rankings, promotion choice, reporting lag, latest Boston medians/OP-22, interval containment, OP-18b/OP-22 correlation, and timing medians. It refits all four candidate models and the interval model, verifying final-test coverage/width, all three bootstrap confidence intervals, and all eight deployed interval bounds.

- **4,438 eligible hospitals; 35,164 labeled release pairs; 4,017 final-test hospitals.** The latest saved panel has 4,658 listed records and 4,081 available OP-18b values. These are reporting hospitals, not every U.S. hospital.
- **Persistence:** MAE 9.4215 minutes, R² 0.93105; county shortest-median accuracy 82.94% across 293 counties versus 24.04% mean random baseline. Driving and patient outcomes are excluded.
- **Ranges:** final-test hospital-median coverage 84.74%, median width 34.14 minutes. Rolling coverage varies 55%–97%; there is no guaranteed 80% coverage for a hospital or year.
- **Boston test:** seven general EDs, MAE 17.9 minutes, rank correlation 1.00. This is one saved release and a small local sample.
- **Timing CSV:** ERNow median 9 seconds (5 participants), nearest-search median 20 seconds (5), full manual comparison 381 seconds (1). These are recorded convenience-sample results, without timestamps or starting locations, not an independently observed controlled trial.
- **Geographic calculation:** rerunning `boston_choice_analysis.py` after address corrections gives 2,001 grid points, 83.41% closest/lowest-total disagreement, median estimated difference 98.34 minutes, extra driving 13.39 minutes. Sensitivity spans 75.36%–83.41%. The grid extends outside Boston city boundaries. Travel is assumed from distance, not measured trips or live traffic.

## Claims corrected or qualified

- “Gets you seen/home fastest” is replaced by comparisons of estimated drive plus hospital medians. Clinical appropriateness and individual outcomes are not evaluated.
- “Chance fastest” is labeled **Fastest in simulation**: 4,000 independent lognormal scenarios of uncertain hospital medians, with approximate spreads. Percentages are uncalibrated and exclude missing routes; they are not individual-patient probabilities.
- “Last year's value” becomes latest reported value. Chronology is by release; reporting windows can overlap and are already historical when published. Two early next-available-release transitions skip a snapshot. The final test has no skipped transition. This is retrospective release-based validation.
- The rolling ranking column measures **Persistence**, independently of the selected model column. The best challenger in each scored fold is a retrospective comparison, not a prospective selection.
- Hospital-level associations and feature importance are not causes or quality-of-care scores. Peer matching uses public proxies, not complete clinical severity adjustment.
- Context feeds do not alter forecasts. Unavailable weather/illness are labeled; event checks may fail or miss events, so “no events detected” does not prove none exist. Road estimates omit traffic, parking, and ambulance conditions.
- Hospital affiliation may help continuity, but record sharing and insurance coverage vary. VA eligibility and pediatric age policies vary.

## Remaining limits

Original national CMS archive ZIPs are absent from this checkout. The whole panel, case-complexity proxies, original archive transforms, and every rolling fold have not been independently rebuilt from original archives. The final-model refits, final interval metrics, and all three displayed bootstrap confidence intervals were independently reproduced from the saved panel. Rolling tables remain saved model outputs rather than a fresh full rolling refit.

The older OP-20 values (2019 or earlier) have not been independently matched to source archives. They remain explicitly labeled historical and unverified, appear only as context, and do not affect ranking.

No verified live hospital queue, patient-level outcomes, prospective clinical trial, calibrated simulation shares, or exhaustive event inventory is available. UI checks in this environment validate Streamlit execution and generated markup; browser screenshots are unavailable, so pixel-level alignment and deployment rendering require a live browser check.
