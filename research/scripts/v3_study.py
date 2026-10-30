"""V3 CANDIDATE STUDY — evidence-backed filters layered on top of Swing v2.

Candidates (from literature + our own study-1 findings), all computed from
day-T data only:
  RS      : stock 63d return > Nifty 63d return (cross-sectional momentum)
  RS+ABS  : RS and stock 63d return > 0 (enhanced momentum, India evidence)
  VOLQ    : volume today <= 4x 20d average (avoid climax volume)
  NEARHI  : close within 15% of 250d high (52-week-high momentum)
  LOWVOL  : ATR% below the day's median among candidates (volatility scaling)
Protocol: base = v2 (quality-first top-5, SL 1.5xATR, TP 2xATR, hold 20,
T+1 open, 0.30% costs). Single filters compared on TRAIN 2011-19; best on
VAL 2020-22 chooses the finalist(s); ONE look at TEST 2023-now.
"""
import warnings, time
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

print("building per-symbol features...", flush=True)
P = {}
for sym, g in px.groupby("symbol", sort=False, observed=True):
    c = g["close"].to_numpy(float); v = g["volume"].to_numpy(float)
    d = g["date"].to_numpy()
    n = len(c)
    r63 = np.full(n, np.nan); r63[63:] = c[63:] / c[:-63] - 1
    v20 = pd.Series(v).shift(1).rolling(20, min_periods=10).mean().to_numpy()
    vr = np.divide(v, v20, out=np.full(n, np.nan), where=(v20 > 0))
    hi250 = pd.Series(c).rolling(250, min_periods=60).max().to_numpy()
    dhi = c / hi250 - 1
    P[str(sym)] = dict(o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
                       l=g["low"].to_numpy(float), c=c,
                       idx={dd: i for i, dd in enumerate(d)},
                       r63=r63, vr=vr, dhi=dhi)
del px

print("loading signals...", flush=True)
sig = pd.read_csv(D + r"\signals_2010.csv.gz")
sig = sig[sig["score"] >= 55].copy()
sig["atr_pct"] = sig["atr"] / sig["close"] * 100
sig["quality"] = (~sig["counter_trend"]) & (sig["trend"] == "Up") & (sig["adx"] >= 25)

# attach features by (symbol,date)
def feat(row_syms, row_dates, key):
    out = np.full(len(row_syms), np.nan)
    for i, (s, dt) in enumerate(zip(row_syms, row_dates)):
        a = P.get(s)
        if a is None: continue
        j = a["idx"].get(dt)
        if j is not None: out[i] = a[key][j]
    return out
t0 = time.time()
syms_arr = sig["symbol"].astype(str).to_numpy(); dates_arr = sig["date"].to_numpy()
sig["r63"] = feat(syms_arr, dates_arr, "r63")
sig["vr"] = feat(syms_arr, dates_arr, "vr")
sig["dhi"] = feat(syms_arr, dates_arr, "dhi")
sig["nifr63"] = sig["date"].map(nif_r63)
print(f"features attached in {(time.time()-t0)/60:.1f} min", flush=True)

sig["RS"] = sig["r63"] > sig["nifr63"]
sig["RSABS"] = sig["RS"] & (sig["r63"] > 0)
sig["VOLQ"] = sig["vr"] <= 4.0
sig["NEARHI"] = sig["dhi"] >= -0.15
med_atr = sig.groupby("date")["atr_pct"].transform("median")
sig["LOWVOL"] = sig["atr_pct"] <= med_atr

_cache = {}
def outcome(sym, date, atrp):
    key = (sym, date)
    if key in _cache: return _cache[key]
    a = P.get(sym); j = a["idx"].get(date) if a else None
    r = None
    if j is not None and j + 1 < len(a["c"]) and atrp > 0 and a["o"][j+1] > 0:
        e = a["o"][j+1]
        lo = a["l"][j+1:j+1+HMAX]; hi = a["h"][j+1:j+1+HMAX]; cl = a["c"][j+1:j+1+HMAX]
        sl = e * (1 - SLX*atrp/100); tp = e * (1 + TPX*atrp/100)
        m = min(HOLD, len(cl)); ex = None
        for k in range(m):
            if lo[k] <= sl: ex = sl; break
            if hi[k] >= tp: ex = tp; break
        if ex is None: ex = cl[m-1]
        r = (ex/e - 1)*100 - COST
    _cache[key] = r
    return r

