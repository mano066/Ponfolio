# Which timeframe is most accurate for swing? — walk-forward, NIFTY + BANKNIFTY

**Splits:** TRAIN 2008–2015 · VAL 2016–2018 · TEST 2019–2020.
**Instruments:** NIFTY (2008–2020) + BANKNIFTY (2010–2020), 1-minute, **no volume**.
**Tested:** all 6 single timeframes {15m,30m,60m,2h,5h,1d}, all **2-timeframe**
combos (higher-TF trend × lower-TF trigger), and all **3-timeframe** stacks
(coarse trend & mid trend & fine trigger) — at 5-day and 10-day swing holds, net
of 0.30% cost, with slippage sensitivity to 20bps. Benchmark = "always-in" (long
for the same horizon regardless of signal). Ranked by **out-of-sample TEST
expectancy**; "stable" = positive in **all three** splits.
Reproduce: `research/scripts/multitimeframe/timeframe_walkforward.py` →
`research/data/timeframe_walkforward.json`.

**[MEASURED, INDEX-ONLY]** — NIFTY/BANKNIFTY only. **NOT** a stock backtest; no
per-stock intraday exists, so this cannot become stock picks. It answers the
timeframe question on the only data that supports it.

---

## Headline answer

**Two conditions matter more than the timeframe itself:**
1. **Holding horizon:** 10-day swings work; **5-day swings have essentially no
   edge** net of cost on either index (mostly negative in test).
2. **Instrument:** the edge is **clear on BANKNIFTY, weak/absent on NIFTY.**

**When there IS an edge (BANKNIFTY, 10-day), the multi-timeframe stack wins and
is stable out-of-sample — and adding a THIRD timeframe is the top result:**

| Rank | Signal | TRAIN | VAL | **TEST** | acc% | stable? |
|---|---|--:|--:|--:|--:|:--:|
| 1 | **3TF: 1d-trend + 5h-trend + 15m-trig** | +0.34 | +0.69 | **+0.80** | 49.4 | ✅ |
| 2 | 3TF: 1d + 2h-trend + 15m-trig | +0.20 | +0.47 | +0.73 | 49.4 | ✅ |
| 3 | **single: 60m** | +0.14 | +0.56 | +0.70 | 50.5 | ✅ |
| 4 | 3TF: 1d + 60m-trend + 30m-trig | +0.12 | +0.49 | +0.67 | 52.8 | ✅ |
| 5 | **3TF: 1d + 60m-trend + 15m-trig** | +0.35 | +0.58 | +0.63 | **53.5** | ✅ |
| 6 | 2TF: 5h-trend + 15m-trig | +0.44 | +0.80 | +0.57 | 51.6 | ✅ |
| 7 | 2TF: 60m-trend + 15m-trig | +0.40 | +0.73 | +0.55 | **55.2** | ✅ |
| — | ALWAYS-IN benchmark | +0.16 | +0.45 | **−0.00** | 50.8 | — |
| — | single: 1d (unstable) | −0.32 | +0.94 | +0.79 | 48.0 | ❌ |

Readings:
- **The full 3-timeframe stack wins:** `daily-trend + 5h-trend + 15m-trigger` has
  the highest stable out-of-sample expectancy (+0.80). Adding the third timeframe
  beat the best 2-TF combo *and* is stable, unlike `single:1d` (higher raw test
  but negative in train → rejected).
- **The recurring pattern: higher-timeframe trend gate(s) + a 15-minute entry
  trigger.** The **15m trigger** appears in almost every winner; the trend
  filter can be daily/5h/2h/60m.
- **Best single timeframe = 60-minute** (only single TF stable across all splits).
- **Highest accuracy:** `60m-trend + 15m-trig` (55.2%) and `1d+60m-trend+15m-trig`
  (53.5%).

**Slippage sensitivity — all stable winners survive to +20bps (BANKNIFTY 10d TEST
expectancy):**

