# Independent Audit — Next-Day NSE Top-Gainer Prediction
**Date:** 2026-07-16 · **Auditor:** independent recomputation from raw CSVs, no reuse of prior model outputs
**Verdict (see §9): "Ranking signal, but not tradable"**

---

## 0. Scope note — files that could not be audited
`predict_next_day_gainers.py` and `next_day_gainers_prediction_report.xlsx` were **not found on this machine** (searched Documents, Desktop, Downloads, project repo). The claimed figures in §8 are therefore audited by *independent reconstruction*, not by code review. Everything below is recomputed from `nse_universe_5y_ohlcv.csv` + `nifty50_daily_5y.csv`.

## 1. Data audit
| Check | Result |
|---|---|
| Rows / symbols / dates | 813,798 / 751 / 1,238 (2021-07-15 → 2026-07-15) |
| Duplicates (date,symbol) | 0 |
| Nulls in OHLCVA | none |
| OHLC integrity (high<low, etc.) | 0 violations |
| Phantom trading dates | **5 found**: 2025-03-18, 2026-01-15, 2026-05-01, 2026-05-28, 2026-06-26 — 100% zero volume, 0% price change. These are NSE holidays emitted by Yahoo with stale prices. **Dropped (rule R1).** All four suspected dates confirmed. |
| Split/bonus handling | 27 symbols show adjustment-factor jumps (normal). **But 13 stock-days have |return|>40% where raw = adjusted return** — i.e. the corporate action was NOT adjusted: DIACABS −88% (2023-09-18), GPIL −79.5% (2024-01-01, 1:5 split), JSLL −78%, CGCL, MOTILALOFS, REDTAPE, ABFRL −66.6% (demerger 2025-05-22), VEDL −64.9% (demerger 2026-04-30), SKFINDIA −54.8%, STAR, QUESS, PARAS, TMPV. **Adjusted prices are NOT reliably adjusted for splits/demergers.** Rule R2: stock-days with |next-day return|>22% (NSE circuit max is 20%) are excluded from target ranking; they also pollute ~1 month of momentum features for those symbols (documented, not fixed — needs a proper corporate-action feed). |
| Survivorship bias | **Present and unfixable with this source.** Universe = today's 751 constituents pulled backward. 0 delisted symbols in file; 124 symbols begin after 2023-07-15 (IPOs). Long-only results are optimistically biased. |
| Top-gainer list reproducibility | 244/249 days match 10/10 exactly (98%). The 5 mismatch days are exactly the phantom dates (all-zero returns → alphabetical garbage rows: ACC, ACMESOLAR, APLAPOLLO…). **The gainer CSVs contain ~5 junk days; the rest reproduce.** |

## 2. Leakage controls applied (all enforced in `audit_2_model.py`)
- Features at T use only data ≤ close of T (rolling windows end at T; 20-day volume mean uses shift(1)).
- Target = T+1 adjusted close-to-close rank. Forward columns never enter features.
- Chronological splits: train ≤ 2024-07-12 · validation 2024-07-15→2025-07-14 · test 2025-07-15→2026-07-14 (untouched until models frozen).
- Scaler fit on train only; rank-blend weights and model choice made on validation only.
- Cross-sectional (within-date) feature ranks — no full-sample normalization.
- Monthly expanding walk-forward re-fit for stability check.
- Eligibility at T (close ≥ ₹5, volume > 0, traded ≥15 of last 20 days, ≥60d history) uses only T-visible data. Avg 650 eligible stocks/day.

## 3. Model comparison — FINAL TEST (2025-07-15 → 2026-07-14, 245 days)
Picks = top-10 by score daily. Net = T+1 open→close, equal-weight, 0.25% costs.

| Model | Prec@10 | Hits/day [95% CI] | ≥1 hit | c2o% | o2c% | net%/d | win% | MaxDD |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Random | 1.4% | 0.14 [0.10,0.19] | 13% | +0.15 | −0.11 | −0.36 | 34% | −60% |
| Chase yesterday's gainer | 6.4% | 0.64 [0.54,0.74] | 50% | +0.27 | −0.19 | −0.44 | 37% | **−68%** |
| Volume surprise | 5.6% | 0.56 [0.47,0.65] | 44% | +0.23 | −0.20 | −0.45 | 34% | −70% |
| Logistic (balanced) | 6.1% | 0.61 [0.52,0.70] | 50% | +0.37 | −0.25 | −0.50 | 34% | −72% |
| Ridge on fwd return | 3.1% | 0.31 [0.25,0.39] | 25% | +0.28 | −0.20 | −0.45 | 36% | −68% |
| **Gradient boosting** | **8.4%** | **0.84 [0.74,0.96]** | **60%** | +0.35 | −0.14 | −0.39 | 41% | −62% |
| Rank blend (val-tuned) | 7.5% | 0.75 [0.63,0.88] | 49% | +0.22 | −0.25 | −0.50 | 36% | −72% |

