# Multi-Timeframe Swing-Trading Strategy Research (2026-07-25)

Research-only. **No live picks, no production changes, no paper-trading writes,
no commits.** Reproduce with
`backend/.venv/Scripts/python.exe research/scripts/multitimeframe/mtf_backtest.py`
→ `research/data/mtf_backtest_results.json` + `research/data/mtf_strategy_configs.json`.

Every number is labelled **[MEASURED]**, **[INFERRED]**, or **[UNVERIFIED]**.

---

## A. Data actually available

| Data | Status | Detail |
|---|---|---|
| Daily per-stock OHLCV | **[MEASURED]** | `nse_universe_2010_ohlcv.csv.gz`, 751 symbols, 2010-01-04→2026-07-17, **daily volume present**. 708 symbols have ≥260 sessions (used). |
| Universe membership | **[INFERRED — biased]** | Today's ~750 names pulled back to 2010 → **survivorship bias**. Literature (arXiv, cited in V4_EXIT_STUDY) puts Indian small/mid survivor-only inflation at ~4.9pp/yr — so treat absolute returns as **overstated**; only the *relative* strategy ranking is trustworthy. |
| Corporate actions | **[INFERRED]** | Yahoo adjusted_close only; ~13 known unadjusted split/CA rows documented, **not** repaired. Raw OHLC used (needed for intrabar stop/target logic). |
| NIFTY daily | **[MEASURED]** | `nifty50_daily_2010.csv`, used for regime + relative strength. |
| NIFTY/BANKNIFTY 1-min | **[MEASURED, index-only]** | `intraday_lake*`, ends **2020-11-27**, **no volume**. Cannot cover the 2023-2026 test window; indices only. |
| Per-stock intraday | **[NONE]** | Only a 7-day HDFCBANK Yahoo sample exists. **No per-stock intraday history for 2010-present or the test window.** |

**Consequence:** all seven strategies are backtested at **daily resolution**.
Every lower-timeframe (60m…1m) entry rule is **design-only [UNVERIFIED]** and
deferred to forward paper shadow mode. This report never claims an intraday
backtest.

## B. Multi-timeframe architecture

| Layer | Timeframe(s) | Role | Backtestable? |
|---|---|---|---|
| Market regime | NIFTY **daily** (60m/2h when available) | bull / sideways / high-vol / bear gate | **[MEASURED]** daily; intraday index ends 2020 |
| Stock trend | stock **daily** | primary swing direction — **controls everything** | **[MEASURED]** |
| Setup | **daily** (5h/2h/60m design-only) | pullback / breakout / RS / reclaim | daily **[MEASURED]**; higher-intraday **[UNVERIFIED]** |
| Entry timing | 60m/30m/15m | precise trigger | **[UNVERIFIED]** — shadow only |
| Execution | 10m/5m/1m | fill quality, spread | **[UNVERIFIED]** — shadow only |

The daily timeframe is authoritative: an invalid daily setup is never overridden
by a lower timeframe (enforced in code — daily gate evaluated first).

## C. Proposed strategy families

S1 Trend-Pullback · S2 Volatility-Contraction Breakout · S3 Relative-Strength
Continuation · S4 Failed-Breakdown Mean-Reversion · S5 Gap-and-Hold · S6
Multi-Timeframe Momentum Alignment · S7 Market-Regime Defensive (overlay).

## D/E. Exact rules, indicators & parameters

Full machine-readable rules per strategy: `research/data/mtf_strategy_configs.json`.
Common indicators: EMA20/50/200, RSI14 (Wilder), ATR14, Bollinger width (20,2),
20/55-day rolling highs, 20-day low, 20d turnover, ret 5/10/20/63/120d, MACD
(EMA12>EMA26). Common gates: liquidity (price≥₹5, 20d turnover≥₹1cr), gap guard
(skip T+1 open gap-ups >4%), safety layer (finite +target, current<target,
target>max-entry, ≥2% upside, ≥1.5 reward:risk). Holding 20 sessions (10 for
S4/S5). Signals fire only on **completed** daily candles; entry = **next-session
open**.