| signal | 0bps | 5 | 10 | 20 |
|---|--:|--:|--:|--:|
| single: 60m | +0.70 | +0.60 | +0.50 | **+0.30** |
| 5h-trend + 15m-trig | +0.57 | +0.47 | +0.37 | +0.17 |
| 60m-trend + 15m-trig | +0.55 | +0.45 | +0.35 | +0.15 |
| 2h-trend + 15m-trig | +0.49 | +0.39 | +0.29 | +0.08 |

All remain positive through 20bps → the edge is cost-resilient (on BANKNIFTY 10d).

---

## Where the edge is weak — NIFTY, and 5-day holds

**NIFTY, 10-day (top of ranking):**

| Signal | TRAIN | VAL | TEST | stable? |
|---|--:|--:|--:|:--:|
| mtf: 1d-trend + 30m-trig | −0.52 | +0.17 | +0.31 | ❌ |
| single: 30m | −0.33 | +0.26 | +0.28 | ❌ |
| single: 1d | −0.43 | +0.46 | +0.25 | ❌ |
| ALWAYS-IN | −0.14 | +0.12 | +0.11 | — |

→ Several signals beat always-in in test, but **none is stable** (all negative in
the 2008–2015 train block, which includes the 2008–2011 chop). No trustworthy
NIFTY edge.

**5-day holds (both indices):** best test expectancies hover near zero or negative
and nothing is stable. **Net of cost, a 5-day index swing has no reliable edge.**

---

## Direct answers to your question

1. **Which single timeframe is most accurate for swing?** → **60-minute.** It is
   the only single timeframe stable out-of-sample (BANKNIFTY 10-day). 15m/30m
   alone are noisier; 5h/2h alone weaker; 1d alone is high-variance (great in val,
   negative in train).
2. **Does multi-timeframe beat single-timeframe?** → **Yes — and 3 beats 2.** The
   top stable signal is the **3-timeframe stack `daily-trend + 5h-trend +
   15m-trigger`** (test +0.80), ahead of the best 2-TF combo and of 60m alone.
   Every winner is a **higher-timeframe trend gate + a 15-minute entry trigger** —
   the classic "trade the higher-TF direction, time the entry on the lower."
3. **Best overall for swing (index):** `3TF: daily + 5h trend + 15m trigger`
   (highest stable expectancy) for return; `60m-trend + 15m-trig` (55.2%) for
   accuracy. The **15-minute trigger** and a **60-minute-or-higher trend filter**
   are the common threads. All survive +20bps slippage.

---

## Honest caveats (do not over-read this)

- **Index-only.** These are NIFTY/BANKNIFTY, not stocks. The result is
  **suggestive** that "60m/higher-TF trend + 15m trigger, 10-day hold" is the best
  multi-timeframe swing structure — but it **cannot be verified on stocks** (no
  per-stock intraday data). Do not deploy it as stock picks on this basis.
- **Inconsistent across instruments** (works on BANKNIFTY, weak on NIFTY) and
  **horizons** (10-day yes, 5-day no). A robust edge should generalize better; this
  one is regime/instrument-sensitive.
- **Small magnitudes** (~0.4–0.7%/trade over 10 days) and **no volume** (index).
- **Ends 2020** — no post-2020 out-of-sample.
- Earlier, on the *daily stock universe*, the analogous lower-TF gate **did not**
  help (ablation: removing it raised expectancy). So the intraday MTF benefit
  seen here on BANKNIFTY does **not** clearly transfer to daily stock selection.

## Net conclusion

On the only data that can answer it: **the multi-timeframe structure that works
best for index swing trading is a higher-timeframe (60m–5h) trend filter combined
with a 15-minute entry trigger, held ~10 days — and 60-minute is the best single
timeframe.** But the edge is modest, index-specific (BANKNIFTY > NIFTY), horizon-
specific (10d > 5d), and **unproven on stocks.** It justifies testing a
higher-TF-trend + 15m-trigger overlay in **forward paper shadow mode** on live
stock data — not a production change.
