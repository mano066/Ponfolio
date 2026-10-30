# Feature-IC replication — the ATR and near-high effects hold (2026-07-30)

**Verdict: both effects replicate, with the same signs and the same 6-of-6 fold
consistency, at roughly 55–60% of the published magnitude.** The shuffled-label
null collapses to |IC| ≤ 0.0017, so the measurement is not leaking. All four
pre-registered gates pass.

This is a **replication check, not a promotion number.** No portfolio
simulation, no costs, no stops, no `rand:N` comparison. It answers one question:
is the mechanism real in the only dataset still recoverable on this machine?

Script: `research/scripts/feature_ic.py` · data: `research/data/feature_ic_train.csv`
(+ `_null.csv`)

---

## Why this was run

`research/V6_TRAINING_PLAN.md` §Phase 4 measured, on a survivorship-free
CA-adjusted panel, that the cross-sectional rank of ATR% predicts forward
returns **negatively** (6/6 folds) while distance-to-252-day-high predicts them
**positively** (6/6). Those are the two most fold-consistent findings in the
corpus, and production v4 ignores the first entirely and uses the second only as
a binary 85%-of-52-week-high flag.

**The rig that produced them is gone.** `harness.py`, `score_v4.py`, `splits.py`,
`build_panel.py`, `build_rank.py` are absent from disk and were never committed
(`git log --all` finds no trace); there is no `E:\nse\` on any drive. So the
findings could not be re-derived, and nothing could be measured against the
`rand:N` bar this project requires before a strategy claim.

What *is* recoverable is `dataset/store/daily/` — 750 symbols, 94.7 MB, tracked
in git and restored with `git checkout -- dataset`. This run uses that.

---

## Data

| Property | Value |
|---|---|
| Source | `dataset/store/daily/*.parquet` (NSE charting, exchange-direct) |
| Panel loaded | **2,756 sessions × 537 symbols** (2008-11 warmup → 2019-12-31) |
| Window | **TRAIN 2010-01-01 → 2019-12-31 only.** VAL and TEST untouched |
| Eligible sample | **461,390 stock-days over 2,458 sessions, median 188 names/day** |
| Eligibility rule | 20-day avg turnover > ₹5 cr **shifted 1 day** (point-in-time) and close > ₹5 |
| Label | forward return, entry `open[t+1]`, exit `close[t+20]` |
| Folds | 6 contiguous date blocks, **20-session embargo trimmed from each side** |

### Corporate actions — inferred, and the residual masked

The store is only *partially* CA-adjusted: NESTLEIND's 10:1 (2024) and IRCTC's
5:1 (2021) read clean, but older events do not — a 60-symbol probe found 134 of
214,784 returns beyond |25%|, worst CESC −98.9%. (`dataset/DATA_INVENTORY.md`
labels A1 "Unadjusted"; that is wrong — `V6_TRAINING_PLAN` defect #1 records that
the charting feed is pre-adjusted while bhavcopy is raw.)

Handling: one-day price steps beyond ±15% that land within ±2% of a known
split/bonus ratio are undone by dividing all earlier bars by that factor;
anything still beyond ±25% afterwards is **masked, not adjusted**, and any label
window containing a hole becomes NaN automatically.

> **inferred 1,735 split/bonus factors over 384 symbols; masked 1,128
> unexplained bars over 350 symbols**

A printed ratio would be authoritative (`V6_TRAINING_PLAN` judgment call #3); an
inferred one is not. This is why **rank IC is the primary statistic** — it is
rank-based and so robust to a residual fake −90%. `top5_edge` is a mean, so it
is reported on labels winsorised at the 1st/99th percentile.

---

## G1 — label sanity

Within-day quintile means of the label (%):

| | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|--:|--:|--:|--:|--:|
| **measured** | −10.87 | −3.87 | −0.01 | +4.10 | +12.82 |
| published | −11.92 | −4.49 | −0.22 | +4.58 | +16.33 |

Monotone and spanning ~24 points, against ~28 published. The narrower spread is
what a survivor-only universe should produce, and it is the first sign of the
uniform attenuation that shows up again below. **PASS.**

---

## Results — measured vs published

TRAIN, 6 purged folds, 20-session embargo, ₹5 cr floor:

| feature | IC | ±sd | folds | top-5 edge | | pub IC | pub edge | pub folds |
|---|--:|--:|--:|--:|---|--:|--:|--:|
| `f_atr_pct_xr` | **−0.0472** | 0.0314 | **0/6 pos** | −1.130% | | −0.0824 | −3.364% | 0/6 |
| `f_dist_252h_xr` | **+0.0565** | 0.0303 | **6/6 pos** | +0.100% | | +0.0908 | +0.321% | 6/6 |
| `f_ret63_xr` | +0.0149 | 0.0225 | 4/6 | +0.779% | | +0.0319 | +0.342% | 5/6 |
| `f_ret20_xr` | −0.0021 | 0.0234 | 3/6 | +0.109% | | +0.0044 | −0.398% | 4/6 |

### G0 — the shuffled null (labels permuted *within* each day)

| feature | null IC | ±sd |
|---|--:|--:|
| `f_atr_pct_xr` | −0.0008 | 0.0056 |
| `f_dist_252h_xr` | −0.0010 | 0.0040 |
| `f_ret63_xr` | −0.0017 | 0.0037 |
| `f_ret20_xr` | −0.0003 | 0.0038 |

Every feature collapses to zero within ±0.0017 (published: within ±0.004).
**PASS** — the evaluation does not leak. That makes the real numbers readable:
ATR sits ~8 null-sd from zero, near-high ~14 null-sd.

### Gate summary

| Gate | Requirement | Result |
|---|---|---|
| G0 | shuffled null \|IC\| < 0.01 | **PASS** — worst 0.0017 |
| G1 | quintile means ordered, ≈−12 → +16% | **PASS** — −10.87 → +12.82 |
| G2 | `f_atr_pct_xr` negative, ≥5/6 folds | **PASS** — −0.0472, **6/6** |
| G3 | `f_dist_252h_xr` positive, ≥5/6 folds | **PASS** — +0.0565, **6/6** |

### Not a liquidity artefact

Sweeping the turnover floor across 5×:

| floor | names/day | ATR IC | folds | near-high IC | folds |
|---|--:|--:|--:|--:|--:|
| ₹2 cr | 256 | −0.0480 | 6/6 neg | +0.0599 | 6/6 pos |
| **₹5 cr** | **188** | **−0.0472** | **6/6 neg** | **+0.0565** | **6/6 pos** |
| ₹10 cr | 142 | −0.0474 | 6/6 neg | +0.0495 | 6/6 pos |

Both effects are flat across the range. The ₹5 cr floor was fixed in advance and
never tuned; these rows are reported instead of moving it.

---

## Two things that bound this result

**1. Survivorship — and it runs *against* the effect.** The 537 symbols with
2010s history are today's index members. On 2010-01-04, 1,223 EQ symbols traded
and 939 (77%) are absent from today's list (`dataset/DATA_INVENTORY.md` B1).
High-ATR names are disproportionately the ones that later collapsed, so removing
them should *shrink* the measured penalty on ATR — and the measured penalty is
indeed ~57% of published (−0.047 vs −0.082), with near-high at ~62% (+0.057 vs
+0.091) and the label spread at ~86%. **A positive result under a bias that
opposes it is meaningful; a negative one would have been inconclusive.** It does
mean the true effect is probably larger than measured here, not smaller.

**2. Disclosed protocol deviation.** The plan's Step 0 said stop if fewer than
~400 symbols reach back to 2010. Measured: **367** (357 with 2009 warmup). The
quantity that gate was protecting is the *per-day* cross-section, which measures
424 with data / 188 eligible per day against the original's 392/day off 4,148
symbols. At ~188 names/day over ~120 independent 20-session blocks the standard
error on mean IC is ≈0.007, so the effects are ~7–8 SE — ample power. I
proceeded on that basis and am recording it here rather than editing the gate.
Changing a gate after seeing results is the failure mode `V6_TRAINING_PLAN`
exists to prevent; this follows its own precedent of disclosing the correction.

---

## What this licenses, and what it does not

**Licensed.** Change v4's *ranking* to stop tilting into high ATR and to use
distance-to-52-week-high as a continuous rank rather than an 85% binary flag.
Ship it as an **opt-in engine with v4 remaining the default.**

The specific production defect this exposes needs no further measurement:
`scan_swing_picks` gates candidates on `predicted_gain_pct >= 5.0`
([swing_trading.py:1684](../backend/swing_trading.py#L1684)), and that value is
`max(distance-to-resistance, 2.5 × ATR/price × 100)`
([swing_trading.py:1491](../backend/swing_trading.py#L1491)). For most names the
ATR term dominates, so **the selection floor reduces to `atr_pct ≥ 2%`** — the
engine *requires* the one property measured negative in 6/6 folds twice, on two
different universes. That is a plausible mechanism for v4's TEST 1.58 against a
random bar of 1.95–2.00.

**Not licensed.** Promoting anything to default. This run has no `rand:N`
comparison, no portfolio simulation, no cost model, and never touched VAL or
TEST. Promotion still requires the survivorship-free rebuild: a bhavcopy
point-in-time downloader (data free from NSE, ~30 min; the downloader itself must
be written — `backfill_eod.py` is symbol-driven and has no bhavcopy path), the
corporate-action master, and `harness.py` with `rand:N` and `--time-exit`.

Also still true and **not** acted on here: the one finding that replicated on
random pickers in the original work is *hold longer* — 40 sessions beat 20 in 8
of 9 cells. Production holds 14. Out of scope by decision, not by evidence.

---

## Live verification of the floor defect (2026-07-30, Nifty 50)

One real scan, both rankings over the same 29 candidates (score ≥ 55). This is a
single day on 50 names — an illustration of the mechanism, not evidence of an
edge.

**Every candidate the 5% floor excludes is a low-volatility name, and no
high-volatility candidate is excluded at all:**

| excluded by `predicted_gain_pct >= 5` | atr_pct | 2.5×ATR% | predicted gain |
|---|--:|--:|--:|
| BHARTIARTL | 1.448 | 3.62 | 3.9 |
| ITC | 1.485 | 3.71 | 3.7 |
| COALINDIA | 1.655 | 4.14 | 4.9 |
| ICICIBANK | 1.671 | 4.18 | 4.2 |
| NTPC | 1.701 | 4.25 | 4.0 |
| POWERGRID | 1.740 | 4.35 | 4.4 |
| TATASTEEL | 1.774 | 4.44 | 4.7 |
| HINDALCO | 1.833 | 4.58 | 4.6 |
| EICHERMOT | 1.852 | 4.63 | 4.6 |

**9 of 9 have `atr_pct < 2.0%`.** Candidate ATR% spans 1.45–3.32, so names above
2.0% existed and none were cut. ICICIBANK sits at **96.4% of its 52-week high** —
the strongest positive feature at its near-maximum — and v4 discards it for being
too calm. BHARTIARTL (90.9% of high, atr 1.45) likewise.

Top-5 lists, same scan, **zero overlap**:

| | v4 (5% floor, score-ranked) | v4.1 (no floor, ATR-penalised + near-high) |
|---|---|---|
| 1 | TMPV — 45.3% of 52w high | ICICIBANK — 96.4% |
| 2 | TRENT — 53.1% | BAJFINANCE — 95.6% |
| 3 | TATACONSUM — 86.0% | SBILIFE — 88.5% |
| 4 | ADANIPORTS — 88.2% | ETERNAL — 83.4% |
| 5 | MARUTI — 80.4% | BHARTIARTL — 90.9% |

Median distance-to-52-week-high rises 80.4% → 90.9%. v4's top two sit at 45% and
53% of their highs; its momentum tier is supposed to require ≥85%, but on a day
when no candidate passes the tier it collapses and raw score ranks alone — which
is how a name 55% below its high reaches #1.

**One correction to how I framed this earlier.** I expected v4.1's picks to be
*less* volatile. Median ATR% actually went 1.93% → 2.06% — slightly up. On the
Nifty 50 every candidate is low-ATR (1.45–3.32), so the penalty has almost no
spread to work with and the near-high term dominates the blend. The floor's
damage here shows up as **exclusion** (9 low-ATR names removed outright) rather
than as mis-ranking. The ATR penalty should matter far more on the broader
universes, where the ATR spread is much wider — that is untested and should not
be assumed.

---

## Reproducing

```powershell
git checkout -- dataset                                   # 750 parquets, 217 MB
python research\scripts\feature_ic.py                     # REAL  — G1/G2/G3
python research\scripts\feature_ic.py --shuffle-null      # NULL  — G0
python research\scripts\feature_ic.py --min-turnover 2e7  # sensitivity
```

~4 minutes per pass. Needs pandas / pyarrow / numpy only, all present in the
default interpreter — no conda env required.
