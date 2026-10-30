# V5 Data Feasibility Audit (2026-07-24)

**Question:** can we actually get 2010→present, 1-minute-resolvable, survivorship-free
NSE data (including delisted names) to research a v5 swing engine, as the brief
requests? **Answer: no — not as one continuous dataset.** Verified facts, tested
access paths, and honest tiers below. This report is the Phase-1 stop-and-report
checkpoint; no strategy research has been run yet.

---

## 1. What already exists in this repo (verified by reading the code/files)

| Item | Status |
|---|---|
| Daily OHLCV, ~750 symbols, 2010-01-04→2026-07-17 | **Exists** — `research/data/nse_universe_2010_ohlcv.csv.gz`, 2,110,297 rows, sourced from `yfinance` |
| Universe used to build it | **Today's ~750-name "Nifty Total Market" list** (`swing_trading.SWING_UNIVERSE`) pulled backward over 16 years → **survivorship-biased**, already flagged in `V4_EXIT_STUDY.md`/`WIN_RATE_OPTIMIZATION.md`/audit report |
| Corporate-action adjustment | Yahoo's `adjusted_close` only; audit report documents **13 unadjusted split/CA rows found and left unfixed**, only flagged |
| Delisted-stock coverage | **0 delisted symbols** in any existing file (confirmed in `next_day_gainers_AUDIT_REPORT.md` §1) |
| Intraday data (any timeframe, any period) | **None exists anywhere in the repo** |
| Wired-up data providers | `yfinance` (public, no key) and Zerodha **Kite MCP** (`kite_client.py` → `https://mcp.kite.trade/mcp`, session-auth, daily interval only in current code) |
| Local analytical store | Flat CSV/CSV.GZ only. No DuckDB/Parquet/SQLite. `duckdb`/`polars`/`pyarrow` are **not installed** |

## 2. What I tested directly, right now

- `curl` to `https://www.nseindia.com` and `https://archives.nseindia.com/.../bhav.csv.zip` with a
  browser user-agent → **HTTP 403 on the homepage**, and the archive endpoint returns HTTP 200 with
  **0 bytes** (bot-challenge page, not the file) without a live browser-issued session/cookie/JS
  challenge pass. NSE's archive site is not scriptable with plain HTTP — this matches the well-known
  pain point in the Indian retail-quant community (libraries like `jugaad-data`/`nsepython` work around
  it with rotating headers and `curl_cffi` TLS fingerprinting, with no reliability guarantee since NSE
  changes the challenge periodically). `curl_cffi` **is already installed** in this repo's venv, which
  makes a workaround plausible but **unverified** — I have not gotten a bhavcopy file through yet.
- Yahoo Finance's own documented API limits (not repo-specific, general fact): intraday history is
  capped at **~60 days for 1m bars** and **~60 days for 5m/15m/30m/60m bars**, regardless of how far
  back you ask. `yfinance` **cannot** supply 2010–present intraday at any resolution — this is a hard
  vendor limit, not a bug to fix.

## 3. Tiers (per the brief's Tier A/B/C framework — never to be combined into one "2010 intraday" claim)

### Tier A — Daily, 2010→latest completed session
- **Feasible now**, with rework. Two paths:
  1. **Fast-start (biased):** reuse the existing `nse_universe_2010_ohlcv.csv.gz` as-is. Fast, but
     inherits survivorship bias + 13 unfixed corporate-action rows — same caveat every prior study
     already carries. Acceptable only as a v0 sanity check, not for a promotion-grade v5 result.
  2. **Rebuilt (survivorship-free):** re-derive the universe from NSE's historical EQ bhavcopy files
     (point-in-time list of every symbol that traded each day, including later-delisted names) plus
     NSE's corporate-action master. **Blocked today by the 403/bot-challenge above** — needs either a
     working `curl_cffi`-based scraper (unverified), or a paid data vendor that resells bhavcopy-derived
     history (see Tier B). This is the only path that satisfies Phase 2's survivorship-free requirement.
