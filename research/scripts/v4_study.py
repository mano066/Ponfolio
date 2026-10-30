"""V4 STUDY — exit-engine and entry-rule candidates on top of Swing v3 selection.

Motivated by per-trade forensics (v4_diag): fixed 2xATR take-profit caps winners
(~50% of losers had MFE >= 1xATR); big gap-up entries lose everywhere.

Protocol (same bar as v2/v3 studies): selection = production v3 (momentum tier,
quality, score; top-5/day). Candidates evaluated on TRAIN 2011-19, finalist
chosen on VALIDATION 2020-22 (must also beat control on train), ONE look at
TEST 2023-26. DISCLOSURE: v4_diag previewed chandelier k=2.5 on test before
this study; the finalist choice below still uses only train+validation.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D = str(ROOT.joinpath("research", "data"))
COST = 0.30; TOP_N = 5; HMAX = 21; SLX = 1.5; TPX = 2.0; HOLD = 20

print("loading prices...", flush=True)
px = pd.read_csv(D + r"\nse_universe_2010_ohlcv.csv.gz",
                 usecols=["date","symbol","open","high","low","close","volume"],
                 dtype={"symbol":"category","open":"float32","high":"float32",
                        "low":"float32","close":"float32","volume":"float64"})
nif = pd.read_csv(D + r"\nifty50_daily_2010.csv").sort_values("date")
nifc = nif.set_index("date")["nifty_close"]
nif_r63 = (nifc / nifc.shift(63) - 1).to_dict()

print("building per-symbol arrays...", flush=True)
P = {}
for sym, g in px.groupby("symbol", sort=False, observed=True):
    c = g["close"].to_numpy(float)
    n = len(c)
    r63 = np.full(n, np.nan); r63[63:] = c[63:] / c[:-63] - 1
    hi250 = pd.Series(c).rolling(250, min_periods=60).max().to_numpy()
    P[str(sym)] = dict(o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
                       l=g["low"].to_numpy(float), c=c,
                       idx={dd: i for i, dd in enumerate(g["date"].to_numpy())},
                       r63=r63, dhi=c / hi250 - 1)
del px

print("loading signals + selecting production-v3 trades...", flush=True)
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

# materialize each trade's forward window once
trades = []  # (date, e, gap, atr_abs, o,h,l,c arrays for window, m)
for s, dt, ap in zip(f["symbol"].astype(str), f["date"], f["atr_pct"]):
    a = P.get(s)
    j = a["idx"].get(dt) if a else None
    if j is None or j + 1 >= len(a["c"]) or not (ap > 0) or a["o"][j+1] <= 0:
        continue
    e = float(a["o"][j+1]); cT = float(a["c"][j])
    lo = a["l"][j+1:j+1+HMAX].astype(float); hi = a["h"][j+1:j+1+HMAX].astype(float)
    cl = a["c"][j+1:j+1+HMAX].astype(float)
    m = min(HOLD, len(cl))
    if m < 1: continue
    trades.append(dict(date=dt, e=e, gap=(e/cT-1)*100 if cT > 0 else np.nan,
                       cT=cT, atr=e*ap/100, lo=lo, hi=hi, cl=cl, m=m))
print(f"trades: {len(trades)}", flush=True)

# ---------------- exit engines ----------------
def x_control(t, e=None):
    e = e or t["e"]; sl = e - SLX*t["atr"]; tp = e + TPX*t["atr"]
    for k in range(t["m"]):
        if t["lo"][k] <= sl: return sl
        if t["hi"][k] >= tp: return tp
    return t["cl"][t["m"]-1]

def x_chand(kx):
    def fn(t, e=None):
        e = e or t["e"]; stop0 = e - SLX*t["atr"]; hh = e
        for k in range(t["m"]):
            stopv = max(stop0, hh - kx*t["atr"])
            if t["lo"][k] <= stopv: return stopv
            hh = max(hh, t["hi"][k])
        return t["cl"][t["m"]-1]
    return fn

def x_breakeven(t, e=None):
    e = e or t["e"]; sl = e - SLX*t["atr"]; tp = e + TPX*t["atr"]; be = e + t["atr"]
    for k in range(t["m"]):
        if t["lo"][k] <= sl: return sl
        if t["hi"][k] >= tp: return tp
        if t["hi"][k] >= be: sl = max(sl, e)  # raise from next bar
    return t["cl"][t["m"]-1]

def x_chand_be(kx):
    def fn(t, e=None):
        e = e or t["e"]; stop0 = e - SLX*t["atr"]; hh = e; be_armed = False
        for k in range(t["m"]):
            stopv = max(stop0, hh - kx*t["atr"], e if be_armed else -1e18)
            if t["lo"][k] <= stopv: return stopv
            hh = max(hh, t["hi"][k])
            if t["hi"][k] >= e + t["atr"]: be_armed = True
        return t["cl"][t["m"]-1]
    return fn

def x_tp3(t, e=None):
    e = e or t["e"]; sl = e - SLX*t["atr"]; tp = e + 3.0*t["atr"]
    for k in range(t["m"]):
        if t["lo"][k] <= sl: return sl
        if t["hi"][k] >= tp: return tp
    return t["cl"][t["m"]-1]

def x_notp(t, e=None):
    e = e or t["e"]; sl = e - SLX*t["atr"]
    for k in range(t["m"]):
        if t["lo"][k] <= sl: return sl
    return t["cl"][t["m"]-1]

def x_lag10(t, e=None):
    e = e or t["e"]; sl = e - SLX*t["atr"]; tp = e + TPX*t["atr"]
    for k in range(t["m"]):
        if t["lo"][k] <= sl: return sl
        if t["hi"][k] >= tp: return tp
        if k == 9 and t["cl"][k] < e: return t["cl"][k]
    return t["cl"][t["m"]-1]

def x_chand_lag10(kx):
    def fn(t, e=None):
        e = e or t["e"]; stop0 = e - SLX*t["atr"]; hh = e
        for k in range(t["m"]):
            stopv = max(stop0, hh - kx*t["atr"])
            if t["lo"][k] <= stopv: return stopv
            if k == 9 and t["cl"][k] < e: return t["cl"][k]
            hh = max(hh, t["hi"][k])
        return t["cl"][t["m"]-1]
    return fn

# ---------------- entry rules (with control exit unless noted) ----------------
def entry_all(t):    return t["e"]                      # market on open
def entry_gap4(t):   return t["e"] if t["gap"] <= 4.0 else None
def entry_gap1(t):   return t["e"] if t["gap"] <= 1.0 else None
def entry_limit(t):  # limit at day-T close: fills if next-day low touches it
    if t["e"] <= t["cT"]: return t["e"]                 # opens at/below limit
    return t["cT"] if t["lo"][0] <= t["cT"] else None

EXITS = [("control SL1.5/TP2/h20", x_control), ("chand k=2.0", x_chand(2.0)),
         ("chand k=2.5", x_chand(2.5)), ("chand k=3.0", x_chand(3.0)),
         ("chand k=3.5", x_chand(3.5)), ("breakeven@1ATR", x_breakeven),
         ("chand2.5+BE", x_chand_be(2.5)), ("TP 3xATR", x_tp3),
         ("no TP (SL only)", x_notp), ("lag-stop d10", x_lag10),
         ("chand2.5+lag d10", x_chand_lag10(2.5))]
ENTRIES = [("skip gap>4%", entry_gap4), ("skip gap>1%", entry_gap1),
           ("limit@closeT", entry_limit)]

def run(period_lo, period_hi, exit_fn, entry_fn=entry_all):
    nets = []
    for t in trades:
        if not (period_lo <= t["date"] <= period_hi): continue
        e = entry_fn(t)
        if e is None: continue
        ex = exit_fn(t, e)
        nets.append((ex/e - 1)*100 - COST)
    if len(nets) < 100: return None
    nets = np.array(nets); w = nets > 0
    return dict(n=len(nets), win=w.mean()*100, exp=nets.mean(),
                pf=nets[w].sum()/max(1e-9, -nets[~w].sum()))

def show(title, rows):
    print(f"\n--- {title} ---")
    print(f"{'candidate':<26}{'trades':>7}{'win%':>7}{'exp%/tr':>9}{'PF':>6}")
    for name, r in rows:
        if r: print(f"{name:<26}{r['n']:>7}{r['win']:>7.1f}{r['exp']:>9.3f}{r['pf']:>6.2f}")

PERIODS = {"TRAIN": ("2011-01-01","2019-12-31"), "VAL": ("2020-01-01","2022-12-31")}
results = {}
for pname, (plo, phi) in PERIODS.items():
    rows = []
    for name, fn in EXITS:
        rows.append((name, run(plo, phi, fn)))
    for name, efn in ENTRIES:
        rows.append((f"entry: {name}", run(plo, phi, x_control, efn)))
    results[pname] = rows
    show(pname, rows)

# finalist: best VAL expectancy that also beats control on TRAIN
tr = {n: r for n, r in results["TRAIN"] if r}
va = {n: r for n, r in results["VAL"] if r}
ctrl_tr = tr["control SL1.5/TP2/h20"]["exp"]; ctrl_va = va["control SL1.5/TP2/h20"]["exp"]
elig = [(n, va[n]["exp"]) for n in va
        if n != "control SL1.5/TP2/h20" and tr.get(n) and tr[n]["exp"] > ctrl_tr
        and va[n]["exp"] > ctrl_va]
elig.sort(key=lambda x: -x[1])
print(f"\ncontrol: train exp {ctrl_tr:+.3f}, val exp {ctrl_va:+.3f}")
print("eligible (beat control on BOTH train and val), by val exp:")
for n, e in elig: print(f"   {n:<26} val exp {e:+.3f}")

# combo: best exit x best entry (if both eligible), checked on train+val
best_exit = next((n for n, _ in elig if not n.startswith("entry:")), None)
best_entry = next((n for n, _ in elig if n.startswith("entry:")), None)
combo_name = None
if best_exit and best_entry:
    xfn = dict(EXITS)[best_exit]
    efn = dict(ENTRIES)[best_entry.replace("entry: ", "")]
    ctr = run(*PERIODS["TRAIN"], xfn, efn); cva = run(*PERIODS["VAL"], xfn, efn)
    show("TRAIN combo", [(f"{best_exit} + {best_entry}", ctr)])
    show("VAL combo", [(f"{best_exit} + {best_entry}", cva)])
    if (ctr and cva and ctr["exp"] > ctrl_tr and cva["exp"] > max(e for _, e in elig)):
        combo_name = (best_exit, best_entry, xfn, efn)

if combo_name:
    finalist = ("COMBO", f"{combo_name[0]} + {combo_name[1]}", combo_name[2], combo_name[3])
elif elig:
    n = elig[0][0]
    if n.startswith("entry: "):
        finalist = ("ENTRY", n, x_control, dict(ENTRIES)[n.replace("entry: ", "")])
    else:
        finalist = ("EXIT", n, dict(EXITS)[n], entry_all)
else:
    finalist = None
print(f"\nfinalist: {finalist[1] if finalist else None}")

print("\n" + "="*70)
print("FINAL TEST 2023-now (one look)")
print("="*70)
TLO, THI = "2023-01-01", "2099-01-01"
te_rows = [("control SL1.5/TP2/h20", run(TLO, THI, x_control))]
if finalist:
    te_rows.append((finalist[1], run(TLO, THI, finalist[2], finalist[3])))
show("TEST", te_rows)

# transparency: all candidates on test, context only (finalist already fixed)
ctx = []
for name, fn in EXITS[1:]:
    ctx.append((f"[ctx] {name}", run(TLO, THI, fn)))
for name, efn in ENTRIES:
    ctx.append((f"[ctx] entry: {name}", run(TLO, THI, x_control, efn)))
show("TEST (all candidates, context)", ctx)

# yearly breakdown of finalist vs control on test
if finalist:
    print("\n--- finalist vs control by test year ---")
    for y in ["2023","2024","2025","2026"]:
        rc = run(f"{y}-01-01", f"{y}-12-31", x_control)
        rf = run(f"{y}-01-01", f"{y}-12-31", finalist[2], finalist[3])
        if rc and rf:
            print(f"   {y}: control {rc['exp']:+.3f} ({rc['win']:.1f}%) | "
                  f"finalist {rf['exp']:+.3f} ({rf['win']:.1f}%)")
print("\nDONE", flush=True)
