# Top-Gainer Prediction Research (2026-07)

Question investigated: **can end-of-day data predict tomorrow's NSE top-10 gainers, and is that tradable?**

Verdict (full details in [next_day_gainers_AUDIT_REPORT.md](next_day_gainers_AUDIT_REPORT.md)):
**"Ranking signal, but not tradable."** Best model catches 0.84/10 next-day gainers vs 0.14 random,
but the predicted gain sits in the overnight gap (close→open, +0.35%) which an after-close prediction
cannot buy; the tradable open→close leg loses −0.39%/day after 0.25% costs, max drawdown ~−62%.

## data/ (snapshots as of 2026-07-15 close, Yahoo Finance)
| file | contents |
|---|---|
| `nse_universe_5y_ohlcv.csv` | 813,798 rows — 751 Nifty Total Market stocks × 5y daily OHLCV, adjusted close, approx. turnover. **Caveats:** survivorship-biased (today's constituents only), 13 unadjusted corporate actions, 5 phantom holiday dates (see audit report §1), no delivery %. |
| `nifty50_daily_5y.csv` | Nifty 50 index daily OHLCV, same window |
| `top_gainers_1y.csv` | daily top-10 gainers, 1y, with next-day/next-5d returns |
| `top_gainers_windows.csv` | each gainer event + 1-month before/after summary metrics |
| `gainers_daily_close.csv` | per-event daily closes, t−30…t+30 around each spike |
| `gainers_daily_indexed.csv` | same, indexed to 100 at spike day |

## scripts/ (regenerate any dataset; run with any Python with pandas+yfinance, sklearn for audits)
- `full_universe_5y.py`, `gainers_1y.py`, `gainers_windows.py`, `gainers_daily.py`, `top_gainers.py` — dataset builders
- `score_gainers.py` — runs production swing scorer on given tickers
- `audit_1_data.py` — data-quality audit · `audit_2_model.py` — leak-free model comparison, walk-forward, costs · `audit_3_latest.py` — latest-day ranking

Scripts resolve paths from the repository root (`ROOT`), so they run from any checkout. Raw price downloads such as `nse_universe_*` and `nifty50_daily_*` are not committed (third-party data); the dataset builders above regenerate them.
