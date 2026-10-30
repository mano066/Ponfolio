# Training plan — v4, v4-advanced, v5, and the recommended v6 (2026-07-28)

Scope: use everything now on disk (`E:\nse`, 12.5 GB) to produce a defensible
engine. Written against measured state, not intentions. Every number cited below
is either from a log in `dataset/store/logs/`, a file in `research/data/`, or a
probe run while writing this document (marked **[probed]**).

---

## 0. The framing that decides everything

"Train v4 / v5" is not one job, because **v4 and v5 are not learned models.**

| Engine | What it actually is | Can it be "trained"? |
|---|---|---|
| **v4** | Deterministic scorer (`swing_v4_hist._analyze_arrays`) + a fixed gate: `quality = not counter_trend & trend=="Up" & adx>=25`, `momentum = dhi>=-0.15 & r63>nifty_r63 & r63>0`, rank by (momentum, quality, score), top-5/day | **No.** It is the frozen incumbent. It gets *re-measured*, never fitted. Fitting it destroys its status as a baseline. |
| **v4-advanced** | v4 selection + portfolio overlay: 1/ATR vol-target sizing, drawdown brake, gap tilt, stop width | **Yes — parameter fitting.** ~7 continuous parameters, fitted by walk-forward search. Not gradient descent. |
| **v5** | Rule ensemble S1/S3/S6/S2 + regime gate + vol targeting | **Yes — parameter fitting**, plus (new) timeframe selection now that 8.4 y of 1-minute data exists. |
| **v6 (proposed)** | A *learned* model that replaces the ranking step and/or sizes positions | **Yes — real ML training.** This is the only place an AI model belongs. |

So the plan has two distinct machines: a **walk-forward parameter search** for
v4-advanced/v5, and a **supervised learning pipeline** for v6. Conflating them is
how the previous v5 effort produced a verdict that reversed twice.

### The two-track data rule (the single most important decision here)

The 1-minute data covers **764 symbols, all currently listed. Zero delisted
names.** The bhavcopy panel covers **4,148 symbols including 3,398 that are not
in today's index**. `V5_BIASFREE_RESULT.md` records what happens when you ignore
that: on the 750-name biased universe v5 beat v4 (2.0 vs 1.37); on the
survivorship-free universe v4 beat v5 (1.81 vs 0.92 CA-adjusted). **The bias did
not flatter v4 — it hid that the simpler engine was the robust one.** Promoting
on the biased number would have shipped the weaker engine.

Therefore:

| Track | Data | Rows | Symbols | Span | Allowed use |
|---|---|--:|--:|---|---|
| **A — bias-free** | `bhavcopy_eod.parquet` + `universe_by_date.parquet` | 7,992,915 | 4,148 (incl. delisted) | 2010-01-04 → 2026-07 | **All selection decisions and all promotion verdicts.** Daily only. |
| **B — biased, high-resolution** | `store/intraday/1m/` (764 syms), `dl/features.parquet` | 1,033,720 sessions | 526 with ≥5 y **[probed]** | 2018-01 → 2026-05 | **Overlay only.** Sizing tilts, entry timing, meta-labels — measured as an *increment on a trade set Track A already chose*, so the bias cancels in the difference. |

**Track B may never define a universe or produce a standalone promotion number.**
That rule is what the previous two reversals bought us.

---

## 1. Readiness — verified, not assumed

**Hardware [probed]:** RTX PRO 6000 Blackwell, 97,887 MiB VRAM · 64 logical cores
· 128 GB RAM · 158 GB free on `E:`. This is heavily over-provisioned for the
problem (see §5.1 on effective sample size). The GPU's value here is **ensembling
and CV fold parallelism, not model size.**

**Software [probed]** (`conda env blackwell`): torch 2.9.1+cu128 (CUDA available),
xgboost 3.2.0, sklearn 1.7.2, pandas 2.3.3, pyarrow 22, numpy 2.2.6, scipy 1.15.3.
**Missing: lightgbm, catboost.** Install lightgbm — its `lambdarank` objective is
the core of the recommended model and it is faster than XGBoost on 64 CPU cores
for this data shape:

```powershell
conda run -n blackwell pip install lightgbm
```

**Data facts probed while writing this:**

| Check | Result | Consequence |
|---|---|---|
| Is the Kaggle 1m store split-adjusted? | **Yes.** NESTLEIND 10:1 (2024-01-05) → −1.73%, not −90%. IRCTC 5:1 (2021-10-29) → −8.67%, not −80%. | Do **not** apply `price_factors.parquet` to it — same double-adjust trap `adjust.py` documents for the charting feed (it broke 272 of 720 symbols). |
| Are demergers adjusted in the 1m store? | Unverified; assume **no**, as in `store/daily`. | `dl_features.py` does **not** call `adjust.flag_events()`, while `harness.py` does. The 44 empirical demerger factors are unhandled in the DL features. Fix in Phase 0. |
| Large-cap 1m depth | WIPRO has **no** `2019-03.parquet`; ITC has **no** `2024-01.parquet`. | Nifty-weighted large caps are effectively absent. Any 1m model is trained on **mid/small caps**. Must be stated in every result. |
| 1m depth distribution | 764 symbols; **526 ≥ 60 months**, 160 at 13–60, 81 at 4–12; max 101 months (= 2018-01 → 2026-05 exactly) | Usable deep panel ≈ 526 symbols × ~2,121 sessions. |

---

## 1b. Phase 0 — BUILT AND VALIDATED (2026-07-29)

Track A is done and passes **32 of 32 data-integrity gates**
(`python validate_panel.py`). New modules:

| File | Role |
|---|---|
| `dataset/splits.py` | the frozen TRAIN/VAL/TEST windows + embargo, imported everywhere |
| `dataset/company.py` | the stable company key (`co`) — see below |
| `dataset/bhav_factors.py` | 1,309 corporate-action factors, each verified against prices |
| `dataset/build_panel.py` | the adjusted panel, PIT eligibility, coverage, 1m depth |
| `dataset/validate_panel.py` | the 32 gates. Run after ANY change to the above |

