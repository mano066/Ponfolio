"""Complete 10-year daily dataset for the Nifty Total Market universe.

Two-pass for maximum completeness:
  Pass 1: bulk chunked yf.download (fast, but chunk mode occasionally drops days)
  Pass 2: per-symbol Ticker().history retry for any symbol missing entirely or
          with interior gaps (single-ticker fetch is the most complete Yahoo mode)
Then: drop phantom holiday dates, detect interior gaps vs the master calendar,
      write master data (csv.gz) + a per-stock coverage/quality report (csv).

Honest limits documented in the coverage report: IPOs have < 10y by definition;
no value is ever fabricated (no forward-fill), gaps are reported, not patched.
"""
import sys, time, io, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import numpy as np
import pandas as pd
import yfinance as yf
import swing_trading as st

OUTDIR = str(ROOT.joinpath("research", "data"))
MASTER = OUTDIR + r"\nse_universe_10y_ohlcv.csv.gz"
COVER  = OUTDIR + r"\nse_universe_10y_coverage.csv"
NIFTY  = OUTDIR + r"\nifty50_daily_10y.csv"
PERIOD = "10y"

syms = list(st.SWING_UNIVERSE)
print(f"target: {len(syms)} Nifty Total Market stocks, period={PERIOD}", flush=True)

def rows_from_df(sub, sym):
    sub = sub.dropna(subset=["Close"])
    if sub.empty:
        return None
    out = pd.DataFrame({
        "date": sub.index.strftime("%Y-%m-%d"),
        "symbol": sym.replace(".NS", ""),
        "open": sub["Open"].round(4), "high": sub["High"].round(4),
        "low": sub["Low"].round(4), "close": sub["Close"].round(4),
        "volume": sub["Volume"].fillna(0).astype("int64"),
        "adjusted_close": sub["Adj Close"].round(4),
    })
    out["turnover"] = (out["close"] * out["volume"]).round(2)
    return out

# ---- Pass 1: bulk chunked ----
frames, got = [], {}
CHUNK = 60
for s in range(0, len(syms), CHUNK):
    chunk = syms[s:s+CHUNK]
    print(f"[P1] chunk {s}-{s+len(chunk)}", flush=True)
    try:
        d = yf.download(chunk, period=PERIOD, group_by="ticker", auto_adjust=False,
                        threads=True, progress=False)
    except Exception as e:
        print(f"     chunk error: {e}", flush=True); d = None
    if d is None or len(d) == 0:
        continue
    lvl0 = set(d.columns.get_level_values(0)) if isinstance(d.columns, pd.MultiIndex) else set()
    for sym in chunk:
        try:
            sub = d.copy() if len(chunk) == 1 else (d[sym].copy() if sym in lvl0 else None)
            if sub is None:
                continue
            r = rows_from_df(sub, sym)
            if r is not None:
                frames.append(r); got[sym] = len(r)
        except Exception:
            pass

# master trading calendar (after we have raw pass-1 data) + phantom detection
alldf = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
def phantom_dates(df):
    z = df.groupby("date")["volume"].apply(lambda x: (x == 0).mean())
    return set(z[z >= 0.99].index)
phantoms = phantom_dates(alldf) if len(alldf) else set()
print(f"[P1] got {len(got)}/{len(syms)} symbols, {len(alldf):,} rows, {len(phantoms)} phantom dates", flush=True)
alldf = alldf[~alldf["date"].isin(phantoms)]
master_cal = sorted(alldf["date"].unique())
cal_idx = {d: i for i, d in enumerate(master_cal)}

def interior_gaps(dates_set, first, last):
    """count master-calendar days within [first,last] missing from dates_set."""
    lo, hi = cal_idx[first], cal_idx[last]
    span = master_cal[lo:hi+1]
    return [d for d in span if d not in dates_set]

# who needs a pass-2 retry: missing entirely OR has interior gaps
by_sym = {sym: g for sym, g in alldf.groupby("symbol")}
retry = []
for sym in syms:
    key = sym.replace(".NS", "")
    if key not in by_sym:
        retry.append(sym); continue
    ds = set(by_sym[key]["date"])
    g = interior_gaps(ds, min(ds), max(ds))
    if g:
        retry.append(sym)
print(f"[P2] {len(retry)} symbols need retry (missing or gapped)", flush=True)

