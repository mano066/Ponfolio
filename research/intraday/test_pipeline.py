from __future__ import annotations

from datetime import date
from pathlib import Path
import contextlib
import io
import json
import tempfile
import types
import unittest

import pandas as pd

from research.intraday.pipeline import (
    command_repair_lake,
    coverage_plan,
    load_catalog,
    merge_by_priority,
    _resolve_lake_path,
)
from research.intraday.schema import (
    add_quality_flags,
    deduplicate_canonical,
    normalize_candles,
    read_partitions,
    write_partitioned,
)


class IntradayPipelineTests(unittest.TestCase):
    def setUp(self):
        self.raw = pd.DataFrame(
            {
                "timestamp": [
                    "2026-07-23 09:15:00",
                    "2026-07-23 09:16:00",
                ],
                "open": [100.0, 101.0],
                "high": [102.0, 103.0],
                "low": [99.0, 100.0],
                "close": [101.0, 102.0],
                "volume": [1000, 1200],
            }
        )

    def test_normalize_and_quality(self):
        frame = normalize_candles(
            self.raw, symbol="HDFCBANK.NS", source="yahoo_recent"
        )
        flagged, summary = add_quality_flags(frame)
        self.assertEqual(summary.rows, 2)
        self.assertTrue(summary.clean)
        self.assertEqual(str(flagged.timestamp_ist.dt.tz), "Asia/Kolkata")

    def test_invalid_ohlc_is_flagged(self):
        raw = self.raw.copy()
        raw.loc[0, "high"] = 98
        frame = normalize_candles(raw, symbol="TEST.NS", source="yahoo_recent")
        flagged, summary = add_quality_flags(frame)
        self.assertEqual(summary.invalid_ohlc, 1)
        self.assertIn("invalid_ohlc", flagged.quality_flags.iloc[0])

    def test_partition_round_trip(self):
        frame = normalize_candles(
            self.raw, symbol="HDFCBANK.NS", source="yahoo_recent"
        )
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_partitioned(frame, Path(tmp))
            loaded = read_partitions(paths)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded.symbol.unique().tolist(), ["HDFCBANK.NS"])

    def test_partition_upsert_is_idempotent(self):
        frame = normalize_candles(
            self.raw, symbol="HDFCBANK.NS", source="yahoo_recent"
        )
        with tempfile.TemporaryDirectory() as tmp:
            first = write_partitioned(
                frame, Path(tmp), file_stem="repeatable"
            )
            second = write_partitioned(
                frame, Path(tmp), file_stem="repeatable"
            )
            loaded = read_partitions(second)
            self.assertEqual(first, second)
            self.assertEqual(len(list(Path(tmp).rglob("*.parquet"))), 1)
            self.assertEqual(len(loaded), len(frame))

    def test_priority_merge_keeps_higher_priority_source(self):
        catalog = load_catalog()
        low = normalize_candles(
            self.raw.iloc[:1], symbol="HDFCBANK.NS", source="yahoo_recent"
        )
        high = normalize_candles(
            self.raw.iloc[:1].assign(close=105),
            symbol="HDFCBANK.NS",
            source="upstox_v3",
        )
        selected, conflicts = merge_by_priority(
            pd.concat([low, high], ignore_index=True), catalog
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected.source.iloc[0], "upstox_v3")
        self.assertEqual(selected.close.iloc[0], 105)
        self.assertEqual(len(conflicts), 2)

    def test_2010_equity_plan_exposes_no_verified_free_full_coverage(self):
        plan = coverage_plan(
            load_catalog(),
            date(2010, 1, 1),
            date(2026, 7, 24),
            instrument_scope="equity",
        )
        eligible = plan[plan.eligible]
        self.assertFalse(plan.verified_full_request.any())
        self.assertFalse(
            (
                eligible.access.eq("free_no_key")
                & eligible.overlap_start.le(date(2010, 1, 1))
            ).any()
        )


