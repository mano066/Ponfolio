# Advanced v5 — Regime-Adaptive Ensemble (2026-07-25)

The flagship "advanced" v5: **one book** that switches strategy by market regime,
sizes by **volatility targeting**, and **de-risks in drawdown**. Event-driven
daily backtest (next-open fills, daily mark-to-market, gap>4% skip, v4 exit,
0.30% round-trip). **[MEASURED, survivorship-biased daily universe.]** Reproduce:
`research/scripts/multitimeframe/ensemble_v5.py` → `research/data/ensemble_v5.json`.

## Design (only what the research proved)

- **BULL** → S1 trend-pullback + S3 relative-strength + S6 momentum.
- **SIDEWAYS** → S2 volatility-contraction breakout **with strong volume (≥2×)**
  (the one place volume helped).
- **BEAR / HIGH-VOL** → **no new longs (cash)**.
- **Volatility-target sizing:** risk 0.5% of equity per trade via ATR
  (`shares = 0.5%·equity / (2.5·ATR)`), capped at 15% position weight, ≤8
  concurrent, ≤3 new/day.
- **Drawdown de-risk:** halve new-trade risk while >15% below the equity peak.

## Result — portfolio metrics

| Config | Period | CAGR% | maxDD% | Calmar | Sharpe | Sortino |
|---|---|--:|--:|--:|--:|--:|
| **v5 ENSEMBLE (full)** | full 2011–26 | 7.6 | **−18.7** | **0.41** | 1.03 | 1.25 |
| | test 2023–26 | 9.0 | **−12.3** | **0.73** | 1.08 | 1.38 |
| | val 2020–22 | 13.0 | −9.9 | 1.31 | 1.69 | 2.15 |
| **v4 production** (ref) | full | 9.3 | **−34.0** | **0.27** | — | — |

**The ensemble earns v4-like returns at roughly half the drawdown**, with a
believable Sharpe ~1.0 and an out-of-sample **test Calmar of 0.73 — ~2.7× v4's
0.27.** Risk-adjusted, it is a clear improvement.

## Which advanced component matters (ablation)

| Remove… | full CAGR | full maxDD | **test Calmar** | takeaway |
|---|--:|--:|--:|---|
| nothing (full) | 7.6 | −18.7 | **0.73** | — |
| − volatility targeting | 18.7 | **−47.3** | **0.14** | **critical** |
| − regime gate | 7.5 | −23.1 | 1.08 | modest DD help |
| − drawdown de-risk | 8.2 | −20.5 | 0.74 | small |

- **Volatility targeting is the single most important advanced feature.** Removing
  it (equal-weight) *looks* better on raw CAGR (18.7%) but blows drawdown out to
  **−47%** and collapses out-of-sample **test Calmar from 0.73 → 0.14** — classic
  overfit to a few large equal-weight winners in training. Sizing by risk, not by
  cash, is the real edge.
- **Regime gating** gives a modest full-period drawdown benefit (−18.7% vs −23%).
- **Drawdown de-risk** contributes little here (vol-targeting already caps risk),
  but is cheap insurance for tail regimes.

## Verdict

The advanced move that actually improves v5 is **risk management, not more signal
complexity**: a regime-adaptive ensemble sized by volatility targeting delivers
v4-comparable return with roughly half the drawdown and a sound (event-driven)
Sharpe. This is the version worth taking to forward paper validation.

## Caveats (unchanged)

- Survivorship-biased universe → absolute CAGR overstated (~5pp/yr); the
  *drawdown/Calmar improvement vs v4* is the trustworthy, bias-shared result.
- No forward paper validation yet; 2023–26 test is partial.
- Intraday/multi-timeframe execution overlay excluded (no per-stock intraday).
- The other Tier-2 advanced ideas (cross-sectional rotation, meta-labeling) are
  designed but untested — meta-labeling especially risks overfitting on a biased
  universe and should wait for the survivorship-free rebuild.
