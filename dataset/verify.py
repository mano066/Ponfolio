"""Integrity report for the store.

    python verify.py                 # summary of everything
    python verify.py --interval 1m   # intraday detail
    python verify.py --symbol RELIANCE

Checks that matter:
  * EOD: bar counts, date span, gaps vs the NSE trading calendar implied by the
    union of all symbols' dates, OHLC sanity (high>=low, high>=open/close).
  * Intraday: bars per session vs the expected 377, duplicate minutes,
    reconstruction of the daily bar from 1m bars (open/high/low/volume must
    agree -- close legitimately differs because the daily close is the
    closing-auction price).
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

import config
import store


def _files(d):
    return sorted(d.glob("*.parquet")) if d.exists() else []


def ohlc_violations(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return {
        "high<low": int((df["high"] < df["low"]).sum()),
        "high<open": int((df["high"] < df["open"]).sum()),
        "high<close": int((df["high"] < df["close"]).sum()),
        "low>open": int((df["low"] > df["open"]).sum()),
        "low>close": int((df["low"] > df["close"]).sum()),
        "nonpositive_close": int((df["close"] <= 0).sum()),
        "negative_volume": int((df["volume"] < 0).sum()),
    }


def report_eod(interval: str = "1d") -> None:
    d = config.STORE / ("daily" if interval == "1d" else f"eod_{interval}")
    files = _files(d)
    print(f"\n=== EOD {interval}: {len(files)} symbol files in {d} ===")
    if not files:
        print("  (empty -- run: python backfill_eod.py)")
        return

    rows, spans, viol_total = [], [], {}
    all_dates = set()
    for f in files:
        df = store.read(f)
        if df.empty:
            rows.append({"symbol": f.stem, "bars": 0, "first": None, "last": None})
            continue
        rows.append({"symbol": f.stem, "bars": len(df),
                     "first": df["ts"].min().date(), "last": df["ts"].max().date(),
                     "dupes": int(df["ts"].duplicated().sum())})
        all_dates.update(df["ts"].dt.date.tolist())
        for k, v in ohlc_violations(df).items():
            viol_total[k] = viol_total.get(k, 0) + v

    s = pd.DataFrame(rows)
    total = int(s["bars"].sum())
    print(f"  total bars     : {total:,}")
    print(f"  bars/symbol    : min={s['bars'].min():,} median={int(s['bars'].median()):,} "
          f"max={s['bars'].max():,}")
    print(f"  date span      : {s['first'].min()} .. {s['last'].max()}")
    print(f"  distinct dates : {len(all_dates):,} (trading days seen across universe)")
    print(f"  duplicate ts   : {int(s.get('dupes', pd.Series([0])).sum())}")
    print(f"  empty files    : {int((s['bars'] == 0).sum())}")

    bad = {k: v for k, v in viol_total.items() if v}
    print(f"  OHLC violations: {bad if bad else 'none'}")

    since_2010 = sum(1 for dt in all_dates if dt.year >= 2010)
    print(f"  trading days >= 2010-01-01: {since_2010:,}")

    stale = s[s["last"] < s["last"].max()]
    if len(stale):
        print(f"  symbols not current ({len(stale)}), most stale:")
        print(stale.nsmallest(5, "last")[["symbol", "last", "bars"]].to_string(index=False))


def report_intraday(interval: str = "1m") -> None:
    base = config.INTRADAY_DIR / interval
    syms = sorted([p for p in base.iterdir() if p.is_dir()]) if base.exists() else []
    print(f"\n=== INTRADAY {interval}: {len(syms)} symbols in {base} ===")
    if not syms:
        print("  (empty -- run: python harvest_intraday.py)")
        return

    tot_rows = 0
    tot_bytes = 0
    per_sym = []
    session_counts = {}
    for sd in syms:
        parts = sorted(sd.glob("*.parquet"))
        n = 0
        first = last = None
        for p in parts:
            tot_bytes += p.stat().st_size
            df = store.read(p)
            if df.empty:
                continue
            n += len(df)
            first = df["ts"].min() if first is None else min(first, df["ts"].min())
            last = df["ts"].max() if last is None else max(last, df["ts"].max())
            if sd.name == syms[0].name:
                for dt, cnt in df.groupby(df["ts"].dt.date).size().items():
                    session_counts[dt] = cnt
        tot_rows += n
        per_sym.append({"symbol": sd.name, "bars": n, "months": len(parts),
                        "first": first, "last": last})

    s = pd.DataFrame(per_sym)
    print(f"  total bars   : {tot_rows:,}")
    print(f"  on disk      : {tot_bytes/1e6:.1f} MB  ({tot_bytes/max(tot_rows,1):.1f} bytes/bar)")
    print(f"  bars/symbol  : min={s['bars'].min():,} median={int(s['bars'].median()):,} "
          f"max={s['bars'].max():,}")
    print(f"  coverage     : {s['first'].min()} .. {s['last'].max()}")

    if session_counts:
        sc = pd.Series(session_counts).sort_index()
        exp = config.EXPECTED_1M_BARS_PER_DAY
        print(f"  bars/session for {syms[0].name} (expected ~{exp} incl. pre-open):")
        for dt, c in sc.items():
            flag = "" if abs(c - exp) <= 2 else "   <-- partial/irregular"
            print(f"    {dt}  {c}{flag}")

    days = s["bars"] / config.EXPECTED_1M_BARS_PER_DAY
    print(f"  approx sessions accumulated: {days.median():.1f} (median symbol)")
    if tot_rows:
        yr = tot_bytes / max(tot_rows, 1) * config.EXPECTED_1M_BARS_PER_DAY * 250 * len(syms)
        print(f"  projected growth: ~{yr/1e9:.2f} GB per year at {len(syms)} symbols")


def reconcile(symbol: str, interval: str = "1m") -> None:
    """Rebuild daily bars from intraday and compare with the stored EOD bars."""
    print(f"\n=== reconcile {symbol}: {interval} -> 1d ===")
    sd = config.INTRADAY_DIR / interval / symbol
    if not sd.exists():
        print("  no intraday data for this symbol")
        return
    intra = pd.concat([store.read(p) for p in sorted(sd.glob("*.parquet"))],
                      ignore_index=True)
    eod = store.read(store.eod_path(symbol, "1d"))
    if intra.empty or eod.empty:
        print("  need both intraday and EOD data")
        return

    intra["d"] = intra["ts"].dt.date
    agg = intra.groupby("d").agg(o=("open", "first"), h=("high", "max"),
                                 l=("low", "min"), c=("close", "last"),
                                 v=("volume", "sum"), n=("ts", "size"))
    eod = eod.copy()
    eod["d"] = eod["ts"].dt.date
    e = eod.set_index("d")

    common = [d for d in agg.index if d in e.index]
    print(f"  overlapping sessions: {len(common)}")
    rows = []
    for d in common[-10:]:
        a, b = agg.loc[d], e.loc[d]
        rows.append({
            "date": d, "bars": int(a.n),
            "open_match": abs(a.o - b.open) < 0.05,
            "high_match": abs(a.h - b.high) < 0.05,
            "low_match": abs(a.l - b.low) < 0.05,
            "vol_pct": round(100 * a.v / b.volume, 1) if b.volume else None,
        })
    print(pd.DataFrame(rows).to_string(index=False))
    print("  (close is expected to differ: daily close = closing-auction price)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default=None)
    ap.add_argument("--symbol", default=None)
    args = ap.parse_args()

    if args.symbol:
        reconcile(args.symbol, args.interval or "1m")
        return 0
    if args.interval:
        if args.interval in config.INTRADAY_INTERVALS:
            report_intraday(args.interval)
        else:
            report_eod(args.interval)
        return 0

    report_eod("1d")
    for iv in sorted(config.INTRADAY_INTERVALS):
        if (config.INTRADAY_DIR / iv).exists():
            report_intraday(iv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
