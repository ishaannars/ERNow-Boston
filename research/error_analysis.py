"""Where ERNow's forecast is wrong, and why.

    python research/error_analysis.py

Uses the final held-out release (the same test year as the headline 9.4-minute error) and the
production forecast (Persistence: the last published median). Reports how errors are distributed,
which hospitals ERNow misses most, and whether the misses could have been seen coming.
Writes data/error_analysis.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    d = pd.read_csv(ROOT / "data" / "ensemble_oof_predictions.csv.gz", dtype={"facility_id": str})
    rel = d["target_release"].max()
    t = d[d["target_release"] == rel].dropna(subset=["target", "lag1"]).copy()
    panel = pd.read_csv(ROOT / "data" / "national_ed_panel.csv.gz", dtype={"facility_id": str})
    snaps = sorted(panel["snapshot"].unique())
    prior = [s for s in snaps if s < rel]
    wide = panel.pivot_table(index="facility_id", columns="snapshot", values="op18b")
    t["prev_change"] = (wide[prior[-1]] - wide[prior[-2]]).abs().reindex(t["facility_id"]).to_numpy()
    meta = panel[panel["snapshot"] == prior[-1]].set_index("facility_id")
    t["edv"] = meta["edv"].reindex(t["facility_id"]).to_numpy()
    t["err"] = t["lag1"] - t["target"]
    t["abs_err"] = t["err"].abs()

    n = len(t)
    worst = t.sort_values("abs_err", ascending=False)
    top10 = worst.head(max(1, n // 10))
    bins = pd.cut(t["prev_change"], [-0.1, 5, 15, 30, np.inf], labels=["0–5 min", "5–15 min", "15–30 min", "30+ min"])
    by_change = (t.groupby(bins, observed=True)
                 .agg(hospitals=("abs_err", "size"), MAE=("abs_err", "mean")).reset_index()
                 .rename(columns={"prev_change": "last_change"}))
    by_size = (t.assign(size=t["edv"].map({1.0: "1 (smallest)", 2.0: "2", 3.0: "3", 4.0: "4 (largest)"}))
               .dropna(subset=["size"]).groupby("size").agg(hospitals=("abs_err", "size"), MAE=("abs_err", "mean")).reset_index())
    rho = float(t[["prev_change", "abs_err"]].dropna().rank().corr().iloc[0, 1])
    out = {
        "method": __doc__.split("\n\n")[2].replace("\n", " "),
        "test_release": str(rel), "hospitals": int(n),
        "MAE": round(float(t["abs_err"].mean()), 2), "median_abs_error": round(float(t["abs_err"].median()), 1),
        "share_within_15": round(float((t["abs_err"] <= 15).mean()), 3),
        "share_within_30": round(float((t["abs_err"] <= 30).mean()), 3),
        "share_over_60": round(float((t["abs_err"] > 60).mean()), 3),
        "worst_10pct_share_of_total_error": round(float(top10["abs_err"].sum() / t["abs_err"].sum()), 3),
        "worst_10pct_min_error": round(float(top10["abs_err"].min()), 1),
        "share_underestimates": round(float((t["err"] < 0).mean()), 3),
        "worst_10pct_share_underestimates": round(float((top10["err"] < 0).mean()), 3),
        "rank_corr_last_change_vs_error": round(rho, 2),
        "by_last_change": [{"last_change": str(r.last_change), "hospitals": int(r.hospitals), "MAE": round(float(r.MAE), 1)}
                           for r in by_change.itertuples()],
        "by_ed_size": [{"size": r.size, "hospitals": int(r.hospitals), "MAE": round(float(r.MAE), 1)} for r in by_size.itertuples()],
    }
    (ROOT / "data" / "error_analysis.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "method"}, indent=1))


if __name__ == "__main__":
    main()
