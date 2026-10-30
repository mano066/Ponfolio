"""Extended history 2010-01-01 -> now. Memory-lean: each chunk is appended to
disk immediately; phantom-date stats are accumulated incrementally; the final
filtered file is written with chunked reads. Same cleaning as the 10y pull."""
import sys, os, time, warnings
from collections import defaultdict
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import numpy as np
import pandas as pd
import yfinance as yf
import swing_trading as st

OUTDIR = str(ROOT.joinpath("research", "data"))
RAW = OUTDIR + r"\_raw_2010.csv"
MASTER = OUTDIR + r"\nse_universe_2010_ohlcv.csv.gz"
NIFTY = OUTDIR + r"\nifty50_daily_2010.csv"
START = "2010-01-01"

syms = list(st.SWING_UNIVERSE)
print(f"target: {len(syms)} stocks from {START}", flush=True)
if os.path.exists(RAW):
    os.remove(RAW)

date_rows = defaultdict(int)
date_zero = defaultdict(int)
got = set()
wrote_header = False

def flush_chunk(sub, sym):
    global wrote_header
    sub = sub.dropna(subset=["Close"])
    if sub.empty:
        return False
    out = pd.DataFrame({
        "date": sub.index.strftime("%Y-%m-%d"),
        "symbol": sym.replace(".NS", ""),
        "open": sub["Open"].round(4), "high": sub["High"].round(4),
        "low": sub["Low"].round(4), "close": sub["Close"].round(4),
        "volume": sub["Volume"].fillna(0).astype("int64"),
        "adjusted_close": sub["Adj Close"].round(4),
    })
    for dd, vv in zip(out["date"], out["volume"]):
        date_rows[dd] += 1
        if vv == 0:
            date_zero[dd] += 1
    out.to_csv(RAW, mode="a", header=not wrote_header, index=False)
    wrote_header = True
    return True

CHUNK = 60
for s in range(0, len(syms), CHUNK):
    chunk = syms[s:s+CHUNK]
    print(f"[P1] chunk {s}-{s+len(chunk)}", flush=True)
    try:
        d = yf.download(chunk, start=START, group_by="ticker", auto_adjust=False,
                        threads=True, progress=False)
    except Exception as e:
        print(f"  chunk error: {e}", flush=True); continue
    if d is None or len(d) == 0:
        continue
    lvl0 = set(d.columns.get_level_values(0)) if isinstance(d.columns, pd.MultiIndex) else set()
    for sym in chunk:
        try:
            sub = d.copy() if len(chunk) == 1 else (d[sym].copy() if sym in lvl0 else None)
            if sub is not None and flush_chunk(sub, sym):
                got.add(sym)
        except Exception:
            pass
    del d

missing = [x for x in syms if x not in got]
print(f"[P2] retrying {len(missing)} symbols", flush=True)
for sym in missing:
    for attempt in range(2):
        try:
            h = yf.Ticker(sym).history(start=START, auto_adjust=False)
            if h is not None and len(h):
                if "Adj Close" not in h.columns:
                    h["Adj Close"] = h["Close"]
                if flush_chunk(h, sym):
                    got.add(sym)
                break
        except Exception:
            time.sleep(0.5)

phantoms = {dd for dd, n in date_rows.items()
            if n >= 50 and date_zero[dd] / n >= 0.99}
print(f"symbols: {len(got)}/{len(syms)} | phantom dates: {len(phantoms)}", flush=True)

# final pass: chunked read -> drop phantoms -> gz
first = True
total = 0
for part in pd.read_csv(RAW, chunksize=250_000):
    part = part[~part["date"].isin(phantoms)]
    total += len(part)
    part.to_csv(MASTER, mode="w" if first else "a", header=first, index=False,
                compression="gzip")
    first = False
os.remove(RAW)
print(f"master rows: {total:,} -> {MASTER}", flush=True)

nd = yf.Ticker("^NSEI").history(start=START, auto_adjust=False)
nifty = pd.DataFrame({"date": nd.index.strftime("%Y-%m-%d"),
                      "nifty_close": nd["Close"].round(2)})
nifty = nifty[~nifty["date"].isin(phantoms)]
nifty.to_csv(NIFTY, index=False)
print(f"nifty rows: {len(nifty):,} from {nifty['date'].min()}")
print("DONE", flush=True)