# ---- Pass 2: per-symbol thorough retry ----
p2frames = []
for i, sym in enumerate(retry):
    if i % 40 == 0:
        print(f"[P2] {i}/{len(retry)}", flush=True)
    for attempt in range(2):
        try:
            t = yf.Ticker(sym)
            h = t.history(period=PERIOD, auto_adjust=False)
            if h is not None and len(h):
                h = h.rename(columns={"Stock Splits": "Splits"})
                if "Adj Close" not in h.columns:
                    h["Adj Close"] = h["Close"]
                r = rows_from_df(h, sym)
                if r is not None:
                    p2frames.append(r)
                break
        except Exception:
            time.sleep(0.5)

if p2frames:
    p2 = pd.concat(p2frames, ignore_index=True)
    p2 = p2[~p2["date"].isin(phantoms)]
    # merge: prefer pass-2 rows (more complete) then pass-1, dedupe on (date,symbol)
    alldf = pd.concat([p2, alldf], ignore_index=True).drop_duplicates(
        subset=["date", "symbol"], keep="first")

alldf = alldf.sort_values(["symbol", "date"]).reset_index(drop=True)
# refresh calendar after pass-2 (may have added dates)
phantoms2 = phantom_dates(alldf)
alldf = alldf[~alldf["date"].isin(phantoms2)]
master_cal = sorted(alldf["date"].unique())
cal_idx = {d: i for i, d in enumerate(master_cal)}

# ---- coverage / quality report ----
cov = []
for sym in syms:
    key = sym.replace(".NS", "")
    g = alldf[alldf["symbol"] == key]
    if len(g) == 0:
        cov.append(dict(symbol=key, status="MISSING", first="", last="", days=0,
                        expected=0, gaps=0, gap_pct=0.0, sample_gaps=""))
        continue
    ds = set(g["date"]); first, last = min(ds), max(ds)
    gaps = interior_gaps(ds, first, last)
    lo, hi = cal_idx[first], cal_idx[last]
    expected = hi - lo + 1
    cov.append(dict(symbol=key, status="OK" if not gaps else "GAPS",
                    first=first, last=last, days=len(g), expected=expected,
                    gaps=len(gaps), gap_pct=round(len(gaps)/expected*100, 2),
                    sample_gaps=";".join(gaps[:5])))
covdf = pd.DataFrame(cov)

# ---- Nifty index ----
try:
    nd = yf.Ticker("^NSEI").history(period=PERIOD, auto_adjust=False)
    nd = nd[~nd.index.strftime("%Y-%m-%d").isin(phantoms2)]
    nifty = pd.DataFrame({
        "date": nd.index.strftime("%Y-%m-%d"),
        "nifty_open": nd["Open"].round(2), "nifty_high": nd["High"].round(2),
        "nifty_low": nd["Low"].round(2), "nifty_close": nd["Close"].round(2),
        "nifty_volume": nd["Volume"].fillna(0).astype("int64")})
    nifty.to_csv(NIFTY, index=False)
except Exception as e:
    print("nifty error:", e, flush=True)

# ---- write ----
alldf = alldf[["date","symbol","open","high","low","close","volume","adjusted_close","turnover"]]
alldf.to_csv(MASTER, index=False, compression="gzip")
covdf.to_csv(COVER, index=False)

# ---- summary ----
print("\n" + "="*64)
print("10-YEAR DATASET SUMMARY")
print("="*64)
print(f"rows                : {len(alldf):,}")
print(f"symbols with data   : {alldf['symbol'].nunique()}/{len(syms)}")
print(f"date range          : {master_cal[0]} .. {master_cal[-1]} ({len(master_cal)} trading days)")
print(f"phantom dates removed: {len(phantoms2)}")
print(f"status OK (no gaps) : {(covdf['status']=='OK').sum()}")
print(f"status GAPS         : {(covdf['status']=='GAPS').sum()}")
print(f"status MISSING      : {(covdf['status']=='MISSING').sum()}")
print(f"symbols with full ~10y (start <= {master_cal[10]}): {(covdf['first']<=master_cal[10]).sum()}")
tot_gaps = covdf['gaps'].sum()
print(f"total interior gap-days across all stocks: {tot_gaps} "
      f"({tot_gaps/max(1,len(alldf))*100:.3f}% of rows)")
print(f"\nworst 10 by gaps:")
print(covdf[covdf['gaps']>0].nlargest(10,'gaps')[['symbol','days','expected','gaps','gap_pct']].to_string(index=False))
print(f"\nMISSING symbols ({(covdf['status']=='MISSING').sum()}):",
      ", ".join(covdf[covdf['status']=='MISSING']['symbol'].tolist()))
print(f"\nwrote:\n  {MASTER}\n  {COVER}\n  {NIFTY}")
print("DONE", flush=True)
