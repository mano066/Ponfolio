"""Bias-free v4-style vs v5 comparison on the survivorship-free universe.

Consumes research/data/pit_universe_daily.parquet (built by universe_builder.py
`build`) — the point-in-time universe INCLUDING delisted/renamed names, keyed by
ISIN. Re-runs a v4-style momentum baseline and the v5 regime-adaptive ensemble on
this unbiased panel, walk-forward, and prints the result next to the
survivorship-BIASED numbers so the bias is quantified.

Run AFTER the full build completes:
  backend/.venv/Scripts/python.exe research/scripts/v5/bias_free_compare.py
Out: research/data/v5_biasfree_comparison.json

CAVEATS: bhavcopy OHLCV is RAW (not split/bonus adjusted) — a follow-on CA
adjustment is needed before fully trusting multi-day returns across a split; the
survivorship effect (the point here) dominates and is what this isolates.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
D = Path(__file__).resolve().parents[2] / "data"
PANEL = D / "pit_universe_daily.parquet"
OUT = D / "v5_biasfree_comparison.json"

COST, TOP_N, GAP_MAX = 0.30, 5, 4.0
MIN_TURNOVER, MIN_PRICE = 1e7, 5.0
STOP_ATR, HOLD = 2.5, 20
TRAIN, VAL, TEST = (2011, 2019), (2020, 2022), (2023, 2026)


def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))


def load_panel():
    if not PANEL.exists():
        raise SystemExit(f"{PANEL} not found — run `universe_builder.py build` first.")
    df = pd.read_parquet(PANEL)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["isin", "date"])


def nifty_series():
    nf = pd.read_csv(D/"nifty50_daily_2010.csv").sort_values("date")
    nf["date"] = pd.to_datetime(nf["date"])
    c = nf.set_index("date")["nifty_close"].astype(float)
    e50, e200 = ema(c, 50), ema(c, 200)
    reg = {}
    for dt in c.index:
        if pd.isna(e200[dt]): reg[dt] = "UNKNOWN"
        elif c[dt] > e200[dt] and e50[dt] > e200[dt]: reg[dt] = "BULL"
        elif c[dt] < e200[dt] and e50[dt] < e200[dt]: reg[dt] = "BEAR"
        else: reg[dt] = "SIDEWAYS"
    r63 = (c/c.shift(63)-1)
    return {d.date(): reg[d] for d in c.index}, {d.date(): r63[d] for d in c.index}


def build_arrays(panel):
    """Per-ISIN daily arrays (raw OHLCV). ISIN keying handles renames/delisting."""
    SYM = {}
    for isin, g in panel.groupby("isin", observed=True):
        if len(g) < 260:
            continue
        c = g["close"].astype(float).reset_index(drop=True)
        o = g["open"].astype(float).reset_index(drop=True)
        h = g["high"].astype(float).reset_index(drop=True)
        lo = g["low"].astype(float).reset_index(drop=True)
        turn = g["turnover"].astype(float).reset_index(drop=True)
        v = g["volume"].astype(float).reset_index(drop=True)
        pc = c.shift(1); tr = pd.concat([h-lo, (h-pc).abs(), (lo-pc).abs()], axis=1).max(axis=1)
        e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
        SYM[isin] = dict(
            sym=g["symbol"].iloc[-1], dates=g["date"].dt.date.to_numpy(),
            o=o.to_numpy(), h=h.to_numpy(), l=lo.to_numpy(), c=c.to_numpy(),
            atr=tr.ewm(alpha=1/14, adjust=False).mean().to_numpy(),
            e20=e20.to_numpy(), e50=e50.to_numpy(), e200=e200.to_numpy(), rsi=rsi(c).to_numpy(),
            e50rise=(e50 > e50.shift(5)).to_numpy(), macdup=(ema(c, 12) > ema(c, 26)).to_numpy(),
            hh20=h.rolling(20).max().to_numpy(), hh250=c.rolling(250, min_periods=60).max().to_numpy(),
            bbw=((4*c.rolling(20).std())/c.rolling(20).mean().replace(0, np.nan)).to_numpy(),
            bbwq=((4*c.rolling(20).std())/c.rolling(20).mean().replace(0, np.nan)).rolling(100, min_periods=60).quantile(0.25).to_numpy(),
            turn=(turn if turn.notna().any() else c*v).rolling(20).mean().to_numpy(),
            vratio=(v/v.rolling(20).mean().replace(0, np.nan)).to_numpy(),
            ret63=(c/c.shift(63)-1).to_numpy(),
            idx={d: i for i, d in enumerate(g["date"].dt.date.to_numpy())})
    return SYM


def make_signals(SYM, REG, NIFR63):
    def liquid(a, j): return a["turn"][j] >= MIN_TURNOVER and a["c"][j] >= MIN_PRICE

    def v4_proxy(a, j):   # v3 momentum + quality (trend), from raw OHLCV
        reg = REG.get(a["dates"][j])
        c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
        if not (c > e20 > e50): return False
        near_hi = a["hh250"][j] > 0 and c >= 0.85*a["hh250"][j]
        rs = a["ret63"][j] > NIFR63.get(a["dates"][j], np.nan)
        return bool(near_hi and rs and a["ret63"][j] > 0)

    def v5(a, j):         # regime-adaptive ensemble
        reg = REG.get(a["dates"][j]); c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
        if reg == "BULL":
            if (c > e50 > e200 and a["e50rise"][j] and (a["l"][j] <= e20*1.02 or abs(c/e20-1) <= 0.02)
                    and c > e20 and 40 <= a["rsi"][j] <= 62 and c > a["o"][j]): return True
            if (c > e50 > e200 and a["ret63"][j] > NIFR63.get(a["dates"][j], np.nan)
                    and j >= 1 and c >= a["hh20"][j-1]*0.92 and c > a["c"][j-1] and c > e20): return True
            if c > e50 > e200 and a["macdup"][j] and 45 <= a["rsi"][j] < 70: return True
        elif reg == "SIDEWAYS":
            if (c > e50 > e200 and np.isfinite(a["bbwq"][j]) and a["bbw"][j] <= a["bbwq"][j]
                    and j >= 1 and c > a["hh20"][j-1] and c <= e20*1.15
                    and np.isfinite(a["vratio"][j]) and a["vratio"][j] >= 2.0): return True
        return False
    return liquid, v4_proxy, v5


def run(SYM, liquid, sig_fn):
    rows = []
    for isin, a in SYM.items():
        c = a["c"]; n = len(c)
        for j in range(260, n-1):
            if not liquid(a, j) or not sig_fn(a, j): continue
            e = float(a["o"][j+1]); cT = float(c[j]); atr = float(a["atr"][j])
            if not (e > 0 and atr > 0) or (e/cT-1)*100 > GAP_MAX: continue
            m = min(HOLD, n-(j+1))
            if m < 1: continue
            rows.append(dict(date=a["dates"][j], e=e, atr=atr, m=m,
                             rank=float(a["ret63"][j]) if np.isfinite(a["ret63"][j]) else -9,
                             op=a["o"][j+1:j+2+m].astype(float), cl=a["c"][j+1:j+1+m].astype(float)))
    df = pd.DataFrame(rows)
    if df.empty: return df
    df["year"] = df["date"].map(lambda d: d.year)
    return df.sort_values(["date", "rank"], ascending=[True, False]).groupby("date").head(TOP_N).reset_index(drop=True)


def exit_v4(t):
    e = t["e"]; sl = e - STOP_ATR*t["atr"]
    for k in range(t["m"]):
        if t["cl"][k] <= sl:
            ex = t["op"][k+1] if k+1 < len(t["op"]) else t["cl"][k]
            return (ex/e-1)*100 - COST
    return (t["cl"][t["m"]-1]/e-1)*100 - COST


def metrics(df, split):
    lo, hi = split; d = df[(df["year"] >= lo) & (df["year"] <= hi)]
    if len(d) < 50: return None
    nets = np.array([exit_v4(r) for _, r in d.iterrows()]); w = nets > 0
    return dict(n=int(len(nets)), win=round(float(w.mean()*100), 2), exp=round(float(nets.mean()), 4),
                pf=round(float(nets[w].sum()/max(1e-9, -nets[~w].sum())), 3))


def main():
    print("loading survivorship-free panel...", flush=True)
    panel = load_panel()
    print(f"  rows={len(panel):,}  ISINs={panel['isin'].nunique():,}  "
          f"{panel['date'].min().date()}..{panel['date'].max().date()}", flush=True)
    REG, NIFR63 = nifty_series()
    SYM = build_arrays(panel)
    print(f"  usable ISINs (>=260d): {len(SYM):,}", flush=True)
    liquid, v4_proxy, v5 = make_signals(SYM, REG, NIFR63)
    res = {"meta": {"universe": "survivorship-free point-in-time (ISIN-keyed, incl. delisted)",
                    "prices": "RAW bhavcopy OHLCV (not CA-adjusted)", "cost": COST}, "engines": {}}
    for name, fn in (("v4_style_momentum", v4_proxy), ("v5_ensemble", v5)):
        df = run(SYM, liquid, fn)
        res["engines"][name] = {"n_all": int(len(df)),
                                "train": metrics(df, TRAIN), "val": metrics(df, VAL), "test": metrics(df, TEST)}
        print(f"  {name}: n={len(df)}", flush=True)
    OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("\n=== BIAS-FREE (survivorship-free) — expectancy %/trade ===")
    print(f"{'engine':<22}{'nAll':>8}{'TRAIN':>8}{'VAL':>8}{'TEST':>8}")
    for name, e in res["engines"].items():
        def g(p): return f"{e[p]['exp']:.3f}" if e[p] else "n/a"
        print(f"{name:<22}{e['n_all']:>8}{g('train'):>8}{g('val'):>8}{g('test'):>8}")
    print("\nCompare to survivorship-BIASED (from v4_vs_v5_comparison.json): "
          "v4 test 1.37 / v5(S1) test 2.13 — the gap between these tables is the bias.")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
