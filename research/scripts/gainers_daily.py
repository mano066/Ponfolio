import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import yfinance as yf
import pandas as pd
import numpy as np
import swing_trading as st

DOCS = str(ROOT.joinpath("research", "data"))
B, A = 30, 30          # 30 days before, 30 after
syms = st.SWING_UNIVERSE
print(f"downloading 2y daily data for {len(syms)} stocks...", file=sys.stderr)
data = yf.download(syms, period="2y", group_by="ticker", progress=False, threads=True, auto_adjust=False)

C = {}
lvl0 = set(data.columns.get_level_values(0))
for s in syms:
    if s in lvl0:
        C[s] = data[s]["Close"]
C = pd.DataFrame(C)
pct = C.pct_change()*100.0
dates = list(C.index); N = len(dates)
print(f"got {C.shape[1]} stocks x {N} days", file=sys.stderr)

offsets = list(range(-B, A+1))
cols = [f"t{o:+d}".replace("+0","0") if o==0 else f"t{o:+d}" for o in offsets]

start_i = max(1, N - 249)
close_rows, idx_rows = [], []
for i in range(start_i, N):
    day = pct.iloc[i].dropna()
    day = day[(day > -50) & (day < 50)]
    top = day.sort_values(ascending=False).head(10)
    for rank,(sym,chg) in enumerate(top.items(),1):
        base = float(C.iloc[i][sym])
        meta = dict(date=dates[i].strftime("%Y-%m-%d"), rank=rank,
                    symbol=sym.replace(".NS",""), spike_gain_pct=round(float(chg),2),
                    spike_close=round(base,2))
        cr = dict(meta); ir = dict(meta)
        for o,c in zip(offsets, cols):
            j = i+o
            if 0 <= j < N and pd.notna(C.iloc[j][sym]):
                v = float(C.iloc[j][sym])
                cr[c] = round(v,2)
                ir[c] = round(v/base*100,2) if base>0 else ""
            else:
                cr[c] = ""; ir[c] = ""
        close_rows.append(cr); idx_rows.append(ir)

order = ["date","rank","symbol","spike_gain_pct","spike_close"] + cols
dfc = pd.DataFrame(close_rows)[order]
dfi = pd.DataFrame(idx_rows)[order]
f_close = DOCS + r"\gainers_daily_close.csv"
f_idx   = DOCS + r"\gainers_daily_indexed.csv"
dfc.to_csv(f_close, index=False)
dfi.to_csv(f_idx, index=False)
print(f"saved {len(dfc)} events x {len(cols)} day-columns", file=sys.stderr)
print(f"  raw closes  -> {f_close}", file=sys.stderr)
print(f"  indexed=100 -> {f_idx}", file=sys.stderr)

# ── Average trajectory across all events (index=100 at spike) ──
num = dfi[cols].apply(pd.to_numeric, errors="coerce")
print("\n=== AVERAGE TRAJECTORY (all 2,480 events, price indexed to 100 on spike day) ===")
print(f"{'offset':>7}{'mean':>9}{'median':>9}{'%above100':>11}")
show = list(range(-30,-19,5)) + list(range(-15,0,3)) + [-2,-1,0,1,2] + list(range(3,16,3)) + list(range(20,31,5))
for o in show:
    c = f"t{o:+d}" if o!=0 else "t0"
    col = num[c].dropna()
    if len(col):
        print(f"{o:>+7}{col.mean():>9.2f}{col.median():>9.2f}{(col>100).mean()*100:>10.1f}%")

peak_after = num[[c for c in cols if c.startswith('t+') ]].max(axis=1)
print(f"\nDay 0 = 100 by definition (the spike close).")
print(f"Mean index 30d BEFORE spike : {num['t-30'].dropna().mean():.2f}  (so avg run-up into spike ~ {num['t-30'].dropna().mean():.0f}->100)")
print(f"Mean index 30d AFTER spike  : {num['t+30'].dropna().mean():.2f}")
print(f"Held above spike close 30d later: {(num['t+30'].dropna()>100).mean()*100:.1f}% of events")