class LegacyPartitionUpsertTests(unittest.TestCase):
    """F2 — write_partitioned must merge legacy hash-suffixed files with the
    current deterministic partition, dedupe on the canonical key, report (not
    average) OHLCV conflicts, and quarantine (not delete) legacy files."""

    def _frame(self, closes, *, source="yahoo_recent", minute_start=15):
        rows = len(closes)
        raw = pd.DataFrame(
            {
                "timestamp": [
                    f"2026-07-23 09:{minute_start + i:02d}:00" for i in range(rows)
                ],
                "open": [100.0 + i for i in range(rows)],
                "high": [102.0 + i for i in range(rows)],
                "low": [99.0 + i for i in range(rows)],
                "close": list(closes),
                "volume": [1000 + i for i in range(rows)],
            }
        )
        return normalize_candles(raw, symbol="HDFCBANK.NS", source=source)

    def _seed_legacy(self, tmp: Path, frame: pd.DataFrame, stem: str) -> Path:
        """Write a partition then rename its canonical file to a legacy
        hash-suffixed name, simulating an older ingest."""
        write_partitioned(frame, tmp, file_stem=stem)
        canonical = next(tmp.rglob(f"{stem}.parquet"))
        legacy = canonical.with_name(f"{stem}-70c9deadbeef1234.parquet")
        canonical.replace(legacy)
        canonical.with_suffix(".manifest.json").unlink(missing_ok=True)
        return legacy

    def test_upsert_merges_legacy_and_current_into_one_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            legacy = self._seed_legacy(tmp, self._frame([101.0, 102.0]), "src")
            self.assertTrue(legacy.exists())
            # Ingest overlapping rows (first minute identical, one new minute).
            write_partitioned(self._frame([101.0, 102.0, 103.0]), tmp, file_stem="src")

            live = [p for p in tmp.rglob("*.parquet")
                    if "_quarantine" not in p.parts]
            self.assertEqual([p.name for p in live], ["src.parquet"],
                             "exactly one canonical logical partition must remain")
            loaded = read_partitions(live)
            self.assertEqual(len(loaded), 3, "exact duplicates collapsed to unique keys")
            quarantined = list((tmp / "_quarantine").rglob("*.parquet"))
            self.assertEqual(len(quarantined), 1, "legacy file moved, not deleted")

    def test_conflicts_are_reported_not_averaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._seed_legacy(tmp, self._frame([100.0]), "src")
            # Same canonical key (same timestamp/source/symbol/interval), but a
            # DIFFERENT close — a genuine conflict.
            write_partitioned(self._frame([105.0]), tmp, file_stem="src")

            canonical = next(tmp.rglob("src.parquet"))
            loaded = pd.read_parquet(canonical)
            self.assertEqual(len(loaded), 1, "one deterministic row kept")
            self.assertIn(loaded.close.iloc[0], (100.0, 105.0),
                          "kept an actual observed value, never an average")
            self.assertNotEqual(loaded.close.iloc[0], 102.5, "must not average")
            conflicts = next(tmp.rglob("src.conflicts.parquet"))
            conflict_rows = pd.read_parquet(conflicts)
            self.assertEqual(len(conflict_rows), 2, "both conflicting rows preserved")
            self.assertEqual(sorted(conflict_rows.close.tolist()), [100.0, 105.0])

    def test_reingestion_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            frame = self._frame([101.0, 102.0, 103.0])
            write_partitioned(frame, tmp, file_stem="src")
            write_partitioned(frame, tmp, file_stem="src")
            write_partitioned(frame, tmp, file_stem="src")
            live = [p for p in tmp.rglob("*.parquet")
                    if "_quarantine" not in p.parts]
            self.assertEqual(len(live), 1)
            self.assertEqual(len(read_partitions(live)), 3)

    def test_stray_tmp_file_never_reenters_dataset(self):
        # A crash between the tmp write and the atomic replace leaves a stray
        # .tmp.parquet; it must never be read back as data.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            write_partitioned(self._frame([101.0, 102.0]), tmp, file_stem="src")
            canonical = next(tmp.rglob("src.parquet"))
            stray = canonical.with_suffix(".tmp.parquet")
            pd.read_parquet(canonical).to_parquet(stray, index=False)
            write_partitioned(self._frame([101.0, 102.0, 103.0]), tmp, file_stem="src")
            live = [p for p in tmp.rglob("*.parquet")
                    if "_quarantine" not in p.parts and not p.name.endswith(".tmp.parquet")]
            self.assertEqual([p.name for p in live], ["src.parquet"])
            self.assertEqual(len(read_partitions(live)), 3)


