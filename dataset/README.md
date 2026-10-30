# NSE dataset builder — Nifty Total Market (751 symbols)

Two stores, built by two different mechanisms, because NSE serves the two
timeframes on completely different terms.

| Store | Interval | Coverage | How |
| --- | --- | --- | --- |
| `store/daily/` | `1d`, `1w`, `1M` | **1995 → today, available immediately** | one request per symbol returns the entire history |
| `store/intraday/1m/` | `1m` … `1h` | **accumulates forward from first run** | server exposes a rolling ~20-session window only |

---

## The headline finding: 1-minute data from 2010 is not obtainable

The original plan was a 2010→2026 1-minute dataset for all 750 symbols. That
cannot be built from NSE, by this tool or any other client of the same API.
Probed directly against `charting.nseindia.com` on 2026-07-27 with RELIANCE:

```
1m  fromDate=0        ->  7,565 bars   2026-06-29 09:07 .. 2026-07-27 09:43
5m  fromDate=0        ->  1,544 bars   2026-06-29 09:07 .. same
15m fromDate=0        ->    522 bars   2026-06-29 09:07 .. same
1h  fromDate=0        ->    140 bars
1d  fromDate=0        ->  7,841 bars   1995-01-05      .. 2026-07-27   <-- full history
1w  fromDate=0        ->  1,648 bars   1995-01-06      .. 2026-07-27
```

Every intraday interval starts at the same date — the wall is a **server-side
cap of roughly 7,500 most recent bars**, about 20 trading sessions:

```
1m window ending -1y   -> EMPTY        1m backward paging:
1m window ending -2y   -> EMPTY          page 0  7,565 bars  2026-06-29 .. 2026-07-27
1m window ending -3y   -> EMPTY          page 1  EMPTY  -> STOP
1m window ending -5y   -> EMPTY
1m window ending -10y  -> EMPTY        earliest 1m bar reachable: 2026-06-29
1m window ending 2010  -> EMPTY
```

Explicit historical windows return nothing, and paging `toDate` backwards dies
on the first step. There is no parameter that unlocks more. So:

- **`1d` from 1995 is free and instant** — that half of the ask is done, and it
  covers 2010→2026 with 15 years to spare.
- **`1m` can only be grown forward.** Run the daily job and you own one month
  after a month, a year after a year. There is no shortcut, and paid vendors
  (TrueData, GDFL, Dhan) exist precisely because this wall exists.

## Second finding: the `openchart` PyPI package is broken

`openchart` **POSTs JSON** to `/v1/charts/symbolHistoricalData`. The current
server only honours **GET with a query string** — its SPA does
`fetch('/v1' + path, {method: 'GET'})`. The POST is answered with a canned
`{"status":true,"data":[]}`, so `openchart` returns an empty DataFrame for every
symbol and every interval while looking like it worked. Its `search()` is worse:
it returns the same 20 indices regardless of what you search for.

`nse_charting.py` in this folder speaks the real contract. Do not reintroduce
the dependency.

## Third finding: timestamps are IST-as-epoch

`time` is epoch-milliseconds that already encodes **IST wall clock**. Decode
with `pd.to_datetime(ms, unit='ms')` and **do not convert timezones**:

- daily bars land on exact midnight (`1784592000000` → `2026-07-21 00:00:00`);
- 1-minute sessions span `09:07 .. 15:30`, which is NSE's real trading day.

Converting to IST shifts sessions to `14:37 .. 21:00`, which is not when NSE
trades. Bar timestamps are **bar-close** times (`09:15:59` is the `09:15` bar),
so the client floors them to the bar's own minute.

Data quality was verified by reconstructing a daily bar from 1-minute bars
(RELIANCE, 2026-07-24):

```
daily : o=1265.0  h=1283.4  l=1249.8  v=9,817,000
from1m: o=1265.0  h=1283.4  l=1249.8  v=9,816,224   (100.0% of volume)
```

Open, high, low and volume agree exactly. Only `close` differs (1280.5 vs
1278.0) — the daily close is the closing-auction price, which is correct
behaviour, not a defect.

Note the intraday feed **lags the live session by several hours**: at 15:14 IST
only bars through 09:43 IST were published. Harvest after 16:30 IST.

