"""Summarize the decision-time test and write it into README.md between the DECISION_TIME markers."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "data" / "decision_time_results.csv"
README = ROOT / "README.md"
START, END = "<!-- DECISION_TIME:START -->", "<!-- DECISION_TIME:END -->"


def fmt(sec):
    sec = int(round(sec))
    return f"{sec // 60} min {sec % 60:02d} s" if sec >= 60 else f"{sec} s"


def main():
    df = pd.read_csv(CSV)
    df["method"] = df["method"].str.strip().str.lower()
    manual, ernow = df[df.method == "manual"]["seconds"], df[df.method == "ernow"]["seconds"]
    if manual.empty or ernow.empty:
        text = "_Not yet measured. Run `python timing_test.py` (guided stopwatch, about 10 minutes)._"
        body = README.read_text()
        i, j = body.index(START) + len(START), body.index(END)
        README.write_text(body[:i] + "\n" + text + "\n" + body[j:])
        print(text)
        return
    n = df["participant"].nunique()
    m, e = manual.median(), ernow.median()
    same = (df.pivot_table(index="participant", columns="method", values="picked_hospital", aggfunc="first")
              .dropna().apply(lambda r: r["manual"] == r["ernow"], axis=1))
    text = (f"Comparing Boston's 6 ERs took a median of **{fmt(m)} manually vs {fmt(e)} in ERNow** "
            f"(**{m / max(e, 1):.0f}× faster**; {n} participant{'s' if n != 1 else ''}, timed with the protocol in `TIMING_TEST.md`).")
    if len(same):
        text += f" Participants picked the same hospital both ways in {same.sum()} of {len(same)} cases."
    body = README.read_text()
    i, j = body.index(START) + len(START), body.index(END)
    README.write_text(body[:i] + "\n" + text + "\n" + body[j:])
    print(text)


if __name__ == "__main__":
    main()
