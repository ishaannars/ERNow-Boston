"""Is the closest Boston ER usually the fastest overall?

Lays a grid of ~2,000 points over Boston, estimates drive time to each of the six ERs,
adds each hospital's forecast typical ED visit (data/boston_forecast.csv), and counts how
often the closest ER is not the one with the shortest drive + typical visit.

Drive time here is estimated from straight-line distance (x1.35 road circuity, 18 mph city
average, +3 min to park), because public routing can't be called 2,000 x 6 times. The app
itself uses real road routing for your actual location.

Run:  python boston_choice_analysis.py   ->  writes data/boston_choice.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "boston_choice.json"


def main():
    h = pd.read_csv(ROOT / "data" / "boston_er_data.csv", dtype={"cms_provider_id": str})
    f = pd.read_csv(ROOT / "data" / "boston_forecast.csv", dtype={"cms_provider_id": str})
    h = h.merge(f[["cms_provider_id", "forecast_op18b"]], on="cms_provider_id")
    R = 3958.8
    rows = []
    for a in np.linspace(42.28, 42.39, 45):
        for b in np.linspace(-71.16, -71.02, 45):
            d = 2 * R * np.arcsin(np.sqrt(np.sin(np.radians(h.latitude - a) / 2) ** 2 + np.cos(np.radians(a))
                                          * np.cos(np.radians(h.latitude)) * np.sin(np.radians(h.longitude - b) / 2) ** 2))
            if d.min() > 4:          # keep points within 4 miles of an ER (Boston proper)
                continue
            drive = d * 1.35 / 18 * 60 + 3
            total = drive + h.forecast_op18b
            near, fast = int(np.argmin(drive)), int(np.argmin(total))
            rows.append((near != fast, float(total[near] - total[fast]), float(drive[fast] - drive[near])))
    r = np.array(rows)
    diff = r[r[:, 0] == 1]
    out = {"locations": int(len(r)),
           "closest_not_fastest_share": float(r[:, 0].mean()),
           "median_minutes_saved_when_different": float(np.median(diff[:, 1])) if len(diff) else 0.0,
           "median_extra_drive_min_when_different": float(np.median(diff[:, 2])) if len(diff) else 0.0,
           "method": "Straight-line distance x1.35 at 18 mph +3 min; typical ED visit = national-model forecast (OP-18b)."}
    OUT.write_text(json.dumps(out, indent=2))
    print(out)


if __name__ == "__main__":
    main()