## F. Resampling validation

Session-anchored resampling (09:15 IST, no cross-session, open=first/high=max/
low=min/close=last/volume=sum, 5h→300m bar + flagged 75m remainder, completed-bar
gating, as-of leakage guards) is implemented in
`research/scripts/v5/mtf_analyzer.py` and **unit-tested** (8 tests pass) in
`research/scripts/v5/test_mtf_analyzer.py`. It is exercised for the (index-only)
intraday data and the live/forward layer — **not** used to fabricate per-stock
history that doesn't exist.

## G. Backtest methodology

Selection base = strategy signal on completed daily candle → top-5/day by a
strategy-specific rank. Entry = next-session open, skip gap>4%. Two exit engines
compared: **v4** (no-TP, 2.5×ATR close-stop, exit next open if breached, 20-session
time exit — the validated production exit) and a **target engine** (+3×ATR target /
−1.5×ATR stop, **stop-first** when both touched in a daily candle — conservative).
Costs 0.30% round trip + slippage sensitivity {0,5,10,20 bps}. No fills outside
the candle range; gap-through-stop fills at the gapped open, not the stop price.
Portfolio sim: equal-weight, ≤8 concurrent, cap/8 per position.

## H. Train / validation / test

TRAIN 2011-2019 · VALIDATION 2020-2022 · **TEST 2023-2026 (untouched — evaluated
once, never tuned on)**. No parameter was chosen using the test period.

## I. Results by strategy — [MEASURED, daily, biased universe]

Expectancy %/trade, v4 exit, 0.30% cost:

| strategy | n(all) | TRAIN | VAL | **TEST** | PF(val) | conc* |
|---|--:|--:|--:|--:|--:|--:|
| **S1 trend-pullback** | 12,430 | 1.85 | 2.05 | **2.06** | 1.44 | 0.03 |
| **S3 rs-continuation** | 11,805 | 2.02 | 2.73 | **1.73** | 1.46 | 0.03 |
| **S6 mtf-momentum** | 12,453 | 1.45 | 1.86 | **2.13** | 1.35 | 0.03 |
| **S2 vol-contraction** | 4,839 | 1.11 | 1.55 | **1.38** | 1.40 | 0.05 |
| S4 failed-breakdown | 9,327 | 0.06 | 0.21 | 0.15 | 1.08 | 0.03 |
| S5 gap-and-hold | 4,131 | −0.91 | −0.01 | 0.56 | 1.00 | 0.06 |
| S7 regime-defensive | 12,430 | 1.85 | 2.05 | 2.06 | 1.44 | 0.03 |

*conc = top-5 winners' share of gross profit; ~0.03–0.06 means the edge is
**broad, not a few outliers** (passes the concentration test). Win rates 43–49%
(edge is in the right-skewed winners, consistent with V4_EXIT_STUDY). S7 ≡ S1
because S1 already gates BULL-only.

Portfolio sim (full 2011-2026, v4 exit):

| strategy | CAGR% | maxDD% | Calmar | n taken |
|---|--:|--:|--:|--:|
| S1 | 9.2 | **−12.4** | **0.74** | 1,131 |
| S3 | 10.6 | −17.2 | 0.61 | 1,131 |
| S6 | 8.6 | −28.2 | 0.30 | 1,132 |
| S2 | 6.6 | −18.9 | 0.35 | 1,126 |
| S4 | 0.3 | −37.7 | 0.01 | 2,271 |
| S5 | n/a | blew up | n/a | 1,950 |

**Caveats [INFERRED]:** (1) CAGR is inflated by survivorship bias (~5pp/yr) — real
CAGR likely ~4–6%. (2) The portfolio Sharpe values in the JSON (3–3.7) are
**overstated** because the equity curve is marked only on exit days
(under-sampling volatility); use Calmar/maxDD for ranking, not Sharpe.

## J. Results by timeframe combination