class RepairLakeTests(unittest.TestCase):
    """F1 — repair-lake dry-run/apply/idempotency and path safety."""

    def _run(self, lake: Path, *, apply: bool) -> dict:
        args = types.SimpleNamespace(lake=str(lake), apply=apply, dry_run=not apply)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            command_repair_lake(args)
        return json.loads(buf.getvalue())

    def _seed_lake_with_dupes(self, tmp: Path) -> Path:
        raw = pd.DataFrame(
            {
                "timestamp": ["2016-07-01 09:15:00", "2016-07-01 09:16:00"],
                "open": [100.0, 101.0], "high": [102.0, 103.0],
                "low": [99.0, 100.0], "close": [101.0, 102.0],
                "volume": [1000, 1200],
            }
        )
        frame = normalize_candles(raw, symbol="NIFTY", source="kaggle_nifty_bank_2008_2020")
        write_partitioned(frame, tmp, file_stem="nifty-community")
        canonical = next(tmp.rglob("nifty-community.parquet"))
        # Make it a legacy hash file containing an exact duplicate of every row.
        doubled = pd.concat([pd.read_parquet(canonical)] * 2, ignore_index=True)
        legacy = canonical.with_name("nifty-community-42cd1bbe53235e21.parquet")
        doubled.to_parquet(legacy, index=False)
        canonical.unlink()
        canonical.with_suffix(".manifest.json").unlink(missing_ok=True)
        return legacy

    def test_dryrun_then_apply_then_second_dryrun_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._seed_lake_with_dupes(tmp)

            dry = self._run(tmp, apply=False)
            self.assertEqual(dry["mode"], "dry-run")
            self.assertEqual(dry["totals"]["exact_duplicate_rows"], 2)
            self.assertFalse(dry["affected_partitions"][0]["applied"])
            # Dry-run changed nothing.
            self.assertTrue(next(tmp.rglob("nifty-community-42cd1bbe53235e21.parquet")).exists())

            applied = self._run(tmp, apply=True)
            self.assertEqual(applied["mode"], "apply")
            self.assertEqual(applied["totals"]["exact_duplicate_rows"], 2)
            self.assertEqual(applied["totals"]["legacy_files_quarantined"], 1)
            live = [p for p in tmp.rglob("*.parquet") if "_quarantine" not in p.parts]
            self.assertEqual([p.name for p in live], ["nifty-community.parquet"])
            self.assertEqual(len(read_partitions(live)), 2)
            self.assertTrue(list(tmp.glob("_repair_manifest_*.json")))

            second = self._run(tmp, apply=False)
            self.assertEqual(second["totals"]["exact_duplicate_rows"], 0)
            self.assertEqual(second["totals"]["partitions_affected"], 0)

    def test_rejects_protected_paths(self):
        for bad in (Path.home(), Path(Path.cwd().anchor)):
            with self.assertRaises(SystemExit):
                _resolve_lake_path(bad)

    def test_rejects_directory_without_parquet(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                _resolve_lake_path(tmp)


class DeduplicateCanonicalTests(unittest.TestCase):
    def _frame(self):
        raw = pd.DataFrame(
            {
                "timestamp": ["2026-07-23 09:15:00", "2026-07-23 09:16:00"],
                "open": [100.0, 101.0], "high": [102.0, 103.0],
                "low": [99.0, 100.0], "close": [101.0, 102.0],
                "volume": [1000, 1200],
            }
        )
        return normalize_candles(raw, symbol="X.NS", source="yahoo_recent")

    def test_identical_duplicates_collapse(self):
        frame = self._frame()
        combined = pd.concat([frame, frame], ignore_index=True)
        deduped, exact, conflicts = deduplicate_canonical(combined)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(exact, 2)
        self.assertTrue(conflicts.empty)

    def test_conflicting_rows_surface(self):
        frame = self._frame()
        other = frame.copy()
        other.loc[0, "close"] = 999.0
        combined = pd.concat([frame, other], ignore_index=True)
        deduped, exact, conflicts = deduplicate_canonical(combined)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(len(conflicts), 2, "both rows of the conflicting key kept")


if __name__ == "__main__":
    unittest.main()
