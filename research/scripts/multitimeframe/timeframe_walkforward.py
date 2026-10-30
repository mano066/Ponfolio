"""Walk-forward per-timeframe swing accuracy — NIFTY + BANKNIFTY (index-only).

Answers: which of 15m/30m/60m/2h/5h/1d — and which MULTI-timeframe combination —
best predicts a forward swing move on the index, evaluated out-of-sample.

Splits (as requested):
  TRAIN 2008-2015  ·  VAL 2016-2018  ·  TEST 2019-2020
Instruments: NIFTY (2008-2020) and BANKNIFTY (2010-2020), both 1-minute, NO
volume (index). Ranking is by TEST expectancy with stability across all splits.

Signal components (identical across timeframes, decided at each day's LAST
completed bar of the timeframe; entry = NEXT daily open; exit = daily close after
`hold` sessions; net of round-trip cost — so all timeframes are comparable and
leakage-free):
  trend(TF)   = EMA20 > EMA50 on TF
  trigger(TF) = close > EMA20 and RSI14 in [45,65] on TF
Single-TF signal      = trend(TF) & trigger(TF)
Multi-TF (Hi x Lo)    = trend(Hi) & trigger(Lo)   (higher-TF regime + lower-TF entry)

HARD LABEL [MEASURED, INDEX-ONLY]: NIFTY/BANKNIFTY only. NOT a tradeable stock
backtest — no per-stock intraday exists. Suggestive for the multi-timeframe
question; not a stock-pick result.

Run: backend/.venv/Scripts/python.exe research/scripts/multitimeframe/timeframe_walkforward.py
Out: research/data/timeframe_walkforward.json
"""
from __future__ import annotations

import glob
import json
import warnings
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
D = Path(__file__).resolve().parents[2] / "data"
OUT = D / "timeframe_walkforward.json"
NSE = "Asia/Kolkata"
COST = 0.30
HOLDS = [5, 10]
SPLITS = {"train": (2008, 2015), "val": (2016, 2018), "test": (2019, 2020)}
OHLCV = {"open": "first", "high": "max", "low": "min", "close": "last"}
TF_ORDER = ["15m", "30m", "60m", "2h", "5h", "1d"]     # fine -> coarse
TF_RULE = {"15m": "15min", "30m": "30min", "60m": "60min",
           "2h": "120min", "5h": "300min", "1d": None}


def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))


def load_1m(symbol):
    # Search BOTH lakes and union — the default lake's BANKNIFTY is truncated at
    # 2016-06; the staged Kaggle lake carries it through 2020-11. Dedup on
    # timestamp so the union gives full 2010-2020 coverage.
    paths = []
    for lake in ("intraday_lake", "intraday_lake_stage_kaggle"):
        paths += [p for p in glob.glob(str(D/lake/"**"/"*.parquet"), recursive=True)
                  if f"symbol={symbol}" in p and "_quarantine" not in p]
    df = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    df["timestamp_ist"] = pd.to_datetime(df["timestamp_ist"])
    df = df.set_index("timestamp_ist").sort_index()[["open", "high", "low", "close"]]
    if df.index.tz is None:
        df.index = df.index.tz_localize(NSE)
    return df[~df.index.duplicated(keep="last")]


def resample_tf(m1, rule):
    if rule is None:
        g = m1.groupby(m1.index.date).agg(OHLCV); g.index = pd.to_datetime(g.index); return g
    pieces = []
    for _, sess in m1.groupby(m1.index.date):
        b = sess.resample(rule, origin="start_day", offset="9h15min",
                          label="left", closed="left").agg(OHLCV).dropna(subset=["close"])
        pieces.append(b)
    return pd.concat(pieces).sort_index()


def daily_state(tf_df):
    """Per-DAY trend & trigger booleans = the state at the day's LAST completed
    TF bar (end-of-day reading; entry is next open, so no lookahead)."""
    c = tf_df["close"]
    e20, e50, r = ema(c, 20), ema(c, 50), rsi(c)
    trend = (e20 > e50)
    trigger = (c > e20) & (r >= 45) & (r <= 65)
    df = pd.DataFrame({"date": [t.date() for t in tf_df.index],
                       "trend": trend.to_numpy(), "trig": trigger.to_numpy()})
    last = df.groupby("date").last()
    return last["trend"].fillna(False), last["trig"].fillna(False)


