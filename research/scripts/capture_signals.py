"""Pass A of the win-rate optimization: score the whole 10y panel once and
SAVE every qualifying signal (score >= 50) with full indicator state, so the
parameter sweep (pass B) can test filters/exits without rescoring.
No forward-looking data is stored — only day-T indicator state."""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import numpy as np
import pandas as pd
import swing_trading as st

DATA = str(ROOT.joinpath("research", "data", "nse_universe_10y_ohlcv.csv.gz"))
OUT = str(ROOT.joinpath("research", "data", "signals_10y.csv.gz"))
WINDOW = 250
SCORE_MIN = 50          # capture below production's 55 so threshold can sweep down too
MIN_PRICE = 5.0
MIN_TURN = 1e7

print("loading...", flush=True)
df = pd.read_csv(DATA)
df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
dates_all = np.array(sorted(df["date"].unique()))
date_pos = {d: i for i, d in enumerate(dates_all)}

S = {}
for sym, g in df.groupby("symbol", sort=False):
    S[sym] = dict(
        d=g["date"].to_numpy(), o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
        l=g["low"].to_numpy(float), c=g["close"].to_numpy(float), v=g["volume"].to_numpy(float),
        pos=np.array([date_pos[x] for x in g["date"].to_numpy()]))
print(f"{len(df):,} rows, {len(S)} symbols", flush=True)

rows = []
t0 = time.time()
for si, sym in enumerate(S):
    if si % 100 == 0:
        print(f"{si}/{len(S)} ({(time.time()-t0)/60:.1f} min, {len(rows):,} signals)", flush=True)
    a = S[sym]
    c, v, pos = a["c"], a["v"], a["pos"]
    for k in range(WINDOW, len(c)):
        if c[k] < MIN_PRICE:
            continue
        nn = min(20, k)
        if float(np.mean(c[k-nn+1:k+1] * v[k-nn+1:k+1])) < MIN_TURN:
            continue
        r = st._analyze_arrays(sym, a["o"][k-WINDOW:k+1], a["h"][k-WINDOW:k+1],
                               a["l"][k-WINDOW:k+1], c[k-WINDOW:k+1], v[k-WINDOW:k+1])
        if not r or r.get("score", 0) < SCORE_MIN:
            continue
        rows.append((a["d"][k], sym, r["score"], r["setup"], r["trend"],
                     bool(r["counter_trend"]), r["rsi"], r["adx"], r["stoch_rsi"],
                     r["macd_signal"], r["bb_position"], r["volume_ratio"],
                     bool(r["volume_spike"]), r["atr"], c[k],
                     r.get("risk_pct") or 0.0, r.get("reward_pct") or 0.0))
print(f"scoring done {(time.time()-t0)/60:.1f} min, {len(rows):,} signals", flush=True)

out = pd.DataFrame(rows, columns=["date","symbol","score","setup","trend","counter_trend",
                                  "rsi","adx","stoch_rsi","macd_signal","bb_position",
                                  "vol_ratio","vol_spike","atr","close",
                                  "risk_pct","reward_pct"])
out.to_csv(OUT, index=False, compression="gzip")
print(f"wrote {OUT}")
print("DONE", flush=True)
