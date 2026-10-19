"""ERNow update 39: does ERNow work equally well for every kind of hospital?

    python research/equity_audit.py

Rule written before running: across the 7 rolling held-out CMS releases (each forecast and range uses
only earlier releases), compare groups on (1) forecast error relative to the group's typical visit
length, so short-visit and long-visit hospitals are comparable, and (2) how often the 80% range
contained the real median. A group is flagged if its relative error is more than 1.25x the overall
rate, or its range coverage is below 70%. Flags are reported, never hidden or tuned away.
Groups: rural (Critical Access) vs other acute hospitals; ownership (government, nonprofit, for-profit);
ED size (CMS volume bands 1-4, smallest to largest).
Writes data/equity_audit.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import national_model as nm  # noqa: E402

REL_ERR_FLAG, COVERAGE_FLAG = 1.25, 0.70


def owner_group(o):
    o = str(o)
    if o.startswith("Government") or o in ("Tribal", "Department of Defense"):
        return "Government"
    if o.startswith("Voluntary"):
        return "Nonprofit"
    if o in ("Proprietary", "Physician"):
        return "For-profit"
    return "Other"


def type_group(t):
    t = str(t)
    if t.startswith("Critical Access") or t.startswith("Rural Emergency"):
        return "Rural (Critical Access)"
    if t.startswith("Acute Care Hospitals"):
        return "Other acute hospitals"
    return "Other"


def main():
    panel = nm.load_panel()
    df, _ = nm.make_transitions(panel)
    lab = df[df["target"].notna()]
    T = int(lab["t"].max())
    cols = nm.FEATURE_GROUPS["+ geography & peers (full)"]
    parts = []
    for k in range(3, T + 1):
        tr, ca, te = lab[lab["t"] <= k - 2], lab[lab["t"] == k - 1], lab[lab["t"] == k]
        if len(tr) < 1000 or len(te) < 500:
            continue
        lo, hi = nm.CQR(cols).fit(tr, ca).predict(te)
        parts.append(te.assign(pred=te["lag1"].to_numpy(), lo=lo, hi=hi, k=k))
        print(f"held-out release {k}: done", flush=True)
    r = pd.concat(parts)
    r["abs_err"] = (r["pred"] - r["target"]).abs()
    r["covered"] = (r["target"] >= r["lo"]) & (r["target"] <= r["hi"])
    r["Hospital type"] = r["hospital_type"].map(type_group)
    r["Ownership"] = r["ownership"].map(owner_group)
    r["ED size"] = r["edv"].map(lambda v: {1.0: "1 (smallest)", 2.0: "2", 3.0: "3", 4.0: "4 (largest)"}.get(v, "Unknown"))
    overall_rel = r["abs_err"].sum() / r["target"].sum()
    out = {"method": __doc__.split("\n\n")[1].replace("\n", " "), "hospital_years": int(len(r)),
           "held_out_releases": int(r["k"].nunique()),
           "overall": {"MAE": round(float(r["abs_err"].mean()), 2), "relative_error": round(float(overall_rel), 4),
                       "coverage": round(float(r["covered"].mean()), 3)},
           "groups": [], "flags": []}
    for dim in ("Hospital type", "Ownership", "ED size"):
        for name, g in r.groupby(dim):
            if name in ("Other", "Unknown") or len(g) < 200:
                continue
            rel = g["abs_err"].sum() / g["target"].sum()
            row = {"dimension": dim, "group": name, "hospital_years": int(len(g)),
                   "typical_visit_min": round(float(g["target"].median()), 1), "MAE": round(float(g["abs_err"].mean()), 2),
                   "relative_error": round(float(rel), 4), "relative_to_overall": round(float(rel / overall_rel), 2),
                   "coverage": round(float(g["covered"].mean()), 3)}
            out["groups"].append(row)
            if rel / overall_rel > REL_ERR_FLAG:
                out["flags"].append(f"{dim} = {name}: relative error {rel / overall_rel:.2f}x overall")
            if g["covered"].mean() < COVERAGE_FLAG:
                out["flags"].append(f"{dim} = {name}: range coverage {g['covered'].mean():.0%}")
    (ROOT / "data" / "equity_audit.json").write_text(json.dumps(out, indent=1))
    print(pd.DataFrame(out["groups"]).to_string(index=False))
    print("Overall:", out["overall"]); print("Flags:", out["flags"] or "none")


if __name__ == "__main__":
    main()
