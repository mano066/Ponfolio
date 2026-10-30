# Bias-free v4-vs-v5 — the survivorship-free universe REVERSES the verdict (2026-07-26)

Re-ran the comparison on the **survivorship-free** point-in-time universe
(`pit_universe_daily.parquet` — 7,460,971 rows, 4,763 ISINs incl. delisted names,
2010-01-04→2026-07-17; 3,831 ISINs with ≥260 sessions). Same harness, same v4
exit, same top-5/day, same walk-forward. Reproduce:
`research/scripts/v5/bias_free_compare.py` → `research/data/v5_biasfree_comparison.json`.

## Result — expectancy %/trade [MEASURED, survivorship-free, RAW prices]

| Engine | n | TRAIN | VAL | **TEST** | win%(test) |
|---|--:|--:|--:|--:|--:|
| **v4-style momentum** | 17,160 | 1.94 | 1.75 | **1.49** | 42.3 |
| v5 ensemble | 13,300 | 1.17 | 0.54 | **0.55** | 41.4 |

### The reversal

| | Biased universe (750 names) | **Survivorship-free universe** |
|---|--:|--:|
| v4 test expectancy | 1.37 | **1.49** |
| v5 test expectancy | ~2.0 | **0.55** |
| Winner | v5 | **v4** |

On the biased large-cap universe, v5 looked better. **On the full
survivorship-free universe, that edge disappears: a simple v4-style momentum
approach is stronger and more stable across all three periods (1.94 / 1.75 /
1.49), while the v5 ensemble collapses to ~0.55.**

## Why this happened

- v5's selectivity (regime gate + pullback/breakout setups) was tuned/observed on
  ~750 large caps. On the full universe of ~3,800 names (incl. small/mid caps and
  delisted names), that selectivity does **not** transfer — it picks a
  lower-expectancy subset than broad "near-52w-high + relative-strength" momentum.
- Survivorship bias was **not** flattering v4 relative to v5. If anything the
  broad universe *helps* momentum (more explosive small/mid movers). The bias had
  been hiding that the simpler momentum signal is the more robust one.

## This is exactly why the rebuild mattered

Had v5 been promoted on the biased backtest, we would have shipped the **weaker**
engine. The survivorship-free re-run — the gate we insisted on — overturned the
recommendation before any promotion. That is the discipline working as intended.

## Honest caveats (why this is PRELIMINARY, not final)

1. **RAW (unadjusted) prices.** Splits/bonuses show up as artificial ~50% gaps.
   This likely hurts **v5 more than v4-style**: v5's pullback (S1) and breakout
   (S2) setups can misread a split as a dip/move, while "near-52w-high momentum"
   rarely selects a stock on its raw split day. So v5's true number may be
   somewhat better than 0.55 — **corporate-action adjustment is required before a
   final verdict.**
2. **v4-style here is a proxy** (trend + near-52w-high + RS), not the exact
   production v4 scorer.
3. Different universe composition than the biased table → not a same-stocks
   comparison; it's a *regime-of-universe* comparison.
4. Win rates ~42% (both) — edge is in the right-skewed winners, as expected.

## FINAL — corporate-action adjusted (the confound removed)

Re-ran with a split/bonus back-adjustment (1,646 CA-sized discontinuities
corrected, applied equally to both engines) —
`research/scripts/v5/bias_free_ca_adjust.py` →
`research/data/v5_biasfree_ca_comparison.json`:

| Engine | | TRAIN | VAL | **TEST** |
|---|---|--:|--:|--:|
| v4-style momentum | raw | 1.94 | 1.75 | 1.49 |
| v4-style momentum | **CA-adj** | 2.16 | 2.58 | **1.81** |
| v5 ensemble | raw | 1.17 | 0.54 | 0.55 |
| v5 ensemble | **CA-adj** | 1.26 | 1.55 | **0.92** |

- CA adjustment helped **both** engines, and helped **v5 more** (test 0.55 → 0.92)
  — confirming split noise was disproportionately hurting v5's dip/breakout
  setups, exactly as hypothesized.
- **But it does not rescue v5.** Even fully split-adjusted, **v4-style momentum
  still beats the v5 ensemble on all three periods (test 1.81 vs 0.92 — roughly
  2×), stably.** The confound is removed and the verdict is unchanged.

## Verdict (definitive on available evidence)

- **v4 wins on the survivorship-free, CA-adjusted universe.** v5's apparent edge
  was a survivorship-bias artifact of the 750-large-cap universe; it does not
  survive on the true universe even after correcting split noise.
- **Do NOT promote v5. Keep v4 as the default and the production engine.**
- **v5 is closed out as a promotion candidate** on current evidence. The v5
  selectable/beta engine remains shipped (behind its toggle) for transparency and
  any future study, but nothing about the product default should change.
- The lasting deliverable from this whole effort is the **survivorship-free
  universe + CA-adjustment pipeline** — it turned a biased "promote v5" into a
  correct "keep v4," and it's reusable for validating any future engine bias-free.

**No production behavior changed by this analysis.** v4 remains default; research
is research-only.
