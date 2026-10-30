"""Does VOLUME improve daily swing selection? — 2010-2026 stock lake.

The daily per-stock lake HAS volume (unlike the index intraday data). This tests
several volume constructs as overlays on the v5 shortlist and asks, in
walk-forward, whether any of them beats the volume-free base out-of-sample.

Volume constructs (all daily, causal):
  vol_ratio      = volume / SMA20(volume)
  vol_expansion  = vol_ratio >= X      (breakout confirmation)
  vol_dryup      = vol_ratio <= X      (healthy light-volume pullback)
  obv_rising     = OBV > SMA20(OBV)    (accumulation)

Overlays tested:
  S1 pullback   : base / +dryup(<=0.9) / +surge(>=1.3)
  S2 breakout   : base / +expansion(>=1.5) / +expansion(>=2.0)
  S6 momentum   : base / +obv_rising / +expansion(>=1.3)

Protocol identical to the MTF daily engine: top-5/day, next-open entry, gap>4%
skip, v4 exit (no-TP, 2.5xATR close, 20 sessions), 0.30% cost, TRAIN 2011-2019 /
VAL 2020-2022 / TEST 2023-2026. [MEASURED, survivorship-biased daily universe.]

Run: backend/.venv/Scripts/python.exe research/scripts/multitimeframe/volume_study.py
Out: research/data/volume_study.json
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
D = Path(__file__).resolve().parents[2] / "data"
OUT = D / "volume_study.json"
COST, TOP_N, GAP_MAX = 0.30, 5, 4.0
MIN_TURNOVER, MIN_PRICE = 1e7, 5.0
TRAIN, VAL, TEST = ("2011-01-01", "2019-12-31"), ("2020-01-01", "2022-12-31"), ("2023-01-01", "2026-12-31")


def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))


print("loading daily lake (with volume)...", flush=True)
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

print("indicators + volume features...", flush=True)
SYM = {}
for sym, g in px.groupby("symbol", sort=False, observed=True):
    g = g.sort_values("date"); c = g["close"].astype(float).reset_index(drop=True)
    o = g["open"].astype(float).reset_index(drop=True); h = g["high"].astype(float).reset_index(drop=True)
    lo = g["low"].astype(float).reset_index(drop=True); v = g["volume"].astype(float).reset_index(drop=True)
    if len(c) < 260: continue
    pc = c.shift(1); tr = pd.concat([h-lo, (h-pc).abs(), (lo-pc).abs()], axis=1).max(axis=1)
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    vma20 = v.rolling(20).mean()
    vratio = (v / vma20.replace(0, np.nan))
    # OBV
    sign = np.sign(c.diff().fillna(0.0))
    obv = (sign * v).cumsum()
    obv_rise = (obv > obv.rolling(20).mean())
    SYM[str(sym)] = dict(
        dates=g["date"].to_numpy(), o=o.to_numpy(), h=h.to_numpy(), l=lo.to_numpy(), c=c.to_numpy(),
        atr=tr.ewm(alpha=1/14, adjust=False).mean().to_numpy(),
        e20=e20.to_numpy(), e50=e50.to_numpy(), e200=e200.to_numpy(), rsi=rsi(c).to_numpy(),
        e50rise=(e50 > e50.shift(5)).to_numpy(), macdup=(ema(c, 12) > ema(c, 26)).to_numpy(),
        hh20=h.rolling(20).max().to_numpy(),
        bbw=((4*c.rolling(20).std())/c.rolling(20).mean().replace(0, np.nan)).to_numpy(),
        bbwq=((4*c.rolling(20).std())/c.rolling(20).mean().replace(0, np.nan)).rolling(100, min_periods=60).quantile(0.25).to_numpy(),
        turn=(c*v).rolling(20).mean().to_numpy(), ret60=(c/c.shift(63)-1).to_numpy(),
        vratio=vratio.to_numpy(), obv_rise=obv_rise.to_numpy(),
        idx={d: i for i, d in enumerate(g["date"].to_numpy())})
del px
print(f"symbols: {len(SYM)}", flush=True)


def liquid(a, j): return a["turn"][j] >= MIN_TURNOVER and a["c"][j] >= MIN_PRICE
def vok(a, j): return np.isfinite(a["vratio"][j])


# base signals
def s1(a, j):
    if regime.get(a["dates"][j]) != "BULL": return False
    c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
    return bool(c > e50 > e200 and a["e50rise"][j] and (a["l"][j] <= e20*1.02 or abs(c/e20-1) <= 0.02)
                and c > e20 and 40 <= a["rsi"][j] <= 62 and a["c"][j] > a["o"][j])


def s2(a, j):
    if regime.get(a["dates"][j]) not in ("BULL", "SIDEWAYS"): return False
    c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
    return bool(c > e50 > e200 and np.isfinite(a["bbwq"][j]) and a["bbw"][j] <= a["bbwq"][j]
                and j >= 1 and c > a["hh20"][j-1] and c <= e20*1.15)


def s6(a, j):
    if regime.get(a["dates"][j]) != "BULL": return False
    c, e50, e200 = a["c"][j], a["e50"][j], a["e200"][j]
    return bool(c > e50 > e200 and a["macdup"][j] and 45 <= a["rsi"][j] < 70)


# volume-overlay variants: (base_fn, extra_condition)
def V(base, cond):
    def fn(a, j):
        return base(a, j) and vok(a, j) and cond(a, j)
    return fn


VARIANTS = {
    "S1_base": s1,
    "S1_+dryup<=0.9": V(s1, lambda a, j: a["vratio"][j] <= 0.9),
    "S1_+surge>=1.3": V(s1, lambda a, j: a["vratio"][j] >= 1.3),
    "S2_base": s2,
    "S2_+expansion>=1.5": V(s2, lambda a, j: a["vratio"][j] >= 1.5),
    "S2_+expansion>=2.0": V(s2, lambda a, j: a["vratio"][j] >= 2.0),
    "S6_base": s6,
    "S6_+obv_rising": V(s6, lambda a, j: bool(a["obv_rise"][j])),
    "S6_+expansion>=1.3": V(s6, lambda a, j: a["vratio"][j] >= 1.3),
}


def build(fn, hold=20):
    rows = []
    for s, a in SYM.items():
        c = a["c"]; n = len(c)
        for j in range(260, n-1):
            if not liquid(a, j) or not fn(a, j): continue
            e = float(a["o"][j+1]); cT = float(c[j]); atr = float(a["atr"][j])
            if not (e > 0 and atr > 0): continue
            if (e/cT-1)*100 > GAP_MAX: continue
            m = min(hold, n-(j+1))
            if m < 1: continue
            rows.append(dict(date=a["dates"][j], e=e, atr=atr, m=m,
                             rank=float(a["ret60"][j]) if np.isfinite(a["ret60"][j]) else -9,
                             op=a["o"][j+1:j+2+m].astype(float), cl=a["c"][j+1:j+1+m].astype(float)))
    df = pd.DataFrame(rows)
    if df.empty: return df
    return df.sort_values(["date", "rank"], ascending=[True, False]).groupby("date").head(TOP_N).reset_index(drop=True)


def exit_v4(t):
    e = t["e"]; sl = e - 2.5*t["atr"]
    for k in range(t["m"]):
        if t["cl"][k] <= sl:
            ex = t["op"][k+1] if k+1 < len(t["op"]) else t["cl"][k]
            return (ex/e - 1)*100 - COST
    return (t["cl"][t["m"]-1]/e - 1)*100 - COST


def metrics(df, period):
    if not len(df): return None
    lo, hi = period; d = df[(df["date"] >= lo) & (df["date"] <= hi)]
    if not len(d): return None
    nets = np.array([exit_v4(r) for _, r in d.iterrows()])
    if len(nets) < 50: return None
    w = nets > 0
    return dict(n=int(len(nets)), acc=round(float(w.mean()*100), 2), exp=round(float(nets.mean()), 4),
                pf=round(float(nets[w].sum()/max(1e-9, -nets[~w].sum())), 3))


print("\nrunning volume overlays...", flush=True)
res = {"meta": {"cost": COST, "top_n": TOP_N, "periods": {"train": TRAIN, "val": VAL, "test": TEST},
                "note": "daily stock lake HAS volume; index intraday does NOT",
                "scope": "MEASURED, survivorship-biased daily universe"}, "variants": {}}
for name, fn in VARIANTS.items():
    df = build(fn)
    res["variants"][name] = {"n_all": int(len(df)),
                             "train": metrics(df, TRAIN), "val": metrics(df, VAL), "test": metrics(df, TEST)}
    print(f"  {name}: n={len(df)}", flush=True)
OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

print("\n=== VOLUME OVERLAY vs BASE (expectancy %/trade) ===")
print(f"{'variant':<24}{'nAll':>7}{'TRAIN':>8}{'VAL':>8}{'TEST':>8}{'val acc':>9}")
for name, v in res["variants"].items():
    def g(p): return f"{v[p]['exp']:.3f}" if v[p] else "n/a"
    va = f"{v['val']['acc']:.1f}" if v['val'] else "n/a"
    mark = "  <= base" if name.endswith("_base") else ""
    print(f"{name:<24}{v['n_all']:>7}{g('train'):>8}{g('val'):>8}{g('test'):>8}{va:>9}{mark}")
print(f"\nwrote {OUT}")
