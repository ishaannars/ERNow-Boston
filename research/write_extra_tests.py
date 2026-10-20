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
    cr_path = ROOT / "data" / "crowding_factor_results.json"
    if cr_path.exists():
        cr = json.loads(cr_path.read_text())
        rows.append((
            "Does hospital crowding (beds in use) make the forecast more accurate?",
            f"**{'Promoted' if cr['promoted'] else 'Not promoted'}.** Statewide crowding (still published weekly, so usable live) "
            f"cut the gradient-boosting model's validation error {cr['gbm_gain_from_crowding_validation']:.0%} "
            f"({cr['gbm_validation_without_crowding']:.1f} → {cr['gbm_validation_with_crowding']:.1f} min), the largest gain of any factor tested, "
            f"but only brought it level with Persistence ({cr['persistence_validation']:.1f} min), short of the 2% bar. "
            f"Per-hospital crowding (HHS, reporting ended 2024) {'lowered' if cr['rolling_gbm_minutes_change_per_hospital'] < 0 else 'raised'} "
            f"the learned model's rolling error by only {abs(cr['rolling_gbm_minutes_change_per_hospital']):.2f} min "
            f"over {cr['rolling_years_per_hospital']} years. Persistence stays.",
            "`research/crowding_factor_test.py`"))
    rg_path = ROOT / "data" / "crowding_range_results.json"
    if rg_path.exists():
        rg = json.loads(rg_path.read_text())
        lt = rg["years_where_crowding_could_be_learned"]
        rows.append((
            "Does crowding make the 80% ranges more accurate?",
            f"**{'Promoted' if rg['promoted'] else 'Not promoted'}.** Interval score {rg['mean_interval_score_without']:.1f} without vs "
            f"{rg['mean_interval_score_with']:.1f} with crowding (lower is better, so {abs(rg['interval_score_gain']):.1%} {'better' if rg['interval_score_gain'] > 0 else 'worse'}). In the {lt['years']} years "
            f"where the model had crowding history to learn from, crowding helped in {lt['years_crowding_better']}. Ranges stay as they are.",
            "`research/crowding_range_test.py`"))
    lines = ["| Question (rule written before running) | Result | Code |", "|---|---|---|"]
    lines += [f"| {q} | {a} | {c} |" for q, a, c in rows]
    return "\n".join(lines)


FSTART, FEND = "<!-- FACTORS:START -->", "<!-- FACTORS:END -->"
ESTART, EEND = "<!-- ERRORS:START -->", "<!-- ERRORS:END -->"


def errors_block():
    e = load("error_analysis.json")
    ch = {r["last_change"]: r["MAE"] for r in e["by_last_change"]}
    sz = {r["size"]: r["MAE"] for r in e["by_ed_size"]}
    lines = [
        f"Test year {e['test_release'][:7]}, {e['hospitals']:,} hospitals. From `research/error_analysis.py`.",
        "",
        f"- **Most estimates are close.** Half were within {e['median_abs_error']:.0f} minutes. "
        f"{e['share_within_15']:.0%} were within 15 minutes and {e['share_within_30']:.0%} within 30. "
        f"Only {e['share_over_60']:.1%} missed by more than an hour.",
        f"- **The misses are concentrated.** The worst 10% of hospitals (off by {e['worst_10pct_min_error']:.0f}+ minutes) "
        f"account for {e['worst_10pct_share_of_total_error']:.0%} of all error.",
        f"- **It doesn't lean one way.** It guessed too low for {e['share_underestimates']:.0%} of hospitals and too high for the rest.",
        f"- **Hospitals that just changed a lot are harder.** Error was {ch['0–5 min']:.1f} minutes when a hospital moved "
        f"0–5 minutes in its last release and {ch['30+ min']:.1f} minutes when it moved 30+.",
        f"- **Bigger EDs are harder.** Error was {sz['1 (smallest)']:.1f} minutes for the smallest EDs and "
        f"{sz['4 (largest)']:.1f} for the largest.",
        "",
        "The range model uses each hospital's latest change and national swings as inputs, so ranges are wider where misses are more likely.",
    ]
    return "\n".join(lines)


