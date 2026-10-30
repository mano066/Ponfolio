"""Finish the v4 diagnostics aggregates from the saved per-trade CSV."""
import warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
df = pd.read_csv(str(ROOT.joinpath("research", "data", "v4_diag_trades.csv")))
bins = [-np.inf,-1,0,1,2,4,np.inf]
labs = ["<-1%","-1..0","0..1","1..2","2..4",">4%"]
df["gapb"] = pd.cut(df["gap_pct"], bins, labels=labs)
df["atrq"] = pd.qcut(df["atr_pct"], 5, labels=["Q1 low","Q2","Q3","Q4","Q5 high"])
TE = df[df["date"] >= "2023-01-01"]

def line(tag, g, tot):
    print(f"   [{tag}] n={len(g):>5} ({len(g)/tot*100:4.1f}%) win={(g['net']>0).mean()*100:4.1f}% "
          f"exp={g['net'].mean():+.3f}")

print("== expectancy by entry-gap bucket ==")
for scope, d in [("ALL", df), ("TEST", TE)]:
    for b, g in d.groupby("gapb", observed=True):
        if len(g) >= 30: print(f"   [{scope}] gap {b:<6}", end=""); line("", g, len(d))

print("\n== expectancy by ATR% quintile ==")
for scope, d in [("ALL", df), ("TEST", TE)]:
    for b, g in d.groupby("atrq", observed=True):
        print(f"   [{scope}] {b:<7}", end=""); line("", g, len(d))

print("\n== expectancy by score band (test) ==")
for lo_, hi_ in [(55,60),(60,65),(65,70),(70,101)]:
    g = TE[(TE["score"]>=lo_)&(TE["score"]<hi_)]
    if len(g) >= 30: print(f"   score {lo_}-{hi_}", end=""); line("", g, len(TE))

print("\n== exit-day distribution (test) ==")
for t, g in TE.groupby("exit_type"):
    print(f"   {t}: median exit day {g['exit_day'].median():.0f}, mean {g['exit_day'].mean():.1f}")

print("\n== TIME exits detail (test) ==")
tt = TE[TE["exit_type"]=="TIME"]
print(f"   n={len(tt)} avg={tt['net'].mean():+.3f} negative-share={(tt['net']<=0).mean()*100:.1f}%")

print("\n== chandelier preview by period ==")
for tag, d in [("TRAIN", df[df["date"]<="2019-12-31"]),
               ("VAL", df[(df["date"]>="2020-01-01")&(df["date"]<="2022-12-31")]),
               ("TEST", TE)]:
    print(f"   {tag}: fixed-TP exp={d['net'].mean():+.3f} | chandelier exp={d['chandelier_net'].mean():+.3f} "
          f"| chand win={(d['chandelier_net']>0).mean()*100:.1f}%")

print("\n== momentum vs non-momentum picks (test) ==")
for m, g in TE.groupby("momentum"):
    print(f"   momentum={m}: ", end=""); line("", g, len(TE))

print("\n== gap x period stability: exp for gap<=0 vs gap>0 ==")
for tag, d in [("TRAIN", df[df["date"]<="2019-12-31"]),
               ("VAL", df[(df["date"]>="2020-01-01")&(df["date"]<="2022-12-31")]),
               ("TEST", TE)]:
    lo_ = d[d["gap_pct"]<=0]; hi_ = d[d["gap_pct"]>0]
    print(f"   {tag}: gap<=0 n={len(lo_)} exp={lo_['net'].mean():+.3f} | gap>0 n={len(hi_)} exp={hi_['net'].mean():+.3f}")
print("\nDONE")
