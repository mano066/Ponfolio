"""Honest walk-forward baseline of the CURRENT swing scanner over 10y.

Uses production scoring (swing_trading._analyze_arrays) verbatim — no
reimplementation — so results reflect the live strategy's real parameters:
  score >= 55, top-5/day, SL = -1.5 ATR, T1 = +2 ATR, liquidity guard.

Trade model (realistic, after-close signal):
  - signal computed at close of day T from trailing 250 bars (no lookahead)
  - ENTER at T+1 open (earliest tradable moment)
  - exit when low<=SL or high>=T1 (SL checked first if both hit same day),
    else at close after MAX_HOLD days
  - costs: ROUNDTRIP% charged on the trade (brokerage+STT+slippage)
Reports win rate, expectancy (R), profit factor, CAGR-ish, drawdown, by year.
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import numpy as np
import pandas as pd
import swing_trading as st

DATA = str(ROOT.joinpath("research", "data", "nse_universe_10y_ohlcv.csv.gz"))
CADENCE = 1          # scan every N trading days (1 = daily, production behavior)
WINDOW = 250         # trailing bars fed to the scorer
SCORE_MIN = 55
TOP_N = 5
MAX_HOLD = 20
ROUNDTRIP = 0.30     # % round-trip cost incl. slippage
MIN_PRICE = 5.0
MIN_TURN = 1e7       # Rs.1 cr avg 20d turnover (liquidity guard)

print("loading 10y data...", flush=True)
df = pd.read_csv(DATA)
df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
dates_all = np.array(sorted(df["date"].unique()))
date_pos = {d: i for i, d in enumerate(dates_all)}
print(f"{len(df):,} rows, {df['symbol'].nunique()} symbols, {len(dates_all)} dates", flush=True)

# per-symbol numpy arrays for speed
S = {}
for sym, g in df.groupby("symbol", sort=False):
    S[sym] = dict(
        d=g["date"].to_numpy(),
        o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
        l=g["low"].to_numpy(float), c=g["close"].to_numpy(float),
        v=g["volume"].to_numpy(float),
        pos=np.array([date_pos[x] for x in g["date"].to_numpy()]),
    )

# --- timing probe ---
probe_syms = list(S)[:20]
t0 = time.time(); n = 0
for sym in probe_syms:
    a = S[sym]
    if len(a["c"]) > WINDOW + 5:
        for i in range(WINDOW, min(WINDOW + 25, len(a["c"]))):
            st._analyze_arrays(sym, a["o"][i-WINDOW:i+1], a["h"][i-WINDOW:i+1],
                               a["l"][i-WINDOW:i+1], a["c"][i-WINDOW:i+1],
                               a["v"][i-WINDOW:i+1]); n += 1
per = (time.time() - t0) / max(n, 1)
elig_est = 550 * (len(dates_all) / CADENCE)
print(f"probe: {per*1000:.2f} ms/score; est calls ~{elig_est:,.0f}; "
      f"est runtime ~{per*elig_est/60:.1f} min", flush=True)

# --- build (date,symbol) -> score by walking each symbol once ---
picks_by_date = {}   # date_idx -> list of (score, sym, entry_ref, risk_pct, reward_pct)
scan_idxs = list(range(WINDOW, len(dates_all), CADENCE))
scanset = set(scan_idxs)
t0 = time.time()
for si, sym in enumerate(S):
    if si % 100 == 0:
        print(f"scoring {si}/{len(S)}  ({(time.time()-t0)/60:.1f} min)", flush=True)
    a = S[sym]
    c, v, pos = a["c"], a["v"], a["pos"]
    for k in range(WINDOW, len(c)):
        di = pos[k]
        if di not in scanset:
            continue
        # liquidity guard (data available at T)
        if c[k] < MIN_PRICE:
            continue
        nn = min(20, k)
        if float(np.mean(c[k-nn+1:k+1] * v[k-nn+1:k+1])) < MIN_TURN:
            continue
        r = st._analyze_arrays(sym, a["o"][k-WINDOW:k+1], a["h"][k-WINDOW:k+1],
                               a["l"][k-WINDOW:k+1], c[k-WINDOW:k+1], v[k-WINDOW:k+1])
        if not r or r.get("score", 0) < SCORE_MIN:
            continue
        rp = r.get("risk_pct"); wp = r.get("reward_pct")
        if not rp or not wp or rp <= 0:
            continue
        picks_by_date.setdefault(di, []).append((r["score"], sym, c[k], rp, wp))
print(f"scoring done in {(time.time()-t0)/60:.1f} min; "
      f"{sum(len(v) for v in picks_by_date.values()):,} qualifying signals", flush=True)

# --- simulate trades: top-5 per scan date, enter T+1 open ---
trades = []
for di, lst in picks_by_date.items():
    lst.sort(reverse=True)
    for score, sym, refc, rp, wp in lst[:TOP_N]:
        a = S[sym]
        j = np.searchsorted(a["pos"], di)
        if j + 1 >= len(a["c"]):
            continue
        entry = a["o"][j+1]
        if entry <= 0:
            continue
        sl = entry * (1 - rp/100)
        tgt = entry * (1 + wp/100)
        exit_px, exit_reason, held = None, None, 0
        for m in range(j+1, min(j+1+MAX_HOLD, len(a["c"]))):
            held = m - j
            lo, hi = a["l"][m], a["h"][m]
            if lo <= sl:           # conservative: stop first
                exit_px, exit_reason = sl, "SL"; break
            if hi >= tgt:
                exit_px, exit_reason = tgt, "T1"; break
        if exit_px is None:
            exit_px, exit_reason = a["c"][min(j+MAX_HOLD, len(a["c"])-1)], "TIME"
        gross = (exit_px/entry - 1) * 100
        net = gross - ROUNDTRIP
        R = net / rp if rp > 0 else 0.0
        trades.append(dict(date=dates_all[di], sym=sym, score=score, entry=entry,
                           gross=gross, net=net, R=R, reason=exit_reason,
                           held=held, risk_pct=rp, reward_pct=wp,
                           year=str(dates_all[di])[:4]))
T = pd.DataFrame(trades)
T.to_csv(str(ROOT.joinpath("research", "data", "baseline_trades_10y.csv")), index=False)

def block(t, label):
    if len(t) == 0:
        print(f"{label}: no trades"); return
    w = t[t["net"] > 0]; l = t[t["net"] <= 0]
    win = len(w)/len(t)*100
    aw = w["net"].mean() if len(w) else 0
    al = l["net"].mean() if len(l) else 0
    pf = (w["net"].sum() / -l["net"].sum()) if len(l) and l["net"].sum() < 0 else float('inf')
    exp_pct = t["net"].mean(); exp_R = t["R"].mean()
    print(f"{label:<12} n={len(t):>5} win={win:5.1f}% avgW={aw:+5.2f}% avgL={al:+5.2f}% "
          f"PF={pf:4.2f} exp={exp_pct:+5.2f}%/tr ({exp_R:+.3f}R) "
          f"SL/T1/TIME={ (t['reason']=='SL').mean()*100:.0f}/{(t['reason']=='T1').mean()*100:.0f}/{(t['reason']=='TIME').mean()*100:.0f}")

print("\n" + "="*78)
print("BASELINE — current scanner parameters, 10y walk-forward, after "
      f"{ROUNDTRIP}% costs")
print("="*78)
block(T, "ALL")
print("-"*78)
for y in sorted(T["year"].unique()):
    block(T[T["year"] == y], y)

# equity curve on 1-unit-risk-per-trade (sequential by date), drawdown
T2 = T.sort_values("date")
eq = (1 + T2["net"]/100).cumprod()
dd = ((eq/eq.cummax()) - 1).min() * 100
# rough annualized: total trades over 10y, avg net per trade
print("-"*78)
print(f"avg hold={T['held'].mean():.1f} days | trades/yr={len(T)/10:.0f} | "
      f"equal-weight compounded MDD={dd:.1f}%")
print(f"expectancy per trade after costs: {T['net'].mean():+.3f}%  "
      f"({T['R'].mean():+.3f}R)  -- THIS is the number that matters")
print("\nwrote research/data/baseline_trades_10y.csv")
print("DONE", flush=True)
