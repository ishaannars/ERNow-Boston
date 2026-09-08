import pandas as pd
import streamlit as st

st.set_page_config(page_title="ERNow Methodology", page_icon="✚", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');
:root{--ivory:#F8F4E6;--shell:#FFFDF5;--ink:#1C1B19;--soft:#403A32;--tea:#B9AD91;--moss:#48513C;--beni:#8C2F2F;--kakishibu:#A85B45;--kakishibu-wash:rgba(168,91,69,.10);}
html, body, [class*="css"], .stApp{font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif;}
.stApp{background:var(--ivory);color:var(--ink)}
.block-container{padding-top:5.4rem!important;padding-bottom:2rem;max-width:900px}
[data-testid="stSidebar"],[data-testid="collapsedControl"]{display:none!important}
.safety-banner{display:block;width:100%;box-sizing:border-box;overflow:visible;background:var(--beni);color:#FFFFFF!important;border-radius:16px;padding:16px 19px;font-size:1rem;line-height:1.5;font-weight:650;margin:0 0 .9rem 0}.safety-banner,.safety-banner *{color:#FFFFFF!important;opacity:1!important}
.nav-wrap{border-bottom:1px solid var(--tea);padding-bottom:.55rem;margin-bottom:1.15rem}
[data-testid="stPageLink-NavLink"]{background:var(--shell)!important;border:1px solid var(--tea)!important;border-radius:10px!important;color:var(--ink)!important;font-weight:650!important}
[data-testid="stPageLink-NavLink"]:hover{border-color:var(--kakishibu)!important;background:var(--kakishibu-wash)!important}
.material-symbols-rounded{color:var(--beni)!important}
@media(max-width:650px){.block-container{padding-top:4.8rem!important}}
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
st.caption("A concise explanation of what ERNow estimates, what data it uses, and where the limits are.")

st.subheader("What ERNow estimates")
st.write("ERNow estimates a likely **ER wait range** for each Boston hospital and compares it with an **estimated road-route time** from the user's location. The estimate combines hospital history, recent reported hospital demand, current local conditions, route access, and other relevant factors. It does not claim to know the live waiting-room queue.")

st.subheader("What goes into the estimate")
st.markdown("""
**Hospital history and recent performance**
- Historical wait from archived CMS Hospital Compare reporting.
- **CMS OP-18b — Median Time from Emergency Department Arrival to Departure for Discharged Emergency Department Patients.** This is shown on hospital cards as **Typical visit duration** and is also used as a newer hospital-throughput signal in the wait estimate.
- Recent emergency-department visit volume, inpatient occupancy, and other available utilization signals from Massachusetts CHIA.
- CMS **Left Before Being Seen (OP-22)** when available.

**Current demand conditions**
- Current Boston hour and day of week.
- Holiday status.
- National Weather Service current observations and active severe-weather alerts.
- Major Boston event signals.
- Latest Massachusetts respiratory-illness activity from CDC.

**Access from the user's location**
- Road-route distance and estimated route duration calculated when the user searches.
- Route duration is an estimate based on the road network and **does not include live traffic**.
""")

st.subheader("Current vs. historical")
st.markdown("""
**Current or frequently changing:** time/day, holiday status, weather observations and alerts, event signals, and route calculations are refreshed when the app is used or on short caches.

**Latest available:** respiratory illness is published on a reporting schedule rather than continuously; recent hospital utilization and occupancy are also reported periodically.

**Historical:** the historical wait comes from an archived CMS measure. A newer standardized hospital-level wait-to-provider measure is not currently published, so ERNow uses it as a baseline and adjusts it using newer hospital throughput, recent reported demand, and current conditions. The **Typical visit duration** value comes from the latest available CMS OP-18b reporting period and is not a live visit-length estimate.
""")

st.subheader("How the model uses the data")
st.markdown("""
1. Begin with each hospital's historical wait.
2. Recalibrate it using newer hospital throughput, including **Typical visit duration (CMS OP-18b)**.
3. Apply a small hospital-specific adjustment for recent reported demand and utilization.
4. Apply bounded current-condition adjustments for time/day, holidays, weather, respiratory activity, and major events.
5. Return a range rather than a single precise minute.
6. Rank hospitals using the estimated wait together with estimated road-route access from the user's location.
""")

st.subheader("Important limitations")
st.markdown("""
- ERNow cannot see the number of people currently waiting, triage severity, real-time staffing, open treatment rooms, boarding load, or incoming ambulance volume.
- **Distance is determined by where the user is located.** ERNow cannot control how close or far a hospital is; it only measures route access and uses it as one part of the comparison.
- Route times are estimates and do not include live traffic, road incidents, parking, or ambulance transport conditions.
- Current-demand labels summarize external conditions; they are **not** measurements of a hospital's live occupancy or waiting room.
- Historical and periodically reported hospital data can differ from conditions inside the ER right now.

For a serious or time-sensitive emergency, call 911 or use the nearest appropriate emergency department rather than choosing a farther hospital because of an ERNow estimate.
""")

with st.expander("Data freshness and source detail"):
    fresh = pd.DataFrame([
        ["Route", "OpenStreetMap/OSRM road routing", "At search / short cache", "Estimated route; no live traffic"],
        ["Weather", "National Weather Service", "Current observation + alerts", "Current public source"],
        ["Time / day / holiday", "Boston clock + calendar rules", "Immediate", "Current"],
        ["Respiratory illness", "CDC Massachusetts ARI", "Latest published release", "Not continuous"],
        ["Events", "City of Boston; optional event API", "Current-date query", "Major-event signal only"],
        ["Hospital utilization", "Massachusetts CHIA", "Latest reported period", "Recent, not live"],
        ["ER visit length", "CMS OP-18b", "Latest public reporting period", "Historical/recent benchmark"],
        ["Historical wait", "Archived CMS Hospital Compare OP-20", "Archived", "Historical baseline only"],
    ], columns=["Factor", "Source", "Freshness", "Meaning"])
    st.dataframe(fresh, use_container_width=True, hide_index=True)

st.caption("ERNow uses public or zero-cost data sources in this build. The forecast is a transparent prototype, not a clinically validated live wait-time service.")
