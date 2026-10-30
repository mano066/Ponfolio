# The measurement rig — survivorship-free panel + random-picker null

Built 2026-07-30. This is the thing whose absence blocked every promotion
decision in this repo. It is committed on purpose (see "Why this is in git").

---

## What was wrong with every earlier number

Two independent defects, both fatal on their own:

**1. Survivorship bias.** Every prior study ran on `research/data/nse_universe_*_ohlcv.csv.gz`,
built by pulling *today's* symbol list backward through yfinance. Names that
delisted, got acquired, or were renamed simply do not appear. Measured on the
new panel: of 4,243 symbols that traded between 2010 and 2026, **3,528 (83%) are
absent from today's universe**, and **1,479 ISINs stopped trading before
2026-07**. Those studies were run on the survivors.

**2. No null hypothesis.** Engines were only ever compared to each other. A rule
that buys liquid Indian equities in a rising market makes money because the
market rose. Without a random picker drawing from the same pool, "v4 makes
+1.58%/trade" is not evidence that v4 *selects* anything.

---

## The two artifacts

### 1. Point-in-time universe — `universe_builder.py`

Source: NSE's own daily equity bhavcopies, fetched with `curl_cffi`
(browser-TLS impersonation, which passes NSE's bot wall). Each bhavcopy is the
exact set of instruments that **traded that day**, so unioning across dates
captures delisted names, renamed tickers and series changes. Keyed by **ISIN**,
a stable instrument id that survives symbol changes.

Handles both NSE formats automatically: legacy `cmDDMONYYYYbhav.csv.zip` up to
2024-07-05, UDiFF `BhavCopy_NSE_CM_*.csv.zip` from 2024-07-08.

```powershell
python research/scripts/v5/universe_builder.py sample    # 8 dates, both formats
python research/scripts/v5/universe_builder.py build --start 2010-01-01 --end 2026-07-30
```

Measured output (build of 2026-07-30, ~70 min, 4,325 weekday dates):

| | |
| --- | --- |
| Panel rows | 7,487,952 |
| Trading days | 4,092 (233 holidays/missing, never fabricated) |
| ISINs | 4,777 — of which **1,479 delisted** before 2026-07, **453 renamed** |
| Usable for signals (≥260 bars) | 3,849 |
| Range | 2010-01-04 → 2026-07-29 |

Compare: production scans a 751-name current-membership universe. The research
panel is 5× broader *and* includes the names that died.

### 2. Selection harness — `harness.py`

```powershell
python research/scripts/v5/harness.py --hold 14,20,40 --rand 20 --engines v4,v4.1
```

Fixed rules, identical for every engine and for the null:

| Parameter | Value | Note |
| --- | --- | --- |
| Entry | open of the bar **after** the signal | no same-bar fill |
| Exit | 2.5-ATR close stop, filled at the **next open**, else close of bar `hold` | v4's own exit |
| Cost | 0.30% round trip | as in every prior study |
| Picks/day | 5 | matches production |
| Gap filter | skip if it opens >4% above the signal close | as in production |
| Warm-up | 260 bars before a symbol is tradeable | |
| Splits | TRAIN 2011-19, VAL 2020-22, TEST 2023-26 | chronological, no shuffling |

**`rand:N` — the null.** N independent uniform-random pickers draw 5 names/day
from the *same* eligible pool the engines rank, and run through the *same*
entry, exit, cost and gap filter. Every engine result is reported as a
percentile of that distribution. An engine has a selection edge only where its
TEST expectancy exceeds the random **p95** — not merely the mean.

The null deliberately ignores engine signals. Sampling only signalled bars
would inherit the engine's own selection and make the comparison circular;
`test_harness.py` asserts this directly.

**`--hold`** sweeps the exit horizon. Production holds **14** trading days, the
old studies used **20**, and the one finding that replicated on *random* pickers
(8 of 9 cells) pointed at **40**. That finding is engine-independent, so it is
worth more than any ranking change and is measured here first.

---

## First results (2026-07-30)

20 random pickers, TEST = 2023-26. `harness_results.json` has the full grid.
Percentile is the engine's position in the random distribution for that split.

| hold | engine | TRAIN 2011-19 | VAL 2020-22 | TEST 2023-26 |
| --- | --- | --- | --- | --- |
| 14 | **v4** | 1.050 (p100) | 0.817 (p35) | 0.195 (**p40**) |
| 14 | v4.1 | −0.556 (p0) | −0.038 (p0) | 0.442 (p95) |
| 14 | *rand mean* | *−0.095* | *0.871* | *0.254* |
| 20 | **v4** | 1.944 (p100) | 1.727 (p80) | 1.399 (p100) |
| 20 | v4.1 | −0.625 (p0) | 0.097 (p0) | 0.828 (p100) |
| 20 | *rand mean* | *0.139* | *1.562* | *0.564* |
| 40 | **v4** | 5.087 (p100) | 2.879 (**p5**) | 4.710 (p100) |
| 40 | v4.1 | −0.431 (p0) | 0.614 (p0) | 1.898 (p85) |
| 40 | *rand mean* | *0.773* | *3.538* | *1.675* |

Scale: 2,975,627 eligible bars over 3,463 dates; ~9,100 TRAIN / ~3,700 VAL /
4,350 TEST trades per engine.

### 1. Hold length is the finding. Production's 14 is the worst setting tested.

Expectancy rises monotonically with hold in **every** cell — both engines, the
random null, all three splits. 18 of 18. And it survives normalising away the
exposure confound (a 40-day hold is ~3× the time in market of a 14-day one):

| TEST, per day-in-market | v4 | v4.1 | rand |
| --- | --- | --- | --- |
| hold 14 | 0.0139 | 0.0316 | 0.0181 |
| hold 20 | 0.0700 | 0.0414 | 0.0282 |
| hold 40 | **0.1177** | 0.0475 | 0.0419 |

There is a mechanical reason to expect this, which is why it replicates on
random pickers: with a **fixed** 2.5-ATR stop, lengthening the hold extends the
upside window without extending the downside — the stop either triggers or it
does not. v4's win rate actually *falls* as hold grows (46.7% → 46.8% → 45.9% in
TRAIN; 42.7% → 41.8% → 40.5% in TEST) while expectancy rises 24×. The gain is
entirely a fatter right tail: let winners run, cut losers at the same stop.