Validation ranking (GBM 0.74 > blend 0.62 > chase 0.60) selected GBM *before* test was opened; test confirmed the ordering. CIs: bootstrap over days (500 resamples).

## 4. Walk-forward stability (monthly expanding refit, GBM, test year)
Hits/day by month: 0.54, 1.11, 1.18, 0.57, 0.58, 0.77, 0.85, 0.95, 0.58, 1.05, 0.63, 0.62, 1.30 → **overall 0.82/day; every month beats random (0.14) — the ranking signal is stable.**
o2c%/day by month: −0.51, −0.21, +0.05, −0.26, −0.23, −0.14, −0.71, +0.34, −0.90, +0.75, −0.39, −0.26, +0.63 → **overall −0.16%/day before costs; sign flips month to month — the tradable return is NOT stable.**
Regime split: bull (21d Nifty up): 0.89 hits/day; bear: 0.79. o2c −0.14% in both. Signal survives regimes; profits don't exist in either.

## 5. Execution timing — where the "signal" lives (test, GBM picks)
| Leg | Mean return |
|---|--:|
| T close → T+1 open (overnight gap) | **+0.35%** |
| T+1 open → T+1 close (tradable intraday) | **−0.14%** |
| T close → T+1 close (what the target measures) | +0.21% |

**This is the central finding.** The model genuinely predicts next-day gainers 6× better than random — but the entire excess return happens in the opening gap, *before the first moment you can buy*. The prediction is generated after T's close; the earliest real fill is T+1 open, and from there the picks **lose** 0.14%/day before costs, −0.39%/day after 0.25% costs (−0.24 at 0.10%, −0.64 at 0.50%). The statistical signal is real; the tradable edge is negative.

## 6. Audit of the previously claimed figures
| Claim | Independent result | Verdict |
|---|---|---|
| Precision@10 ≈ 6.7% | Chase baseline: 6.4% (test); GBM: 8.4% | **Plausible — matches the chase baseline, not a skilled model** |
| ≈0.67 correct/day | Chase: 0.64 [0.54,0.74] | Reproduced within CI |
| Random ≈ 0.15/day | 0.14 [0.10,0.19] (analytic 10×10/650 = 0.154) | Reproduced |
| Net o2c ≈ −0.45%/day | Chase net: −0.44%/day | Reproduced |
| MaxDD ≈ −67.8% | Chase MDD: −68.1% | Reproduced |

The prior "model's" claimed performance is statistically indistinguishable from **"buy yesterday's top gainers"** — a zero-parameter baseline. It found the momentum-persistence effect and nothing more. Its own numbers (negative net, −68% drawdown) already said "don't trade this"; that conclusion stands.

## 7. Latest ranking audit (signal date 2026-07-15, walk-forward-trained GBM)
Top-10: PATANJALI, NUVOCO, PCJEWELLER, JUSTDIAL, ATHERENERG, HFCL, KALYANKJIL, GODREJIND, ELLEN, AEGISLOG.
Overlap with the claimed candidate list: **7/10** (claimed list also overlaps 6/10 with naive "chase" ranks). The claimed ranking is **broadly reproducible** and is, again, mostly a re-sort of 07-15's gainers. Expected hit rate if used: ~0.8 of 10 names correct; expected tradable return: negative. **Not buy recommendations.**

## 8. Corrected code
- `audit_1_data.py` — data-quality audit (reproduces §1)
- `audit_2_model.py` — leak-free pipeline, all models/baselines, walk-forward, costs, regimes (§3–5)
- `audit_3_latest.py` — walk-forward latest-day ranking (§7)
Copies saved alongside this report in Documents.

## 9. Conclusion — **"Ranking signal, but not tradable"**
1. Next-day top-gainer membership is *statistically* predictable well above chance (0.84 vs 0.14 hits/day; CIs disjoint; stable across 13 walk-forward months and both market regimes). The signal is mostly short-term momentum persistence plus volume/volatility character — which is why naive "chase" captures ~75% of it.
2. The predictable component is concentrated **overnight (close→open)**, which an after-close prediction cannot buy. The tradable leg (open→close) is negative before costs and worse after: **−0.39%/day at realistic costs, 37–41% daily win rate, ~−62% max drawdown.**
3. Data caveats that bound any stronger claim: survivorship-biased universe (results are *optimistic*), 13 unadjusted corporate actions, approximate turnover, no delivery %, 5 phantom dates (now removed).
4. Anything claiming profitability on this dataset should be presumed to be leaking the overnight gap or the T+1 close into its features until proven otherwise.
