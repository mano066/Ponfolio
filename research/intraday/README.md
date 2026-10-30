# NSE intraday multi-source lake

This directory is the acquisition and audit layer for the requested
2010-to-present NSE intraday research.

## Non-negotiable coverage rule

No current free source covers every NSE equity at one-minute resolution from
2010 to the present. The pipeline therefore stores every row with its source,
timestamp, symbol, adjustment status, ingest time, and quality flags. It never
fills an uncovered historical range with a different timeframe and never
describes a union of partial datasets as complete.

The current evidence-backed source windows are maintained in
`source_catalog.json`; measured local results are in
`VERIFIED_COVERAGE.md`. Run:

```powershell
backend\.venv\Scripts\python.exe research\intraday\pipeline.py catalog
backend\.venv\Scripts\python.exe research\intraday\pipeline.py plan --start 2010-01-01 --scope equity
```

## Canonical schema

All adapters normalize into these columns:

`timestamp_utc, timestamp_ist, symbol, instrument_id, exchange, interval,
open, high, low, close, volume, source, source_file, adjusted,
ingested_at_utc, quality_flags`

The raw lake is partitioned by source, symbol, year, and month. Each Parquet
part has a JSON manifest containing row count, date range, and a SHA-256 digest.

## Real-source commands

Recent Yahoo sample with no credentials:

```powershell
backend\.venv\Scripts\python.exe research\intraday\pipeline.py fetch-yahoo HDFCBANK.NS --period 7d --interval 1m
```

Download a catalogued Kaggle dataset (requires `kagglehub`):

```powershell
backend\.venv\Scripts\python.exe -m pip install kagglehub
backend\.venv\Scripts\python.exe research\intraday\pipeline.py download-kaggle kaggle_nifty_bank_2008_2020
backend\.venv\Scripts\python.exe research\intraday\pipeline.py ingest-kaggle-index
```

Import a normalized or hand-cleaned community CSV:

```powershell
backend\.venv\Scripts\python.exe research\intraday\pipeline.py import-csv HDFCBANK.NS path\to\file.csv --source kaggle_stock_market_india_2017 --timestamp-col timestamp
```

Alpha Vantage month test (premium key and NSE coverage verification required):

```powershell
$env:ALPHAVANTAGE_API_KEY='...'
backend\.venv\Scripts\python.exe research\intraday\pipeline.py fetch-alpha HDFCBANK.NS --month 2010-01 --interval 1min
```

Upstox (instrument key example is illustrative):

```powershell
$env:UPSTOX_ACCESS_TOKEN='...'
backend\.venv\Scripts\python.exe research\intraday\pipeline.py fetch-upstox HDFCBANK 'NSE_EQ|INE040A01034' --start 2022-01-01 --end 2022-01-31
```

Dhan (security ID must come from Dhan's current instrument master):

```powershell
$env:DHAN_ACCESS_TOKEN='...'
backend\.venv\Scripts\python.exe research\intraday\pipeline.py fetch-dhan HDFCBANK 1333 --start '2022-01-01 09:15:00' --end '2022-03-31 15:30:00'
```

Their official documented intraday windows begin in 2022 and cover the
trailing five years respectively. Dhan requests must not exceed 90 days.

## Validate, audit, and merge

```powershell
backend\.venv\Scripts\python.exe research\intraday\pipeline.py validate
backend\.venv\Scripts\python.exe research\intraday\audit_lake.py
backend\.venv\Scripts\python.exe research\intraday\pipeline.py merge
```

The merge selects duplicate symbol/timestamps using catalog priority and writes
every conflict to a separate Parquet file. Conflicts are never silently averaged.

## Historical session warning

NSE continuous trading opened at 09:00 IST starting 4 January 2010. The
15-minute pre-open call auction was introduced on 18 October 2010, after which
continuous trading begins at 09:15 for covered cash-market securities. Coverage
audits report observed session boundaries and gaps; research resampling must use
the correct point-in-time session calendar.

## Still missing for the full objective

- Free one-minute equity data for 2010-2012.
- Broad all-NSE equity data for 2013-2014.
- Delisted-symbol intraday coverage and point-in-time identifiers.
- A verified free bridge for many symbols between the community-dataset end and
  the official Upstox/Dhan windows.
- Credentials for account-bound APIs.

Those gaps are data availability gaps, not engineering gaps. Official NSE
historical order/trade files or a licensed vendor are required if the final
dataset must truly be all NSE equities, survivorship-aware, and continuous from
2010.