| Output (`E:\nse\panel\`) | Contents |
|---|---|
| `daily_pit_adj.parquet` | **6,563,092 rows · 3,150 companies · 2010-01-04 → 2026-07-27** (242 MB) |
| `pit_eligible.parquet` | 1,940,450 (date, company) rows; median **394** names/day; 2,015 companies ever eligible |
| `bhav_factors.parquet` | 1,309 factors / 924 companies — 1,068 exact, 207 inferred, 18 unlinked, 16 approx |
| `coverage.parquet` | per-source spans, incl. the declared 1m hole |
| `intraday_depth.parquet` | 805 symbols; **535 deep** (≥60 months), 270 shallow |

21.4% of rows required corporate-action adjustment, across 924 companies.

### Nine defects found while building it

Each of these would have silently corrupted every number downstream. They are the
reason Phase 0 was worth doing before any model.

| # | Defect | Consequence if shipped |
|---|---|---|
| 1 | **bhavcopy is RAW; the charting feed is pre-adjusted** — opposite directions | NESTLEIND reads −90.17% instead of −1.67% |
| 2 | NSE's stated ex-date is wrong for 13 factors (IRCTC: records 10-29, steps 10-28) | Leaves the artefact *and* fabricates a reverse step |
| 3 | **Renames break symbol matching** — the CA feed uses today's name, bhavcopy the name of the day | WELSPUNIND −89.6%, TRIL −89.6%, DAAWAT −89.2% left in the data |
| 4 | **The ISIN changes on a face-value split** — the very event being matched | Keying on full ISIN *lost* 383 matches vs. the prefix |
| 5 | Pandas renders missing ISINs as `<NA>`, not `"NAN"` | My own blank-check missed it and a dedup **deleted 515,602 rows** (18 months, the deepest history) |
| 6 | ETF/mutual-fund ISIN prefixes are AMC codes shared across schemes | BANKBEES+GOLDBEES+NIFTYBEES+LIQUIDBEES merged into one "company" |
| 7 | A DVR line shares its prefix with the ordinary line (`INE224E01`) | Interleaved two price series → ten fake −95% actions (the TATASTEEL bug shape) |
| 8 | Stale `prev_close` across a trading suspension | STAMPEDE, suspended and printing weekly at ₹0.85, produced ten fake corporate actions |
| 9 | A `MAX_FACTOR` sanity ceiling made extreme steps skip *recording*, not just adjusting | Hid the single largest artefact in the panel (MAJESCO, below) |

### Three judgment calls, stated explicitly

**1. Unexplained big steps are flagged, NOT masked.** 2,971 sessions show an
unexplained ≥18% step. Masking them was the original plan and it was wrong:
2,421 sit inside India's 20% circuit band, and the largest contributors are
**YESBANK (14 sessions, the 2020 moratorium), ADANIENT (10, Hindenburg 2023) and
FINANTECH (9, the 2013 NSEL scam)**. Those are real losses. Deleting them
flatters every strategy in exactly the way survivorship bias does. The `big_move`
flag exists so a study can exclude them *and say that it did*.

**2. The masking threshold is −90%, not −50%.** A one-session −90% move on a
liquid name is mechanically a corporate action. But **YESBANK fell 56.1% in a
single session and that was real** — F&O names carry no per-stock circuit limit.
A −50% rule would have deleted it. So `ca_suspect` (39 sessions) triggers only
beyond −90%.

**3. A printed ratio is authoritative; prices only locate it.** The price series
confirms *that* a discontinuity happened and *which* session, and never vetoes the
printed ratio. A 10:1 split on a day the stock also gapped −27% (BESTAGRO, DANGEE,
HARDWYN, LAL, LANDSMILL) is still a 10:1 split. This lifted acceptance from 619 to
**1,084 of 1,153** in-span factors; the 51 refused are cases with *no*
discontinuity at all (ZEEL's "22:1" is a bonus **debenture**, not a price split)
and are masked rather than adjusted.

### The company key, and why it is not the symbol or the ISIN

`co` = ISIN[:9], because that prefix survives both a rename and a face-value
split. Refinements needed in practice: funds (`INF*`) excluded; prefixes whose
ISINs **overlap in time** fall back to the full ISIN (1 case, the DVR line);
pre-2011 rows backfill from the symbol's earliest known ISIN; and 36 pre-ISIN
orphans are stitched to their successor when the join is unambiguous on all four
of adjacency, price continuity (≤5%), non-recurrence and uniqueness — which is how
TATATEA (ends 2010-07-20 at ₹121.90) rejoins TATAGLOBAL→TATACONSUM (begins
2010-07-21 at ₹121.55). 49 keys remain orphaned; that is a known, bounded
limitation (7,435 rows, 0.11%).

### MAJESCO — the case that needed all of it

Raw close **₹985.60 → ₹12.20** on 2020-12-23, a fall of ₹973.40 that is exactly
its **₹974/share special dividend** after selling its US business. NSE's feed
carries no corporate action for it (the company later delisted), the dividend
record does not align, and the implied 80.8× ratio exceeded the sanity ceiling so
it was never recorded. It sat in the eligible universe as a −98.8% "return" on a
name with **₹1.3 bn average daily turnover**. Now caught by `ca_suspect`.

### Phase 1 — v4 re-measured on the panel (2026-07-29)

v4 was re-scored on the Phase-0 panel with **the scorer untouched** — same
`_analyze_arrays`, same WINDOW=250 / SCORE_MIN=50 / MIN_PRICE=5 / MIN_TURN=1e7,
same gate, same top-5/day. Only the prices underneath changed, and they changed
because they were wrong.

```
python score_v4.py --source panel --workers 14      # 10.3 min
python harness.py  --source panel --strategies v4
```

**2,309,073 signals over 2,324 companies** → `panel/v4_signals_panel.parquet`.

| v4, same frozen gate | Universe | TRAIN | VAL | **TEST** | win% | PF | CAGR% | maxDD% | Calmar |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `v4_ablations.csv` (corrected store) | biased, ~750 | 0.94 | 2.40 | **1.67** | 50.6 | 1.38 | 22.83 | −53.5 | 0.43 |
| `V5_BIASFREE` *proxy* momentum, CA-adj | bias-free, 3,831 | 2.16 | 2.58 | **1.81** | — | — | — | — | — |
| **Phase-0 panel, real scorer** | bias-free + CA-adj, 2,593 | 1.10 | 1.70 | **0.35** | 47.7 | 1.24 | 12.28 | −40.9 | 0.30 |

**v4's out-of-sample expectancy falls from 1.67 to 0.35%/trade** once the universe
is survivorship-free *and* the corporate actions are correct. Note the middle row:
`V5_BIASFREE`'s 1.81 came from a **proxy** (trend + near-52w-high + RS), not the
production scorer, and its own caveat §2 said so. Running the real gate on properly
corrected data does not reproduce it.

Drawdown improves (−53.5% → −40.9%) because the CA artefacts that produced fake
−90% sessions are gone, but Calmar still falls to 0.30 on weaker returns.

Both universes saturate the top-5/day cap identically (5 × 3,777 sessions = 18,885
pairs), so the count is fixed and only the *composition* of the five changes.

#### The benchmark that interprets it — v4 vs 8 random seeds

`rand:N` picks 5 liquid names per day at random, ranked by crc32 over
`(symbol, date, seed)` so the row is reproducible rather than a fresh PRNG draw.
Everything else is identical: same universe, same next-open entry, same 2.5×ATR
close-stop, same 20-session exit, same 0.30% cost.

| Engine | TRAIN | VAL | **TEST** | win% | PF | CAGR% | maxDD% | Calmar |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| **v4 frozen** | **1.10** | **1.70** | **0.35** | 47.7 | 1.24 | 12.28 | **−40.9** | **0.30** |
| rand:1 | 0.46 | 1.14 | 0.75 | 47.7 | 1.16 | 1.73 | −69.3 | 0.02 |
| rand:2 | 0.48 | 1.69 | 0.74 | 48.2 | 1.19 | 9.81 | −66.4 | 0.15 |
| rand:3 | 0.23 | 1.68 | 0.58 | 47.6 | 1.15 | 7.87 | −65.8 | 0.12 |
| rand:4 | 0.37 | 1.08 | 0.86 | 48.3 | 1.15 | 7.93 | −51.7 | 0.15 |
| rand:5 | 0.42 | 1.26 | 0.54 | 47.6 | 1.15 | 6.23 | −63.9 | 0.10 |
| rand:6 | 0.62 | 1.96 | 0.48 | 48.5 | 1.21 | 8.25 | −62.7 | 0.13 |
| rand:7 | 0.38 | 1.50 | 0.66 | 48.4 | 1.16 | 10.05 | −55.4 | 0.18 |
| rand:8 | 0.30 | 1.67 | 0.63 | 47.2 | 1.16 | 10.44 | −57.9 | 0.18 |
| **random mean ± sd** | 0.41 ± 0.13 | 1.50 ± 0.31 | **0.66 ± 0.12** | | | | | |

**v4's selection edge decays monotonically to below-random out of sample:**

| Window | v4 | random mean | v4 − random | in σ of the random spread |
|---|--:|--:|--:|--:|
| TRAIN | 1.10 | 0.41 | **+0.69** | **+5.4σ** |
| VAL | 1.70 | 1.50 | +0.20 | +0.6σ |
| **TEST** | **0.35** | **0.66** | **−0.31** | **−2.5σ** |

v4's TEST expectancy is **below all eight random draws** (range 0.48–0.86). TRAIN
+5.4σ → VAL +0.6σ → TEST −2.5σ is the textbook decay profile of a rule fitted to
its development period, and v4's gate was built on data covering 2011–2022.

**But v4 is decisively better on risk, and that part is real.** It beats every
random seed on drawdown (−40.9% vs −51.7 to −69.3), on CAGR (12.28 vs 1.73–10.44)
and on Calmar (0.30 vs 0.02–0.18). v4 selects names with materially better risk
characteristics even when its per-trade expectancy does not beat chance.

*Caveat on that:* those portfolio figures are **full-period 2010–2026**, so they
are dominated by TRAIN where v4 genuinely excels, and they are not a clean
out-of-sample statement. The seed spread also measures variation in *which* names
random picks, not the full sampling error of the expectancy estimate — the trades
overlap in time and cluster within days, so effective n is a few hundred day-blocks,
not 4,250 trades.

#### What this changes about the plan

The plan already argued for pointing ML at **sizing rather than picking**, on the
basis that selection was worth ~+0.30%/trade over random while risk sizing moved
Calmar 0.43 → 0.61. This is stronger than that: on honest data v4's out-of-sample
selection is worth **nothing at all**, while its risk profile is worth a great
deal. So:

- Phase 2 (risk overlay) and Phase 5 (meta-label sizing) move up: they act on the
  part of v4 that demonstrably works.
- Phase 4's learned ranker stops being a refinement and becomes **the only
  candidate for adding selection skill**, since the incumbent has none to preserve.
- Any future engine must clear the `rand:N` row, not zero. That row is now
  mandatory in every comparison.

### Phase 2 — the risk overlay does NOT survive an honest walk-forward (2026-07-29)

`fit_overlay.py`: 24 trade-shaping sets × ~1,344 portfolio configurations = **28,224
scored**. Ranked on TRAIN only → top 200 → stability gate → one VAL pick → **one**
TEST look.

#### First, a bug that invalidated the original sweep

`portfolio_vol_target` capped the *number* of open positions but never the **sum of
their weights**, so `risk=1.25, max_weight=0.20, max_concurrent=12` quietly ran
**2.26× gross** — unfunded, uncosted leverage. A parameter search then rewards
leverage in a rising tape; the uncapped TRAIN leader printed a **VAL CAGR of 94%**.
Measured on the real trade set:

| config | gross | CAGR% | maxDD% |
|---|--:|--:|--:|
| risk 0.75 / mw 0.30 / conc 8, uncapped | 1.48× | 19.07 | −57.2 |
| risk 1.25 / mw 0.20 / conc 12, uncapped | **2.26×** | 24.02 | −81.4 |
| same two, `gross_cap=1.0` | 0.96× | **7.97 / 9.44** | −51.5 / −53.8 |

Removing the leverage cuts CAGR by ~60%. Worse, `portfolio()` divides by
`max_concurrent` and *is* normalised to 100% gross, so every vol-target-vs-equal-weight
comparison in `v4_advanced.csv` pitted an unlevered baseline against a levered
challenger. It looked plausible only because `avg_w 0.124 × 8` lands near 1.0 by
coincidence.

Uncapped, **0 of 200** configurations cleared the stability gate. Capped, 6 of 200 did.

#### The result, and the decomposition that matters

Selected: `top_n=3, atr_stop=2.5, time_exit=30, risk=1.05, max_weight=0.10,
dd_brake=0.10, brake_scale=0.5, gap_tilt=(1.0,1.0,0.5), max_concurrent=12`.
**Plateau: only 2 of 18 one-step neighbours are also eligible** — near a spike, so
weak evidence by the plan's own standard.

| Config | TRAIN Calmar | VAL | **TEST** | TEST CAGR% | TEST maxDD% |
|---|--:|--:|--:|--:|--:|
| equal-weight, v4 frozen (top5/2.5/20) | 0.17 | 1.15 | **−0.15** | −9.20 | −60.9 |
| vol-target plain 0.75%, top5 | 0.14 | 1.51 | **−0.13** | −8.13 | −61.2 |
| **equal-weight, top3/2.5/30** | 0.64 | 1.90 | **0.32** | 11.72 | −36.4 |
| **FITTED overlay, top3/2.5/30** | 1.06 | 3.11 | **0.31** | 8.72 | **−28.5** |

**The sizing overlay contributes nothing.** Equal-weight on the selected trade
shape gets TEST Calmar **0.32**; adding volatility targeting, the drawdown brake
and the gap tilt gives **0.31**. All of the improvement comes from the
*trade-shaping* parameters — fewer positions (top-3 not top-5) held longer
(30 sessions not 20) — which lifted TEST Calmar from −0.15 to 0.32.

**This contradicts `V5_ADVANCED_ENSEMBLE`'s central claim** that volatility
targeting is "the single most important advanced feature" (removing it collapsed
test Calmar 0.73 → 0.14). That ablation was run on the survivorship-biased universe
*with uncapped leverage*. On the corrected panel with a gross cap, vol targeting is
**Calmar-neutral out of sample**. What it does buy is a genuine drawdown reduction
(−36.4% → −28.5%) at the cost of CAGR (11.72 → 8.72) — the only configuration that
meets a −30% drawdown mandate, which is worth something for a risk limit but is not
a performance edge.

Note also TRAIN 1.06 → VAL 3.11 → **TEST 0.31**: the same steep decay v4's selection
showed. And the plan's original gate ("Calmar > 0.61") was itself derived from the
leaky number, so the correct gate is *versus equal-weight on the same trades* —
against which the overlay **fails**.

#### Verdict

- **Do not ship the vol-target/brake/gap-tilt overlay as a performance improvement.**
  It is a drawdown tool, and should be described only as that.
- The real, transferable finding is much simpler: **hold fewer positions for
  longer.** top-3 / 30-session beat top-5 / 20-session by +0.47 TEST Calmar with no
  sizing machinery at all. That deserves its own confirmation run, since top_n and
  time_exit were inside the search space and so carry selection benefit.
- Phase 5's meta-labelling now has a harder job than assumed: there is no
  established sizing gain for it to build on, so it must beat *equal-weight*.

### Phase 5 — meta-label sizing: a real but marginal gain (2026-07-29)

`build_meta.py` → 31 features at 100% coverage, all from the **signal bar** except
`f_entry_gap` (the overnight gap to the entry open, observed before capital is
committed). `fit_meta.py` → LightGBM binary, depth ≤ 4,
`min_child_samples=200`, `lambda_l2=20`, 6 purged folds with a 20-session embargo,
5-seed averaged, terciles fitted on TRAIN only → size multipliers 0.5 / 1.0 / 1.5.
The model never changes which names are picked.

#### Cross-validated signal, and the two ablations

| Run | CV AUC | folds > 0.50 | CV IC |
|---|--:|--:|--:|
| full feature set | **0.5295 ± 0.0312** | 5/6 | +0.0555 ± 0.0653 |
| **labels shuffled** (null) | **0.5060 ± 0.0059** | 4/6 | −0.0110 ± 0.0512 |
| `f_entry_gap` removed | 0.5193 ± 0.0354 | 5/6 | +0.0380 ± 0.0707 |

The shuffled run tripped the gate and refused to proceed to a TEST look — the
evaluation is not leaking. Real AUC sits ~0.024 above the shuffled null, i.e. weak
but present. Dropping `f_entry_gap` costs roughly half the portfolio benefit, so the
model is **partly** a rediscovery of the hand-built gap tilt and partly not.

Top features by gain are dominated by **market context, not stock features**:
`m_breadth` 13.4%, `m_vol20` 11.4%, `m_ret63` 8.8%, `m_dist_ema200` 7.4%,
`m_ret20` 5.8%. The model is largely learning *when* v4 signals pay, not *which*
ones — which is consistent with Phase 1 finding no cross-sectional selection edge.

#### Portfolio effect on the frozen v4 shape (top5 / 2.5 / 20)

| Config | TRAIN | VAL | **TEST** | TEST CAGR% | TEST maxDD% |
|---|--:|--:|--:|--:|--:|
| equal-weight (the bar) | 0.17 | 1.15 | −0.15 | −9.20 | −60.9 |
| vol-target flat | 0.14 | 1.51 | −0.13 | −8.13 | −61.2 |
| vol-target + META | 0.46 | 0.86 | **+0.03** | +1.67 | −49.1 |

#### Portfolio effect on the better shape (top3 / 2.5 / 30)

| Config | TRAIN | VAL | **TEST** | TEST CAGR% | TEST maxDD% |
|---|--:|--:|--:|--:|--:|
| equal-weight (the bar) | 0.64 | **1.90** | 0.32 | 11.72 | −36.4 |
| vol-target flat | 0.70 | 1.51 | 0.26 | 10.68 | −40.5 |
| **vol-target + META** | 0.76 | 1.23 | **0.47** | **16.64** | **−35.6** |

On the better shape META improves TEST Calmar **0.32 → 0.47**, CAGR 11.72 → 16.64,
and drawdown −36.4 → −35.6 — all three at once, which is the gate the plan set.

#### Four caveats that keep this "promising", not "proven"

1. **VAL gets worse.** 1.90 → 1.23 with META. It helps TRAIN and TEST but hurts
   VAL, so the effect is not consistent across windows.
2. **TEST terciles are not monotonic** (low −0.07, mid +1.39, high +1.07). The gain
   comes mainly from *down-weighting the worst* tercile, not from identifying
   winners. That is a narrower claim than "the model ranks trades".
3. **The trade shape carries selection benefit.** top3/2.5/30 was chosen in Phase 2
   using TRAIN+VAL, so its TEST figures are not fully out-of-sample.
4. **AUC 0.53 is thin** — ~0.024 over the shuffled null, one fold negative.

#### Verdict

Meta-label sizing is the **only** thing tested so far that improves out-of-sample
Calmar, CAGR and drawdown simultaneously. But it does so from a weak signal that is
partly the known gap tilt, it is inconsistent across windows, and it rests on a
trade shape that itself needs independent confirmation. It earns a forward
paper-validation slot behind a flag; it does not earn promotion.

### Confirmation of the trade-shape finding — "longer" holds up, "fewer" does not (2026-07-29)

`confirm_shape.py` re-runs the top_n × time_exit grid over **random** pickers as
well as v4. Random selection has no signal to overfit, so an effect that appears
there too is structural rather than fitted. Every cell uses one instrument — a
gross-capped (1.0) volatility-target book at `max_concurrent=20` — because
`portfolio()` divides by max_concurrent and would otherwise let top_n change gross
exposure and confound the comparison.

**TEST Calmar by shape:**

| engine | time_exit | top3 | top5 | top8 |
|---|--:|--:|--:|--:|
| v4 | 20 | −0.03 | −0.17 | 0.06 |
| v4 | **40** | **0.41** | 0.08 | 0.07 |
| rand:1 | 20 | 0.34 | 0.12 | 0.11 |
| rand:1 | **40** | 0.58 | **0.81** | 0.28 |
| rand:2 | 20 | 0.99 | 0.46 | 0.46 |
| rand:2 | **40** | 0.70 | 1.01 | **1.59** |

**1. The longer hold is real.** Going from a 20- to a 40-session time exit improves
TEST Calmar in **8 of 9** (engine, top_n) cells, including for both random pickers.
That is consistent with `V4_EXIT_STUDY` §5's finding that no exit rule beat doing
nothing, and with simple cost arithmetic: at 0.30% round-trip, halving turnover
halves the cost drag.

**2. "Fewer positions" does NOT replicate — I was wrong to headline it.** At
exit40, v4 prefers top3 (0.41 > 0.08 > 0.07), but rand:1 prefers top5 (0.81) and
rand:2 prefers **top8** (1.59). The direction reverses across engines, so
`top_n=3` was fitted to v4 (or noise), not a structural effect. The earlier claim
that "hold fewer positions for longer" was the durable finding is **half retracted**:
only the *longer* half survives.

**3. v4 loses to random on TEST across the entire grid.** v4's best TEST Calmar is
0.41; rand:1 reaches 0.81 and rand:2 reaches 1.59, and rand:2's *worst* cell (0.46)
beats v4's second-best. The same TRAIN/VAL-win, TEST-lose pattern Phase 1 found in
per-trade expectancy shows up in risk-adjusted return, which is an independent
confirmation on a different metric.

**4. TEST-window Calmar is extremely noisy, and this bounds every conclusion
above.** Two random seeds differ by 1.31 Calmar in the same cell (top8/exit40: 0.28
vs 1.59). A 3.5-year TEST window contains few independent drawdown episodes, so
Calmar there has very wide error bars. Nothing in this table except the exit-length
gradient should be treated as established, and even that deserves more seeds.

**Consequence for Phase 2 / Phase 5.** The `top3` component of Phase 2's selected
configuration is not confirmed, so the Phase-5 meta-sizing result rested on a trade
shape whose `top_n` element is engine-specific. Re-measured on `top5/exit40` — the
shape the confirmation test supports:

| Config (top5 / 2.5 / exit40, conc 20) | TRAIN | VAL | **TEST** | TEST CAGR% | TEST maxDD% |
|---|--:|--:|--:|--:|--:|
| equal-weight (the bar) | 0.47 | 0.84 | **0.20** | 8.35 | −42.3 |
| vol-target flat | 0.21 | 1.25 | 0.15 | 6.51 | −43.5 |
| vol-target + META | 0.40 | 1.09 | **0.18** | 7.08 | −39.6 |

**Meta sizing does NOT beat equal weight on the confirmed shape** (0.18 vs 0.20),
and the gate refused it. TEST terciles are again non-monotonic (low +1.25, mid
+2.20, high +1.23), with the middle tercile the strongest — so the model is not
ordering trades even where it appears to help.

**So the Phase-5 result was shape-specific, and is withdrawn.** Meta sizing helps
on top3/exit30 (0.32 → 0.47) and hurts slightly on top5/exit40 (0.20 → 0.18). An
effect that flips sign with a parameter that itself failed confirmation is not an
effect. It keeps its forward-paper slot at most as a drawdown tool (−42.3 → −39.6).

**A methodological caveat that bounds all of the above.** The same cell measured
with two different portfolio instruments gives materially different Calmar: v4
top5/exit40 scores **0.08** under the gross-capped vol-target book at conc 20
(`confirm_shape.py`) and **0.20** under equal weight at conc 20 (`fit_meta.py`).
The choice of portfolio instrument moves TEST Calmar by roughly as much as the
strategy parameters do. Any conclusion resting on a Calmar difference below ~0.15
on this TEST window is not supportable.

---

## 1c. Consolidated state after Phases 0, 1, 2, 5 (2026-07-29)

| # | Question | Verdict | Evidence |
|---|---|---|---|
| 0 | Is the data honest? | **Now yes** | 32/32 gates; 9 defects fixed |
| 1 | Does v4 select stocks? | **No** | TEST 0.35 vs random 0.66 ± 0.12; below all 8 seeds |
| 2 | Does the risk overlay add Calmar? | **No** | 0.31 vs 0.32 equal-weight; prior gain was leverage + a test look |
| — | Fewer positions? | **No** | direction reverses across engines (v4 top3, rand:2 top8) |
| — | **Longer holding period?** | **Yes** | improves TEST Calmar in **8 of 9** cells, random pickers included |
| 5 | Does learned sizing add Calmar? | **Not established** | +0.15 on one shape, −0.02 on the confirmed shape |

**One robust finding: hold positions longer (40 sessions, not 20).** It replicates
on random pickers, so it is structural rather than fitted, and it is what the cost
arithmetic predicts — 0.30% round-trip means halving turnover halves the drag. It
agrees with `V4_EXIT_STUDY` §5, which found no exit rule beat doing nothing, and
with Kaminski & Lo (stops reduce expected return under noise/reversal).

**Everything the repo previously believed about v4's edge has now failed on honest
data.** The selection edge, the volatility-target overlay, and the drawdown
brake/gap tilt all fail to beat their proper benchmarks once survivorship bias,
corporate actions, and unfunded leverage are removed. That is the value of Phase 0
rather than an argument against it.

**What this means for Phase 4.** The learned ranker is now the only untried source
of selection skill, and it starts from a clean slate: there is no incumbent edge to
preserve, and the bar it must clear is the `rand:N` row, not zero.

### Phase 4 — the cross-sectional signal is REAL, and it is not momentum (2026-07-29)

`build_rank.py` → **1,907,842 rows × 30 features**, 3,787 sessions, 1,999 companies,
median 392 eligible candidates/day. Label = within-day quintile of the 20-session
forward return from the next open. Grade means are −11.92 / −4.49 / −0.22 / +4.58 /
**+16.33%** — a 28-point spread available to anything that can order the cross-section.

`fit_rank.py`, 6 purged folds inside TRAIN (embargo 20 sessions), all figures mean ± sd
across folds:

| Rung | IC | sd | top5_edge | folds +ve |
|---|--:|--:|--:|--:|
| R0 `f_ret20_xr` | +0.0044 | 0.0302 | −0.398% | 4/6 |
| R0 `v_score` (v4's own scorer) | +0.0101 | 0.0139 | −0.260% | 4/6 |
| R0 `f_ret63_xr` | +0.0319 | 0.0293 | +0.342% | 5/6 |
| R0 `f_dist_252h_xr` | **+0.0908** | 0.0344 | +0.321% | **6/6** |
| R0 `f_atr_pct_xr` | **−0.0824** | 0.0272 | **−3.364%** | **0/6** |
| **R1 ridge** | **+0.1151** | 0.0334 | +0.808% | **6/6** |
| R2 lambdarank | +0.0645 | 0.0315 | **+1.398%** | 6/6 |

**The null test says the signal is genuine.** Labels shuffled *within each day*:

| Rung | shuffled IC | shuffled edge |
|---|--:|--:|
| R0 `f_dist_252h_xr` | −0.0020 ± 0.0031 | +0.097% |
| R0 `f_atr_pct_xr` | +0.0014 ± 0.0029 | −0.038% |
| R1 ridge | −0.0018 ± 0.0041 | −0.128% |
| R2 lambdarank | +0.0000 ± 0.0035 | +0.003% |

Every rung collapses to zero within ±0.004. Ridge's real IC of +0.1151 is ~28 null
standard deviations away. After four phases of null results, **this is the first
large, clean signal measured anywhere in this work.**

#### Four things that matter more than the headline

**1. The strongest single predictor is volatility, with a negative sign.**
`f_atr_pct_xr` scores IC −0.0824 and a top-5 edge of **−3.364%, negative in 6 of 6
folds**. Ranking *by highest ATR* is the single most reliable way to lose money in
this universe — the low-volatility / lottery-stock effect, which is well documented
in Indian equities. Nothing else found in this entire exercise is this consistent.

**2. That plausibly explains Phase 1.** v4 selects volatile momentum names
(`MIN_TURN` liquidity floor, near-52-week-high, ADX ≥ 25), and volatility is
strongly negative for forward returns here. v4 may be losing to random precisely
because random picking does *not* tilt toward high ATR.

**3. v4's own scorer is nearly worthless cross-sectionally.** `v_score` alone:
IC +0.0101, top-5 edge **−0.260%**, 4/6 folds. That is a fourth independent
confirmation of Phase 1, this time from inside the feature set.

**4. Ridge beats the GBDT on IC, and the GBDT wins on the top-5.** Ridge +0.1151 vs
lambdarank +0.0645 on IC, but lambdarank has the better top-5 edge (+1.398% vs
+0.808%). That is not a contradiction — `lambdarank_truncation_level=5` optimises
NDCG@5, i.e. the top of the list only, so full-cross-section IC penalises it for
doing exactly what it was asked. It echoes `dl_compare.py`'s original finding that
ridge ≈ GRU: on this data shape, linear is hard to beat.

#### Protocol note — a gate I mis-specified

The pre-registered gate was "R2 must beat R1 by ≥0.01 **IC**". R2 failed it (0.0645
vs 0.1151) and the script correctly refused a TEST look. But the production decision
is top-5-per-day selection, and on that metric R2 is the best rung. The gate was
measuring the wrong thing.

Changing a gate after seeing results is the exact failure this plan exists to
prevent, so: the IC gate stands as failed, and the choice between R1 and R2 is made
on **VAL**, which Phase 4 has not yet touched (all CV above is inside TRAIN). One
TEST look follows that choice. This is a disclosed protocol correction, not a
silent one.

Also note `top5_edge` fold variance is very large (R2: −2.176% to +3.079%), so
ridge-vs-lambdarank is **not** separable on TRAIN evidence.

#### A label defect, quantified and bounded

`y_fwd` is NaN when a company's series ends inside the 20-session forward window, so
those rows are dropped rather than counted as the loss a real book would take —
survivorship bias in the *label*. Measured: 32,608 of 1,940,450 eligible rows are
dropped (1.68%), of which only **1,171 (0.06%)** belong to companies that actually
stopped trading. Their final-20-session returns are median **−3.5%** but mean
**+5.1%**, because delisting includes takeovers at a premium as well as failures. So
the bias is small and its sign is not even clearly optimistic. Documented rather than
fixed; it would need a delisting-recovery assumption to do properly.

### THE TABLE — every engine, one universe, one configuration (2026-07-29)

`final_compare.py`: all engines in one process, off one feature build, at top-5/day,
2.5×ATR close-stop, **40-bar exit** (the confirmed shape), 0.30% round trip, on the
bias-free CA-adjusted panel. Earlier phases measured engines at different holding
periods, and expectancy scales roughly with holding period — a v6 number at exit 40
beside a v4 number at exit 20 overstates v6 about 2×. `harness.py` had no
`--time-exit` flag at all, which is how that slipped through; it does now.

| strategy | n | TRAIN | VAL | **TEST** | win% | PF | CAGR% | maxDD% | Calmar |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **v6:lgbm** | 17,483 | *14.03* | 7.91 | **6.44** | 61.4 | 3.50 | 108.94 | −45.6 | 2.39 |
| **s1** trend-pullback | 13,131 | 1.08 | 1.67 | **2.65** | 43.6 | 1.24 | 9.10 | −50.3 | 0.18 |
| **s3** rs-continuation | 12,218 | 2.50 | 3.22 | **2.35** | 42.1 | 1.35 | 18.38 | −52.1 | 0.35 |
| **v6:near_high** (unfitted) | 17,013 | 1.01 | 3.30 | **2.28** | 45.2 | 1.34 | 15.51 | −39.8 | 0.39 |
| rand:1 | 18,766 | 0.35 | 2.95 | 2.00 | 44.3 | 1.23 | 3.58 | −59.0 | 0.06 |
| sX vol-contraction | 4,622 | −0.11 | 1.68 | 1.98 | 40.5 | 1.21 | 5.76 | −36.8 | 0.16 |
| rand:2 | 18,778 | 0.41 | 3.46 | 1.96 | 44.4 | 1.25 | 10.02 | −61.6 | 0.16 |
| rand:3 | 18,780 | 0.26 | 3.12 | 1.95 | 44.3 | 1.21 | 3.58 | −51.7 | 0.07 |
| s6 daily-momentum | 13,011 | −0.04 | 0.55 | 1.60 | 39.8 | 1.06 | 10.33 | −45.2 | 0.23 |
| **v4** (incumbent) | 18,343 | 2.53 | 3.64 | **1.58** | 47.1 | 1.47 | 13.95 | −38.1 | 0.37 |
| v6:low_atr (unfitted) | 18,656 | 1.35 | 1.12 | **1.37** | 47.9 | 1.47 | 10.11 | −33.7 | 0.30 |

**The random bar is 1.95–2.00** — a 0.05 spread across three seeds, so it is precise.
Four engines clear it: v6:lgbm, s1, s3, v6:near_high. **v4 (1.58) does not**, and
neither does low-ATR (1.37), the "anomaly" that looked strongest on TRAIN folds.

#### v6:lgbm's 6.44 decomposed — 2023 carries it

| TEST year | mean | median | n | sd |
|---|--:|--:|--:|--:|
| **2023** | **+14.62** | +9.24 | 1,110 | 28.02 |
| **2024** | **−1.96** | **−10.25** | 1,033 | 19.82 |
| 2025 | +5.29 | +1.53 | 1,168 | 21.35 |
| 2026 | +8.18 | +3.66 | 546 | 23.13 |

2023 — India's small-cap mania — contributes more than half the total. 2024 is
outright negative with a median of −10.25%. With four annual observations, mean
+6.5% and a cross-year sd of ~7%, the estimate is about **1.9 standard errors from
zero**: suggestive, not conclusive.

**Excluding 2023 the mean is +3.84%**, still above random's 1.97 (+1.87 edge). Apply
the ₹100 cr capacity haircut (the edge falls from +2.25% to +0.93% cross-sectionally,
≈41%) and the durable claim is roughly **+0.8%/trade over random** — modest, real,
and a long way from 6.44.

Profit is right-skewed but not fragile: the best 7% of trades carry 75% of P&L (the
Wilcox/Zarattini pattern `V4_EXIT_STUDY` cites), yet the single best trade is only
0.5% and the top 10 only 4.7%. Excluding the best 5% of trades the mean is still
+2.75%. Exits split 61.5% time / 38.5% stop, mean hold 29.8 bars.

#### Phase 3's daily half — a genuine surprise

**s1 (2.65) and s3 (2.35) beat random on TEST**, which `V5_BIASFREE_RESULT` concluded
they could not ("v5 ensemble collapses to ~0.55"). Two things reconcile it: that work
used a **proxy** momentum rule and measured at a 20-bar exit, and this runs the
actual s1/s3 gates at the 40-bar exit that the shape confirmation supports. So the
v5 rules were closed out partly on a configuration artefact.

That said, s1 and s3 buy their expectancy with risk: maxDD −50.3% and −52.1% against
v4's −38.1%, and Calmar 0.18 / 0.35. They beat random per-trade, not per unit of
risk. **v5 should be reopened as a candidate, not promoted.**

#### Bottom line

| Claim | Status |
|---|---|
| v4 has a selection edge | **refuted** — below all 3 random seeds at matched config |
| Volatility targeting is the key advanced feature | **refuted** — was 2.26× unfunded leverage |
| Low-ATR is a strong signal | **refuted** — TRAIN-only; worst engine in the table |
| "Fewer positions" helps | **refuted** — reverses across engines |
| Learned meta-sizing helps | **not established** — flips sign with trade shape |
| Longer holding period helps | **supported** — 8 of 9 cells, random included |
| A learned ranker beats random | **supported, modestly** — ~+0.8%/trade after capacity, 2024 negative |
| v5's s1/s3 beat random | **supported** — reopens a question previously closed |

### Still open in Phase 0

**0.3 — Track B CA masking.** `dl_features.py` does not call
`adjust.flag_events()`, so the 1-minute feature panel ignores demerger sessions
that `harness.py` masks. Fixing it requires rebuilding `dl/features.parquet`
(~1 h of compute across 6 workers). Track A is unaffected.

---

## 2. Phase 0 — data foundation (as originally specified)

Every measured number in this repo's history changed when the data changed. Do
this first or repeat the reversal.

| # | Task | Output | Gate |
|---|---|---|---|
| 0.1 | Build the CA-adjusted, survivorship-free daily panel from `bhavcopy_eod.parquet` + `universe_by_date.parquet`. Apply **empirical** (demerger) factors only; splits/bonuses are already in. Mask, don't fabricate, where a factor is unverifiable — `adjust.mask_returns()` is the pattern. | `E:\nse\panel\daily_pit_adj.parquet` | Zero \|1-day return\| > 50% that is not flagged `ca_event`. Spot-check ADANIENT 2015-06-03 → masked, not −82.8%. |
| 0.2 | Point-in-time universe membership + liquidity: for each date, symbols with 20-day avg turnover > ₹5 cr **as known on that date**. No forward information. | `panel/pit_eligible.parquet` | On 2010-01-04 the eligible set must contain names absent from today's index (`ABAN`, `ABGSHIP`, `3IINFOTECH`). If it doesn't, the PIT logic is broken. |
| 0.3 | Add `ca_event` masking to `dl_features.py`; rebuild `dl/features.parquet`. | features.parquet v2 | 44 demerger sessions excluded; row count drops by a few hundred, not thousands. |
| 0.4 | Explicitly mark the **2026-05-16 → 2026-06-28 hole** (1m ends 2026-05-15, live accumulator starts 2026-06-29). Never interpolate. | `panel/coverage.parquet` | Any 1m study spanning that window fails loudly instead of silently bridging. |
| 0.5 | Tag each 1m symbol `deep` / `shallow` (≥60 months vs not) and each as `largecap_missing`. | `panel/1m_depth.parquet` | 526 deep, 238 not. |
| 0.6 | Freeze splits. **TRAIN 2010-01-01→2019-12-31 · VAL 2020-01-01→2022-12-31 · TEST 2023-01-01→2026-07** with a **20-session embargo** at each boundary. Write them to one config module both tracks import. | `dataset/splits.py` | Two engines cannot silently use different windows, which is how v4's TEST=1.37 became non-comparable to harness numbers. |

Effort: 2–3 days. This is the highest-value work in the plan and it involves no
model at all.

---

## 3. Phase 1 — v4: freeze and re-measure (no training)

v4 is the benchmark. Its only job is to produce one honest number on the Phase-0
panel so everything else has something to beat.

```powershell
python score_v4.py --source bhav --workers 12      # already produced 2,357,294 signals
python harness.py --timeframe 1d --strategies v4 --survivorship-free
```

**Do not tune anything.** Report the number that comes out.

Current best-known v4 figures, for reference:

| Source | Universe | TRAIN | VAL | TEST | win% | PF | CAGR% | maxDD% | Calmar |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `v4_ablations.csv` (corrected store) | 750 biased | 0.94 | 2.40 | **1.67** | 50.6 | 1.38 | 22.83 | **−53.5** | 0.43 |
| `V5_BIASFREE_RESULT` v4-style proxy, CA-adj | 3,831 bias-free | 2.16 | 2.58 | **1.81** | — | — | — | — | — |
| `V4_EXIT_STUDY` finalist | yfinance | 1.11 | 2.66 | 1.51 | 50.1 | — | — | — | — |

Note the honesty check from `V4_EXIT_STUDY` §5 that governs how to read all of
this: **random 5/day, hold 20 days, no stop → TEST +1.52%/trade.** v4's edge over
random is +0.61 train / +0.81 val / **+0.30 test**. The absolute level is drift and
survivorship; the *selection* edge is ~0.3%/trade on test. Any model claiming a
large improvement must beat random-by-a-margin, not beat zero.

**Deliverable:** `results/v4_frozen.json` — one row, never re-run with different
parameters.

---

## 4. Phase 2 — v4-advanced: fit the risk overlay properly

This is where the repo's largest measured win already lives, and where the
current work is under-searched and has a leak.

**What's measured today** (`v4_advanced.csv`, `v4_advanced_gap.csv`):

| variant | CAGR% | maxDD% | Calmar |
|---|--:|--:|--:|
| v4 equal-weight baseline | 22.83 | −53.5 | 0.43 |
| vol-target 0.75% | 22.22 | −53.2 | 0.42 |
| vol-target + brake15 | 20.65 | −38.1 | 0.54 |
| vol-tgt + brake15 + stop2.0 | 20.89 | −36.4 | 0.57 |
| + gap tilt 1.0/1.0/0.5 | 20.68 | −34.1 | **0.61** |

Calmar 0.43 → 0.61 for −2pp of CAGR. That is a bigger, more reliable improvement
than anything the signal research produced. `V5_ADVANCED_ENSEMBLE` §ablation
independently confirms it: removing vol targeting collapses test Calmar 0.73 →
**0.14** while *raising* CAGR to 18.7% — the classic overfit signature.

**Two problems to fix:**

1. **Leak.** Those rows report **full-period** CAGR/maxDD/Calmar. The full period
   includes TEST 2023–26. Selecting `gap tilt 1.0/1.0/0.5` because it scored 0.61
   full-period **is a test look.** Redo the search reporting TRAIN-only, select on
   VAL, one TEST look at the end.
2. **Under-search.** Six hand-built combinations over ~7 parameters. Use a real
   search.

**Search space:**

| Parameter | Current | Range to search | Prior / why |
|---|---|---|---|
| `target_risk_pct` | 0.75 | 0.30 – 1.25, step 0.05 | Sets gross leverage. Drives both CAGR and DD linearly-ish; the ratio is what matters. |
| `max_weight` | 0.25 | 0.08 – 0.30 | Caps concentration on low-ATR names. `avg_w` is 0.124, so 0.25 rarely binds — likely inert, verify before keeping. |
| `atr_stop` | 2.5 | 2.0, 2.5, 3.0, 3.5, **no stop** | `V4_EXIT_STUDY` §5: *no exit rule beat doing nothing.* No-stop must be in the space or the search is rigged. |
| `dd_brake` | 0.15 | none, 0.10, 0.15, 0.20, 0.25 | Portfolio-state-aware; a per-trade stop cannot do this. |
| `brake_scale` | 0.5 | 0.25, 0.5, 0.75 | |
| `gap_tilt` (dn/flat/up) | 1.0/1.0/0.5 | dn ∈ {1.0,1.5,2.0}, up ∈ {0.4,0.7,1.0} | Measured on 17,972 trades: gap-down >1.5% median +1.25 / win 54.9%; gap-up >1.5% highest mean 2.37 but **negative median** — lottery tickets. |
| `top_n` | 5 | 3, 5, 8, 10 | top-3 cut maxDD to −43.1% at CAGR 16.4 (`v4_ablations.csv`). |
| `max_concurrent` | 8 | 6, 8, 12, 16 | Interacts with top_n; more slots = more diversification but more capital idle. |
| `time_exit` | 20 | 15, 20, 30, 40 | `V4_EXIT_STUDY`: median hold already runs to the full 20; winners are being cut. |

Full grid ≈ 300k combinations — trivially parallel across 64 cores, but that many
looks at VAL *is* overfitting VAL. **Protocol:**

- Rank on **TRAIN** (2010–2019) by Calmar. Keep the top 200.
- Re-score those 200 on **VAL** (2020–2022). Select **one** config — prefer the
  centre of a stable plateau over the single peak. Report the plateau width; a
  parameter whose optimum is a spike is noise.
- **One** TEST look. Publish it whatever it says.
- **Stability requirement:** the chosen config must be within 15% of best on both
  TRAIN and VAL, and must not rank in the bottom half of the 200 in either. A
  config that wins VAL but is mediocre on TRAIN is a VAL artefact.

**Objective function:** not CAGR. Use **Calmar**, with a hard constraint
`maxDD ≥ −30%` and `n_taken ≥ 800` (below that, portfolio metrics are a few
lucky trades).

**Deliverable:** `results/v4_advanced_walkforward.json` + a plateau heat map.
Expected outcome, stated in advance so it can't be moved: **Calmar 0.61 → 0.65–0.75,
maxDD −34% → −25 to −30%, CAGR 18–21%.** If the honest walk-forward comes in
*below* 0.61, that tells you the 0.61 was the leak, and that is a real finding.

Effort: 2 days (1 compute-bound).

---

## 5. Phase 3 — v5: the one genuinely new capability

v5 has been refuted twice (`V5_BIASFREE_RESULT`: closed out as a promotion
candidate). Reopening it is only justified because **one input changed**: the
multi-timeframe hypothesis was previously `[UNVERIFIED]` and excluded for lack of
intraday history. There are now 8.4 years of it.

```powershell
python harness.py --compare 1d,60m,30m,15m,5m --strategies s1,s3,s6,sX --start 2018-01-01
```

**What to test, and the honest prior on each:**

| Question | Method | Prior |
|---|---|---|
| Does any strategy improve on a lower timeframe? | Same rules, resampled bars, 2018–2026, deep-1m symbols only | **Low.** `intraday_entry.csv` already measured entry timing: `delay_15` +0.031, `delay_30` +0.034 %/trade vs open. That is nothing. |
| Does the regime gate help on the bias-free panel? | `--bull-only` ablation on Track A | **Low–medium.** `v4_ablations.csv`: BULL-only cut CAGR 22.8→14.6 *and worsened Calmar* 0.43→0.33. It cost more return than drawdown. |
| Is ORB30 entry real? | `intraday_entry.csv`: mean 5.067, median **0.743** vs open 0.185, win 52.4% — but **fill 50.5%** and `vs_open −1.388` on paired trades | **Selection artefact, probably.** A 30-min opening-range break only fills on days that already moved up; the paired comparison being −1.388 says the unfilled half was where the money was. Test as: *does taking ORB30 when available and open otherwise beat always-open?* That is the only decision-relevant framing. |
| Ensemble weighting across S1/S3/S6 | Fit weights on TRAIN, hold on VAL | **Low.** Bias-free CA-adjusted, the v5 ensemble scored TEST 0.92 vs v4's 1.81 — a 2× gap. Weighting will not close 2×. |

**Kill criterion, set now:** if no v5 variant reaches **TEST ≥ 1.6%/trade** on the
Phase-0 bias-free panel (v4 sits at 1.67–1.81), v5 is closed permanently and the
timeframe question is answered "no". Budget **3 days**, then stop regardless of
how interesting it looks.

This phase's realistic value is a *documented negative result* that stops future
re-litigation. That is worth 3 days; it is not worth 3 weeks.

---

## 6. Phase 4 — v6: the learned model (the recommendation)

### 6.1 The constraint that dictates every modelling choice

`dl/features.parquet` has 1,033,720 rows. **The effective sample size is roughly
100–200 independent observations, not a million.**

- Labels are **20-session forward returns** → consecutive samples share 95% of
  their label window.
- The cross-section is **highly correlated** → 526 symbols on one date are close
  to one observation of "the market that day", not 526.
- ~2,121 sessions ÷ 20-session label ≈ **106 non-overlapping time blocks.**

A model with 100k+ parameters facing ~106 independent observations will fit
noise perfectly. This is not a hardware problem and 96 GB of VRAM does not help.
**It is why the existing result is what it is:**

| model | val_IC | EVAL_IC | secs |
|---|--:|--:|--:|
| ridge | 0.1021 | 0.0446 | 2 |
| GRU | 0.0610 | **0.0483** | 16 |

The GRU beats a linear model by **0.0037 IC** — i.e. by nothing — and its val_IC
is *worse*. `dl_compare.py`'s own docstring predicted this: *"A GRU that beats
ridge by 0.002 IC has learned essentially nothing and should not be deployed."*
It was right. Note also that **XGBoost was never run** (absent from
`dl_model_ladder.csv`) — the rung most likely to win on tabular finance data is
the one that is missing.

**Conclusion: do not scale the model. Fix the target, fix the validation, fix the
features, and ensemble small models.**

### 6.2 The three changes that matter more than architecture

**(a) Cross-sectional label, not absolute return.** Today the target is `fwd20` =
raw forward return. Every stock's `fwd20` is dominated by the market's `fwd20`, so
most of the variance the model chases is beta it cannot use — the harness picks
5 names *per day*, so only within-day ordering matters.

Replace with a per-day rank target:

```python
g = df.groupby("date")["fwd20"]
df["y_rank"] = g.rank(pct=True)                 # 0..1, market beta removed
df["y_top"]  = (df["y_rank"] >= 0.80).astype(int)   # alt: binary top-quintile
```

This alone typically lifts measured IC materially, because it stops measuring the
part of the signal that is unusable.

**(b) Learning-to-rank objective.** LightGBM `lambdarank`, `group` = trading day.
This optimises exactly the production decision (order the day's candidates) rather
than a regression the harness throws away.

**(c) Purged, embargoed, *multi-fold* CV.** Current setup: one TRAIN/EVAL split
with a 20-session embargo — the embargo is right, one fold is not. A single
EVAL_IC of 0.045 has an unknown standard error; with ~106 blocks it could easily
be 0.045 ± 0.04. Use **combinatorial purged CV** (López de Prado): 6 folds,
20-session embargo both sides, report **mean ± std across folds**. A model is only
real if its IC is positive in ≥5 of 6 folds.

### 6.3 The model ladder, in order, with kill gates

| Rung | Model | Data | Why | Kill gate |
|---|---|---|---|---|
| **R0** | Per-day rank of a single feature (`ret63`, `dist_252h`) | Track A daily | The true null. If a learned model can't beat one column, stop. | — |
| **R1** | Ridge on ranked features | Track A | Linear baseline, re-measured with the new target | — |
| **R2** | **LightGBM `lambdarank`** | Track A daily, bias-free, 2010–2026, 4,148 syms | **The primary model.** GBDT is state of the art for tabular finance; this is the rung that was skipped. | Must beat R1 by ≥0.01 mean IC and be positive in ≥5/6 folds |
| **R3** | R2 + Track B microstructure features, on the 526-deep-symbol subset | A ∪ B | Answers: *do 1-minute features add anything?* Measured as the increment over R2 **on the same symbols and dates**, so the bias cancels | Must add ≥0.01 IC on the overlap. `dl_compare.py` already prints micro-block gain share — use it |
| **R4** | 20-seed ensemble of R2/R3 | same | This is what the GPU is for. At ~106 independent blocks, seed-averaging cuts variance more than any architecture change | Ensemble IC std across folds must shrink vs single model |
| **R5** | Small temporal model — 2-layer GRU (64 hidden) **or** 1D-CNN, ≤200k params, 20 seeds | Track B sequences | Only if R3 shows real signal. Tests whether *sequence* structure adds beyond point-in-time features | Must beat R4 by ≥0.01 mean IC. **Given the existing GRU≈ridge result, expected to fail.** |
| **R6** | PatchTST / FT-Transformer / TFT | — | **Do not build.** ~106 independent observations. Revisit only if the vendor 1-minute purchase (C1: 2012→now, ~1B rows) lands and adds delisted names. | — |

### 6.4 Feature plan

Keep the existing 28. Add — in this order, each measured for incremental IC:

| Block | Features | Rationale |
|---|---|---|
| Cross-sectional | per-day percentile rank of `ret20`, `ret63`, `dist_252h`, `atr_pct`, `turnover` | The decision is relative; give the model relative inputs |
| Sector-relative | return minus sector median (sector from `store/universe`) | Separates stock alpha from sector rotation |
| Regime / index | NIFTY `ret20/63`, distance to EMA200, INDIA VIX level and z-score, breadth (% of universe above EMA200) | Lets the model learn *when* momentum works instead of hard-coding a BULL gate that measurably cost more than it saved |
| Liquidity | ADV rank, turnover trend, ₹-volume z-score | Impact proxy; also the axis `V5_V4_COMPARISON` flagged as never bucket-tested |
| Corporate-action proximity | sessions since/until a known ex-date | Prevents learning on the artefacts `adjust.py` documents |

**Explicitly forbidden:** anything using `t+1` or later data; anything normalised
on statistics fitted outside TRAIN; sector/index membership as known *today*
applied to 2012 (use `universe_by_date.parquet`).

### 6.5 Hyperparameters to search (LightGBM lambdarank)

| Parameter | Range | Note |
|---|---|---|
| `num_leaves` | 15 – 63 | Keep small. 31 is a sane default at this sample size |
| `min_data_in_leaf` | 200 – 3000 | **The most important regulariser here.** Large values force the model to find effects present in many stock-days |
| `learning_rate` | 0.02 – 0.05 | With early stopping on the purged inner fold |
| `num_boost_round` | ≤ 2000, early stop 100 | Let early stopping choose; do not fix it |
| `feature_fraction` | 0.4 – 0.8 | Financial features are collinear; aggressive subsampling helps |
| `bagging_fraction` / `freq` | 0.6 – 0.9 / 1 | Bag **by date**, never by row — row bagging leaks within-day structure |
| `lambda_l1` / `lambda_l2` | 0 – 5 / 1 – 50 | Lean on L2 |
| `lambdarank_truncation_level` | 5 – 20 | Set near the production top-N (5). This is the point of using lambdarank |
| `max_bin` | 63 – 255 | Lower = more regularisation |

Search with **Optuna, ~200 trials, objective = mean purged-CV rank IC**, on the
64 cores. Not a 300k grid: with ~106 independent blocks, 200 trials is already
enough optimisation pressure to overfit the CV, so also hold out the final TEST
period from the tuning entirely.

### 6.6 The step that translates IC into money — do not skip it

**Rank IC is not a result.** `dl_compare.py` and `dl_train.py` stop at IC and
decile tables; nothing has ever run the model's picks through `harness.py`. A
model with EVAL IC 0.048 and no backtest is an unverified claim.

Required final step for any rung that passes its gate:

```python
# add to harness.py STRATEGIES
def v6_model(a, j, reg) -> bool:
    return (a["sym"], a["dates"][j]) in _V6["keys"]   # top-5/day from predictions.parquet
```

Then run it through the **identical** harness — same next-open entry, same 0.30%
round trip, same gap>4% skip, same stop, same 20-session exit, same top-5/day, same
portfolio sim — so the only thing that differs from v4 is the ranking. That is the
comparison that decides anything.

---

## 7. Phase 5 — v6-size: meta-labelling (the highest expected value per unit of effort)

The evidence says selection is worth ~+0.30%/trade on test over random, while risk
sizing moved Calmar 0.43 → 0.61. **So point the model at sizing, not picking.**

- **Setup:** v4 (or v4-advanced) generates candidates as today. A classifier
  predicts `P(net_pct > 0)` for each candidate using features known at signal
  time. Output maps to a weight multiplier on top of `target_risk_pct / atr_pct`.
- **Model:** LightGBM binary, `max_depth` ≤ 4, ≤ 12 features, strong L2.
- **Sample:** 17,972 v4 trades — of which only **~1,722 are actually taken** by the
  ≤8-concurrent portfolio. **This is a tiny sample.** Train on all 17,972 signals
  (the label is well-defined for all of them), but evaluate on the taken set.
- **Validation:** purged CV by `entry_date`, 20-session embargo. Fewer than 20
  effective independent quarters — expect wide error bars and *say so*.
- **Gate:** must beat flat vol-target sizing on **TEST** Calmar (0.61 baseline) and
  must not increase maxDD. If it only helps on VAL, discard it.
- **Failure mode to watch:** the classifier learns the gap tilt that is already
  hard-coded, then double-counts it. Ablate: does the model add anything *given*
  the gap tilt is already applied?

Effort: 3 days. Realistic upside: Calmar 0.61 → 0.70–0.80. That is a larger, more
robust gain than the selection model is likely to produce.

---

## 8. Recommendation

**Build `v6 = v4 selection + learned rank blend + vol-target sizing with a learned
meta-label, on the Phase-0 bias-free CA-adjusted panel.**

Concretely, and in priority order:

| Priority | Work | Why this order | Expected gain |
|---|---|---|---|
| **1** | Phase 0 data foundation | Every prior verdict reversed when data changed, twice. Nothing else is trustworthy first. | Correctness, not performance |
| **2** | Phase 2 honest walk-forward of v4-advanced | The biggest measured win in the repo (Calmar 0.43→0.61) currently rests on a test look. Making it honest is cheap and either confirms the best result you have or exposes it. | Calmar 0.65–0.75 |
| **3** | Phase 5 meta-label sizing | Sizing has the demonstrated leverage; selection demonstrably has ~0.3%/trade. | Calmar → 0.70–0.80 |
| **4** | Phase 4 R2 (LightGBM lambdarank, cross-sectional target, purged CV) | The skipped rung, with the target fixed. Cheap: minutes to train. | OOS rank IC 0.02–0.05; **+0.2 to +0.5 %/trade** if it survives the harness |
| **5** | Phase 4 R3/R4 (add 1m microstructure, ensemble) | Answers whether the 7 GB of 1-minute data earns its keep — as an increment, bias-cancelled | Unknown; this is the actual open question |
| **6** | Phase 3 v5 multi-timeframe, time-boxed to 3 days | Closes a question rather than opening one | Most likely a documented negative |
| **7** | R5/R6 deep sequence models | Only if 5 pays off | Expected ~0 on current evidence |

**Blend, don't replace.** Final selection score = `0.5 · rank(v4_score) + 0.5 ·
rank(v6_pred)`, with the weight fitted on TRAIN and held. Reasons: v4 is the only
engine that has survived a bias-free CA-adjusted test; a rank blend degrades
gracefully if the model decays; and it makes the model's contribution measurable
as a weight rather than an all-or-nothing switch.

**What I would not do:** train a large sequence model, a transformer, or anything
sized to the GPU rather than to the data. The repo already ran that experiment and
the GRU tied a ridge regression. With ~106 independent time blocks, model capacity
is not the binding constraint and adding it converts a weak honest signal into a
strong dishonest one.

---

## 9. Results table to fill in — with gates set before measuring

Publish exactly this, whatever it says. Baselines are frozen from §3.

| Engine | Universe | TRAIN | VAL | **TEST** | win% | PF | CAGR% | maxDD% | **Calmar** | Verdict gate |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|---|
| **random 5/day, 20d hold** | bias-free | — | — | *(≈1.52)* | — | — | — | — | — | The real null. Nothing that fails to beat this ships. |
| **v4 frozen** | bias-free CA-adj | — | — | *(≈1.67–1.81)* | ~50 | ~1.38 | ~22 | ~−53 | ~0.43 | Baseline. Never re-tuned. |
| v4-advanced (walk-forward) | bias-free | | | | | | | | | Calmar > 0.61 **and** maxDD ≥ −30% |
| v5 best variant | bias-free | | | | | | | | | TEST ≥ 1.6 or closed permanently |
| v6-rank (R2) | bias-free | | | | | | | | | IC positive in ≥5/6 folds **and** TEST ≥ v4 + 0.2 |
| v6-rank + 1m (R3) | overlap subset | | | | | | | | | ≥ +0.01 IC over R2 on the same rows |
| v6-size (meta-label) | bias-free | | | | | | | | | TEST Calmar > v4-advanced, maxDD not worse |
| **v6 blend (proposed)** | bias-free | | | | | | | | | Must clear all of the above simultaneously |

Also report, because their absence is what made previous verdicts fragile:

- **IC mean ± std across all 6 CV folds**, plus per-fold signs.
- **Per-year TEST expectancy** (2023, 2024, 2025, 2026) — one good year can carry a
  whole test window.
- **Liquidity buckets** (ADV terciles) and **market-cap buckets** — flagged as
  "❓ not tested" in `V5_V4_COMPARISON` and still untested.
- **Cost sensitivity** at 0.30% / 0.50% / 0.70% round trip.
- **Delisted-name contribution:** what share of profit comes from names that later
  delisted? If it is large, the bias-free panel is doing real work; if it is zero,
  question the panel.
- **Turnover and capacity:** ₹ deployable before impact eats the edge.

---

## 10. Schedule

| Week | Phase | Deliverable |
|---|---|---|
| 1 (days 1–3) | 0 | Bias-free CA-adjusted panel, PIT eligibility, frozen splits, `dataset/splits.py` |
| 1 (days 4–5) | 1 + 2 start | `v4_frozen.json`; walk-forward search running on 64 cores |
| 2 (days 1–2) | 2 | `v4_advanced_walkforward.json` + plateau map |
| 2 (days 3–5) | 5 | Meta-label sizing model + purged CV + harness result |
| 3 (days 1–3) | 4 R0–R2 | LightGBM lambdarank, cross-sectional target, 6-fold purged CV, **through the harness** |
| 3 (days 4–5) | 4 R3–R4 | 1m increment measured bias-cancelled; 20-seed ensemble |
| 4 (days 1–3) | 3 | v5 multi-timeframe, time-boxed; publish result including a negative |
| 4 (days 4–5) | — | v6 blend, full results table, forward paper-trading harness armed |

Then — and this is the gate `V5_V4_COMPARISON` demanded and never got — **forward
paper validation behind a feature flag, v4 remaining the default**, for a
pre-committed window before any promotion.

---

## 11. Failure modes, named in advance

| Risk | How it shows up | Mitigation |
|---|---|---|
| Overfitting to ~106 independent blocks | High CV IC, TEST IC ≈ 0 | Purged multi-fold CV; ≥5/6 positive folds; capacity caps; seed ensembling |
| Survivorship bias re-entering through Track B | A 1m model posts a great number on 764 current names | Track B produces *increments* only, never standalone verdicts (§0) |
| Selection on full-period metrics | Exactly what `v4_advanced.csv` did | TRAIN-rank → VAL-select → single TEST look, enforced in code |
| Double-adjusting corporate actions | Series breaks silently; correlation to reference collapses | `adjust.py` default (empirical only) is correct — **[probed]** the 1m store is already split-adjusted. Never apply `price_factors` to either feed |
| Silently bridging the 2026-05-16 → 06-28 hole | 6-week gap treated as continuous | `panel/coverage.parquet` + hard failure |
| The ORB30 mirage | Filtered subsample looks great, paired comparison is −1.388 | Always evaluate as "ORB30 when available, open otherwise" vs "always open" |
| Confusing IC with P&L | A model ships on IC 0.05 and loses money | No rung passes without a `harness.py` run under identical rules |
| Mid/small-cap-only 1m panel | Model tuned on illiquid names, deployed on large caps | `largecap_missing` tag surfaces in every 1m result; capacity analysis mandatory |

---

## 12. What the data does *not* support, so don't plan for it

- **1-minute before 2018** for this universe — the Kaggle set starts 2018-01, and
  `DATA_INVENTORY.md` D1 records no vendor archive before 2012-01-02 at any price.
- **1-minute for delisted names** (D2) — vendors retire tokens on delisting. So a
  *bias-free intraday* study is not currently possible. This is the single
  structural limit on the whole ML plan, and it is why Track A must stay daily.
- **Tick / order-book** modelling (C3) — no data, no tooling.
- **The 6-week hole** cannot be recovered: NSE's 28-day rolling window has closed
  over it, and no free source reaches back.

If the C1 vendor purchase (2012→now, ~1B rows, ~22 GB) is ever made, the first
question to ask is §4.1 of `VENDOR_RFQ.md`: **does it include delisted symbols?**
If yes, Track A and Track B merge and R5/R6 become worth building. If no, this
plan's ceiling stands.
