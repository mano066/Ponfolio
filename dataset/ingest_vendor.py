"""Ingest purchased 1-minute data from any vendor into this store, and prove
it is worth what was paid for it.

Workflow for a paid delivery -- do not skip the order:

    # 1. see what the loader makes of the files, write nothing
    python ingest_vendor.py --path D:\\vendor_sample --profile auto --dry-run

    # 2. load into an ISOLATED namespace (never straight into 1m)
    python ingest_vendor.py --path D:\\vendor_sample --profile auto --commit

    # 3. reconcile against our independent daily history -- the acceptance test
    python ingest_vendor.py --validate --dest 1m_vendor

    # 4. only once step 3 passes, merge into the main 1m store
    python ingest_vendor.py --promote --dest 1m_vendor --into 1m

Nothing is written without --commit, and vendor bars never touch `1m` until
--promote. That way a bad delivery cannot silently corrupt data we already
trust.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import config
import store

# --- column aliases -------------------------------------------------------
ALIASES = {
    "symbol":   ["symbol", "ticker", "tradingsymbol", "scrip", "scripname",
                 "name", "instrument", "series_symbol"],
    "datetime": ["datetime", "date_time", "timestamp", "date time", "datetimestamp"],
    "date":     ["date", "ymd", "tradedate", "trade_date", "dt"],
    "time":     ["time", "hhmm", "bartime", "tm"],
    "open":     ["open", "o", "openprice", "open_price"],
    "high":     ["high", "h", "highprice", "high_price"],
    "low":      ["low", "l", "lowprice", "low_price"],
    "close":    ["close", "c", "closeprice", "close_price", "last", "ltp"],
    "volume":   ["volume", "v", "vol", "qty", "quantity", "tradedqty",
                 "traded_quantity", "totalqty"],
}

PROFILES = {
    # TrueData IEOD: YMD,Time,Open,High,Low,Close,Volume[,OI], symbol in filename
    "truedata": {"symbol_from": "filename", "ts_convention": "open"},
    # GDFL / NimbleData: Ticker,Date,Time,Open,High,Low,Close,Volume,OI
    "gdfl":     {"symbol_from": "column", "ts_convention": "open"},
    "generic":  {"symbol_from": "auto", "ts_convention": "open"},
    "auto":     {"symbol_from": "auto", "ts_convention": "open"},
}

DATA_GLOBS = ["*.csv", "*.csv.gz", "*.txt", "*.txt.gz", "*.parquet"]
MANIFEST = "vendor_ingest_manifest"


# --- helpers --------------------------------------------------------------
def _norm(col: str) -> str:
    return str(col).strip().lower().replace("_", "").replace(" ", "").replace("-", "")


def build_column_map(cols: list[str], overrides: dict) -> dict:
    """vendor column name -> canonical field."""
    lookup = {}
    for canon, names in ALIASES.items():
        for n in names:
            lookup[_norm(n)] = canon
    mapping = {}
    for c in cols:
        canon = lookup.get(_norm(c))
        if canon and canon not in mapping.values():
            mapping[c] = canon
    mapping.update(overrides)          # explicit --map always wins
    return mapping


def canonical_symbols() -> dict:
    """normalised symbol -> canonical universe symbol."""
    p = config.UNIVERSE_DIR / "tokens.csv"
    if not p.exists():
        return {}
    tok = pd.read_csv(p, dtype={"token": str})
    out = {}
    for s in tok["symbol"].astype(str):
        out[_norm(s)] = s
    for s, cs in zip(tok["symbol"].astype(str), tok["chart_symbol"].astype(str)):
        out[_norm(cs)] = s                      # RELIANCE-EQ -> RELIANCE
        out[_norm(cs.split("-")[0])] = s
    return out


def symbol_from_filename(path: Path, known: dict) -> str | None:
    stem = path.name
    for suf in (".gz", ".csv", ".txt", ".parquet"):
        if stem.lower().endswith(suf):
            stem = stem[: -len(suf)]
    cand = [stem]
    for sep in ("_", "-", "."):
        cand.append(stem.split(sep)[0])
    for c in cand:
        hit = known.get(_norm(c))
        if hit:
            return hit
    return None


def _read_any(path: Path, nrows: int | None = None) -> pd.DataFrame:
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
        return df.head(nrows) if nrows else df
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        head = fh.readline()
    sep = "\t" if head.count("\t") > head.count(",") else ","
    # a vendor file with no header still parses if the first row is data
    has_header = any(ch.isalpha() for ch in head.replace("E", "").replace("e", ""))
    return pd.read_csv(path, sep=sep, nrows=nrows,
                       header=0 if has_header else None,
                       compression="gzip" if path.name.endswith(".gz") else None)


def parse_timestamps(df: pd.DataFrame, mapping: dict, convention: str) -> pd.Series:
    """Return bar-OPEN minute timestamps, naive IST."""
    inv = {v: k for k, v in mapping.items()}
    if "datetime" in inv:
        ts = pd.to_datetime(df[inv["datetime"]], errors="coerce",
                            dayfirst=False, format="mixed")
    elif "date" in inv and "time" in inv:
        d = df[inv["date"]].astype(str).str.strip()
        t = df[inv["time"]].astype(str).str.strip()
        # YMD arrives as 20120102 or 2012-01-02; Time as 09:15 or 0915 or 91500
        d = d.str.replace(r"[/.]", "-", regex=True)
        t = t.where(t.str.contains(":"), t.str.zfill(6).str.replace(
            r"^(\d{2})(\d{2})(\d{2})$", r"\1:\2:\3", regex=True))
        ts = pd.to_datetime(d + " " + t, errors="coerce", format="mixed")
    elif "date" in inv:
        ts = pd.to_datetime(df[inv["date"]], errors="coerce", format="mixed")
    else:
        raise ValueError("no datetime, date+time, or date column found")

    if convention == "close":
        # 09:16:00 labelled as close means the 09:15 bar; 09:15:59 means 09:15.
        exact = ts.dt.second.eq(0) & ts.dt.microsecond.eq(0)
        ts = ts.where(~exact, ts - pd.Timedelta(minutes=1))
    return ts.dt.floor("min")


def normalise(df: pd.DataFrame, mapping: dict, convention: str) -> pd.DataFrame:
    ts = parse_timestamps(df, mapping, convention)
    inv = {v: k for k, v in mapping.items()}
    missing = [f for f in ("open", "high", "low", "close") if f not in inv]
    if missing:
        raise ValueError(f"missing OHLC column(s): {missing}")

    out = pd.DataFrame({"ts": ts})
    for f in ("open", "high", "low", "close"):
        out[f] = pd.to_numeric(df[inv[f]], errors="coerce")
    out["volume"] = (pd.to_numeric(df[inv["volume"]], errors="coerce")
                     if "volume" in inv else 0)

    out = out.dropna(subset=["ts", "open", "high", "low", "close"])
    out["volume"] = out["volume"].fillna(0)
    # epoch_ms mirrors the store convention: naive IST read as if UTC
    out["epoch_ms"] = (out["ts"].astype("int64") // 1_000_000)
    out = out[["ts", "epoch_ms", "open", "high", "low", "close", "volume"]]
    return (out.sort_values("ts")
               .drop_duplicates(subset="ts", keep="last")
               .astype({"epoch_ms": "int64", "volume": "int64"})
               .reset_index(drop=True))


# --- ingest ---------------------------------------------------------------
def discover(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for g in DATA_GLOBS:
        files.extend(root.rglob(g))
    return sorted(set(files))


def ingest(path: Path, profile: str, dest: str, overrides: dict,
           convention: str | None, commit: bool, limit: int | None) -> int:
    prof = PROFILES.get(profile, PROFILES["auto"])
    convention = convention or prof["ts_convention"]
    known = canonical_symbols()
    if not known:
        print("[warn] tokens.csv missing -- symbols will not be validated "
              "against the universe")

    files = discover(path)
    if limit:
        files = files[:limit]
    if not files:
        raise SystemExit(f"no data files found under {path}")
    print(f"[ingest] {len(files)} file(s) under {path}")
    print(f"[ingest] profile={profile} dest={dest} ts_convention={convention} "
          f"commit={commit}")

    manifest = store.load_state(MANIFEST)
    stats = {"files": 0, "rows": 0, "written": 0, "skipped": 0, "unmatched": []}
    per_symbol: dict[str, int] = {}

    for i, f in enumerate(files, 1):
        try:
            raw = _read_any(f)
        except Exception as e:
            print(f"  [skip] {f.name}: unreadable ({e})")
            stats["skipped"] += 1
            continue
        if raw.empty:
            stats["skipped"] += 1
            continue

        mapping = build_column_map(list(raw.columns), overrides)
        inv = {v: k for k, v in mapping.items()}

        # resolve symbol
        sym = None
        if prof["symbol_from"] in ("column", "auto") and "symbol" in inv:
            vals = raw[inv["symbol"]].astype(str).unique()
            if len(vals) == 1:
                sym = known.get(_norm(vals[0]), vals[0].strip().upper())
        if sym is None:
            sym = symbol_from_filename(f, known)
        if sym is None and "symbol" in inv:
            sym = "__MULTI__"          # one file holding many symbols
        if sym is None:
            print(f"  [skip] {f.name}: cannot determine symbol")
            stats["skipped"] += 1
            stats["unmatched"].append(f.name)
            continue

        try:
            if sym == "__MULTI__":
                groups = raw.groupby(raw[inv["symbol"]].astype(str))
            else:
                groups = [(sym, raw)]
            for gsym, chunk in groups:
                canon = known.get(_norm(gsym), str(gsym).strip().upper())
                norm = normalise(chunk, mapping, convention)
                if norm.empty:
                    continue
                stats["rows"] += len(norm)
                per_symbol[canon] = per_symbol.get(canon, 0) + len(norm)
                if commit:
                    res = store.write_intraday(canon, dest, norm)
                    stats["written"] += res["added"]
        except Exception as e:
            print(f"  [skip] {f.name}: {e}")
            stats["skipped"] += 1
            continue

        stats["files"] += 1
        if i <= 3 or i % 100 == 0:
            print(f"  [{i}/{len(files)}] {f.name} -> {sym}  cols={mapping}")

    print(f"\n[ingest] files ok={stats['files']} skipped={stats['skipped']}")
    print(f"[ingest] rows parsed={stats['rows']:,}  symbols={len(per_symbol)}")
    if commit:
        print(f"[ingest] rows written={stats['written']:,} into intraday/{dest}/")
        manifest[datetime.now().isoformat(timespec="seconds")] = {
            "source": str(path), "profile": profile, "dest": dest,
            "ts_convention": convention, "files": stats["files"],
            "rows_written": stats["written"], "symbols": len(per_symbol),
        }
        store.save_state(MANIFEST, manifest)
    else:
        print("[ingest] DRY RUN -- nothing written. Re-run with --commit.")

    if per_symbol:
        s = pd.Series(per_symbol)
        print(f"[ingest] bars/symbol: min={s.min():,} median={int(s.median()):,} "
              f"max={s.max():,}")
    if stats["unmatched"]:
        print(f"[ingest] {len(stats['unmatched'])} unmatched filenames, e.g. "
              f"{stats['unmatched'][:5]}")
    return 0


# --- acceptance test ------------------------------------------------------
def validate(dest: str, price_tol: float, vol_tol: float,
             symbols: list[str] | None, verbose: bool,
             shortfall_tol: float = 0.05) -> int:
    """Reconstruct daily bars from vendor 1m data, compare to our daily store.

    Two conventions have to be handled or the test rejects good data:

    * The daily `open` is the **opening-auction** price, which lands in the
      pre-open block near 09:07 -- not in the 09:15 bar. A vendor shipping
      session-only (09:15-15:30) bars therefore cannot match the daily open,
      and its session volume is legitimately short by the pre-open block.
      So we auto-detect whether pre-open is present and switch from equality
      to containment (`high <= daily high`, `low >= daily low`, volume short by
      no more than `shortfall_tol`) when it is not.
    * The daily `close` is the closing-auction price, so `close` is never
      compared.

    Partial sessions (bar count well below a full day) are excluded rather than
    failed -- they are an artefact of when the data was cut, not a defect.
    """
    base = config.INTRADAY_DIR / dest
    if not base.exists():
        raise SystemExit(f"nothing ingested at {base}")
    syms = symbols or sorted(p.name for p in base.iterdir() if p.is_dir())
    print(f"[validate] {len(syms)} symbol(s) in intraday/{dest} "
          f"vs independent daily store")
    print(f"[validate] tolerance: price={price_tol} rupees, volume={vol_tol*100:.0f}%, "
          f"volume shortfall (session-only) <= {shortfall_tol*100:.0f}%")

    preopen_cut = pd.to_datetime(config.PREOPEN_CUTOFF).time()
    tot = {"sessions": 0, "pass": 0, "open": 0, "high": 0, "low": 0, "vol": 0,
           "no_eod": 0, "bad_ohlc": 0, "dupes": 0, "partial": 0, "open_skipped": 0}
    per_symbol_fail = {}
    bar_counts = []
    conventions = {}

    for sym in syms:
        parts = sorted((base / sym).glob("*.parquet"))
        if not parts:
            continue
        intra = pd.concat([store.read(p) for p in parts], ignore_index=True)
        if intra.empty:
            continue
        tot["dupes"] += int(intra["ts"].duplicated().sum())
        tot["bad_ohlc"] += int(((intra["high"] < intra["low"]) |
                                (intra["high"] < intra["open"]) |
                                (intra["high"] < intra["close"]) |
                                (intra["low"] > intra["open"]) |
                                (intra["low"] > intra["close"])).sum())

        eod = store.read(store.eod_path(sym, "1d"))
        if eod.empty:
            tot["no_eod"] += 1
            continue
        eod = eod.assign(d=eod["ts"].dt.date).set_index("d")

        intra = intra.assign(d=intra["ts"].dt.date)
        agg = intra.groupby("d").agg(o=("open", "first"), h=("high", "max"),
                                     l=("low", "min"), v=("volume", "sum"),
                                     n=("ts", "size"),
                                     first_t=("ts", "min"))
        # convention detection: does this feed carry the pre-open block?
        has_preopen = bool((agg["first_t"].dt.time <= preopen_cut).mean() > 0.5)
        conventions[sym] = "with pre-open" if has_preopen else "session-only"

        full = agg["n"].max()
        fails = 0
        for d, a in agg.iterrows():
            if d not in eod.index:
                continue
            if full and a.n < 0.9 * full:
                tot["partial"] += 1          # incomplete session, not a defect
                continue
            b = eod.loc[d]
            tot["sessions"] += 1
            bar_counts.append(int(a.n))
            ok = True

            if has_preopen:
                if abs(a.o - b.open) > price_tol:
                    tot["open"] += 1; ok = False
                if abs(a.h - b.high) > price_tol:
                    tot["high"] += 1; ok = False
                if abs(a.l - b.low) > price_tol:
                    tot["low"] += 1; ok = False
                if b.volume and abs(a.v - b.volume) / b.volume > vol_tol:
                    tot["vol"] += 1; ok = False
            else:
                # session-only: the daily extremes must CONTAIN the vendor's
                tot["open_skipped"] += 1
                if a.h > b.high + price_tol:
                    tot["high"] += 1; ok = False
                if a.l < b.low - price_tol:
                    tot["low"] += 1; ok = False
                if b.volume:
                    ratio = a.v / b.volume
                    if ratio > 1 + vol_tol or ratio < 1 - shortfall_tol:
                        tot["vol"] += 1; ok = False

            if ok:
                tot["pass"] += 1
            else:
                fails += 1
                if verbose and fails <= 3:
                    print(f"  {sym} {d} [{conventions[sym]}]: "
                          f"vendor o={a.o} h={a.h} l={a.l} v={a.v:,.0f} "
                          f"| eod o={b.open} h={b.high} l={b.low} v={b.volume:,.0f}")
        if fails:
            per_symbol_fail[sym] = fails

    n = tot["sessions"]
    if not n:
        print("[validate] no comparable sessions -- is the daily store built?")
        return 1
    rate = 100.0 * tot["pass"] / n

    conv_counts = pd.Series(conventions).value_counts().to_dict() if conventions else {}
    print(f"\n[validate] detected convention: {conv_counts}")
    print(f"[validate] sessions compared : {n:,}")
    print(f"[validate] reconciled        : {tot['pass']:,}  ({rate:.2f}%)")
    print(f"[validate] mismatches        : open={tot['open']} high={tot['high']} "
          f"low={tot['low']} volume={tot['vol']}")
    print(f"[validate] partial sessions excluded : {tot['partial']:,}")
    if tot["open_skipped"]:
        print(f"[validate] open not comparable on {tot['open_skipped']:,} sessions "
              f"(session-only feed: daily open is the opening-auction price)")
    print(f"[validate] duplicate minutes : {tot['dupes']:,}")
    print(f"[validate] OHLC violations   : {tot['bad_ohlc']:,}")
    print(f"[validate] symbols w/o daily : {tot['no_eod']}")
    if bar_counts:
        bc = pd.Series(bar_counts)
        print(f"[validate] bars/session      : min={bc.min()} median={int(bc.median())} "
              f"max={bc.max()}  (expect ~375 session-only, ~377 with pre-open)")
    if per_symbol_fail:
        worst = sorted(per_symbol_fail.items(), key=lambda kv: -kv[1])[:10]
        print(f"[validate] worst symbols     : {worst}")

    verdict = "PASS" if rate >= 99.0 else "FAIL"
    print(f"\n[validate] VERDICT: {verdict} "
          f"(acceptance threshold 99.00%, got {rate:.2f}%)")
    print("[validate] note: `close` is never compared -- the daily close is the "
          "closing-auction price and legitimately differs.")
    return 0 if verdict == "PASS" else 2


def promote(dest: str, into: str, commit: bool) -> int:
    src = config.INTRADAY_DIR / dest
    if not src.exists():
        raise SystemExit(f"nothing to promote at {src}")
    syms = sorted(p.name for p in src.iterdir() if p.is_dir())
    print(f"[promote] intraday/{dest} -> intraday/{into}  ({len(syms)} symbols) "
          f"commit={commit}")
    added_total = 0
    for i, sym in enumerate(syms, 1):
        for p in sorted((src / sym).glob("*.parquet")):
            df = store.read(p)
            if df.empty:
                continue
            if commit:
                a, _ = store.merge_write(df, store.intraday_path(sym, into, p.stem))
                added_total += a
            else:
                added_total += len(df)
        if i % 100 == 0:
            print(f"  {i}/{len(syms)}")
    if commit:
        print(f"[promote] merged, {added_total:,} new bars into intraday/{into}/")
    else:
        print(f"[promote] DRY RUN -- would consider {added_total:,} bars. "
              f"Re-run with --commit.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", type=Path, help="vendor file or directory")
    ap.add_argument("--profile", default="auto", choices=sorted(PROFILES))
    ap.add_argument("--dest", default="1m_vendor",
                    help="intraday namespace to write to (default keeps vendor "
                         "data isolated from 1m)")
    ap.add_argument("--map", default=None,
                    help="explicit column overrides, e.g. "
                         "\"Date Time=datetime,Vol=volume\"")
    ap.add_argument("--ts-convention", default=None, choices=["open", "close"],
                    help="whether vendor timestamps label the bar's open or close")
    ap.add_argument("--limit", type=int, default=None,
                    help="only process the first N files (for sampling)")
    ap.add_argument("--commit", action="store_true", help="actually write")
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--validate", action="store_true",
                    help="run the acceptance test against the daily store")
    ap.add_argument("--symbols", default=None, help="restrict validation")
    ap.add_argument("--price-tol", type=float, default=0.05)
    ap.add_argument("--vol-tol", type=float, default=0.02)
    ap.add_argument("--vol-shortfall-tol", type=float, default=0.05,
                    help="how far below the daily volume a session-only feed may "
                         "fall before it counts as a mismatch (pre-open block)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--promote", action="store_true",
                    help="merge --dest into --into after validation passes")
    ap.add_argument("--into", default="1m")
    args = ap.parse_args()

    if args.promote:
        return promote(args.dest, args.into, args.commit)
    if args.validate:
        syms = args.symbols.split(",") if args.symbols else None
        return validate(args.dest, args.price_tol, args.vol_tol, syms,
                        args.verbose, args.vol_shortfall_tol)
    if not args.path:
        ap.error("--path is required unless --validate or --promote is used")

    overrides = {}
    if args.map:
        for pair in args.map.split(","):
            k, _, v = pair.partition("=")
            overrides[k.strip()] = v.strip()
    return ingest(args.path, args.profile, args.dest, overrides,
                  args.ts_convention, args.commit and not args.dry_run,
                  args.limit)


if __name__ == "__main__":
    sys.exit(main())
