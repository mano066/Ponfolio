# V4 Exit Study — 2010→2026 (2026-07-19)

**Question:** after v2 (quality gate) and v3 (momentum tier) improved *which stocks*
get picked, what is the next real improvement? **Answer: the exit engine.** v1/v2/v3
all inherited the same exits — stop-loss 1.5×ATR (intraday touch), take-profit 2×ATR,
20-day time exit — and this study shows those exits, not the picks, are the biggest
leak in the system.

---

## 1. Why exits were the suspect (per-trade forensics, 19,137 trades)

Replaying production v3 selection over 16 years (`v4_diag.py`,
`data/v4_diag_trades.csv`) shows:

- **~48% of losers were up ≥ +1×ATR at some point before losing** (train 47.9%,
  val 50.2%, test 52.0%). The fixed 2×ATR target caps winners while the stop gives
  back open profit.
- **~20% of stop-outs later hit the take-profit anyway** in the same 20-day window
  (whipsaw) — the 1.5×ATR intraday-touch stop monetizes noise.
- Median favorable excursion (+7.4% in test) exceeds the ~+5% take-profit distance:
  the system regularly *had* bigger wins available and refused them.
- Entry-gap forensics: entries that gap up >4% at the open lose (−1.4%/trade in
  every period); gap-downs ≤−1% win (+1.0%). But the buckets in between are
  unstable across periods, so only the extreme is real.

## 2. What the literature says (2 independent web-research sweeps, full citations §7)

- Momentum/breakout profits are **right-skewed**: <7% of trades drive all cumulative
  profit (Wilcox & Crittenden, 18,000+ trades; Zarattini 2024 extension). A 1.33R
  take-profit cap is structurally fatal.
- Stop + **uncapped upside** doubled momentum Sharpe (Han-Zhou-Zhu, US 1926–2013).
- Stops only add expected return when returns have positive serial correlation;
  under noise/reversal every stop rule lowers expected return (Kaminski & Lo, JFM
  2014). India shows daily-frequency *reversal* except in liquid names — tight
  stops are mathematically the wrong tool here.
- Tight/trailing stops and breakeven moves rank mid-to-poor across huge sweeps
  (Davey 567,000 backtests; Alvarez: trailing ATR was his *worst* exit; wide
  end-of-day-evaluated stops his best). Partial profit-taking is arithmetic drag.
- Momentum profit concentrates **overnight** (Lou-Polk-Skouras JFE 2019; Indian
  replication 2024) → limit-at-prior-close entries are adversely selected for
  momentum: they fill only the picks that weakened.

## 3. Walk-forward study (same protocol as v2/v3 studies)

Base = production v3 selection (momentum tier → quality → score, top-5/day, T+1
open entry, 0.30% costs). 14 candidates: chandelier trails k∈{2.0…3.5}, breakeven,
chandelier+breakeven, TP 3×ATR, **no-TP (SL only)**, laggard time-stops, gap
filters, limit-at-close entry. Ranked on TRAIN 2011–19, finalist chosen on
VALIDATION 2020–22, one look at TEST 2023–26 (`scripts/v4_study.py`).

Protocol finalist: **no-TP + limit-at-close entry** → test **+0.63%/trade vs
−0.16 control** (PF 1.18 vs 0.95), positive in 3 of 4 test years.
The no-TP family dominated; chandelier trails were consistently *worse* than plain
no-TP (matching Alvarez/Davey); breakeven and laggard stops failed train — all
rejected without touching test.

## 4. Robustness + the literature's missing candidate (`scripts/v4_robust.py`)

Realistic fills (gap-through-stop filled at the open, not the stop price) and a
+0.20% slippage stress keep the finalist positive (test +0.54 and +0.34). The
literature's #1 indictment — the stop is too tight and intraday-triggered — was
then tested (disclosed second test look, within the already-chosen no-TP family):

| exit engine (realistic fills) | TRAIN exp%/tr | VAL | TEST | TEST win% | med hold |
|---|--:|--:|--:|--:|--:|
| control: SL1.5 intraday + TP2 + 20d | +0.06 | +0.77 | **−0.18** | 44.5% | 6d |
| no-TP, SL 1.5×ATR intraday | +0.25 | +1.81 | +0.58 | 36.5% | 14d |
| no-TP, SL 2.5×ATR intraday | +0.67 | +2.29 | +1.07 | 47.2% | 20d |
| **no-TP, SL 2.5×ATR close-evaluated** | **+1.11** | **+2.66** | **+1.51** | **50.1%** | 20d |
| no-TP, SL 3.0×ATR close-evaluated | +1.17 | +2.73 | +1.61 | 51.3% | 20d |

Monotonic in all three periods: remove the cap, loosen the stop, evaluate on close.
Win rate returns to ~50% because noise stop-outs disappear.

## 5. The honesty check that reframes everything (`scripts/v4_bench.py`)

Benchmarks with **no exit skill at all**:

