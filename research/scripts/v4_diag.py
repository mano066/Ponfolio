"""V4 DIAGNOSTICS — per-trade forensics of the production v3 selection, 2011-2026.

Replays production v3 (momentum-tier first, quality second, score third, top-5/day,
SL 1.5xATR, TP 2xATR, hold 20d, T+1 open entry, 0.30% costs) and records per trade:
entry gap, exit type/day, net return, MFE/MAE over the full 20d window.
Then prints the aggregates that should drive v4 design. Diagnostics only — no
strategy choices are made here.
"""
import warnings, time
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D = str(ROOT.joinpath("research", "data"))
OUT = str(ROOT.joinpath("research", "data", "v4_diag_trades.csv"))
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
    c = g["close"].to_numpy(float)
    n = len(c)
    r63 = np.full(n, np.nan); r63[63:] = c[63:] / c[:-63] - 1
    hi250 = pd.Series(c).rolling(250, min_periods=60).max().to_numpy()
    dhi = c / hi250 - 1
    P[str(sym)] = dict(o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
                       l=g["l" "ow"].to_numpy(float), c=c,
                       idx={dd: i for i, dd in enumerate(g["date"].to_numpy())},
                       r63=r63, dhi=dhi)
del px

print("loading signals...", flush=True)
sig = pd.read_csv(D + r"\signals_2010.csv.gz")
sig = sig[sig["score"] >= 55].copy()
sig["atr_pct"] = sig["atr"] / sig["close"] * 100
sig["quality"] = (~sig["counter_trend"]) & (sig["trend"] == "Up") & (sig["adx"] >= 25)

def feat(row_syms, row_dates, key):
    out = np.full(len(row_syms), np.nan)
    for i, (s, dt) in enumerate(zip(row_syms, row_dates)):
        a = P.get(s)
        if a is None: continue
        j = a["idx"].get(dt)
        if j is not None: out[i] = a[key][j]
    return out
syms_arr = sig["symbol"].astype(str).to_numpy(); dates_arr = sig["date"].to_numpy()
sig["r63"] = feat(syms_arr, dates_arr, "r63")
sig["dhi"] = feat(syms_arr, dates_arr, "dhi")
sig["nifr63"] = sig["date"].map(nif_r63)
sig["momentum"] = (sig["dhi"] >= -0.15) & (sig["r63"] > sig["nifr63"]) & (sig["r63"] > 0)
sig["momentum"] = sig["momentum"].fillna(False)

# production v3 ordering: momentum tier first, quality second, score third
f = sig.sort_values(["date","momentum","quality","score"],
                    ascending=[True,False,False,False]).groupby("date").head(TOP_N)
print(f"selected trades: {len(f)}", flush=True)

rows = []
for s, dt, ap, sc, q, m in zip(f["symbol"].astype(str), f["date"], f["atr_pct"],
                               f["score"], f["quality"], f["momentum"]):
    a = P.get(s)
    j = a["idx"].get(dt) if a else None
    if j is None or j + 1 >= len(a["c"]) or not (ap > 0) or a["o"][j+1] <= 0:
        continue
    e = float(a["o"][j+1])
    gap = (e / float(a["c"][j]) - 1) * 100 if a["c"][j] > 0 else np.nan
    lo = a["l"][j+1:j+1+HMAX]; hi = a["h"][j+1:j+1+HMAX]; cl = a["c"][j+1:j+1+HMAX]
    sl = e * (1 - SLX*ap/100); tp = e * (1 + TPX*ap/100)
    mtr = min(HOLD, len(cl))
    ex = None; exd = mtr; ety = "TIME"
    for k in range(mtr):
        if lo[k] <= sl: ex, exd, ety = sl, k+1, "SL"; break
        if hi[k] >= tp: ex, exd, ety = tp, k+1, "TP"; break
    if ex is None: ex = float(cl[mtr-1])
    net = (ex/e - 1)*100 - COST
    # full-window excursions (independent of exit) and post-SL recovery
    mfe = (np.max(hi[:mtr]) / e - 1) * 100
    mae = (np.min(lo[:mtr]) / e - 1) * 100
    tp_after_sl = bool(ety == "SL" and np.max(hi[exd-1:mtr]) >= tp)
    # alternative exit previews (same window): chandelier 2.5xATR trailing, no TP
    atr_abs = e * ap / 100
    hh = e; ch_ex = None; ch_d = mtr
    for k in range(mtr):
        stopv = max(sl, hh - 2.5 * atr_abs)
        if lo[k] <= stopv: ch_ex, ch_d = stopv, k+1; break
        hh = max(hh, float(hi[k]))
    if ch_ex is None: ch_ex = float(cl[mtr-1])
    ch_net = (ch_ex/e - 1)*100 - COST
    rows.append((dt, dt[:4], s, float(sc), bool(q), bool(m), round(gap,3), round(ap,3),
                 ety, exd, round(net,3), round(mfe,3), round(mae,3), tp_after_sl,
                 round(ch_net,3)))

