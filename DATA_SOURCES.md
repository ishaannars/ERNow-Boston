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
