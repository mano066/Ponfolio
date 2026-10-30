"""Canonical schema, normalization, partitioning, and quality checks.

The lake stores raw/as-traded one-minute candles. Derived timeframes must be
resampled from these rows after source selection and deduplication.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import hashlib
import json
import re

import numpy as np
import pandas as pd


CANONICAL_COLUMNS = [
    "timestamp_utc",
    "timestamp_ist",
    "symbol",
    "instrument_id",
    "exchange",
    "interval",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "source_file",
    "adjusted",
    "ingested_at_utc",
    "quality_flags",
]

# The identity of one canonical candle. Two rows sharing this key are the "same"
# observation; if their OHLCV agrees they are exact duplicates (keep one), if it
# differs they are a conflict (never silently averaged — reported/kept for
# source-priority resolution). Used by write_partitioned() and repair-lake.
CANONICAL_KEY = ["source", "symbol", "interval", "timestamp_utc"]
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def deduplicate_canonical(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, int, pd.DataFrame]:
    """Split a frame into (deduplicated_rows, exact_duplicate_row_count,
    conflicting_rows).

    Grouping is by CANONICAL_KEY. Within a key group:
      * if every OHLCV column is single-valued -> exact duplicate; one
        deterministic row is retained (sorted by ingested_at_utc then a stable
        content hash, keep last).
      * if any OHLCV column differs -> conflict; ALL rows of that key are
        returned in the conflict frame and the deterministic keep-last row is
        still chosen for the deduplicated output so a write never averages or
        drops data silently.
    Pure function: no I/O.
    """
    if frame.empty:
        return frame.copy(), 0, frame.iloc[0:0].copy()
    key = [c for c in CANONICAL_KEY if c in frame.columns]
    work = frame.copy()
    # Deterministic ordering so "keep last" is reproducible across machines and
    # runs regardless of the order files were read in.
    sort_cols = key + [c for c in ("ingested_at_utc",) if c in work.columns]
    work = work.sort_values(sort_cols, kind="stable").reset_index(drop=True)

    dup_mask = work.duplicated(key, keep=False)
    exact_duplicate_rows = int(work.duplicated(key, keep="first").sum())

    conflict_rows = work.iloc[0:0].copy()
    if dup_mask.any():
        ohlcv = [c for c in OHLCV_COLUMNS if c in work.columns]
        grouped = work[dup_mask].groupby(key, dropna=False, observed=True)
        # A key group is a conflict when any OHLCV column has >1 distinct value.
        nunique = grouped[ohlcv].nunique()
        conflict_keys = nunique[(nunique > 1).any(axis=1)].index
        if len(conflict_keys):
            idx = work.set_index(key).index
            conflict_rows = work[idx.isin(conflict_keys)].copy()

    deduped = work.drop_duplicates(key, keep="last").reset_index(drop=True)
    return deduped, exact_duplicate_rows, conflict_rows


@dataclass(frozen=True)
class QualitySummary:
    rows: int
    duplicate_keys: int
    invalid_ohlc: int
    nonpositive_prices: int
    outside_session: int
    missing_volume: int

    @property
    def clean(self) -> bool:
        return not any(
            (self.duplicate_keys, self.invalid_ohlc, self.nonpositive_prices)
        )


def safe_symbol(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(symbol).strip().upper())


def _timestamp_series(values, timezone_name: str) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    if parsed.dt.tz is None:
        parsed = parsed.dt.tz_localize(
            timezone_name, ambiguous="NaT", nonexistent="shift_forward"
        )
    else:
        parsed = parsed.dt.tz_convert(timezone_name)
    return parsed


def normalize_candles(
    frame: pd.DataFrame,
    *,
    symbol: str,
    source: str,
    timestamp_col: str = "timestamp",
    instrument_id: str | None = None,
    exchange: str = "NSE",
    interval: str = "1m",
    source_file: str = "",
    timezone_name: str = "Asia/Kolkata",
    adjusted: bool = False,
) -> pd.DataFrame:
    """Normalize a provider frame into the canonical candle schema."""
    work = frame.copy()
    work.columns = [str(c).strip().lower().replace(" ", "_") for c in work.columns]
    timestamp_col = timestamp_col.lower().replace(" ", "_")
    required = {timestamp_col, "open", "high", "low", "close"}
    missing = sorted(required - set(work.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    timestamps_ist = _timestamp_series(work[timestamp_col], timezone_name)
    out = pd.DataFrame(
        {
            "timestamp_ist": timestamps_ist,
            "open": pd.to_numeric(work["open"], errors="coerce"),
            "high": pd.to_numeric(work["high"], errors="coerce"),
            "low": pd.to_numeric(work["low"], errors="coerce"),
            "close": pd.to_numeric(work["close"], errors="coerce"),
            "volume": pd.to_numeric(
                work["volume"] if "volume" in work else np.nan, errors="coerce"
            ),
        }
    )
    out["timestamp_utc"] = out["timestamp_ist"].dt.tz_convert("UTC")
    out["symbol"] = safe_symbol(symbol)
    out["instrument_id"] = instrument_id or ""
    out["exchange"] = exchange
    out["interval"] = interval
    out["source"] = source
    out["source_file"] = source_file
    out["adjusted"] = bool(adjusted)
    out["ingested_at_utc"] = datetime.now(timezone.utc).isoformat()
    out["quality_flags"] = ""
    out = out.dropna(
        subset=["timestamp_utc", "open", "high", "low", "close"]
    ).sort_values("timestamp_utc")
    return out[CANONICAL_COLUMNS].reset_index(drop=True)


def add_quality_flags(frame: pd.DataFrame) -> tuple[pd.DataFrame, QualitySummary]:
    out = frame.copy()
    flags: list[list[str]] = [[] for _ in range(len(out))]
    invalid_ohlc = (
        (out["high"] < out[["open", "close"]].max(axis=1))
        | (out["low"] > out[["open", "close"]].min(axis=1))
        | (out["high"] < out["low"])
    )
    nonpositive = (out[["open", "high", "low", "close"]] <= 0).any(axis=1)
    ist = pd.to_datetime(out["timestamp_ist"], errors="coerce")
    minutes = ist.dt.hour * 60 + ist.dt.minute
    # Covers both the historic 09:00 start and modern 09:15 start. A
    # date-aware session calendar is applied at the research/resampling stage.
    outside_session = (minutes < 9 * 60) | (minutes >= 15 * 60 + 30)
    missing_volume = out["volume"].isna()
    duplicates = out.duplicated(["symbol", "timestamp_utc"], keep=False)

    for mask, label in (
        (invalid_ohlc, "invalid_ohlc"),
        (nonpositive, "nonpositive_price"),
        (outside_session, "outside_regular_session"),
        (missing_volume, "missing_volume"),
        (duplicates, "duplicate_key"),
    ):
        for idx in np.flatnonzero(mask.to_numpy()):
            flags[idx].append(label)
    out["quality_flags"] = ["|".join(row) for row in flags]

    summary = QualitySummary(
        rows=len(out),
        duplicate_keys=int(duplicates.sum()),
        invalid_ohlc=int(invalid_ohlc.sum()),
        nonpositive_prices=int(nonpositive.sum()),
        outside_session=int(outside_session.sum()),
        missing_volume=int(missing_volume.sum()),
    )
    return out, summary


def dataframe_digest(frame: pd.DataFrame) -> str:
    stable = frame.sort_values(["symbol", "timestamp_utc"]).reset_index(drop=True)
    # Vectorized stable hashes avoid serializing millions of rows to CSV merely
    # to compute a content identity. Column names/dtypes are included so two
    # differently shaped frames cannot share a digest accidentally.
    row_hashes = pd.util.hash_pandas_object(stable, index=False).to_numpy()
    metadata = "|".join(
        f"{column}:{stable[column].dtype}" for column in stable.columns
    ).encode("utf-8")
    digest = hashlib.sha256(metadata)
    digest.update(row_hashes.tobytes())
    return digest.hexdigest()


def _partition_member_files(target_dir: Path, stem: str) -> list[Path]:
    """Every parquet file belonging to one logical partition file-stem.

    Matches the deterministic canonical name ``{stem}.parquet`` and any legacy
    hash-suffixed variant ``{stem}-<hash>.parquet`` written by older ingests.
    Temporary (``.tmp.parquet``), conflict sidecar, and manifest files are
    excluded so they never re-enter the data set.
    """
    if not target_dir.exists():
        return []
    canonical = target_dir / f"{stem}.parquet"
    members: list[Path] = []
    for path in sorted(target_dir.glob(f"{stem}*.parquet")):
        name = path.name
        if name.endswith(".tmp.parquet") or name.endswith(".conflicts.parquet"):
            continue
        if path == canonical or name.startswith(f"{stem}-"):
            members.append(path)
    return members


def write_partitioned(
    frame: pd.DataFrame,
    root: Path,
    *,
    file_stem: str = "part",
) -> list[Path]:
    """Upsert source/symbol/year/month partitions with a sidecar manifest.

    Idempotent and resumable. For each partition the incoming rows are combined
    with EVERY existing file for that logical file-stem — both the current
    deterministic ``{stem}.parquet`` and any legacy hash-suffixed
    ``{stem}-<hash>.parquet`` — then deduplicated on CANONICAL_KEY. OHLCV
    conflicts are detected and written to a ``.conflicts.parquet`` sidecar
    rather than silently averaged. One deterministic canonical file is written
    atomically and re-opened to verify before any legacy file is moved into the
    ``_quarantine`` tree (never deleted). A crash before the atomic replace
    leaves the previous partition intact.
    """
    root = Path(root)
    written: list[Path] = []
    work = frame.copy()
    ts = pd.to_datetime(work["timestamp_ist"])
    work["_year"] = ts.dt.year
    work["_month"] = ts.dt.month
    stem = safe_symbol(file_stem).lower()

    for (source, symbol, year, month), part in work.groupby(
        ["source", "symbol", "_year", "_month"], observed=True
    ):
        rel_partition = (
            Path(f"source={safe_symbol(source)}")
            / f"symbol={safe_symbol(symbol)}"
            / f"year={int(year):04d}"
            / f"month={int(month):02d}"
        )
        target_dir = root / rel_partition
        target_dir.mkdir(parents=True, exist_ok=True)
        payload = part.drop(columns=["_year", "_month"]).reset_index(drop=True)
        parquet = target_dir / f"{stem}.parquet"

        members = _partition_member_files(target_dir, stem)
        legacy_members = [m for m in members if m != parquet]
        frames = [pd.read_parquet(m) for m in members] + [payload]
        combined = pd.concat(frames, ignore_index=True)

        deduped, exact_dups, conflicts = deduplicate_canonical(combined)

        # Conflicts are preserved for later source-priority resolution, never
        # averaged away. Written before the canonical file so they survive even
        # if this partition is inspected mid-migration.
        conflict_path = target_dir / f"{stem}.conflicts.parquet"
        if not conflicts.empty:
            conflict_tmp = conflict_path.with_suffix(".tmp.parquet")
            conflicts.to_parquet(conflict_tmp, index=False)
            conflict_tmp.replace(conflict_path)

        full_digest = dataframe_digest(deduped)
        temporary = parquet.with_suffix(".tmp.parquet")
        deduped.to_parquet(temporary, index=False)
        temporary.replace(parquet)

        # Verify the written canonical file re-opens with the expected row count
        # BEFORE any legacy file is quarantined — a corrupt/short write must not
        # cause data loss.
        verify = pd.read_parquet(parquet)
        if len(verify) != len(deduped):
            raise RuntimeError(
                f"partition verify failed for {parquet}: "
                f"wrote {len(deduped)} rows, re-read {len(verify)}"
            )

        # Only now retire legacy hash-suffixed files: move (never delete) them
        # into a mirrored _quarantine tree so the operation stays recoverable.
        for legacy in legacy_members:
            quarantine_dir = root / "_quarantine" / rel_partition
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            legacy.replace(quarantine_dir / legacy.name)

        manifest = parquet.with_suffix(".manifest.json")
        manifest_temporary = manifest.with_suffix(".tmp.json")
        manifest_temporary.write_text(
            json.dumps(
                {
                    "path": str(parquet),
                    "rows": len(deduped),
                    "exact_duplicates_removed": exact_dups,
                    "conflict_rows": int(len(conflicts)),
                    "legacy_files_quarantined": [m.name for m in legacy_members],
                    "first_timestamp_utc": str(deduped["timestamp_utc"].min()),
                    "last_timestamp_utc": str(deduped["timestamp_utc"].max()),
                    "sha256_rows": full_digest,
                    "source": source,
                    "symbol": symbol,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        manifest_temporary.replace(manifest)
        written.append(parquet)
    return written


def lake_partition_paths(lake: Path) -> list[Path]:
    """Every live canonical parquet file in a lake.

    Excludes the ``_quarantine`` tree (superseded legacy files retained for
    recovery), ``.tmp.parquet`` (interrupted writes), and ``.conflicts.parquet``
    (conflict sidecars) so lake readers never double-count or resurrect them.
    """
    lake = Path(lake)
    out: list[Path] = []
    for path in sorted(lake.rglob("*.parquet")):
        if "_quarantine" in path.parts:
            continue
        name = path.name
        if name.endswith(".tmp.parquet") or name.endswith(".conflicts.parquet"):
            continue
        out.append(path)
    return out


def read_partitions(paths: Iterable[Path]) -> pd.DataFrame:
    frames = [pd.read_parquet(path) for path in paths]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=CANONICAL_COLUMNS
    )
