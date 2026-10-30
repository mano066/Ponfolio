"""
Tests for the yfinance cache-heal path in _safe_yf_history.

    python -m unittest test_yf_cache_heal -v

The bug these pin: on 28 Oct 2026 yfinance's SQLite cache started failing with
"database disk image is malformed". _safe_yf_history slept 5+15+30s per symbol
on every attempt, the sleeps held all of the server's worker threads, and the
login screen sat on "Connecting to server..." because even /api/status could
not be answered.
"""

import inspect
import time
import unittest
from unittest import mock

import pandas as pd
import peewee

import main

MALFORMED = "database disk image is malformed"


class _Ticker:
    """Stand-in for yf.Ticker whose history() follows a scripted list."""
    script: list = []

    def __init__(self, symbol):
        pass

    def history(self, period):
        step = _Ticker.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class TestCacheHeal(unittest.TestCase):
    def setUp(self):
        main._yf_history_cache.clear()
        self.heal = mock.patch.object(main, "_heal_yf_cache").start()
        self.sleep = mock.patch.object(main._time, "sleep").start()
        mock.patch.object(main.yf, "Ticker", _Ticker).start()
        self.addCleanup(mock.patch.stopall)

    def test_db_error_heals_and_retries_without_sleeping(self):
        _Ticker.script = [peewee.DatabaseError(MALFORMED), pd.DataFrame({"Close": [1.0]})]
        df = main._safe_yf_history("HEAL1.NS", "5d")
        self.assertEqual(len(df), 1)
        self.heal.assert_called_once()
        self.sleep.assert_not_called()

    def test_db_error_that_persists_gives_up_without_sleeping(self):
        _Ticker.script = [peewee.DatabaseError(MALFORMED)] * 3
        df = main._safe_yf_history("HEAL2.NS", "5d")
        self.assertTrue(df.empty)
        self.sleep.assert_not_called()
        self.assertEqual(len(_Ticker.script), 1)  # two tries, not three

    def test_sqlite3_errors_count_too(self):
        import sqlite3
        self.assertTrue(main._is_yf_cache_db_error(sqlite3.DatabaseError(MALFORMED)))
        self.assertTrue(main._is_yf_cache_db_error(peewee.OperationalError("database is locked")))

    def test_network_errors_keep_the_backoff(self):
        # Rate limits and dropped connections do recover with time.
        self.assertFalse(main._is_yf_cache_db_error(ConnectionError("reset")))
        _Ticker.script = [ConnectionError("reset"), pd.DataFrame({"Close": [1.0]})]
        main._safe_yf_history("HEAL3.NS", "5d")
        self.sleep.assert_called_once_with(5)
        self.heal.assert_not_called()


class TestStatusEndpoint(unittest.TestCase):
    def test_status_is_async(self):
        # A sync handler shares the threadpool with the slow price fetches;
        # async keeps the login screen's readiness check answerable.
        self.assertTrue(inspect.iscoroutinefunction(main.read_root))


if __name__ == "__main__":
    unittest.main()
