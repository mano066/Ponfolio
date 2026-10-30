"""CLI for catalog inspection, coverage planning, ingestion, and validation."""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import json
import os
import sys

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from research.intraday.providers import (  # type: ignore
        download_kaggle_dataset,
        fetch_alpha_vantage_month,
        fetch_dhan,
        fetch_upstox,
        fetch_yahoo,
        import_generic_csv,
        import_kaggle_nifty_bank_file,
    )
    from research.intraday.schema import (  # type: ignore
        CANONICAL_KEY,
        OHLCV_COLUMNS,
        add_quality_flags,
        dataframe_digest,
        deduplicate_canonical,
        lake_partition_paths,
        read_partitions,
        write_partitioned,
    )
else:
    from .providers import (
        download_kaggle_dataset,
        fetch_alpha_vantage_month,
        fetch_dhan,
        fetch_upstox,
        fetch_yahoo,
        import_generic_csv,
        import_kaggle_nifty_bank_file,
    )
    from .schema import (
        CANONICAL_KEY,
        OHLCV_COLUMNS,
        add_quality_flags,
        dataframe_digest,
        deduplicate_canonical,
        lake_partition_paths,
        read_partitions,
        write_partitioned,
    )

import hashlib
import re
import time


HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "source_catalog.json"
DEFAULT_LAKE = HERE.parent / "data" / "intraday_lake"


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def catalog_frame(catalog: dict) -> pd.DataFrame:
    rows = []
    for source in catalog["sources"]:
        rows.append(
            {
                "id": source["id"],
                "type": source["type"],
                "access": source["access"],
                "scope": source["instrument_scope"],
                "start": source.get("start"),
                "end": source.get("end") or "present/unknown",
                "intervals": ",".join(source.get("intervals", [])),
                "priority": source["priority"],
            }
        )
    return pd.DataFrame(rows).sort_values("priority", ascending=False)


