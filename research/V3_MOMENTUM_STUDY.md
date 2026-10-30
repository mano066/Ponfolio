# V3 Momentum Study — 2010→2026 (2026-07-19)

**Question:** can evidence-backed momentum filters improve Swing v2's pick selection?

**Candidates** (literature + our study-1 findings, all day-T computable):
RS (63d return > Nifty 63d) · RS+ABS (RS and > 0) · VOLQ (volume ≤ 4× avg) ·
NEARHI (within 15% of 52-week high) · LOWVOL (below-median ATR%).
Literature basis: cross-sectional momentum robust in India (Nifty Alpha 50 /
Momentum 30); "enhanced momentum" (relative+absolute) outperforms plain momentum
in India (Emerald IJOEM 2025); 52-week-high effect (George & Hwang).

**Protocol:** base = v2 production selection (quality-first top-5, SL 1.5×ATR,
TP 2×ATR, hold 20d, T+1 open, 0.30% costs), 16y panel (1.26M signals). Singles
ranked on TRAIN 2011–19; best two on VALIDATION 2020–22 form the finalist combo
(chosen before test); ONE look at TEST 2023–26.

## Result — the finalist survived all three periods

Finalist (picked on validation): **NEARHI + RS+ABS** — within 15% of 52w high,
63d return > Nifty's and > 0.

| Period | v2 control (exp %/tr) | v2 + NEARHI+RSABS | Δ |
|---|--:|--:|--:|
| Train 2011–19 | +0.037 | **+0.089** | +0.05 |
| Validation 2020–22 | +0.541 | **+0.734** | +0.19 |
| **Test 2023–26 (one look)** | −0.262 | **−0.160** | **+0.10** |

Win rate on test 44.5% vs 43.7%; PF 0.95 vs 0.92. Same trade count (filter
narrows the pool; five picks still fill). Effect is modest (~₹10 per ₹10,000
per trade) but **directionally consistent everywhere, including unseen data** —
the same bar the v2 quality gate passed. LOWVOL had the best raw test number
(−0.064) but failed validation badly (+0.169 vs +0.541) and was therefore not
selectable; citing it post-hoc would be test-peeking.

## Deployment (Swing v3)
`scan_swing_picks` now ranks in tiers: **momentum-passing first** (quality-first
within), then the rest — the exact tested configuration with graceful fallback.
Nifty 63d benchmark fetched once per scan; if unavailable, the momentum test
degrades to absolute-strength only. Picks carry `v3_momentum` alongside
`quality_pick`. Scoring, threshold, exits unchanged.

## Honest expectations
v3 does not make the strategy a money machine: the test period stays negative
(−0.16%/trade) — it loses *less* in a weak tape and earns *more* in a good one.
Expectancy remains regime-driven; position sizing discipline unchanged.

## Files
- `scripts/v3_study.py` (reuses `data/signals_2010.csv.gz`, `data/nse_universe_2010_ohlcv.csv.gz`)
