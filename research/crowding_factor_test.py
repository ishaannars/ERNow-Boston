"""ERNow update 42: does hospital crowding (inpatient beds in use) make the forecast more accurate?

    python research/crowding_factor_test.py

Data (download with scripts/download_crowding_data.py):
- Statewide: CDC NHSN Weekly Hospital Respiratory Data by Jurisdiction (ua7e-t2fy), % of inpatient beds
  occupied, Aug 2020 to now. Still published weekly, so ERNow COULD use it live.
- Per hospital: HHS COVID-19 Reported Patient Impact and Hospital Capacity by Facility (anag-cw7u), beds in
  use / beds, ICU in use / ICU beds, Jan 2020 to Apr 2024. Reporting ended May 2024, so ERNow could NOT use
  it live; tested only as an upper bound ("if hospital-level crowding were public, would it help?").

Rule written before running (same contest as national_model.py and the respiratory test):
- Promote only the live-usable statewide version, only if its best challenger beats Persistence by >= 2%
  on validation AND, across rolling held-out years, the challenger with crowding beats the same challenger
  without it on average. Otherwise Persistence stays and the result is reported.
- An ORACLE version (crowding during the very period being forecast) is reported as a ceiling only.
Every crowding feature uses only weeks before the forecast date, except the labeled ORACLE ones.
Writes data/crowding_factor_results.json.
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import national_model as nm  # noqa: E402

warnings.filterwarnings("ignore")
MIN_WEEKS = 20  # of ~52 in a 12-month window


def load_state():
    n = pd.read_csv(ROOT / "data" / "nhsn_state_hrd.csv.gz", low_memory=False)
    n["date"] = pd.to_datetime(n["weekendingdate"]).dt.tz_localize(None)
    n["occ"] = pd.to_numeric(n["pctinptbedsocc"], errors="coerce")
    n.loc[(n["occ"] <= 0) | (n["occ"] > 100), "occ"] = np.nan  # impossible values (data errors)
    n = n.dropna(subset=["occ"])
    return {s: g.set_index("date")["occ"].sort_index() for s, g in n.groupby("jurisdiction")}


def load_facility():
    h = pd.read_csv(ROOT / "data" / "hhs_facility_capacity.csv.gz", dtype={"ccn": str})
    h["date"] = pd.to_datetime(h["week"]).dt.tz_localize(None)
    for c in ("beds_used", "beds", "icu_used", "icu_beds"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
        h.loc[h[c] < 0, c] = np.nan  # -999999 = small count hidden for privacy
    h["occ"] = 100 * h["beds_used"] / h["beds"].where(h["beds"] > 0)
    h["icu"] = 100 * h["icu_used"] / h["icu_beds"].where(h["icu_beds"] > 0)
    h.loc[(h["occ"] > 120), "occ"] = np.nan
    h.loc[(h["icu"] > 120), "icu"] = np.nan
    occ = {c: g.set_index("date")["occ"].dropna().sort_index() for c, g in h.groupby("ccn")}
    icu = {c: g.set_index("date")["icu"].dropna().sort_index() for c, g in h.groupby("ccn")}
    return occ, icu


def window_mean(series_by_key, key, end, months=12):
    s = series_by_key.get(key)
    if s is None or pd.isna(end):
        return np.nan
    v = s[(s.index > end - pd.DateOffset(months=months)) & (s.index <= end)]
    return float(v.mean()) if len(v) >= MIN_WEEKS else np.nan


def add_features(df, snap_dates, by, key_col, prefix):
    keys_end = df[[key_col, "period_end"]].drop_duplicates()
    cur = {(k, e): window_mean(by, k, e) for k, e in keys_end.itertuples(index=False)}
    prev = {(k, e): window_mean(by, k, e - pd.DateOffset(years=1)) if pd.notna(e) else np.nan
            for k, e in keys_end.itertuples(index=False)}
    keys_rel = df[[key_col, "release_date"]].drop_duplicates()
    rec = {(k, d): window_mean(by, k, d) for k, d in keys_rel.itertuples(index=False)}
    keys_tgt = df[[key_col, "target_period_end"]].dropna().drop_duplicates()
    tgt = {(k, e): window_mean(by, k, e) for k, e in keys_tgt.itertuples(index=False)}
    pairs_e = list(zip(df[key_col], df["period_end"]))
    df[f"{prefix}_current"] = [cur.get(p) for p in pairs_e]
    df[f"{prefix}_change"] = df[f"{prefix}_current"] - np.array([prev.get(p) for p in pairs_e], dtype=float)
    df[f"{prefix}_recent"] = [rec.get(p) for p in zip(df[key_col], df["release_date"])]
    df[f"{prefix}_recent_vs_current"] = df[f"{prefix}_recent"] - df[f"{prefix}_current"]
    df[f"{prefix}_target_ORACLE"] = [tgt.get(p) for p in zip(df[key_col], df["target_period_end"])]
    df[f"{prefix}_target_vs_current_ORACLE"] = df[f"{prefix}_target_ORACLE"] - df[f"{prefix}_current"]
    live = [f"{prefix}_current", f"{prefix}_change", f"{prefix}_recent", f"{prefix}_recent_vs_current"]
    return live, [f"{prefix}_target_ORACLE", f"{prefix}_target_vs_current_ORACLE"]


def main():
    panel = nm.load_panel()
    df, snaps = nm.make_transitions(panel)
    snap_dates = {i: pd.Timestamp(s) for i, s in enumerate(snaps)}
    df = df.copy()
    df["period_end"] = pd.to_datetime(df["op18b_period_end"])
    df["target_period_end"] = df.groupby("facility_id")["period_end"].shift(-1)
    df["release_date"] = df["t"].map(snap_dates)

    state = load_state()
    s_live, s_oracle = add_features(df, snap_dates, state, "state", "occ_state")
    occ, icu = load_facility()
    f_live, f_oracle = add_features(df, snap_dates, occ, "facility_id", "occ_hosp")
    i_live, _ = add_features(df, snap_dates, icu, "facility_id", "icu_hosp")
    f_live = f_live + i_live[:2]
    nm.NUMERIC += s_live + s_oracle + f_live + f_oracle + i_live + [c for c in df.columns if c.startswith("icu_hosp_target")]

    full = nm.FEATURE_GROUPS["+ geography & peers (full)"]
    lab = df[df["target"].notna()]
    T = int(lab["t"].max())
    cov = {name: {str(snap_dates[k + 1].date()) if k + 1 in snap_dates else str(k): round(float(lab.loc[lab.t == k, col].notna().mean()), 3)
                  for k in sorted(lab.t.unique())}
           for name, col in [("statewide (live-usable)", "occ_state_current"), ("per hospital (ended 2024)", "occ_hosp_current")]}
    print("Coverage by target release:", json.dumps(cov, indent=1), flush=True)

    out = {"single_split": {}, "rolling": [], "coverage_by_target_release": cov}
    train, valid, test = lab[lab.t <= T - 2], lab[lab.t == T - 1], lab[lab.t == T]
    for label, extra in [("baseline features", []), ("+ statewide crowding (live-usable)", s_live),
                         ("+ statewide crowding ORACLE", s_live + s_oracle)]:
        res = {}
        for name, model in nm.candidate_models(full + extra).items():
            model.fit(train)
            res[name] = [float(mean_absolute_error(valid["target"], model.predict(valid))),
                         float(mean_absolute_error(test["target"], model.predict(test)))]
        out["single_split"][label] = res
        pv = res["Persistence baseline"][0]
        best = min((k for k in res if k != "Persistence baseline"), key=lambda k: res[k][0])
        print(f"== {label}: Persistence valid {pv:.2f} | best {best[:22]} valid {res[best][0]:.2f} "
              f"(gain {1 - res[best][0] / pv:+.1%})", flush=True)

    for k in range(2, T + 1):
        tr, te = lab[lab.t < k], lab[lab.t == k]
        if len(tr) < 1000 or len(te) < 500:
            continue
        row = {"k": k, "release": str(snap_dates[k + 1].date()) if k + 1 in snap_dates else str(k),
               "persistence": float(mean_absolute_error(te["target"], te["lag1"]))}
        variants = [("base", []), ("state", s_live)]
        if te["occ_hosp_current"].notna().mean() >= 0.5:
            variants.append(("hosp", f_live))
        for tag, extra in variants:
            ms = nm.candidate_models(full + extra)
            for name in ("Ridge regression", "Gradient boosting"):
                ms[name].fit(tr)
                row[f"{name[:5]}_{tag}"] = float(mean_absolute_error(te["target"], ms[name].predict(te)))
        out["rolling"].append(row)
        print({kk: (round(v, 2) if isinstance(v, float) else v) for kk, v in row.items()}, flush=True)

    # Decision under the pre-set rule
    ss = out["single_split"]
    pv = ss["+ statewide crowding (live-usable)"]["Persistence baseline"][0]
    live = ss["+ statewide crowding (live-usable)"]
    best = min((k for k in live if k != "Persistence baseline"), key=lambda k: live[k][0])
    gain = 1 - live[best][0] / pv
    roll = out["rolling"]
    def avg_diff(tag):
        rows = [r for r in roll if f"Gradi_{tag}" in r]
        if not rows:
            return None, 0
        return float(np.mean([r[f"Gradi_{tag}"] - r["Gradi_base"] for r in rows])), len(rows)
    sd, sn = avg_diff("state")
    hd, hn = avg_diff("hosp")
    promoted = bool(gain >= nm.PROMOTION_MARGIN and sd is not None and sd < 0)
    oracle = ss["+ statewide crowding ORACLE"]
    obest = min((k for k in oracle if k != "Persistence baseline"), key=lambda k: oracle[k][0])
    out.update({
        "method": " ".join(__doc__.split("\n\n")[1:3]).replace("\n", " "),
        "statewide_best_challenger": best, "statewide_validation_gain_vs_persistence": round(float(gain), 4),
        "statewide_oracle_validation_gain_vs_persistence": round(float(1 - oracle[obest][0] / pv), 4),
        "rolling_gbm_minutes_change_statewide": None if sd is None else round(sd, 3), "rolling_years_statewide": sn,
        "rolling_gbm_minutes_change_per_hospital": None if hd is None else round(hd, 3), "rolling_years_per_hospital": hn,
        "gbm_validation_without_crowding": round(ss["baseline features"]["Gradient boosting"][0], 3),
        "gbm_validation_with_crowding": round(live["Gradient boosting"][0], 3),
        "gbm_validation_with_crowding_ORACLE": round(oracle["Gradient boosting"][0], 3),
        "gbm_test_without_crowding": round(ss["baseline features"]["Gradient boosting"][1], 3),
        "gbm_test_with_crowding": round(live["Gradient boosting"][1], 3),
        "persistence_validation": round(pv, 3), "persistence_test": round(live["Persistence baseline"][1], 3),
        "gbm_gain_from_crowding_validation": round(1 - live["Gradient boosting"][0] / ss["baseline features"]["Gradient boosting"][0], 4),
        "promoted": promoted,
        "conclusion": ("Promoted: statewide crowding cleared the pre-set rule." if promoted else
                       "Not promoted: statewide crowding did not clear the pre-set rule, so Persistence stays."),
    })
    (ROOT / "data" / "crowding_factor_results.json").write_text(json.dumps(out, indent=1))
    print(out["conclusion"])
    print({k: out[k] for k in ("gbm_validation_without_crowding", "gbm_validation_with_crowding", "persistence_validation",
                               "gbm_gain_from_crowding_validation", "statewide_validation_gain_vs_persistence", "statewide_oracle_validation_gain_vs_persistence",
                               "rolling_gbm_minutes_change_statewide", "rolling_gbm_minutes_change_per_hospital",
                               "rolling_years_per_hospital")})


if __name__ == "__main__":
    main()
