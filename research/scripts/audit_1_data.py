import warnings, sys
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DOCS = str(ROOT.joinpath("research", "data"))
u = pd.read_csv(DOCS + r"\nse_universe_5y_ohlcv.csv", parse_dates=["date"])
n = pd.read_csv(DOCS + r"\nifty50_daily_5y.csv", parse_dates=["date"])
tg = pd.read_csv(DOCS + r"\top_gainers_1y.csv", parse_dates=["date"])

print("=" * 70)
print("SECTION 1 — DATA AUDIT")
print("=" * 70)
print(f"universe rows        : {len(u):,}")
print(f"symbols              : {u['symbol'].nunique()}")
print(f"date range           : {u['date'].min().date()} .. {u['date'].max().date()}")
print(f"trading dates        : {u['date'].nunique()}")
dups = u.duplicated(subset=["date", "symbol"]).sum()
print(f"duplicate (date,sym) : {dups}")
print(f"null counts          : " + ", ".join(f"{c}={u[c].isna().sum()}" for c in ["open","high","low","close","volume","adjusted_close"] if u[c].isna().sum() > 0) or "none in OHLCVA")

# OHLC integrity
bad_hl = (u["high"] < u["low"]).sum()
bad_h = ((u["high"] < u[["open", "close"]].max(axis=1)) & u["open"].notna()).sum()
bad_l = ((u["low"] > u[["open", "close"]].min(axis=1)) & u["open"].notna()).sum()
nonpos = (u["close"] <= 0).sum()
print(f"\nOHLC integrity: high<low={bad_hl}, high<max(o,c)={bad_h}, low>min(o,c)={bad_l}, close<=0={nonpos}")

# zero-volume
zv = u.groupby("date")["volume"].apply(lambda s: (s == 0).mean())
allzv = zv[zv >= 0.99]
print(f"\ndates where >=99% of stocks have ZERO volume ({len(allzv)}):")
for d, frac in allzv.items():
    dow = d.strftime("%A")
    print(f"  {d.date()} ({dow}): {frac*100:.1f}% zero-volume")
suspects = ["2026-01-15", "2026-05-01", "2026-05-28", "2026-06-26"]
print("\nsuspect dates check:")
for s in suspects:
    d = pd.Timestamp(s)
    sub = u[u["date"] == d]
    if len(sub) == 0:
        print(f"  {s}: NOT in file")
    else:
        zfrac = (sub["volume"] == 0).mean()
        # do prices move at all that day?
        prev = u[u["date"] < d]["date"].max()
        m = u[u["date"].isin([prev, d])].pivot_table(index="symbol", columns="date", values="adjusted_close")
        if m.shape[1] == 2:
            chg = (m.iloc[:, 1] / m.iloc[:, 0] - 1).abs()
            moved = (chg > 0.0005).mean()
        else:
            moved = np.nan
        print(f"  {s} ({d.strftime('%A')}): rows={len(sub)}, zero-vol={zfrac*100:.1f}%, stocks with price change={moved*100:.1f}%")

# per-symbol history length (IPO/survivorship indicator)
sym_start = u.groupby("symbol")["date"].min()
full_hist = (sym_start <= u["date"].min() + pd.Timedelta(days=7)).sum()
print(f"\nsymbols with full 5y history      : {full_hist}/{u['symbol'].nunique()}")
print(f"symbols starting after 2023-07-15 : {(sym_start > '2023-07-15').sum()} (IPOs/recent listings)")
print(f"symbols starting after 2025-07-15 : {(sym_start > '2025-07-15').sum()}")
last = u.groupby("symbol")["date"].max()
dead = last[last < u["date"].max() - pd.Timedelta(days=7)]
print(f"symbols that STOP trading before file end (delisted-in-window): {len(dead)}")
print("=> survivorship: universe is TODAY'S constituents; delisted/removed names absent -> POSITIVE bias for long strategies")

# adjusted vs close divergence (split handling check)
u["adj_factor"] = u["adjusted_close"] / u["close"]
fac_jump = u.sort_values(["symbol", "date"]).groupby("symbol")["adj_factor"].apply(
    lambda s: (s.pct_change().abs() > 0.05).sum())
print(f"\nsymbols with >=1 adjustment-factor jump >5% (splits/bonuses/dividends): {(fac_jump > 0).sum()}")

# extreme adjusted returns
u = u.sort_values(["symbol", "date"])
u["ret"] = u.groupby("symbol")["adjusted_close"].pct_change() * 100
ext = u[u["ret"].abs() > 40].copy()
print(f"\nadjusted daily moves >40% ({len(ext)} events):")
for _, r in ext.sort_values("ret", key=abs, ascending=False).head(15).iterrows():
    # compare raw-close return to adjusted return to detect bad adjustment
    print(f"  {r['date'].date()} {r['symbol']:<12} adjret={r['ret']:+7.1f}%  close={r['close']:>9.2f}")
named = ["DIACABS", "GPIL", "JSLL", "ABFRL", "VEDL", "SKFINDIA"]
print("\nnamed suspects — raw vs adjusted return on their extreme day:")
for sym in named:
    s = u[u["symbol"] == sym].sort_values("date").copy()
    if s.empty:
        print(f"  {sym}: not in file"); continue
    s["raw_ret"] = s["close"].pct_change() * 100
    w = s[s["ret"].abs() > 30]
    if w.empty:
        w = s.loc[s["ret"].abs().nlargest(1).index]
    for _, r in w.iterrows():
        verdict = "CORPORATE ACTION (raw≠adj)" if abs(r["raw_ret"] - r["ret"]) > 10 else "real move or split leak in adj too"
        print(f"  {sym:<10} {r['date'].date()} adj={r['ret']:+7.1f}% raw={r['raw_ret']:+7.1f}%  -> {verdict}")

# reproduce top-gainers list from universe file
print("\n" + "=" * 70)
print("REPRODUCIBILITY: top_gainers_1y.csv vs recomputed from universe file")
print("=" * 70)
u["rawret"] = u.groupby("symbol")["close"].pct_change() * 100
dates_1y = sorted(tg["date"].unique())
match_days = exact = 0
mismatch_examples = []
for d in dates_1y:
    day = u[u["date"] == d].dropna(subset=["rawret"])
    day = day[day["rawret"].between(-50, 50)]
    mine = set(day.nlargest(10, "rawret")["symbol"])
    theirs = set(tg[tg["date"] == d]["symbol"])
    inter = len(mine & theirs)
    match_days += 1
    if inter == 10:
        exact += 1
    elif len(mismatch_examples) < 3:
        mismatch_examples.append((pd.Timestamp(d).date(), inter, sorted(theirs - mine)[:3], sorted(mine - theirs)[:3]))
print(f"days compared: {match_days}, exact 10/10 match: {exact} ({exact/match_days*100:.1f}%)")
for d, inter, only_t, only_m in mismatch_examples:
    print(f"  {d}: overlap {inter}/10; only-in-file={only_t} only-recomputed={only_m}")
print("(mismatches expected where the 1y file used unadjusted closes vs corporate-action days, or +/-50% filter)")
