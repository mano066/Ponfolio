# Data inventory — what exists, what is free, what costs money

Measured 2026-07-27. Every "reachable" claim below was probed, not assumed.

---

## A. HAVE — on disk and verified

| # | Dataset | Coverage | Volume | Size | Source | Quality |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | **Daily OHLCV**, 750 symbols | 1995-01-05 → 2026-07-27 | 2,922,116 bars | 95 MB | NSE charting (exchange-direct) | Unadjusted, 0 dupes, 0 OHLC violations |
| A2 | **1-minute OHLCV**, 750 symbols | 2026-06-29 → 2026-07-27 (21 sessions) | 5,407,130 bars | 122 MB | NSE charting | Reconciles to daily at 100% on O/H/L, 99.9–100% volume |
| A3 | Universe constituents | as of 2026-07-27 | 751 rows | 49 KB | NSE index CSV | Company, industry, series, ISIN |
| A4 | Token map | current | 750 rows | 43 KB | NSE symbol search | 750/751; miss is `DUMMYTRVN`, NSE's own placeholder |

### Also in the repo, from earlier work (`research/data/`) — usable but flawed

| # | Dataset | Coverage | Volume | Source | Known problems |
| --- | --- | --- | --- | --- | --- |
| A5 | `nse_universe_2010_ohlcv.csv.gz` | 2010 → 2026-07-17 | 2,110,297 rows | yfinance | **Survivorship-biased** (today's names pulled backward), adjusted-close only, 13 unfixed corporate-action rows |
| A6 | `nse_universe_10y_ohlcv.csv.gz` | ~2016 → 2026 | 40 MB | yfinance | same caveats |
| A7 | `nifty50_daily_*.csv`, `signals_*.csv.gz` | various | — | derived | downstream of A5/A6, inherits their bias |

**A1 supersedes A5/A6** for most purposes: exchange-direct rather than Yahoo, unadjusted,
15 years deeper, and validated. A5 is still the only file with the *derived signal columns*.

---

## B. FREE AND REACHABLE — verified, not yet fetched

| # | Dataset | Coverage | Effort | Why you'd want it |
| --- | --- | --- | --- | --- |
| B1 | **Bhavcopy point-in-time universe** | verified back to **1996** | ~30 min download | **Fixes survivorship bias.** On 2010-01-04, 1,223 EQ symbols traded; 939 (77%) are absent from today's list. Every study on A5 is running on the 23% that survived. |
| B2 | **Bhavcopy daily OHLCV incl. delisted** | 1996 → now | same download as B1 | Daily prices for names that no longer exist — impossible via A1, which only knows current symbols |
| B3 | **Index OHLCV** (NIFTY 50, BANK, IT, …) | **1990-07-03** → now, 8,765 bars | one command | Benchmark/regime series, deeper than any equity |
| B4 | Weekly `1w` / Monthly `1M` bars | 1995 → now | `backfill_eod.py --interval 1w` | Higher-timeframe context |
| B5 | F&O instruments | tokens resolve (`RELIANCE26AUGFUT`) | untested depth | Futures basis, rollover studies |
| B6 | 5m/10m/15m/30m/1h intraday | same 28-day window as 1m | — | **Redundant** — derive from A2 with `load.resample()` instead |

### Not found yet
| Item | Status |
| --- | --- |
| Corporate-action master (splits/bonus) | Two likely URLs 404'd. Endpoint needs discovery — required to adjust A1/B2 correctly |

---

## C. MUST BUY — **nothing here exists on disk. 0 bytes.**

These rows describe data you could *acquire*. The sizes are **estimates of what
a delivery would be**, calculated so vendors can quote against a real scope —
not measurements of anything you own. Contrast with section A, where every
number was measured from actual files.

| # | Dataset | Coverage *if bought* | Est. size *if bought* | Vendor | **What exists today** |
| --- | --- | --- | --- | --- | --- |
| C1 | 1-minute OHLCV | 2012-01-02 → now | ~1.0B rows / ~22 GB | TickData (deepest found) | **No data.** Only tooling: `VENDOR_RFQ.md` 6.7 KB, `VENDOR_EMAIL.md` 3.1 KB, `ingest_vendor.py` 22 KB |
| C2 | 1-minute OHLCV | ~3 years back | ~4 GB | Kite Connect (historical add-on) | **No data, no loader.** Integration exists at `stock_app/backend/kite_client.py`; backfiller not written |
| C3 | Tick / order-book | varies | very large | TickData, GDFL | **No data, no tooling.** Only for sub-minute execution modelling |

C1 is a purchase order, a receiving dock and a quality inspector — all built and
tested. No shipment has been ordered. To turn it into real data:

```powershell
# 1. send VENDOR_EMAIL.md + VENDOR_RFQ.md, receive a sample
python ingest_vendor.py --path <sample> --profile auto --commit
python ingest_vendor.py --validate --dest 1m_vendor    # exit 0 = pay, 2 = do not
```

Until a vendor delivers, `store/intraday/1m_vendor/` does not exist.

---

## D. DOES NOT EXIST AT ANY PRICE

| # | Dataset | Why |
| --- | --- | --- |
| D1 | 1-minute **2010 → 2012** for the full universe | No vendor archive found starting before 2012-01-02 |
| D2 | 1-minute for **delisted** symbols | Vendors retire instrument tokens on delisting; ask §4.1 before assuming |
| D3 | 1-minute from NSE beyond 28 days | Hard server cap: all six intraday timeframes share one rolling ~20-session window. Explicit older windows return empty; backward paging fails on page 1 |

---

## The gap, stated plainly

| Resolution | 2010 → 2012 | 2012 → 2026 | 2026-06-29 → now |
| --- | --- | --- | --- |
| **Daily** | HAVE (A1, back to 1995) | HAVE | HAVE |
| **Daily, survivorship-free** | free via B1/B2 | free via B1/B2 | free via B1/B2 |
| **1-minute** | **impossible (D1)** | **buy (C1)** | HAVE (A2), growing daily |

The only genuinely unreachable cell is 1-minute before 2012. Everything else is
either already on disk, one command away, or purchasable.
