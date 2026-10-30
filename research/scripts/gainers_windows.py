import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import yfinance as yf
import pandas as pd
import numpy as np
import swing_trading as st

SCR = str(ROOT.joinpath("research", "data"))
OUT = SCR + r"\top_gainers_windows.csv"
W = 21  # ~1 trading month

syms = st.SWING_UNIVERSE
print(f"downloading 2y daily OHLCV for {len(syms)} stocks...", file=sys.stderr)
data = yf.download(syms, period="2y", group_by="ticker", progress=False, threads=True, auto_adjust=False)

O,H,L,C,V = {},{},{},{},{}
lvl0 = set(data.columns.get_level_values(0))
for s in syms:
    if s in lvl0:
        d = data[s]
        O[s],H[s],L[s],C[s],V[s] = d["Open"],d["High"],d["Low"],d["Close"],d["Volume"]
O,H,L,C,V = (pd.DataFrame(x) for x in (O,H,L,C,V))
print(f"got {C.shape[1]} stocks x {C.shape[0]} days", file=sys.stderr)

pct = C.pct_change()*100.0
vol20 = V.rolling(20).mean()
dates = list(C.index)
N = len(dates)

# Build gainers list over the LAST 249 trading days (same window as the 1y run)
start_i = max(1, N - 249)
rows = []
for i in range(start_i, N):
    day = pct.iloc[i].dropna()
    day = day[(day > -50) & (day < 50)]
    top = day.sort_values(ascending=False).head(10)
    for rank,(sym,chg) in enumerate(top.items(),1):
        close = C.iloc[i][sym]; prev = C.iloc[i-1][sym]
        hi = H.iloc[i][sym]; lo = L.iloc[i][sym]
        vr = (V.iloc[i][sym]/vol20.iloc[i][sym]) if vol20.iloc[i][sym]>0 else np.nan
        cpr = (close-lo)/(hi-lo) if (hi-lo)>0 else np.nan  # close position in day range
        # pre-spike run-up: return over W days ending the day BEFORE the spike
        pre = ((prev / C.iloc[i-1-W][sym])-1)*100 if i-1-W>=0 else np.nan
        def fwd(k):
            return ((C.iloc[i+k][sym]/close)-1)*100 if i+k<N else np.nan
        # forward path stats over next W days
        if i+W < N:
            path = C.iloc[i+1:i+1+W][sym]
            mg = (path.max()/close-1)*100
            mdd = (path.min()/close-1)*100
        else:
            mg=mdd=np.nan
        rows.append(dict(
            date=dates[i].strftime("%Y-%m-%d"), rank=rank, symbol=sym.replace(".NS",""),
            prev_close=round(float(prev),2), close=round(float(close),2), gain_pct=round(float(chg),2),
            volume=int(V.iloc[i][sym]) if pd.notna(V.iloc[i][sym]) else 0,
            vol_ratio=round(float(vr),2) if pd.notna(vr) else "",
            close_in_range=round(float(cpr),2) if pd.notna(cpr) else "",
            pre_1m_pct=round(float(pre),2) if pd.notna(pre) else "",
            next_1d=round(float(fwd(1)),2) if pd.notna(fwd(1)) else "",
            next_5d=round(float(fwd(5)),2) if pd.notna(fwd(5)) else "",
            next_10d=round(float(fwd(10)),2) if pd.notna(fwd(10)) else "",
            next_21d=round(float(fwd(21)),2) if pd.notna(fwd(21)) else "",
            max_gain_1m=round(float(mg),2) if pd.notna(mg) else "",
            max_dd_1m=round(float(mdd),2) if pd.notna(mdd) else "",
        ))

df = pd.DataFrame(rows)
df.to_csv(OUT, index=False)
print(f"saved {len(df)} events ({df['date'].nunique()} days) -> {OUT}", file=sys.stderr)

def num(col):
    s = pd.to_numeric(df[col], errors="coerce"); return s
d1 = num("next_1d"); d5 = num("next_5d"); d21 = num("next_21d")
pre = num("pre_1m_pct"); vr = num("vol_ratio"); cir = num("close_in_range"); g = num("gain_pct")
mg = num("max_gain_1m"); mdd = num("max_dd_1m")

def stat(mask, label):
    a1=d1[mask].dropna(); a5=d5[mask].dropna(); a21=d21[mask].dropna()
    print(f"{label:<34} n={len(a1):>4} | nextD {a1.mean():+5.2f}% (win {(a1>0).mean()*100:4.1f}%) "
          f"| 5d {a5.mean():+5.2f}% | 21d {a21.mean():+6.2f}% (win {(a21>0).mean()*100:4.1f}%)")

print("\n================ PREDICTIVE ANALYSIS: what precedes a good NEXT DAY? ================")
print(f"overall baseline                   n={len(d1.dropna())}")
stat(d1.notna(), "ALL top-10 gainers")

print("\n-- by PRE-SPIKE 1-month run-up (was it already trending up?) --")
stat(pre< -5, "  fell >5% into spike (reversal)")
stat((pre>=-5)&(pre<5), "  flat -5..+5% into spike")
stat((pre>=5)&(pre<20), "  rose 5-20% into spike")
stat(pre>=20, "  rose >20% into spike (extended)")

print("\n-- by how it CLOSED on the spike day (strength) --")
stat(cir>=0.8, "  closed in top 20% of range")
stat((cir>=0.5)&(cir<0.8), "  closed mid-upper range")
stat(cir<0.5, "  closed in lower half (weak)")

print("\n-- by VOLUME surge on spike day --")
stat(vr>=5, "  volume >5x avg (huge)")
stat((vr>=2)&(vr<5), "  volume 2-5x avg")
stat(vr<2, "  volume <2x avg (no conviction)")

print("\n-- by SIZE of the gain --")
stat((g>=5)&(g<8), "  gained 5-8%")
stat((g>=8)&(g<12), "  gained 8-12%")
stat(g>=12, "  gained >12% (biggest pops)")

print("\n-- by RANK on the list --")
stat(df["rank"]==1, "  rank 1 (biggest gainer)")
stat(df["rank"]<=3, "  rank 1-3")
stat(df["rank"]>=8, "  rank 8-10")

print("\n-- BEST COMBO test: strong close + big volume + NOT extended --")
stat((cir>=0.8)&(vr>=3)&(pre<20), "  strong+vol+not-extended")

print(f"\nAfter making the list, over next 1 month: avg MAX gain {mg.dropna().mean():+.2f}%, "
      f"avg MAX drawdown {mdd.dropna().mean():+.2f}%")

print("\n================ EXAMPLE: NETWORK18 around 2025-07-16 ================")
sym="NETWORK18.NS"
if sym in C.columns:
    try:
        ci = dates.index(pd.Timestamp("2025-07-16"))
    except ValueError:
        ci = C.index.get_indexer([pd.Timestamp("2025-07-16")], method="nearest")[0]
    lo=max(0,ci-21); hi=min(N,ci+22)
    print(f"{'date':<12}{'close':>9}{'chg%':>8}   (day 0 = the top-gainer spike)")
    for j in range(lo,hi):
        cl=C.iloc[j][sym]; ch=pct.iloc[j][sym]
        tag=" <== SPIKE" if j==ci else ""
        off=j-ci
        if pd.notna(cl):
            print(f"{dates[j].strftime('%Y-%m-%d'):<12}{cl:>9.2f}{ch:>+8.2f}  {off:+3d}{tag}")
