"""Signal capture over the 2010-now panel (same logic as the 10y capture)."""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import numpy as np
import pandas as pd
import swing_trading as st

DATA = str(ROOT.joinpath("research", "data", "nse_universe_2010_ohlcv.csv.gz"))
OUT = str(ROOT.joinpath("research", "data", "signals_2010.csv.gz"))
WINDOW = 250
SCORE_MIN = 50
MIN_PRICE = 5.0
MIN_TURN = 1e7

print("loading...", flush=True)
# memory-lean: float32 downcast, no global sort (the download wrote each
# symbol contiguously and already date-ascending)
df = pd.read_csv(DATA,
                 usecols=["date", "symbol", "open", "high", "low", "close", "volume"],
                 dtype={"symbol": "category", "open": "float32", "high": "float32",
                        "low": "float32", "close": "float32", "volume": "float64"})
print(f"{len(df):,} rows, {df['symbol'].nunique()} symbols, "
      f"{df['date'].min()}..{df['date'].max()}", flush=True)

rows = []
t0 = time.time()
syms = df["symbol"].unique()
for si, (sym, g) in enumerate(df.groupby("symbol", sort=False)):
    if si % 100 == 0:
        print(f"{si}/{len(syms)} ({(time.time()-t0)/60:.1f} min, {len(rows):,} signals)", flush=True)
    o = g["open"].to_numpy(float); h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float); c = g["close"].to_numpy(float)
    v = g["volume"].to_numpy(float); d = g["date"].to_numpy()
    for k in range(WINDOW, len(c)):
        if c[k] < MIN_PRICE:
            continue
        nn = min(20, k)
        if float(np.mean(c[k-nn+1:k+1] * v[k-nn+1:k+1])) < MIN_TURN:
            continue
        r = st._analyze_arrays(sym, o[k-WINDOW:k+1], h[k-WINDOW:k+1],
                               l[k-WINDOW:k+1], c[k-WINDOW:k+1], v[k-WINDOW:k+1])
        if not r or r.get("score", 0) < SCORE_MIN:
            continue
        rows.append((d[k], sym, r["score"], bool(r["counter_trend"]), r["trend"],
                     r["adx"], r["atr"], c[k]))
print(f"scoring done {(time.time()-t0)/60:.1f} min, {len(rows):,} signals", flush=True)
out = pd.DataFrame(rows, columns=["date","symbol","score","counter_trend","trend",
                                  "adx","atr","close"])
out.to_csv(OUT, index=False, compression="gzip")
print(f"wrote {OUT}")
print("DONE", flush=True)
