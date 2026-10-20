"""ERNow core logic, kept separate from the Streamlit app so it can be unit-tested.

chance_fastest: for each ER, the share of simulated trips (drive + typical visit) in which it is quickest.
calibrate_chance: optional correction curve, applied only if it improved held-out years.
"""
import json
from pathlib import Path

import numpy as np

CALIBRATION_FILE = Path(__file__).parent / "data" / "chance_calibration.json"


def chance_fastest(drive, mid, lo, hi, n=4000, seed=11):
    """Share of simulated drive + hospital-median scenarios won (checked against held-out years).

    Lognormal spread is approximated from interval bounds; patient-level visit
    variability is not measured. Missing routes or valid bounds are excluded.
    """
    drive_a, mid_a = np.asarray(drive, dtype=float), np.asarray(mid, dtype=float)
    lo_a, hi_a = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    ok = (np.isfinite(drive_a) & np.isfinite(mid_a) & np.isfinite(lo_a) & np.isfinite(hi_a)
          & (mid_a > 0) & (lo_a > 0) & (hi_a >= lo_a))
    probs = np.full(len(mid), np.nan)
    if ok.sum() < 2:
        return probs
    rng = np.random.default_rng(seed)
    m, l, h, d = (np.asarray(x, dtype=float)[ok] for x in (mid, lo, hi, drive))
    sigma = np.maximum(np.log(np.maximum(h, m + 1) / np.maximum(l, 1)) / (2 * 1.2816), 0.01)
    draws = d + np.exp(np.log(np.maximum(m, 1)) + sigma * rng.standard_normal((n, len(m))))
    wins = np.bincount(draws.argmin(axis=1), minlength=len(m)) / n
    probs[np.where(ok)[0]] = wins
    return calibrate_chance(probs)


def calibrate_chance(probs, calibration_file=None):
    """Map simulated shares to tested probabilities (isotonic fit on held-out years, data/chance_calibration.json)."""
    try:
        cal = json.loads(Path(calibration_file or CALIBRATION_FILE).read_text())
        x, y = np.asarray(cal["x"], float), np.asarray(cal["y"], float)
    except Exception:
        return probs
    if not cal.get("calibration_helps_held_out", False):
        return probs  # held-out years showed the raw simulation is already as accurate; don't adjust it
    out = np.asarray(probs, float).copy()
    ok = np.isfinite(out)
    out[ok] = np.interp(out[ok], x, y)
    return out
