"""V5 SELECTION STUDY — daily-only, isolated, does NOT touch production.

Question v5 asks (Phase 4.1 Selection): on top of the v3 momentum+quality
selection and the v4 exit engine (both frozen), does an additional *selection*
filter raise out-of-sample expectancy without shrinking the trade count to
noise?

Honest scope (see research/V5_DATA_FEASIBILITY.md and
research/intraday/VERIFIED_COVERAGE.md):
  * DAILY data only. The intraday lake is NIFTY/BANKNIFTY indices, ends
    2020-11-27, and has no per-stock breadth, so it CANNOT feed a promotable
    universe-scale selection feature and is deliberately excluded here.
  * Universe is today's ~750 names pulled back to 2010 -> SURVIVORSHIP-BIASED,
    identical to v2/v3/v4 studies. Any "v5 beats v4" result inherits that bias;
    it is an apples-to-apples comparison, not a bias-free absolute.

Protocol (identical bar to the v4 study, so the comparison is fair):
  * selection base = production v3 (momentum tier -> quality -> score, top-5/day)
  * exit = PRODUCTION v4: no take-profit, stop 2.5xATR evaluated on the DAILY
    CLOSE (exit next open if breached), 20-session time exit
  * entry = T+1 open, skip gap-ups > 4% (production max_entry guard)
  * costs = 0.30% round trip
  * candidates evaluated on TRAIN 2011-2019 and VALIDATION 2020-2022 ONLY.
    TEST 2023-2026 is FROZEN and intentionally not computed in this script.

Run:
  backend/.venv/Scripts/python.exe research/scripts/v5/v5_selection_study.py
Outputs:
  research/data/v5_selection_train_val.json  (machine-readable)
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

D = Path(__file__).resolve().parents[2] / "data"
OUT = D / "v5_selection_train_val.json"

# Frozen protocol constants (match v4 study).
COST = 0.30           # % round trip
TOP_N = 5             # picks per day
HMAX = 21             # forward window to materialize
HOLD = 20             # v4 time-exit sessions
SLX = 2.5             # v4 stop = 2.5 x ATR, evaluated on close
# TEST is frozen; this script must never read past VAL.
TRAIN = ("2011-01-01", "2019-12-31")
VAL = ("2020-01-01", "2022-12-31")
FROZEN_TEST_START = "2023-01-01"

print("loading prices...", flush=True)
px = pd.read_csv(
    D / "nse_universe_2010_ohlcv.csv.gz",
    usecols=["date", "symbol", "open", "high", "low", "close", "volume"],
    dtype={"symbol": "category", "open": "float32", "high": "float32",
           "low": "float32", "close": "float32", "volume": "float64"},
)
nif = pd.read_csv(D / "nifty50_daily_2010.csv").sort_values("date")
nifc = nif.set_index("date")["nifty_close"]
nif_r63 = (nifc / nifc.shift(63) - 1).to_dict()

print("building per-symbol arrays...", flush=True)
P: dict[str, dict] = {}
for sym, g in px.groupby("symbol", sort=False, observed=True):
    c = g["close"].to_numpy(float)
    v = g["volume"].to_numpy(float)
    n = len(c)
    r63 = np.full(n, np.nan)
    r63[63:] = c[63:] / c[:-63] - 1
    hi250 = pd.Series(c).rolling(250, min_periods=60).max().to_numpy()
    # Realized-volatility contraction: 20d return-vol vs its own trailing
    # 250d distribution. Low percentile == "coiled" base. Uses only data up
    # to and including day j (no lookahead — pct_rank of the trailing window).
    ret = pd.Series(c).pct_change()
    vol20 = ret.rolling(20, min_periods=20).std()
    vol_pctl = vol20.rolling(250, min_periods=120).apply(
        lambda w: (w[-1] >= w).mean(), raw=True
    ).to_numpy()
    # 20d average traded value (liquidity), in rupees.
    turn20 = pd.Series(c * v).rolling(20, min_periods=20).mean().to_numpy()
    P[str(sym)] = dict(
        o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
        l=g["low"].to_numpy(float), c=c,
        idx={dd: i for i, dd in enumerate(g["date"].to_numpy())},
        r63=r63, dhi=c / hi250 - 1, volp=vol_pctl, turn=turn20,
    )
del px

print("loading signals + production-v3 selection...", flush=True)
sig = pd.read_csv(D / "signals_2010.csv.gz")
sig = sig[sig["score"] >= 55].copy()
sig["atr_pct"] = sig["atr"] / sig["close"] * 100
sig["quality"] = (~sig["counter_trend"]) & (sig["trend"] == "Up") & (sig["adx"] >= 25)
syms_arr = sig["symbol"].astype(str).to_numpy()
dates_arr = sig["date"].to_numpy()


def feat(key: str) -> np.ndarray:
    out = np.full(len(sig), np.nan)
    for i, (s, dt) in enumerate(zip(syms_arr, dates_arr)):
        a = P.get(s)
        if a is None:
            continue
        j = a["idx"].get(dt)
        if j is not None:
            out[i] = a[key][j]
    return out


sig["r63"] = feat("r63")
sig["dhi"] = feat("dhi")
sig["volp"] = feat("volp")
sig["turn"] = feat("turn")
sig["nifr63"] = sig["date"].map(nif_r63)
sig["momentum"] = ((sig["dhi"] >= -0.15) & (sig["r63"] > sig["nifr63"])
                   & (sig["r63"] > 0)).fillna(False)

# Production v3 ranking, top-5/day. Same ordering the live scanner uses.
f = sig.sort_values(
    ["date", "momentum", "quality", "score"],
    ascending=[True, False, False, False],
).groupby("date").head(TOP_N)

print("materializing forward windows...", flush=True)
trades = []
for s, dt, ap, volp, turn in zip(
    f["symbol"].astype(str), f["date"], f["atr_pct"], f["volp"], f["turn"]
):
    a = P.get(s)
    j = a["idx"].get(dt) if a else None
    if j is None or j + 1 >= len(a["c"]) or not (ap > 0) or a["o"][j + 1] <= 0:
        continue
    e = float(a["o"][j + 1])
    cT = float(a["c"][j])
    m = min(HOLD, len(a["c"]) - (j + 1))
    if m < 1:
        continue
    trades.append(dict(
        date=dt, e=e, cT=cT, gap=(e / cT - 1) * 100 if cT > 0 else np.nan,
        atr=e * ap / 100,
        op=a["o"][j + 1:j + 1 + m + 1].astype(float),   # +1 so next-open exists
        lo=a["l"][j + 1:j + 1 + m].astype(float),
        hi=a["h"][j + 1:j + 1 + m].astype(float),
        cl=a["c"][j + 1:j + 1 + m].astype(float),
        m=m, volp=volp, turn=turn,
    ))
print(f"trades: {len(trades)}", flush=True)


def exit_v4(t) -> float:
    """Production v4 exit: no TP, stop 2.5xATR evaluated on the CLOSE; if a
    close breaches the stop, exit at the NEXT session's open (realistic — the
    signal is only known after that close). Otherwise time-exit at the last
    held close. A gap straight through the stop fills at the gapped open, not
    the stop price (no better-than-market fill)."""
    e = t["e"]
    sl = e - SLX * t["atr"]
    for k in range(t["m"]):
        if t["cl"][k] <= sl:                      # stop confirmed on this close
            nxt = k + 1
            if nxt < len(t["op"]):
                return float(t["op"][nxt])        # exit next open
            return float(t["cl"][k])              # last bar: no next open
    return float(t["cl"][t["m"] - 1])


# Selection candidates: each is a boolean gate applied ON TOP of the v3 top-5.
# Pre-registered family (only these are tested — no post-hoc additions).
CANDIDATES = {
    "baseline_v4": lambda t: True,
    "vol_contraction<=0.40": lambda t: np.isfinite(t["volp"]) and t["volp"] <= 0.40,
    "vol_contraction<=0.25": lambda t: np.isfinite(t["volp"]) and t["volp"] <= 0.25,
    "liquid_turn>=5cr": lambda t: np.isfinite(t["turn"]) and t["turn"] >= 5e7,
    "coiled+liquid": lambda t: (np.isfinite(t["volp"]) and t["volp"] <= 0.40
                                and np.isfinite(t["turn"]) and t["turn"] >= 5e7),
}


def run(period, gate) -> dict | None:
    lo, hi = period
    nets = []
    for t in trades:
        if not (lo <= t["date"] <= hi):
            continue
        if t["gap"] > 4.0:            # production max_entry gap guard
            continue
        if not gate(t):
            continue
        ex = exit_v4(t)
        nets.append((ex / t["e"] - 1) * 100 - COST)
    if len(nets) < 100:
        return None
    nets = np.array(nets)
    w = nets > 0
    return dict(
        n=int(len(nets)), win=round(float(w.mean() * 100), 2),
        exp=round(float(nets.mean()), 4),
        med=round(float(np.median(nets)), 4),
        pf=round(float(nets[w].sum() / max(1e-9, -nets[~w].sum())), 3),
    )


results = {"protocol": {
    "cost_pct": COST, "top_n": TOP_N, "hold_sessions": HOLD, "stop_atr": SLX,
    "exit": "no-TP, 2.5xATR close-evaluated (production v4)",
    "train": TRAIN, "val": VAL,
    "test_status": f"FROZEN (>= {FROZEN_TEST_START}, not computed here)",
    "universe": "today's ~750 names back to 2010 (survivorship-biased)",
    "intraday_used": False,
}, "train": {}, "val": {}}

for name, gate in CANDIDATES.items():
    results["train"][name] = run(TRAIN, gate)
    results["val"][name] = run(VAL, gate)


def show(title, block):
    print(f"\n--- {title} ---")
    print(f"{'candidate':<26}{'trades':>7}{'win%':>7}{'exp%/tr':>9}{'PF':>6}")
    for name in CANDIDATES:
        r = block[name]
        if r:
            print(f"{name:<26}{r['n']:>7}{r['win']:>7.1f}{r['exp']:>9.3f}{r['pf']:>6.2f}")
        else:
            print(f"{name:<26}{'<100 trades — n/a':>29}")


show("TRAIN 2011-2019", results["train"])
show("VAL 2020-2022", results["val"])

OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\nwrote {OUT}")
print("TEST 2023-2026 intentionally NOT evaluated — freeze parameters first.")