def evaluate(sig_dates, dpos, dopen, dclose, hold, split, slip=0.0):
    lo, hi = split
    nets = []
    for d in sig_dates:
        if not (lo <= d.year <= hi):
            continue
        key = d.date() if hasattr(d, "date") else d   # dpos is keyed by date objects
        i = dpos.get(key)
        if i is None or i + 1 >= len(dopen):
            continue
        entry = dopen[i + 1] * (1 + slip / 100)        # buy slightly worse
        if entry <= 0:
            continue
        ex = dclose[min(i + 1 + hold, len(dclose) - 1)] * (1 - slip / 100)
        nets.append((ex / entry - 1) * 100 - COST)
    if len(nets) < 25:
        return None
    a = np.array(nets); w = a > 0
    return dict(n=int(len(a)), acc=round(float(w.mean()*100), 2), exp=round(float(a.mean()), 4),
                pf=round(float(a[w].sum()/max(1e-9, -a[~w].sum())), 3))


def analyze_instrument(symbol):
    print(f"loading {symbol}...", flush=True)
    m1 = load_1m(symbol)
    print(f"  {symbol}: {len(m1):,} 1-min rows {m1.index.min().date()}->{m1.index.max().date()}", flush=True)
    daily = resample_tf(m1, None)
    dclose, dopen = daily["close"].to_numpy(), daily["open"].to_numpy()
    ddates = [d.date() for d in daily.index]
    dpos = {d: i for i, d in enumerate(ddates)}
    # per-TF daily state
    trend, trig = {}, {}
    for tf in TF_ORDER:
        tr, tg = daily_state(resample_tf(m1, TF_RULE[tf]))
        trend[tf], trig[tf] = tr, tg
    all_days = pd.Index(sorted(set().union(*[set(trend[tf].index) for tf in TF_ORDER])))

    def sig_dates(mask_series):
        idx = mask_series[mask_series].index
        return pd.to_datetime(list(idx))

    signals = {}
    # single-TF
    for tf in TF_ORDER:
        m = (trend[tf].reindex(all_days, fill_value=False)
             & trig[tf].reindex(all_days, fill_value=False))
        signals[f"single:{tf}"] = sig_dates(m)
    # 2-TF: higher-TF trend filter x lower-TF trigger (all coarse>fine pairs)
    for fine, coarse in combinations(TF_ORDER, 2):   # order fine->coarse
        m = (trend[coarse].reindex(all_days, fill_value=False)
             & trig[fine].reindex(all_days, fill_value=False))
        signals[f"mtf2:{coarse}_trend+{fine}_trig"] = sig_dates(m)
    # 3-TF stacks: coarse trend & mid trend & fine trigger (full alignment)
    for fine, mid, coarse in combinations(TF_ORDER, 3):
        m = (trend[coarse].reindex(all_days, fill_value=False)
             & trend[mid].reindex(all_days, fill_value=False)
             & trig[fine].reindex(all_days, fill_value=False))
        signals[f"mtf3:{coarse}+{mid}_trend+{fine}_trig"] = sig_dates(m)

    out = {}
    for name, dates in signals.items():
        rec = {"signal_days_total": int(len(dates))}
        for h in HOLDS:
            rec[f"hold_{h}d"] = {s: evaluate(dates, dpos, dopen, dclose, h, sp)
                                 for s, sp in SPLITS.items()}
        out[name] = rec
    # always-in benchmark
    ref = {}
    for h in HOLDS:
        ref[f"hold_{h}d"] = {}
        for s, (lo, hi) in SPLITS.items():
            nets = []
            for i in range(len(daily) - 1):
                if not (lo <= ddates[i].year <= hi):
                    continue
                e = dopen[i + 1]
                if e <= 0:
                    continue
                nets.append((dclose[min(i+1+h, len(dclose)-1)]/e - 1)*100 - COST)
            a = np.array(nets); w = a > 0
            ref[f"hold_{h}d"][s] = dict(n=int(len(a)), acc=round(float(w.mean()*100), 2),
                                        exp=round(float(a.mean()), 4),
                                        pf=round(float(a[w].sum()/max(1e-9, -a[~w].sum())), 3)) if len(a) else None
    return {"signals": out, "always_in": ref,
            "daily_sessions": len(daily), "range": f"{ddates[0]}..{ddates[-1]}"}