df = pd.DataFrame(rows, columns=["date","year","symbol","score","quality","momentum",
                                 "gap_pct","atr_pct","exit_type","exit_day","net",
                                 "mfe","mae","tp_after_sl","chandelier_net"])
df.to_csv(OUT, index=False)
print(f"saved {len(df)} trades -> {OUT}", flush=True)

def block(d, name):
    if len(d) < 30:
        print(f"\n== {name}: only {len(d)} trades =="); return
    w = d["net"] > 0
    print(f"\n== {name}: n={len(d)} win={w.mean()*100:.1f}% exp={d['net'].mean():+.3f} "
          f"PF={d.loc[w,'net'].sum()/max(1e-9,-d.loc[~w,'net'].sum()):.2f} ==")
    et = d.groupby("exit_type")["net"].agg(["count","mean"])
    for t, r in et.iterrows():
        print(f"   exit {t:<5} {int(r['count']):>6} trades ({r['count']/len(d)*100:4.1f}%)  avg {r['mean']:+.3f}")
    sl = d[d["exit_type"]=="SL"]
    if len(sl): print(f"   SL trades that later hit TP anyway (whipsaw): {sl['tp_after_sl'].mean()*100:.1f}%")
    print(f"   median MFE {d['mfe'].median():+.2f}%  median MAE {d['mae'].median():+.2f}%")
    lose = d[d["net"]<=0]
    if len(lose): print(f"   losers whose MFE reached +1xATR ({SLX}R proxy): "
                        f"{(lose['mfe'] >= lose['atr_pct']).mean()*100:.1f}%")
    print(f"   chandelier-2.5ATR-no-TP preview: exp={d['chandelier_net'].mean():+.3f} "
          f"win={(d['chandelier_net']>0).mean()*100:.1f}%")

TR = df[(df["date"]>="2011-01-01")&(df["date"]<="2019-12-31")]
VA = df[(df["date"]>="2020-01-01")&(df["date"]<="2022-12-31")]
TE = df[df["date"]>="2023-01-01"]
block(TR, "TRAIN 2011-19"); block(VA, "VAL 2020-22"); block(TE, "TEST 2023-26")

print("\n== per-year ==")
for y, g in df.groupby("year"):
    w = (g["net"]>0).mean()*100
    print(f"   {y}: n={len(g):>5} win={w:4.1f}% exp={g['net'].mean():+.3f}")

print("\n== expectancy by entry-gap bucket (all years / test) ==")
bins = [-np.inf,-1,0,1,2,4,np.inf]
labs = ["<-1%","-1..0","0..1","1..2","2..4",">4%"]
df["gapb"] = pd.cut(df["gap_pct"], bins, labels=labs)
for scope, d in [("ALL", df), ("TEST", TE)]:
    for b, g in d.groupby("gapb", observed=True):
        if len(g) >= 30:
            print(f"   [{scope}] gap {b:<6} n={len(g):>5} ({len(g)/len(d)*100:4.1f}%) "
                  f"win={(g['net']>0).mean()*100:4.1f}% exp={g['net'].mean():+.3f}")

print("\n== expectancy by ATR%% quintile (all / test) ==")
df["atrq"] = pd.qcut(df["atr_pct"], 5, labels=["Q1 low","Q2","Q3","Q4","Q5 high"])
for scope, d in [("ALL", df), ("TEST", TE)]:
    for b, g in d.groupby("atrq", observed=True):
        print(f"   [{scope}] {b:<7} n={len(g):>5} win={(g['net']>0).mean()*100:4.1f}% exp={g['net'].mean():+.3f}")

print("\n== expectancy by score band (test) ==")
for lo_, hi_ in [(55,60),(60,65),(65,70),(70,101)]:
    g = TE[(TE["score"]>=lo_)&(TE["score"]<hi_)]
    if len(g) >= 30:
        print(f"   score {lo_}-{hi_}: n={len(g):>5} win={(g['net']>0).mean()*100:4.1f}% exp={g['net'].mean():+.3f}")

print("\n== TIME exits: where do they end (test)? ==")
te_time = TE[TE["exit_type"]=="TIME"]
if len(te_time):
    print(f"   n={len(te_time)} avg={te_time['net'].mean():+.3f} "
          f"| negative-at-exit share={(te_time['net']<=0).mean()*100:.1f}%")

print("\n== early laggards (test): trades below entry at day 5 (proxy: MAE<=-0.5xATR by then unavailable; use exit_day/SL) ==")
print("\nDONE", flush=True)
