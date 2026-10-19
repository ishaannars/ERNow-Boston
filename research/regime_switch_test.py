"""ERNow update 38: can a volatility signal pick the right model each year?

    python research/regime_switch_test.py

Finding this builds on: learned models beat Persistence in the volatile 2020-2023 releases and lose in
stable years. Rule written before running:
- Signal (known before each forecast): how much hospital medians moved between the two most recently
  published releases (mean absolute change, minutes).
- Switch: use the challenger when the signal is above a threshold, Persistence otherwise. The threshold is
  chosen only from earlier held-out releases (expanding window, candidates = earlier signals or "never"),
  so each year is decided without seeing it. The first two releases are only used to choose.
- Challenger fixed in advance: partial pooling (best validation challenger in the main study). Ridge and
  gradient boosting are reported as sensitivity checks, not used to pick the winner.
- Promote only if, over the evaluated releases, the switch beats Persistence by >= 2% MAE, the paired
  hospital bootstrap 95% interval excludes zero, and county decision regret is not worse.
Writes data/regime_switch_results.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = "Persistence baseline"
MAIN = "Partial pooling (shrink toward state & peer means)"
SENS = ["Ridge regression", "Gradient boosting"]


def volatility_by_release(panel, releases):
    snaps = sorted(panel["snapshot"].unique())
    wide = panel.pivot_table(index="facility_id", columns="snapshot", values="op18b")
    sig = {}
    for rel in releases:
        prior = [s for s in snaps if s < rel]
        a, b = prior[-1], prior[-2]
        sig[rel] = float((wide[a] - wide[b]).abs().mean())
    return sig


def regret(df, col):
    out = []
    for _, g in df.groupby(["target_release", "state", "county"]):
        if len(g) >= 3:
            out.append(g.loc[g[col].idxmin(), "target"] - g["target"].min())
    return float(np.mean(out))


def run_switch(d, sig, rels, chal):
    mae = {r: {m: float((g[m] - g["target"]).abs().mean()) for m in (BASE, chal)} for r, g in d.groupby("target_release")}
    choice = {}
    for i, rel in enumerate(rels):
        if i < 2:
            continue
        past = rels[:i]
        cands = [np.inf] + sorted(sig[p] for p in past)
        def past_err(t):
            return np.mean([mae[p][chal] if sig[p] > t else mae[p][BASE] for p in past])
        best = min(cands, key=lambda t: (past_err(t), -t))  # ties -> higher threshold (stay with Persistence)
        choice[rel] = {"threshold": None if np.isinf(best) else round(best, 2), "signal": round(sig[rel], 2),
                       "uses": chal if sig[rel] > best else BASE}
    ev = d[d["target_release"].isin(choice)].copy()
    use_chal = ev["target_release"].map(lambda r: choice[r]["uses"] == chal).to_numpy()
    ev["switch"] = np.where(use_chal, ev[chal], ev[BASE])
    return ev, choice


def main():
    d = pd.read_csv(ROOT / "data" / "ensemble_oof_predictions.csv.gz", dtype={"facility_id": str})
    panel = pd.read_csv(ROOT / "data" / "national_ed_panel.csv.gz", dtype={"facility_id": str})
    rels = sorted(d["target_release"].unique())
    sig = volatility_by_release(panel, rels)
    rng = np.random.default_rng(7)
    results = {}
    for chal in [MAIN] + SENS:
        ev, choice = run_switch(d, sig, rels, chal)
        e_base, e_sw = (ev[BASE] - ev["target"]).abs().to_numpy(), (ev["switch"] - ev["target"]).abs().to_numpy()
        gain = (e_base.mean() - e_sw.mean()) / e_base.mean()
        boot = []
        for _ in range(2000):
            i = rng.integers(0, len(ev), len(ev))
            boot.append((e_base[i].mean() - e_sw[i].mean()) / e_base[i].mean())
        oracle = np.minimum(*[ev.groupby("target_release").apply(lambda g, m=m: (g[m] - g["target"]).abs().mean()) for m in (BASE, chal)])
        results[chal] = {
            "evaluated_releases": sorted(choice), "choices": choice,
            "persistence_MAE": round(float(e_base.mean()), 3), "switch_MAE": round(float(e_sw.mean()), 3),
            "gain_vs_persistence": round(float(gain), 4),
            "gain_ci95": [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)],
            "best_possible_switch_MAE": round(float((oracle * ev.groupby("target_release").size()).sum() / len(ev)), 3),
            "county_regret_persistence": round(regret(ev, BASE), 2), "county_regret_switch": round(regret(ev, "switch"), 2),
        }
    m = results[MAIN]
    promoted = (m["gain_vs_persistence"] >= 0.02 and m["gain_ci95"][0] > 0
                and m["county_regret_switch"] <= m["county_regret_persistence"])
    out = {"method": __doc__.split("\n\n")[1].replace("\n", " ") + " " + __doc__.split("\n\n")[2].replace("\n", " "),
           "signal_by_release": {k: round(v, 2) for k, v in sig.items()},
           "main_challenger": MAIN, "results": results, "promoted": bool(promoted),
           "best_possible_gain_main": round(1 - results[MAIN]["best_possible_switch_MAE"] / results[MAIN]["persistence_MAE"], 4),
           "conclusion": ("Promoted: the volatility switch beats Persistence under the pre-set rule."
                          if promoted else "Not promoted: the volatility switch did not clear the pre-set rule, so Persistence stays.")}
    (ROOT / "data" / "regime_switch_results.json").write_text(json.dumps(out, indent=1))
    print("signal:", out["signal_by_release"])
    for k, v in results.items():
        print(k[:20], {x: v[x] for x in ("persistence_MAE", "switch_MAE", "gain_vs_persistence", "gain_ci95", "best_possible_switch_MAE",
                                         "county_regret_persistence", "county_regret_switch")})
        print("   ", {r: c["uses"][:12] + f" (t={c['threshold']}, s={c['signal']})" for r, c in v["choices"].items()})
    print(out["conclusion"])


if __name__ == "__main__":
    main()