Because per-stock intraday is unavailable, "timeframe combination" reduces to
**daily setup + (daily-proxy) higher-momentum confirmation**. The one testable
proxy is S6's multi-horizon alignment gate (ret5>0 & ret10>0 & ret20>0). Its
ablation (§N) shows it **subtracts** 0.70%/trade. **[MEASURED] conclusion: adding
a lower-timeframe-style confirmation layer did not improve selection; it only cut
trades.** True 1m–60m timing may still help *execution* (fills/slippage), which is
a separate, unbacktestable question.

## K. Regime-by-regime performance — [MEASURED]

Expectancy %/trade (v4, all periods):

| strategy | BULL | SIDEWAYS | HIGH-VOL | BEAR |
|---|--:|--:|--:|--:|
| S1 | 1.95 | — | — | — |
| S2 | 1.32 | **1.27** | — | — |
| S3 | 2.08 | — | — | — |
| S6 | 1.71 | — | — | — |
| S4 | 0.19 | −0.49 | — | — |
| S5 | −0.06 | −1.10 | — | — |

S1/S3/S6 are BULL-gated so have no non-bull trades ("—" = n<50). **S2 is the only
strategy with a positive edge outside pure bull markets** (bull + sideways) → best
regime diversifier. S4/S5 lose in sideways.

## L. Cost & slippage sensitivity — [MEASURED] (VAL expectancy)

| strategy | 0bps | 5 | 10 | 20 |
|---|--:|--:|--:|--:|
| S3 | 2.73 | 2.62 | 2.52 | 2.31 |
| S1 | 2.05 | 1.95 | 1.85 | 1.64 |
| S6 | 1.86 | 1.76 | 1.66 | 1.46 |
| S2 | 1.55 | 1.45 | 1.35 | 1.15 |
| S4 | 0.21 | 0.11 | 0.01 | **−0.19** |
| S5 | −0.01 | −0.11 | −0.21 | **−0.41** |

S1/S2/S3/S6 remain solidly positive at +20bps. **S4 turns negative; S5 negative
throughout** → both fail cost-resilience.

## M. Parameter-stability analysis

Stability judged by train→val→test consistency (no grid over-fit; a small,
pre-registered rule set was used, not a swept parameter surface):

- **S1: most stable** — 1.85 / 2.05 / 2.06 (monotone, no test collapse).
- **S6: stable**, even rises into test (1.45 / 1.86 / 2.13).
- **S2: stable**, lower magnitude (1.11 / 1.55 / 1.38).
- **S3: strong but degrades** val→test (2.73 → 1.73) — watch for regime dependence.
- S4/S5: unstable / weak.

## N. Ablation results — [MEASURED] (VAL expectancy Δ when component removed)

| strategy | −regime | −trend | −volume | −RS | −lower_tf |
|---|--:|--:|--:|--:|--:|
| S1 | +0.33 | **−0.17** | 0 | 0 | 0 |
| S2 | +0.22 | +0.03 | **+0.32** | 0 | 0 |
| S3 | +0.56 | **−0.26** | 0 | +0.23 | 0 |
| S4 | −0.23 | −0.04 | 0 | 0 | 0 |
| S6 | +0.60 | **−0.33** | 0 | 0 | **+0.70** |

Readings:
- **Daily trend filter is a genuine edge** (removing it hurts S1/S3/S6). Keep.
- **Lower-TF confirmation is NOT an edge** — removing S6's alignment gate *adds*
  +0.70%/trade. This directly answers the brief: the lower timeframe merely
  reduced trades; it did not improve results (on the daily proxy). **Drop it from
  selection; keep only as execution-timing research.**
- **S2's volume filter hurts** (+0.32 when removed) → drop the rel-volume gate.
- **S3's strict triple-horizon RS slightly hurts** (+0.23) → relax to single-horizon.
- **Regime filter raises drawdown-adjusted safety but lowers raw expectancy** on
  this biased universe (removing it adds expectancy *and* worse-regime tail risk)
  → keep it as a **risk** control, not an expectancy booster. For S4 the regime
  filter genuinely helps expectancy (+0.23 to keep it).

## O. Rejected strategies and reasons

