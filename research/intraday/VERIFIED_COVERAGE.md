# Verified NSE intraday coverage (24 July 2026)

## Bottom line

There is no verified free/open source that supplies every NSE equity at
one-minute resolution from 2010 to the present. Combining sources improves
coverage, but it does not make the result complete or survivorship-free.

## Source map

| Source | Cost/access | Verified or documented intraday window | Scope | Suitable role |
|---|---|---:|---|---|
| [Kaggle NIFTY/BANKNIFTY archive](https://www.kaggle.com/datasets/nishanthsalian/indian-stock-index-1minute-data-2008-2020) | Free download | NIFTY 2008-01-01 to 2020-11-27; BANKNIFTY 2010-03-02 to 2020-11-27 | Two indices only | Historical index research |
| [Kaggle NIFTY stock archive](https://www.kaggle.com/datasets/debashis74017/stock-market-data-nifty-50-stocks-1-min-data) | Free download | Data card says 2015 to February 2022 and 5-minute sampling | Named stocks/indices, not all NSE | Partial mid-history stock coverage |
| [Kaggle Stock Market India](https://www.kaggle.com/datasets/hk7797/stock-market-india) | Free download | Starts in 2017; end must be measured from files | About 150 named stocks and 9 indices | Partial newer stock coverage |
| [nse1minR](https://github.com/ramamet/nse1minR) | Open repository | Repository describes 2013-2016 files | Variable stock/index coverage | Partial older community coverage |
| [Upstox V3](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/) | Account and token | Official minute/hour history from January 2022 | Supported active instruments | Primary recent backfill |
| [Dhan V2](https://dhanhq.co/docs/v2/historical-data/) | Account and token | Official last five years; maximum 90 days/request | Supported active instruments | Recent redundancy/backfill |
| [Yahoo via yfinance](https://ranaroussi.github.io/yfinance/reference/yfinance.functions.html) | No key; unofficial | Intraday limited to the most recent 60 days | Currently resolved symbols | Short recent sample/gap check |
| [Groww](https://groww.in/trade-api/docs/python-sdk/historical-data) | Account and token | Official last three months | Supported active instruments | Short recent redundancy |
| [Alpha Vantage](https://www.alphavantage.co/documentation/#intraday) | Historical intraday is premium | Provider claims 20+ years for global equities; NSE depth is unverified | Symbol-dependent | Test only after obtaining a key |
| [Zerodha Kite](https://kite.trade/docs/connect/v3/historical/) | Paid API/account | Documentation says several years, not a guaranteed 2010 start | Token-dependent | Optional broker source |
| [NSE historical order/trade data](https://archives.nseindia.com/content/press/Historical_order_Data_Tariff.pdf) | Paid exchange files | Historical, subject to quotation/agreement | Authoritative exchange files | Required route for defensible full-depth gaps |

## Locally verified datasets

> **Two distinct lakes exist on disk. Their statistics are NOT interchangeable
> and must never be summed.** Audit re-run and repair applied **25 July 2026**.
>
> | Lake path | Partitions | Rows | Symbols | Sources | Canonical dup keys |
> |---|---:|---:|---|---|---:|
> | `research/data/intraday_lake_stage_kaggle` (staged) | 284 | 2,171,980 | NIFTY, BANKNIFTY | Kaggle only | 0 |
> | `research/data/intraday_lake` (default) | 232 | 1,763,821 (post-repair) | NIFTY, BANKNIFTY, HDFCBANK.NS | Kaggle + Yahoo | 0 (was 7,125) |
>
> The earlier "2,171,980 unique index rows" figure is the **staged Kaggle lake**
> and is correct/clean. The **default lake** is a separate, smaller ingestion
> (a subset of the Kaggle index rows plus the Yahoo HDFCBANK sample); it is the
> lake the pipeline writes to by default and the one that carried the duplicate
> defect below.

### Staged Kaggle lake — `research/data/intraday_lake_stage_kaggle`

- Downloaded 26 CSV files (about 250 MB) with Kaggle dataset version 8.
- Raw consolidated inputs: 2,186,230 rows.
- Canonical unique output: 2,171,980 rows in 284 monthly Parquet partitions.
- NIFTY: 1,171,766 unique rows, 3,172 dates, from
  `2008-01-01 09:55 IST` through `2020-11-27 15:32 IST`.
- BANKNIFTY: 1,000,214 unique rows, 2,663 dates, from
  `2010-03-02 09:01 IST` through `2020-11-27 15:32 IST`.
- 2010 NIFTY: 96,683 rows across 251 dates, beginning 4 January.
- 2010 BANKNIFTY: 81,817 rows across 212 dates, beginning 2 March.
- Raw duplicate-key rows: 28,500; canonical duplicate keys after upsert: 0.
- Invalid/non-positive OHLC rows: 0.
- Rows flagged outside the broad 09:00-15:29 session boundary: 10,061.
- Volume is absent for every row. The dataset must not be used for
  volume-dependent signals without another verified source.

### Default lake — `research/data/intraday_lake`

Audited and repaired 25 July 2026 with
`python research/intraday/pipeline.py repair-lake --lake <abs path> --apply`.

- Contents: NIFTY + BANKNIFTY (subset of the Kaggle index rows) + the Yahoo
  HDFCBANK.NS sample. 232 monthly Parquet partitions.
- **Before repair:** 1,770,946 rows; 14,250 exact-duplicate rows (7,125
  duplicate canonical keys) — all inside the single partition
  `source=KAGGLE_NIFTY_BANK_2008_2020/symbol=NIFTY/year=2016/month=07`.
  Every partition was still stored under a legacy hash-suffixed filename.
- **Duplicate class:** exact — every duplicate key had identical OHLCV
  (0 conflicting keys). Nothing was averaged or discarded on conflict.
- **After repair:** 1,763,821 rows; 0 duplicate keys; 232 deterministic
  canonical files (`nifty-community.parquet`, `banknifty-community.parquet`,
  `sample.parquet`). A second dry-run reports 0 remaining duplicates
  (idempotent).
- **Recoverability:** the 232 superseded legacy files were **moved, not
  deleted**, to `research/data/intraday_lake/_quarantine/…` (mirrored partition
  tree); a `_repair_manifest_*.json` records before/after hashes, row counts,
  and timings.

### Yahoo HDFCBANK sample (inside the default lake)

- 2,625 one-minute rows for `HDFCBANK.NS`.
- Observed window: `2026-07-16 09:15 IST` through
  `2026-07-24 15:29 IST`.
- Duplicate, invalid-OHLC, non-positive-price, outside-session, and
  missing-volume counts: all zero.
- This sample verifies the adapter, not historical depth.

## Point-in-time constraints

- "All NSE stocks" requires a point-in-time security master that includes
  delisted securities, ticker changes, mergers, and instrument identifiers.
  A list of today's symbols introduces survivorship bias.
- NSE continuous trading began at 09:00 IST from 4 January 2010. The pre-open
  call auction began on 18 October 2010, after which the eligible cash-market
  continuous session starts at 09:15. Resampling must use date-aware session
  boundaries.
- Five-, ten-, fifteen-, thirty-, sixty-, 120-, and 300-minute bars should be
  derived only from selected canonical one-minute bars, per trading session.
  Daily bars must be derived per session, never across overnight gaps.

## Remaining hard gaps

1. No verified free one-minute equity archive for all NSE securities in
   2010-2012.
2. Community coverage in 2013-2021 is a changing subset, not a point-in-time
   complete universe.
3. Free broker APIs cover recent active instruments and require credentials.
4. Delisted securities and corporate-action-correct point-in-time identifiers
   remain unavailable from the identified free sources.

Therefore a claim of complete 2010-present, all-NSE, one-minute coverage
requires licensed exchange/vendor data. The open-source pipeline can still
produce an honest partial lake with explicit provenance and gap reports.
