"""
Unit tests for the pure dip-threshold backtest layer.

    python -m unittest test_backtest_engine -v

No network, no yfinance — every series is constructed so the expected answer
can be worked out by hand.
"""

import unittest

import backtest_engine as bt


def _flat(n, value=100.0):
    return [value] * n


def _v_shape(pre=300, fall=100, recover=300, top=100.0, bottom=70.0):
    """Rise to a peak, fall to `bottom`, recover past the old peak."""
    down = [top + (bottom - top) * (i + 1) / fall for i in range(fall)]
    up = [bottom + (top * 1.5 - bottom) * (i + 1) / recover for i in range(recover)]
    return _flat(pre, top) + down + up


class TestDrawdownSeries(unittest.TestCase):
    def test_new_high_is_zero_drawdown(self):
        dd = bt.drawdown_series([100, 110, 120])
        self.assertEqual(dd, [0.0, 0.0, 0.0])

    def test_drawdown_is_a_positive_magnitude(self):
        dd = bt.drawdown_series([100, 80])
        self.assertAlmostEqual(dd[1], 20.0)

    def test_peak_is_running_not_full_series(self):
        """
        The lookahead guard. If the peak were max(whole series), the early bars
        would be scored against a high that had not happened yet — a strategy
        that needs to know the future is not a strategy.
        """
        dd = bt.drawdown_series([100, 50, 1000])
        self.assertAlmostEqual(dd[0], 0.0)
        self.assertAlmostEqual(dd[1], 50.0)   # vs 100, NOT vs the later 1000
        self.assertAlmostEqual(dd[2], 0.0)

    def test_recovery_returns_to_zero(self):
        dd = bt.drawdown_series([100, 80, 100, 120])
        self.assertAlmostEqual(dd[-1], 0.0)


class TestFindSignals(unittest.TestCase):
    def test_fires_on_first_bar_past_the_threshold(self):
        dd = [0.0, 4.0, 6.0, 7.0]
        self.assertEqual(bt.find_signals(dd, 5.0), [2])

    def test_one_episode_yields_one_signal(self):
        """
        The de-duplication that keeps the sample honest: a selloff that sits
        below the line for a hundred days is ONE observation, not a hundred.
        """
        dd = [0.0] + [12.0] * 100
        self.assertEqual(len(bt.find_signals(dd, 10.0)), 1)

    def test_rearms_only_after_recovery(self):
        # Dips to 12, recovers to 4 (below 10 * 0.5), dips again -> two signals.
        dd = [0.0, 12.0, 12.0, 4.0, 12.0]
        self.assertEqual(bt.find_signals(dd, 10.0), [1, 4])

    def test_partial_recovery_does_not_rearm(self):
        # Recovers to 6, which is still above the 5.0 re-arm line for T=10.
        dd = [0.0, 12.0, 6.0, 12.0]
        self.assertEqual(bt.find_signals(dd, 10.0), [1])

    def test_deeper_threshold_fires_no_more_often_than_a_shallow_one(self):
        dd = bt.drawdown_series(_v_shape())
        shallow = len(bt.find_signals(dd, 5.0))
        deep = len(bt.find_signals(dd, 25.0))
        self.assertGreaterEqual(shallow, deep)

    def test_non_positive_threshold_yields_nothing(self):
        self.assertEqual(bt.find_signals([0.0, 5.0], 0.0), [])


class TestForwardReturn(unittest.TestCase):
    def test_matches_hand_computation(self):
        self.assertAlmostEqual(bt.forward_return([100, 0, 0, 110], 0, 3), 10.0)

    def test_unfinished_window_is_none_not_zero(self):
        """
        The rule the whole module rests on. A five-year question asked of the
        last day of the series has no answer yet, and zero is not that answer.
        """
        self.assertIsNone(bt.forward_return([100, 110], 0, 5))
        self.assertIsNone(bt.forward_return([100, 110], 1, 1))


class TestMaxDrawdown(unittest.TestCase):
    def test_peak_to_trough_within_window(self):
        self.assertAlmostEqual(bt.max_drawdown([100, 120, 60, 90]), 50.0)

    def test_monotonic_rise_has_no_drawdown(self):
        self.assertAlmostEqual(bt.max_drawdown([100, 110, 120]), 0.0)

    def test_too_short_is_none(self):
        self.assertIsNone(bt.max_drawdown([100]))


