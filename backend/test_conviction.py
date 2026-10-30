"""
Tests for conviction & position-size discipline.

    python -m unittest test_conviction -v

Two halves: the pure rules in conviction.py, and the endpoint wiring in main
with fundamentals, prices and persistence stubbed so nothing touches the
network or the user's files.
"""

import unittest
from datetime import date
from unittest import mock

import conviction as cv

S = cv.merge_settings(None)
TODAY = date(2026, 10, 7)

GOOD = {"earnings_growth_pct": 20.0, "revenue_growth_pct": 15.0, "roe_pct": 22.0,
        "operating_margin_pct": 25.0, "free_cashflow": 5e9,
        "debt_to_equity": 30.0, "current_ratio": 1.8, "pe": 20.0}
WEAK = {"earnings_growth_pct": -12.0, "revenue_growth_pct": -4.0, "roe_pct": 6.0,
        "operating_margin_pct": 3.0, "free_cashflow": -1e9,
        "debt_to_equity": 280.0, "current_ratio": 0.8, "pe": 60.0}

THESIS = {"what_it_does": "Sells cigarettes and FMCG goods across India.",
          "growth_reason": "FMCG margins expanding, hotel demerger unlocks value.",
          "expected_eps_growth_pct": 10, "expected_sales_growth_pct": 8,
          "sell_triggers": [{"text": "Sales shrink", "metric": "revenue_growth_pct",
                             "op": "<", "value": 0}]}


class HealthTestCase(unittest.TestCase):
    def test_a_good_business_scores_strong(self):
        h = cv.business_health(GOOD)
        self.assertGreaterEqual(h["score"], 75)
        self.assertEqual(h["grade"], cv.GRADE_STRONG)
        self.assertEqual(h["coverage"], 100.0)

    def test_a_weak_business_scores_poor(self):
        self.assertEqual(cv.business_health(WEAK)["grade"], cv.GRADE_POOR)

    def test_missing_data_is_unknown_not_zero(self):
        h = cv.business_health({"roe_pct": 22.0})
        self.assertGreater(h["score"], 90)       # only quality is known, and it is good
        self.assertTrue(h["low_coverage"])
        eps = next(c for c in h["checks"] if c["key"] == "eps_growth")
        self.assertEqual(eps["status"], cv.STATUS_UNKNOWN)

    def test_nothing_known_means_no_score(self):
        h = cv.business_health({})
        self.assertIsNone(h["score"])
        self.assertEqual(h["grade"], cv.GRADE_UNKNOWN)

    def test_banks_are_not_scored_on_leverage(self):
        h = cv.business_health({**GOOD, "debt_to_equity": 900.0}, financial=True)
        keys = {c["key"] for c in h["checks"]}
        self.assertNotIn("debt_to_equity", keys)
        self.assertNotIn("current_ratio", keys)
        self.assertEqual(h["coverage"], 100.0)

    def test_financial_detection(self):
        self.assertTrue(cv.is_financial("Financial Services", "Banks - Regional"))
        self.assertFalse(cv.is_financial("Technology", "IT Services"))

    def test_peg_needs_positive_growth(self):
        self.assertEqual(cv.peg_ratio(30, 20), 1.5)
        self.assertIsNone(cv.peg_ratio(30, -5))

    def test_the_price_and_average_cost_play_no_part(self):
        a = cv.business_health(GOOD)["score"]
        b = cv.business_health({**GOOD, "price": 1, "avg_cost": 9999,
                                "drawdown_pct": 60})["score"]
        self.assertEqual(a, b)


