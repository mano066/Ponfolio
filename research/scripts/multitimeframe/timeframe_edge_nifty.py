"""Which timeframe's signal best predicts a swing move? — NIFTY index only.

This is the ONLY honest way to compare 15m/30m/60m/2h/5h/1d "analysis": run the
IDENTICAL swing signal on each timeframe of the one instrument that actually has
intraday history — the NIFTY index (1-minute, 2008-2020, NO volume). It measures
the FORWARD SWING RETURN (held in calendar days, resolved on daily closes) after
a signal fires on each timeframe, so the results are directly comparable.

HARD LABELS:
  [MEASURED, INDEX-ONLY] NIFTY, 2008-2020, no volume. NOT a tradeable stock-pick
  backtest. There is NO per-stock intraday data, so this cannot be extended to
  the ~750-name swing universe. It answers "does finer-timeframe timing improve a
  swing entry on the index?" — nothing more.

Run: backend/.venv/Scripts/python.exe research/scripts/multitimeframe/timeframe_edge_nifty.py
Out: research/data/timeframe_edge_nifty.json
"""
from __future__ import annotations

import glob
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
D = Path(__file__).resolve().parents[2] / "data"
OUT = D / "timeframe_edge_nifty.json"
NSE = "Asia/Kolkata"
COST = 0.30                      # % round trip
HOLDS = [5, 10]                  # forward swing horizons (trading days)

OHLCV = {"open": "first", "high": "max", "low": "min", "close": "last"}
TFS = {"15m": "15min", "30m": "30min", "60m": "60min",
       "2h": "120min", "5h": "300min", "1d": None}


def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))


print("loading NIFTY 1-minute (index-only)...", flush=True)
paths = [p for p in glob.glob(str(D/"intraday_lake"/"**"/"*.parquet"), recursive=True)
         if "symbol=NIFTY" in p and "_quarantine" not in p]
m1 = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
m1["timestamp_ist"] = pd.to_datetime(m1["timestamp_ist"])
m1 = m1.set_index("timestamp_ist").sort_index()[["open", "high", "low", "close"]]
if m1.index.tz is None:
    m1.index = m1.index.tz_localize(NSE)
m1 = m1[~m1.index.duplicated(keep="last")]
print(f"NIFTY 1-min rows: {len(m1):,}  {m1.index.min().date()} -> {m1.index.max().date()}", flush=True)


def resample_tf(rule):
    if rule is None:
        # daily from 1-min
        g = m1.groupby(m1.index.date).agg(OHLCV)
        g.index = pd.to_datetime(g.index)
        return g
    pieces = []
    for _, sess in m1.groupby(m1.index.date):
        b = sess.resample(rule, origin="start_day", offset="9h15min",
                          label="left", closed="left").agg(OHLCV).dropna(subset=["close"])
        pieces.append(b)
    return pd.concat(pieces).sort_index()


# Daily bars = the swing "clock" for forward returns (held in calendar days).
daily = resample_tf(None)
dclose = daily["close"].to_numpy()
dopen = daily["open"].to_numpy()
ddates = np.array([d.date() for d in daily.index])
dpos = {d: i for i, d in enumerate(ddates)}
print(f"daily sessions: {len(daily)}", flush=True)


def signal_bars(tf_df):
    """Identical swing-pullback-continuation signal on any timeframe:
    uptrend (EMA20>EMA50), price above/reclaiming EMA20, RSI cooled [45,65].
    Returns the list of signal *dates* (one per calendar day: first fire)."""
    c = tf_df["close"]
    e20, e50, r = ema(c, 20), ema(c, 50), rsi(c)
    sig = (e20 > e50) & (c > e20) & (r >= 45) & (r <= 65)
    sig = sig.fillna(False)
    fired = tf_df.index[sig.to_numpy()]
    # one signal per calendar day (the first) — a swing entry is once/day
    seen, days = set(), []
    for ts in fired:
        d = ts.date()
        if d in seen:
            continue
        seen.add(d)
        days.append(d)
    return days


def evaluate(days, hold):
    """Enter next daily OPEN after the signal day; exit daily CLOSE `hold`
    sessions later. Net of round-trip cost. Comparable across timeframes."""
    nets = []
    for d in days:
        i = dpos.get(d)
        if i is None or i + 1 >= len(daily):
            continue
        entry = dopen[i + 1]
        ex_i = min(i + 1 + hold, len(daily) - 1)
        if entry <= 0:
            continue
        nets.append((dclose[ex_i] / entry - 1) * 100 - COST)
    if len(nets) < 30:
        return None
    a = np.array(nets); w = a > 0
    return dict(n=int(len(a)), win=round(float(w.mean()*100), 2),
                exp=round(float(a.mean()), 4), med=round(float(np.median(a)), 4),
                pf=round(float(a[w].sum()/max(1e-9, -a[~w].sum())), 3))


# Buy-and-hold / always-in reference over the same daily clock.
def reference(hold):
    nets = []
    for i in range(len(daily) - hold - 1):
        entry = dopen[i + 1]
        if entry <= 0:
            continue
        nets.append((dclose[min(i + 1 + hold, len(daily)-1)] / entry - 1) * 100 - COST)
    a = np.array(nets); w = a > 0
    return dict(n=int(len(a)), win=round(float(w.mean()*100), 2),
                exp=round(float(a.mean()), 4), pf=round(float(a[w].sum()/max(1e-9, -a[~w].sum())), 3))


print("\nevaluating each timeframe...", flush=True)
res = {"meta": {
    "instrument": "NIFTY index (1-min source)", "period": f"{m1.index.min().date()}..{m1.index.max().date()}",
    "cost_pct": COST, "holds_days": HOLDS, "volume": "absent (index)",
    "scope": "INDEX-ONLY methodology demo; NOT a stock-pick backtest; no per-stock intraday exists",
}, "by_timeframe": {}, "reference_always_in": {}}

for tf, rule in TFS.items():
    tf_df = resample_tf(rule)
    tf_df = tf_df.assign(_c=tf_df["close"])
    days = signal_bars(tf_df)
    res["by_timeframe"][tf] = {"signal_days": len(days),
                               **{f"hold_{h}d": evaluate(days, h) for h in HOLDS}}
    print(f"  {tf:>4}: {len(days)} signal-days", flush=True)

for h in HOLDS:
    res["reference_always_in"][f"hold_{h}d"] = reference(h)

OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

print("\n=== NIFTY-index timeframe edge (forward swing return, net of cost) ===")
print(f"{'timeframe':<10}{'sig-days':>9}{'5d exp%':>9}{'5d win%':>9}{'5d PF':>7}"
      f"{'10d exp%':>10}{'10d win%':>9}{'10d PF':>7}")
for tf in TFS:
    b = res["by_timeframe"][tf]
    h5, h10 = b["hold_5d"], b["hold_10d"]
    def g(m, k): return f"{m[k]:.3f}" if m else "n/a"
    print(f"{tf:<10}{b['signal_days']:>9}{g(h5,'exp'):>9}{g(h5,'win'):>9}{g(h5,'pf'):>7}"
          f"{g(h10,'exp'):>10}{g(h10,'win'):>9}{g(h10,'pf'):>7}")
ref5, ref10 = res["reference_always_in"]["hold_5d"], res["reference_always_in"]["hold_10d"]
print(f"{'ALWAYS-IN':<10}{'-':>9}{ref5['exp']:>9.3f}{ref5['win']:>9.2f}{ref5['pf']:>7.2f}"
      f"{ref10['exp']:>10.3f}{ref10['win']:>9.2f}{ref10['pf']:>7.2f}")
print(f"\nwrote {OUT}")