def scoreboard():
    """Every factor ERNow has tested, in plain English, built from the saved result files."""
    nat, resp = load("national_results.json"), load("respiratory_factor_results.json")
    sw, cal = load("regime_switch_results.json"), load("chance_calibration.json")
    ab = {a["features"]: a["test_MAE"] for a in nat["ablation"]}
    base = ab["Persistence (no features)"]
    extra = [v for k, v in ab.items() if k != "Persistence (no features)"]
    test_rows = nat["split"]["test_rows"]
    rows = [
        {"factor": "Last published ED visit time", "data": "CMS (OP-18b)", "live": True, "used": "Center estimate",
         "result": f"Most accurate option: {base:.1f}-min average error on {test_rows:,} hospitals it never saw"},
        {"factor": "Past trend, other ED measures, hospital traits, state and peer averages", "data": "CMS", "live": True,
         "used": "Ranges and look-alike hospitals",
         "result": f"Made the center estimate less accurate ({min(extra):.1f}–{max(extra):.1f} vs {base:.1f} min), so they're used only in the ranges and look-alike matching"},
        {"factor": "How much ED times swung nationally in the latest release", "data": "CMS", "live": True, "used": "Ranges",
         "result": f"Ranges widen or narrow with recent swings; {nat['intervals']['test_coverage']:.0%} held the true value (target 80%)"},
        {"factor": "Drive time from where you are", "data": "OpenStreetMap routing", "live": True, "used": "Your total time",
         "result": "Added to the typical visit to find the lowest total"},
        {"factor": "Respiratory-illness season", "data": "CDC FluView (ILINet)", "live": True, "used": "",
         "result": f"No gain, even with perfect knowledge of the coming season (rolling error {resp['rolling_avg_MAE']['gradient_boosting_plus_respiratory']:.2f} "
                   f"with vs {resp['rolling_avg_MAE']['gradient_boosting']:.2f} min without)"},
        {"factor": "Model switching in turbulent years", "data": "CMS", "live": True, "used": "",
         "result": f"{sw['results'][sw['main_challenger']]['gain_vs_persistence']:+.1%}; even a perfect switch would gain only {sw['best_possible_gain_main']:.1%}"},
        {"factor": "Correction curve for \"chance it's quickest\"", "data": "CMS", "live": True, "used": "",
         "result": "Did not improve unseen years, so the raw simulation is shown"},
    ]
    if (ROOT / "data" / "crowding_factor_results.json").exists():
        cr = load("crowding_factor_results.json")
        rr = load("crowding_range_results.json") if (ROOT / "data" / "crowding_range_results.json").exists() else None
        rows.append({"factor": "Hospital crowding, statewide (beds in use)", "data": "CDC NHSN", "live": True, "used": "",
                     "result": f"Learned model {cr['gbm_gain_from_crowding_validation']:.0%} better but only tied the center estimate"
                               + ("" if rr is None else f"; ranges {abs(rr['interval_score_gain']):.1%} {'better' if rr['interval_score_gain'] > 0 else 'worse'}")})
        rows.append({"factor": "Hospital crowding, per hospital", "data": "HHS (reporting ended 2024)", "live": False, "used": "",
                     "result": f"Only {abs(cr['rolling_gbm_minutes_change_per_hospital']):.2f} min better per year, and no longer published"})
    rows += [
        {"factor": "Extreme weather days", "data": "NOAA", "live": True, "used": "Next to test", "result": "Not tested yet"},
        {"factor": "Community factors (uninsured rate, share aged 65+)", "data": "Census ACS", "live": True, "used": "Next to test",
         "result": "Not tested yet"},
    ]
    return rows


def tested_extra_count(rows=None):
    rows = rows or scoreboard()
    return sum(1 for r in rows if r["used"] == "")


def factor_block(rows=None):
    rows = rows or scoreboard()
    lines = ["| Factor | Data | Usable live? | Result | Used in ERNow? |", "|---|---|---|---|---|"]
    for r in rows:
        used = r["used"] if r["used"] else "No"
        mark = "✅ " + used if used not in ("No", "Next to test") else ("⏳ Next to test" if used == "Next to test" else "❌ No")
        lines.append(f"| {r['factor']} | {r['data']} | {'Yes' if r['live'] else 'No'} | {r['result']} | {mark} |")
    return "\n".join(lines)


def _replace(body, start, end, text):
    i, j = body.index(start) + len(start), body.index(end)
    return body[:i] + "\n" + text + "\n" + body[j:]


def main():
    p = ROOT / "README.md"
    rows = scoreboard()
    (ROOT / "data" / "factor_scoreboard.json").write_text(json.dumps({"rows": rows, "extra_factors_tested_not_used": tested_extra_count(rows)}, indent=1))
    body = _replace(p.read_text(), START, END, block())
    body = _replace(body, FSTART, FEND, factor_block(rows))
    if ESTART in body and (ROOT / "data" / "error_analysis.json").exists():
        body = _replace(body, ESTART, EEND, errors_block())
    p.write_text(body)
    print("README More tests and factor blocks updated; data/factor_scoreboard.json written.")


if __name__ == "__main__":
    main()