The cost is capital, not return: at 5 picks/day a 40-session hold implies ~200
concurrent positions versus ~70 at 14. That is a position-sizing and capacity
question, not a reason the expectancy is wrong.

### 2. At production's hold, v4 does not beat a coin flip.

v4 at hold 14 scores **p40 in TEST** — below the random median (0.195 vs 0.254).
This corroborates, on survivorship-free data with a real null, the earlier
conclusion that v4's selection edge was not what it appeared.

### 3. v4's edge at longer holds is real but regime-dependent.

At holds 20 and 40, v4 is p100 in TRAIN *and* TEST — genuinely above all 20
random pickers. But VAL is erratic: p35, p80, then **p5 at hold 40**, i.e. below
the 5th percentile of random through 2020-2022. A rule reading p100 / p5 / p100
across three consecutive periods has not demonstrated a durable edge; it has
demonstrated sensitivity to regime. That is exactly what VAL is for.

### 4. v4.1 is refuted.

**Percentile 0 in both TRAIN and VAL, at every hold** — worse than all 20 random
pickers across 2011-2022 (~12,800 trades), with negative expectancy and profit
factor 0.79-0.90. It is positive only in TEST. A rule that loses to random for
twelve years and wins for three has not shown an edge; the TEST result is the
anomaly.

The two features' information coefficient was real and replicated 6/6 folds
twice. It did not convert into a profitable ranking. **IC is not P&L**, and this
is the measurement that settles it. v4.1 stays reachable via the engine toggle
for inspection and is labelled REFUTED in `main.py`; it must not be promoted on
the strength of the IC study.

### What this does not say

Nothing here endorses raising production's hold to 40 sessions. The result is
consistent, mechanically explicable and survives the exposure adjustment, but it
rests on **raw, split-unadjusted prices**, and a longer hold spans more
corporate actions per trade — so the longest holds absorb the most of this rig's
known bias. Confirming the direction needs the corporate-action master. What can
be said now: 14 sessions is the worst of the three tested, for every engine and
for random selection alike, and the 14-day desk was never measured against a
null before.

---

## Verification

`research/scripts/v5/test_harness.py` — 12 tests, no network. What they pin:

- **No lookahead**: entry is the open *after* the signal bar; ranks are computed
  within a single date's cross-section, never across dates.
- **Exit arithmetic**: time exit uses the close of bar `hold`; a stop detected on
  a close fills at the *following* open, never at the stop price itself (which
  would flatter every result); a hold running past a delisting is truncated, not
  silently dropped.
- **Null fairness**: reproducible per seed, varies across seeds, draws only from
  the eligible pool, and still trades when no engine signals exist.
- `--hold` actually reaches the exit — if it were ignored two different holds
  would score identically.

---

## The caveat that bounds every number

**Bhavcopy OHLCV is RAW — not adjusted for splits or bonuses.** A 1:2 split
inside a hold window reads as a ~-50% return. This depresses engines and the
random null roughly equally, so **column comparisons and percentiles are usable
while absolute expectancies are biased downward**. Do not quote an absolute
expectancy from this rig as a return estimate.

Fixing it needs the corporate-action master, which `dataset/DATA_INVENTORY.md`
lists under "Not found yet" — two likely NSE URLs 404'd and the endpoint still
needs discovery. That is the single highest-value remaining data task.

Also: the Nifty benchmark series (`nifty50_daily_2010.csv`) ends 2026-07-17, so
the last ~9 trading days of the panel have no relative-strength reference and
cannot produce a signal. Harmless at this scale; the harness prints the range.

---

## Why this is in git

The predecessor of this rig was written, produced the most valuable findings in
the project, and was **lost because it was never committed**. Everything
reproducible is now tracked:

- `universe_builder.py`, `harness.py`, `test_harness.py`, `bias_free_compare.py`
- `harness_results.json` — the machine-readable results

Deliberately **not** tracked (`.gitignore`): `research/data/*.parquet` (the
180 MB panel — over GitHub's 100 MB limit) and `research/data/bhavcopy_cache/`
(3,657 zips). Both rebuild from the committed builder in ~70 minutes, which is
the right trade. The irreplaceable data — intraday sessions that fall outside
NSE's ~20-session window — lives in `dataset/store/` and *is* versioned, for
exactly the reason stated in `dataset/.gitignore`.