---

## Setup

```powershell
cd dataset
pip install pandas pyarrow requests            # no openchart
python build_universe.py                       # constituents + token map
python backfill_eod.py                         # 1995->today, all symbols
python harvest_intraday.py --interval 1m       # first 1m window
python verify.py                               # integrity report
```

Then register the daily job so the 1-minute store starts growing:

```powershell
powershell -ExecutionPolicy Bypass -File setup_schedule.ps1
```

Mon–Fri 17:00 local, `-StartWhenAvailable` so a run missed while the machine was
off fires on next boot. Remove with `setup_schedule.ps1 -Remove`.

## Why missing a day is survivable

Every harvest pulls the **whole** ~20-session window and merges on timestamp,
newest copy winning. The job is idempotent and self-healing: skip a day, a week,
even two weeks, and the next run backfills every missed bar. Only a gap longer
than the server window (~20 sessions) loses data permanently.

## Reading the data

```python
from load import daily, intraday, panel, universe, resample

daily("RELIANCE", start="2010-01-01")        # EOD OHLCV
intraday("RELIANCE", "1m", session_only=True)
panel(["RELIANCE","TCS","INFY"], field="close", start="2015-01-01")
resample(intraday("RELIANCE","1m"), "15min") # build any coarser bar from 1m
universe()                                   # symbol, token, industry, isin
```

Storing `1m` and resampling upward is strictly better than harvesting `5m`/`15m`
separately — same source, one store, no drift.

## Files

| File | Role |
| --- | --- |
| `config.py` | paths, verified API limits, session envelope |
| `nse_charting.py` | the working GET client (replaces `openchart`) |
| `store.py` | parquet merge-append, atomic writes, resume state |
| `build_universe.py` | constituent CSV → token map |
| `backfill_eod.py` | full `1d`/`1w` history, resumable |
| `harvest_intraday.py` | rolling-window `1m` harvester, idempotent |
| `load.py` | read API for research code |
| `verify.py` | integrity + reconciliation report |
| `run_daily.ps1` | Task Scheduler entry point |
| `setup_schedule.ps1` | register/remove the scheduled task |

## Store layout

```
store/
  universe/nifty_total_market.csv    as published by NSE
  universe/tokens.csv               symbol -> scripcode
  daily/<SYMBOL>.parquet            full EOD history
  intraday/1m/<SYMBOL>/<YYYY-MM>.parquet
  state/<job>.json                  per-symbol resume state
  logs/                             run logs
```

Growth for the 1-minute store: 377 bars/session × ~250 sessions × 751 symbols
≈ **71M rows/year**. See `verify.py` output for the measured bytes/bar and its
projection on real data.

## Fourth finding: the daily open is the *opening-auction* price

The daily bar's `open` comes from the pre-open block near 09:07 — **not** from
the 09:15 minute bar. Session-only (09:15–15:30) intraday data therefore cannot
reproduce the daily open, and its session volume is legitimately short by the
pre-open block (~3% on RELIANCE).

This matters because it silently breaks naive validation. The vendor acceptance
test detects which convention a feed uses and switches from equality to
containment accordingly — see below.

## Buying real 2010→2026 1-minute history

No free API serves it, and it is not purchasable self-serve either:

| Source | 1-min depth |
| --- | --- |
| NSE charting (this tool) | ~20 sessions, rolling — free |
| Kite Connect | **~3 years** (60 days/request, 3 req/s) — *not* 2010 |
| GDFL / NimbleData | 1-min only 60 days; their 2010 archive is EOD |
| TrueData IEOD | daily 1-min CSVs; archive depth unpublished, ask |
| TickData | NSE intraday from **2012-01-02** — closest to the goal |

`VENDOR_RFQ.md` is a ready-to-send request for quote. Its §4 questions are the
ones that decide whether a delivery is usable — above all **survivorship bias**:
a 2012–2026 file containing only today's 751 survivors will inflate every
backtest run on it. Ask for delisted names and point-in-time constituents first.

### Ingesting a delivery — do not skip the order