class TestHorizonStats(unittest.TestCase):
    def test_incomplete_entries_are_dropped_and_n_reports_the_truth(self):
        closes = _flat(10)
        # Entries 8 and 9 cannot complete a 5-day window.
        stats = bt.horizon_stats(closes, [0, 1, 8, 9], 5)
        self.assertEqual(stats["n"], 2)

    def test_no_completed_observations_yields_none_not_zero(self):
        stats = bt.horizon_stats(_flat(10), [9], 5)
        self.assertEqual(stats["n"], 0)
        self.assertIsNone(stats["mean_pct"])
        self.assertIsNone(stats["positive_rate_pct"])
        self.assertIsNone(stats["worst_pct"])

    def test_positive_rate_counts_strictly_positive_returns(self):
        # Flat market: no return is > 0, so the positive rate is 0, not 100.
        stats = bt.horizon_stats(_flat(300), [0, 1, 2], 63)
        self.assertEqual(stats["positive_rate_pct"], 0.0)

    def test_cagr_only_reported_from_a_year_out(self):
        closes = [100.0 * (1.0 + i / 1000.0) for i in range(1400)]
        self.assertIsNone(bt.horizon_stats(closes, [0], 63)["mean_cagr_pct"])
        self.assertIsNotNone(bt.horizon_stats(closes, [0], 252)["mean_cagr_pct"])

    def test_worst_drawdown_can_be_switched_off(self):
        closes = _v_shape()
        self.assertIsNone(
            bt.horizon_stats(closes, [0], 252, with_drawdown=False)["worst_drawdown_pct"])
        self.assertIsNotNone(
            bt.horizon_stats(closes, [0], 252, with_drawdown=True)["worst_drawdown_pct"])


class TestBaselineAndEdge(unittest.TestCase):
    def test_baseline_covers_every_day(self):
        closes = _v_shape()
        base = bt.baseline_profile(closes)
        self.assertEqual(base["3m"]["n"], len(closes) - bt.HORIZON_DAYS["3m"])

    def test_edge_is_signal_minus_baseline(self):
        closes = _v_shape()
        dd = bt.drawdown_series(closes)
        base = bt.baseline_profile(closes)
        study = bt.study_threshold(closes, dd, 10.0, base)
        for h in bt.HORIZONS:
            s = study["forward"][h]["mean_pct"]
            b = base[h]["mean_pct"]
            e = study["edge"][h]["mean_pp"]
            if s is None or b is None:
                self.assertIsNone(e)
            else:
                self.assertAlmostEqual(e, round(s - b, 2))

    def test_edge_is_none_when_either_side_is_unknown(self):
        # A signal with no completed window cannot have a measurable edge.
        closes = _flat(600)
        base = bt.baseline_profile(closes)
        study = bt.study_threshold(closes, bt.drawdown_series(closes), 10.0, base)
        self.assertIsNone(study["edge"]["5y"]["mean_pp"])


class TestReliability(unittest.TestCase):
    def test_few_episodes_are_flagged_unreliable(self):
        closes = _v_shape()
        dd = bt.drawdown_series(closes)
        base = bt.baseline_profile(closes)
        study = bt.study_threshold(closes, dd, 25.0, base)
        self.assertLess(study["signals"], bt.MIN_SIGNALS_FOR_RELIABLE)
        self.assertFalse(study["reliable"])

    def test_unreliable_studies_cannot_be_selected_as_best(self):
        """
        The overfitting guard that matters most in practice: a -30% threshold
        that fired once and happened to catch the bottom will post a
        spectacular edge. It must never be chosen on the strength of that.
        """
        closes = _v_shape()
        dd = bt.drawdown_series(closes)
        base = bt.baseline_profile(closes)
        lonely = bt.study_threshold(closes, dd, 25.0, base)
        self.assertIsNone(bt._score_threshold(lonely))


class TestBacktestBenchmark(unittest.TestCase):
    def test_thin_history_is_refused_rather_than_studied(self):
        r = bt.backtest_benchmark("^X", "X", _flat(100))
        self.assertEqual(r["status"], bt.STATUS_INSUFFICIENT_HISTORY)
        self.assertIsNone(r["best_threshold_pct"])
        self.assertEqual(r["thresholds"], [])
        self.assertTrue(r["note"])

    def test_dirty_values_are_dropped_not_fatal(self):
        closes = _v_shape()
        closes[10] = float("nan")
        closes[20] = -5.0
        closes[30] = "oops"
        r = bt.backtest_benchmark("^X", "X", closes)
        self.assertEqual(r["status"], bt.STATUS_OK)
        self.assertEqual(r["points"], len(closes) - 3)

    def test_report_shape_is_stable_across_both_statuses(self):
        ok = bt.backtest_benchmark("^X", "X", _v_shape())
        thin = bt.backtest_benchmark("^X", "X", _flat(50))
        self.assertEqual(set(ok) - {"active_threshold_pct"}, set(thin))

    def test_active_threshold_is_the_deepest_one_reached_today(self):
        # Ends 30% below its running peak, easing down over ten sessions so the
        # fall reads as a market move rather than as a split.
        closes = _flat(600, 100.0) + [100.0 - 3.0 * i for i in range(1, 11)]
        r = bt.backtest_benchmark("^X", "X", closes)
        self.assertAlmostEqual(r["current_drawdown_pct"], 30.0)
        self.assertEqual(r["active_threshold_pct"], 30.0)
        self.assertFalse(r["history"]["trimmed"])

    def test_no_active_threshold_at_a_high(self):
        r = bt.backtest_benchmark("^X", "X", [100.0 + i for i in range(600)])
        self.assertEqual(r["current_drawdown_pct"], 0.0)
        self.assertIsNone(r["active_threshold_pct"])

    def test_every_default_threshold_is_reported_even_with_no_signals(self):
        # A rising series never dips; all five rows must still be present, each
        # honestly showing zero signals rather than being silently omitted.
        r = bt.backtest_benchmark("^X", "X", [100.0 + i for i in range(600)])
        self.assertEqual(len(r["thresholds"]), len(bt.DEFAULT_THRESHOLDS))
        self.assertTrue(all(t["signals"] == 0 for t in r["thresholds"]))


