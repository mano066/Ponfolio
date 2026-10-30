# Win-Rate Optimization Study — 10-Year Walk-Forward (2026-07-18)

**Goal tested:** can the swing scanner reach ~80% win rate, and does that make money?
**Method:** 892,509 signals captured from the production scorer over 2016–2026 (751 stocks).
2,700 parameter configs swept on TRAIN (2016–22), candidates confirmed on VALIDATION
(2023–24), one config per objective evaluated ONCE on untouched TEST (2025–26).
Entry T+1 open, 0.30% round-trip costs, top-5/day, liquidity-guarded.

## Result 1 — 80% win rate: ACHIEVED, but it loses money
Config: score≥55 · trend=Up · not counter-trend · ADX≥25 · **TP=0.5×ATR · SL=3.0×ATR** · hold 20d

| Period | Trades | Win rate | Expectancy/trade | Profit factor |
|---|--:|--:|--:|--:|
| Train 2016–22 | 6,647 | 82.6% | −0.26% | 0.85 |
| Validation 2023–24 | 2,455 | **85.3%** | −0.06% | 0.96 |
| **Test 2025–26 (untouched)** | 1,895 | **80.3%** | **−0.59%** | 0.70 |

The 80% number is real and survives out-of-sample. It is also a textbook
tight-target/wide-stop illusion: it wins ~+1.7% at a time and loses ~−8.4% at a time.
Four winners fund one loser; costs eat the rest. **Do not trade this.**

## Result 2 — the best-expectancy config ALSO failed the final test
Config: same filters, **TP=2.0×ATR, SL=3.0×ATR** (looked genuinely good in-sample):

| Period | Win rate | Expectancy/trade | PF |
|---|--:|--:|--:|
| Train | 56.9% | +0.40% | 1.11 |
| Validation | 59.9% | +0.72% | 1.22 |
| **Test (first look)** | 50.6% | **−0.82%** | 0.80 |

The in-sample edge did not generalize. 2025 was simply a bad year for the setup class
(the unmodified baseline also lost −0.39%/trade on the same period).

## Result 3 — what IS real
- The **quality filters add a stable win-rate lift**: trend=Up + ADX≥25 + no counter-trend
  raised win rate by +8–12pp over unfiltered in every period, including test
  (50.6% vs 42.0% baseline). The relative improvement is durable; the market's absolute
  profitability in the period is what varies.
- The scanner's true 10y baseline is **44.8% win, −0.026R/trade — near-breakeven**, not
  the +0.69R/71% suggested by the code comment (see `baseline_trades_10y.csv`).

## Verdict
**"80% win rate: demonstrated, not tradable. No swept configuration held positive
expectancy on the untouched test period."** Parameter tuning on this indicator set
cannot honestly deliver both high accuracy and profit; anyone selling that combination
is selling the geometry illusion above.

**Recommended actions** (in order of expected real-world value):
1. Keep score/exit params as-is; add the trend/ADX quality filters for pick quality
   (real, stable win-rate lift) with honest expectations about expectancy.
2. Position sizing + portfolio-level risk (fixed fractional risk/trade) — the proven
   lever for survivability that this study did not touch.
3. Regime gating (e.g. stand aside when Nifty < its 200-DMA) — 2018/2024/2025 losses
   cluster in weak-breadth regimes; worth a follow-up study.

## Files
- `data/signals_10y.csv.gz` — 892,509 signals with indicator state
- `data/sweep_train_results.csv` — all 2,700 train-period configs
- `data/baseline_trades_10y.csv` — 11,085 baseline trades
- `scripts/capture_signals.py`, `scripts/sweep_winrate.py`, `scripts/test_best_exp.py`,
  `scripts/backtest_baseline.py`
