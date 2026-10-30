# V5 Multi-Timeframe Swing Strategy — categories & timeframe roles (2026-07-25)

A design spec for how v5 uses 1m → 1d together to pick the best swing trade,
with the data-honesty constraints from
[V5_DATA_FEASIBILITY.md](V5_DATA_FEASIBILITY.md) and
[intraday/VERIFIED_COVERAGE.md](intraday/VERIFIED_COVERAGE.md) built in.
Implementation: [scripts/v5/mtf_analyzer.py](scripts/v5/mtf_analyzer.py);
tests: [scripts/v5/test_mtf_analyzer.py](scripts/v5/test_mtf_analyzer.py).

## 0. The honest split (read this first)

A swing trade is a **daily thesis executed with an intraday trigger.** The two
halves have completely different data support:

| Half | Timeframes | Question | Data status |
|---|---|---|---|
| **Selection** (the edge) | 1d / weekly | *What* to buy | Backtestable on the 2010 daily lake |
| **Execution** (the timing) | 60m → 1m | *When / at what price* today | **Live/forward only** — no per-stock intraday history for 2010-present or the 2023-2026 test window |

So v5 does **not** claim a historical intraday backtest. The daily selection
edge is validated with walk-forward (see [V5_METHODOLOGY.md](V5_METHODOLOGY.md));
the intraday layers run **live, in forward paper-trading (shadow mode)** to
refine entry timing and fill quality. Anyone who "backtests" 1m entries across
the universe on data we don't have is manufacturing results.

## 1. Timeframe roles (top-down)

| Timeframe | Role | Signals used |
|---|---|---|
| **Weekly / Daily** | Thesis + selection | EMA20/50/200 stack, 52w-high proximity, 63d relative strength vs Nifty, volatility-contraction percentile, ADX, ATR (risk unit) |
| **2h / 60m** | Structure intact? | Intermediate trend (close>EMA20>EMA50), higher-low structure, swing S/R zones |
| **30m / 15m** | Trigger *today* | Pullback-to-VWAP reclaim, opening-range breakout, breakout-retest hold above VWAP |
| **5m / 1m** | Exact fill | VWAP side, momentum turn, relative volume, spread/liquidity sanity, precise stop placement |

Each lower timeframe **confirms**, it never overrides the daily thesis. If the
daily thesis is absent, no intraday pattern makes it a swing buy.

## 2. The four setup categories (new in v5)

Each category is a specific alignment across the stack. The analyzer classifies
top-down and the first match wins.

### A. `TREND_PULLBACK_CONTINUATION`
- **Daily:** uptrend (close>EMA20>EMA50), above EMA200.
- **60m:** trend intact (no lower-low break).
- **15m:** price pulled back and *reclaimed* VWAP/EMA20 (the trigger).
- **5m/1m:** momentum turns back up above VWAP for the fill.
- *Thesis:* buy the dip inside an established uptrend.

### B. `VOLATILITY_CONTRACTION_BREAKOUT`
- **Daily:** uptrend + volatility-contraction percentile ≤ 0.35 (a "coiled" base).
- **15m:** opening-range / base breakout holding above VWAP.
- **5m/1m:** volume expansion confirms the break (not a fake-out).
- *Thesis:* the coiled spring — expansion after contraction.

### C. `RELATIVE_STRENGTH_MOMENTUM`
- **Daily:** uptrend, within 15% of the 52-week high, 63d return **beats Nifty**.
- **60m:** trend intact.
- **15m:** breakout-retest holds above VWAP.
- *Thesis:* strongest names continue; ride relative strength.

### D. `SUPPORT_RECLAIM_REVERSAL`
- **Daily:** not yet in an uptrend but **above EMA200** (long-term intact).
- **60m:** basing / higher-low forming.
- **15m:** reclaim of a broken level, holding VWAP.
- *Thesis:* early turn off support — the only counter-trend-tolerant category,
  gated hard by EMA200 so it never buys a falling knife.

If none match → `NO_SETUP`.

## 3. Alignment score & actionability

A 0–100 **Multi-Timeframe Alignment (MTFA)** score, weighted toward the higher
(more reliable, less noisy) timeframes:

| Layer | Points |
|---|--:|
| Daily trend up | 30 |
| Above daily EMA200 | 10 |
| 60m/2h trend intact | 20 |
| 15m/30m holding above VWAP | 20 |
| 5m/1m momentum above VWAP | 20 |

A recommendation is **actionable only when a category matches AND MTFA ≥ 70** —
i.e. the daily thesis plus at least the higher-intraday structure agree. Below
70 it is `WAIT` (thesis present, waiting for intraday confirmation). This plugs
straight into the existing `validate_recommendation` states (READY_TO_BUY /
NEAR_BUY_ZONE / WAIT / MISSED_ENTRY / TARGET_ALREADY_REACHED / …).

## 4. Risk & entry (unchanged v4 risk unit)

- **Entry zone:** ±1% band around the completed-candle reference price, refined
  by the 15m trigger.
- **Stop:** 2.5×ATR below entry, evaluated on the daily close (production v4 unit
  — the exit study still governs exits; multi-timeframe changes *entry timing*,
  not the validated exit engine).
- **Invalidation:** daily close below the stop.

## 5. Leakage control (enforced in code, tested)

- Every read is **as-of** a timestamp. An intraday bar is visible only once its
  **close** time (open + interval) ≤ as_of — a lower timeframe can never see an
  unfinished higher-timeframe bar (`completed_intraday`).
- Daily uses **only completed sessions** (`completed_daily`): the current
  session is invisible until 15:30.
- Resampling is **session-anchored to 09:15** and never crosses a session; the
  5-hour bar yields one 300-min bar plus a flagged partial remainder
  (`resample_session_anchored`). All four properties have unit tests.

## 6. How this is deployed (per the promotion protocol)

1. Daily selection edge validated by walk-forward first (no intraday claim).
2. This multi-timeframe layer runs in **shadow / forward paper-trading** on live
   data — recording MTFA scores and fills against real prices going forward.
3. Only after a genuine forward paper-validation window (and if it beats the
   no-intraday daily baseline after costs) does intraday confirmation earn a
   place in production. Until then it is advisory timing, not a proven edge.
