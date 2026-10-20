"""ERNow update 42b: does hospital crowding make the 80% ranges more accurate?

    python research/crowding_range_test.py

Crowding did not improve the center forecast enough to replace Persistence (crowding_factor_test.py).
Ranges are a separate model (gradient-boosting quantile regression + conformal calibration), so this
tests whether statewide crowding (CDC NHSN, still published weekly, usable live) helps them.

Rule written before running. For every rolling held-out release where crowding data exists, fit the
production range model twice, without and with statewide crowding, using only earlier releases. Score
with the interval score (width plus a penalty for each miss, the standard proper score for an 80% range;
lower is better). Promote crowding into the live ranges only if it:
  1. lowers the average interval score by at least 2%,
  2. lowers it in a majority of those years, and
  3. keeps the latest year's coverage within 75-85% (target 80%).
Writes data/crowding_range_results.json.
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))
import national_model as nm  # noqa: E402
from crowding_factor_test import add_features, load_state  # noqa: E402

ALPHA = 1 - nm.COVERAGE_TARGET


def interval_score(y, lo, hi, a=ALPHA):
    return (hi - lo) + (2 / a) * np.maximum(lo - y, 0) + (2 / a) * np.maximum(y - hi, 0)


def main():
    panel = nm.load_panel()
    df, snaps = nm.make_transitions(panel)
    snap_dates = {i: pd.Timestamp(s) for i, s in enumerate(snaps)}
    df = df.copy()
    df["period_end"] = pd.to_datetime(df["op18b_period_end"])
    df["target_period_end"] = df.groupby("facility_id")["period_end"].shift(-1)
    df["release_date"] = df["t"].map(snap_dates)
    live, _ = add_features(df, snap_dates, load_state(), "state", "occ_state")
    nm.NUMERIC += [c for c in df.columns if c.startswith("occ_state")]
    full = nm.FEATURE_GROUPS["+ geography & peers (full)"]
    lab = df[df["target"].notna()]
    T = int(lab["t"].max())
    rows = []
    for k in range(3, T + 1):
        tr, ca, te = lab[lab["t"] <= k - 2], lab[lab["t"] == k - 1], lab[lab["t"] == k]
        if len(tr) < 1000 or len(te) < 500 or te["occ_state_current"].notna().mean() < 0.9:
            continue
        y = te["target"].to_numpy()
        row = {"k": k, "release": str(snap_dates[k + 1].date()) if k + 1 in snap_dates else str(k),
               "hospitals": int(len(te))}
        for tag, cols in (("without", full), ("with", full + live)):
            lo, hi = nm.CQR(cols).fit(tr, ca).predict(te)
            row[f"coverage_{tag}"] = round(float(np.mean((y >= lo) & (y <= hi))), 4)
            row[f"width_{tag}"] = round(float(np.mean(hi - lo)), 2)
            row[f"score_{tag}"] = round(float(np.mean(interval_score(y, lo, hi))), 3)
        rows.append(row)
        print(row, flush=True)
    r = pd.DataFrame(rows)
    gain = 1 - r["score_with"].mean() / r["score_without"].mean()
    wins = int((r["score_with"] < r["score_without"]).sum())
    last_cov = float(r.iloc[-1]["coverage_with"])
    promoted = bool(gain >= 0.02 and wins > len(r) / 2 and 0.75 <= last_cov <= 0.85)
    # In early years no training release had crowding data yet, so the model could not learn from it
    # (with == without). Report the years where it could, separately.
    learn = r[(r["score_with"] != r["score_without"]) | (r["width_with"] != r["width_without"])]
    out = {"method": " ".join(__doc__.split("\n\n")[1:3]).replace("\n", " "),
           "years_where_crowding_could_be_learned": {
               "years": int(len(learn)), "years_crowding_better": int((learn["score_with"] < learn["score_without"]).sum()),
               "mean_score_without": round(float(learn["score_without"].mean()), 3) if len(learn) else None,
               "mean_score_with": round(float(learn["score_with"].mean()), 3) if len(learn) else None},
           "years": rows, "years_tested": int(len(r)),
           "mean_interval_score_without": round(float(r["score_without"].mean()), 3),
           "mean_interval_score_with": round(float(r["score_with"].mean()), 3),
           "interval_score_gain": round(float(gain), 4), "years_better": wins,
           "mean_width_without": round(float(r["width_without"].mean()), 2),
           "mean_width_with": round(float(r["width_with"].mean()), 2),
           "mean_coverage_without": round(float(r["coverage_without"].mean()), 3),
           "mean_coverage_with": round(float(r["coverage_with"].mean()), 3),
           "latest_year_coverage_with": round(last_cov, 3), "promoted": promoted,
           "conclusion": ("Promoted: statewide crowding makes the ranges more accurate under the pre-set rule."
                          if promoted else "Not promoted: crowding did not make the ranges accurate enough to change them.")}
    (ROOT / "data" / "crowding_range_results.json").write_text(json.dumps(out, indent=1))
    print({k: v for k, v in out.items() if k not in ("method", "years")})


if __name__ == "__main__":
    main()
