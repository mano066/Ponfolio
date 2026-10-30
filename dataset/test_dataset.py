"""Tests for the dataset layer.

    python -m unittest test_dataset -v

The network tests hit NSE and are skipped unless NSE_LIVE_TESTS=1, so the suite
stays fast and deterministic by default.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import config
import store
from nse_charting import NSECharting

LIVE = os.environ.get("NSE_LIVE_TESTS") == "1"


def _rows(*triples):
    """(epoch_ms, close, volume) -> raw API-shaped rows."""
    return [{"time": ms, "open": c, "high": c, "low": c, "close": c, "volume": v}
            for ms, c, v in triples]


class TestTimestampDecoding(unittest.TestCase):
    """The single most load-bearing behaviour: raw epoch == IST wall clock."""

    def test_daily_bar_lands_on_midnight(self):
        df = NSECharting._to_frame(_rows((1784592000000, 100.0, 5)), "1d")
        self.assertEqual(df["ts"].iloc[0], pd.Timestamp("2026-07-21 00:00:00"))

    def test_intraday_floors_close_time_to_its_own_minute(self):
        # 09:15:59 is the 09:15 bar, not the 09:16 bar.
        df = NSECharting._to_frame(_rows((1782724559000, 1310.2, 283319)), "1m")
        self.assertEqual(df["ts"].iloc[0], pd.Timestamp("2026-06-29 09:15:00"))

    def test_no_timezone_shift_applied(self):
        # A +5:30 shift would put this bar at 14:45, outside NSE hours.
        df = NSECharting._to_frame(_rows((1782724559000, 1.0, 1)), "1m")
        self.assertEqual(df["ts"].iloc[0].hour, 9)

    def test_empty_payload_yields_typed_empty_frame(self):
        df = NSECharting._to_frame([], "1m")
        self.assertTrue(df.empty)
        self.assertEqual(list(df.columns),
                         ["ts", "epoch_ms", "open", "high", "low", "close", "volume"])

    def test_duplicate_minute_keeps_latest(self):
        # 15:30:00 and 15:30:02 both floor to 15:30; the later bar must win.
        df = NSECharting._to_frame(_rows((1782757800000, 10.0, 1),
                                         (1782757802000, 11.0, 2)), "1m")
        self.assertEqual(len(df), 1)
        self.assertEqual(df["close"].iloc[0], 11.0)

    def test_rows_sorted_ascending(self):
        df = NSECharting._to_frame(_rows((1782724619000, 2.0, 1),
                                         (1782724559000, 1.0, 1)), "1m")
        self.assertTrue(df["ts"].is_monotonic_increasing)

    def test_rejects_unknown_interval(self):
        with self.assertRaises(ValueError):
            NSECharting().history("1", "X", "Equity", interval="7m")


class TestStoreMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "T.parquet"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_write_then_idempotent_rewrite(self):
        df = NSECharting._to_frame(_rows((1784592000000, 100.0, 5),
                                         (1784678400000, 101.0, 6)), "1d")
        added, total = store.merge_write(df, self.path)
        self.assertEqual((added, total), (2, 2))
        added, total = store.merge_write(df, self.path)
        self.assertEqual(added, 0, "re-merging identical data must add nothing")
        self.assertEqual(total, 2)

    def test_overlapping_window_appends_only_new_bars(self):
        first = NSECharting._to_frame(_rows((1784592000000, 100.0, 5)), "1d")
        store.merge_write(first, self.path)
        # next run re-sends the old bar plus one new one
        second = NSECharting._to_frame(_rows((1784592000000, 100.0, 5),
                                             (1784678400000, 101.0, 6)), "1d")
        added, total = store.merge_write(second, self.path)
        self.assertEqual((added, total), (1, 2))

    def test_corrected_bar_overwrites_older_copy(self):
        store.merge_write(NSECharting._to_frame(_rows((1784592000000, 100.0, 5)), "1d"),
                          self.path)
        store.merge_write(NSECharting._to_frame(_rows((1784592000000, 999.0, 7)), "1d"),
                          self.path)
        out = store.read(self.path)
        self.assertEqual(len(out), 1)
        self.assertEqual(out["close"].iloc[0], 999.0)

    def test_empty_frame_is_a_noop(self):
        store.merge_write(NSECharting._to_frame(_rows((1784592000000, 100.0, 5)), "1d"),
                          self.path)
        added, total = store.merge_write(NSECharting._to_frame([], "1d"), self.path)
        self.assertEqual((added, total), (0, 1))

    def test_read_of_missing_file_is_empty_not_error(self):
        self.assertTrue(store.read(self.tmp / "nope.parquet").empty)

    def test_stored_order_is_chronological(self):
        store.merge_write(NSECharting._to_frame(_rows((1784678400000, 101.0, 6)), "1d"),
                          self.path)
        store.merge_write(NSECharting._to_frame(_rows((1784592000000, 100.0, 5)), "1d"),
                          self.path)
        self.assertTrue(store.read(self.path)["ts"].is_monotonic_increasing)


class TestIntradayPartitioning(unittest.TestCase):
    def setUp(self):
        self.orig = config.INTRADAY_DIR
        self.tmp = Path(tempfile.mkdtemp())
        config.INTRADAY_DIR = self.tmp

    def tearDown(self):
        config.INTRADAY_DIR = self.orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_frame_spanning_two_months_splits_into_two_files(self):
        df = NSECharting._to_frame(_rows((1782724559000, 1.0, 1),    # 2026-06-29
                                         (1783330559000, 2.0, 1)), "1m")  # 2026-07-06
        res = store.write_intraday("TEST", "1m", df)
        self.assertEqual(res["months"], 2)
        self.assertEqual(res["added"], 2)
        got = sorted(p.stem for p in (self.tmp / "1m" / "TEST").glob("*.parquet"))
        self.assertEqual(got, ["2026-06", "2026-07"])


class TestUniverse(unittest.TestCase):
    def test_constituents_present_and_sane(self):
        csv = config.UNIVERSE_DIR / f"{config.UNIVERSE_NAME}.csv"
        if not csv.exists():
            self.skipTest("run build_universe.py first")
        df = pd.read_csv(csv)
        self.assertIn("Symbol", df.columns)
        self.assertGreater(len(df), 700)
        self.assertFalse(df["Symbol"].duplicated().any())

    def test_tokens_cover_the_universe(self):
        tok_p = config.UNIVERSE_DIR / "tokens.csv"
        csv = config.UNIVERSE_DIR / f"{config.UNIVERSE_NAME}.csv"
        if not (tok_p.exists() and csv.exists()):
            self.skipTest("run build_universe.py first")
        tok = pd.read_csv(tok_p, dtype={"token": str})
        cons = pd.read_csv(csv)
        self.assertFalse(tok["symbol"].duplicated().any())
        self.assertFalse(tok["token"].isna().any())
        self.assertGreaterEqual(len(tok) / len(cons), 0.98)


class TestVendorIngest(unittest.TestCase):
    """The loader has to survive whatever column names a vendor invents."""

    def setUp(self):
        import ingest_vendor
        self.iv = ingest_vendor

    def test_maps_terse_vendor_columns(self):
        m = self.iv.build_column_map(["YMD", "Time", "O", "H", "L", "C", "Vol", "OI"], {})
        self.assertEqual(m["YMD"], "date")
        self.assertEqual(m["O"], "open")
        self.assertEqual(m["Vol"], "volume")
        self.assertNotIn("OI", m)

    def test_maps_verbose_vendor_columns(self):
        m = self.iv.build_column_map(
            ["Ticker", "Date Time", "OpenPrice", "HighPrice", "LowPrice",
             "ClosePrice", "TradedQty"], {})
        self.assertEqual(m["Ticker"], "symbol")
        self.assertEqual(m["Date Time"], "datetime")
        self.assertEqual(m["TradedQty"], "volume")

    def test_explicit_map_overrides_detection(self):
        m = self.iv.build_column_map(["close", "weird"], {"weird": "volume"})
        self.assertEqual(m["weird"], "volume")

    def test_close_labelled_timestamps_shift_back_one_bar(self):
        # 09:16:00 as a bar-close label is the 09:15 bar
        df = pd.DataFrame({"date": ["2012-01-02"], "time": ["09:16:00"]})
        mapping = {"date": "date", "time": "time"}
        ts = self.iv.parse_timestamps(df, mapping, "close")
        self.assertEqual(ts.iloc[0], pd.Timestamp("2012-01-02 09:15:00"))

    def test_open_labelled_timestamps_are_untouched(self):
        df = pd.DataFrame({"date": ["2012-01-02"], "time": ["09:15:00"]})
        ts = self.iv.parse_timestamps(df, {"date": "date", "time": "time"}, "open")
        self.assertEqual(ts.iloc[0], pd.Timestamp("2012-01-02 09:15:00"))

    def test_compact_date_and_time_formats(self):
        df = pd.DataFrame({"date": ["20120102"], "time": ["091500"]})
        ts = self.iv.parse_timestamps(df, {"date": "date", "time": "time"}, "open")
        self.assertEqual(ts.iloc[0], pd.Timestamp("2012-01-02 09:15:00"))

    def test_normalise_produces_store_schema(self):
        df = pd.DataFrame({"date": ["20120102", "20120102"],
                           "time": ["09:15", "09:16"],
                           "o": [10.0, 11.0], "h": [12.0, 12.5],
                           "l": [9.0, 10.5], "c": [11.0, 12.0],
                           "v": [100, 200]})
        mapping = {"date": "date", "time": "time", "o": "open", "h": "high",
                   "l": "low", "c": "close", "v": "volume"}
        out = self.iv.normalise(df, mapping, "open")
        self.assertEqual(list(out.columns),
                         ["ts", "epoch_ms", "open", "high", "low", "close", "volume"])
        self.assertEqual(len(out), 2)
        self.assertEqual(out["ts"].iloc[0], pd.Timestamp("2012-01-02 09:15:00"))

    def test_normalise_rejects_missing_ohlc(self):
        df = pd.DataFrame({"date": ["20120102"], "time": ["09:15"], "o": [1.0]})
        with self.assertRaises(ValueError):
            self.iv.normalise(df, {"date": "date", "time": "time", "o": "open"}, "open")

    def test_normalise_drops_unparseable_rows(self):
        df = pd.DataFrame({"date": ["20120102", "garbage"], "time": ["09:15", "x"],
                           "o": [10.0, 1.0], "h": [12.0, 1.0],
                           "l": [9.0, 1.0], "c": [11.0, 1.0], "v": [100, 1]})
        mapping = {"date": "date", "time": "time", "o": "open", "h": "high",
                   "l": "low", "c": "close", "v": "volume"}
        self.assertEqual(len(self.iv.normalise(df, mapping, "open")), 1)

    def test_symbol_recovered_from_filename_variants(self):
        known = {"reliance": "RELIANCE"}
        for name in ["RELIANCE.csv", "RELIANCE_2012.csv", "RELIANCE-EQ.csv.gz"]:
            self.assertEqual(
                self.iv.symbol_from_filename(Path(name), known), "RELIANCE",
                f"failed on {name}")

    def test_unknown_filename_returns_none(self):
        self.assertIsNone(self.iv.symbol_from_filename(Path("junk123.csv"),
                                                       {"reliance": "RELIANCE"}))


@unittest.skipUnless(LIVE, "set NSE_LIVE_TESTS=1 to hit the network")
class TestLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = NSECharting()

    def test_resolve_picks_exact_symbol_not_first_match(self):
        # searching RELIANCE also returns RELCHEMQ / RELINFRA / RHFL
        hit = self.c.resolve("RELIANCE")
        self.assertIsNotNone(hit)
        self.assertEqual(str(hit["symbol"]).upper(), "RELIANCE-EQ")
        self.assertEqual(str(hit["scripcode"]), "2885")

    def test_daily_reaches_back_to_the_nineties(self):
        df = self.c.history("2885", "RELIANCE-EQ", "Equity", interval="1d")
        self.assertGreater(len(df), 7000)
        self.assertLess(df["ts"].min().year, 2000)

    def test_one_minute_is_a_rolling_window_not_history(self):
        """Documents the wall: 1m cannot reach 2010. If this ever fails,
        NSE widened the window and the backfill story changes."""
        df = self.c.history("2885", "RELIANCE-EQ", "Equity", interval="1m")
        self.assertFalse(df.empty)
        span_days = (df["ts"].max() - df["ts"].min()).days
        self.assertLess(span_days, 60, "1m window unexpectedly wide -- re-probe limits")

    def test_intraday_reconstructs_the_daily_bar(self):
        d1 = self.c.history("2885", "RELIANCE-EQ", "Equity", interval="1d")
        m1 = self.c.history("2885", "RELIANCE-EQ", "Equity", interval="1m")
        m1 = m1[m1["ts"].dt.date < m1["ts"].max().date()]      # skip partial today
        day = m1["ts"].max().date()
        intra = m1[m1["ts"].dt.date == day]
        bar = d1[d1["ts"].dt.date == day].iloc[0]
        self.assertAlmostEqual(intra["open"].iloc[0], bar["open"], delta=0.05)
        self.assertAlmostEqual(intra["high"].max(), bar["high"], delta=0.05)
        self.assertAlmostEqual(intra["low"].min(), bar["low"], delta=0.05)
        self.assertGreater(intra["volume"].sum() / bar["volume"], 0.98)


if __name__ == "__main__":
    unittest.main(verbosity=2)
