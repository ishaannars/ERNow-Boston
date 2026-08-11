# ERFlow Boston — Publication Build

ERFlow Boston is a consumer-facing emergency-department access forecasting prototype. The consumer provides only a location. ERFlow then compares six Boston emergency departments using a zero-cost estimated travel time, current/fresh public demand signals, recent CMS ED-throughput data, and legacy CMS wait-to-provider benchmarks.

## Consumer flow

1. Emergency safety warning appears first.
2. User taps **Get My Location**.
3. ERFlow automatically refreshes all available current signals.
4. Hospitals are ranked by **modeled time until initial evaluation = estimated travel time + modeled wait to first provider evaluation**.
5. The closest ER is always surfaced separately as a safety reference.
6. A separate Methodology & Data Sources page explains all sources, freshness, assumptions, and limitations.

## What every hospital card shows

- modeled wait-to-provider range
- estimated travel time and distance
- current relative wait pressure
- 2019 historical wait-to-provider benchmark (CMS-derived OP-20)
- latest available historical ED duration (CMS OP-18b)

## Dynamic inputs

- **Travel estimate:** recalculated from the user’s location, straight-line distance, and the current Boston hour/day. It is intentionally not labeled as live traffic.
- **Weather:** latest NWS observation and active alerts; refreshed frequently (10-minute observation cache / 5-minute alert cache).
- **Time/day/holiday:** computed immediately from Boston local time.
- **Respiratory illness:** latest CDC Massachusetts ARI level. This source is updated weekly and is intentionally labeled "latest weekly," not live.
- **Events:** current City of Boston event feed, with optional Ticketmaster Discovery API coverage for broader major-event detection.

## Historical inputs

- **CMS OP-18b:** latest available public arrival-to-departure ED duration baseline.
- **Legacy CMS OP-20:** 2019 arrival-to-provider historical benchmark for the six hospitals. It is never presented as a current wait time.

## Ranking model

The publication build no longer uses an arbitrary 60/30/10 normalized score. It ranks directly in minutes:

`modeled access time = estimated travel time + modeled wait to provider`

The modeled wait starts with the hospital's historical OP-20 wait benchmark, receives a small hospital-specific recalibration from its latest relative CMS OP-18b throughput, and then bounded adjustments from current time/day/holiday, NWS weather, CDC respiratory activity, and high-impact event signals.

The output is intentionally shown as a wide range because ERFlow cannot observe live waiting-room census, triage severity, staffing, open treatment rooms, boarding, or ambulance arrivals.

## Optional secret

ERFlow works without paid API credentials. The only optional secret is for broader event coverage:

```toml
TICKETMASTER_API_KEY = "your-ticketmaster-discovery-api-key"
```

The app still runs without it using the City of Boston event feed. Never commit real keys to GitHub.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Portfolio framing

**ERFlow Boston — Emergency Department Access Forecasting Platform | Python, Pandas, Streamlit, REST APIs**

Built and deployed a location-first healthcare analytics application that compares Boston emergency departments using estimated travel calculation, current weather, temporal/calendar signals, public respiratory surveillance, local events, CMS ED-throughput metrics, and archived wait-to-provider benchmarks; designed transparent uncertainty ranges, data-freshness labeling, and emergency-routing safety guardrails.

## Important disclaimer

ERFlow is a portfolio forecasting prototype, not a clinical decision tool and not a confirmed live hospital wait-time service. For a possible medical emergency, call 911 or seek the nearest appropriate emergency care rather than driving farther based on ERFlow rankings.
