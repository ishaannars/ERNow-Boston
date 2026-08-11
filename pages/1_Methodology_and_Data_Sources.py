import pandas as pd
import streamlit as st

st.set_page_config(page_title="ERFlow Methodology", page_icon="📚", layout="wide")
st.title("Methodology & Data Sources")
st.caption("What ERFlow measures, which inputs are current, how the ranking works, and where uncertainty remains.")
st.warning("ERFlow is a portfolio forecasting prototype. It does not have a live hospital queue, triage, staffing, or boarding feed and must not be used to delay emergency care.")

st.header("Consumer ranking")
st.markdown("""
ERFlow ranks hospitals by a directly understandable quantity:

**modeled time until initial evaluation = estimated travel time + modeled wait to first provider evaluation**

The app does **not** call this a confirmed live wait time. It is a forecast built from public historical hospital benchmarks plus current external signals.
""")

st.header("Five items shown on every hospital card")
st.markdown("""
1. **Modeled wait to provider** — a wide range estimated from legacy CMS OP-20, latest CMS throughput context, and current demand signals.
2. **Estimated travel time / distance** — a zero-cost estimate recalculated from the user’s location, straight-line distance, and the current Boston hour/day. It is not live traffic.
3. **Current wait pressure** — a relative label based on the modeled wait among the Boston hospitals in the app.
4. **Historical wait benchmark** — 2019 CMS-derived OP-20 arrival-to-provider median.
5. **Recent historical ED duration** — latest available CMS OP-18b arrival-to-departure median for eligible discharged ED patients.
""")

st.header("Freshness of each factor")
fresh = pd.DataFrame([
    ["Estimated travel time", "ERFlow distance + current hour/day heuristic", "Recalculated at search time", "Zero-cost; not live traffic"],
    ["Weather", "National Weather Service observations + active alerts", "Latest station observation; NWS notes observations may be delayed up to ~20 minutes", "No API key"],
    ["Time / day", "Boston local system clock", "Immediate", "No API key"],
    ["Holiday", "Calendar rules, including Massachusetts Patriots' Day", "Immediate for the current date", "No API key"],
    ["Respiratory illness", "CDC Acute Respiratory Illness activity — Massachusetts", "Latest published weekly level", "Not minute-by-minute live; no equivalent statewide live feed is public"],
    ["Events", "City of Boston current event feed; optional Ticketmaster Discovery API", "Current event calendar/search window", "Ticketmaster broadens major-event coverage if key is added"],
    ["Recent ED duration", "CMS Timely and Effective Care — OP-18b", "Latest CMS public reporting period", "Historical baseline"],
    ["Wait to provider", "CMS-derived Hospital Compare OP-20 archive", "2019 legacy snapshot", "Historical baseline"],
], columns=["Factor", "Source", "Freshness", "Note"])
st.dataframe(fresh, use_container_width=True, hide_index=True)

st.header("How wait-to-provider is modeled")
st.markdown("""
For each hospital, ERFlow begins with its **2019 historical CMS OP-20 median wait to first provider evaluation**. Because OP-20 was retired and is not current, ERFlow does not present that number as today's wait.

The model then:

- uses the hospital's **latest available CMS OP-18b total ED duration relative to the Boston sample median** as a small hospital-specific recalibration signal;
- applies bounded current demand adjustments for **time/day/holiday, current NWS weather, latest CDC respiratory-illness activity, and high-impact current Boston events**;
- deliberately uses a **wide uncertainty range** because live queue, triage severity, staffing, treatment-room availability, boarding load, and incoming ambulance volume are unavailable publicly.

The dynamic coefficients are transparent prototype assumptions, **not clinically validated causal effects**. They are intentionally bounded so an external signal cannot overwhelm the hospital's underlying historical benchmark.
""")

st.header("Why the ranking changed from earlier ERFlow versions")
st.markdown("""
Earlier versions used a normalized weighted score dominated by total ED duration. That was harder for a consumer to interpret and could double-count travel distance and ETA.

The publication version instead sorts by **minutes of modeled access time**. Distance is displayed and used as a safety/context signal, while estimated travel time captures an approximate travel burden. This avoids giving distance its own arbitrary weight after travel time is already known.
""")

st.header("Historical wait-to-provider values")
st.markdown("""
ERFlow uses a consistent 2019 CMS-derived Hospital Compare snapshot for the retired **OP-20: Door to Diagnostic Evaluation by a Qualified Medical Professional** measure:

- Tufts Medical Center — **28 min**
- Boston Medical Center — **70 min**
- Brigham and Women's Faulkner Hospital — **16 min**
- Massachusetts General Hospital — **28 min**
- Brigham and Women's Hospital — **24 min**
- Beth Israel Deaconess Medical Center — **48 min**

These are historical medians, not current waits. The app preserves the year next to every displayed benchmark.
""")

st.header("What is genuinely current vs. latest available")
st.markdown("""
**Current at search time:** location, local time/day, holiday status, recalculated travel estimate, NWS current observation/alerts, and current event-calendar queries.

**Latest available rather than live:** CDC respiratory-illness activity (weekly), CMS ED-duration data (periodic), and 2019 OP-20 wait benchmarks (legacy historical).

ERFlow never relabels a proxy or stale source as live. If a current feed fails, the UI says so.
""")

st.header("Known limitations")
st.markdown("""
ERFlow cannot observe every Boston hospital's live:

- waiting-room census
- triage-severity distribution
- physician/nurse staffing
- available treatment rooms
- boarding patients
- ambulance arrivals

Those variables can dominate actual waiting time. A future hospital partnership or validated operational feed would be necessary before calling the product a live ER wait-time service.
""")

st.header("Publication requirements")
st.markdown("""
No paid API is required for the core app. ERFlow uses a zero-cost estimated travel time rather than live traffic.

Optional: add **`TICKETMASTER_API_KEY`** to broaden coverage of current major sports/music events beyond the City of Boston event feed. The app still works without it.
""")

st.page_link("app.py", label="Back to ERFlow rankings", icon="🏥")
