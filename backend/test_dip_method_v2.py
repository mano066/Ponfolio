"""
Tests for the v2 dip method: ETFs, board order, and where fund evidence is read.

    python -m unittest test_dip_method_v2 -v

Pure computation only — no network.
"""

import unittest

import market_indices as mi
import mf_dip
import stock_dip


def _study(rows):
    """A backtest study in backtest_engine's shape: (depth, signals, reliable, edge)."""
    return {"status": "ok", "years": 9.8, "thresholds": [
        {"threshold_pct": d, "signals": n, "reliable": r,
         "edge": {"1y": {"mean_pp": e}}} for d, n, r, e in rows]}


NIFTY = _study([(5.0, 20, True, -2.28), (10.0, 9, True, 0.14),
                (15.0, 4, False, 11.09), (20.0, 1, False, 40.37)])


class FundEvidenceDepthTestCase(unittest.TestCase):
    """The backtest measures the BENCHMARK, so it is read at the benchmark's depth."""

    def test_the_deepest_reliable_crossed_threshold_is_used(self):
        ev = mf_dip.backtest_evidence_depth(NIFTY, 13.8)
        self.assertEqual(ev["depth_pct"], 10.0)
        self.assertEqual(ev["edge_pp"], 0.14)

    def test_an_unreliable_deeper_threshold_is_skipped_not_fatal(self):
        # 15% has only 4 episodes; 10% still has evidence.
        self.assertEqual(mf_dip.backtest_evidence_depth(NIFTY, 16.0)["depth_pct"], 10.0)

    def test_no_threshold_crossed_means_no_evidence(self):
        self.assertIsNone(mf_dip.backtest_evidence_depth(NIFTY, 3.0))

    def test_a_fund_barely_down_still_gets_its_benchmarks_evidence(self):
        # The live case: NAV 5.7% off its peak, Nifty 13.8% off. The factor
        # used to be None because no NAV zone had been reached.
        fund = {"scheme_name": "HDFC Balanced Advantage", "nav": 551.0,
                "transactions": []}
        row = mf_dip.analyse_fund(fund, peak_nav=584.2, benchmark="^NSEI",
                                  benchmark_label="NIFTY 50",
                                  benchmark_drawdown_pct=13.8, study=NIFTY)
        self.assertIsNotNone(row["factors"][mf_dip.FACTOR_BACKTEST])
        self.assertEqual(row["backtest_evidence"]["depth_pct"], 10.0)
        self.assertTrue(any("History" in r for r in row["reasons"]))

    def test_a_negative_edge_scores_zero_not_none(self):
        self.assertEqual(mf_dip.score_backtest_support(
            study=NIFTY, benchmark_drawdown_pct=7.0), 0.0)

    def test_deeper_contrary_episodes_halve_the_support(self):
        gold = _study([(5.0, 14, True, 8.66), (10.0, 4, False, -20.5),
                       (15.0, 3, False, -21.59), (20.0, 2, False, -8.4)])
        ev = mf_dip.backtest_evidence_depth(gold, 17.5)
        self.assertEqual(ev["depth_pct"], 5.0)
        self.assertEqual(ev["contradicted_by"]["depth_pct"], 15.0)
        self.assertEqual(mf_dip.score_backtest_support(
            study=gold, benchmark_drawdown_pct=17.5), 50.0)

    def test_one_or_two_contrary_episodes_do_not_count(self):
        study = _study([(5.0, 14, True, 8.66), (10.0, 2, False, -20.5)])
        ev = mf_dip.backtest_evidence_depth(study, 12.0)
        self.assertIsNone(ev["contradicted_by"])

    def test_the_zone_only_call_still_works(self):
        self.assertIsNone(mf_dip.score_backtest_support([]))


