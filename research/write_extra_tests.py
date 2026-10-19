"""Write the README "More tests" block from the saved result files (no typed-in numbers).

    python research/write_extra_tests.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- EXTRA_TESTS:START -->", "<!-- EXTRA_TESTS:END -->"


def load(name):
    return json.loads((ROOT / "data" / name).read_text())


def block():
    imp, cal = load("national_impact.json"), load("chance_calibration.json")
    sw, eq = load("regime_switch_results.json"), load("equity_audit.json")
    m = sw["results"][sw["main_challenger"]]
    lo, hi = imp["mean_minutes_saved_ci95_county_bootstrap"]
    cov = [g["coverage"] for g in eq["groups"]]
    rows = [
        ("Across the U.S., does picking by forecast beat picking any ER in the same county?",
         f"Yes: **{imp['mean_minutes_saved_vs_random']:.0f} min** shorter typical visit (95% CI {lo:.0f}–{hi:.0f}, county bootstrap), "
         f"better in **{imp['share_better_than_random']:.0%}** of {imp['county_years']:,} county-years across {imp['counties']} counties "
         f"and {imp['releases']} held-out releases; true quickest picked {imp['share_picked_true_quickest']:.0%} of the time.",
         "`research/national_impact.py`"),
        ("Is \"chance it's quickest\" honest?",
         f"Close: when it said {cal['example_predicted_090']:.0%}, the ER was quickest {cal['example_actual_090']:.0%} of the time "
         f"({cal['hospital_years']:,} hospital-years, {cal['held_out_years']} held-out years). A correction curve "
         + ("improved" if cal["calibration_helps_held_out"] else "did **not** improve")
         + f" unseen years (Brier {cal['brier_raw']} raw vs {cal['brier_calibrated_cross_fitted']} cross-fitted), so "
         + ("it is applied." if cal["calibration_helps_held_out"] else "the raw simulation is shown."),
         "`research/calibrate_chance_fastest.py`"),
        ("Learned models win in turbulent years. Can a volatility signal pick the model each year?",
         f"**{'Promoted' if sw['promoted'] else 'Not promoted'}.** Switching gained {m['gain_vs_persistence']:+.1%} "
         f"(95% CI {m['gain_ci95'][0]:+.1%} to {m['gain_ci95'][1]:+.1%}); even a perfect year-by-year switch would gain only "
         f"{sw['best_possible_gain_main']:.1%}, under the 2% bar. Persistence stays.",
         "`research/regime_switch_test.py`"),
        ("Does it work as well for rural, government, for-profit, and small hospitals?",
         ("No group flagged" if not eq["flags"] else "Flagged: " + "; ".join(eq["flags"]))
         + f" (flag = error >1.25× overall or range coverage <70%). Coverage {min(cov):.0%}–{max(cov):.0%} across groups; "
         f"{eq['hospital_years']:,} hospital-years, {eq['held_out_releases']} held-out releases.",
         "`research/equity_audit.py`"),
    ]
    lines = ["| Question (rule written before running) | Result | Code |", "|---|---|---|"]
    lines += [f"| {q} | {a} | {c} |" for q, a, c in rows]
    return "\n".join(lines)


def main():
    p = ROOT / "README.md"
    body = p.read_text()
    i, j = body.index(START) + len(START), body.index(END)
    p.write_text(body[:i] + "\n" + block() + "\n" + body[j:])
    print("README More tests block updated.")


if __name__ == "__main__":
    main()
