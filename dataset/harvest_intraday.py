"""Harvest the rolling intraday window and append it to the store.

This is the accumulation engine. The server exposes only its most recent
~7,500 intraday bars per symbol (~20 trading days); older windows return
nothing and backward paging does not work. So 1-minute history cannot be
bought or backfilled -- it can only be *accumulated forward* from today.

Because every run pulls the full ~20-day window and merges on timestamp, the
job is idempotent and self-healing: miss a day, a week, even two weeks, and
the next run silently recovers every missed bar. Only a gap longer than the
window loses data permanently.

    python harvest_intraday.py                     # 1m for the whole universe
    python harvest_intraday.py --interval 5m
    python harvest_intraday.py --symbols RELIANCE,TCS
    python harvest_intraday.py --drop-preopen      # keep 09:15..15:30 only

Run it once per trading day after 16:00 IST. The intraday feed lags the live
session by several hours, so an intraday run captures a partial day (which the
next run completes).
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

import config
import store
from build_universe import load_tokens
from nse_charting import NSECharting, NSEChartingError, polite_sleep


def _drop_preopen(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    tod = df["ts"].dt.time
    lo = pd.to_datetime(config.SESSION_OPEN).time()
    hi = pd.to_datetime(config.SESSION_CLOSE).time()
    return df[(tod >= lo) & (tod <= hi)]


def run(interval: str, symbols: list[str] | None, drop_preopen: bool) -> int:
    if interval not in config.INTRADAY_INTERVALS:
        raise SystemExit(f"{interval} is not intraday; use backfill_eod.py")

    tok = load_tokens()
    if symbols:
        want = {s.strip().upper() for s in symbols}
        tok = tok[tok["symbol"].str.upper().isin(want)]
        if tok.empty:
            raise SystemExit(f"no tokens matched {sorted(want)}")

    job = f"harvest_{interval}"
    state = store.load_state(job)
    run_stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[{interval}] harvesting {len(tok)} symbols at {run_stamp} "
          f"(workers={config.MAX_WORKERS})")

    client = NSECharting()
    started = time.time()
    counters = {"ok": 0, "empty": 0, "error": 0, "added": 0}
    errors: list[str] = []

    def work(row):
        polite_sleep()
        sym = str(row["symbol"])
        try:
            df = client.history(row["token"], str(row["chart_symbol"]),
                                str(row.get("symbol_type") or "Equity"),
                                interval=interval)
        except NSEChartingError as e:
            return sym, None, str(e)
        return sym, df, None

    done = 0
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        futs = [pool.submit(work, r) for _, r in tok.iterrows()]
        for fut in as_completed(futs):
            sym, df, err = fut.result()
            done += 1
            prev = state.get(sym, {})
            if err:
                counters["error"] += 1
                errors.append(f"{sym}: {err}")
                state[sym] = {**prev, "last_run": run_stamp,
                              "last_status": "error", "error": err}
            else:
                if drop_preopen:
                    df = _drop_preopen(df)
                if df.empty:
                    counters["empty"] += 1
                    state[sym] = {**prev, "last_run": run_stamp,
                                  "last_status": "empty"}
                else:
                    res = store.write_intraday(sym, interval, df)
                    counters["ok"] += 1
                    counters["added"] += res["added"]
                    state[sym] = {
                        **prev,
                        "last_run": run_stamp,
                        "last_status": "ok",
                        "added": res["added"],
                        "window_first": str(df["ts"].min()),
                        "window_last": str(df["ts"].max()),
                        "coverage_start": min(
                            [d for d in [prev.get("coverage_start"),
                                         str(df["ts"].min())] if d]),
                        "coverage_end": max(
                            [d for d in [prev.get("coverage_end"),
                                         str(df["ts"].max())] if d]),
                    }
            if done % 25 == 0 or done == len(tok):
                store.save_state(job, state)
                rate = done / max(time.time() - started, 1e-9)
                eta = (len(tok) - done) / max(rate, 1e-9)
                print(f"[{interval}] {done}/{len(tok)}  ok={counters['ok']} "
                      f"empty={counters['empty']} err={counters['error']} "
                      f"newbars={counters['added']:,}  {rate:.1f}/s "
                      f"eta={eta/60:.1f}m", flush=True)

    store.save_state(job, state)
    elapsed = (time.time() - started) / 60
    covs = [v.get("coverage_start") for v in state.values() if v.get("coverage_start")]
    print(f"\n[{interval}] done in {elapsed:.1f}m")
    print(f"  symbols ok  : {counters['ok']}")
    print(f"  empty       : {counters['empty']}")
    print(f"  errors      : {counters['error']}")
    print(f"  new bars    : {counters['added']:,}")
    if covs:
        print(f"  accumulated coverage starts at: {min(covs)}")
    if errors:
        print("  first errors:")
        for e in errors[:10]:
            print("   ", e)

    log = config.LOG_DIR / f"harvest_{interval}.log"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"{run_stamp}\tok={counters['ok']}\tempty={counters['empty']}"
                 f"\terr={counters['error']}\tadded={counters['added']}"
                 f"\t{elapsed:.1f}m\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1m",
                    choices=sorted(config.INTRADAY_INTERVALS))
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--drop-preopen", action="store_true",
                    help="store only 09:15..15:30 bars (drops the pre-open block)")
    args = ap.parse_args()
    syms = args.symbols.split(",") if args.symbols else None
    return run(args.interval, syms, args.drop_preopen)


if __name__ == "__main__":
    sys.exit(main())