class EtfTestCase(unittest.TestCase):
    def test_known_etfs_map_to_the_index_they_track(self):
        self.assertEqual(mi.etf_benchmark("ITIETF.BO")[0], "^CNXIT")
        self.assertEqual(mi.etf_benchmark("HEALTHIETF.NS")[0], "^CNXPHARMA")
        proxied = next(iter(mi.ETF_PROXY))
        self.assertIn("proxy", mi.etf_benchmark(f"{proxied}.NS")[1])
        self.assertIsNone(mi.etf_benchmark("HDFCBANK.NS"))

    def _etf(self, **kw):
        args = dict(benchmark_drawdown_pct=13.8, study=NIFTY,
                    price_integrity={"points": 250})
        args.update(kw)
        holding = {"symbol": "NIFTYBEES.NS", "name": "NIFTYBEES", "price": 250.0,
                   "drawdown_pct": 13.5, "benchmark": "^NSEI",
                   "benchmark_label": "NIFTY 50"}
        return stock_dip.analyse_etf(holding, **args)

    def test_an_etf_is_scored_without_fundamentals(self):
        row = self._etf()
        self.assertEqual(row["instrument"], "etf")
        self.assertIsNotNone(row["score"])
        self.assertFalse(row["low_confidence"])
        self.assertEqual(row["reason_for_fall"]["reason"], stock_dip.REASON_MARKET_WIDE)

    def test_a_thin_own_series_falls_back_to_the_index(self):
        # A .BO series that served one bar: its "drawdown" was not a measurement.
        row = self._etf(price_integrity={"points": 1})
        self.assertEqual(row["drawdown_pct"], 13.8)

    def test_an_etf_near_its_high_is_not_a_dip_buy(self):
        row = self._etf(benchmark_drawdown_pct=2.0)
        holding_dd = row["drawdown_pct"]
        self.assertEqual(holding_dd, 13.5)  # own series is real, so it is used
        row = self._etf(benchmark_drawdown_pct=2.0,
                        price_integrity={"points": 3})
        self.assertEqual(row["action"], stock_dip.ACTION_WATCH)
        self.assertEqual(row["reason_for_fall"]["reason"], stock_dip.REASON_NOT_FALLING)

    def test_a_shallow_etf_dip_is_watch_not_avoid(self):
        # An ETF 7.2% down once scored 6 and read "avoid averaging" — wording
        # for a company with a problem, not for an index that has barely moved.
        row = self._etf(benchmark_drawdown_pct=7.2, study=None,
                        price_integrity={"points": 3})
        self.assertEqual(row["action"], stock_dip.ACTION_WATCH)

    def test_history_against_the_depth_still_says_avoid(self):
        against = _study([(5.0, 25, True, -8.0), (10.0, 7, True, -6.4)])
        row = self._etf(benchmark_drawdown_pct=12.0, study=against,
                        price_integrity={"points": 3})
        self.assertEqual(row["action"], stock_dip.ACTION_AVOID)

    def test_no_study_still_scores_on_drawdown(self):
        row = self._etf(study=None)
        self.assertIsNone(row["factors"][stock_dip.FACTOR_BACKTEST])
        self.assertEqual(row["confidence"], 60.0)


class BoardOrderTestCase(unittest.TestCase):
    def test_stocks_sort_by_action_then_score(self):
        rows = [
            {"symbol": "A", "action": "watch", "score": 79.8, "confidence": 90},
            {"symbol": "B", "action": "consider", "score": 78.6, "confidence": 90},
            {"symbol": "C", "action": "do_not_average", "score": 90, "confidence": 90},
            {"symbol": "D", "action": "watch", "score": None, "confidence": 0},
            {"symbol": "E", "action": "accumulate", "score": 81, "confidence": 70},
        ]
        rows.sort(key=stock_dip.board_sort_key)
        self.assertEqual([r["symbol"] for r in rows], ["E", "B", "A", "D", "C"])

    def test_low_confidence_rows_sink(self):
        rows = [
            {"scheme_name": "unmeasured", "action": "watch", "score": 27,
             "low_confidence": True},
            {"scheme_name": "measured", "action": "wait", "score": 43,
             "low_confidence": False},
        ]
        rows.sort(key=mf_dip.board_sort_key)
        self.assertEqual(rows[0]["scheme_name"], "measured")

    def test_funds_sort_by_action_then_score(self):
        rows = [
            {"scheme_name": "deep", "action": "watch", "score": 57},
            {"scheme_name": "best", "action": "add", "score": 80},
            {"scheme_name": "ok", "action": "attractive", "score": 70},
        ]
        rows.sort(key=mf_dip.board_sort_key)
        self.assertEqual([r["scheme_name"] for r in rows], ["best", "ok", "deep"])


class AverageCostIsNotAReasonTestCase(unittest.TestCase):
    """Your average cost says nothing about whether a fund is a buy today."""

    def _fund(self, avg_nav):
        fund = {"scheme_name": "Some Flexi Cap", "nav": 100.0, "transactions": [
            {"type": "buy", "units": 10, "nav": avg_nav, "date": "2025-01-01",
             "amount": 10 * avg_nav}]}
        return mf_dip.analyse_fund(fund, peak_nav=110.0, benchmark="^NSEI",
                                   benchmark_label="NIFTY 50",
                                   benchmark_drawdown_pct=12.0, study=NIFTY)

    def test_the_score_ignores_the_average(self):
        self.assertEqual(self._fund(80.0)["score"], self._fund(140.0)["score"])

    def test_no_reason_mentions_the_average(self):
        reasons = " ".join(self._fund(140.0)["reasons"]).lower()
        self.assertNotIn("your average", reasons)


if __name__ == "__main__":
    unittest.main()
