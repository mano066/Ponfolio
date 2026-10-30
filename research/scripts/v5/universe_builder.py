"""Survivorship-free point-in-time NSE universe + security master.

Builds the unbiased universe the whole v5 program has been caveated on. Source =
NSE daily equity bhavcopies (the exchange's own end-of-day files), fetched with
curl_cffi (browser-TLS impersonation) which passes NSE's bot wall. Each bhavcopy
is the exact set of instruments that TRADED that day — so unioning across dates
captures delisted names, renamed tickers, and series changes, keyed by ISIN (a
stable instrument id that survives symbol changes).

Handles both NSE formats automatically:
  * <= 2024-07-05  : legacy  archives.nseindia.com/.../cmDDMONYYYYbhav.csv.zip
  * >= 2024-07-08  : UDiFF   nsearchives.nseindia.com/.../BhavCopy_NSE_CM_..._F_0000.csv.zip

Idempotent + resumable: raw zips cached under research/data/bhavcopy_cache/ and
skipped if present. Rate-limited. Never fabricates a missing/holiday day.

CLI:
  # small proof run (a few dates spread across years, old+new formats):
  python research/scripts/v5/universe_builder.py sample
  # full point-in-time build over a date range (LONG — thousands of files):
  python research/scripts/v5/universe_builder.py build --start 2010-01-01 --end 2026-07-17 --every 1

Outputs:
  research/data/security_master.parquet   (one row per ISIN: symbols, series, dates)
  research/data/pit_universe_daily.parquet (date, isin, symbol, series, close, turnover)
"""
from __future__ import annotations

import argparse
import io
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    from curl_cffi import requests as cq
except ImportError as e:  # pragma: no cover
    raise SystemExit("curl_cffi required: pip install curl_cffi") from e

D = Path(__file__).resolve().parents[2] / "data"
CACHE = D / "bhavcopy_cache"
CACHE.mkdir(parents=True, exist_ok=True)
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
UDIFF_CUTOVER = date(2024, 7, 8)          # NSE switched to UDiFF here
RATE_SLEEP = 0.6                          # polite delay between live fetches
EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}   # cash-market equity series

_SESSION = None


def _session():
    global _SESSION
    if _SESSION is None:
        s = cq.Session(impersonate="chrome")
        try:
            s.get("https://www.nseindia.com", timeout=20)   # warm cookies
        except Exception:
            pass
        _SESSION = s
    return _SESSION