- **S5 Gap-and-Hold — REJECT.** Negative/near-zero expectancy (val −0.01, PF 1.00),
  negative in both regimes, negative at all slippage, portfolio blew up. The
  strategy's real structure (hold above a *fraction of the gap*, confirmed on the
  first 30/60-min bar) **cannot be captured daily** — it needs intraday we lack.
  Revisit only with real per-stock intraday.
- **S4 Failed-Breakdown — REJECT (for now).** Marginal (val +0.21), turns negative
  at +20bps, −37.7% portfolio drawdown. Edge too thin to survive costs.
- **S7 Regime-Defensive — NOT a standalone strategy.** Identical to S1 because
  every long strategy here is already BULL-gated. Retained as a **portfolio-level
  overlay** (size 1.0 bull / 0.5 sideways / 0.25 high-vol / 0.0 bear), applied on
  top of a regime-agnostic base — not as its own signal.

## P. Shortlisted strategies

1. **S1 Trend-Pullback** — primary. Best stability, lowest drawdown (−12%), best
   Calmar (0.74), broad edge, cost-resilient.
2. **S3 RS-Continuation** — highest expectancy; relax the RS filter; watch
   val→test degradation and higher drawdown.
3. **S6 Daily-Momentum (lower-TF gate removed)** — stable, rising into test.
4. **S2 Vol-Contraction Breakout (volume filter removed)** — the regime
   diversifier (only one positive in sideways markets); fewer trades.

All four: positive in **validation and untouched test**, survive +20bps slippage,
low profit-concentration, simple/explainable rules.

## Q. Recommended paper-trading candidates

For **forward paper shadow mode** (not production), in priority order: **S1**,
then **S3 (relaxed RS)**, with **S2 (no-volume)** as a diversifier and the **S7
regime overlay** applied at the portfolio level. **S6** only if the daily-momentum
variant (no lower-TF gate) is used. The multi-timeframe *execution* layer
(`mtf_analyzer.py`) rides along in shadow mode **purely to measure whether
intraday timing improves fills** — it must not gate selection.

## R. Remaining risks & data limitations

1. **Survivorship bias** inflates every absolute figure (~5pp/yr) — unblock needs
   the point-in-time universe rebuild.
2. **No per-stock intraday** → lower-TF timing is unproven; S5/gap logic
   unbacktestable.
3. **Unadjusted corporate actions** (~13 rows) can distort individual trades.
4. **Portfolio Sharpe overstated** by exit-day-only equity marking (use Calmar/DD).
5. **Reported edge is gross of real-world impact** beyond flat cost+slippage
   (participation limits, partial fills) — modelled only crudely.
6. Sector-relative strength **not** computed (no sector map wired) — S3 uses
   NIFTY-relative only.

## S. Exact files that would need changes (later, on approval only)

- `backend/swing_trading.py` — add S1/S3/S2 signal generators behind a feature
  flag alongside the v4 scorer; reuse the existing `validate_recommendation`
  (finite-target invariant already in place) and paper-order path. **Not touched
  in this phase.**
- `backend/main.py` — optional flag to expose v5 candidates in shadow.
- New: `backend/swing_v5_signals.py` (isolated), `research/scripts/multitimeframe/`
  (already added, research-only).

## T. Implementation plan (proposed, pending approval)

1. **Approve shortlist & configs** (this document).
2. Wire S1 (+S3, S2) as **shadow-mode** signal generators behind a feature flag —
   record signals/fills against live prices, **no production surface change**.
3. Run a **forward paper-validation window** (e.g. 3–6 months) comparing v4 vs the
   v5 shortlist and vs the multi-timeframe execution overlay.
4. Only if a shortlisted strategy beats v4 forward **after costs** and holds its
   drawdown profile → promote behind a flag, v4 remains default.
5. In parallel, pursue the **survivorship-free universe rebuild** to re-run this
   study bias-free (the single highest-value data unblock).

**STOP — awaiting approval before any production integration.** No production
code, paper-trading data, or git state was modified in this phase.
