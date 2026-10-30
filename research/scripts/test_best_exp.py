"""Evaluate on the untouched TEST period the best-EXPECTANCY config that was
selected on validation (score>=55, trend=up, ADX>=25, SL=3xATR, TP=2xATR,
hold=20). Selection used only train+validation; this is its first test look.
Also break down by year and compute R-expectancy."""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DATA = str(ROOT.joinpath("research", "data", "nse_universe_10y_ohlcv.csv.gz"))
SIG = str(ROOT.joinpath("research", "data", "signals_10y.csv.gz"))
COST = 0.30; TOP_N = 5; HMAX = 21

px = pd.read_csv(DATA).sort_values(["symbol", "date"])
P = {}
for sym, g in px.groupby("symbol", sort=False):
    P[sym] = dict(o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
                  l=g["low"].to_numpy(float), c=g["close"].to_numpy(float),
                  idx={dd: i for i, dd in enumerate(g["date"])})
sig = pd.read_csv(SIG)
sig["atr_pct"] = sig["atr"] / sig["close"] * 100

def run(d, score_min, slx, tpx, hold, label):
    m = (d["score"] >= score_min) & (~d["counter_trend"]) & (d["trend"] == "Up") & (d["adx"] >= 25)
    f = d[m].sort_values(["date", "score"], ascending=[True, False]).groupby("date").head(TOP_N)
    rows = []
    for sym, date, atrp in zip(f["symbol"], f["date"], f["atr_pct"]):
        a = P.get(sym); j = a["idx"].get(date) if a else None
        if j is None or j + 1 >= len(a["c"]) or atrp <= 0:
            continue
        e = a["o"][j+1]
        if e <= 0:
            continue
        lo = a["l"][j+1:j+1+HMAX]; hi = a["h"][j+1:j+1+HMAX]; cl = a["c"][j+1:j+1+HMAX]
        sl = e * (1 - slx*atrp/100); tp = e * (1 + tpx*atrp/100)
        n = min(hold, len(cl)); ex = None
        for k in range(n):
            if lo[k] <= sl: ex = sl; break
            if hi[k] >= tp: ex = tp; break
        if ex is None: ex = cl[n-1]
        net = (ex/e - 1)*100 - COST
        rows.append((date[:4], net, net/(slx*atrp) if atrp > 0 else 0))
    t = pd.DataFrame(rows, columns=["year", "net", "R"])
    w = t[t["net"] > 0]; l = t[t["net"] <= 0]
    pf = w["net"].sum()/max(1e-9, -l["net"].sum())
    print(f"\n{label}: n={len(t)} win={len(w)/len(t)*100:.1f}% exp={t['net'].mean():+.3f}%/tr "
          f"({t['R'].mean():+.3f}R) PF={pf:.2f} avgW={w['net'].mean():+.2f}% avgL={l['net'].mean():+.2f}%")
    for y, g in t.groupby("year"):
        wy = (g["net"] > 0).mean()*100
        print(f"  {y}: n={len(g):>4} win={wy:5.1f}% exp={g['net'].mean():+.3f}%")
    return t

TE = sig[sig["date"] > "2024-12-31"]
TR = sig[sig["date"] <= "2022-12-31"]
VA = sig[(sig["date"] > "2022-12-31") & (sig["date"] <= "2024-12-31")]
print("CONFIG: score>=55, trend=Up, not counter-trend, ADX>=25, SL=3xATR, TP=2xATR, hold=20, top-5/day, 0.30% costs")
run(TR, 55, 3.0, 2.0, 20, "TRAIN 2016-2022 (reference)")
run(VA, 55, 3.0, 2.0, 20, "VALIDATION 2023-2024 (selection basis)")
run(TE, 55, 3.0, 2.0, 20, "FINAL TEST 2025-2026 (first look)")
print("DONE")
