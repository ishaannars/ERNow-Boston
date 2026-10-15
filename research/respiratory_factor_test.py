"""Factor test: does respiratory-illness season (CDC ILINet, state level) make ERNow's forecast more accurate?

    python research/respiratory_factor_test.py

Same contest as national_model.py: promotion needs a 2% validation gain over Persistence; rolling held-out years.
Also runs an ORACLE check with perfect knowledge of the coming season (upper bound, not deployable).
"""
import sys, json, numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import national_model as nm
from sklearn.metrics import mean_absolute_error

ABBR = {'Alabama':'AL','Alaska':'AK','Arizona':'AZ','Arkansas':'AR','California':'CA','Colorado':'CO','Connecticut':'CT','Delaware':'DE','District of Columbia':'DC','Florida':'FL','Georgia':'GA','Hawaii':'HI','Idaho':'ID','Illinois':'IL','Indiana':'IN','Iowa':'IA','Kansas':'KS','Kentucky':'KY','Louisiana':'LA','Maine':'ME','Maryland':'MD','Massachusetts':'MA','Michigan':'MI','Minnesota':'MN','Mississippi':'MS','Missouri':'MO','Montana':'MT','Nebraska':'NE','Nevada':'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY','North Carolina':'NC','North Dakota':'ND','Ohio':'OH','Oklahoma':'OK','Oregon':'OR','Pennsylvania':'PA','Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD','Tennessee':'TN','Texas':'TX','Utah':'UT','Vermont':'VT','Virginia':'VA','Washington':'WA','West Virginia':'WV','Wisconsin':'WI','Wyoming':'WY','Puerto Rico':'PR'}
ili = pd.read_csv(ROOT / "data" / "cdc_ilinet_state.csv", skiprows=1)
ili = ili[ili["REGION"].isin(ABBR)]
ili["state"] = ili["REGION"].map(ABBR)
ili["ili"] = pd.to_numeric(ili["%UNWEIGHTED ILI"], errors="coerce")
ili["date"] = pd.to_datetime(ili["YEAR"].astype(str) + "-01-01") + pd.to_timedelta((ili["WEEK"] - 1) * 7, unit="D")
ili = ili.dropna(subset=["ili"])[["state", "date", "ili"]]
by_state = {s: g.set_index("date")["ili"].sort_index() for s, g in ili.groupby("state")}
def window_mean(state, end, months=12):
    s = by_state.get(state)
    if s is None or pd.isna(end): return np.nan
    v = s[(s.index > end - pd.DateOffset(months=months)) & (s.index <= end)]
    return float(v.mean()) if len(v) >= 20 else np.nan

panel = nm.load_panel(); df, snaps = nm.make_transitions(panel)
snap_dates = {i: pd.Timestamp(s) for i, s in enumerate(snaps)}
df = df.copy()
df["period_end"] = pd.to_datetime(df["op18b_period_end"])
# next period end (target window) per facility, for the oracle check only
df["target_period_end"] = df.groupby("facility_id")["period_end"].shift(-1)
keys = df[["state", "period_end"]].drop_duplicates()
cache = {(r.state, r.period_end): window_mean(r.state, r.period_end) for r in keys.itertuples()}
df["ili_current"] = [cache.get((s, e)) for s, e in zip(df["state"], df["period_end"])]
df["ili_prev"] = [window_mean(s, e - pd.DateOffset(years=1)) if pd.notna(e) else np.nan for s, e in zip(df["state"], df["period_end"])]
df["release_date"] = df["t"].map(snap_dates)
rk = df[["state", "release_date"]].drop_duplicates()
rc = {(r.state, r.release_date): window_mean(r.state, r.release_date) for r in rk.itertuples()}
df["ili_recent"] = [rc.get((s, d)) for s, d in zip(df["state"], df["release_date"])]
df["ili_change"] = df["ili_current"] - df["ili_prev"]
df["ili_recent_vs_current"] = df["ili_recent"] - df["ili_current"]
tk = df[["state", "target_period_end"]].dropna().drop_duplicates()
tc = {(r.state, r.target_period_end): window_mean(r.state, r.target_period_end) for r in tk.itertuples()}
df["ili_target_ORACLE"] = [tc.get((s, e)) for s, e in zip(df["state"], df["target_period_end"])]
df["ili_target_vs_current_ORACLE"] = df["ili_target_ORACLE"] - df["ili_current"]
print("ILI coverage:", df["ili_current"].notna().mean().round(3), "states missing:", sorted(set(df.state) - set(by_state))[:10])

DEPLOY = ["ili_current", "ili_change", "ili_recent", "ili_recent_vs_current"]
ORACLE = ["ili_target_ORACLE", "ili_target_vs_current_ORACLE"]
nm.NUMERIC += DEPLOY + ORACLE
full = nm.FEATURE_GROUPS["+ geography & peers (full)"]
lab = df[df["target"].notna()]; T = int(lab["t"].max())

def run_split(train, valid, test, extra):
    cols = full + extra
    res = {}
    for name, model in nm.candidate_models(cols).items():
        model.fit(train)
        res[name] = (mean_absolute_error(valid["target"], model.predict(valid)), mean_absolute_error(test["target"], model.predict(test)))
    return res

out = {}
train, valid, test = lab[lab.t <= T-2], lab[lab.t == T-1], lab[lab.t == T]
for label, extra in [("baseline features", []), ("+ respiratory (deployable)", DEPLOY), ("+ respiratory ORACLE (perfect future knowledge)", DEPLOY + ORACLE)]:
    r = run_split(train, valid, test, extra); out[label] = r
    pv, pt = r["Persistence baseline"]
    best = min((k for k in r if k != "Persistence baseline"), key=lambda k: r[k][0])
    gain = 1 - r[best][0] / pv
    print(f"\n== {label}\n  Persistence: valid {pv:.2f}  test {pt:.2f}")
    for k, (v, t) in r.items():
        if k != "Persistence baseline": print(f"  {k[:45]:45s} valid {v:.2f}  test {t:.2f}")
    print(f"  best challenger {best[:30]}: validation gain {gain:.1%} -> {'PROMOTED' if gain >= 0.02 else 'not promoted (needs 2%)'}")

# rolling: does +respiratory beat the same model without it, year by year?
print("\n== Rolling held-out years: GBM / Ridge test MAE, without vs with respiratory, and persistence")
rows=[]
for k in range(2, T + 1):
    tr, te = lab[lab.t < k], lab[lab.t == k]
    if len(tr) < 1000 or len(te) < 500: continue
    row = {"k": k, "release": str(snap_dates[k+1].date()) if k+1 in snap_dates else str(k)}
    row["persistence"] = mean_absolute_error(te["target"], te["lag1"])
    for tag, extra in [("base", []), ("resp", DEPLOY)]:
        ms = nm.candidate_models(full + extra)
        for name in ["Ridge regression", "Gradient boosting"]:
            ms[name].fit(tr); row[f"{name[:5]}_{tag}"] = mean_absolute_error(te["target"], ms[name].predict(te))
    rows.append(row); print({kk: (round(v, 2) if isinstance(v, float) else v) for kk, v in row.items()}, flush=True)
json.dump({"single_split": {k: {m: list(v) for m, v in r.items()} for k, r in out.items()}, "rolling": rows}, open(ROOT / "data" / "respiratory_factor_raw.json", "w"), indent=1)
