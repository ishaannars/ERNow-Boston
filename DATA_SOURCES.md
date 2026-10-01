# ERNow Boston — Data Sources

## Current / dynamic

### Zero-cost estimated travel time

ERNow estimates road-route travel time and distance from the user's location using OpenStreetMap road data through OSRM. The route is recalculated at search time. The estimate does **not** include live traffic, accidents, parking time, or ambulance transport conditions. If routing is unavailable, ERNow does not fabricate a route estimate.

### National Weather Service API
Uses the user's coordinates to discover nearby observation stations, retrieves the latest available station observation, and checks active alerts for the point. NWS notes observation delivery can be delayed by upstream QC processing.

### Boston local time and holiday calendar
Computed at request time from `America/New_York`, including major U.S. holidays and Massachusetts Patriots' Day.

### CDC Acute Respiratory Illness (ARI), Massachusetts
Uses the latest published state-level ARI category. CDC updates this dataset weekly, so ERNow labels it as latest weekly rather than live.

### Current events

ERNow checks multiple sources for Boston events that may affect traffic or emergency-department demand, including:

- City of Boston event data
- TD Garden's official event schedule
- MLB's official schedule for Red Sox home games
- recent Boston.com local and traffic RSS coverage
- optional Ticketmaster data when an API key is configured

Event data is used as a contextual demand signal, not as a live measure of hospital activity.

## Historical hospital baselines

### CMS OP-18b
Latest available public median emergency-department arrival-to-departure duration for eligible discharged patients. This is throughput, not wait-to-provider.

### CMS-derived OP-20 archive
Legacy median minutes from ED arrival until evaluation by a qualified healthcare professional. Used only as a historical wait benchmark and documented as a 2019 historical benchmark.

## Model limitation

No public source reliably provides all six Boston ERs' live queue, triage mix, staffing, room availability, boarding load, or incoming ambulance volume. ERNow therefore produces a forecast range rather than a confirmed live wait time.

## Added sources

### CMS Hospital Compare archives (national model)
Six releases (2021-10 to 2026-08) of `Timely_and_Effective_Care-Hospital` and `Hospital_General_Information` for every U.S. hospital: OP-18b, OP-18c, OP-22, ED volume category, hospital type, ownership, and star rating. Used to train and test the national ED performance model (`national_model.py`). Each release is published 9–12 months after its reporting period ends.

### CHIA Hospital Profiles, HFY 2024
Massachusetts Center for Health Information and Analysis hospital profiles: annual ED visits and **inpatient** occupancy (from CHIA Hospital Cost Reports). Inpatient occupancy is not ED crowding; a full hospital tends to back up its ED because admitted patients wait there for a bed. Shown as annual context.

### CMS Complications & Deaths (case complexity for peers)
Patient-volume denominators from the newest release: heart-attack and stroke volume, whether a hospital performs CABG (cardiac) surgery, and inpatient volume. Used only to match each Boston hospital with similar-complexity U.S. peers.

### Note on CHIA and weather/illness/events
CHIA utilization and Boston context (weather, respiratory illness, events) are displayed for context and are not used to adjust any number.
