from pathlib import Path

import pandas as pd
import streamlit as st

from historical_modeling import history_status, train_historical_models
from modeling import TEMPLATE_PATH, train_and_compare, training_status

st.set_page_config(page_title="ERNow Model Lab", page_icon="✚", layout="wide")
BASE = Path(__file__).resolve().parents[1]
HOSPITAL_DATA = BASE / "data" / "boston_er_data.csv"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');
:root{--ivory:#F8F4E6;--shell:#FFFDF5;--ink:#1C1B19;--soft:#403A32;--tea:#B9AD91;--moss:#48513C;--beni:#8C2F2F}
html,body,[class*="css"],.stApp{font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif}
.stApp{background:var(--ivory);color:var(--ink)}
.block-container{padding-top:5.4rem!important;padding-bottom:2rem;max-width:960px}
[data-testid="stSidebar"],[data-testid="collapsedControl"]{display:none!important}
.safety-banner{background:var(--beni);color:#fff!important;border-radius:16px;padding:16px 19px;font-size:1rem;line-height:1.5;font-weight:650;margin:0 0 .9rem 0}
.safety-banner,.safety-banner *{color:#fff!important}
.nav-wrap{border-bottom:1px solid var(--tea);padding-bottom:.55rem;margin-bottom:1.15rem}
[data-testid="stPageLink-NavLink"]{background:var(--shell)!important;border:1px solid var(--tea)!important;border-radius:10px!important;color:var(--ink)!important;font-weight:650!important}
[data-testid="stPageLink-NavLink"] *{color:var(--ink)!important}
[data-testid="stPageLink-NavLink"] .material-symbols-rounded{color:var(--beni)!important}
.status-card{background:var(--shell);border:1px solid var(--tea);border-left:4px solid var(--moss);border-radius:14px;padding:1rem 1.05rem;margin:.6rem 0 1rem 0}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="safety-banner">🚨 <strong>Possible emergency?</strong> Model Lab is an analytics view, not a clinical decision tool.</div>', unsafe_allow_html=True)

st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
a,b,c,_ = st.columns([1,1.15,1,3.85])
with a:
    st.page_link("app.py", label="ERNow", icon=":material/emergency:", use_container_width=True)
with b:
    st.page_link("pages/1_Methodology.py", label="Methodology", icon=":material/menu_book:", use_container_width=True)
with c:
    st.page_link("pages/2_Model_Lab.py", label="Model Lab", icon=":material/monitoring:", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.title("Model Lab")
st.caption("Machine-learning analysis, longitudinal CMS validation, and hospital-utilization exploration.")

hist = history_status()

# 1
st.subheader("1. Model Status")
if hist["ready"]:
    result = train_historical_models()
    st.markdown('<div class="status-card"><strong>Historical CMS model active.</strong><br>ERNow detected longitudinal OP-18b hospital data and is validating models on later reporting periods that were not used for training.</div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns(3)
    c1.metric("Historical rows", hist["rows"])
    c2.metric("Holdout rows", result["test_rows"])
    c3.metric("Best holdout model", result["best_model"])
else:
    st.markdown(f'<div class="status-card"><strong>Historical pipeline ready.</strong><br>{hist["reason"]}</div>', unsafe_allow_html=True)

# 2
st.subheader("2. Model Comparison")
if hist["ready"]:
    m = result["metrics"].copy()
    m["MAE"] = m["MAE"].round(1)
    m["RMSE"] = m["RMSE"].round(1)
    m["R2"] = m["R2"].round(3)
    st.dataframe(m, use_container_width=True, hide_index=True)
    st.caption("Target: CMS OP-18b median ED arrival-to-departure duration. This is throughput, not live wait-to-provider.")
else:
    st.info("Add CMS archive ZIPs to `data/cms_archives/` and run `python cms_history_pipeline.py`.")

# 3
st.subheader("3. Feature Drivers")
st.write("The historical model uses hospital identity, reporting period, the hospital's previous OP-18b value, a second lag, and a leakage-safe rolling historical mean.")
st.caption("Lag and rolling features use only prior reporting periods. They do not look ahead.")

# 4
st.subheader("4. Demand & Utilization Analysis")
base = pd.read_csv(HOSPITAL_DATA)
cols = ["hospital","legacy_wait_to_provider_min","typical_ed_minutes","recent_ed_visits","recent_occupancy_pct"]
st.dataframe(base[cols], use_container_width=True, hide_index=True)
left,right = st.columns(2)
with left:
    st.caption("Recent reported ED visits")
    st.bar_chart(base.set_index("hospital")["recent_ed_visits"])
with right:
    st.caption("Reported occupancy")
    st.bar_chart(base.set_index("hospital")["recent_occupancy_pct"])

# 5
st.subheader("5. Validation & Error Analysis")
if hist["ready"]:
    st.write(
        f"Training period: **{result['train_start'].date()} → {result['train_end'].date()}**  \n"
        f"Holdout period: **{result['test_start'].date()} → {result['test_end'].date()}**"
    )
    st.dataframe(result["hospital_error"].round({"MAE":1}), use_container_width=True, hide_index=True)
    st.caption("Hospital-level MAE shows whether aggregate performance hides weaker performance at a specific hospital.")
else:
    st.write("The split is chronological: earlier CMS reporting periods are training data and later periods are held out for evaluation.")

# 6
st.subheader("6. Feature Value / Ablation")
st.write(
    "The current historical implementation establishes the strongest honest baseline first: hospital + calendar features, then lagged outcome history. "
    "Weather, respiratory illness, event, and utilization histories should only be added once those signals are aligned to the same historical reporting periods."
)
st.caption("This avoids pretending that today's contextual data existed historically at the same granularity.")

st.divider()
st.caption("ERNow Model Lab · Real CMS longitudinal throughput validation when archive history is present · Not a live queue model.")
