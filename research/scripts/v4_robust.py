"""V4 ROBUSTNESS — realistic stop fills + cost stress for the v4 finalist.

Finalist: no take-profit (SL 1.5xATR + 20d time exit) + limit-at-closeT entry.
Checks: (1) gap-through-stop realism: if a day OPENS below the stop, fill at
that open, not the stop price (applied to control too, for fairness);
(2) extra 0.20% slippage stress; (3) hold-length stats.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D = str(ROOT.joinpath("research", "data"))
COST = 0.30; TOP_N = 5; HMAX = 21; SLX = 1.5; TPX = 2.0; HOLD = 20

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
f = sig.sort_values(["date","momentum","quality","score"],
                    ascending=[True,False,False,False]).groupby("date").head(TOP_N)

trades = []
for s, dt, ap in zip(f["symbol"].astype(str), f["date"], f["atr_pct"]):
    a = P.get(s)
    j = a["idx"].get(dt) if a else None
    if j is None or j + 1 >= len(a["c"]) or not (ap > 0) or a["o"][j+1] <= 0:
        continue
    e = float(a["o"][j+1]); cT = float(a["c"][j])
    sl_ = slice(j+1, j+1+HMAX)
    m = min(HOLD, len(a["c"][sl_]))
    if m < 1: continue
    trades.append(dict(date=dt, e=e, cT=cT, atr=e*ap/100,
                       o=a["o"][sl_].astype(float), lo=a["l"][sl_].astype(float),
                       hi=a["h"][sl_].astype(float), cl=a["c"][sl_].astype(float), m=m))
print(f"trades: {len(trades)}", flush=True)

def fill_stop(t, k, stopv, realistic):
    if realistic and t["o"][k] < stopv:
        return t["o"][k]          # gapped through the stop: filled at open
    return stopv

def x_control(t, e, realistic):
    sl = e - SLX*t["atr"]; tp = e + TPX*t["atr"]
    for k in range(t["m"]):
        if k > 0 and t["o"][k] >= tp and realistic:  # gap up through TP: better fill
            return t["o"][k], k+1
        if t["lo"][k] <= sl: return fill_stop(t, k, sl, realistic), k+1
        if t["hi"][k] >= tp: return tp, k+1
    return t["cl"][t["m"]-1], t["m"]

def x_notp(t, e, realistic, slx=SLX):
    sl = e - slx*t["atr"]
    for k in range(t["m"]):
        if t["lo"][k] <= sl: return fill_stop(t, k, sl, realistic), k+1
    return t["cl"][t["m"]-1], t["m"]

def x_notp_sl(slx):
    return lambda t, e, realistic: x_notp(t, e, realistic, slx)

def x_notp_close(slx):
    # stop evaluated on CLOSE only; exit at next day's open (always realistic)
    def fn(t, e, realistic):
        sl = e - slx*t["atr"]
        for k in range(t["m"]):
            if t["cl"][k] <= sl:
                if k + 1 < len(t["o"]): return t["o"][k+1], k+2
                return t["cl"][k], k+1
        return t["cl"][t["m"]-1], t["m"]
    return fn

def entry_all(t): return t["e"]
def entry_limit(t):
    if t["e"] <= t["cT"]: return t["e"]
    return t["cT"] if t["lo"][0] <= t["cT"] else None

def run(plo, phi, xfn, efn, realistic, cost):
    nets = []; holds = []
    for t in trades:
        if not (plo <= t["date"] <= phi): continue
        e = efn(t)
        if e is None: continue
        ex, hd = xfn(t, e, realistic)
        nets.append((ex/e - 1)*100 - cost); holds.append(hd)
    nets = np.array(nets); w = nets > 0
    return dict(n=len(nets), win=w.mean()*100, exp=nets.mean(),
                pf=nets[w].sum()/max(1e-9, -nets[~w].sum()),
                hold=float(np.median(holds)))

PER = [("TRAIN","2011-01-01","2019-12-31"), ("VAL","2020-01-01","2022-12-31"),
       ("TEST","2023-01-01","2099-01-01")]
print(f"\n{'period':<7}{'variant':<34}{'n':>6}{'win%':>7}{'exp':>8}{'PF':>6}{'medHold':>8}")
for pn, lo_, hi_ in PER:
    for label, xfn, efn, realistic, cost in [
        ("control, idealized fills", x_control, entry_all, False, COST),
        ("control, realistic fills", x_control, entry_all, True, COST),
        ("noTP SL1.5 (no limit), realistic", x_notp_sl(1.5), entry_all, True, COST),
        ("v4 finalist (noTP+limit), idealized", x_notp_sl(1.5), entry_limit, False, COST),
        ("v4 finalist (noTP+limit), realistic", x_notp_sl(1.5), entry_limit, True, COST),
        ("v4 finalist, realistic +0.2% slip", x_notp_sl(1.5), entry_limit, True, COST+0.20),
        ("noTP SL2.0 intraday, realistic", x_notp_sl(2.0), entry_all, True, COST),
        ("noTP SL2.5 intraday, realistic", x_notp_sl(2.5), entry_all, True, COST),
        ("noTP SL2.5 close-eval, realistic", x_notp_close(2.5), entry_all, True, COST),
        ("noTP SL3.0 close-eval, realistic", x_notp_close(3.0), entry_all, True, COST),
    ]:
        r = run(lo_, hi_, xfn, efn, realistic, cost)
        print(f"{pn:<7}{label:<34}{r['n']:>6}{r['win']:>7.1f}{r['exp']:>8.3f}{r['pf']:>6.2f}{r['hold']:>8.0f}")
print("\nDONE", flush=True)
