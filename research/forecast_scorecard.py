"""Did the forecast hold? Score every past Boston forecast against what CMS published next.

ERNow's forecast for a release is the hospital's previous published median (Persistence, the
model that won the national test). For each later release this records, per hospital, the
forecast, the published value, and the miss, plus whether the ER forecast to be fastest was
in fact the fastest of the six.

    python research/forecast_scorecard.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def scorecard(history):
    wide = (history.pivot_table(index="snapshot_date", columns="hospital", values="observed_wait_min", aggfunc="last")
            .sort_index())
    periods = (history.groupby("snapshot_date")[["reporting_start", "reporting_end"]].first())
    checks = []
    for prev, cur in zip(wide.index[:-1], wide.index[1:]):
        f, a = wide.loc[prev].dropna(), wide.loc[cur].dropna()
        both = f.index.intersection(a.index)
        if len(both) < 2:
            continue
        miss = (a[both] - f[both])
        checks.append({
            "release": cur,
            "period": f"{periods.loc[cur, 'reporting_start']} to {periods.loc[cur, 'reporting_end']}",
            "hospitals": int(len(both)),
            "mae_min": round(float(miss.abs().mean()), 1),
            "within_15": int((miss.abs() <= 15).sum()),
            "forecast_fastest": str(f[both].idxmin()),
            "actual_fastest": str(a[both].idxmin()),
            "fastest_held": bool(f[both].idxmin() == a[both].idxmin()),
            "rank_corr": round(float(f[both].rank().corr(a[both].rank())), 2),
            "rows": [{"hospital": h, "forecast": float(f[h]), "actual": float(a[h]), "miss": float(miss[h])}
                     for h in sorted(both, key=lambda x: a[x])],
        })
    n = sum(c["hospitals"] for c in checks)
    return {
        "method": "python research/forecast_scorecard.py",
        "model": "Persistence (previous published median)",
        "checks": checks,
        "summary": {
            "forecasts_checked": n,
            "releases_checked": len(checks),
            "mae_min": round(sum(c["mae_min"] * c["hospitals"] for c in checks) / n, 1) if n else None,
            "within_15_share": round(sum(c["within_15"] for c in checks) / n, 3) if n else None,
            "fastest_held": sum(c["fastest_held"] for c in checks),
        },
    }


if __name__ == "__main__":
    out = scorecard(pd.read_csv(ROOT / "data" / "cms_op18b_history.csv"))
    (ROOT / "data" / "forecast_scorecard.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["summary"], indent=2))
    for c in out["checks"]:
        print(c["release"], c["mae_min"], c["within_15"], "/", c["hospitals"], "fastest held:", c["fastest_held"], c["rank_corr"])
