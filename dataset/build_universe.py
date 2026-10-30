"""Build the symbol universe and resolve every symbol to its charting token.

    python build_universe.py            # refresh constituents + resolve missing
    python build_universe.py --force    # re-resolve every token from scratch

Outputs:
    store/universe/nifty_total_market.csv   as published by NSE
    store/universe/tokens.csv               symbol, series, token, chart_symbol...
    store/universe/unresolved.csv           anything the search could not match
"""
from __future__ import annotations

import argparse
import io
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

import config
from nse_charting import NSECharting, NSEChartingError, polite_sleep

CONSTITUENTS = config.UNIVERSE_DIR / f"{config.UNIVERSE_NAME}.csv"
TOKENS = config.UNIVERSE_DIR / "tokens.csv"
UNRESOLVED = config.UNIVERSE_DIR / "unresolved.csv"


def fetch_constituents() -> pd.DataFrame:
    headers = {"User-Agent": config.USER_AGENT, "Accept": "*/*"}
    last = None
    for url in config.UNIVERSE_CSV_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=60)
            if r.status_code == 200 and len(r.content) > 1000:
                df = pd.read_csv(io.StringIO(r.text))
                df.columns = [c.strip() for c in df.columns]
                print(f"[universe] {url} -> {len(df)} rows")
                return df
            last = f"HTTP {r.status_code} len={len(r.content)}"
        except requests.RequestException as e:
            last = repr(e)
    raise SystemExit(f"[universe] could not download constituent list: {last}")


def resolve_all(symbols: pd.DataFrame, force: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    known: dict[str, dict] = {}
    if TOKENS.exists() and not force:
        prev = pd.read_csv(TOKENS)
        known = {str(r["symbol"]): r.to_dict() for _, r in prev.iterrows()}
        print(f"[tokens] {len(known)} already resolved, reusing")

    todo = [(r["Symbol"], str(r.get("Series", "EQ")).strip() or "EQ")
            for _, r in symbols.iterrows()
            if force or str(r["Symbol"]) not in known]
    print(f"[tokens] resolving {len(todo)} symbols with {config.MAX_WORKERS} workers")

    client = NSECharting()
    resolved, missing = [], []

    def work(item):
        sym, series = item
        polite_sleep()
        try:
            hit = client.resolve(sym, series=series)
        except NSEChartingError as e:
            return sym, series, None, str(e)
        return sym, series, hit, None

    done = 0
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        futs = {pool.submit(work, it): it for it in todo}
        for fut in as_completed(futs):
            sym, series, hit, err = fut.result()
            done += 1
            if hit:
                resolved.append({
                    "symbol": sym,
                    "series": series,
                    "token": str(hit.get("scripcode")),
                    "chart_symbol": hit.get("symbol"),
                    "symbol_type": hit.get("type") or "Equity",
                    "description": hit.get("description"),
                })
            else:
                missing.append({"symbol": sym, "series": series, "error": err or "no match"})
            if done % 50 == 0 or done == len(todo):
                print(f"[tokens] {done}/{len(todo)} resolved={len(resolved)} missing={len(missing)}",
                      flush=True)

    rows = list(known.values()) + resolved
    tok = pd.DataFrame(rows).drop_duplicates(subset="symbol", keep="last")
    tok = tok.sort_values("symbol").reset_index(drop=True)
    return tok, pd.DataFrame(missing)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="re-resolve every token instead of reusing tokens.csv")
    args = ap.parse_args()

    cons = fetch_constituents()
    if "Symbol" not in cons.columns:
        raise SystemExit(f"[universe] unexpected columns: {list(cons.columns)}")
    cons.to_csv(CONSTITUENTS, index=False)
    print(f"[universe] saved {CONSTITUENTS} ({len(cons)} symbols)")

    tok, missing = resolve_all(cons, args.force)
    tok.to_csv(TOKENS, index=False)
    print(f"[tokens] saved {TOKENS} ({len(tok)} resolved)")

    if not missing.empty:
        missing.to_csv(UNRESOLVED, index=False)
        print(f"[tokens] {len(missing)} unresolved -> {UNRESOLVED}")
        print(missing.head(20).to_string())
    elif UNRESOLVED.exists():
        UNRESOLVED.unlink()

    coverage = 100.0 * len(tok) / max(len(cons), 1)
    print(f"[tokens] coverage {len(tok)}/{len(cons)} = {coverage:.1f}%")
    return 0


def load_tokens() -> pd.DataFrame:
    if not TOKENS.exists():
        raise SystemExit("tokens.csv missing -- run: python build_universe.py")
    return pd.read_csv(TOKENS, dtype={"token": str})


if __name__ == "__main__":
    sys.exit(main())
