import pandas as pd
import streamlit as st

st.set_page_config(page_title="ERNow Methodology", page_icon="✚", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');
:root{--ivory:#F8F4E6;--shell:#FFFDF5;--ink:#1C1B19;--soft:#403A32;--tea:#B9AD91;--moss:#48513C;--beni:#8C2F2F;--kakishibu:#A85B45;--kakishibu-wash:rgba(168,91,69,.10)}
html,body,[class*="css"],.stApp{font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif}
.stApp{background:var(--ivory);color:var(--ink)}
.block-container{padding-top:5.4rem!important;padding-bottom:2rem;max-width:900px}
[data-testid="stSidebar"],[data-testid="collapsedControl"]{display:none!important}
.safety-banner{display:block;width:100%;box-sizing:border-box;background:var(--beni);color:#fff!important;border-radius:16px;padding:16px 19px;font-size:1rem;line-height:1.5;font-weight:650;margin:0 0 .9rem 0}
.safety-banner,.safety-banner *{color:#fff!important}
.nav-wrap{border-bottom:1px solid var(--tea);padding-bottom:.55rem;margin-bottom:1.15rem}
[data-testid="stPageLink-NavLink"]{background:var(--shell)!important;border:1px solid var(--tea)!important;border-radius:10px!important;color:var(--ink)!important;font-weight:650!important}
[data-testid="stPageLink-NavLink"] *{color:var(--ink)!important}
[data-testid="stPageLink-NavLink"] .material-symbols-rounded{color:var(--beni)!important}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="safety-banner">
🚨 <strong>Possible emergency?</strong> Call 911 or go to the nearest appropriate emergency department.
ERNow estimates must never be used to delay emergency care.
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
nav1, nav2, _ = st.columns([1, 1, 4])
with nav1:
    st.page_link("app.py", label="ERNow", icon=":material/emergency:", use_container_width=True)
with nav2:
    st.page_link("pages/1_Methodology.py", label="Methodology", icon=":material/menu_book:", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.title("Methodology")
st.caption("How ERNow builds its estimate, which data are current, and what the app cannot know.")

st.subheader("What ERNow estimates")
st.write(
    "ERNow estimates a likely **ER wait range** for each included Boston hospital and combines it with "
    "**estimated road-route access** from the user's location. It does not claim to know a hospital's live waiting-room queue."
)

st.subheader("What goes into the estimate")
st.markdown("""
**Hospital history and recent performance**
- Historical wait-to-provider from archived CMS Hospital Compare reporting.
- **CMS OP-18b — Median Time from Emergency Department Arrival to Departure for Discharged Emergency Department Patients.** This appears as **Typical visit duration** and is used as a newer hospital-throughput signal.
- Recent reported emergency-department volume, occupancy, and other utilization signals from Massachusetts sources.
- CMS **Left Before Being Seen (OP-22)** when available.

**Current and contextual conditions**
- Boston time, day of week, and holiday status.
- Weather and severe-weather alerts.
- Seasonal respiratory illness conditions.
- Major Boston events that may affect traffic or demand.

**Access**
- Road-route distance and estimated route duration calculated from the user's location.
- Route time is **not live traffic**.
""")

st.subheader("Accuracy and freshness")
st.markdown("""
**Weather — current official observations.**  
ERNow uses the latest available **National Weather Service** observation near the user's coordinates and checks active NWS alerts. This is current official weather data, but the nearest reporting station may not exactly match conditions on the user's block.

**Seasonal respiratory illness — latest CDC reporting period.**  
ERNow uses the latest Massachusetts **CDC Acute Respiratory Illness (ARI)** surveillance category as a broad seasonal demand signal. It is public-health surveillance, not a live count of patients in a specific ER.

**Major events nearby — official schedules plus a local-news check.**  
ERNow checks multiple sources rather than relying on one calendar. The current build uses the **City of Boston event feed**, **TD Garden's official event schedule**, and **MLB's official schedule for Red Sox home games at Fenway Park**. It also checks recent **Boston.com local/traffic RSS coverage** for major event or closure stories, and can use Ticketmaster when an API key is configured.

Only events plausibly large enough to affect traffic or emergency-department demand should influence the model. If the homepage says **None detected**, that means no qualifying event was found by the sources checked; it is not a guarantee that no event exists.
""")

st.subheader("How the model uses the data")
st.markdown("""
1. Start with each hospital's historical wait-to-provider baseline.
2. Recalibrate with newer hospital throughput, including **Typical visit duration (CMS OP-18b)**.
3. Apply a bounded hospital-specific adjustment for recent reported demand/utilization.
4. Apply bounded contextual adjustments for time/day, holidays, weather, seasonal respiratory illness, and major events.
5. Return a **range**, not a single precise minute.
6. Rank hospitals using estimated wait together with estimated road-route access.
""")

st.subheader("Important limitations")
st.markdown("""
- ERNow cannot see the number of people currently waiting, triage severity, real-time staffing, open treatment rooms, boarding load, or incoming ambulance volume.
- Current-demand labels are **not** measurements of a hospital's live occupancy or waiting room.
- Historical and periodically reported hospital data can differ from conditions inside the ER right now.
- Distance depends on the user's location.
- Route time does not include live traffic, road incidents, parking, or ambulance transport conditions.
- Event and news sources can miss events, change format, or become temporarily unavailable.

For a serious or time-sensitive emergency, call 911 or use the nearest appropriate emergency department rather than choosing a farther hospital because of an ERNow estimate.
""")

with st.expander("Data freshness and source detail"):
    fresh = pd.DataFrame([
        ["Weather", "National Weather Service", "Current observation + active alerts", "Official nearby observation; exact-block conditions can vary"],
        ["Seasonal respiratory illness", "CDC Massachusetts ARI", "Latest published reporting period", "Statewide surveillance, not live hospital demand"],
        ["Major events", "City of Boston + TD Garden + MLB + Boston.com local/traffic; optional Ticketmaster", "Official schedules checked at use; local-news layer cached up to 6 hours", "Detection aid, not a guarantee"],
        ["Route", "OpenStreetMap/OSRM road routing", "At search / short cache", "Road route; no live traffic"],
        ["Time / day / holiday", "Boston clock + calendar rules", "Immediate", "Current"],
        ["Hospital utilization", "Massachusetts CHIA / public reporting", "Latest reported period", "Recent, not live"],
        ["ER visit duration", "CMS OP-18b", "Latest public reporting period", "Hospital throughput signal"],
        ["Historical wait", "Archived CMS Hospital Compare OP-20", "Archived", "Historical baseline only"],
    ], columns=["Factor", "Source", "Freshness", "Meaning"])
    st.dataframe(fresh, use_container_width=True, hide_index=True)

st.caption("ERNow is a forecasting prototype using public or zero-cost data sources. It is not a clinically validated live wait-time service.")