results = {"meta": {"instruments": ["NIFTY", "BANKNIFTY"], "splits": SPLITS,
                    "cost_pct": COST, "holds": HOLDS, "volume": "absent (index)",
                    "scope": "INDEX-ONLY; not a stock backtest; no per-stock intraday exists"},
           "instruments": {}}
for sym in ("NIFTY", "BANKNIFTY"):
    results["instruments"][sym] = analyze_instrument(sym)

OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


def rank_table(sym, hold):
    inst = results["instruments"][sym]
    rows = []
    for name, rec in inst["signals"].items():
        h = rec[f"hold_{hold}d"]
        tr, va, te = h["train"], h["val"], h["test"]
        if not (tr and va and te):
            continue
        stable = tr["exp"] > 0 and va["exp"] > 0 and te["exp"] > 0
        rows.append((name, tr, va, te, stable))
    rows.sort(key=lambda r: r[3]["exp"], reverse=True)   # by TEST expectancy
    return rows


for sym in ("NIFTY", "BANKNIFTY"):
    for hold in HOLDS:
        rows = rank_table(sym, hold)
        print(f"\n=== {sym} — {hold}-day swing, ranked by TEST expectancy (top 12) ===")
        print(f"{'signal':<34}{'TRAIN exp/acc':>16}{'VAL exp/acc':>15}{'TEST exp/acc':>16}{'stable':>8}")
        for name, tr, va, te, stable in rows[:12]:
            print(f"{name:<34}{tr['exp']:>7.3f}/{tr['acc']:<6.1f}{va['exp']:>7.3f}/{va['acc']:<5.1f}"
                  f"{te['exp']:>8.3f}/{te['acc']:<6.1f}{'YES' if stable else '':>8}")
        ai = results["instruments"][sym]["always_in"][f"hold_{hold}d"]
        if ai["train"] and ai["test"]:
            print(f"{'ALWAYS-IN (benchmark)':<34}{ai['train']['exp']:>7.3f}/{ai['train']['acc']:<6.1f}"
                  f"{ai['val']['exp']:>7.3f}/{ai['val']['acc']:<5.1f}{ai['test']['exp']:>8.3f}/{ai['test']['acc']:<6.1f}")

# ── cost/slippage sensitivity on the stable winners (BANKNIFTY 10-day) ──
print("\n=== SLIPPAGE SENSITIVITY — BANKNIFTY 10-day TEST expectancy (stable signals) ===")
print(f"{'signal':<34}{'0bps':>8}{'5bps':>8}{'10bps':>8}{'20bps':>8}")
sym = "BANKNIFTY"
m1 = load_1m(sym)
daily = resample_tf(m1, None)
dclose, dopen = daily["close"].to_numpy(), daily["open"].to_numpy()
ddates = [d.date() for d in daily.index]; dpos = {d: i for i, d in enumerate(ddates)}
trendB, trigB = {}, {}
for tf in TF_ORDER:
    trendB[tf], trigB[tf] = daily_state(resample_tf(m1, TF_RULE[tf]))
allB = pd.Index(sorted(set().union(*[set(trendB[tf].index) for tf in TF_ORDER])))
stable_defs = {
    "single:60m": trendB["60m"].reindex(allB, fill_value=False) & trigB["60m"].reindex(allB, fill_value=False),
    "mtf2:5h_trend+15m_trig": trendB["5h"].reindex(allB, fill_value=False) & trigB["15m"].reindex(allB, fill_value=False),
    "mtf2:60m_trend+15m_trig": trendB["60m"].reindex(allB, fill_value=False) & trigB["15m"].reindex(allB, fill_value=False),
    "mtf2:2h_trend+15m_trig": trendB["2h"].reindex(allB, fill_value=False) & trigB["15m"].reindex(allB, fill_value=False),
}
sens = {}
for name, mask in stable_defs.items():
    dts = pd.to_datetime(list(mask[mask].index))
    row = {}
    for slip in (0.0, 0.05, 0.10, 0.20):
        m = evaluate(dts, dpos, dopen, dclose, 10, SPLITS["test"], slip=slip)
        row[f"slip_{slip}"] = m["exp"] if m else None
    sens[name] = row
    print(f"{name:<34}" + "".join(f"{row[f'slip_{s}']:>8.3f}" if row[f'slip_{s}'] is not None else f"{'n/a':>8}"
                                    for s in (0.0, 0.05, 0.10, 0.20)))
results["slippage_sensitivity_bnf_10d_test"] = sens
OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
print(f"\nwrote {OUT}")
