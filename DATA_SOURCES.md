# ERNow Boston — sources and periods (Version 27)

See [CLAIMS_AUDIT.md](CLAIMS_AUDIT.md) for verification scope and `data/source_verification.json` for exact primary-source values, workbook hashes, and cell references.

| Data | Source and period | Use and limits |
|---|---|---|
| Median ED visit | [CMS hospital dataset](https://data.cms.gov/provider-data/topics/hospitals), OP-18b; saved Aug 2026 release, Oct 2024–Sep 2025 reporting period | Eight available hospital medians verified against CMS API; forecast hospital medians, not patient stays, first-provider waits, or live queues. Excludes psychiatric/mental-health and transfers. |
| National model | Ten saved CMS snapshots, Oct 2017–Aug 2026 | 4,438 eligible reporting hospitals and 35,164 labeled release pairs. Release chronology is retrospective; periods can overlap. Raw ZIPs absent; final metrics refitted from saved panel. |
| Left before seen | CMS OP-22, calendar 2024 | All eight displayed rates checked against CMS; national median from eligible saved reporting records. Not a personal-risk estimate. |
| Peer matching | CMS hospital characteristics and Complications & Deaths denominators, latest saved release | 25 similar reporting hospitals matched on structural and case-complexity proxies. Does not fully adjust severity or evaluate quality. Raw proxy archives not independently rebuilt in this audit. |
| Utilization | [CHIA HFY 2024 Hospital Profiles](https://www.chiamass.gov/insights-analysis/health-care-settings-providers/hospital-profiles/massachusetts-acute-hospital-profiles/) | All six populated ED-volume and inpatient-occupancy pairs checked against original workbook. Occupancy is inpatient, not ED crowding. Context only. |
| Stays over four hours | [CHIA ED databook](https://www.chiamass.gov/insights-analysis/health-care-settings-providers/emergency-department-database-edd-reporting/), preliminary Sep 2026 publication | Treat-and-release aggregate: 32.95% Oct–Dec 2019 vs 44.06% Jul–Sep 2025; sheet VI-1. Context only. |
| Historical provider wait | CMS OP-20, 2019 or earlier | Legacy CSV values not independently verified against original archive. Explicitly labeled unverified historical context; never used for ranking. |
| ER addresses and services | Official hospital/VA pages; checked Oct 2, 2026 | Ten departments, including specialist, pediatric, and veterans' services. Four corrected ER addresses have approximate Census-geocoded coordinates; other campus coordinates remain approximate. See audit for sources. |
| Hospital affiliation | Official hospital/system pages, CHIA profiles | Optional continuity preference and sorting. Not an insurance-network filter; record sharing varies. |
| Drive time/distance | OpenStreetMap through public OSRM routing server | Cached up to five minutes. No live traffic, parking, ambulance routing, or guaranteed availability. Missing routes are not fabricated and cannot win the comparison. |
| Weather/alerts | National Weather Service observation and point-alert APIs | Latest available observation, which may be delayed. Context only. |
| Respiratory illness | CDC Massachusetts acute respiratory illness category | Latest available published weekly category; not live or hospital-specific. Context only. |
| Events | City of Boston, TD Garden, MLB home schedule, Boston.com RSS, optional Ticketmaster | Detection cached 15 minutes; not exhaustive. Missing sources and no detections are distinct. Context only. |
| Geographic comparison | `boston_choice_analysis.py` | 2,001 sampled points near Boston ERs, including areas outside city boundaries; assumed distance-based driving. Not observed patient trips. |
| Decision times | `data/decision_time_results.csv`, [protocol](TIMING_TEST.md) | Small recorded convenience sample: five ERNow, five nearest-search, one full comparison. Not a controlled trial. |

## Current behavior

Only saved CMS forecasts and road-route estimates determine the estimated time ranking. CHIA, weather, respiratory illness, events, and historical OP-20 are context only. The app does not refresh CMS forecast values automatically; rebuild with `national_model.py` after supplying archives. It has no verified live hospital wait feed.

Hospital-median ranges target 80% empirical coverage, not a guarantee or individual-patient interval. Simulation shares are uncalibrated comparisons of uncertain hospital medians. Data freshness, clinical appropriateness, and personal outcomes remain separate limitations.
