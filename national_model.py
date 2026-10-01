"""ERNow national ED performance model.

Builds a panel of every U.S. hospital in the saved CMS Hospital Compare archives, trains
and compares forecasting models for next-period ED visit duration (CMS OP-18b), builds
tested 80% prediction intervals (conformalized quantile regression), and evaluates
ranking accuracy, feature groups, drivers, and peers. Writes small result files that the
Streamlit app reads, so the deployed app never needs the 87 MB of archives.

Run (from the repo root, with the archives in data/cms_archives/):
    python national_model.py

Outputs:
    data/national_ed_panel.csv.gz   one row per hospital x CMS release
    data/national_results.json      metrics, coverage, ranking, ablation, drivers, evidence
    data/boston_forecast.csv        Boston forecasts, 80% ranges, peers, change flags
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent
ARCHIVES = ROOT / "data" / "cms_archives"
PANEL_PATH = ROOT / "data" / "national_ed_panel.csv.gz"
RESULTS_PATH = ROOT / "data" / "national_results.json"
BOSTON_PATH = ROOT / "data" / "boston_forecast.csv"
BOSTON_CSV = ROOT / "data" / "boston_er_data.csv"

MEASURES = ["OP_18a", "OP_18b", "OP_18c", "OP_18d", "OP_22", "EDV"]
EDV_ORDER = {"low": 1, "medium": 2, "high": 3, "very high": 4}
PROMOTION_MARGIN = 0.02      # a learned model must beat Persistence MAE by 2% on validation
COVERAGE_TARGET = 0.80       # 80% prediction intervals
SEED = 7


# ----------------------------------------------------------------------------------------
# 1. Panel
# ----------------------------------------------------------------------------------------
def _find(names, pattern):
    hits = [n for n in names if re.search(pattern, n, re.I) and "__MACOSX" not in n and "REH_" not in n]
    return hits[0] if hits else None


def _snapshot_date(zip_name):
    m = re.search(r"(\d{4})(\d{2})", zip_name)
    return pd.Timestamp(int(m.group(1)), int(m.group(2)), 1)


def build_panel():
    frames = []
    for zpath in sorted(ARCHIVES.glob("hospitals_compare_*.zip")):
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            tec = _find(names, r"Timely_and_Effective_Care-Hospital\.csv$")
            gen = _find(names, r"Hospital_General_Information\.csv$")
            if not tec or not gen:
                continue
            t = pd.read_csv(io.BytesIO(z.read(tec)), dtype=str, encoding="latin-1")
            g = pd.read_csv(io.BytesIO(z.read(gen)), dtype=str, encoding="latin-1")
        t = t[t["Measure ID"].isin(MEASURES)]
        wide = t.pivot_table(index="Facility ID", columns="Measure ID", values="Score", aggfunc="first")
        ends = t[t["Measure ID"] == "OP_18b"].groupby("Facility ID")["End Date"].first()
        wide = wide.join(ends.rename("op18b_period_end"))
        gcols = {c.lower(): c for c in g.columns}
        g = g.rename(columns={
            gcols.get("facility id"): "facility_id", gcols.get("facility name"): "facility_name",
            gcols.get("state"): "state",
            (gcols.get("city/town") or gcols.get("city")): "city",
            (gcols.get("county/parish") or gcols.get("county name")): "county",
            gcols.get("hospital type"): "hospital_type", gcols.get("hospital ownership"): "ownership",
            gcols.get("hospital overall rating"): "rating",
        })
        g = g[["facility_id", "facility_name", "state", "city", "county", "hospital_type", "ownership", "rating"]]
        df = wide.reset_index().rename(columns={"Facility ID": "facility_id"}).merge(g, on="facility_id", how="left")
        df["snapshot"] = _snapshot_date(zpath.name)
        frames.append(df)
    if not frames:
        raise SystemExit("No CMS archives found in data/cms_archives/.")
    panel = pd.concat(frames, ignore_index=True)
    for m in ["OP_18a", "OP_18b", "OP_18c", "OP_18d", "OP_22"]:
        panel[m] = pd.to_numeric(panel.get(m), errors="coerce")
    panel["edv"] = panel.get("EDV").astype(str).str.strip().str.lower().map(EDV_ORDER)
    panel["rating"] = pd.to_numeric(panel["rating"], errors="coerce")
    panel["county"] = panel["county"].astype(str).str.upper().str.strip()
    panel["city"] = panel["city"].astype(str).str.upper().str.strip()
    panel["op18b_period_end"] = pd.to_datetime(panel["op18b_period_end"], errors="coerce")
    panel = panel.drop(columns=["EDV"], errors="ignore")
    panel = panel.rename(columns={"OP_18a": "op18a", "OP_18b": "op18b", "OP_18c": "op18c",
                                  "OP_18d": "op18d", "OP_22": "op22"})
    panel = panel.sort_values(["facility_id", "snapshot"]).reset_index(drop=True)
    PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(PANEL_PATH, index=False, compression="gzip")
    return panel


def load_acuity():
    """Public case-complexity proxies from the newest archive's Complications & Deaths file:
    heart-attack + stroke patient volume, whether the hospital does cardiac (CABG) surgery,
    and inpatient volume (PSI-03 denominator). Larger, more specialized hospitals treat
    sicker patients, which lengthens ED stays for reasons that are not worse care."""
    zips = sorted(ARCHIVES.glob("hospitals_compare_*.zip"))
    if not zips:
        return pd.DataFrame(columns=["facility_id"])
    with zipfile.ZipFile(zips[-1]) as z:
        name = _find(z.namelist(), r"Complications_and_Deaths-Hospital\.csv$")
        if not name:
            return pd.DataFrame(columns=["facility_id"])
        c = pd.read_csv(io.BytesIO(z.read(name)), dtype=str, encoding="latin-1")
    c["den"] = pd.to_numeric(c.get("Denominator"), errors="coerce")
    w = c.pivot_table(index="Facility ID", columns="Measure ID", values="den", aggfunc="first")
    out = pd.DataFrame(index=w.index)
    out["serious_volume"] = np.log1p(w.get("MORT_30_AMI", 0).fillna(0) + w.get("MORT_30_STK", 0).fillna(0))
    out["cardiac_surgery"] = (w.get("MORT_30_CABG", pd.Series(0, index=w.index)).fillna(0) > 0).astype(float)
    out["inpatient_volume"] = np.log1p(w.get("PSI_03", pd.Series(0, index=w.index)).fillna(0))
    return out.reset_index().rename(columns={"Facility ID": "facility_id"})


def load_panel():
    if not PANEL_PATH.exists():
        return build_panel()
    p = pd.read_csv(PANEL_PATH, dtype={"facility_id": str}, parse_dates=["snapshot", "op18b_period_end"])
    return p


# ----------------------------------------------------------------------------------------
# 2. Supervised transitions: features at release t -> OP-18b at release t+1
# ----------------------------------------------------------------------------------------
HISTORY = ["lag1", "lag2", "delta"]
# OP-18a and OP-18d only appear in the newest release, so they cannot be used for training.
ED_MEASURES = ["op18c", "op22"]
HOSPITAL = ["edv", "rating", "hospital_type", "ownership"]
GEOGRAPHY = ["state", "state_mean_gap", "peer_mean_gap"]
NUMERIC = ["lag1", "lag2", "delta", "op18c", "op22", "edv", "rating",
           "state_mean_gap", "peer_mean_gap"]
CATEGORICAL = ["hospital_type", "ownership", "state"]
FEATURE_GROUPS = {"History only": HISTORY,
                  "+ other ED measures": HISTORY + ED_MEASURES,
                  "+ hospital characteristics": HISTORY + ED_MEASURES + HOSPITAL,
                  "+ geography & peers (full)": HISTORY + ED_MEASURES + HOSPITAL + GEOGRAPHY}


def make_transitions(panel):
    snaps = sorted(panel["snapshot"].unique())
    p = panel.copy()
    p["t"] = p["snapshot"].map({s: i for i, s in enumerate(snaps)})
    p = p.sort_values(["facility_id", "t"])
    p["lag1"] = p["op18b"]
    p["lag2"] = p.groupby("facility_id")["op18b"].shift(1)
    p["delta"] = p["lag1"] - p["lag2"]
    p["target"] = p.groupby("facility_id")["op18b"].shift(-1)
    # same-release state and peer (volume x type) means: partial pooling inputs
    p["state_mean_gap"] = p.groupby(["t", "state"])["op18b"].transform("mean") - p["lag1"]
    p["peer_mean_gap"] = p.groupby(["t", "edv", "hospital_type"])["op18b"].transform("mean") - p["lag1"]
    p = p[p["lag1"].notna()].copy()
    return p, snaps


def _pre(cols):
    num = [c for c in cols if c in NUMERIC]
    cat = [c for c in cols if c in CATEGORICAL]
    return ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                          ("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=10))]), cat),
    ])


def _gbm(loss="squared_error", quantile=None):
    kw = dict(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=40,
              l2_regularization=1.0, random_state=SEED)
    if loss == "quantile":
        return HistGradientBoostingRegressor(loss="quantile", quantile=quantile, **kw)
    return HistGradientBoostingRegressor(**kw)


def _gbm_pipe(cols, loss="squared_error", quantile=None):
    cat = [c for c in cols if c in CATEGORICAL]
    num = [c for c in cols if c in NUMERIC]
    pre = ColumnTransformer([
        ("num", "passthrough", num),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=False), cat),
    ])
    return Pipeline([("pre", pre), ("m", _gbm(loss, quantile))])


class DeltaModel:
    """Predicts the change from the last value, then adds it back (stable for panels)."""

    def __init__(self, pipe, cols):
        self.pipe, self.cols = pipe, cols

    def fit(self, df):
        X = df[self.cols].copy()
        self.pipe.fit(X, df["target"] - df["lag1"])
        return self

    def predict(self, df):
        return df["lag1"].to_numpy() + self.pipe.predict(df[self.cols].copy())


class PartialPooling:
    """Shrink each hospital's last value toward its state and peer (volume x type) means,
    with a damped trend term. Weights fit by least absolute error on training data, so a
    few extreme hospitals cannot dominate (robust partial pooling)."""

    grid_a = np.linspace(-0.3, 0.3, 13)
    grid_b = np.linspace(0.0, 0.5, 11)
    grid_c = np.linspace(0.0, 0.5, 11)

    def fit(self, df):
        d, sg, pg = df["delta"].fillna(0).to_numpy(), df["state_mean_gap"].fillna(0).to_numpy(), df["peer_mean_gap"].fillna(0).to_numpy()
        y, l1 = df["target"].to_numpy(), df["lag1"].to_numpy()
        best = None
        for a in self.grid_a:
            for b in self.grid_b:
                for c in self.grid_c:
                    e = np.mean(np.abs(y - (l1 + a * d + b * sg + c * pg)))
                    if best is None or e < best[0]:
                        best = (e, a, b, c)
        _, self.a, self.b, self.c = best
        return self

    def predict(self, df):
        return (df["lag1"] + self.a * df["delta"].fillna(0) + self.b * df["state_mean_gap"].fillna(0)
                + self.c * df["peer_mean_gap"].fillna(0)).to_numpy()


class Persistence:
    def fit(self, df):
        return self

    def predict(self, df):
        return df["lag1"].to_numpy()


def candidate_models(cols=None):
    full = cols or FEATURE_GROUPS["+ geography & peers (full)"]
    return {
        "Persistence baseline": Persistence(),
        "Ridge regression": DeltaModel(Pipeline([("pre", _pre(full)), ("m", Ridge(alpha=10.0))]), full),
        "Partial pooling (shrink toward state & peer means)": PartialPooling(),
        "Gradient boosting": DeltaModel(_gbm_pipe(full), full),
    }


def _metrics(y, yhat):
    return {"MAE": float(mean_absolute_error(y, yhat)),
            "RMSE": float(np.sqrt(mean_squared_error(y, yhat))),
            "R2": float(r2_score(y, yhat))}


# ----------------------------------------------------------------------------------------
# 3. Tested intervals: conformalized quantile regression (CQR)
# ----------------------------------------------------------------------------------------
def _mad(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    return float(np.median(np.abs(x - np.median(x)))) if len(x) else 1.0


class CQR:
    """Conformalized quantile regression with a volatility (regime) adjustment.

    Year-to-year ED changes are calmer in some years than others, so a range calibrated on
    one year over- or under-covers the next. At prediction time we already know how much
    hospitals changed in the latest release (lag1 - lag2), so the calibrated half-width is
    scaled by recent national volatility / calibration-period volatility. Nothing from the
    period being predicted is used.
    """

    def __init__(self, cols, alpha=1 - COVERAGE_TARGET):
        self.cols, self.alpha = cols, alpha
        self.lo = DeltaModel(_gbm_pipe(cols, "quantile", alpha / 2), cols)
        self.hi = DeltaModel(_gbm_pipe(cols, "quantile", 1 - alpha / 2), cols)
        self.q = 0.0

    def fit(self, train, calib):
        self.lo.fit(train)
        self.hi.fit(train)
        lo, hi = self.lo.predict(calib), self.hi.predict(calib)
        y = calib["target"].to_numpy()
        scores = np.maximum(lo - y, y - hi)
        n = len(scores)
        level = min(1.0, np.ceil((n + 1) * (1 - self.alpha)) / n)
        self.q = float(np.quantile(scores, level, method="higher"))
        self.calib_vol = _mad(calib["delta"]) or 1.0
        return self

    def predict(self, df, adaptive=True):
        lo, hi = self.lo.predict(df) - self.q, self.hi.predict(df) + self.q
        lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
        if adaptive:
            ratio = (_mad(df["delta"]) or self.calib_vol) / self.calib_vol
            center, half = (lo + hi) / 2, (hi - lo) / 2 * ratio
            lo, hi = center - half, center + half
        return lo, hi


# ----------------------------------------------------------------------------------------
# 4. Ranking evaluation: does the predicted order match what happened?
# ----------------------------------------------------------------------------------------
def _spearman(a, b):
    a, b = pd.Series(a).rank(), pd.Series(b).rank()
    if a.nunique() < 2 or b.nunique() < 2:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def ranking_eval(test, pred_col):
    out = {"national_spearman": _spearman(test[pred_col], test["target"])}
    groups = [g for _, g in test.groupby(["state", "county"]) if len(g) >= 3]
    rhos, hits, chance = [], [], []
    for g in groups:
        rhos.append(_spearman(g[pred_col], g["target"]))
        hits.append(float(g[pred_col].idxmin() == g["target"].idxmin()))
        chance.append(1.0 / len(g))
    out.update({"local_groups": len(groups),
                "mean_local_spearman": float(np.nanmean(rhos)) if rhos else None,
                "fastest_pick_accuracy": float(np.mean(hits)) if hits else None,
                "fastest_pick_random_baseline": float(np.mean(chance)) if chance else None})
    return out


# ----------------------------------------------------------------------------------------
# 5. Main pipeline
# ----------------------------------------------------------------------------------------
def run():
    panel = load_panel()
    df, snaps = make_transitions(panel)
    labeled = df[df["target"].notna()]
    T = int(labeled["t"].max())                    # last labeled transition (test)
    train = labeled[labeled["t"] <= T - 2]
    valid = labeled[labeled["t"] == T - 1]         # model selection + conformal calibration
    test = labeled[labeled["t"] == T]              # untouched final test
    full_cols = FEATURE_GROUPS["+ geography & peers (full)"]

    # --- model comparison: fit on train, select on validation, report on test
    results, val_mae, fitted = [], {}, {}
    for name, model in candidate_models().items():
        model.fit(train)
        fitted[name] = model
        val_mae[name] = mean_absolute_error(valid["target"], model.predict(valid))
        m = _metrics(test["target"], model.predict(test))
        results.append({"model": name, "validation_MAE": float(val_mae[name]), **m})
    base_val = val_mae["Persistence baseline"]
    learned = {k: v for k, v in val_mae.items() if k != "Persistence baseline"}
    best_learned = min(learned, key=learned.get)
    promoted = learned[best_learned] <= base_val * (1 - PROMOTION_MARGIN)
    selected = best_learned if promoted else "Persistence baseline"
    test = test.copy()
    test["pred_selected"] = fitted[selected].predict(test)
    test["pred_persistence"] = test["lag1"]

    # --- tested 80% intervals: fit on train, calibrate on validation, measure on test
    cqr = CQR(full_cols).fit(train, valid)
    lo, hi = cqr.predict(test)
    y = test["target"].to_numpy()
    coverage = float(np.mean((y >= lo) & (y <= hi)))
    width = float(np.median(hi - lo))
    hit = ((y >= lo) & (y <= hi)).astype(float)
    cov_ci = [float(np.percentile(np.random.default_rng(SEED).choice(hit, (2000, len(hit))).mean(1), q)) for q in (2.5, 97.5)]
    slo, shi = cqr.predict(test, adaptive=False)
    static_cov, static_width = float(np.mean((y >= slo) & (y <= shi))), float(np.median(shi - slo))
    # earlier held-out year (the method was chosen on this fold, before looking at the final test)
    bt_train, bt_cal, bt_test = labeled[labeled["t"] <= T - 3], labeled[labeled["t"] == T - 2], labeled[labeled["t"] == T - 1]
    bcqr = CQR(full_cols).fit(bt_train, bt_cal)
    blo, bhi = bcqr.predict(bt_test)
    by = bt_test["target"].to_numpy()
    backtest_cov, backtest_width = float(np.mean((by >= blo) & (by <= bhi))), float(np.median(bhi - blo))
    old_band = float(np.mean((y >= 0.65 * test["lag1"]) & (y <= 1.55 * test["lag1"])))
    old_width = float(np.median(0.90 * test["lag1"]))
    cov_by_volume = (pd.DataFrame({"edv": test["edv"], "hit": (y >= lo) & (y <= hi)})
                     .groupby("edv")["hit"].mean().rename(index={1: "low", 2: "medium", 3: "high", 4: "very high"}))

    # --- ranking accuracy
    ranking = {"selected": ranking_eval(test, "pred_selected"),
               "persistence": ranking_eval(test, "pred_persistence")}

    # --- statistical confidence: bootstrap the test release (2,000 resamples, by hospital / by county)
    rng = np.random.default_rng(SEED)
    B = 2000
    y_t = test["target"].to_numpy()
    err_p = np.abs(y_t - test["lag1"].to_numpy())
    err_c = np.abs(y_t - fitted[best_learned].predict(test))
    n_t = len(test)
    idx = rng.integers(0, n_t, (B, n_t))
    diff = err_p[idx].mean(1) - err_c[idx].mean(1)            # >0 means the challenger is better
    groups = [g for _, g in test.groupby(["state", "county"]) if len(g) >= 3]
    hits = np.array([float(g["pred_selected"].idxmin() == g["target"].idxmin()) for g in groups])
    gidx = rng.integers(0, len(hits), (B, len(hits)))
    pick = hits[gidx].mean(1)
    confidence = {
        "resamples": B,
        "mae_gain_vs_best_challenger_min": float(diff.mean()),
        "mae_gain_ci95": [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))],
        "fastest_pick_ci95": [float(np.percentile(pick, 2.5)), float(np.percentile(pick, 97.5))],
    }

    # --- ablation: gradient boosting with growing feature groups
    ablation = []
    for gname, cols in FEATURE_GROUPS.items():
        m = DeltaModel(_gbm_pipe(cols), cols).fit(train)
        ablation.append({"features": gname, "test_MAE": float(mean_absolute_error(test["target"], m.predict(test)))})
    ablation.insert(0, {"features": "Persistence (no features)",
                        "test_MAE": float(mean_absolute_error(test["target"], test["lag1"]))})

    # --- drivers: permutation importance of the full gradient-boosting model on test
    gb = fitted["Gradient boosting"]
    Xt = test[full_cols].copy()
    pi = permutation_importance(gb.pipe, Xt, test["target"] - test["lag1"], n_repeats=5,
                                random_state=SEED, scoring="neg_mean_absolute_error")
    drivers = sorted([{"feature": c, "importance_min": float(v)} for c, v in zip(full_cols, pi.importances_mean)],
                     key=lambda d: -d["importance_min"])

    # --- structural differences (who waits longest), latest release
    latest = panel[panel["snapshot"] == panel["snapshot"].max()].copy()
    vol = latest.dropna(subset=["op18b"]).groupby("edv").agg(
        hospitals=("op18b", "size"), median_op18b=("op18b", "median"), median_op22=("op22", "median"))
    vol.index = vol.index.map({1: "low", 2: "medium", 3: "high", 4: "very high"})
    own = latest.dropna(subset=["op18b"]).groupby("ownership").agg(
        hospitals=("op18b", "size"), median_op18b=("op18b", "median"), median_op22=("op22", "median"))
    own = own[own["hospitals"] >= 30].sort_values("median_op18b", ascending=False)
    corr_op22 = float(latest[["op18b", "op22"]].corr(method="spearman").iloc[0, 1])

    # --- deployment: refit on train+valid, calibrate on test, forecast the next release
    deploy_train = labeled[labeled["t"] <= T - 1]
    final = candidate_models()[selected].fit(deploy_train)
    final_cqr = CQR(full_cols).fit(deploy_train, test)
    now = df[df["t"] == df["t"].max()].copy()
    now["forecast"] = final.predict(now)
    now["lo80"], now["hi80"] = final_cqr.predict(now)
    # keep the stated range consistent with the selected point forecast
    now["lo80"] = np.minimum(now["lo80"], now["forecast"])
    now["hi80"] = np.maximum(now["hi80"], now["forecast"])

    # --- peers: nearest hospitals nationally on structure (not on the outcome)
    acu = load_acuity()
    now = now.merge(acu, on="facility_id", how="left") if len(acu) else now
    for c in ["serious_volume", "cardiac_surgery", "inpatient_volume"]:
        if c not in now:
            now[c] = 0.0
        now[c] = now[c].fillna(0.0)
    feat = now[["edv", "rating", "serious_volume", "cardiac_surgery", "inpatient_volume"]].copy()
    feat["edv"] = feat["edv"].fillna(feat["edv"].median())
    feat["rating"] = feat["rating"].fillna(feat["rating"].median())
    feat[["serious_volume", "inpatient_volume", "cardiac_surgery"]] *= 1.5   # weight case complexity
    feat = pd.concat([feat, pd.get_dummies(now[["hospital_type", "ownership"]].fillna("Unknown"), dtype=float) * 2.0], axis=1)
    scale = feat.std().replace(0, 1)
    featn = (feat - feat.mean()) / scale
    nn = NearestNeighbors(n_neighbors=26).fit(featn.to_numpy())

    # --- change flags: unusual latest change vs the national distribution of changes
    changes = df["delta"].dropna()
    mad = float(np.median(np.abs(changes - changes.median()))) * 1.4826 or 1.0

    boston = pd.read_csv(BOSTON_CSV, dtype={"cms_provider_id": str})
    boston["cms_provider_id"] = boston["cms_provider_id"].str.zfill(6)
    rows = []
    for _, b in boston.iterrows():
        hit = now[now["facility_id"].str.zfill(6) == b["cms_provider_id"]]
        if hit.empty:
            continue
        h = hit.iloc[0]
        idx = now.index.get_loc(hit.index[0])
        _, nbr = nn.kneighbors(featn.iloc[[idx]].to_numpy())
        peers = now.iloc[[i for i in nbr[0] if i != idx][:25]]
        peer_med = float(peers["op18b"].median())
        rows.append({
            "hospital": b["hospital"], "cms_provider_id": b["cms_provider_id"],
            "latest_op18b": float(h["op18b"]), "period_end": str(h["op18b_period_end"].date()) if pd.notna(h["op18b_period_end"]) else "",
            "forecast_op18b": float(h["forecast"]), "lo80": float(h["lo80"]), "hi80": float(h["hi80"]),
            "peer_median_op18b": peer_med, "vs_peers_min": float(h["op18b"] - peer_med),
            "latest_change_min": float(h["delta"]) if pd.notna(h["delta"]) else None,
            "change_flag": bool(pd.notna(h["delta"]) and abs(h["delta"]) > 2.5 * mad),
        })
    bos = pd.DataFrame(rows)
    bos.to_csv(BOSTON_PATH, index=False)

    # --- Boston backtest on the test transition
    bt = test[test["facility_id"].str.zfill(6).isin(boston["cms_provider_id"])]
    boston_bt = {"hospitals": int(len(bt)),
                 "MAE_selected": float(mean_absolute_error(bt["target"], bt["pred_selected"])) if len(bt) else None,
                 "spearman_selected": _spearman(bt["pred_selected"], bt["target"]) if len(bt) >= 3 else None,
                 "fastest_pick_correct": bool(bt["pred_selected"].idxmin() == bt["target"].idxmin()) if len(bt) else None}

    # --- Tesla-case evidence computed from the data
    lag = (panel.dropna(subset=["op18b_period_end"]).groupby("snapshot")["op18b_period_end"].max())
    lag_months = ((lag.index.to_series() - lag) .dt.days / 30.44)
    evidence = {
        "hospitals_latest_release": int(latest["facility_id"].nunique()),
        "hospitals_with_op18b_latest": int(latest["op18b"].notna().sum()),
        "boston_spread_min": float(bos["latest_op18b"].max() - bos["latest_op18b"].min()) if len(bos) else None,
        "boston_fastest": bos.loc[bos["latest_op18b"].idxmin(), "hospital"] if len(bos) else None,
        "boston_slowest": bos.loc[bos["latest_op18b"].idxmax(), "hospital"] if len(bos) else None,
        "boston_fastest_min": float(bos["latest_op18b"].min()) if len(bos) else None,
        "boston_slowest_min": float(bos["latest_op18b"].max()) if len(bos) else None,
        "data_lag_months_min": float(lag_months.min()), "data_lag_months_max": float(lag_months.max()),
        "releases": len(snaps),
    }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": "Next-release CMS OP-18b (median ED visit duration, discharged patients, minutes)",
        "releases": [str(pd.Timestamp(s).date()) for s in snaps],
        "split": {"train_transitions": f"releases 1-{T - 1} -> next", "validation_transition": f"release {T} -> {T + 1}",
                  "test_transition": f"release {T + 1} -> {T + 2}",
                  "train_rows": int(len(train)), "validation_rows": int(len(valid)), "test_rows": int(len(test)),
                  "total_rows": int(len(labeled)), "hospitals": int(labeled["facility_id"].nunique())},
        "models": results, "selected_model": selected, "best_learned_model": best_learned,
        "learned_model_promoted": bool(promoted), "promotion_margin": PROMOTION_MARGIN,
        "intervals": {"method": "Regime-adaptive conformalized quantile regression (gradient boosting, q=0.10/0.90)",
                      "target_coverage": COVERAGE_TARGET, "test_coverage": coverage,
                      "median_width_min": width,
                      "test_coverage_ci95": cov_ci, "backtest_coverage": backtest_cov, "backtest_width_min": backtest_width,
                      "static_test_coverage": static_cov, "static_width_min": static_width, "old_fixed_band_coverage": old_band,
                      "old_fixed_band_median_width_min": old_width,
                      "coverage_by_volume": {k: float(v) for k, v in cov_by_volume.items()}},
        "ranking": ranking, "confidence": confidence, "boston_backtest": boston_bt, "ablation": ablation, "drivers": drivers[:10],
        "structure": {"by_volume": vol.reset_index().rename(columns={"edv": "ed_volume"}).to_dict("records"),
                      "by_ownership": own.reset_index().to_dict("records"),
                      "spearman_op18b_vs_left_without_being_seen": corr_op22},
        "evidence": evidence,
    }
    RESULTS_PATH.write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    build_panel()
    r = run()
    s = r["split"]
    print(f"Panel: {s['total_rows']:,} labeled rows, {s['hospitals']:,} hospitals")
    for m in r["models"]:
        print(f"  {m['model']:<52} val MAE {m['validation_MAE']:6.1f}  test MAE {m['MAE']:6.1f}  R2 {m['R2']:.3f}")
    print("Selected:", r["selected_model"], "(promoted)" if r["learned_model_promoted"] else "(baseline kept)")
    i = r["intervals"]
    print(f"80% intervals: test coverage {i['test_coverage']:.1%}, median width {i['median_width_min']:.0f} min "
          f"(old fixed band: {i['old_fixed_band_coverage']:.1%}, {i['old_fixed_band_median_width_min']:.0f} min)")
    print("Ranking:", json.dumps(r["ranking"], indent=1))
    print("Boston backtest:", r["boston_backtest"])
    print("Ablation:", r["ablation"])
    print("Top drivers:", r["drivers"][:5])
    print("Evidence:", r["evidence"])
    print(f"Wrote {RESULTS_PATH.name}, {BOSTON_PATH.name}, {PANEL_PATH.name}")
