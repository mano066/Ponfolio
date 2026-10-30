"""Advanced v5 flagship: regime-adaptive ensemble + volatility-target sizing +
drawdown de-risking. Event-driven daily portfolio backtest (2010-2026).

Combines only what the research established:
  * BULL regime      -> S1 (trend-pullback) + S3 (rel-strength) + S6 (momentum)
  * SIDEWAYS regime  -> S2 (vol-contraction breakout) WITH strong volume (>=2x)
  * BEAR / HIGH-VOL  -> no new longs (cash) — the regime-defensive rule
Position sizing = fixed fractional RISK per trade via ATR (volatility targeting),
capped by max position weight and max concurrency; new-trade risk is HALVED while
the book sits in >15% drawdown.

Event-driven engine (fixes the earlier exit-day-only equity curve): daily
mark-to-market, next-open fills, gap>4% skip, v4 exit (close<=2.5xATR stop ->
next open; 20-session time exit), 0.30% round-trip cost.

[MEASURED, survivorship-biased daily universe, raw OHLC.] Reproduce:
backend/.venv/Scripts/python.exe research/scripts/multitimeframe/ensemble_v5.py
Out: research/data/ensemble_v5.json
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
D = Path(__file__).resolve().parents[2] / "data"
OUT = D / "ensemble_v5.json"

COST_SIDE = 0.0015          # 0.15% each side ~ 0.30% round trip
GAP_MAX = 0.04
MIN_TURNOVER, MIN_PRICE = 1e7, 5.0
CAP0 = 1_000_000
RISK_PCT = 0.005            # 0.5% equity risked per trade (vol targeting)
MAX_POS_WT = 0.15           # <=15% equity per position
MAX_CONCURRENT = 8
MAX_NEW_PER_DAY = 3
DD_DERISK_LEVEL = 0.15      # halve risk when >15% below equity peak
STOP_ATR, HOLD = 2.5, 20
SPLITS = {"train": (2011, 2019), "val": (2020, 2022), "test": (2023, 2026)}


def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))


print("loading daily lake...", flush=True)
px = pd.read_csv(D/"nse_universe_2010_ohlcv.csv.gz",
                 usecols=["date", "symbol", "open", "high", "low", "close", "volume"],
                 dtype={"symbol": "category", "open": "f4", "high": "f4", "low": "f4",
                        "close": "f4", "volume": "f8"})
nfc = pd.read_csv(D/"nifty50_daily_2010.csv").sort_values("date").set_index("date")["nifty_close"].astype(float)
n_e50, n_e200 = ema(nfc, 50), ema(nfc, 200)
n_vol = nfc.pct_change().rolling(20).std()*np.sqrt(252)
n_volhi = n_vol.rolling(252, min_periods=120).quantile(0.80)
regime = {}
for dt in nfc.index:
    c, e50, e200, vol, vhi = nfc[dt], n_e50[dt], n_e200[dt], n_vol[dt], n_volhi[dt]
    if pd.isna(e200): regime[dt] = "UNKNOWN"
    elif pd.notna(vhi) and vol > vhi and c < e50: regime[dt] = "HIGHVOL"
    elif c > e200 and e50 > e200: regime[dt] = "BULL"
    elif c < e200 and e50 < e200: regime[dt] = "BEAR"
    else: regime[dt] = "SIDEWAYS"
nif_r63 = (nfc/nfc.shift(63)-1).to_dict()

print("indicators...", flush=True)
SYM = {}
calendar = set()
for sym, g in px.groupby("symbol", sort=False, observed=True):
    g = g.sort_values("date"); c = g["close"].astype(float).reset_index(drop=True)
    o = g["open"].astype(float).reset_index(drop=True); h = g["high"].astype(float).reset_index(drop=True)
    lo = g["low"].astype(float).reset_index(drop=True); v = g["volume"].astype(float).reset_index(drop=True)
    if len(c) < 260: continue
    pc = c.shift(1); tr = pd.concat([h-lo, (h-pc).abs(), (lo-pc).abs()], axis=1).max(axis=1)
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    dts = g["date"].to_numpy(); calendar.update(dts.tolist())
    SYM[str(sym)] = dict(
        dates=dts, o=o.to_numpy(), h=h.to_numpy(), l=lo.to_numpy(), c=c.to_numpy(),
        atr=tr.ewm(alpha=1/14, adjust=False).mean().to_numpy(),
        e20=e20.to_numpy(), e50=e50.to_numpy(), e200=e200.to_numpy(), rsi=rsi(c).to_numpy(),
        e50rise=(e50 > e50.shift(5)).to_numpy(), macdup=(ema(c, 12) > ema(c, 26)).to_numpy(),
        hh20=h.rolling(20).max().to_numpy(),
        bbw=((4*c.rolling(20).std())/c.rolling(20).mean().replace(0, np.nan)).to_numpy(),
        bbwq=((4*c.rolling(20).std())/c.rolling(20).mean().replace(0, np.nan)).rolling(100, min_periods=60).quantile(0.25).to_numpy(),
        turn=(c*v).rolling(20).mean().to_numpy(), ret60=(c/c.shift(63)-1).to_numpy(),
        vratio=(v/v.rolling(20).mean().replace(0, np.nan)).to_numpy(),
        idx={d: i for i, d in enumerate(dts)})
del px
CAL = sorted(calendar)
print(f"symbols: {len(SYM)}  trading days: {len(CAL)}", flush=True)


def liquid(a, j): return a["turn"][j] >= MIN_TURNOVER and a["c"][j] >= MIN_PRICE


def signals_for(a, j, reg):
    """Return set of strategy tags firing for symbol at bar j under regime."""
    tags = []
    c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
    if reg == "BULL":
        if (c > e50 > e200 and a["e50rise"][j] and (a["l"][j] <= e20*1.02 or abs(c/e20-1) <= 0.02)
                and c > e20 and 40 <= a["rsi"][j] <= 62 and a["c"][j] > a["o"][j]):
            tags.append("S1")
        if (c > e50 > e200 and a["ret60"][j] > nif_r63.get(a["dates"][j], np.nan)
                and j >= 1 and c >= a["hh20"][j-1]*0.92 and c > a["c"][j-1] and c > e20):
            tags.append("S3")
        if c > e50 > e200 and a["macdup"][j] and 45 <= a["rsi"][j] < 70:
            tags.append("S6")
    elif reg == "SIDEWAYS":
        if (c > e50 > e200 and np.isfinite(a["bbwq"][j]) and a["bbw"][j] <= a["bbwq"][j]
                and j >= 1 and c > a["hh20"][j-1] and c <= e20*1.15
                and np.isfinite(a["vratio"][j]) and a["vratio"][j] >= 2.0):
            tags.append("S2v")
    return tags


def run_portfolio(risk_pct=RISK_PCT, use_regime=True, use_voltarget=True, use_derisk=True):
    cash = CAP0
    positions = {}                 # sym -> dict(shares, entry, stop, held, entry_j)
    pending_buys, pending_sells = [], []
    peak = CAP0
    equity_curve = []              # (date, equity)
    turnover_val = 0.0
    for t, day in enumerate(CAL):
        reg = regime.get(day, "UNKNOWN")
        # 1. execute pending sells at today open
        for sym in pending_sells:
            if sym not in positions: continue
            a = SYM[sym]; j = a["idx"].get(day)
            px_ = a["o"][j] if j is not None else positions[sym]["entry"]
            cash += positions[sym]["shares"] * px_ * (1 - COST_SIDE)
            turnover_val += positions[sym]["shares"] * px_
            del positions[sym]
        pending_sells = []
        # 2. execute pending buys at today open (gap guard)
        for b in pending_buys:
            sym = b["sym"]; a = SYM[sym]; j = a["idx"].get(day)
            if j is None or sym in positions: continue
            op = a["o"][j]
            if op <= 0 or op / b["ref_close"] - 1 > GAP_MAX: continue     # skip gap-ups
            cost_val = b["shares"] * op * (1 + COST_SIDE)
            if cost_val > cash or b["shares"] <= 0: continue
            cash -= cost_val; turnover_val += b["shares"] * op
            positions[sym] = dict(shares=b["shares"], entry=op,
                                  stop=op - STOP_ATR*b["atr"], held=0, entry_j=j)
        pending_buys = []
        # 3. mark-to-market at close
        equity = cash
        for sym, p in positions.items():
            a = SYM[sym]; j = a["idx"].get(day)
            equity += p["shares"] * (a["c"][j] if j is not None else p["entry"])
        peak = max(peak, equity)
        equity_curve.append((day, equity))
        dd = equity / peak - 1
        # 4. decide exits for tomorrow
        for sym, p in list(positions.items()):
            a = SYM[sym]; j = a["idx"].get(day)
            if j is None: continue
            p["held"] += 1
            if a["c"][j] <= p["stop"] or p["held"] >= HOLD:
                pending_sells.append(sym)
        # 5. decide new entries for tomorrow
        open_slots = MAX_CONCURRENT - (len(positions) + len(pending_buys))
        if open_slots > 0 and (reg in ("BULL", "SIDEWAYS") or not use_regime):
            eff_reg = reg if use_regime else "BULL"
            cands = []
            for sym, a in SYM.items():
                if sym in positions: continue
                j = a["idx"].get(day)
                if j is None or j < 260 or j+1 >= len(a["c"]): continue
                if not liquid(a, j): continue
                tags = signals_for(a, j, eff_reg)
                if not tags: continue
                atr = a["atr"][j]
                if not (atr > 0): continue
                cands.append((a["ret60"][j] if np.isfinite(a["ret60"][j]) else -9, sym, a, j, atr))
            cands.sort(reverse=True)
            risk_budget = risk_pct * equity * (0.5 if (use_derisk and dd < -DD_DERISK_LEVEL) else 1.0)
            taken = 0
            for _, sym, a, j, atr in cands:
                if taken >= MAX_NEW_PER_DAY or (len(positions)+len(pending_buys)) >= MAX_CONCURRENT:
                    break
                ref = a["c"][j]
                if use_voltarget:
                    shares = int(risk_budget / (STOP_ATR * atr))
                else:
                    shares = int((equity / MAX_CONCURRENT) / ref)
                # cap by max position weight and cash
                shares = min(shares, int(MAX_POS_WT * equity / ref))
                if shares <= 0: continue
                pending_buys.append(dict(sym=sym, shares=shares, atr=atr, ref_close=ref))
                taken += 1
    eq = pd.Series([e for _, e in equity_curve], index=pd.to_datetime([d for d, _ in equity_curve]))
    return eq, turnover_val


def metrics(eq, split=None):
    e = eq
    if split:
        lo, hi = split
        e = eq[(eq.index.year >= lo) & (eq.index.year <= hi)]
    if len(e) < 20:
        return None
    rets = e.pct_change().dropna()
    yrs = max((e.index[-1]-e.index[0]).days/365.25, 0.4)
    cagr = (e.iloc[-1]/e.iloc[0])**(1/yrs) - 1
    dd = (e/e.cummax()-1).min()
    sharpe = rets.mean()/rets.std()*np.sqrt(252) if rets.std() > 0 else 0
    down = rets[rets < 0].std()
    sortino = rets.mean()/down*np.sqrt(252) if down and down > 0 else 0
    return dict(start=round(float(e.iloc[0])), end=round(float(e.iloc[-1])),
                cagr_pct=round(float(cagr*100), 2), max_dd_pct=round(float(dd*100), 2),
                calmar=round(float(cagr/abs(dd)), 2) if dd < 0 else 0,
                sharpe=round(float(sharpe), 2), sortino=round(float(sortino), 2))


print("\nrunning flagship ensemble + ablations...", flush=True)
configs = {
    "v5_ENSEMBLE_full": dict(use_regime=True, use_voltarget=True, use_derisk=True),
    "ens_no_regime": dict(use_regime=False, use_voltarget=True, use_derisk=True),
    "ens_no_voltarget": dict(use_regime=True, use_voltarget=False, use_derisk=True),
    "ens_no_derisk": dict(use_regime=True, use_voltarget=True, use_derisk=False),
}
res = {"meta": {"cost_roundtrip_pct": 0.30, "risk_pct": RISK_PCT, "max_concurrent": MAX_CONCURRENT,
                "max_pos_wt": MAX_POS_WT, "dd_derisk": DD_DERISK_LEVEL,
                "scope": "MEASURED, survivorship-biased daily universe, event-driven"},
       "configs": {}}
for name, cfg in configs.items():
    eq, turn = run_portfolio(**cfg)
    res["configs"][name] = {"full": metrics(eq),
                            **{s: metrics(eq, sp) for s, sp in SPLITS.items()}}
    print(f"  {name} done", flush=True)

OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

print("\n=== ADVANCED v5 ENSEMBLE — portfolio metrics ===")
print(f"{'config':<20}{'CAGR%':>7}{'maxDD%':>8}{'Calmar':>7}{'Sharpe':>7}{'Sortino':>8}  (period)")
for name, m in res["configs"].items():
    for per in ("full", "train", "val", "test"):
        r = m[per]
        if r:
            print(f"{(name if per=='full' else '  .'+per):<20}{r['cagr_pct']:>7}{r['max_dd_pct']:>8}"
                  f"{r['calmar']:>7}{r['sharpe']:>7}{r['sortino']:>8}  ({per})")
    print()
print("Reference — v4 production portfolio (from v4_vs_v5): CAGR 9.3% / maxDD -34% / Calmar 0.27")
print(f"wrote {OUT}")
