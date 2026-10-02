"""Summarize the decision-time test and write it into README.md between the DECISION_TIME markers.

Three kinds of runs (data/decision_time_results.csv, column `method`):
  full    manual comparison with the same information ERNow shows (each ER's ED time and drive time)
  quick   the usual way: search "ER near me", skim, pick (closest ER only)
  ernow   the same decision in ERNow
Older rows labeled `manual` count as `full`.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "data" / "decision_time_results.csv"
README = ROOT / "README.md"
CHOICE = ROOT / "data" / "boston_choice.json"
START, END = "<!-- DECISION_TIME:START -->", "<!-- DECISION_TIME:END -->"
PLACEHOLDER = "_Not yet measured. Run `python timing_test.py` (guided stopwatch, about 10 minutes)._"


def fmt(sec):
    sec = int(round(sec))
    return f"{sec // 60} min {sec % 60:02d} s" if sec >= 60 else f"{sec} s"


def hm(minutes):
    m = int(round(minutes))
    return f"{m // 60}h {m % 60}m" if m >= 60 else f"{m} min"


def summary():
    """Medians per run type, or {} when nothing is recorded yet. Also used by the app."""
    if not CSV.exists():
        return {}
    df = pd.read_csv(CSV)
    if df.empty:
        return {}
    df["method"] = df["method"].astype(str).str.strip().str.lower().replace({"manual": "full"})
    out = {}
    for m in ["full", "quick", "ernow"]:
        d = df[df.method == m]
        if len(d):
            out[m] = {"median_seconds": float(d["seconds"].median()), "participants": int(d["participant"].nunique())}
    return out


def readme_text(s):
    if "ernow" not in s or not ({"full", "quick"} & set(s)):
        return PLACEHOLDER
    e = s["ernow"]["median_seconds"]
    lines = []
    if "quick" in s:
        q, n = s["quick"]["median_seconds"], s["quick"]["participants"]
        ne = s["ernow"]["participants"]
        lines.append(f"- **Recorded decision times** (\"ER near me\", pick the closest): **{fmt(e)} in ERNow "
                     f"({ne} participant{'s' if ne != 1 else ''}) vs {fmt(q)} for the search ({n} participant{'s' if n != 1 else ''})**. "
                     "Recorded medians from a small convenience sample; the search protocol chooses the nearest ER. This is not a controlled trial or a population-wide speed estimate.")
    if "full" in s:
        f, n = s["full"]["median_seconds"], s["full"]["participants"]
        lines.append(f"- **Recorded manual comparison:** gathering the same facts by hand (each ER's ED time and drive time) took "
                     f"{fmt(f)} ({n} participant{'s' if n != 1 else ''}).")
    return "\n".join(lines) + "\n\nTimed with `python timing_test.py` (protocol in `TIMING_TEST.md`)."


def main():
    text = readme_text(summary())
    body = README.read_text()
    i, j = body.index(START) + len(START), body.index(END)
    README.write_text(body[:i] + "\n" + text + "\n" + body[j:])
    print(text)


if __name__ == "__main__":
    main()