def run(d, extra_mask=None, label=""):
    f = d if extra_mask is None else d[extra_mask]
    f = f.sort_values(["date","quality","score"], ascending=[True,False,False]).groupby("date").head(TOP_N)
    nets = []
    for s, dt, ap in zip(f["symbol"].astype(str), f["date"], f["atr_pct"]):
        r = outcome(s, dt, ap)
        if r is not None: nets.append(r)
    if len(nets) < 100: return None
    nets = np.array(nets)
    w = nets > 0
    return dict(label=label, n=len(nets), win=w.mean()*100, exp=nets.mean(),
                pf=nets[w].sum()/max(1e-9, -nets[~w].sum()))

def show(rows, title):
    print(f"\n--- {title} ---")
    print(f"{'candidate':<24}{'trades':>7}{'win%':>7}{'exp%/tr':>9}{'PF':>6}")
    for r in rows:
        if r: print(f"{r['label']:<24}{r['n']:>7}{r['win']:>7.1f}{r['exp']:>9.3f}{r['pf']:>6.2f}")

TR = sig[(sig["date"] >= "2011-01-01") & (sig["date"] <= "2019-12-31")]
VA = sig[(sig["date"] >= "2020-01-01") & (sig["date"] <= "2022-12-31")]
TE = sig[sig["date"] >= "2023-01-01"]

CANDS = [("v2 base (control)", None), ("v2 + RS", "RS"), ("v2 + RSABS", "RSABS"),
         ("v2 + VOLQ", "VOLQ"), ("v2 + NEARHI", "NEARHI"), ("v2 + LOWVOL", "LOWVOL")]

tr_rows = []
for name, col in CANDS:
    m = None if col is None else TR[col].fillna(False)
    tr_rows.append(run(TR, m, name))
show(tr_rows, "TRAIN 2011-2019")

va_rows = []
for name, col in CANDS:
    m = None if col is None else VA[col].fillna(False)
    va_rows.append(run(VA, m, name))
show(va_rows, "VALIDATION 2020-2022")

# combos of the two best single filters on validation (excluding control)
va_valid = [r for r in va_rows[1:] if r]
va_valid.sort(key=lambda r: r["exp"], reverse=True)
best2 = [r["label"].replace("v2 + ", "") for r in va_valid[:2]]
print(f"\nbest singles on validation: {best2}")
combo_col = None
if len(best2) == 2:
    VA2 = VA.copy(); TR2 = TR.copy()
    VA2["COMBO"] = VA2[best2[0]].fillna(False) & VA2[best2[1]].fillna(False)
    TR2["COMBO"] = TR2[best2[0]].fillna(False) & TR2[best2[1]].fillna(False)
    show([run(TR2, TR2["COMBO"], f"v2 + {best2[0]}+{best2[1]}")], "TRAIN combo")
    cr = run(VA2, VA2["COMBO"], f"v2 + {best2[0]}+{best2[1]}")
    show([cr], "VALIDATION combo")
    if cr and cr["exp"] > va_valid[0]["exp"] and cr["n"] >= 800:
        combo_col = best2

# finalist: best on validation (single or combo), must beat control on BOTH train and val
control_va = va_rows[0]
finalist = None
if combo_col:
    finalist = ("COMBO", combo_col)
elif va_valid and va_valid[0]["exp"] > control_va["exp"]:
    finalist = ("SINGLE", va_valid[0]["label"].replace("v2 + ", ""))
print(f"\nfinalist: {finalist}")

print("\n" + "="*70)
print("FINAL TEST 2023-now (untouched, one look)")
print("="*70)
te_rows = [run(TE, None, "v2 base (control)")]
if finalist:
    if finalist[0] == "COMBO":
        TE2 = TE.copy()
        TE2["COMBO"] = TE2[finalist[1][0]].fillna(False) & TE2[finalist[1][1]].fillna(False)
        te_rows.append(run(TE2, TE2["COMBO"], f"v2 + {finalist[1][0]}+{finalist[1][1]}"))
    else:
        te_rows.append(run(TE, TE[finalist[1]].fillna(False), f"v2 + {finalist[1]}"))
show(te_rows, "TEST")
# transparency: all singles on test (context only, finalist decision already made)
show([run(TE, TE[c].fillna(False), f"[context] v2 + {c}") for _, c in CANDS[1:]],
     "TEST (all singles, for context)")
print("\nDONE", flush=True)
