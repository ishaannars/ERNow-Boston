# ERFlow Boston — Data Sources

## Current / dynamic

### Zero-cost estimated travel time
ERFlow estimates travel time from the user’s location, straight-line distance to each hospital, and the current Boston hour/day. The estimate is recalculated at search time and is intentionally **not** labeled as live traffic or a routed navigation ETA. No paid API or private key is required.

### National Weather Service API
Uses the user's coordinates to discover nearby observation stations, retrieves a latest station observation, and checks active alerts for the point. NWS notes observation delivery can be delayed by upstream QC processing.

### Boston local time and holiday calendar
Computed at request time from `America/New_York`, including major U.S. holidays and Massachusetts Patriots' Day.

### CDC Acute Respiratory Illness (ARI), Massachusetts
Uses the latest published state-level ARI category. CDC updates this dataset weekly, so ERFlow labels it as latest weekly rather than live.

### Current events
Uses the City of Boston event feed. If `TICKETMASTER_API_KEY` is configured, ERFlow also queries the Ticketmaster Discovery API for Boston events in the upcoming six-hour window. Only high-impact event keywords are allowed to adjust the forecast; ordinary meetings/classes do not.

## Historical hospital baselines

### CMS OP-18b
Latest available public median emergency-department arrival-to-departure duration for eligible discharged patients. This is throughput, not wait-to-provider.

### CMS-derived OP-20 archive (2019)
Legacy median minutes from ED arrival until evaluation by a qualified healthcare professional. Used only as a historical wait benchmark and clearly labeled 2019.

## Model limitation

No public source reliably provides all six Boston ERs' live queue, triage mix, staffing, room availability, boarding load, or incoming ambulance volume. ERFlow therefore produces a forecast range rather than a confirmed live wait time.
