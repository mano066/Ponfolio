import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import yfinance as yf
import pandas as pd
import swing_trading as st

DOCS = str(ROOT.joinpath("research", "data"))
STOCK_OUT = DOCS + r"\nse_universe_5y_ohlcv.csv"
NIFTY_OUT = DOCS + r"\nifty50_daily_5y.csv"

syms = st.SWING_UNIVERSE
print(f"[1/3] downloading 5y daily OHLCV for {len(syms)} stocks (chunked)...", file=sys.stderr)

CHUNK = 100
frames = []
for start in range(0, len(syms), CHUNK):
    chunk = syms[start:start+CHUNK]
    print(f"  chunk {start}-{start+len(chunk)}...", file=sys.stderr)
    d = yf.download(chunk, period="5y", group_by="ticker", auto_adjust=False,
                     threads=True, progress=False)
    lvl0 = set(d.columns.get_level_values(0)) if isinstance(d.columns, pd.MultiIndex) else set()
    for sym in chunk:
        try:
            if len(chunk) == 1:
                sub = d.copy()
            else:
                if sym not in lvl0:
                    continue
                sub = d[sym].copy()
            sub = sub.dropna(subset=["Close"])
            if sub.empty:
                continue
            out = pd.DataFrame({
                "date": sub.index.strftime("%Y-%m-%d"),
                "symbol": sym.replace(".NS", ""),
                "open": sub["Open"].round(2),
                "high": sub["High"].round(2),
                "low": sub["Low"].round(2),
                "close": sub["Close"].round(2),
                "volume": sub["Volume"].fillna(0).astype("int64"),
                "adjusted_close": sub["Adj Close"].round(2),
            })
            out["turnover"] = (out["close"] * out["volume"]).round(2)
            out["delivery_pct"] = ""  # not available from Yahoo Finance
            frames.append(out)
        except Exception as e:
            print(f"    skip {sym}: {e}", file=sys.stderr)

print(f"[2/3] concatenating {len(frames)} stock frames...", file=sys.stderr)
full = pd.concat(frames, ignore_index=True)
full = full.sort_values(["symbol", "date"]).reset_index(drop=True)
cols = ["date","symbol","open","high","low","close","volume","adjusted_close","turnover","delivery_pct"]
full = full[cols]
full.to_csv(STOCK_OUT, index=False)
print(f"  saved {len(full):,} rows, {full['symbol'].nunique()} symbols -> {STOCK_OUT}", file=sys.stderr)
print(f"  date range: {full['date'].min()} to {full['date'].max()}", file=sys.stderr)

print("[3/3] downloading Nifty 50 index 5y daily...", file=sys.stderr)
nd = yf.download("^NSEI", period="5y", auto_adjust=False, progress=False)
if isinstance(nd.columns, pd.MultiIndex):
    nd.columns = nd.columns.get_level_values(0)
nifty = pd.DataFrame({
    "date": nd.index.strftime("%Y-%m-%d"),
    "nifty_open": nd["Open"].round(2),
    "nifty_high": nd["High"].round(2),
    "nifty_low": nd["Low"].round(2),
    "nifty_close": nd["Close"].round(2),
    "nifty_volume": nd["Volume"].fillna(0).astype("int64"),
})
nifty.to_csv(NIFTY_OUT, index=False)
print(f"  saved {len(nifty):,} rows -> {NIFTY_OUT}", file=sys.stderr)

print("\nDONE.", file=sys.stderr)
print(f"stock rows: {len(full):,} | symbols: {full['symbol'].nunique()} | nifty rows: {len(nifty):,}", file=sys.stderr)