class TestWalkForward(unittest.TestCase):
    def test_short_series_reports_insufficient_history(self):
        closes = _flat(600)
        wf = bt.walk_forward(closes, bt.drawdown_series(closes),
                             bt.DEFAULT_THRESHOLDS)
        self.assertEqual(wf["status"], bt.STATUS_INSUFFICIENT_HISTORY)
        self.assertIsNone(wf["selected_threshold_pct"])

    def test_selection_uses_only_the_training_half(self):
        """
        The out-of-sample contract: the split index must fall inside the
        series, and every scored signal must come from after it.
        """
        closes = _v_shape(pre=800, fall=200, recover=1600)
        dd = bt.drawdown_series(closes)
        wf = bt.walk_forward(closes, dd, bt.DEFAULT_THRESHOLDS)
        self.assertEqual(wf["status"], bt.STATUS_OK)
        if wf["selected_threshold_pct"] is not None:
            cut = wf["split_index"]
            self.assertGreater(cut, 0)
            self.assertLess(cut, len(closes))
            picked = [i for i in bt.find_signals(dd, wf["selected_threshold_pct"])
                      if i >= cut]
            self.assertEqual(wf["out_of_sample"]["signals"], len(picked))

    def test_no_qualifying_threshold_says_so_rather_than_picking_a_fluke(self):
        # A series that never dips gives the trainer nothing reliable to pick.
        closes = [100.0 + i for i in range(3000)]
        wf = bt.walk_forward(closes, bt.drawdown_series(closes),
                             bt.DEFAULT_THRESHOLDS)
        self.assertIsNone(wf["selected_threshold_pct"])
        self.assertTrue(wf["note"])


class TestCorporateActionTrimming(unittest.TestCase):
    """
    GOLDBEES.NS prints +9,900% on 2019-12-23 — a unit split. Left in the
    series it gave this engine a one-year mean forward return of 6,463% at the
    -15% threshold. A forward return spanning a split is not a return.
    """

    def test_split_is_detected_and_history_truncated_to_the_clean_tail(self):
        closes = _flat(300, 0.34) + _flat(700, 34.0)     # 1:100 style step
        r = bt.backtest_benchmark("^GOLD", "Gold", closes)
        self.assertTrue(r["history"]["trimmed"])
        self.assertEqual(r["history"]["dropped"], 300)
        self.assertEqual(r["points"], 700)

    def test_statistics_after_trimming_are_sane(self):
        closes = _flat(300, 0.34) + _v_shape(pre=300, fall=100, recover=600)
        r = bt.backtest_benchmark("^GOLD", "Gold", closes)
        for row in r["thresholds"]:
            mean = row["forward"]["1y"]["mean_pct"]
            if mean is not None:
                self.assertLess(abs(mean), 500.0)

    def test_clean_series_is_not_trimmed(self):
        r = bt.backtest_benchmark("^X", "X", _v_shape())
        self.assertFalse(r["history"]["trimmed"])
        self.assertEqual(r["history"]["dropped"], 0)

    def test_only_the_last_discontinuity_matters(self):
        # Two splits: everything before the SECOND one must go.
        closes = _flat(200, 1.0) + _flat(200, 50.0) + _flat(600, 2000.0)
        r = bt.backtest_benchmark("^X", "X", closes)
        self.assertEqual(r["history"]["dropped"], 400)
        self.assertEqual(len(r["history"]["events"]), 2)

    def test_trimmed_series_too_short_reports_insufficient_history(self):
        closes = _flat(600, 1.0) + _flat(50, 100.0)
        r = bt.backtest_benchmark("^X", "X", closes)
        self.assertEqual(r["status"], bt.STATUS_INSUFFICIENT_HISTORY)
        self.assertTrue(r["history"]["trimmed"])


if __name__ == "__main__":
    unittest.main()