class SizeTestCase(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(cv.position_band(0.5, S), cv.SIZE_EXIT_OR_GROW)
        self.assertEqual(cv.position_band(1.5, S), cv.SIZE_BELOW_MIN)
        self.assertEqual(cv.position_band(5, S), cv.SIZE_OK)
        self.assertEqual(cv.position_band(12, S), cv.SIZE_OVER_MAX)
        self.assertEqual(cv.position_band(None, S), cv.SIZE_UNKNOWN)

    def test_weights_merge_exchanges_and_skip_unpriced(self):
        w, total = cv.weights_by_symbol([
            {"symbol": "ITC.NS", "total_value": 300},
            {"symbol": "ITC.BO", "total_value": 100},
            {"symbol": "TCS.NS", "total_value": 600},
            {"symbol": "X.NS", "total_value": None},
        ])
        self.assertEqual(total, 1000)
        self.assertEqual(w, {"ITC": 40.0, "TCS": 60.0})

    def test_settings_ignore_garbage(self):
        s = cv.merge_settings({"max_position_pct": "abc", "min_position_pct": 3,
                               "watch_min_days": -5})
        self.assertEqual(s["max_position_pct"], 10.0)
        self.assertEqual(s["min_position_pct"], 3.0)
        self.assertEqual(s["watch_min_days"], 45)


class ThesisTestCase(unittest.TestCase):
    def test_clean_keeps_the_answers_and_triggers(self):
        t = cv.clean_thesis(THESIS, TODAY)
        self.assertEqual(t["sell_triggers"][0]["metric"], "revenue_growth_pct")
        self.assertEqual(t["written_at"], "2026-10-07")
        self.assertEqual(cv.thesis_status(t, S, TODAY), cv.THESIS_OK)

    def test_text_only_triggers_are_kept(self):
        t = cv.clean_thesis({**THESIS, "sell_triggers": ["Promoter sells stake"]}, TODAY)
        self.assertEqual(t["sell_triggers"][0], {"text": "Promoter sells stake",
                                                 "metric": None, "op": None, "value": None})

    def test_bad_triggers_are_refused(self):
        with self.assertRaises(ValueError):
            cv.clean_thesis({**THESIS, "sell_triggers": [
                {"text": "x", "metric": "share_price", "op": "<", "value": 1}]})
        with self.assertRaises(ValueError):
            cv.clean_thesis({**THESIS, "sell_triggers": [
                {"text": "x", "metric": "roe_pct", "op": "!=", "value": 1}]})

    def test_states(self):
        self.assertEqual(cv.thesis_status(None, S, TODAY), cv.THESIS_MISSING)
        self.assertEqual(cv.thesis_status({"what_it_does": "x"}, S, TODAY),
                         cv.THESIS_INCOMPLETE)
        old = cv.clean_thesis(THESIS, date(2025, 9, 1))
        self.assertEqual(cv.thesis_status(old, S, TODAY), cv.THESIS_STALE)

    def test_fired_triggers(self):
        t = cv.clean_thesis(THESIS, TODAY)
        self.assertEqual(cv.fired_triggers(t, GOOD), [])
        fired = cv.fired_triggers(t, {"revenue_growth_pct": -3.0})
        self.assertEqual(fired[0]["current"], -3.0)


class QuarterTestCase(unittest.TestCase):
    def test_one_snapshot_per_quarter_refreshed_in_place(self):
        snaps, changed = cv.record_snapshot([], GOOD, date(2026, 8, 20))
        self.assertTrue(changed)
        snaps, changed = cv.record_snapshot(snaps, GOOD, date(2026, 9, 1))
        self.assertFalse(changed)                         # same numbers
        snaps, changed = cv.record_snapshot(
            snaps, {**GOOD, "revenue_growth_pct": 9.0}, date(2026, 9, 2))
        self.assertTrue(changed)
        self.assertEqual(len(snaps), 1)
        snaps, _ = cv.record_snapshot(snaps, GOOD, TODAY)  # next quarter
        self.assertEqual([s["quarter"] for s in snaps], ["2026Q3", "2026Q4"])

    def test_no_data_records_nothing(self):
        self.assertEqual(cv.record_snapshot([], {}, TODAY), ([], False))

    def test_judging_against_the_thesis(self):
        t = cv.clean_thesis(THESIS, TODAY)
        self.assertEqual(cv.judge_quarter(t, {"earnings_growth_pct": 12,
                                              "revenue_growth_pct": 9}), cv.RESULT_MET)
        self.assertEqual(cv.judge_quarter(t, {"earnings_growth_pct": 12,
                                              "revenue_growth_pct": 2}), cv.RESULT_MISSED)
        self.assertEqual(cv.judge_quarter(t, {}), cv.RESULT_UNKNOWN)

    def test_manual_verdict_overrides_and_streak_counts(self):
        t = cv.clean_thesis(THESIS, TODAY)
        snaps = [{"quarter": "2026Q1", "earnings_growth_pct": 20, "revenue_growth_pct": 20},
                 {"quarter": "2026Q2", "earnings_growth_pct": 1, "revenue_growth_pct": 1},
                 {"quarter": "2026Q3", "earnings_growth_pct": 30, "revenue_growth_pct": 30}]
        results = cv.quarter_results(t, snaps, {"2026Q3": {"result": "missed"}})
        self.assertEqual([r["result"] for r in results], ["met", "missed", "missed"])
        self.assertTrue(results[-1]["manual"])
        self.assertEqual(cv.missed_streak(results), 2)

    def test_trend_flags_need_three_quarters(self):
        snaps = [{"revenue_growth_pct": 15, "operating_margin_pct": 20},
                 {"revenue_growth_pct": 10, "operating_margin_pct": 21},
                 {"revenue_growth_pct": 4, "operating_margin_pct": 22}]
        flags = cv.trend_flags(snaps)
        self.assertEqual(len(flags), 1)
        self.assertIn("Sales growth slowed", flags[0])
        self.assertEqual(cv.trend_flags(snaps[:2]), [])

    def test_results_season(self):
        self.assertTrue(cv.results_season(date(2026, 10, 20))["in_season"])
        nxt = cv.results_season(date(2026, 12, 1))
        self.assertFalse(nxt["in_season"])
        self.assertEqual(nxt["start"], "2027-01-15")
        self.assertIn("Oct–Dec 2026", nxt["label"])


class ActionTestCase(unittest.TestCase):
    def _row(self, *, weight=5.0, fund=GOOD, thesis=THESIS, snaps=None,
             manual=None, today=TODAY):
        t = cv.clean_thesis(thesis, today) if thesis else None
        return cv.analyse_holding({"symbol": "ITC.NS", "name": "ITC"},
                                  weight_pct=weight, fundamentals=fund,
                                  financial=False, thesis=t, snapshots=snaps,
                                  manual_results=manual, settings=S, today=today)

    def test_no_thesis_is_borrowed_conviction(self):
        r = self._row(thesis=None)
        self.assertTrue(r["borrowed_conviction"])
        self.assertEqual(r["action"], cv.ACTION_WRITE_THESIS)
        self.assertFalse(r["add_gate"]["allowed"])

    def test_a_good_holding_with_a_met_thesis_may_be_added_to(self):
        r = self._row(snaps=[{"quarter": "2026Q3", **GOOD}])
        self.assertEqual(r["last_result"], cv.RESULT_MET)
        self.assertEqual(r["action"], cv.ACTION_ADD)
        self.assertTrue(r["add_gate"]["allowed"])

    def test_under_one_percent_is_exit_or_grow(self):
        self.assertEqual(self._row(weight=0.6)["action"], cv.ACTION_EXIT_OR_GROW)

    def test_over_max_is_never_added_to(self):
        r = self._row(weight=14)
        self.assertEqual(r["action"], cv.ACTION_TRIM)
        self.assertFalse(r["add_gate"]["allowed"])

    def test_a_fired_trigger_comes_first(self):
        r = self._row(fund={**GOOD, "revenue_growth_pct": -2.0}, weight=0.5)
        self.assertEqual(r["action"], cv.ACTION_SELL_REVIEW)

    def test_two_misses_mean_reduce(self):
        miss = {"earnings_growth_pct": 1, "revenue_growth_pct": 1}
        r = self._row(snaps=[{"quarter": "2026Q2", **miss}, {"quarter": "2026Q3", **miss}])
        self.assertEqual(r["missed_streak"], 2)
        self.assertEqual(r["action"], cv.ACTION_REDUCE)

    def test_weak_health_blocks_adding_but_is_not_a_sell(self):
        r = self._row(fund={**WEAK, "revenue_growth_pct": 9.0})
        self.assertFalse(r["add_gate"]["allowed"])
        self.assertTrue(any("health" in b for b in r["add_gate"]["blockers"]))
        self.assertEqual(r["action"], cv.ACTION_HOLD)

    def test_no_result_yet_is_not_a_pass(self):
        r = self._row(snaps=None)
        self.assertEqual(r["last_result"], cv.RESULT_UNKNOWN)
        self.assertFalse(r["add_gate"]["allowed"])
        self.assertIn(cv.NO_RESULT_BLOCKER, r["add_gate"]["blockers"])
        self.assertEqual(r["action"], cv.ACTION_HOLD)

    def test_no_business_data_is_not_a_pass(self):
        r = self._row(fund={}, snaps=[{"quarter": "2026Q3", **GOOD}])
        self.assertIn(cv.NO_HEALTH_BLOCKER, r["add_gate"]["blockers"])

    def test_review_due(self):
        r = self._row(thesis={**THESIS, "next_review": "2026-10-01"})
        self.assertEqual(r["action"], cv.ACTION_REVIEW)

    def test_board_order_is_most_urgent_first(self):
        rows = [{"action": cv.ACTION_HOLD, "weight_pct": 9},
                {"action": cv.ACTION_SELL_REVIEW, "weight_pct": 1},
                {"action": cv.ACTION_ADD, "weight_pct": 3}]
        rows.sort(key=cv.board_sort_key)
        self.assertEqual([r["action"] for r in rows],
                         [cv.ACTION_SELL_REVIEW, cv.ACTION_ADD, cv.ACTION_HOLD])


class WatchlistTestCase(unittest.TestCase):
    def _stage(self, added, thesis=THESIS, fund=GOOD):
        t = cv.clean_thesis(thesis, TODAY) if thesis else None
        return cv.watch_stage({"symbol": "TCS.NS", "added_at": added}, thesis=t,
                              health=cv.business_health(fund), settings=S, today=TODAY)

    def test_a_name_heard_recently_waits(self):
        w = self._stage("2026-09-30")
        self.assertEqual(w["stage"], cv.STAGE_WAITING)
        self.assertEqual(w["ready_after"], "2026-11-14")

    def test_after_the_wait_it_needs_a_thesis(self):
        self.assertEqual(self._stage("2026-07-01", thesis=None)["stage"],
                         cv.STAGE_NEEDS_THESIS)

    def test_a_weak_business_fails_the_check(self):
        self.assertEqual(self._stage("2026-07-01", fund=WEAK)["stage"],
                         cv.STAGE_FAILS_CHECK)

    def test_ready_for_a_one_percent_start(self):
        w = self._stage("2026-07-01")
        self.assertEqual(w["stage"], cv.STAGE_READY)
        self.assertEqual(w["initial_position_pct"], 1.0)


class EndpointTestCase(unittest.TestCase):
    """The wiring in main: no network, no files."""

    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    def setUp(self):
        m = self.main
        self._conv = m.user_conviction
        self._watch = list(m.user_watchlist)
        m.user_conviction = {}
        m.user_watchlist[:] = [{"symbol": "TCS.NS", "name": "TCS"}]
        book = {"holdings": [
            {"symbol": "ITC.NS", "name": "ITC", "total_value": 9000},
            {"symbol": "TINY.NS", "name": "Tiny", "total_value": 50},
            {"symbol": "BANKBEES.BO", "name": "BANKBEES", "total_value": 950},
        ]}
        for name, kw in (("get_portfolio", {"return_value": book}),
                         ("_stock_fundamentals", {"return_value": GOOD}),
                         ("_get_stock_info", {"return_value": {"sector": "Consumer Defensive"}}),
                         ("_history_symbol", {"side_effect": lambda s: s}),
                         ("_save_conviction", {}), ("_save_watchlist", {})):
            p = mock.patch.object(m, name, **kw)
            self.mocks = getattr(self, "mocks", {})
            self.mocks[name] = p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.main.user_conviction = self._conv
        self.main.user_watchlist[:] = self._watch

    def test_the_board(self):
        out = self.main.get_conviction_board()
        rows = {r["key"]: r for r in out["holdings"]}
        self.assertEqual(rows["ITC"]["weight_pct"], 90.0)
        self.assertEqual(rows["ITC"]["size_band"], cv.SIZE_OVER_MAX)  # over 10%
        # No thesis yet, so writing it comes before the size question.
        self.assertEqual(rows["ITC"]["action"], cv.ACTION_WRITE_THESIS)
        self.assertEqual(rows["TINY"]["action"], cv.ACTION_EXIT_OR_GROW)
        self.assertEqual(rows["BANKBEES"]["instrument"], "etf")
        # An ETF is not blocked for lacking earnings it can never have.
        self.assertNotIn(cv.NO_RESULT_BLOCKER, rows["BANKBEES"]["add_gate"]["blockers"])
        self.assertNotIn(cv.NO_HEALTH_BLOCKER, rows["BANKBEES"]["add_gate"]["blockers"])
        self.assertIsNone(rows["BANKBEES"]["health"]["score"])
        self.assertEqual(out["watchlist"][0]["stage"], cv.STAGE_WAITING)
        self.assertEqual(out["summary"]["borrowed_conviction"], 3)
        # The first sight of a quarter is snapshotted and saved; ETFs are not.
        self.assertIn("ITC", self.main.user_conviction["snapshots"])
        self.assertNotIn("BANKBEES", self.main.user_conviction["snapshots"])
        self.mocks["_save_conviction"].assert_called()
        self.mocks["_save_watchlist"].assert_called()  # added_at backfilled

    def test_thesis_round_trip(self):
        saved = self.main.put_conviction_thesis("ITC.NS", dict(THESIS))
        self.assertEqual(saved["thesis_state"], cv.THESIS_OK)
        out = self.main.get_conviction_board()
        itc = next(r for r in out["holdings"] if r["key"] == "ITC")
        self.assertFalse(itc["borrowed_conviction"])
        self.main.delete_conviction_thesis("ITC")
        self.assertNotIn("ITC", self.main.user_conviction["theses"])

    def test_a_bad_thesis_is_a_400(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.main.put_conviction_thesis("ITC", {**THESIS, "sell_triggers": [
                {"text": "x", "metric": "nope", "op": "<", "value": 1}]})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_manual_result_and_settings(self):
        from fastapi import HTTPException
        self.main.put_conviction_result("ITC", {"quarter": "2026Q3", "result": "missed"})
        self.assertEqual(self.main.user_conviction["manual_results"]["ITC"]["2026Q3"]["result"],
                         "missed")
        self.main.put_conviction_result("ITC", {"quarter": "2026Q3", "result": "clear"})
        self.assertNotIn("2026Q3", self.main.user_conviction["manual_results"]["ITC"])
        with self.assertRaises(HTTPException):
            self.main.put_conviction_result("ITC", {"quarter": "Q3", "result": "met"})
        s = self.main.put_conviction_settings({"max_position_pct": 15})
        self.assertEqual(s["settings"]["max_position_pct"], 15.0)


if __name__ == "__main__":
    unittest.main()
