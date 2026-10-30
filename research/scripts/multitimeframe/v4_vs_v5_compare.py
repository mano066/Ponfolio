"""Apples-to-apples v4 (production) vs v5 multi-timeframe shortlist.

Both engines run in ONE harness — identical exit (v4: no-TP, 2.5xATR close-stop,
exit next open, 20-session), identical costs (0.30% + slippage), identical
top-5/day, gap>4% skip, next-open entry, and identical TRAIN/VAL/TEST periods.

v4 = production v3 selection (momentum tier + quality gate + score>=55), the
incumbent. Reporting its TEST is not tuning — v4 is already frozen/deployed.

MEASURED: daily, survivorship-biased current universe, raw OHLC (same caveats as
MULTITIMEFRAME_STRATEGY_RESEARCH_2026-07-25.md). Lower-timeframe timing UNVERIFIED.

Run: backend/.venv/Scripts/python.exe research/scripts/multitimeframe/v4_vs_v5_compare.py
Out: research/data/v4_vs_v5_comparison.json
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
D = Path(__file__).resolve().parents[2] / "data"
OUT = D / "v4_vs_v5_comparison.json"

COST = 0.30
TOP_N = 5
GAP_MAX = 4.0
MIN_TURNOVER, MIN_PRICE = 1e7, 5.0
TRAIN, VAL, TEST = ("2011-01-01", "2019-12-31"), ("2020-01-01", "2022-12-31"), ("2023-01-01", "2026-12-31")


def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))


print("loading lake + nifty...", flush=True)
px = pd.read_csv(D/"nse_universe_2010_ohlcv.csv.gz",
                 usecols=["date", "symbol", "open", "high", "low", "close", "volume"],
                 dtype={"symbol": "category", "open": "f4", "high": "f4", "low": "f4",
                        "close": "f4", "volume": "f8"})
nfc = pd.read_csv(D/"nifty50_daily_2010.csv").sort_values("date").set_index("date")["nifty_close"].astype(float)
n_e50, n_e200 = ema(nfc, 50), ema(nfc, 200)
regime = {}
for dt in nfc.index:
    if pd.isna(n_e200[dt]): regime[dt] = "UNKNOWN"
    elif nfc[dt] > n_e200[dt] and n_e50[dt] > n_e200[dt]: regime[dt] = "BULL"
    elif nfc[dt] < n_e200[dt] and n_e50[dt] < n_e200[dt]: regime[dt] = "BEAR"
    else: regime[dt] = "SIDEWAYS"
nif_r63 = (nfc/nfc.shift(63) - 1).to_dict()

print("indicators...", flush=True)
SYM = {}
for sym, g in px.groupby("symbol", sort=False, observed=True):
    g = g.sort_values("date"); c = g["close"].astype(float).reset_index(drop=True)
    o = g["open"].astype(float).reset_index(drop=True); h = g["high"].astype(float).reset_index(drop=True)
    lo = g["low"].astype(float).reset_index(drop=True); v = g["volume"].astype(float).reset_index(drop=True)
    n = len(c)
    if n < 260: continue
    pc = c.shift(1); tr = pd.concat([h-lo, (h-pc).abs(), (lo-pc).abs()], axis=1).max(axis=1)
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    hh250 = c.rolling(250, min_periods=60).max()
    SYM[str(sym)] = dict(
        dates=g["date"].to_numpy(), o=o.to_numpy(), h=h.to_numpy(), l=lo.to_numpy(), c=c.to_numpy(),
        atr=tr.ewm(alpha=1/14, adjust=False).mean().to_numpy(),
        e20=e20.to_numpy(), e50=e50.to_numpy(), e200=e200.to_numpy(), rsi=rsi(c).to_numpy(),
        e50rise=(e50 > e50.shift(5)).to_numpy(), macdup=(ema(c, 12) > ema(c, 26)).to_numpy(),
        hh20=h.rolling(20).max().to_numpy(), bbw=((4*c.rolling(20).std())/c.rolling(20).mean().replace(0, np.nan)).to_numpy(),
        bbwq=((4*c.rolling(20).std())/c.rolling(20).mean().replace(0, np.nan)).rolling(100, min_periods=60).quantile(0.25).to_numpy(),
        turn=(c*v).rolling(20).mean().to_numpy(), ret20=(c/c.shift(20)-1).to_numpy(),
        ret60=(c/c.shift(63)-1).to_numpy(), dhi=(c/hh250-1).to_numpy(),
        idx={d: i for i, d in enumerate(g["date"].to_numpy())})
del px
print(f"symbols: {len(SYM)}", flush=True)


def liquid(a, j): return a["turn"][j] >= MIN_TURNOVER and a["c"][j] >= MIN_PRICE


# v4 = v3 selection from captured production signals
print("loading v3 signals for v4 baseline...", flush=True)
sig = pd.read_csv(D/"signals_2010.csv.gz")
sig = sig[sig["score"] >= 55].copy()
sig["quality"] = (~sig["counter_trend"]) & (sig["trend"] == "Up") & (sig["adx"] >= 25)
sig["r63"] = [SYM[s]["ret60"][SYM[s]["idx"][d]] if s in SYM and d in SYM[s]["idx"] else np.nan
              for s, d in zip(sig["symbol"].astype(str), sig["date"])]
sig["dhi"] = [SYM[s]["dhi"][SYM[s]["idx"][d]] if s in SYM and d in SYM[s]["idx"] else np.nan
              for s, d in zip(sig["symbol"].astype(str), sig["date"])]
sig["nifr63"] = sig["date"].map(nif_r63)
sig["momentum"] = ((sig["dhi"] >= -0.15) & (sig["r63"] > sig["nifr63"]) & (sig["r63"] > 0)).fillna(False)
v4sel = sig.sort_values(["date", "momentum", "quality", "score"],
                        ascending=[True, False, False, False]).groupby("date").head(TOP_N)
V4_KEYS = set(zip(v4sel["symbol"].astype(str), v4sel["date"]))


# v5 shortlist signal fns (same as mtf_backtest, distilled)
def s1(a, j):
    reg = regime.get(a["dates"][j])
    if reg != "BULL": return False
    c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
    return bool(c > e50 > e200 and a["e50rise"][j] and (a["l"][j] <= e20*1.02 or abs(c/e20-1) <= 0.02)
                and c > e20 and 40 <= a["rsi"][j] <= 62 and a["c"][j] > a["o"][j])


def s3(a, j):
    reg = regime.get(a["dates"][j]); dt = a["dates"][j]
    if reg != "BULL": return False
    c, e50, e200 = a["c"][j], a["e50"][j], a["e200"][j]
    if not (c > e50 > e200): return False
    if not (a["ret60"][j] > nif_r63.get(dt, np.nan)): return False   # relaxed RS (per ablation)
    return bool(j >= 1 and c >= a["hh20"][j-1]*0.92 and c > a["c"][j-1] and c > a["e20"][j])


def s2(a, j):
    reg = regime.get(a["dates"][j])
    if reg not in ("BULL", "SIDEWAYS"): return False
    c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
    return bool(c > e50 > e200 and np.isfinite(a["bbwq"][j]) and a["bbw"][j] <= a["bbwq"][j]
                and j >= 1 and c > a["hh20"][j-1] and c <= e20*1.15)   # no-volume variant


def s6(a, j):
    reg = regime.get(a["dates"][j])
    if reg != "BULL": return False
    c, e50, e200 = a["c"][j], a["e50"][j], a["e200"][j]
    return bool(c > e50 > e200 and a["macdup"][j] and 45 <= a["rsi"][j] < 70)  # no lower-tf gate


def v4(a, j): return (a["sym"], a["dates"][j]) in V4_KEYS  # placeholder; handled below


def build(sig_fn, hold, rank="ret60", is_v4=False):
    rows = []
    for s, a in SYM.items():
        c = a["c"]; n = len(c)
        for j in range(260, n-1):
            if not liquid(a, j): continue
            ok = (s, a["dates"][j]) in V4_KEYS if is_v4 else sig_fn(a, j)
            if not ok: continue
            e = float(a["o"][j+1]); cT = float(c[j]); atr = float(a["atr"][j])
            if not (e > 0 and atr > 0): continue
            gap = (e/cT-1)*100 if cT > 0 else 99
            if gap > GAP_MAX: continue
            m = min(hold, n-(j+1))
            if m < 1: continue
            rows.append(dict(date=a["dates"][j], sym=s, e=e, atr=atr, m=m,
                             rank=float(a[rank][j]) if np.isfinite(a[rank][j]) else -9,
                             op=a["o"][j+1:j+2+m].astype(float),
                             cl=a["c"][j+1:j+1+m].astype(float)))
    df = pd.DataFrame(rows)
    if df.empty: return df
    return df.sort_values(["date", "rank"], ascending=[True, False]).groupby("date").head(TOP_N).reset_index(drop=True)


def exit_v4(t, slip=0.0):
    e = t["e"]*(1+slip/100); sl = t["e"] - 2.5*t["atr"]
    for k in range(t["m"]):
        if t["cl"][k] <= sl:
            ex = t["op"][k+1] if k+1 < len(t["op"]) else t["cl"][k]
            return (ex*(1-slip/100)/e - 1)*100 - COST
    return (t["cl"][t["m"]-1]*(1-slip/100)/e - 1)*100 - COST


def metrics(nets):
    if len(nets) < 50: return None
    nets = np.asarray(nets, float); w = nets > 0; wins, losses = nets[w], nets[~w]
    tw = wins.sum()
    return dict(n=int(len(nets)), win=round(float(w.mean()*100), 2), exp=round(float(nets.mean()), 4),
                pf=round(float(tw/max(1e-9, -losses.sum())), 3),
                top5_share=round(float(np.sort(wins)[-5:].sum()/tw), 3) if tw > 0 and len(wins) >= 5 else None)


def portfolio(df, cap=1_000_000, maxpos=8):
    if not len(df): return None
    df = df.sort_values("date").reset_index(drop=True); free = []; trades = []
    for _, r in df.iterrows():
        d0 = r["date"]; free = [x for x in free if x > d0]
        if len(free) >= maxpos: continue
        net = exit_v4(r)/100.0; a = SYM[r["sym"]]; j = a["idx"][d0]
        d1 = a["dates"][min(j+r["m"], len(a["dates"])-1)]; free.append(d1); trades.append((d1, net))
    if not trades: return None
    t = pd.DataFrame(trades, columns=["exit", "net"]).sort_values("exit")
    per = cap/maxpos; eq = cap; curve = []
    for day, grp in t.groupby("exit"):
        eq += per*grp["net"].sum(); curve.append((day, eq))
    s = pd.Series([x[1] for x in curve], index=pd.to_datetime([x[0] for x in curve]))
    yrs = max((s.index[-1]-s.index[0]).days/365.25, 0.5)
    dd = (s/s.cummax()-1).min()
    cagr = (s.iloc[-1]/cap)**(1/yrs)-1
    return dict(cagr_pct=round(float(cagr*100), 2), max_dd_pct=round(float(dd*100), 2),
                calmar=round(float(cagr/abs(dd)), 2) if dd < 0 else 0, n_taken=int(len(t)))


def dates_of(df): return df["date"].to_numpy() if len(df) else np.array([])


ENGINES = {
    "v4_production": (None, 20, True),
    "v5_S1_trend_pullback": (s1, 20, False),
    "v5_S3_rs_continuation": (s3, 20, False),
    "v5_S2_vol_contraction": (s2, 20, False),
    "v5_S6_daily_momentum": (s6, 20, False),
}

print("\nrunning engines in one harness...", flush=True)
comp = {"meta": {"cost_pct": COST, "top_n": TOP_N, "exit": "v4 no-TP/2.5ATR close/20d",
                 "periods": {"train": TRAIN, "val": VAL, "test": TEST},
                 "caveat": "daily, survivorship-biased, raw OHLC; lower-TF timing unverified"},
        "engines": {}}
for name, (fn, hold, isv4) in ENGINES.items():
    df = build(fn, hold, is_v4=isv4)
    dts = dates_of(df)
    nets = {p: np.array([exit_v4(r) for _, r in df[(dts >= lo) & (dts <= hi)].iterrows()])
            for p, (lo, hi) in (("train", TRAIN), ("val", VAL), ("test", TEST))} if len(df) else {}
    comp["engines"][name] = {
        "n_all": int(len(df)),
        "train": metrics(nets.get("train", [])) if len(df) else None,
        "val": metrics(nets.get("val", [])) if len(df) else None,
        "test": metrics(nets.get("test", [])) if len(df) else None,
        "portfolio_full": portfolio(df),
    }
    print(f"  {name} done (n={len(df)})", flush=True)

OUT.write_text(json.dumps(comp, indent=2, default=str), encoding="utf-8")

print("\n=== v4 vs v5 — expectancy %/trade (identical harness) ===")
print(f"{'engine':<26}{'nAll':>7}{'TRAIN':>8}{'VAL':>8}{'TEST':>8}{'PFval':>7}{'CAGR':>7}{'maxDD':>8}{'Calmar':>7}")
for name, e in comp["engines"].items():
    def g(p, k): return e[p][k] if e[p] else None
    pf = g("val", "pf"); pr = e["portfolio_full"] or {}
    def s(x, d=2): return f"{x:.{d}f}" if isinstance(x, (int, float)) else "n/a"
    print(f"{name:<26}{e['n_all']:>7}{s(g('train','exp')):>8}{s(g('val','exp')):>8}"
          f"{s(g('test','exp')):>8}{s(pf):>7}{s(pr.get('cagr_pct')):>7}"
          f"{s(pr.get('max_dd_pct')):>8}{s(pr.get('calmar')):>7}")
print(f"\nwrote {OUT}")
