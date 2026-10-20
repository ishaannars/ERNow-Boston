"""Unit tests for ERNow's core decision logic (ernow_core.py)."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ernow_core import calibrate_chance, chance_fastest  # noqa: E402


def test_shares_add_up_to_one():
    p = chance_fastest([5, 10, 15], [120, 150, 180], [100, 130, 160], [140, 170, 200])
    assert np.isclose(np.nansum(p), 1.0)
    assert np.all((p >= 0) & (p <= 1))


def test_clearly_quickest_er_wins_almost_always():
    p = chance_fastest([5, 30], [90, 240], [85, 230], [95, 250])
    assert p[0] > 0.99 and p[1] < 0.01


def test_identical_ers_split_evenly():
    p = chance_fastest([10, 10], [150, 150], [130, 130], [170, 170], n=20000)
    assert abs(p[0] - 0.5) < 0.02


def test_same_seed_same_answer():
    args = ([8, 12, 9], [140, 135, 160], [120, 115, 140], [160, 155, 180])
    assert np.array_equal(chance_fastest(*args), chance_fastest(*args))


def test_missing_route_is_excluded_not_guessed():
    p = chance_fastest([np.nan, 10, 12], [150, 140, 160], [130, 120, 140], [170, 160, 180])
    assert np.isnan(p[0]) and np.isclose(np.nansum(p), 1.0)


def test_fewer_than_two_valid_ers_gives_no_chance():
    p = chance_fastest([np.nan, 10], [150, 140], [130, 120], [170, 160])
    assert np.all(np.isnan(p))


def test_drive_time_counts():
    near = chance_fastest([5, 60], [150, 150], [130, 130], [170, 170])
    assert near[0] > 0.95


def test_calibration_skipped_when_it_did_not_help(tmp_path):
    f = tmp_path / "cal.json"
    f.write_text(json.dumps({"x": [0, 1], "y": [0.5, 0.5], "calibration_helps_held_out": False}))
    probs = np.array([0.1, 0.9])
    assert np.array_equal(calibrate_chance(probs, f), probs)


def test_calibration_applied_when_it_helped(tmp_path):
    f = tmp_path / "cal.json"
    f.write_text(json.dumps({"x": [0, 1], "y": [0.0, 0.5], "calibration_helps_held_out": True}))
    assert np.allclose(calibrate_chance(np.array([0.2, 1.0]), f), [0.1, 0.5])


def test_missing_calibration_file_is_safe(tmp_path):
    probs = np.array([0.3, 0.7])
    assert np.array_equal(calibrate_chance(probs, tmp_path / "none.json"), probs)
