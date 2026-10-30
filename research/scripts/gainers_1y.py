import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import yfinance as yf
import pandas as pd
import numpy as np
import swing_trading as st

OUT = str(ROOT.joinpath("research", "data", "top_gainers_1y.csv"))

syms = st.SWING_UNIVERSE
print(f"downloading 1y daily data for {len(syms)} stocks...", file=sys.stderr)
data = yf.download(syms, period="1y", group_by="ticker", progress=False, threads=True, auto_adjust=False)

closes, vols = {}, {}
lvl0 = set(data.columns.get_level_values(0))
for s in syms:
    if s in lvl0:
        closes[s] = data[s]["Close"]
        vols[s] = data[s]["Volume"]
closes = pd.DataFrame(closes)
vols = pd.DataFrame(vols)
print(f"got data for {closes.shape[1]} stocks, {closes.shape[0]} trading days", file=sys.stderr)

pct = closes.pct_change() * 100.0

rows = []
dates = list(pct.index)
for i, date in enumerate(dates):
    if i == 0:
        continue
    day = pct.iloc[i].dropna()
    # ignore junk moves from missing data
    day = day[(day > -50) & (day < 50)]
    top = day.sort_values(ascending=False).head(10)
    for rank, (sym, chg) in enumerate(top.items(), 1):
        close = closes.iloc[i][sym]
        prev = closes.iloc[i - 1][sym]
        vol = vols.iloc[i][sym]
        # follow-through: what happened AFTER making the gainers list
        nxt1 = pct.iloc[i + 1][sym] if i + 1 < len(dates) else np.nan
        nxt5 = ((closes.iloc[i + 5][sym] / close) - 1) * 100.0 if i + 5 < len(dates) else np.nan
        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "rank": rank,
            "symbol": sym.replace(".NS", ""),
            "prev_close": round(float(prev), 2),
            "close": round(float(close), 2),
            "gain_pct": round(float(chg), 2),
            "volume": int(vol) if pd.notna(vol) else 0,
            "next_day_pct": round(float(nxt1), 2) if pd.notna(nxt1) else "",
            "next_5d_pct": round(float(nxt5), 2) if pd.notna(nxt5) else "",
        })

df = pd.DataFrame(rows)
df.to_csv(OUT, index=False)
print(f"saved {len(df)} rows ({df['date'].nunique()} days) -> {OUT}", file=sys.stderr)

# ── Follow-through stats: does buying yesterday's top-10 gainer work? ──
ft = df[df["next_day_pct"] != ""].copy()
ft["next_day_pct"] = ft["next_day_pct"].astype(float)
ft5 = df[df["next_5d_pct"] != ""].copy()
ft5["next_5d_pct"] = ft5["next_5d_pct"].astype(float)

print("\n=== WHAT HAPPENS AFTER A STOCK MAKES THE TOP-10 GAINERS LIST ===")
print(f"sample: {len(ft)} gainer events over {df['date'].nunique()} trading days")
print(f"avg gain on the day it made the list : {df['gain_pct'].mean():+.2f}%")
print(f"avg return the NEXT day              : {ft['next_day_pct'].mean():+.2f}%")
print(f"next day was positive                : {(ft['next_day_pct'] > 0).mean()*100:.1f}% of the time")
print(f"avg return over the NEXT 5 days      : {ft5['next_5d_pct'].mean():+.2f}%")
print(f"next 5 days were positive            : {(ft5['next_5d_pct'] > 0).mean()*100:.1f}% of the time")
print(f"median next-day return               : {ft['next_day_pct'].median():+.2f}%")

print("\n=== rank-1 gainers only (the biggest daily winner) ===")
r1 = ft[ft["rank"] == 1]
r15 = ft5[ft5["rank"] == 1]
print(f"avg next-day return : {r1['next_day_pct'].mean():+.2f}%  (positive {(r1['next_day_pct']>0).mean()*100:.1f}% of the time)")
print(f"avg next-5d return  : {r15['next_5d_pct'].mean():+.2f}%  (positive {(r15['next_5d_pct']>0).mean()*100:.1f}% of the time)")

print("\n=== most frequent top-10 appearances (last 1y) ===")
print(df["symbol"].value_counts().head(15).to_string())

print("\n=== sample: last 3 days of top-10 lists ===")
last3 = sorted(df["date"].unique())[-3:]
print(df[df["date"].isin(last3)][["date","rank","symbol","gain_pct","next_day_pct"]].to_string(index=False))
