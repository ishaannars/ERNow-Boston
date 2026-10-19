"""ERNow checks that run on every push (GitHub Actions) and locally with `pytest -q`."""
import json
import py_compile
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(name):
    return json.loads((DATA / name).read_text())


def test_published_claims_match_saved_results():
    out = subprocess.run([sys.executable, "scripts/verify_claims.py"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "PASS" in out.stdout


def test_every_python_file_compiles():
    files = [p for p in ROOT.rglob("*.py") if not {".venv", "__pycache__"} & set(p.parts)]
    assert files
    for path in files:
        py_compile.compile(str(path), doraise=True)


def test_boston_ranges_contain_forecast():
    fc = pd.read_csv(DATA / "boston_forecast.csv")
    assert (fc["ed_type"] == "general").sum() == 7
    assert (fc["lo80"] > 0).all()
    assert (fc["lo80"] <= fc["forecast_op18b"]).all() and (fc["forecast_op18b"] <= fc["hi80"]).all()


def test_promotion_rule_is_respected():
    res = load("national_results.json")
    val = {m["model"]: m["validation_MAE"] for m in res["models"]}
    gain = (val["Persistence baseline"] - val[res["best_learned_model"]]) / val["Persistence baseline"]
    if res["learned_model_promoted"]:
        assert gain >= res["promotion_margin"]
    else:
        assert res["selected_model"] == "Persistence baseline" and gain < res["promotion_margin"]


def test_calibration_only_applied_if_it_helps_unseen_years():
    cal = load("chance_calibration.json")
    helps = (cal["brier_calibrated_cross_fitted"] < cal["brier_raw"]
             and cal["latest_year"]["brier_calibrated_on_earlier_years"] < cal["latest_year"]["brier_raw"])
    assert cal["calibration_helps_held_out"] == helps


def test_regime_switch_follows_its_rule():
    sw = load("regime_switch_results.json")
    m = sw["results"][sw["main_challenger"]]
    should = (m["gain_vs_persistence"] >= 0.02 and m["gain_ci95"][0] > 0
              and m["county_regret_switch"] <= m["county_regret_persistence"])
    assert sw["promoted"] == should


def test_national_impact_is_internally_consistent():
    imp = load("national_impact.json")
    lo, hi = imp["mean_minutes_saved_ci95_county_bootstrap"]
    assert lo <= imp["mean_minutes_saved_vs_random"] <= hi
    assert 0 <= imp["share_picked_true_quickest"] <= imp["share_better_than_random"] <= 1


def test_equity_flags_follow_their_rule():
    eq = load("equity_audit.json")
    expected = sum((g["relative_to_overall"] > 1.25) + (g["coverage"] < 0.70) for g in eq["groups"])
    assert len(eq["flags"]) == expected


def test_readme_more_tests_block_is_current():
    sys.path.insert(0, str(ROOT / "research"))
    import write_extra_tests as w
    assert w.block() in (ROOT / "README.md").read_text()


def test_startup_styling_never_raises():
    pytest.importorskip("streamlit")
    sys.path.insert(0, str(ROOT))
    import startup_theme
    startup_theme.install_startup_theme()
