"""ERNow update 37: what choosing by ERNow's forecast is worth across the U.S.

    python research/national_impact.py

Rule written before running: within every U.S. county with 3+ EDs, at each of the 7 rolling held-out CMS
releases, pick the ER with the lowest forecast (Persistence, the production model: last published median)
and compare the ER's *actual* next-release median with (a) the county average, which is what picking any
ER in the county at random gets you, and (b) the true quickest. The forecast uses only data published
before each release, so there is no look-ahead. Drive time is not included (no national routing), so this
measures the hospital part only; the Boston analysis includes drive time separately.
Writes data/national_impact.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    d = pd.read_csv(ROOT / "data" / "ensemble_oof_predictions.csv.gz", dtype={"facility_id": str})
    rows = []
    for (rel, st, co), g in d.groupby(["target_release", "state", "county"]):
        g = g.dropna(subset=["target", "lag1"])
        if len(g) < 3:
            continue
        pick = g.loc[g["lag1"].idxmin(), "target"]
        rows.append({"release": rel, "county": f"{co}, {st}", "n_eds": len(g),
                     "saved_vs_random": float(g["target"].mean() - pick),
                     "behind_quickest": float(pick - g["target"].min()),
                     "spread": float(g["target"].max() - g["target"].min())})
    r = pd.DataFrame(rows)
    rng = np.random.default_rng(7)
    # Resample whole counties (a county appears in several releases, so its years are not independent).
    by_county = [g["saved_vs_random"].to_numpy() for _, g in r.groupby("county")]
    boot = []
    for _ in range(2000):
        pick = rng.integers(0, len(by_county), len(by_county))
        boot.append(np.concatenate([by_county[i] for i in pick]).mean())
    out = {
        "method": __doc__.split("\n\n")[1].replace("\n", " "),
        "county_years": int(len(r)), "counties": int(r["county"].nunique()), "releases": int(r["release"].nunique()),
        "mean_minutes_saved_vs_random": round(float(r["saved_vs_random"].mean()), 1),
        "mean_minutes_saved_ci95_county_bootstrap": [round(float(np.percentile(boot, 2.5)), 1), round(float(np.percentile(boot, 97.5)), 1)],
        "median_minutes_saved_vs_random": round(float(r["saved_vs_random"].median()), 1),
        "share_better_than_random": round(float((r["saved_vs_random"] > 0).mean()), 3),
        "mean_minutes_behind_quickest": round(float(r["behind_quickest"].mean()), 1),
        "share_picked_true_quickest": round(float((r["behind_quickest"] == 0).mean()), 3),
        "median_county_spread_minutes": round(float(r["spread"].median()), 1),
        "by_release": [{"release": k, "county_years": int(len(g)), "mean_saved": round(float(g["saved_vs_random"].mean()), 1),
                        "share_true_quickest": round(float((g["behind_quickest"] == 0).mean()), 3)}
                       for k, g in r.groupby("release")],
        "limits": "Hospital medians only (no drive time); counties with 3+ reporting EDs; medians, not individual visits.",
    }
    (ROOT / "data" / "national_impact.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("method", "by_release")}, indent=1))


if __name__ == "__main__":
    main()
