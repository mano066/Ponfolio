# Regime Gate Study — 2010→2026 (2026-07-19)

**Question:** should Swing v2 stop (or shrink) trading when the overall market is weak
(Nifty below its moving averages)?

**Method:** 2.11M rows (751 stocks, 2010→2026, phantom dates removed), 1.26M signals
through the production scorer, 19,137 simulated v2 trades (quality-first top-5/day,
SL 1.5×ATR, TP 2×ATR, hold 20d, T+1 open entry, 0.30% costs). Gates computed through
day T only. Sweep on TRAIN 2011–19, confirm on VAL 2020–22, one look at TEST 2023–26.
Gates: Nifty > 200/150/100-DMA, golden cross (50>200), half-size below 200-DMA.

## Result: the regime gate FAILED — every variant, every period

| Period | v2 no gate (exp %/tr) | Best gate variant | Verdict |
|---|--:|--:|---|
| Train 2011–19 | +0.037 | +0.016 (golden) — all ≤ no-gate | gate hurts |
| Val 2020–22 | +0.541 | +0.408 (half-size) — all ≤ no-gate | gate hurts |
| Test 2023–26 | −0.262 | −0.262 (g200, identical) — none better | gate useless |

The 200-DMA gate skipped 22–29% of days and still delivered equal-or-worse expectancy
everywhere. Yearly detail shows why: the gate does dodge parts of bad years (2025:
−0.77 vs −1.17) but pays for it by missing early recoveries, which are the strategy's
best stretches (2011 gated: −2.15 vs −0.73; 2026 gated: −2.10 vs −0.14; 2020 gated:
+0.43 vs +0.79). Net effect ≈ zero or negative.

**Why (the useful insight):** v2's stock-level quality gate already embeds the regime —
in weak markets few stocks qualify as "uptrend + ADX≥25", so exposure shrinks
automatically. An index-level gate on top is redundant where it's right and late where
it's wrong (200-DMA signals turn AFTER the move).

## Secondary finding — the 16-year honest baseline of v2 picks
+0.04%/trade (2011–19), +0.54 (2020–22), −0.26 (2023–26): near-breakeven overall,
profitable mainly in strong tape. Consistent with the 10y study. No change to
expectations: v2 improves pick quality, not market physics. Survivorship bias inflates
early-decade numbers (universe = today's constituents).

## Decision
**Do not deploy any regime gate.** v2 stays as-is. Ideas remaining from the improvement
list, in order: relative-strength vs Nifty in the quality gate; volume-quality
refinement (demote >5× volume-spike picks); sector cap on the daily 5; ATR-based
position sizing in the paper trader.

## Files
- `data/nse_universe_2010_ohlcv.csv.gz` (2.11M rows) · `data/signals_2010.csv.gz`
  (1.26M signals) · `data/nifty50_daily_2010.csv`
- `scripts/download_2010.py` · `scripts/capture_2010.py` · `scripts/regime_study.py`
