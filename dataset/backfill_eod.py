"""Backfill full end-of-day history (1995 -> today) for the whole universe.

This is the part of the ask that IS immediately satisfiable: the server returns
a symbol's entire daily history -- ~7,800 bars back to 1995-01-05 -- in one
request. One pass over 751 symbols builds the complete 2010-2026 dataset (and
15 years more besides) in minutes.

    python backfill_eod.py                      # 1d for every symbol
    python backfill_eod.py --interval 1w
    python backfill_eod.py --symbols RELIANCE,TCS
    python backfill_eod.py --force              # ignore resume state
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


def run(interval: str, symbols: list[str] | None, force: bool) -> int:
    tok = load_tokens()
    if symbols:
        want = {s.strip().upper() for s in symbols}
        tok = tok[tok["symbol"].str.upper().isin(want)]
        if tok.empty:
            raise SystemExit(f"no tokens matched {sorted(want)}")

    job = f"backfill_eod_{interval}"
    state = {} if force else store.load_state(job)
    todo = [r for _, r in tok.iterrows()
            if force or state.get(str(r["symbol"]), {}).get("status") != "ok"]

    print(f"[eod {interval}] universe={len(tok)}  to fetch={len(todo)}  "
          f"workers={config.MAX_WORKERS}")
    if not todo:
        print(f"[eod {interval}] nothing to do (use --force to refetch)")
        return 0

    client = NSECharting()
    started = time.time()
    counters = {"ok": 0, "empty": 0, "error": 0, "rows": 0}

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
        futs = [pool.submit(work, r) for r in todo]
        for fut in as_completed(futs):
            sym, df, err = fut.result()
            done += 1
            if err:
                counters["error"] += 1
                state[sym] = {"status": "error", "error": err,
                              "at": datetime.now().isoformat(timespec="seconds")}
            elif df is None or df.empty:
                counters["empty"] += 1
                state[sym] = {"status": "empty",
                              "at": datetime.now().isoformat(timespec="seconds")}
            else:
                added, total = store.merge_write(df, store.eod_path(sym, interval))
                counters["ok"] += 1
                counters["rows"] += total
                state[sym] = {
                    "status": "ok", "rows": total, "added": added,
                    "first": str(df["ts"].min().date()),
                    "last": str(df["ts"].max().date()),
                    "at": datetime.now().isoformat(timespec="seconds"),
                }
            if done % 25 == 0 or done == len(todo):
                store.save_state(job, state)
                rate = done / max(time.time() - started, 1e-9)
                eta = (len(todo) - done) / max(rate, 1e-9)
                print(f"[eod {interval}] {done}/{len(todo)}  ok={counters['ok']} "
                      f"empty={counters['empty']} err={counters['error']}  "
                      f"{rate:.1f}/s  eta={eta/60:.1f}m", flush=True)

    store.save_state(job, state)
    ok_rows = [v["rows"] for v in state.values() if v.get("status") == "ok"]
    firsts = [v["first"] for v in state.values() if v.get("status") == "ok"]
    print(f"\n[eod {interval}] done in {(time.time()-started)/60:.1f}m")
    print(f"  symbols ok   : {counters['ok']}")
    print(f"  empty        : {counters['empty']}")
    print(f"  errors       : {counters['error']}")
    if ok_rows:
        print(f"  total bars   : {sum(ok_rows):,}")
        print(f"  bars/symbol  : min={min(ok_rows):,} median={int(pd.Series(ok_rows).median()):,} max={max(ok_rows):,}")
        print(f"  earliest bar : {min(firsts)}")
    return 0 if counters["error"] == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1d", choices=["1d", "1w", "1M"])
    ap.add_argument("--symbols", default=None,
                    help="comma-separated subset, e.g. RELIANCE,TCS")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    syms = args.symbols.split(",") if args.symbols else None
    return run(args.interval, syms, args.force)


if __name__ == "__main__":
    sys.exit(main())
