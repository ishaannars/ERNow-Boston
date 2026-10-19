"""Calibrate ERNow's "chance it's quickest" against what actually happened.

    python research/calibrate_chance_fastest.py

For every rolling held-out CMS release, conformal ranges are fit only on earlier releases, the app's
4,000-draw simulation gives each hospital a chance of having the lowest median within its county
(counties with 3+ EDs), and we record whether it truly did. An isotonic regression maps simulated
chances to observed frequencies; the map and a reliability table go to data/chance_calibration.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import national_model as nm  # noqa: E402


def raw_chance(mid, lo, hi, n=4000, seed=11):
    m, l, h = (np.asarray(x, float) for x in (mid, lo, hi))
    ok = np.isfinite(m) & np.isfinite(l) & np.isfinite(h) & (m > 0) & (l > 0) & (h >= l)
    out = np.full(len(m), np.nan)
    if ok.sum() < 2:
        return out
    m, l, h = m[ok], l[ok], h[ok]
    sigma = np.maximum(np.log(np.maximum(h, m + 1) / np.maximum(l, 1)) / (2 * 1.2816), 0.01)
    draws = np.exp(np.log(np.maximum(m, 1)) + sigma * np.random.default_rng(seed).standard_normal((n, len(m))))
    out[np.where(ok)[0]] = np.bincount(draws.argmin(axis=1), minlength=len(m)) / n
    return out


def main():
    panel = nm.load_panel(); df, _ = nm.make_transitions(panel)
    lab = df[df["target"].notna()]; T = int(lab["t"].max()); cols = nm.FEATURE_GROUPS["+ geography & peers (full)"]
    rows = []
    for k in range(3, T + 1):
        tr, ca, te = lab[lab["t"] <= k - 2], lab[lab["t"] == k - 1], lab[lab["t"] == k]
        if len(tr) < 1000 or len(te) < 500:
            continue
        lo, hi = nm.CQR(cols).fit(tr, ca).predict(te)
        te = te.assign(mid=te["lag1"].to_numpy(), lo=lo, hi=hi)
        for _, g in te.groupby(["state", "county"]):
            if len(g) < 3:
                continue
            p = raw_chance(g["mid"], g["lo"], g["hi"])
            win = (g["target"].to_numpy() == g["target"].min()).astype(float)
            rows += [(k, pi, wi) for pi, wi in zip(p, win) if np.isfinite(pi)]
        print(f"held-out release {k}: done", flush=True)
    r = pd.DataFrame(rows, columns=["k", "p", "win"])
    # Honest score: for each held-out year, fit the calibration curve on the OTHER years only,
    # then score that year (cross-fitted). Also the strictest check: fit on earlier years, test on the latest.
    cross = np.full(len(r), np.nan)
    for k in sorted(r.k.unique()):
        fit, test = r[r.k != k], r.k == k
        cross[test.to_numpy()] = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(fit.p, fit.win).predict(r.p[test])
    latest = r.k.max()
    early, last = r[r.k < latest], r[r.k == latest]
    last_cal = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(early.p, early.win).predict(last.p)
    iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(r.p, r.win)
    xs = np.unique(np.round(iso.X_thresholds_, 4)); ys = iso.predict(xs)
    r["bin"] = pd.cut(r.p, [0, .01, .05, .2, .4, .6, .8, .95, .99, 1.0001], right=False)
    tab = r.groupby("bin", observed=True).agg(n=("win", "size"), predicted=("p", "mean"), actual=("win", "mean")).reset_index()
    ex = tab.iloc[6]
    out = {"method": __doc__.split("\n\n")[1].replace("\n", " "), "hospital_years": int(len(r)), "held_out_years": int(r.k.nunique()),
           "x": [float(x) for x in xs], "y": [float(y) for y in ys],
           "bins": [{"range": str(t.bin), "n": int(t.n), "predicted": round(float(t.predicted), 4), "actual": round(float(t.actual), 4)} for t in tab.itertuples()],
           "example_predicted_090": round(float(ex.predicted), 3), "example_actual_090": round(float(ex.actual), 3),
           "brier_raw": round(float(np.mean((r.p - r.win) ** 2)), 5),
           "brier_calibrated_in_sample": round(float(np.mean((iso.predict(r.p) - r.win) ** 2)), 5),
           "brier_calibrated_cross_fitted": round(float(np.mean((cross - r.win) ** 2)), 5),
           "latest_year": {"hospital_years": int(len(last)),
                           "brier_raw": round(float(np.mean((last.p - last.win) ** 2)), 5),
                           "brier_calibrated_on_earlier_years": round(float(np.mean((last_cal - last.win) ** 2)), 5)}}
    out["calibration_helps_held_out"] = bool(out["brier_calibrated_cross_fitted"] < out["brier_raw"]
                                             and out["latest_year"]["brier_calibrated_on_earlier_years"] < out["latest_year"]["brier_raw"])
    (ROOT / "data" / "chance_calibration.json").write_text(json.dumps(out, indent=1))
    print(tab.to_string(index=False)); print(f"{len(r):,} hospital-years · Brier raw {out['brier_raw']} · cross-fitted {out['brier_calibrated_cross_fitted']} · latest year {out['latest_year']}")


if __name__ == "__main__":
    main()