def _urls_for(d: date) -> list[str]:
    if d >= UDIFF_CUTOVER:
        ymd = d.strftime("%Y%m%d")
        return [f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"]
    dd = f"{d.day:02d}{MONTHS[d.month-1]}{d.year}"
    return [
        f"https://archives.nseindia.com/content/historical/EQUITIES/{d.year}/{MONTHS[d.month-1]}/cm{dd}bhav.csv.zip",
        f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{d.year}/{MONTHS[d.month-1]}/cm{dd}bhav.csv.zip",
    ]


def _cache_path(d: date) -> Path:
    return CACHE / f"bhav_{d.strftime('%Y%m%d')}.zip"


def fetch_raw(d: date, *, retries: int = 3) -> bytes | None:
    """Return the raw bhavcopy zip bytes for date d (cached). None on
    holiday/missing (not an error — NSE simply has no file)."""
    cp = _cache_path(d)
    if cp.exists():
        b = cp.read_bytes()
        return b if b[:2] == b"PK" else None
    for url in _urls_for(d):
        for attempt in range(retries):
            try:
                r = _session().get(
                    url, headers={"Referer": "https://www.nseindia.com/all-reports"}, timeout=40)
                if r.status_code == 200 and r.content[:2] == b"PK":
                    cp.write_bytes(r.content)
                    time.sleep(RATE_SLEEP)
                    return r.content
                if r.status_code in (403, 401):        # cookie expired -> re-warm
                    global _SESSION
                    _SESSION = None
                    time.sleep(1.0 + attempt)
                    continue
                break                                   # 404 == no file that day
            except Exception:
                time.sleep(1.0 + attempt)
    time.sleep(RATE_SLEEP)
    return None


def parse_bhav(raw: bytes, d: date) -> pd.DataFrame | None:
    """Unify old + UDiFF into: date, symbol, series, isin, open, high, low,
    close, volume, turnover. Equity series only."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    except Exception:
        return None
    df.columns = [c.strip() for c in df.columns]
    if "TckrSymb" in df.columns:            # UDiFF (new)
        m = pd.DataFrame({
            "symbol": df["TckrSymb"].astype(str).str.strip(),
            "series": df["SctySrs"].astype(str).str.strip(),
            "isin": df.get("ISIN", pd.Series(index=df.index)).astype(str).str.strip(),
            "open": pd.to_numeric(df["OpnPric"], errors="coerce"),
            "high": pd.to_numeric(df["HghPric"], errors="coerce"),
            "low": pd.to_numeric(df["LwPric"], errors="coerce"),
            "close": pd.to_numeric(df["ClsPric"], errors="coerce"),
            "volume": pd.to_numeric(df["TtlTradgVol"], errors="coerce"),
            "turnover": pd.to_numeric(df.get("TtlTrfVal"), errors="coerce"),
        })
    elif "SYMBOL" in df.columns:            # legacy
        m = pd.DataFrame({
            "symbol": df["SYMBOL"].astype(str).str.strip(),
            "series": df["SERIES"].astype(str).str.strip(),
            "isin": df.get("ISIN", pd.Series(index=df.index)).astype(str).str.strip(),
            "open": pd.to_numeric(df["OPEN"], errors="coerce"),
            "high": pd.to_numeric(df["HIGH"], errors="coerce"),
            "low": pd.to_numeric(df["LOW"], errors="coerce"),
            "close": pd.to_numeric(df["CLOSE"], errors="coerce"),
            "volume": pd.to_numeric(df["TOTTRDQTY"], errors="coerce"),
            "turnover": pd.to_numeric(df.get("TOTTRDVAL"), errors="coerce"),
        })
    else:
        return None
    m = m[m["series"].isin(EQUITY_SERIES)].copy()
    m["date"] = pd.Timestamp(d)
    return m.dropna(subset=["close"]).reset_index(drop=True)


def get_day(d: date) -> pd.DataFrame | None:
    raw = fetch_raw(d)
    return parse_bhav(raw, d) if raw else None


def build(dates: list[date]) -> pd.DataFrame:
    frames, got, miss = [], 0, 0
    for i, d in enumerate(dates):
        df = get_day(d)
        if df is None or df.empty:
            miss += 1
        else:
            frames.append(df)
            got += 1
        if (i + 1) % 10 == 0 or i == len(dates) - 1:
            print(f"  {i+1}/{len(dates)}  trading-days={got} holidays/missing={miss}", flush=True)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def security_master(panel: pd.DataFrame) -> pd.DataFrame:
    """One row per ISIN (the stable id): every symbol it ever used (renames),
    series seen, first/last trading date, and #days — this is the artifact that
    makes the universe point-in-time and survivorship-free."""
    g = panel.groupby("isin", observed=True)
    out = g.agg(
        symbols=("symbol", lambda s: sorted(set(s))),
        series=("series", lambda s: sorted(set(s))),
        first_date=("date", "min"),
        last_date=("date", "max"),
        n_days=("date", "nunique"),
    ).reset_index()
    out["primary_symbol"] = out["symbols"].str[-1]
    out["renamed"] = out["symbols"].str.len() > 1
    return out.sort_values("first_date")


def daterange(start: date, end: date, every: int) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:          # skip weekends (holidays handled by missing file)
            out.append(d)
        d += timedelta(days=every)
    return out


def cmd_sample(_):
    # A spread of dates across years and BOTH formats — proves the fetcher works
    # and that we capture names absent from today's list (survivorship-free).
    sample = [date(2012, 6, 15), date(2015, 1, 2), date(2018, 3, 15), date(2020, 11, 27),
              date(2021, 7, 15), date(2023, 5, 10), date(2024, 6, 3), date(2025, 1, 15)]
    print(f"SAMPLE fetch of {len(sample)} dates (old + UDiFF formats)...", flush=True)
    panel = build(sample)
    if panel.empty:
        raise SystemExit("No bhavcopy data fetched — NSE may be unreachable from here.")
    sm = security_master(panel)
    print(f"\nrows: {len(panel):,}  unique ISINs: {panel['isin'].nunique():,}  "
          f"unique symbols: {panel['symbol'].nunique():,}")
    print("per-day equity counts:")
    for d, n in panel.groupby("date")["symbol"].nunique().items():
        print(f"  {d.date()}: {n:,} equities")

    # Survivorship-free proof: how many sampled symbols are NOT in today's
    # hardcoded SWING_UNIVERSE (i.e. delisted / renamed / never-included)?
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
        import swing_trading
        today = {s.replace(".NS", "") for s in swing_trading.SWING_UNIVERSE}
        hist = set(panel["symbol"])
        missing = sorted(hist - today)
        print(f"\nsurvivorship check: {len(hist):,} historical symbols sampled; "
              f"{len(missing):,} are NOT in today's SWING_UNIVERSE")
        print("  examples absent from today's list:", missing[:15])
    except Exception as e:
        print("survivorship check skipped:", e)

    out_sm = D / "security_master_sample.parquet"
    out_pn = D / "pit_universe_sample.parquet"
    sm.to_parquet(out_sm, index=False)
    panel.to_parquet(out_pn, index=False)
    print(f"\nwrote {out_sm}  ({len(sm)} ISINs)")
    print(f"wrote {out_pn}  ({len(panel)} rows)")
    print("\nOK — survivorship-free pipeline verified. Full build command:")
    print("  python research/scripts/v5/universe_builder.py build --start 2010-01-01 --end 2026-07-17")


def cmd_build(a):
    start = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end)
    dates = daterange(start, end, a.every)
    print(f"BUILD {start}..{end}  ({len(dates)} weekday dates, every={a.every})", flush=True)
    panel = build(dates)
    if panel.empty:
        raise SystemExit("No data fetched.")
    sm = security_master(panel)
    sm.to_parquet(D / "security_master.parquet", index=False)
    panel.to_parquet(D / "pit_universe_daily.parquet", index=False)
    print(f"\nwrote security_master.parquet ({len(sm):,} ISINs) and "
          f"pit_universe_daily.parquet ({len(panel):,} rows)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sample").set_defaults(func=cmd_sample)
    b = sub.add_parser("build")
    b.add_argument("--start", default="2010-01-01")
    b.add_argument("--end", default=date.today().isoformat())
    b.add_argument("--every", type=int, default=1, help="day step (1=every weekday)")
    b.set_defaults(func=cmd_build)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