| variant | TRAIN | VAL | TEST |
|---|--:|--:|--:|
| v3 picks, hold 20d, **no stop** | +1.24 | +2.84 | **+1.82** |
| v3 picks, no-TP SL2.5 close-eval | +1.11 | +2.66 | +1.51 |
| **RANDOM 5/day** from pool, hold 20d, no stop | +0.63 | +2.03 | **+1.52** |
| control exits (v3 production) | +0.06 | +0.77 | −0.18 |

Three conclusions:
1. **No exit rule beats doing nothing.** Every stop/target variant subtracts from
   the plain 20-day hold, in every period — exactly Kaminski-Lo. The old engine
   subtracts ~2%/trade; the loose close-evaluated stop subtracts ~0.2–0.3.
2. **Absolute levels are inflated.** Even random picks "earn" +1.5%/trade in the
   test window. The universe is today's index members (survivors) — Indian
   smallcap survivor-only backtests overstate returns ~4.9pp/yr (arXiv 2603.19380)
   — and 2023's rally dominates. The defensible claim is the *relative* ranking
   (which held in train, val, test, and the literature), **not** the absolute
   +1.5%/trade.
3. **Selection still matters**: v3 picks beat random by +0.61 train / +0.81 val /
   +0.30 test per trade — the v2/v3 work is real, it was just being cancelled by
   the exits.

Per-day-of-capital (holds lengthen 6d→20d, so per-trade numbers aren't comparable
alone): control −0.027%/day vs SL2.5-close-eval +0.079%/day — still ~3× better
even after adjusting for the longer capital lock-up.

## 6. v4 recommendation (not yet deployed)

**Keep v3 selection unchanged. Replace the exit engine:**
- **No take-profit.** Winners exit at the 20-day time exit (or stop).
- **Stop-loss 2.5×ATR below entry, evaluated on the daily close only**; exit at
  the next open if breached. (3.0×ATR scored marginally higher; 2.5 is chosen as
  the more conservative risk cap — the difference is inside the noise.)
- **20-day time exit** unchanged.
- **Skip entries that gap up >4% at the open** (small, consistent, and free).
- Optional, literature-strong, untested on our data: size positions ∝ 1/ATR%.

Honest expectations: win rate ~50% (similar to v2/v3 headline), but wins get much
bigger and stop-outs rarer-but-larger (−2.5×ATR ≈ −8 to −12% on a volatile name —
position sizing matters MORE, not less). Median hold rises to the full 20 days →
fewer trades per year per rupee, more overnight/event exposure per trade. Expect
long stretches where an open trade is red without being stopped; that is the
design, not a malfunction.

**Deliberately rejected for v4:** chandelier trailing stops (worse than no-TP
everywhere; net-negative in literature), breakeven stops (failed train; literature
mixed-to-negative), partial profit taking (arithmetic drag), laggard time-stops
(failed train), limit-at-close entry (protocol finalist included it, but it added
nothing on test — +0.63 vs +0.66 without — and the overnight-momentum literature
says it sheds the best entries; simplicity wins), broad earnings avoidance
(earnings announcement premium + Indian PEAD argue against).

**Disclosure of test looks:** test 2023–26 was consulted twice — once for the
protocol finalist (§3), once for the stop-width refinement inside the already
chosen no-TP family (§4), prompted by independent literature rather than test
results. The no-stop/random benchmarks (§5) also touch test but select nothing.

## 7. Sources (key)
- Kaminski & Lo, *When Do Stop-Loss Rules Stop Losses?* JFM 2014 (ssrn 968338)
- Wilcox & Crittenden, *Does Trend Following Work on Stocks?* 2005; Zarattini,
  Pagani & Wilcox 2024 (ssrn 5084316)
- Han, Zhou & Zhu, *Taming Momentum Crashes* (ssrn 2407199)
- Dai et al., *Risk Reduction Using Trailing Stop-Loss Rules*, IRF 2021
- Davey, 567,000-backtest exit study (kjtradingsystems.com); Alvarez Quant
  Trading stop-loss studies (alvarezquanttrading.com, Better System Trader #37)
- Lou, Polk & Skouras, *A Tug of War*, JFE 2019; Indian overnight-sentiment
  replication, Vision (Sage) 2024
- Barroso & Santa-Clara, *Momentum Has Its Moments*, JFE 2015 (vol scaling)
- Nifty200 Momentum 30 drawdown 2024–25 (Wright Research); NSE smallcap
  survivorship study (arXiv 2603.19380); SEBI/Budget cost changes (Zerodha)

## Files
- `scripts/v4_diag.py` + `data/v4_diag_trades.csv` — per-trade forensics
- `scripts/v4_study.py` — 14-candidate walk-forward study
- `scripts/v4_robust.py` — realistic fills, slippage stress, stop-width grid
- `scripts/v4_bench.py` — no-stop / random-pick drift benchmarks
