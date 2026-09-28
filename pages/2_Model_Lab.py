from pathlib import Path

import pandas as pd
import streamlit as st

from modeling import TEMPLATE_PATH, train_and_compare, training_status

st.set_page_config(page_title="ERNow Model Lab", page_icon="✚", layout="wide")
BASE = Path(__file__).resolve().parents[1]
HOSPITAL_DATA = BASE / "data" / "boston_er_data.csv"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');
:root{--ivory:#F8F4E6;--shell:#FFFDF5;--ink:#1C1B19;--soft:#403A32;--tea:#B9AD91;--moss:#48513C;--beni:#8C2F2F;--kakishibu:#A85B45;--wash:rgba(168,91,69,.10)}
html,body,[class*="css"],.stApp{font-family:'Instrument Sans','Helvetica Neue',Arial,sans-serif}
.stApp{background:var(--ivory);color:var(--ink)}
.block-container{padding-top:5.4rem!important;padding-bottom:2rem;max-width:960px}
[data-testid="stSidebar"],[data-testid="collapsedControl"]{display:none!important}
.safety-banner{display:block;width:100%;box-sizing:border-box;background:var(--beni);color:#fff!important;border-radius:16px;padding:16px 19px;font-size:1rem;line-height:1.5;font-weight:650;margin:0 0 .9rem 0}
.safety-banner,.safety-banner *{color:#fff!important}
.nav-wrap{border-bottom:1px solid var(--tea);padding-bottom:.55rem;margin-bottom:1.15rem}
[data-testid="stPageLink-NavLink"]{background:var(--shell)!important;border:1px solid var(--tea)!important;border-radius:10px!important;color:var(--ink)!important;font-weight:650!important}
[data-testid="stPageLink-NavLink"] *{color:var(--ink)!important}
[data-testid="stPageLink-NavLink"] .material-symbols-rounded{color:var(--beni)!important}
.status-card{background:var(--shell);border:1px solid var(--tea);border-left:4px solid var(--moss);border-radius:14px;padding:1rem 1.05rem;margin:.6rem 0 1rem 0}
.status-title{font-weight:700;color:var(--ink);margin-bottom:.2rem}.status-copy{color:var(--soft);font-size:.9rem;line-height:1.45}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="safety-banner">🚨 <strong>Possible emergency?</strong> Call 911 or go to the nearest appropriate emergency department. ERNow model analysis is not a clinical decision tool.</div>
""", unsafe_allow_html=True)

st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
nav1, nav2, nav3, _ = st.columns([1, 1.15, 1, 3.85])
with nav1:
    st.page_link("app.py", label="ERNow", icon=":material/emergency:", use_container_width=True)
with nav2:
    st.page_link("pages/1_Methodology.py", label="Methodology", icon=":material/menu_book:", use_container_width=True)
with nav3:
    st.page_link("pages/2_Model_Lab.py", label="Model Lab", icon=":material/monitoring:", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.title("Model Lab")
st.caption("Data-science layer for training, comparing, and validating ER wait prediction models.")

status = training_status()
if status["ready"]:
    st.markdown("""
<div class="status-card"><div class="status-title">Supervised training dataset detected</div><div class="status-copy">ERNow will use a chronological holdout set so future observations are tested against models trained only on earlier observations.</div></div>
""", unsafe_allow_html=True)
    result = train_and_compare(status["data"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Training rows", result["train_rows"])
    c2.metric("Holdout rows", result["test_rows"])
    c3.metric("Best holdout model", result["best_model_name"])

    st.subheader("Model comparison")
    metrics = result["metrics"].copy()
    metrics["MAE"] = metrics["MAE"].round(1)
    metrics["RMSE"] = metrics["RMSE"].round(1)
    metrics["R2"] = metrics["R2"].round(3)
    st.dataframe(metrics, use_container_width=True, hide_index=True)
    st.caption("MAE and RMSE are in minutes. Models are ranked on the chronological holdout set, not on training fit.")

    st.subheader("Time-based validation")
    st.write(
        f"Training window: **{result['train_start']} → {result['train_end']}**  "
        f"\nHoldout window: **{result['test_start']} → {result['test_end']}**"
    )

    importance = result["feature_importance"]
    if not importance.empty:
        st.subheader("Most influential features")
        st.caption(f"Interpretation model: {result['interpret_model_name']}")
        st.bar_chart(importance.set_index("Feature")["Importance"])
        st.caption("Importance is model-specific and does not prove causation.")
else:
    warning_text = " ".join(status["warnings"]) if status["warnings"] else "Validated labeled history is not connected yet."
    st.markdown(
        f"""
<div class="status-card"><div class="status-title">Supervised learning pipeline ready — labeled history still required</div><div class="status-copy">{warning_text} ERNow will not invent training rows or accuracy scores. Until validated historical wait observations are connected, the consumer ranking remains the transparent bounded forecasting model shown on the Methodology page.</div></div>
""",
        unsafe_allow_html=True,
    )

    st.subheader("What the training pipeline will do")
    st.markdown("""
- Engineer temporal features such as hour, day of week, month, and weekend status.
- Combine hospital throughput/utilization with weather, respiratory illness, holidays, and major-event indicators when those historical features are available.
- Compare a median baseline, linear regression, Ridge regression, and Random Forest.
- Split data chronologically so the test period occurs **after** the training period.
- Report **MAE, RMSE, and R²** on the holdout period.
- Expose feature importance or coefficient magnitude for model interpretation.
""")

    if TEMPLATE_PATH.exists():
        st.caption("A schema-only template is included at `data/ernow_historical_template.csv`. It contains no fabricated observations.")

st.divider()
st.subheader("Current hospital feature analysis")
base = pd.read_csv(HOSPITAL_DATA)
show_cols = [
    "hospital",
    "legacy_wait_to_provider_min",
    "typical_ed_minutes",
    "recent_ed_visits",
    "recent_occupancy_pct",
]
st.dataframe(base[show_cols], use_container_width=True, hide_index=True)

left, right = st.columns(2)
with left:
    st.caption("Recent reported ED visits by hospital")
    st.bar_chart(base.set_index("hospital")["recent_ed_visits"])
with right:
    st.caption("Reported occupancy by hospital")
    st.bar_chart(base.set_index("hospital")["recent_occupancy_pct"])

st.subheader("Why this is separate from the live ranking")
st.write(
    "The production ranking currently uses explicit, bounded adjustments because ERNow does not yet have a sufficiently large, validated historical series of observed wait-to-provider targets across all six hospitals. The Model Lab is designed to replace or recalibrate those rules only after the learned model demonstrates better out-of-time performance."
)
st.caption("Descriptive relationships in the six-hospital table are exploratory only and should not be treated as causal findings.")
