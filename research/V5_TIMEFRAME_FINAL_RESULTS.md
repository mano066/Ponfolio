# Final result: v4 vs v5, and per-timeframe (15m/30m/1h/5h/1d) — 2026-07-25

You asked for a per-timeframe breakdown to see which timeframe beats the others.
Here is the honest, complete answer in two panels, because **two different data
realities apply.** Reproduce:
`research/scripts/multitimeframe/v4_vs_v5_compare.py` and
`research/scripts/multitimeframe/timeframe_edge_nifty.py`.

---

## Why there are two panels (the data reality, restated)

- **Stocks (the actual product):** only **daily** OHLCV exists per stock,
  2010-present. There is **NO per-stock 15m/30m/1h/5h history at all.** So a
  stock swing strategy can only be backtested at **1 day**. The "15m/30m/1h/5h"
  rows for stocks are **not computable — there is nothing to run them on.**
- **NIFTY index:** the *only* instrument with all timeframes (1-min, 2008-2020,
  no volume). It is the only place a per-timeframe comparison can actually run —
  but it is the **index, not a tradeable stock pick**, and it ends 2020.

---

## PANEL 1 — Stock universe (the product). [MEASURED, daily, survivorship-biased]

Net %/trade after cost, one identical harness; portfolio 2011-2026.

| Engine | Timeframe | TRAIN | VAL | **TEST** | CAGR | **maxDD** | **Calmar** |
|---|---|--:|--:|--:|--:|--:|--:|
| **v4 production** | 1 day | 1.14 | 2.57 | **1.37** | 9.3% | **−34%** | 0.27 |
| **v5 S1** | 1 day | 1.62 | 2.04 | **2.13** | 9.4% | **−12%** | **0.76** |
| **v5 S6** | 1 day | 2.52 | 2.75 | **2.16** | 9.6% | −19% | 0.51 |
| **v5 S3** | 1 day | 1.77 | 3.11 | **1.88** | 9.0% | −17% | 0.52 |
| v5 (any) | 15m / 30m / 1h / 5h | — | — | — | — | — | — |
| | | | | **NO PER-STOCK INTRADAY DATA — NOT COMPUTABLE** | | | |

**Panel-1 verdict:** among what is computable, **v5 daily (S1/S6) beats v4** —
same ~9% CAGR at roughly **⅓ the drawdown** (−12% vs −34%), and higher
out-of-sample test expectancy. The intraday rows cannot be filled.

---

## PANEL 2 — NIFTY index per-timeframe. [MEASURED, INDEX-ONLY, 2008-2020, no volume]

Identical swing-pullback signal run on each timeframe; metric = forward swing
return (held in calendar days, resolved on daily closes), net of 0.30% cost.
"ALWAYS-IN" = being long for the same horizon regardless of signal (the honest
benchmark).

| Timeframe | signal-days | 5-day exp% | 5-day win% | 5-day PF | 10-day exp% | 10-day PF |
|---|--:|--:|--:|--:|--:|--:|
| 15m | 1,942 | −0.31 | 46.5 | 0.75 | −0.08 | 0.95 |
| 30m | 1,653 | −0.38 | 44.9 | 0.70 | −0.15 | 0.90 |
| 60m | 1,431 | −0.36 | 44.3 | 0.70 | −0.15 | 0.90 |
| 2h | 1,271 | −0.27 | 45.3 | 0.76 | −0.08 | 0.94 |
| 5h | 1,098 | −0.31 | 44.9 | 0.74 | −0.22 | 0.85 |
| **1 day** | 937 | **−0.21** | 46.3 | **0.81** | **−0.07** | **0.95** |
| **ALWAYS-IN** | — | **−0.21** | 48.5 | 0.84 | **−0.04** | 0.97 |

**Panel-2 verdict — this is the direct answer to "which timeframe wins":**
- **No timeframe has a positive edge** on the index net of cost; all are negative.
- **Finer timeframes do NOT beat daily.** The daily (1d) signal is the *least
  bad* of the signals and 15m/30m/60m are *worse*.
- **No signal timeframe beats simply being ALWAYS-IN.** The timing added nothing;
  it only reduced trades and slightly hurt.

---

## Combined conclusion

1. **On stocks (what matters), only daily is testable — and v5-daily clearly
   beats v4** on drawdown/Calmar and out-of-sample expectancy.
2. **On the only data where all timeframes exist (NIFTY), finer timeframes lose to
   daily and to always-in.** There is **no measured evidence that 15m/30m/1h/5h
   analysis improves swing selection** — and two independent tests now agree:
   this index study, and the earlier daily-universe ablation (removing S6's
   lower-timeframe gate *raised* expectancy +0.70%/trade).
3. **The plausible remaining role for intraday is execution only** (better fills /
   slippage), which cannot be tested without per-stock intraday data and belongs
   in forward paper shadow mode, not selection.

**Recommendation stands:** keep v4 as default; take **v5-daily (S1 primary, S6/S3
secondary)** to forward paper shadow mode; do **not** build the strategy on
lower-timeframe selection — the evidence says it does not help. Pursue per-stock
intraday only to study execution, and rebuild the survivorship-free universe to
make the Panel-1 result bias-free.

*Caveats: index mean-reverts differently than individual stocks, so Panel 2 is
suggestive, not proof, for stocks — but it is the only intraday evidence that
exists, and it converges with the daily ablation. All Panel-1 absolute numbers
are survivorship-inflated.*
