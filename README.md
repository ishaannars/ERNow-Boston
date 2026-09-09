# ERNow Boston

ERNow Boston is a location-based emergency department comparison tool built to help users understand which nearby Boston ERs may offer the best combination of **estimated wait time and route access**.

The app does not claim to provide live hospital queue times. Instead, it combines historical hospital performance with current public signals such as weather, time of day, illness activity, local events, and recent hospital demand to produce a transparent estimate.

## What the app does

A user shares their location, and ERNow:

1. Finds the six Boston emergency departments included in the project
2. Estimates route time and distance from the user
3. Estimates ER wait as a range
4. Factors in current local demand conditions
5. Ranks hospitals using wait, access, and other relevant signals
6. Always shows the closest ER separately as a safety reference

## What each hospital card shows

Each hospital card includes:

- **Estimated ER wait**
- **Estimated route time and distance**
- **Current demand conditions**
- **Historical wait**
- **Typical visit duration**

The goal is to keep the main experience simple while still giving enough context to understand why one hospital may rank above another.

## How the estimate works

ERNow uses a mix of historical hospital data and current contextual data.

Historical and hospital-specific inputs include:

- historical wait-to-provider performance
- recent ER visit duration
- recent reported ED demand
- hospital throughput and utilization measures

Current inputs include:

- time of day
- day of week
- holidays
- weather conditions
- respiratory illness activity
- major Boston events
- route access from the user’s location

Recent hospital demand is used inside the model but is not shown as a separate consumer-facing score.

## Current vs. historical data

Some inputs change frequently, while others come from the latest available public reporting period.

Examples of frequently changing inputs:

- current time and day
- weather
- local events
- route estimate

Examples of periodically updated inputs:

- respiratory illness activity
- hospital ED demand
- hospital throughput
- ER visit duration

Historical wait data is used as a hospital-specific reference point when more recent standardized wait-to-provider data is not publicly available.

## Typical visit duration

The “Typical visit duration” shown on each hospital card is based on the CMS measure:

**OP-18b — Median Time from Emergency Department Arrival to Departure for Discharged Emergency Department Patients**

This is not the same as wait time. It represents the typical total time a discharged patient spends in the emergency department from arrival to departure.

ERNow uses this as a hospital throughput signal alongside other inputs.

## Travel estimate

Route access is estimated from the user’s location.

Distance depends entirely on where the user is located and is not something ERNow can control.

Route time is shown as an estimate and should not be interpreted as live traffic unless a live traffic source is added in a future version.

## Limitations

ERNow does not have access to:

- live waiting-room counts
- triage severity
- real-time staffing
- open treatment rooms
- boarding levels
- live ambulance arrivals

Because of this, ERNow provides estimates rather than confirmed live hospital wait times.

For a possible medical emergency, users should call 911 or seek the nearest appropriate emergency care rather than delaying care based on ERNow rankings.

## Data sources

The project uses public data from sources including:

- Centers for Medicare & Medicaid Services (CMS)
- Massachusetts hospital and capacity reporting
- National Weather Service
- Centers for Disease Control and Prevention
- City of Boston public event data

See `DATA_SOURCES.md` and the in-app **Methodology** page for more detail on each source and how it is used.

pip install -r requirements.txt
streamlit run app.py
