"""A "day change" must be a session change.

Yahoo serves several NSE sector indices sparsely: a one-month request for
^CNXFMCG, ^CNXMETAL, ^CNXAUTO, ^CNXSERVICE and NIFTY_FIN_SERVICE.NS returned a
SINGLE bar while ^NSEI, ^CNXIT and ^CNXPHARMA returned 23. Spliced onto the
cached decade, the newest bar's neighbour was weeks old, so the tape printed a
multi-week move as today's: FMCG at -6.88% on a day the Nifty moved -0.34%,
and METAL's "day" gain (+7.98%) larger than its own one-week gain (+6.57%).

The tell is arithmetic: a single session's move cannot exceed the week that
contains it. These tests pin the rule that produced the fix.
"""
import unittest
from datetime import date, timedelta

import market_indices as M

META = {"symbol": "^TEST", "label": "TEST", "group": "sector"}


def series(pairs):
    """pairs: [(date, close), ...] -> (closes, dates)."""
    return [c for _, c in pairs], [d for d, _ in pairs]


class SessionGapTests(unittest.TestCase):
    def test_consecutive_sessions_give_a_day_change(self):
        closes, dates = series([
            (date(2026, 9, 7), 100.0),
            (date(2026, 9, 8), 101.0),
            (date(2026, 9, 9), 102.0),
        ])
        row = M.summarize_index(META, closes, dates=dates)
        self.assertAlmostEqual(row["day_chg_pct"], 0.99, places=2)
        self.assertEqual(row["day_chg_span_days"], 1)

    def test_friday_to_monday_is_still_one_session(self):
        closes, dates = series([
            (date(2026, 9, 4), 100.0),   # Friday
            (date(2026, 9, 7), 99.0),    # Monday
        ])
        row = M.summarize_index(META, closes, dates=dates)
        self.assertEqual(row["day_chg_span_days"], 3)
        self.assertAlmostEqual(row["day_chg_pct"], -1.0, places=2)

    def test_a_long_weekend_still_counts(self):
        closes, dates = series([
            (date(2026, 9, 3), 100.0),
            (date(2026, 9, 7), 101.0),   # 4 days: holiday Friday
        ])
        row = M.summarize_index(META, closes, dates=dates)
        self.assertEqual(row["day_chg_span_days"], 4)
        self.assertIsNotNone(row["day_chg_pct"])

    def test_the_real_fmcg_shape_reports_no_day_change(self):
        # The exact failure: today's bar, and nothing adjacent behind it.
        closes, dates = series([
            (date(2026, 8, 1), 48748.70),
            (date(2026, 9, 9), 45397.05),
        ])
        row = M.summarize_index(META, closes, dates=dates)
        self.assertIsNone(row["day_chg_pct"])
        self.assertIsNone(row["day_chg"])
        self.assertEqual(row["day_chg_span_days"], 39)
        # The level and the stale reference are still reported, so the UI can
        # explain the gap instead of hiding it.
        self.assertEqual(row["last"], 45397.05)
        self.assertEqual(row["prev_close"], 48748.70)
        self.assertEqual(row["prev_bar_date"], "2026-08-01")
        self.assertEqual(row["last_bar_date"], "2026-09-09")

    def test_a_five_day_gap_is_already_too_wide(self):
        closes, dates = series([
            (date(2026, 9, 2), 100.0),
            (date(2026, 9, 7), 90.0),
        ])
        row = M.summarize_index(META, closes, dates=dates)
        self.assertIsNone(row["day_chg_pct"])
        self.assertEqual(row["day_chg_span_days"], 5)

    def test_without_dates_the_old_positional_behaviour_stands(self):
        # Callers that supply no dates cannot be judged, and degrading them to
        # "no day change" would blank the backtest's own path.
        row = M.summarize_index(META, [100.0, 99.0])
        self.assertAlmostEqual(row["day_chg_pct"], -1.0, places=2)
        self.assertIsNone(row["day_chg_span_days"])

    def test_trailing_returns_survive_a_sparse_series(self):
        # Only the day change is withheld; the long-horizon columns still
        # describe their own stated spans.
        pairs = [(date(2026, 1, 1) + timedelta(days=7 * i), 100.0 + i)
                 for i in range(40)]
        closes, dates = series(pairs)
        row = M.summarize_index(META, closes, dates=dates)
        self.assertIsNone(row["day_chg_pct"])
        self.assertIsNotNone(row["off_high_pct"])
        self.assertIsNotNone(row["above_low_pct"])

    def test_a_single_bar_has_neither_change_nor_span(self):
        row = M.summarize_index(META, [100.0], dates=[date(2026, 9, 9)])
        self.assertIsNone(row["day_chg_pct"])
        self.assertIsNone(row["day_chg_span_days"])
        self.assertEqual(row["last"], 100.0)

    def test_the_gap_helper_reads_dates_strings_and_datetimes(self):
        self.assertEqual(
            M._calendar_gap(date(2026, 9, 1), date(2026, 9, 9)), 8)
        self.assertEqual(M._calendar_gap("2026-09-01", "2026-09-09"), 8)
        self.assertEqual(
            M._calendar_gap("2026-09-01T00:00:00", "2026-09-03"), 2)
        self.assertIsNone(M._calendar_gap("not a date", date(2026, 9, 9)))
        self.assertIsNone(M._calendar_gap(None, date(2026, 9, 9)))


