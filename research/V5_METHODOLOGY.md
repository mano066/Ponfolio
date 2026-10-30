# V5 Methodology & In-Sample Findings (2026-07-25)

This documents the isolated v5 research pipeline and its **first** pre-registered
study. It does **not** change production. It cleanly separates verified facts,
protocol, in-sample findings, and limitations, as the brief requires.

## 1. Honest scope (what v5 can and cannot be, given the data)

- **Daily only.** Verified daily OHLCV exists 2010→present
  (`research/data/nse_universe_2010_ohlcv.csv.gz`). See
  [V5_DATA_FEASIBILITY.md](V5_DATA_FEASIBILITY.md).
- **Intraday is excluded from any promotable result.** The intraday lake
  (`research/data/intraday_lake*`) contains only NIFTY/BANKNIFTY 1-minute data,
  **ends 2020-11-27**, and has no per-stock breadth. The v5 test window is
  2023–2026, which the intraday lake cannot cover, so an intraday-derived
  feature would break the walk-forward or leak. It is therefore not used here.
  See [intraday/VERIFIED_COVERAGE.md](intraday/VERIFIED_COVERAGE.md).
- **Survivorship bias, disclosed.** The universe is today's ~750 names pulled
  back to 2010 — identical to the v2/v3/v4 studies. Every number below is an
  apples-to-apples comparison against v4 on the *same* biased universe, **not**
  a bias-free absolute. A bias-free result needs the point-in-time universe
  rebuild (still pending; deliberately out of this patch).

## 2. Protocol (identical to the v4 study, so the comparison is fair)

- Selection base = production v3 (momentum tier → quality gate → score, top-5/day).
- Exit = **production v4**: no take-profit; stop 2.5×ATR evaluated on the daily
  **close**; exit at the next session's open if breached; 20-session time exit.
- Entry = T+1 open; skip gap-ups > 4% (production `max_entry_price` guard).
- Costs = 0.30% round trip.
- Splits: **TRAIN 2011–2019**, **VALIDATION 2020–2022**. **TEST 2023–2026 is
  frozen** and was not computed — no candidate earned a test look (see §4).
- Reproducible command:
  `backend/.venv/Scripts/python.exe research/scripts/v5/v5_selection_study.py`
  → writes `research/data/v5_selection_train_val.json`.

## 3. Harness validation

`baseline_v4` in this harness reproduces the V4_EXIT_STUDY finalist:

| period | this harness (exp%/tr, PF) | V4_EXIT_STUDY finalist |
|---|---|---|
| TRAIN | **+1.13, 1.33** | +1.11 |
| VAL | **+2.65, 1.65** | +2.66 |

The pipeline is therefore a faithful, isolated reproduction of v4 — the correct
baseline for any v5 candidate to beat.

## 4. Pre-registered candidate family + in-sample result

Only these selection gates were tested (no post-hoc additions), each applied on
top of the v3 top-5 with the v4 exit:

| candidate | TRAIN exp%/tr | TRAIN PF | VAL exp%/tr | VAL PF | verdict |
|---|--:|--:|--:|--:|---|
| **baseline_v4** | **1.130** | **1.33** | **2.654** | **1.65** | — |
| vol_contraction ≤0.40 | 0.855 | 1.26 | 1.956 | 1.52 | worse both |
| vol_contraction ≤0.25 | 0.802 | 1.25 | 1.922 | 1.53 | worse both |
| liquid_turn ≥ ₹5cr | 0.650 | 1.19 | 2.470 | 1.62 | worse both |
| coiled + liquid | 0.367 | 1.11 | 1.541 | 1.42 | worse both |

**Every candidate underperforms v4 on both TRAIN and VALIDATION.** The
volatility-contraction and liquidity filters remove exactly the higher-momentum,
higher-volatility, smaller names that generate v4's right-skewed winners —
consistent with V4_EXIT_STUDY's finding that momentum/breakout profit is
right-skewed and concentrated in a minority of explosive trades.

## 5. Decision

Per the promotion protocol, a candidate advances to the frozen test only if it
beats the baseline on train **and** validation. **None did**, so:

- **No v5 candidate was granted a look at the 2023–2026 test.** The test remains
  untouched.
- **v4 is retained.** This first v5 selection family is rejected.

This is a genuine negative result, reported as-is. It does not prove "no v5 is
possible" — only that these specific *daily selection* filters do not help on
this (biased) universe.

## 6. What a real v5 edge would require (honest next steps)

1. **A survivorship-free point-in-time universe** (delisted names, historical
   membership). The current bias flatters every engine equally, but a real edge
   test needs the unbiased universe. This is the highest-value unblock.
2. **Genuine per-stock intraday history covering the test window** (a paid
   vendor from ~2016+), to study *execution* (Phase 4.2) rather than selection —
   the one place intraday can add value the daily bar cannot.
3. New selection hypotheses beyond momentum/quality/vol/liquidity (e.g.
   sector-relative strength, earnings-drift windows), each pre-registered and
   run through this same harness.

Until (1) or (2) lands, v4 stays the production engine.