```powershell
python ingest_vendor.py --path D:\vendor_sample --profile auto --dry-run   # 1. inspect
python ingest_vendor.py --path D:\vendor_sample --profile auto --commit    # 2. isolated
python ingest_vendor.py --validate --dest 1m_vendor                        # 3. accept
python ingest_vendor.py --promote --dest 1m_vendor --into 1m --commit      # 4. merge
```

Vendor bars land in `1m_vendor` and never touch `1m` until `--promote`, so a bad
delivery cannot corrupt data you already trust. Nothing is written without
`--commit`.

The loader auto-detects column names (`O/H/L/C/Vol`, `OpenPrice/TradedQty`,
`Ticker/Date Time`, …), recovers symbols from filenames or a column, and handles
bar-open vs bar-**close** timestamp labelling via `--ts-convention`.

`--validate` is the acceptance test: it rebuilds daily bars from the vendor's
1-minute data and reconciles them against the independent daily store —
`open`/`high`/`low` to 0.05 rupees, volume to 2% — auto-detecting whether the
feed includes pre-open, excluding partial sessions, and never comparing `close`.
It **exits 2 on failure**, so it can gate a payment or a CI step.

Verified against synthetic deliveries built from real NSE data: a session-only
feed and a with-pre-open feed both reconcile at **100.00%**, while a feed
corrupted by 0.4% price drift and 12% volume under-reporting scores **0.00%**.

## Back up `store/intraday/` — it cannot be rebuilt

The two stores have opposite risk profiles, and it is worth being blunt about it:

- `store/daily/` is **regenerable**. Delete it and `python backfill_eod.py`
  rebuilds all 2.9M bars from 1995 in about 3 minutes.
- `store/intraday/1m/` is **irreplaceable**. Once a session falls outside NSE's
  ~20-session window it can never be fetched again, at any price. Every day the
  accumulator runs, the unrecoverable portion grows.

Both **are** versioned in git, which is the off-machine copy. Losing
`store/intraday/` locally would otherwise mean restarting the accumulation clock
from zero, and no amount of money buys back the gap.

### Snapshot cadence — commit monthly, not per harvest

Measured churn for one harvest:

| Changes | Files | Size |
| --- | --- | --- |
| `daily/` (each symbol gains 1 bar) | 750 | 97 MB |
| current-month intraday (gains ~377 bars) | 750 | 107 MB |
| closed months (rewritten byte-identically) | 0 | 0 |
| **total** | **1,500** | **~204 MB** |

Adding a single bar recompresses an entire parquet file, and zstd-compressed
parquet does not delta-compress, so each changed file becomes a whole new git
object. Committing every harvest costs roughly **51 GB/year**; monthly snapshots
cost about **2.5 GB**. Closed months cost nothing at all — they are rewritten
with identical bytes, which git ignores for free.

`run_daily.ps1` therefore calls `snapshot_store.ps1`, which is a no-op on every
run except the first of a new month:

```powershell
powershell -File snapshot_store.ps1              # commit if a snapshot is due
powershell -File snapshot_store.ps1 -Force       # commit now
powershell -File snapshot_store.ps1 -Push        # and push
powershell -File snapshot_store.ps1 -Cadence weekly
```

It stages only `store/`, so your code changes stay under your own control, and
it never pushes unless `-Push` is passed. To let the scheduled task push on its
own, add `-Push` to the snapshot line in `run_daily.ps1`.

If the repo still grows faster than you like, the next lever is to stop
versioning `store/daily/` (it rebuilds in ~3 minutes via `backfill_eod.py`) and
keep only `store/intraday/`, which is the irreplaceable half.

`store/universe/` matters more than its size suggests: a snapshot of which
symbols were in the index on a given date is precisely the point-in-time
constituent data that survivorship-bias-free backtesting needs (RFQ §4.1).

## Measured store state (2026-07-27)

```
EOD 1d     : 750 symbols   2,922,116 bars   1995-01-05 .. 2026-07-27
             0 duplicates, 0 OHLC violations, 4,106 trading days since 2010
Intraday 1m: 750 symbols   5,407,130 bars   127.7 MB  (23.6 bytes/bar)
             ~20 sessions banked, 376-377 bars/session
             projected growth ~1.67 GB/year
```

`min=147` bars on the EOD side is not a defect — it is a recently listed symbol.
Symbols legitimately start at their listing date (360ONE begins 2019-09-19).
