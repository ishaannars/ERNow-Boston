from pathlib import Path

import pandas as pd
import streamlit as st

from historical_modeling import history_status, train_historical_models

st.set_page_config(page_title="ERNow Boston", page_icon="✚", layout="wide")
BASE = Path(__file__).resolve().parents[1]
HOSPITAL_DATA = BASE / "data" / "boston_er_data.csv"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');
:root{--ivory:#F8F4E6;--shell:#FFFDF5;--ink:#1C1B19;--soft:#403A32;--tea:#B9AD91;--moss:#48513C;--beni:#8C2F2F;--kakishibu:#A85B45;--wash:rgba(168,91,69,.08)}
html,body,[class*="css"],.stApp{font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif}
.stApp,[data-testid="stAppViewContainer"],[data-testid="stAppViewBlockContainer"],section.main{background:var(--ivory)!important;color:var(--ink)}
.block-container{padding-top:5.4rem!important;padding-bottom:2rem;max-width:960px}
[data-testid="stSidebar"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stStatusWidget"],
.stDeployButton,
button[kind="header"]{
    display:none!important;
}
.safety-banner{background:var(--beni);color:#fff!important;border-radius:16px;padding:16px 19px;font-size:1rem;line-height:1.5;font-weight:650;margin:0 0 .9rem}
.safety-banner,.safety-banner *{color:#fff!important}
.nav-wrap{border-bottom:1px solid var(--tea);padding-bottom:.55rem;margin-bottom:1.15rem}
[data-testid="stPageLink-NavLink"]{background:var(--shell)!important;border:1px solid var(--tea)!important;border-radius:10px!important;color:var(--ink)!important;font-weight:650!important;white-space:nowrap!important;overflow:visible!important;min-width:max-content!important}
[data-testid="stPageLink-NavLink"] *{color:var(--ink)!important;white-space:nowrap!important}
[data-testid="stPageLink-NavLink"] .material-symbols-rounded{color:var(--beni)!important}
.status-card{background:var(--shell);border:1px solid var(--tea);border-left:4px solid var(--moss);border-radius:14px;padding:.9rem 1rem;margin:.5rem 0 .8rem}
.status-title{font-weight:700;font-size:.98rem}
.status-copy{color:var(--soft);font-size:.88rem;margin-top:.25rem;line-height:1.48}
.mini-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.55rem;margin:.45rem 0 1rem}
.mini-card{background:var(--shell);border:1px solid var(--tea);border-radius:12px;padding:.72rem .8rem}
.mini-label{font-size:.7rem;color:var(--soft);text-transform:uppercase;letter-spacing:.04em;font-weight:650}
.mini-value{font-size:.95rem;font-weight:700;margin-top:.18rem;color:var(--ink);word-break:break-word}
.feature-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.55rem;margin:.4rem 0 .7rem}
.feature-card{background:var(--shell);border:1px solid var(--tea);border-radius:12px;padding:.75rem .8rem}
.feature-title{font-weight:700;font-size:.86rem;margin-bottom:.18rem}
.feature-copy{font-size:.78rem;color:var(--soft);line-height:1.42}
.callout{background:var(--wash);border-left:3px solid var(--kakishibu);border-radius:10px;padding:.78rem .85rem;color:var(--soft);font-size:.84rem;line-height:1.48;margin:.55rem 0 .85rem}
.note{background:var(--shell);border:1px solid var(--tea);border-radius:12px;padding:.78rem .85rem;color:var(--soft);font-size:.84rem;line-height:1.5;margin:.55rem 0 .8rem}
@media(max-width:720px){.mini-grid,.feature-grid{grid-template-columns:1fr}}

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

.status-card{padding:.9rem 1rem!important;margin:.5rem 0 .95rem!important}
.mini-grid{gap:.5rem!important;margin:.45rem 0 1rem!important}
.mini-card{padding:.68rem .75rem!important}
.mini-label,.mini-value,.feature-title{font-weight:600!important}
.feature-grid{gap:.5rem!important;margin:.4rem 0 .8rem!important}
.feature-card{padding:.72rem .78rem!important}
.callout,.note{margin:.52rem 0 .82rem!important}


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

st.markdown('<div class="safety-banner"><strong>Possible emergency?</strong> This page explains the predictive layer inside ERNow. It is not a clinical decision tool.</div>', unsafe_allow_html=True)

st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
a,b,c,_ = st.columns([1.10,1.45,1.45,3.00])
with a:
    st.page_link("app.py", label="ERNow", icon=":material/emergency:", use_container_width=True)
with b:
    st.page_link("pages/1_Methodology.py", label="Methodology", icon=":material/menu_book:", use_container_width=True)
with c:
    st.page_link("pages/2_Model_Lab.py", label="Forecast Model", icon=":material/monitoring:", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.title("Forecast Model")
st.caption("How ERNow tests its historical model and uses the selected prediction inside the wait forecast.")

hist = history_status()
result = train_historical_models() if hist["ready"] else None

st.subheader("1. Model status")
if hist["ready"]:
    hospitals = hist["data"]["hospital"].nunique()
    start = hist["data"]["timestamp"].min().year
    end = hist["data"]["timestamp"].max().year
    predictor = result["selected_model"]
    st.markdown(
        '<div class="status-card"><div class="status-title">Learning model active</div>'
        '<div class="status-copy">Real CMS history is loaded, later reporting periods are reserved for validation, and the best-performing historical predictor is available to help shape ERNow\'s wait forecast.</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""<div class="mini-grid">
        <div class="mini-card"><div class="mini-label">Historical observations</div><div class="mini-value">{hist['rows']}</div></div>
        <div class="mini-card"><div class="mini-label">Boston ERs</div><div class="mini-value">{hospitals}</div></div>
        <div class="mini-card"><div class="mini-label">Reporting coverage</div><div class="mini-value">{start}–{end}</div></div>
        <div class="mini-card"><div class="mini-label">Holdout observations</div><div class="mini-value">{result['test_rows']}</div></div>
        <div class="mini-card"><div class="mini-label">Selected predictor</div><div class="mini-value">{predictor}</div></div>
        <div class="mini-card"><div class="mini-label">Validation</div><div class="mini-value">Earlier → later</div></div>
        </div>""",
        unsafe_allow_html=True,
    )
else:
    st.markdown(f'<div class="status-card"><div class="status-title">Historical model not ready</div><div class="status-copy">{hist["reason"]}</div></div>', unsafe_allow_html=True)

st.subheader("2. What the model predicts")
st.write(
    "The model learns from CMS OP-18b, which measures the median time discharged patients spend in the ED from arrival to departure. "
    "Using prior reporting periods, it estimates expected ER flow for each hospital."
)
st.write(
    "This is not the same as predicting a live waiting-room queue. ERNow uses the historical prediction as one input inside the broader wait forecast."
)

st.subheader("3. Model comparison")
if hist["ready"]:
    metrics = result["metrics"].copy().rename(columns={"MAE":"MAE (min)","RMSE":"RMSE (min)","R2":"R²"})
    metrics["MAE (min)"] = metrics["MAE (min)"].round(1)
    metrics["RMSE (min)"] = metrics["RMSE (min)"].round(1)
    metrics["R²"] = metrics["R²"].round(3)
    st.dataframe(metrics, use_container_width=True, hide_index=True)

    if result["learned_model_promoted"]:
        summary = f"{result['best_ml_model']} performed best on later held-out periods and cleared the promotion threshold, so ERNow uses it as the historical predictor."
    else:
        summary = f"{result['selected_model']} performed best on the holdout period. The strongest learned challenger was {result['best_ml_model']}, but it did not improve enough to replace the simpler predictor."
    st.markdown(f'<div class="callout">{summary}</div>', unsafe_allow_html=True)
    st.caption("MAE is the average error in minutes. RMSE gives more weight to larger misses. R² shows how much variation the model explains; a negative value means it performed worse than predicting the holdout average.")
else:
    st.info("Generate `data/cms_op18b_history.csv` with `python cms_history_pipeline.py`.")

st.subheader("4. What the model uses")
st.markdown("""<div class="feature-grid">
<div class="feature-card"><div class="feature-title">Hospital identity</div><div class="feature-copy">Captures persistent differences across the six included Boston hospitals.</div></div>
<div class="feature-card"><div class="feature-title">Reporting period</div><div class="feature-copy">Year, month, and quarter help the model learn how outcomes change over time.</div></div>
<div class="feature-card"><div class="feature-title">Recent history</div><div class="feature-copy">Prior reporting periods and a rolling historical average give the model recent context without looking ahead.</div></div>
</div>""", unsafe_allow_html=True)
st.caption("All lagged features use only information that would have been available before the period being predicted, which prevents look-ahead leakage.")

st.subheader("5. Current hospital context")
base = pd.read_csv(HOSPITAL_DATA)
display = base[["hospital","legacy_wait_to_provider_min","typical_ed_minutes","recent_ed_visits","recent_occupancy_pct"]].rename(columns={
    "hospital":"Hospital",
    "legacy_wait_to_provider_min":"Historical wait (min)",
    "typical_ed_minutes":"Typical ED stay (min)",
    "recent_ed_visits":"Recent ED visits",
    "recent_occupancy_pct":"Occupancy (%)",
})
st.dataframe(display, use_container_width=True, hide_index=True)
left,right = st.columns(2)
with left:
    st.caption("Recent reported ED visits")
    st.bar_chart(base.set_index("hospital")["recent_ed_visits"])
with right:
    st.caption("Reported occupancy")
    st.bar_chart(base.set_index("hospital")["recent_occupancy_pct"])

st.subheader("6. Validation")
if hist["ready"]:
    st.write(
        f"Training period: {result['train_start'].date()} → {result['train_end'].date()}  \n"
        f"Holdout period: {result['test_start'].date()} → {result['test_end'].date()}"
    )
    st.caption("Earlier periods train the model; later periods test it. This better reflects how the model would face future data than a random split.")
    err = result["hospital_error"].copy().rename(columns={"hospital":"Hospital","MAE":"MAE (min)","Observations":"Holdout observations"})
    err["MAE (min)"] = err["MAE (min)"].round(1)
    st.dataframe(err, use_container_width=True, hide_index=True)
    st.caption("Holdout MAE by hospital")
    st.bar_chart(result["hospital_error"].set_index("hospital")["MAE"])
else:
    st.write("Earlier reporting periods train the model; later periods test it.")

st.subheader("7. How it affects your estimate")
st.write(
    "The selected historical model contributes one bounded hospital-level signal. ERNow then combines that signal with recent utilization and current conditions to estimate a wait range. "
    "Travel time from your location is added afterward to compare overall access."
)
st.markdown(
    '<div class="note"><strong>Important boundary:</strong> the machine-learning layer improves the forecast, but it does not directly observe a hospital\'s live queue. ERNow therefore shows a wait range and route context instead of claiming an exact real-time queue minute.</div>',
    unsafe_allow_html=True,
)

with st.expander("Technical details"):
    st.markdown("""
**Historical target**
- CMS OP-18b median ED arrival-to-departure duration for discharged patients.

**Models compared**
- Persistence baseline
- Ridge regression
- Random Forest

**Validation**
- Chronological train/holdout split
- MAE, RMSE, and R²
- Hospital-level MAE

**Selection rule**
- A learned model replaces the baseline only when it improves holdout MAE by the configured promotion margin.

**Role in ERNow**
- The selected historical prediction becomes one bounded signal inside the consumer wait forecast.
""")

st.divider()
st.caption("ERNow Forecast Model · Historical CMS model validation · Not a live queue model.")
