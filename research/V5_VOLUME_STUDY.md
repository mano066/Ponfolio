# Does volume improve daily swing selection? — 2010-2026 stock lake (2026-07-25)

The daily per-stock lake **has volume** (2010–2026). This tests whether adding
volume confirmation improves the v5 shortlist, walk-forward. (The *index intraday*
data has no volume and is unaffected by this — different dataset.)

Protocol: top-5/day, next-open entry, gap>4% skip, v4 exit (no-TP, 2.5×ATR close,
20 sessions), 0.30% cost. TRAIN 2011–19 / VAL 2020–22 / TEST 2023–26.
**[MEASURED, survivorship-biased daily universe.]** Reproduce:
`research/scripts/multitimeframe/volume_study.py` → `research/data/volume_study.json`.

## Result — expectancy %/trade

| Variant | n | TRAIN | VAL | **TEST** | verdict |
|---|--:|--:|--:|--:|---|
| **S1 pullback base** | 13,246 | 1.62 | 2.04 | **2.13** | — |
| S1 + volume dry-up (≤0.9×) | 12,962 | 1.61 | 2.07 | 1.74 | ❌ worse test |
| S1 + volume surge (≥1.3×) | 11,034 | 1.29 | 1.84 | 1.40 | ❌ worse |
| **S2 breakout base** | 6,023 | 1.06 | 1.85 | **1.37** | — |
| S2 + volume expansion ≥1.5× | 4,264 | 1.09 | 1.43 | 1.56 | ~ mixed |
| **S2 + volume expansion ≥2.0×** | 3,126 | 1.01 | 1.67 | **2.12** | ✅ **better test** |
| **S6 momentum base** | 13,280 | 2.52 | 2.75 | **2.16** | — |
| S6 + OBV rising | 13,280 | 2.69 | 2.64 | 2.18 | ~ neutral (near no-op) |
| S6 + volume expansion ≥1.3× | 13,217 | 1.22 | 2.15 | 2.43 | ⚠️ better test, worse train (unstable) |

## Findings

1. **Volume does NOT uniformly help.** For **pullback (S1)** and **momentum (S6)**
   setups, volume filters mostly **hurt or are neutral** — filtering on volume
   strips out good trades. This matches the earlier ablation (a weak 1.2× filter
   hurt S2).

2. **Volume genuinely helps ONE setup type: breakouts.** Requiring **strong**
   volume expansion (**≥2× the 20-day average**) on an S2 breakout raises
   out-of-sample **TEST expectancy from 1.37 → 2.12** — textbook "real breakouts
   trade on volume." Note it **halves the trade count** (6,023 → 3,126) and
   slightly lowers validation, so it trades breadth for quality.

3. **The threshold matters:** a *weak* volume filter (≥1.2–1.5×) does little or
   hurts; only a *strong* one (≥2×) adds edge on breakouts. This is why the
   earlier S2 ablation (1.2×) showed volume hurting — the level was too low.

4. **OBV-rising is a near-no-op** in an uptrend (almost always true), so it adds
   nothing as a filter.

## Recommendation

- **Add strong-volume confirmation (≥2× avg) to the breakout strategy (S2) only.**
  It's the one place volume earns its keep out-of-sample.
- **Do not** add volume filters to pullback (S1) or momentum (S6) — keep them
  volume-free; volume only removes good trades there.
- Keep the existing **liquidity** use of volume (20-day turnover ≥ ₹1cr) for all
  strategies — that's about tradeability, not signal, and is unaffected.

## Caveats

- Survivorship-biased daily universe — absolute numbers overstated; the S2-volume
  *relative* improvement is the trustworthy part.
- The strong-volume S2 variant has only ~3,100 trades → higher variance; the test
  gain is encouraging but should be confirmed in forward paper mode.
- This is **daily** volume. Intraday volume (which could confirm intraday
  breakouts) is unavailable for stocks, so it remains untested.
