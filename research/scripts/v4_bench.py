"""V4 BENCHMARK — separate exit skill from pool drift (and survivorship bias).

Baselines: (a) v3-selected top-5/day held 20d with NO stop at all;
(b) RANDOM 5/day from the score>=55 pool, held 20d, no stop (seeded).
Per-year table for the no-stop hold and the SL2.5/3.0 close-eval variants.
If the pool itself drifts up strongly, part of every long-hold result is
drift/survivorship, not exit skill.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D = str(ROOT.joinpath("research", "data"))
COST = 0.30; TOP_N = 5; HMAX = 21; HOLD = 20

print("loading...", flush=True)
px = pd.read_csv(D + r"\nse_universe_2010_ohlcv.csv.gz",
                 usecols=["date","symbol","open","high","low","close","volume"],
                 dtype={"symbol":"category","open":"float32","high":"float32",
                        "low":"float32","close":"float32","volume":"float64"})
nif = pd.read_csv(D + r"\nifty50_daily_2010.csv").sort_values("date")
nifc = nif.set_index("date")["nifty_close"]
nif_r63 = (nifc / nifc.shift(63) - 1).to_dict()
P = {}
for sym, g in px.groupby("symbol", sort=False, observed=True):
    c = g["close"].to_numpy(float); n = len(c)
    r63 = np.full(n, np.nan); r63[63:] = c[63:] / c[:-63] - 1
    hi250 = pd.Series(c).rolling(250, min_periods=60).max().to_numpy()
    P[str(sym)] = dict(o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
                       l=g["low"].to_numpy(float), c=c,
                       idx={dd: i for i, dd in enumerate(g["date"].to_numpy())},
                       r63=r63, dhi=c / hi250 - 1)
del px
sig = pd.read_csv(D + r"\signals_2010.csv.gz")
sig = sig[sig["score"] >= 55].copy()
sig["atr_pct"] = sig["atr"] / sig["close"] * 100
sig["quality"] = (~sig["counter_trend"]) & (sig["trend"] == "Up") & (sig["adx"] >= 25)
syms_arr = sig["symbol"].astype(str).to_numpy(); dates_arr = sig["date"].to_numpy()
def feat(key):
    out = np.full(len(sig), np.nan)
    for i, (s, dt) in enumerate(zip(syms_arr, dates_arr)):
        a = P.get(s)
        if a is None: continue
        j = a["idx"].get(dt)
        if j is not None: out[i] = a[key][j]
    return out
sig["r63"] = feat("r63"); sig["dhi"] = feat("dhi")
sig["nifr63"] = sig["date"].map(nif_r63)
sig["momentum"] = ((sig["dhi"] >= -0.15) & (sig["r63"] > sig["nifr63"])
                   & (sig["r63"] > 0)).fillna(False)

def windows(fr):
    out = []
    for s, dt, ap in zip(fr["symbol"].astype(str), fr["date"], fr["atr_pct"]):
        a = P.get(s)
        j = a["idx"].get(dt) if a else None
        if j is None or j + 1 >= len(a["c"]) or not (ap > 0) or a["o"][j+1] <= 0:
            continue
        sl_ = slice(j+1, j+1+HMAX)
        m = min(HOLD, len(a["c"][sl_]))
        if m < 1: continue
        out.append(dict(date=dt, e=float(a["o"][j+1]), atr=float(a["o"][j+1])*ap/100,
                        o=a["o"][sl_].astype(float), lo=a["l"][sl_].astype(float),
                        cl=a["c"][sl_].astype(float), m=m))
    return out

v3sel = windows(sig.sort_values(["date","momentum","quality","score"],
                ascending=[True,False,False,False]).groupby("date").head(TOP_N))
rng = np.random.default_rng(42)
rnd = windows(sig.sample(frac=1.0, random_state=42).groupby("date").head(TOP_N))
print(f"v3-selected: {len(v3sel)}  random: {len(rnd)}", flush=True)

def x_hold(t):
    return t["cl"][t["m"]-1]
def x_close_sl(slx):
    def fn(t):
        sl = t["e"] - slx*t["atr"]
        for k in range(t["m"]):
            if t["cl"][k] <= sl:
                if k + 1 < len(t["o"]): return t["o"][k+1]
                return t["cl"][k]
        return t["cl"][t["m"]-1]
    return fn

def stat(trs, xfn, lo_, hi_):
    nets = [ (xfn(t)/t["e"]-1)*100 - COST for t in trs if lo_ <= t["date"] <= hi_ ]
    if len(nets) < 50: return None
    nets = np.array(nets); w = nets > 0
    return dict(n=len(nets), win=w.mean()*100, exp=nets.mean(),
                pf=nets[w].sum()/max(1e-9, -nets[~w].sum()))

PER = [("TRAIN","2011-01-01","2019-12-31"), ("VAL","2020-01-01","2022-12-31"),
       ("TEST","2023-01-01","2099-01-01")]
print(f"\n{'period':<7}{'variant':<36}{'n':>6}{'win%':>7}{'exp':>8}{'PF':>6}")
for pn, lo_, hi_ in PER:
    for label, trs, fn in [
        ("v3 picks, hold20 NO STOP", v3sel, x_hold),
        ("v3 picks, noTP SL2.5 close-eval", v3sel, x_close_sl(2.5)),
        ("v3 picks, noTP SL3.0 close-eval", v3sel, x_close_sl(3.0)),
        ("RANDOM 5/day, hold20 NO STOP", rnd, x_hold),
        ("RANDOM 5/day, noTP SL2.5 close-eval", rnd, x_close_sl(2.5)),
    ]:
        r = stat(trs, fn, lo_, hi_)
        if r: print(f"{pn:<7}{label:<36}{r['n']:>6}{r['win']:>7.1f}{r['exp']:>8.3f}{r['pf']:>6.2f}")

print("\n--- per test year ---")
for y in ["2023","2024","2025","2026"]:
    row = [y]
    for label, trs, fn in [("hold-nostop", v3sel, x_hold),
                           ("SL2.5ce", v3sel, x_close_sl(2.5)),
                           ("random-hold", rnd, x_hold)]:
        r = stat(trs, fn, f"{y}-01-01", f"{y}-12-31")
        row.append(f"{label} {r['exp']:+.3f} ({r['win']:.0f}%)" if r else f"{label} n/a")
    print("   " + " | ".join(row))
print("\nDONE", flush=True)
