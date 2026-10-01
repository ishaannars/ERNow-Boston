"""Summarize the decision-time test and write it into README.md between the DECISION_TIME markers.

Three kinds of runs (data/decision_time_results.csv, column `method`):
  full    manual comparison with the same information ERNow shows (6 ED times + 6 drive times)
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
    if "full" in s:
        f, n = s["full"]["median_seconds"], s["full"]["participants"]
        lines.append(f"- **Full comparison** (the same information ERNow shows: 6 ED times + 6 drive times): "
                     f"**{fmt(f)} manually vs {fmt(e)} in ERNow**, {f / max(e, 1):.0f}× faster "
                     f"({n} participant{'s' if n != 1 else ''}).")
    if "quick" in s:
        q, n = s["quick"]["median_seconds"], s["quick"]["participants"]
        tail = ""
        if CHOICE.exists():
            ch = json.loads(CHOICE.read_text())
            tail = (f" It only finds the closest ER, and the closest isn't the fastest overall from "
                    f"{ch['closest_not_fastest_share']:.0%} of Boston locations.")
        lines.append(f"- **The usual quick search** (\"ER near me\", pick the closest): {fmt(q)} "
                     f"({n} participant{'s' if n != 1 else ''}).{tail}")
    return "\n".join(lines) + "\n\nTimed with `python timing_test.py` (protocol in `TIMING_TEST.md`)."


def main():
    text = readme_text(summary())
    body = README.read_text()
    i, j = body.index(START) + len(START), body.index(END)
    README.write_text(body[:i] + "\n" + text + "\n" + body[j:])
    print(text)


if __name__ == "__main__":
    main()
