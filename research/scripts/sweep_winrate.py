"""Pass B: parameter sweep for high win-rate configs, walk-forward honest.

Split:  TRAIN <= 2022-12-31 | VALIDATION 2023-2024 | TEST 2025+ (untouched
until one config is chosen on validation).
For each config: filter signals -> top-5/day by score -> enter T+1 open ->
exit on SL/TP (ATR-multiples) or time. Costs 0.30% round trip.
Objective: configs reaching >=78% win on TRAIN with max expectancy, plus the
global max-expectancy config for comparison. Winner picked on VALIDATION.
"""
import sys, time, warnings, itertools
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DATA = str(ROOT.joinpath("research", "data", "nse_universe_10y_ohlcv.csv.gz"))
SIG = str(ROOT.joinpath("research", "data", "signals_10y.csv.gz"))
COST = 0.30
TOP_N = 5
HMAX = 21  # longest horizon we ever need

print("loading prices...", flush=True)
px = pd.read_csv(DATA).sort_values(["symbol", "date"])
P = {}
for sym, g in px.groupby("symbol", sort=False):
    P[sym] = dict(d=list(g["date"]), o=g["open"].to_numpy(float),
                  h=g["high"].to_numpy(float), l=g["low"].to_numpy(float),
                  c=g["close"].to_numpy(float),
                  idx={dd: i for i, dd in enumerate(g["date"])})
print("loading signals...", flush=True)
sig = pd.read_csv(SIG)
print(f"{len(sig):,} signals", flush=True)

sig["atr_pct"] = sig["atr"] / sig["close"] * 100
TR = sig["date"] <= "2022-12-31"
VA = (sig["date"] > "2022-12-31") & (sig["date"] <= "2024-12-31")
TE = sig["date"] > "2024-12-31"

_path_cache = {}
def fwd(sym, date):
    key = (sym, date)
    if key in _path_cache:
        return _path_cache[key]
    a = P.get(sym)
    j = a["idx"].get(date) if a else None
    if j is None or j + 1 >= len(a["c"]):
        _path_cache[key] = None
        return None
    e = a["o"][j+1]
    hi = a["h"][j+1:j+1+HMAX]; lo = a["l"][j+1:j+1+HMAX]; cl = a["c"][j+1:j+1+HMAX]
    r = (e, lo, hi, cl)
    _path_cache[key] = r if e > 0 else None
    return _path_cache[key]

def run(d, score_min, tfilt, adx_min, slx, tpx, hold):
    m = d["score"] >= score_min
    if tfilt == "noct":
        m &= ~d["counter_trend"]
    elif tfilt == "up":
        m &= (~d["counter_trend"]) & (d["trend"] == "Up")
    if adx_min:
        m &= d["adx"] >= adx_min
    f = d[m]
    if len(f) == 0:
        return None
    f = f.sort_values(["date", "score"], ascending=[True, False]).groupby("date").head(TOP_N)
    nets = []
    for sym, date, atrp in zip(f["symbol"], f["date"], f["atr_pct"]):
        p = fwd(sym, date)
        if p is None or atrp <= 0:
            continue
        e, lo, hi, cl = p
        # ATR% is relative to signal close; SL/TP set off entry price
        sl = e * (1 - slx * atrp / 100)
        tp = e * (1 + tpx * atrp / 100)
        n = min(hold, len(cl))
        exitp = None
        for m2 in range(n):
            if lo[m2] <= sl:
                exitp = sl; break
            if hi[m2] >= tp:
                exitp = tp; break
        if exitp is None:
            exitp = cl[n-1]
        nets.append((exitp/e - 1) * 100 - COST)
    if len(nets) < 50:
        return None
    nets = np.array(nets)
    win = (nets > 0).mean() * 100
    risk = slx  # in ATR units; R multiple = net% / (slx*atr%) varies per trade; report % terms
    return dict(n=len(nets), win=win, exp=nets.mean(),
                pf=(nets[nets > 0].sum() / max(1e-9, -nets[nets <= 0].sum())))

grid = list(itertools.product(
    [55, 60, 65, 70, 75],            # score_min
    ["none", "noct", "up"],          # trend filter
    [0, 20, 25],                     # adx_min
    [1.5, 2.0, 2.5, 3.0],            # SL x ATR
    [0.5, 0.75, 1.0, 1.5, 2.0],      # TP x ATR
    [5, 10, 20],                     # max hold
))
print(f"grid: {len(grid)} configs", flush=True)

dtr = sig[TR]
res = []
t0 = time.time()
for i, (sm, tf, ax, slx, tpx, hd) in enumerate(grid):
    if i % 200 == 0:
        print(f"{i}/{len(grid)} ({(time.time()-t0)/60:.1f} min)", flush=True)
    r = run(dtr, sm, tf, ax, slx, tpx, hd)
    if r:
        res.append(dict(score_min=sm, tfilt=tf, adx=ax, slx=slx, tpx=tpx, hold=hd, **r))
R = pd.DataFrame(res)
R.to_csv(str(ROOT.joinpath("research", "data", "sweep_train_results.csv")), index=False)
print(f"\ntrain sweep done: {len(R)} valid configs", flush=True)

# candidates: high win-rate band and global best expectancy
hw = R[(R["win"] >= 78) & (R["n"] >= 400)].nlargest(8, "exp")
be = R[R["n"] >= 400].nlargest(4, "exp")
cand = pd.concat([hw, be]).drop_duplicates(subset=["score_min","tfilt","adx","slx","tpx","hold"])
print("\n--- TRAIN candidates ---")
print(cand.to_string(index=False))

print("\n--- VALIDATION (2023-2024) ---")
dva = sig[VA]
va_rows = []
for _, c in cand.iterrows():
    r = run(dva, c["score_min"], c["tfilt"], c["adx"], c["slx"], c["tpx"], int(c["hold"]))
    if r:
        va_rows.append(dict(score_min=c["score_min"], tfilt=c["tfilt"], adx=c["adx"],
                            slx=c["slx"], tpx=c["tpx"], hold=int(c["hold"]), **r))
V = pd.DataFrame(va_rows)
print(V.to_string(index=False))

# winner: on validation, require win>=75, then max expectancy; fallback max exp
Vw = V[V["win"] >= 75]
best = (Vw if len(Vw) else V).nlargest(1, "exp").iloc[0]
print(f"\nWINNER (chosen on validation): score>={best['score_min']}, trend={best['tfilt']}, "
      f"ADX>={best['adx']}, SL={best['slx']}xATR, TP={best['tpx']}xATR, hold={best['hold']}d")

print("\n--- FINAL TEST (2025-2026, untouched) ---")
dte = sig[TE]
t = run(dte, best["score_min"], best["tfilt"], best["adx"], best["slx"], best["tpx"], int(best["hold"]))
print(t)
# also test-run the CURRENT production config for comparison
base = run(dte, 55, "none", 0, 1.5, 2.0, 20)
print("baseline (current params) on same test period:", base)
print("DONE", flush=True)
