# v4 (production) vs v5 multi-timeframe shortlist — head-to-head (2026-07-25)

Both engines run in **one identical harness**: same exit (v4 = no take-profit,
2.5×ATR close-stop, exit next open, 20-session time exit), same 0.30% round-trip
cost, same top-5/day, same gap>4% skip, same next-session-open entry, same
TRAIN/VAL/TEST windows. Reproduce:
`backend/.venv/Scripts/python.exe research/scripts/multitimeframe/v4_vs_v5_compare.py`
→ `research/data/v4_vs_v5_comparison.json`.

**Labels:** [MEASURED] = daily resolution, **survivorship-biased** current
~708-name universe, raw OHLC (~13 unadjusted CA rows). Lower-timeframe timing is
[UNVERIFIED] and excluded. v4 is the frozen incumbent, so reporting its TEST is
not tuning.

## Result — [MEASURED]

| Engine | n(all) | TRAIN | VAL | **TEST** | PF(val) | CAGR% | **maxDD%** | **Calmar** |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| **v4 production** (v3 momentum+quality) | 18,862 | 1.14 | 2.57 | **1.37** | 1.62 | 9.33 | **−34.0** | 0.27 |
| v5 S1 trend-pullback | 13,246 | 1.62 | 2.04 | **2.13** | 1.44 | 9.39 | **−12.4** | **0.76** |
| v5 S3 rs-continuation | 13,265 | 1.77 | 3.11 | **1.88** | 1.54 | 9.02 | −17.5 | 0.52 |
| v5 S6 daily-momentum | 13,280 | 2.52 | 2.75 | **2.16** | 1.46 | 9.55 | −18.7 | 0.51 |
| v5 S2 vol-contraction | 6,023 | 1.06 | 1.85 | **1.37** | 1.49 | 7.30 | −15.1 | 0.48 |

(expectancy = net %/trade after cost; CAGR/maxDD/Calmar from an equal-weight,
≤8-concurrent portfolio sim over 2011–2026.)

**v4 reproduction check:** this harness gives v4 = 1.14 / 2.57 / 1.37, matching
V4_EXIT_STUDY's finalist (1.11 / 2.66 / 1.51) — the baseline is faithfully
reproduced, so the comparison is fair.

## What the numbers say

1. **Out-of-sample (TEST 2023–2026), every v5 shortlist strategy meets or beats
   v4.** v4 = **1.37**; S6 = 2.16, S1 = 2.13, S3 = 1.88, S2 = 1.37. The two best
   (S1, S6) are **~55% higher** expectancy than v4 on the untouched test.

2. **The decisive difference is drawdown / risk-adjusted return.** v4 carries a
   **−34% max drawdown** (Calmar 0.27); the v5 strategies cut that to **−12% to
   −19%** (Calmar 0.48–**0.76**) at *similar* CAGR (~9%). S1 nearly **triples**
   v4's Calmar.

3. **Why:** v4 (v3 momentum selection) is **not regime-gated** — it keeps buying
   through bear/high-vol regimes (2020 crash, 2022), which is where the −34%
   drawdown comes from. The v5 shortlist is **BULL-gated**, so it sidesteps the
   worst regimes. This is the core structural improvement — better *risk*, not
   dramatically better raw return.

4. **v4's strength:** highest VAL profit factor (1.62) and more trades (18,862 vs
   ~13k) — it's less selective, which helped in the strong 2020–2022 momentum
   tape but at the cost of deep drawdowns.

## Promotion-criteria check (from the original brief)

| Criterion | v5 shortlist (S1/S6) | Status |
|---|---|---|
| Positive expectancy after all costs | Yes (survives +20bps, see main report §L) | ✅ [MEASURED] |
| Outperforms v4 on the final untouched period | Yes on TEST expectancy (2.1 vs 1.37) | ✅ [MEASURED] |
| Lower or comparable max drawdown | **Much lower** (−12/−19% vs −34%) | ✅ [MEASURED] |
| Sufficient independent trades | ~13k signals, 1.1k portfolio trades | ✅ |
| Stable across years/regimes | S1/S6 stable train→val→test; but BULL-only (untested in bear) | ⚠️ partial |
| Stable across liquidity/market-cap | not yet bucketed | ❓ not tested |
| No material lookahead / survivorship bias | lookahead controlled; **survivorship bias PRESENT** (biased universe) | ❌ bias remains |
| No dependence on unavailable data | daily-only; intraday excluded | ✅ |
| No after-hours / retrospective fills | next-open entry, safety layer enforced | ✅ |
| Reproducible from saved data + config | Yes (script + JSON configs) | ✅ |

## Verdict

**On this (biased, daily) evidence, the v5 shortlist — led by S1 and S6 — is a
genuine risk-adjusted improvement over v4:** equal-or-better out-of-sample test
expectancy at roughly **half to a third of v4's drawdown**, with a broad edge
(top-5 winners = ~3% of profit) that survives realistic costs.

**But it does NOT yet clear all promotion gates:**
- The **survivorship bias is unremoved** — it flatters every engine and cannot be
  netted out until the point-in-time universe is rebuilt. v4 and v5 share the
  bias, so the *relative* ranking holds, but absolute numbers are overstated.
- **No forward paper validation** has run.
- Liquidity/market-cap bucket stability and bear-regime behaviour are untested
  (v5 is BULL-gated, so it simply stands aside in bears — good for drawdown, but
  means it is *unproven*, not *proven safe*, in bear tapes).

## Recommendation

Do **not** replace v4 yet. Instead:
1. Deploy **S1 (primary) + S6/S3 (secondary)** in **shadow / forward paper mode**
   behind a feature flag — record signals and simulated fills against live prices
   alongside v4; **v4 stays the default**.
2. Require a **forward paper-validation window** where v5 beats v4 after costs and
   holds its lower-drawdown profile.
3. In parallel, **rebuild the survivorship-free universe** and re-run this exact
   comparison bias-free — the single result that would make the case decisive.
4. Promote a v5 strategy to default only after (2) and (3) both pass.

**No production code, paper-trading data, or git state was modified.** Awaiting
approval before any integration.
