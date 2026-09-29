import pandas as pd
import streamlit as st

st.set_page_config(page_title="ERNow Boston", page_icon="✚", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');
:root{--ivory:#F8F4E6;--shell:#FFFDF5;--ink:#1C1B19;--soft:#403A32;--tea:#B9AD91;--moss:#48513C;--beni:#8C2F2F;--kakishibu:#A85B45;--wash:rgba(168,91,69,.08)}
html,body,[class*="css"],.stApp{font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif}
.stApp,[data-testid="stAppViewContainer"],[data-testid="stAppViewBlockContainer"],section.main{background:var(--ivory)!important;color:var(--ink)}
.block-container{padding-top:5.4rem!important;padding-bottom:2rem;max-width:920px}
[data-testid="stSidebar"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stStatusWidget"],
.stDeployButton,
button[kind="header"]{
    display:none!important;
}
.safety-banner{display:block;width:100%;box-sizing:border-box;background:var(--beni);color:#fff!important;border-radius:16px;padding:16px 19px;font-size:1rem;line-height:1.5;font-weight:650;margin:0 0 .9rem}
.safety-banner,.safety-banner *{color:#fff!important}
.nav-wrap{border-bottom:1px solid var(--tea);padding-bottom:.55rem;margin-bottom:1.15rem}
[data-testid="stPageLink-NavLink"]{background:var(--shell)!important;border:1px solid var(--tea)!important;border-radius:10px!important;color:var(--ink)!important;font-weight:650!important;white-space:nowrap!important;overflow:visible!important;min-width:max-content!important}
[data-testid="stPageLink-NavLink"] *{color:var(--ink)!important;white-space:nowrap!important}
[data-testid="stPageLink-NavLink"] .material-symbols-rounded{color:var(--beni)!important}
.ds-card{background:var(--shell);border:1px solid var(--tea);border-left:4px solid var(--moss);border-radius:14px;padding:.9rem 1rem;margin:.45rem 0 1rem}
.ds-title{font-weight:700;margin-bottom:.28rem}
.ds-sub{color:var(--soft);font-size:.9rem;line-height:1.5}
.ds-tags{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.55rem}
.ds-tag{font-size:.73rem;border:1px solid var(--tea);background:var(--ivory);border-radius:999px;padding:.23rem .48rem;font-weight:600;color:var(--soft)}

/* Editorial body copy only; headings/navigation remain Instrument Sans. */
.stMarkdown p,.stMarkdown li,[data-testid="stCaptionContainer"],.stAlert p{
  font-family:Georgia,'Times New Roman',serif!important;
  line-height:1.62;
}
h1,h2,h3,h4,h5,h6,[data-testid="stPageLink-NavLink"],button,.stButton{
  font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif!important;
}


/* Final page rhythm */
.block-container{padding-top:5.15rem!important;padding-bottom:2.4rem!important}
h1{margin-bottom:.3rem!important}
h2{margin-top:1.55rem!important;margin-bottom:.42rem!important}
h3{margin-top:1.15rem!important;margin-bottom:.35rem!important}
.stMarkdown p{margin:.15rem 0 .72rem!important}
.stMarkdown ul,.stMarkdown ol{margin-top:.18rem!important;margin-bottom:.85rem!important}
.stMarkdown li{margin-bottom:.22rem!important}
.stMarkdown strong{font-weight:600!important}
[data-testid="stDataFrame"]{margin:.45rem 0 .85rem!important}

.ds-card{padding:.92rem 1rem!important;margin:.55rem 0 1.1rem!important}
.ds-tags{gap:.38rem .44rem!important;margin-top:.5rem!important}
.ds-tag{padding:.22rem .46rem!important;font-size:.71rem!important;font-weight:600!important}


/* Quiet body emphasis */
.stMarkdown strong,[data-testid="stCaptionContainer"] strong,.stAlert strong{
  font-weight:500!important;
}
.stMarkdown h1 strong,.stMarkdown h2 strong,.stMarkdown h3 strong,.stMarkdown h4 strong,
h1 strong,h2 strong,h3 strong,h4 strong{
  font-weight:700!important;
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="safety-banner">
<strong>Possible emergency?</strong> Call 911 or go to the nearest appropriate emergency department. ERNow estimates should never be used to delay emergency care.
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
a,b,c,_ = st.columns([1.10,1.45,1.45,3.00])
with a:
    st.page_link("app.py", label="ERNow", icon=":material/emergency:", use_container_width=True)
with b:
    st.page_link("pages/1_Methodology.py", label="Methodology", icon=":material/menu_book:", use_container_width=True)
with c:
    st.page_link("pages/2_Model_Lab.py", label="Forecast Model", icon=":material/monitoring:", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.title("Methodology")
st.caption("How ERNow combines hospital history, current conditions, and travel access to estimate ER wait ranges.")

st.markdown("""
<div class="ds-card">
  <div class="ds-title">Machine-learning layer</div>
  <div class="ds-sub">ERNow uses a validated historical model to estimate expected ER flow. That prediction becomes one input to the public wait forecast, alongside current hospital conditions, weather, respiratory illness, major events, and route access.</div>
  <div class="ds-tags">
    <span class="ds-tag">6 Boston ERs</span>
    <span class="ds-tag">36 historical observations</span>
    <span class="ds-tag">2020–2025 reporting periods</span>
    <span class="ds-tag">Aug 2026 CMS archive snapshot</span>
    <span class="ds-tag">Persistence · Ridge · Random Forest</span>
  </div>
</div>
""", unsafe_allow_html=True)

st.subheader("What ERNow estimates")
st.write(
    "ERNow estimates a likely ER wait range for each included Boston hospital and combines it with "
    "travel access from the user's location. It does not claim to know a hospital's live waiting-room queue."
)

st.subheader("What shapes the forecast")
st.markdown("""
**Hospital history and utilization**
- Archived CMS wait-to-provider information.
- CMS OP-18b hospital-throughput history.
- Recent reported ED volume, occupancy, and related utilization signals.
- CMS Left Before Being Seen (OP-22) when available.

**Current conditions**
- Boston time, day of week, holidays, and season.
- National Weather Service observations and severe-weather alerts.
- CDC Massachusetts respiratory-illness surveillance.
- Major Boston events that may affect demand or access.

**Travel access**
- Road-route distance and estimated travel time from the user's location to each hospital.
- Travel time is personalized by hospital but does not include live traffic.
""")

st.subheader("Where machine learning fits")
st.write(
    "The historical model learns from longitudinal CMS OP-18b data, which measures the median time discharged patients spend in the ED from arrival to departure. "
    "It uses prior reporting periods to estimate expected ER flow for each hospital."
)
st.write(
    "ERNow then uses that prediction as one bounded signal inside the wait forecast. The app also accounts for reported utilization, time, weather, respiratory illness, major events, and route access."
)

st.subheader("How the displayed wait range is built")
st.markdown("""
1. Start with each hospital's archived wait-to-provider baseline.
2. Add a bounded adjustment from the validated historical model and recent hospital-throughput data.
3. Adjust for reported utilization and current local conditions.
4. Return a wait range rather than an exact minute.
5. Combine the wait forecast with travel access from the user's location to rank nearby ERs.
""")

st.subheader("Why the estimate stays cautious")
st.write(
    "CMS OP-18b measures total ED arrival-to-departure time for discharged patients; it is not a direct live wait-to-provider target. "
    "The model therefore improves the forecast without being presented as a live queue measurement."
)

st.subheader("Accuracy and freshness")
st.markdown("""
Weather — current National Weather Service observations and alerts.  
Respiratory illness — latest published CDC Massachusetts ARI reporting period.  
Major events — current-date checks from Boston-area public sources.  
Route — OpenStreetMap / OSRM road routing at search time, without live traffic.  
Hospital utilization — latest available public Massachusetts reporting.  
Historical model — longitudinal CMS OP-18b reporting periods used for chronological validation.
""")

st.subheader("Important limitations")
st.markdown("""
- ERNow cannot see current triage severity, staffing, open treatment rooms, boarding load, ambulance arrivals, or the exact number of people waiting right now.
- Public hospital data can lag behind conditions inside the ER.
- Current-demand labels are contextual estimates, not direct live queue measurements.
- Travel time excludes live traffic, parking, road incidents, and ambulance transport conditions.
- Predictive relationships can improve forecasting, but they do not establish causation.

For a serious or time-sensitive emergency, call 911 or use the nearest appropriate emergency department rather than choosing a farther hospital because of an ERNow estimate.
""")

with st.expander("Source and freshness detail"):
    fresh = pd.DataFrame([
        ["Weather", "National Weather Service", "Current observation + alerts", "Current contextual signal"],
        ["Respiratory illness", "CDC Massachusetts ARI", "Latest reporting period", "Statewide illness signal"],
        ["Major events", "Boston-area public sources", "Current-date checks", "Contextual demand signal"],
        ["Route", "OpenStreetMap / OSRM", "At search", "Personalized by hospital; no live traffic"],
        ["Hospital utilization", "Massachusetts public reporting", "Latest reported period", "Recent, not live"],
        ["ER throughput", "CMS OP-18b", "Longitudinal reporting periods", "Historical model target"],
        ["Historical wait", "Archived CMS Hospital Compare OP-20", "Archived", "Historical baseline"],
    ], columns=["Factor", "Source", "Freshness", "Meaning"])
    st.dataframe(fresh, use_container_width=True, hide_index=True)

st.caption("ERNow is a forecasting prototype built on public or zero-cost data sources. It is not a clinical decision tool or a confirmed live wait-time service.")