class BreadthTests(unittest.TestCase):
    """Breadth must not count an un-comparable index as unchanged."""

    def rows(self):
        # build_tape returns rows in INDEX_UNIVERSE order and drops anything
        # not in it, so the fixture uses real symbols: two densely served, one
        # sparse — which is exactly the shape the live feed produces.
        dense_closes, dense_dates = series([
            (date(2026, 9, 8), 100.0), (date(2026, 9, 9), 101.0)])
        down_closes, down_dates = series([
            (date(2026, 9, 8), 100.0), (date(2026, 9, 9), 99.0)])
        sparse_closes, sparse_dates = series([
            (date(2026, 8, 1), 100.0), (date(2026, 9, 9), 90.0)])
        return [
            M.summarize_index(
                {"symbol": "^NSEI", "label": "NIFTY 50", "group": "broad"},
                dense_closes, dates=dense_dates),
            M.summarize_index(
                {"symbol": "^CNXIT", "label": "IT", "group": "sector"},
                down_closes, dates=down_dates),
            M.summarize_index(
                {"symbol": "^CNXFMCG", "label": "FMCG", "group": "sector"},
                sparse_closes, dates=sparse_dates),
        ]

    def test_only_comparable_indices_are_counted(self):
        breadth = M.build_tape(self.rows())["breadth"]
        self.assertEqual(breadth["up"], 1)
        self.assertEqual(breadth["down"], 1)
        self.assertEqual(breadth["comparable"], 2)
        self.assertEqual(breadth["no_prior_session"], 1)
        # The sparse index is not silently flat.
        self.assertEqual(breadth["flat"], 0)

    def test_the_sparse_index_is_still_available_on_the_tape(self):
        breadth = M.build_tape(self.rows())["breadth"]
        self.assertEqual(breadth["available"], 3)



class SpanChangeTests(unittest.TestCase):
    """A frozen-history index still has a real move — over a stated period."""

    def test_the_span_change_survives_when_the_day_change_cannot(self):
        closes, dates = series([
            (date(2026, 7, 17), 48748.70),
            (date(2026, 9, 9), 45397.05),
        ])
        row = M.summarize_index(META, closes, dates=dates)
        self.assertIsNone(row["day_chg_pct"])
        self.assertAlmostEqual(row["span_chg_pct"], -6.88, places=2)
        self.assertEqual(row["day_chg_span_days"], 54)
        self.assertTrue(row["stale_history"])

    def test_on_adjacent_bars_the_two_figures_agree(self):
        closes, dates = series([
            (date(2026, 9, 8), 100.0), (date(2026, 9, 9), 101.0)])
        row = M.summarize_index(META, closes, dates=dates)
        self.assertEqual(row["day_chg_pct"], row["span_chg_pct"])
        self.assertFalse(row["stale_history"])

    def test_a_single_bar_has_no_span_change_either(self):
        row = M.summarize_index(META, [100.0], dates=[date(2026, 9, 9)])
        self.assertIsNone(row["span_chg_pct"])
        self.assertIsNone(row["day_chg_pct"])

    def test_the_span_change_is_signed_the_same_way_as_the_move(self):
        up_closes, up_dates = series([
            (date(2026, 7, 17), 100.0), (date(2026, 9, 9), 108.0)])
        row = M.summarize_index(META, up_closes, dates=up_dates)
        self.assertGreater(row["span_chg_pct"], 0)
        self.assertEqual(row["span_chg"], 8.0)

if __name__ == "__main__":
    unittest.main()
