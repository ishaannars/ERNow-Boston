# ERNow Boston

**Live app:** https://ernowboston.streamlit.app/

ERNow Boston is a location-based healthcare forecasting app that ranks six Boston emergency departments using **estimated ER wait time and travel access**.

It combines public hospital data with current contextual signals such as weather, seasonal respiratory illness, major local events, time of day, and road routing. ERNow does **not** claim to provide live hospital queue times.

## What it does

Users share their location and ERNow:

1. Estimates road-route time and distance to six Boston ERs
2. Estimates an ER wait range for each hospital
3. Uses hospital throughput and recent utilization data
4. Adjusts for weather, time, illness, holidays, and major events
5. Ranks hospitals using estimated wait and route access

## What each result shows

- Estimated ER wait
- Estimated route time and distance
- Current demand conditions
- Historical wait
- Typical visit duration

## Key data sources

- CMS hospital data
- Massachusetts hospital reporting
- National Weather Service
- CDC Massachusetts respiratory surveillance
- City of Boston event data
- TD Garden and MLB schedules
- Boston-area local/traffic news
- OpenStreetMap / OSRM routing

## Important limitations

ERNow cannot see live waiting-room counts, triage severity, real-time staffing, treatment-room availability, boarding load, or incoming ambulance volume.

Because of this, results are **forecasts, not confirmed live wait times**.

For a possible medical emergency, call **911** or go to the nearest appropriate emergency department rather than delaying care based on an ERNow estimate.

## Built with

Python · Pandas · Streamlit · REST APIs · Public healthcare data · Geolocation · Road routing

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