def _fixed_date(value: str | None, today: date) -> date | None:
    if not value:
        return today
    if value == "rolling_60_days":
        return today - pd.Timedelta(days=60)
    if value == "rolling_3_months":
        return (pd.Timestamp(today) - pd.DateOffset(months=3)).date()
    if value == "rolling_5_years":
        return (pd.Timestamp(today) - pd.DateOffset(years=5)).date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def coverage_plan(
    catalog: dict,
    start: date,
    end: date,
    *,
    instrument_scope: str,
) -> pd.DataFrame:
    # Anchor rolling provider windows to the requested research end date. This
    # makes plans reproducible across machines and time zones.
    today = end
    rows = []
    for source in catalog["sources"]:
        source_start = _fixed_date(source.get("start"), today)
        source_end = _fixed_date(source.get("end"), today)
        overlap_start = max(start, source_start) if source_start else None
        overlap_end = min(end, source_end) if source_end else None
        has_overlap = bool(
            overlap_start and overlap_end and overlap_start <= overlap_end
        )
        scope = source["instrument_scope"]
        scope_match = (
            instrument_scope == "any"
            or instrument_scope in scope
            or instrument_scope == "equity"
            and any(
                marker in scope
                for marker in (
                    "stock",
                    "nse_instrument",
                    "equities",
                    "equity",
                    "symbols",
                )
            )
            or instrument_scope == "index"
            and "indice" in scope
        )
        candidate = bool(scope_match and (has_overlap or source_start is None))
        rows.append(
            {
                "source": source["id"],
                "eligible": candidate,
                "overlap_start": overlap_start,
                "overlap_end": overlap_end,
                "scope_match": scope_match,
                "verified_full_universe": bool(
                    source.get("verified_full_universe", False)
                ),
                "verified_full_request": bool(
                    candidate
                    and source.get("verified_full_universe", False)
                    and source_start
                    and source_start <= start
                    and source_end
                    and source_end >= end
                ),
                "access": source["access"],
                "coverage_confidence": source.get(
                    "coverage_confidence", "requires_live_sample"
                ),
                "notes": source["notes"],
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["eligible", "overlap_start"], ascending=[False, True]
    )


def merge_by_priority(
    frame: pd.DataFrame, catalog: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    priorities = {s["id"]: s["priority"] for s in catalog["sources"]}
    work = frame.copy()
    work["_priority"] = work["source"].map(priorities).fillna(0)
    work = work.sort_values(
        ["symbol", "timestamp_utc", "_priority"],
        ascending=[True, True, False],
    )
    conflicts = work[
        work.duplicated(["symbol", "timestamp_utc"], keep=False)
    ].copy()
    selected = work.drop_duplicates(
        ["symbol", "timestamp_utc"], keep="first"
    ).drop(columns="_priority")
    return selected.reset_index(drop=True), conflicts.reset_index(drop=True)


def command_catalog(args) -> None:
    print(catalog_frame(load_catalog(args.catalog)).to_string(index=False))


def command_plan(args) -> None:
    plan = coverage_plan(
        load_catalog(args.catalog),
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
        instrument_scope=args.scope,
    )
    print(plan.to_string(index=False))


def command_download_kaggle(args) -> None:
    catalog = load_catalog(args.catalog)
    source = next(s for s in catalog["sources"] if s["id"] == args.source)
    if source["adapter"] != "kaggle":
        raise SystemExit(f"{args.source} is not a Kaggle source")
    print(download_kaggle_dataset(source["dataset"]))


def command_ingest_kaggle_index(args) -> None:
    catalog = load_catalog(args.catalog)
    source = next(
        s for s in catalog["sources"] if s["id"] == "kaggle_nifty_bank_2008_2020"
    )
    root = args.dataset_root or download_kaggle_dataset(source["dataset"])
    files = [
        (root / "NIFTY_data" / "NIFTY_2008_2020.csv", "NIFTY"),
        (root / "BANK_NIFTY_data" / "BNF_2010_2020.csv", "BANKNIFTY"),
    ]
    all_paths = []
    aggregate = {
        "rows": 0,
        "duplicate_keys": 0,
        "invalid_ohlc": 0,
        "nonpositive_prices": 0,
        "outside_session": 0,
        "missing_volume": 0,
    }
    for path, symbol in files:
        if not path.exists():
            raise SystemExit(f"Expected dataset file is missing: {path}")
        frame = import_kaggle_nifty_bank_file(path, symbol=symbol)
        flagged, summary = add_quality_flags(frame)
        paths = write_partitioned(
            flagged, args.lake, file_stem=f"{symbol.lower()}-community"
        )
        all_paths.extend(paths)
        for key in aggregate:
            aggregate[key] += getattr(summary, key)
    print(
        json.dumps(
            {
                "dataset_root": str(root),
                "quality": aggregate,
                "partitions": len(all_paths),
                "files": [str(p) for p in all_paths],
            },
            indent=2,
        )
    )


def _persist(frame: pd.DataFrame, args) -> None:
    flagged, summary = add_quality_flags(frame)
    paths = write_partitioned(flagged, args.lake, file_stem=args.file_stem)
    print(json.dumps({"quality": summary.__dict__, "files": [str(p) for p in paths]}, indent=2))


def command_fetch_yahoo(args) -> None:
    frame = fetch_yahoo(args.symbol, period=args.period, interval=args.interval)
    if frame.empty:
        raise SystemExit("No Yahoo rows returned")
    _persist(frame, args)


def command_fetch_alpha(args) -> None:
    frame = fetch_alpha_vantage_month(
        args.symbol, args.month, interval=args.interval
    )
    if frame.empty:
        raise SystemExit("No Alpha Vantage rows returned")
    _persist(frame, args)


def command_fetch_upstox(args) -> None:
    frame = fetch_upstox(
        args.instrument_key,
        args.symbol,
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
        interval_minutes=args.interval_minutes,
    )
    if frame.empty:
        raise SystemExit("No Upstox rows returned")
    _persist(frame, args)


def command_fetch_dhan(args) -> None:
    frame = fetch_dhan(
        args.security_id,
        args.symbol,
        datetime.fromisoformat(args.start),
        datetime.fromisoformat(args.end),
        interval_minutes=args.interval_minutes,
    )
    if frame.empty:
        raise SystemExit("No Dhan rows returned")
    _persist(frame, args)


def command_import_csv(args) -> None:
    frame = import_generic_csv(
        args.path,
        symbol=args.symbol,
        source=args.source,
        timestamp_col=args.timestamp_col,
        interval=args.interval,
    )
    _persist(frame, args)


def command_validate(args) -> None:
    paths = lake_partition_paths(args.lake)
    frame = read_partitions(paths)
    flagged, summary = add_quality_flags(frame)
    print(json.dumps({"quality": summary.__dict__, "partitions": len(paths)}, indent=2))
    if not summary.clean:
        raise SystemExit(2)


def command_merge(args) -> None:
    paths = lake_partition_paths(args.lake)
    frame = read_partitions(paths)
    selected, conflicts = merge_by_priority(frame, load_catalog(args.catalog))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_parquet(output, index=False)
    conflict_path = output.with_name(output.stem + "-conflicts.parquet")
    conflicts.to_parquet(conflict_path, index=False)
    print(
        json.dumps(
            {
                "selected_rows": len(selected),
                "conflict_rows": len(conflicts),
                "output": str(output),
                "conflicts": str(conflict_path),
            },
            indent=2,
        )
    )


_LEGACY_HASH_RE = re.compile(r"^(?P<stem>.+)-[0-9a-f]{6,}$")


def _resolve_lake_path(raw: str | Path) -> Path:
    """Resolve and hard-validate a lake path before any destructive operation.

    Refuses the filesystem root, the user's home directory, and the repository
    root/tree so a mistyped or empty argument can never rewrite unrelated files.
    The target must be an existing directory that actually contains parquet
    partitions (i.e. looks like a lake).
    """
    resolved = Path(raw).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise SystemExit(f"--lake must be an existing directory: {resolved}")

    forbidden = {
        Path(resolved.anchor).resolve(),      # drive / filesystem root
        Path.home().resolve(),                # home directory
        HERE.parents[1].resolve(),            # repository root
        (HERE.parent / "data").resolve(),     # shared research/data dir itself
        HERE.resolve(),                       # the intraday package dir
    }
    if resolved in forbidden:
        raise SystemExit(f"Refusing to operate on protected path: {resolved}")
    if resolved in HERE.parents:
        raise SystemExit(
            f"Refusing to operate on an ancestor of the code tree: {resolved}"
        )
    if not any(resolved.rglob("*.parquet")):
        raise SystemExit(
            f"No parquet partitions found under {resolved} — refusing to treat "
            "it as a lake"
        )
    return resolved


def _lake_partition_groups(lake: Path) -> dict[tuple[Path, str], list[Path]]:
    """Group every canonical parquet file in the lake by (dir, logical stem).

    Legacy ``{stem}-<hash>.parquet`` and current ``{stem}.parquet`` files in the
    same directory collapse to one logical partition. Quarantine, temp, and
    conflict-sidecar files are ignored so repair never re-ingests them.
    """
    groups: dict[tuple[Path, str], list[Path]] = {}
    quarantine = (lake / "_quarantine").resolve()
    for path in sorted(lake.rglob("*.parquet")):
        if quarantine in path.resolve().parents:
            continue
        name = path.name
        if name.endswith(".tmp.parquet") or name.endswith(".conflicts.parquet"):
            continue
        stem = path.stem  # filename without .parquet
        match = _LEGACY_HASH_RE.match(stem)
        logical = match.group("stem") if match else stem
        groups.setdefault((path.parent, logical), []).append(path)
    return groups


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def command_repair_lake(args) -> None:
    """Deduplicate and consolidate one explicitly-supplied lake.

    Dry-run is mandatory: without --apply nothing is written. Detects exact
    duplicate canonical keys (source+symbol+interval+timestamp_utc), separates
    identical-OHLCV duplicates (safe to collapse) from conflicting duplicates
    (different OHLCV — never averaged, preserved to a conflict sidecar), and on
    --apply rewrites each affected partition atomically, verifies the re-read,
    and moves superseded legacy files into a _quarantine tree (never deletes).
    """
    lake = _resolve_lake_path(args.lake)
    apply = bool(args.apply)
    started = time.time()
    started_iso = datetime.now().isoformat(timespec="seconds")

    groups = _lake_partition_groups(lake)
    report_partitions = []
    totals = {
        "partitions_scanned": 0,
        "partitions_affected": 0,
        "rows_before": 0,
        "rows_after": 0,
        "exact_duplicate_rows": 0,
        "identical_dup_keys": 0,
        "conflict_keys": 0,
        "legacy_files_quarantined": 0,
    }

    for (parent, stem), members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        totals["partitions_scanned"] += 1
        frames = [pd.read_parquet(m) for m in members]
        combined = pd.concat(frames, ignore_index=True)
        deduped, exact_dups, conflicts = deduplicate_canonical(combined)

        key = [c for c in CANONICAL_KEY if c in combined.columns]
        dup_key_mask = combined.duplicated(key, keep=False)
        total_dup_keys = int(combined[dup_key_mask].drop_duplicates(key).shape[0])
        conflict_keys = (
            int(conflicts.drop_duplicates(key).shape[0]) if not conflicts.empty else 0
        )
        identical_dup_keys = total_dup_keys - conflict_keys

        canonical = parent / f"{stem}.parquet"
        legacy_members = [m for m in members if m != canonical]
        needs_repair = (
            exact_dups > 0
            or not conflicts.empty
            or bool(legacy_members)
            or len(members) > 1
        )

        rel = parent.relative_to(lake)
        entry = {
            "partition": str(rel).replace("\\", "/"),
            "stem": stem,
            "files": [m.name for m in members],
            "rows_before": int(len(combined)),
            "rows_after": int(len(deduped)),
            "exact_duplicate_rows": int(exact_dups),
            "identical_dup_keys": int(identical_dup_keys),
            "conflict_keys": int(conflict_keys),
            "legacy_files": [m.name for m in legacy_members],
            "needs_repair": needs_repair,
            "applied": False,
        }

        totals["rows_before"] += int(len(combined))
        totals["exact_duplicate_rows"] += int(exact_dups)
        totals["identical_dup_keys"] += int(identical_dup_keys)
        totals["conflict_keys"] += int(conflict_keys)

        if not needs_repair:
            totals["rows_after"] += int(len(combined))
            continue

        totals["partitions_affected"] += 1
        entry["hash_before"] = {
            m.name: _file_sha256(m) for m in members
        }

        if apply:
            if not conflicts.empty:
                conflict_path = parent / f"{stem}.conflicts.parquet"
                conflict_tmp = conflict_path.with_suffix(".tmp.parquet")
                conflicts.to_parquet(conflict_tmp, index=False)
                conflict_tmp.replace(conflict_path)

            temporary = canonical.with_suffix(".tmp.parquet")
            deduped.to_parquet(temporary, index=False)
            temporary.replace(canonical)
            verify = pd.read_parquet(canonical)
            if len(verify) != len(deduped):
                raise RuntimeError(
                    f"repair verify failed for {canonical}: wrote "
                    f"{len(deduped)} rows, re-read {len(verify)}"
                )
            for legacy in legacy_members:
                quarantine_dir = lake / "_quarantine" / rel
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                legacy.replace(quarantine_dir / legacy.name)
                totals["legacy_files_quarantined"] += 1
            entry["applied"] = True
            entry["hash_after"] = _file_sha256(canonical)
            totals["rows_after"] += int(len(deduped))
        else:
            totals["rows_after"] += int(len(deduped))

        report_partitions.append(entry)

    manifest = {
        "lake": str(lake),
        "mode": "apply" if apply else "dry-run",
        "started_at": started_iso,
        "execution_seconds": round(time.time() - started, 3),
        "totals": totals,
        "affected_partitions": report_partitions,
    }
    if apply:
        stamp = started_iso.replace(":", "").replace("-", "")
        manifest_path = lake / f"_repair_manifest_{stamp}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)

    print(json.dumps(manifest, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("catalog")
    p.set_defaults(func=command_catalog)

    p = sub.add_parser("plan")
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--scope", choices=["any", "equity", "index"], default="equity")
    p.set_defaults(func=command_plan)

    p = sub.add_parser("download-kaggle")
    p.add_argument("source")
    p.set_defaults(func=command_download_kaggle)

    p = sub.add_parser("ingest-kaggle-index")
    p.add_argument("--dataset-root", type=Path)
    p.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    p.set_defaults(func=command_ingest_kaggle_index)

    p = sub.add_parser("fetch-upstox")
    p.add_argument("symbol")
    p.add_argument("instrument_key")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--interval-minutes", type=int, default=1)
    p.add_argument("--interval", default="1m")
    p.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    p.add_argument("--file-stem", default="upstox")
    p.set_defaults(func=command_fetch_upstox)

    p = sub.add_parser("fetch-dhan")
    p.add_argument("symbol")
    p.add_argument("security_id")
    p.add_argument("--start", required=True, help="ISO date or datetime")
    p.add_argument("--end", required=True, help="ISO date or datetime")
    p.add_argument("--interval-minutes", type=int, default=1)
    p.add_argument("--interval", default="1m")
    p.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    p.add_argument("--file-stem", default="dhan")
    p.set_defaults(func=command_fetch_dhan)

    for name, func in (
        ("fetch-yahoo", command_fetch_yahoo),
        ("fetch-alpha", command_fetch_alpha),
        ("import-csv", command_import_csv),
    ):
        p = sub.add_parser(name)
        p.add_argument("symbol")
        p.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
        p.add_argument("--file-stem", default="part")
        p.add_argument("--interval", default="1m" if name != "fetch-alpha" else "1min")
        if name == "fetch-yahoo":
            p.add_argument("--period", default="7d")
        elif name == "fetch-alpha":
            p.add_argument("--month", required=True)
        else:
            p.add_argument("path", type=Path)
            p.add_argument("--source", required=True)
            p.add_argument("--timestamp-col", default="timestamp")
        p.set_defaults(func=func)

    p = sub.add_parser("validate")
    p.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    p.set_defaults(func=command_validate)

    p = sub.add_parser("merge")
    p.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_LAKE.parent / "canonical_1m.parquet",
    )
    p.set_defaults(func=command_merge)

    p = sub.add_parser(
        "repair-lake",
        help="Deduplicate/consolidate a lake. Dry-run unless --apply is given.",
    )
    p.add_argument(
        "--lake",
        required=True,
        help="Absolute path to the lake to repair (no default — must be explicit).",
    )
    p.add_argument("--dry-run", action="store_true", help="Report only (default).")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Perform the repair. Without this flag the command only reports.",
    )
    p.set_defaults(func=command_repair_lake)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
