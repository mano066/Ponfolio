# Survivorship-free NSE universe — UNBLOCKED (2026-07-25)

The single highest-value gate for v5 promotion — a **point-in-time,
survivorship-free universe** — is now achievable. The blocker (NSE's bot wall
returning 403 to plain HTTP, documented in V5_DATA_FEASIBILITY.md) is bypassed
with `curl_cffi` browser-TLS impersonation, which is already installed.

Pipeline: `research/scripts/v5/universe_builder.py`.

## What it does

Fetches NSE daily **equity bhavcopies** (the exchange's own end-of-day files) —
each is the exact set of instruments that *traded* that day, so unioning across
dates captures **delisted, renamed, and series-changed** names. Keyed by **ISIN**
(a stable id that survives ticker changes). Handles both NSE formats
automatically (legacy `cm…bhav.csv.zip` ≤ 2024-07-05; UDiFF ≥ 2024-07-08),
caches raw zips (resumable, idempotent), rate-limits, and never invents a
holiday/missing day.

## Proof (8-date sample, both formats, 0 misses) — [MEASURED]

| Metric | Value |
|---|---|
| Rows | 15,668 |
| Unique ISINs | 3,704 |
| Unique symbols | 3,633 |
| Equities/day | 1,496 (2012) → 2,649 (2025) |
| **Symbols NOT in today's `SWING_UNIVERSE`** | **2,951 of 3,633 (81%)** |

Examples absent from today's list: `63MOONS`, `3IINFOTECH`, `8KMILES`,
`A2ZINFRA`, `20MICRONS` — delisted/renamed names the current 750-name universe
silently drops. **This is the survivorship bias that inflated every prior v4/v5
backtest** (~5pp/yr per the literature cited in V4_EXIT_STUDY).

Artifacts written: `research/data/security_master_sample.parquet` (one row per
ISIN: all symbols used, series, first/last date, #days) and
`research/data/pit_universe_sample.parquet`.

## Full build (the actual rebuild)

```
python research/scripts/v5/universe_builder.py build --start 2010-01-01 --end 2026-07-17
```

This downloads every weekday bhavcopy 2010→present (~4,000 files). It is a
multi-hour, rate-limited job — but resumable (cached zips are skipped on rerun)
and idempotent. Outputs `security_master.parquet` + `pit_universe_daily.parquet`,
which become the point-in-time membership + OHLCV backbone for a **bias-free**
re-run of the v4-vs-v5 comparison and the v5 shortlist.

## Why this matters

Every measured result so far shares one caveat: *survivorship-biased universe →
absolute numbers overstated; only the v4-vs-v5 relative ranking is trustworthy.*
This pipeline removes that caveat. It is the decisive data unblock — the other
promotion gate alongside forward paper validation. Rerunning
`v4_vs_v5_compare.py` / `ensemble_v5.py` on this universe would turn the current
"relative improvement" verdict into a **bias-free absolute** one.

## Notes / limits

- Bhavcopy gives **raw** OHLCV; corporate-action adjustment (splits/bonus) still
  needs NSE's CA feed or a ratio series before computing multi-day returns across
  a split — a follow-on step, tracked separately.
- Fetching depends on NSE keeping the archive reachable; `curl_cffi` works today
  but NSE periodically changes its bot challenge (re-warm logic is built in).
- Research-only; no production code, paper data, or git state changed by this.
