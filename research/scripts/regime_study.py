"""REGIME GATE STUDY (2010-now): does a market filter improve Swing v2?

Simulates the PRODUCTION v2 selection: quality picks (Up, not counter-trend,
ADX>=25) ranked first then score, top-5/day, SL 1.5xATR, TP 2xATR, hold 20d,
enter T+1 open, 0.30% costs. Gates tested (all computed through day T, no
lookahead), sweep on TRAIN 2011-2019, confirm on VAL 2020-2022 (covid crash +
recovery), one look at TEST 2023-now.
Gates: none | nifty>200dma | >150dma | >100dma | golden(50>200) | half-size<200dma
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
D = str(ROOT.joinpath("research", "data"))
COST = 0.30; TOP_N = 5; HMAX = 21; SLX = 1.5; TPX = 2.0; HOLD = 20

print("loading...", flush=True)
px = pd.read_csv(D + r"\nse_universe_2010_ohlcv.csv.gz").sort_values(["symbol", "date"])
sig = pd.read_csv(D + r"\signals_2010.csv.gz")
nif = pd.read_csv(D + r"\nifty50_daily_2010.csv").sort_values("date")

P = {}
for sym, g in px.groupby("symbol", sort=False):
    P[sym] = dict(o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
                  l=g["low"].to_numpy(float), c=g["close"].to_numpy(float),
                  idx={dd: i for i, dd in enumerate(g["date"])})

nif["dma200"] = nif["nifty_close"].rolling(200).mean()
nif["dma150"] = nif["nifty_close"].rolling(150).mean()
nif["dma100"] = nif["nifty_close"].rolling(100).mean()
nif["dma50"] = nif["nifty_close"].rolling(50).mean()
nif["g200"] = nif["nifty_close"] > nif["dma200"]
nif["g150"] = nif["nifty_close"] > nif["dma150"]
nif["g100"] = nif["nifty_close"] > nif["dma100"]
nif["gold"] = nif["dma50"] > nif["dma200"]
NIF = nif.set_index("date")[["g200", "g150", "g100", "gold"]].to_dict("index")

sig["atr_pct"] = sig["atr"] / sig["close"] * 100
sig["quality"] = (~sig["counter_trend"]) & (sig["trend"] == "Up") & (sig["adx"] >= 25)
sig = sig[sig["score"] >= 55]
print(f"{len(sig):,} signals >=55, {sig['date'].nunique()} days", flush=True)

# v2 selection: quality first, then score
sig = sig.sort_values(["date", "quality", "score"], ascending=[True, False, False])
picks = sig.groupby("date").head(TOP_N)
print(f"{len(picks):,} daily picks", flush=True)

# simulate each pick once; gates then just mask/scale
trades = []
for sym, date, atrp in zip(picks["symbol"], picks["date"], picks["atr_pct"]):
    a = P.get(sym); j = a["idx"].get(date) if a else None
    if j is None or j + 1 >= len(a["c"]) or atrp <= 0:
        continue
    e = a["o"][j+1]
    if e <= 0:
        continue
    lo = a["l"][j+1:j+1+HMAX]; hi = a["h"][j+1:j+1+HMAX]; cl = a["c"][j+1:j+1+HMAX]
    sl = e * (1 - SLX*atrp/100); tp = e * (1 + TPX*atrp/100)
    n = min(HOLD, len(cl)); ex = None
    for k in range(n):
        if lo[k] <= sl: ex = sl; break
        if hi[k] >= tp: ex = tp; break
    if ex is None: ex = cl[n-1]
    trades.append((date, sym, (ex/e - 1)*100 - COST))
T = pd.DataFrame(trades, columns=["date", "symbol", "net"])
T["year"] = T["date"].str[:4]
print(f"{len(T):,} simulated trades {T['date'].min()}..{T['date'].max()}", flush=True)

def regime_ok(date, gate):
    r = NIF.get(date)
    if r is None or (isinstance(r.get("g200"), float) and np.isnan(r["g200"])):
        return True  # no DMA yet -> allow (early 2010 only)
    if gate == "none": return True
    if gate == "g200": return bool(r["g200"])
    if gate == "g150": return bool(r["g150"])
    if gate == "g100": return bool(r["g100"])
    if gate == "gold": return bool(r["gold"])
    return True

SPLITS = [("TRAIN 2011-2019", "2011-01-01", "2019-12-31"),
          ("VAL 2020-2022", "2020-01-01", "2022-12-31"),
          ("TEST 2023-now", "2023-01-01", "2099-01-01")]
GATES = ["none", "g200", "g150", "g100", "gold", "half200"]
GNAMES = {"none": "no gate (v2 as-is)", "g200": "Nifty > 200-DMA",
          "g150": "Nifty > 150-DMA", "g100": "Nifty > 100-DMA",
          "gold": "50-DMA > 200-DMA", "half200": "half size below 200-DMA"}

def stats(t, weights=None):
    if len(t) == 0: return None
    w = np.ones(len(t)) if weights is None else weights
    net = t["net"].to_numpy()
    wins = (net > 0)
    tot = (net * w).sum(); risked = w.sum()
    exp = tot / risked
    pf = (net[wins] * w[wins]).sum() / max(1e-9, -(net[~wins] * w[~wins]).sum())
    return dict(n=int(w.sum()), win=wins.mean()*100 if weights is None else
                (w[wins].sum()/risked*100), exp=exp, pf=pf, tot=tot)

print("\n" + "="*88)
print(f"REGIME GATE STUDY — v2 picks, {SLX}xATR SL / {TPX}xATR TP, after {COST}% costs")
print("="*88)
for label, d0, d1 in SPLITS:
    part = T[(T["date"] >= d0) & (T["date"] <= d1)]
    print(f"\n--- {label} ({part['date'].nunique()} trading days, {len(part):,} unrestricted trades) ---")
    print(f"{'gate':<26}{'trades':>7}{'win%':>7}{'exp%/tr':>9}{'PF':>6}{'sum net%':>10}{'days out%':>10}")
    for g in GATES:
        if g == "half200":
            w = part["date"].map(lambda d: 1.0 if regime_ok(d, "g200") else 0.5).to_numpy()
            s = stats(part, w)
            days_out = 0.0
        else:
            mask = part["date"].map(lambda d: regime_ok(d, g))
            sub = part[mask]
            s = stats(sub)
            days_out = 100 - mask.mean()*100
        if s:
            print(f"{GNAMES[g]:<26}{s['n']:>7.0f}{s['win']:>7.1f}{s['exp']:>9.3f}{s['pf']:>6.2f}"
                  f"{s['tot']:>10.0f}{days_out:>9.1f}%")

# yearly detail for no-gate vs g200 (the primary comparison)
print("\n--- yearly: no gate vs Nifty>200-DMA gate ---")
print(f"{'year':<6}{'trades':>7}{'exp none':>10}{'exp g200':>10}{'traded%':>9}")
for y, part in T.groupby("year"):
    mask = part["date"].map(lambda d: regime_ok(d, "g200"))
    s0 = stats(part); s1 = stats(part[mask])
    if s0 and s1:
        print(f"{y:<6}{len(part):>7}{s0['exp']:>10.3f}{s1['exp']:>10.3f}{mask.mean()*100:>8.1f}%")
    elif s0:
        print(f"{y:<6}{len(part):>7}{s0['exp']:>10.3f}{'ALL OUT':>10}{0:>8.1f}%")
print("\nDONE", flush=True)