- Estimated size for path 2 at full historical breadth (~2,500 avg point-in-time active EQ symbols/day
  × ~4,140 trading days since 2010): **~10M row-days**, trivial storage (<1 GB as Parquet).

### Tier B — Intraday, longest *reliably* available window
- **Nothing is currently wired up or paid for.** Two realistic options, neither verified in this repo:
  1. **Zerodha Kite Connect historical-data API** — requires the ₹2,000/month "Historical Data" add-on
     on an active Kite trading account (separate from the free MCP session already used for daily
     data/LTP). Typical real-world coverage is **instrument-dependent, commonly ~2015–2017 onward**,
     rate-limited (documented at 3 req/sec, ~180 req/min), and **does not reliably serve delisted
     instrument tokens** — once a symbol delists its token is usually retired.
  2. **Commercial vendors** (e.g. TrueData, Global Datafeeds, AlgoTest/Definedge) sell bulk historical
     1-minute NSE equity data, typically from **~2015–2020 onward** depending on vendor/plan, at cost
     (subscription or one-time fee — I have not obtained current pricing and won't guess a number).
     Delisted-stock coverage varies by vendor and would need to be confirmed directly with them before
     buying.
  - **No option here reaches back to 2010, and none has confirmed delisted-stock intraday coverage.**
    A realistic Tier B window, if pursued, is **~2016/2018→present, survivorship-*incomplete***.

### Tier C — Recent high-quality 1-minute data (execution/slippage studies only)
- Most achievable tier. Either the Kite historical API (if the ₹2,000/month add-on is active) or a
  vendor trial for roughly the **trailing 1–3 years**, current-universe-only. Sufficient for fill/
  slippage modeling (Phase 7–9) but not for a 16-year signal study.

## 4. Storage/compute reality check (why "billions of rows" in the brief is literally correct)

- 1-minute bars/session = 375 (09:15–15:30). Trading days since 2010 ≈ 4,140.
- **Current 750-symbol universe only, 1-min, full period:** 750 × 375 × 4,140 ≈ **1.16 billion rows**
  (impossible anyway per §3 — no vendor covers this from 2010 — shown only to size the ask).
- **Survivorship-free universe (~2,500 avg symbols/day), 1-min, full period:** ≈ **3.9 billion rows**.
- At a compact partitioned-Parquet encoding (~20–30 bytes/row compressed) that's **~25–100 GB**
  compressed for whichever slice actually turns out to be purchasable — not "impossible on a laptop,"
  but firmly a multi-day download+ETL job with rate-limit-aware incremental fetching (Phase 15), not
  something to run interactively in one session.
- Reproducibility: any Tier B/C dataset bought from a vendor is licensed, not redistributable — the
  manifest/checksum layer (Phase 15) must record vendor+plan+fetch-date so results are reproducible
  *by someone with the same license*, not by an arbitrary third party.

## 5. Verdict against the brief's instruction

> "Do not claim 2010–present 1-minute coverage unless it is actually available."

It is not available — from any source, free or paid, with delisted-stock coverage — and I'm not
claiming it. Concretely deliverable without new spend:

- **Tier A, path 2 (survivorship-free daily, 2010→present)** — pending either a working bhavcopy
  scraper or a small vendor purchase for the historical universe/corporate-action master.
- **Tier C (recent 1–3y intraday, current universe)** — pending confirmation the Kite historical add-on
  is active, or a vendor trial.
- **True Tier B (multi-year intraday, survivorship-aware)** — requires a paid vendor decision I can't
  make unilaterally (cost, vendor choice, and how much delisted-coverage gap is acceptable are business
  decisions, not engineering ones).

**Recommendation:** proceed now with Tier A (rebuild survivorship-free daily universe) as the primary
v5 research track — this directly answers the Selection question (Phase 4.1) and is what v4 itself
runs on, so it's the cleanest apples-to-apples comparison. Treat intraday (Tiers B/C) as a
budget-gated follow-on for the Execution question (Phase 4.2), scoped down to whatever window a chosen
vendor actually delivers, clearly labeled, never blended into the daily backtest.
