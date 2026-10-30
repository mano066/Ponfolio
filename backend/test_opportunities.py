"""
Unit tests for the Today's Opportunities master bar.

    python -m unittest test_opportunities -v

The tests that matter here are the ones asserting the bar stays SILENT when
nothing qualifies, and that a risk row is never crowded out by opportunities.
"""

import unittest

import opportunities as op


def _fund(name="Small Cap Fund", score=82.0, dd=14.6, category="Small Cap",
          low_conf=False, reasons=None):
    return {
        "scheme_name": name,
        "category": category,
        "nav": 92.0,
        "score": score,
        "low_confidence": low_conf,
        "benchmark_drawdown_pct": dd,
        "reasons": reasons if reasons is not None
        else ["Nifty Smallcap 250 is 14.6% off its high"],
    }


def _stock(symbol="ABC.NS", name="ABC Ltd", score=79.0, dd=23.0,
           action="consider", blocked=False, low_conf=False, reasons=None):
    return {
        "symbol": symbol,
        "name": name,
        "price": 850.0,
        "drawdown_pct": dd,
        "benchmark_label": "IT",
        "score": score,
        "action": action,
        "averaging_blocked": blocked,
        "low_confidence": low_conf,
        "reasons": reasons if reasons is not None
        else ["23.0% below its 52-week high"],
    }


def _tape(nifty=9.2, small=2.0, mid=1.8):
    def row(sym, off):
        return {"symbol": sym, "status": "ok", "off_high_pct": off}
    return {"indices": [
        row("^NSEI", nifty),
        row("NIFTYSMLCAP250.NS", small),
        row("NIFTYMIDCAP150.NS", mid),
    ]}


class TestMarketSignal(unittest.TestCase):
    def test_reads_the_spread_not_an_average(self):
        """
        The two halves of this market routinely disagree. Today large caps are
        ~9% off while smallcaps sit at their highs; an average would hide the
        one fact a dip dashboard exists to surface.
        """
        sig = op.market_signal(_tape(nifty=9.2, small=2.0, mid=1.8))
        self.assertIn("Large caps", sig["summary"])
        self.assertIn("smallcaps", sig["summary"].lower())
        self.assertAlmostEqual(sig["broad_off_high_pct"], 9.2)
        self.assertAlmostEqual(sig["smallcap_off_high_pct"], 2.0)

    def test_signal_follows_the_deepest_index(self):
        self.assertEqual(op.market_signal(_tape(1, 1, 1))["signal"],
                         op.MARKET_NORMAL)
        self.assertEqual(op.market_signal(_tape(7, 1, 1))["signal"],
                         op.MARKET_CORRECTION)
        self.assertEqual(op.market_signal(_tape(2, 18, 2))["signal"],
                         op.MARKET_OPPORTUNITY)
        self.assertEqual(op.market_signal(_tape(2, 30, 2))["signal"],
                         op.MARKET_HIGH_RISK)

    def test_red_is_reserved_for_risk(self):
        # Same palette rule as the tape: a correction is green, not red.
        opp = op.market_signal(_tape(2, 18, 2))
        risk = op.market_signal(_tape(2, 30, 2))
        self.assertEqual(opp["emoji"], "\U0001f7e2")
        self.assertEqual(risk["emoji"], "\U0001f534")

    def test_dead_tape_is_unknown_not_normal(self):
        sig = op.market_signal({"indices": []})
        self.assertEqual(sig["signal"], op.MARKET_UNKNOWN)
        self.assertIsNone(sig["broad_off_high_pct"])

    def test_summary_is_one_sentence(self):
        summary = op.market_signal(_tape())["summary"]
        self.assertEqual(summary.count("."), 1)


class TestQuietDay(unittest.TestCase):
    """
    The behaviour this widget lives or dies by. The measured backtest in this
    app says most days offer nothing — shallow dips carried a NEGATIVE edge
    over buying on a random day — so a bar that manufactures a BUY every
    morning is not merely useless, it is wrong.
    """

    def test_nothing_qualifying_yields_a_quiet_board(self):
        board = op.build_board(funds=[_fund(score=40)],
                               stocks=[_stock(score=35)],
                               tape=_tape())
        self.assertEqual(board["status"], op.STATUS_QUIET)
        self.assertEqual(board["buy_count"], 0)
        self.assertEqual(board["headline"], op.QUIET_HEADLINE)
        self.assertTrue(board["detail"])

    def test_empty_portfolio_is_quiet_not_broken(self):
        board = op.build_board(tape=_tape())
        self.assertEqual(board["status"], op.STATUS_QUIET)
        self.assertEqual(board["rows"], [])

    def test_a_qualifying_buy_makes_the_board_actionable(self):
        board = op.build_board(funds=[_fund(score=82)], tape=_tape())
        self.assertEqual(board["status"], op.STATUS_ACTIONABLE)
        self.assertIsNone(board["headline"])


class TestAdmission(unittest.TestCase):
    def test_below_the_buy_threshold_never_reaches_a_buy_slot(self):
        board = op.build_board(funds=[_fund(score=64)], tape=_tape())
        self.assertEqual(board["buy_count"], 0)

    def test_low_confidence_funds_are_not_recommended(self):
        board = op.build_board(funds=[_fund(score=90, low_conf=True)],
                               tape=_tape())
        self.assertEqual(board["buy_count"], 0)

    def test_a_stock_the_engine_would_not_buy_is_not_promoted(self):
        # High score, but the stock layer capped it at watch.
        board = op.build_board(stocks=[_stock(score=84, action="watch")],
                               tape=_tape())
        self.assertEqual(board["buy_count"], 0)

    def test_buy_rows_are_capped(self):
        funds = [_fund(name="F%d" % i, score=90 - i) for i in range(6)]
        board = op.build_board(funds=funds, tape=_tape())
        self.assertEqual(board["buy_count"], op.MAX_BUY_ROWS)

    def test_rows_are_ranked_best_first(self):
        board = op.build_board(
            funds=[_fund(name="Low", score=70), _fund(name="High", score=88)],
            tape=_tape())
        self.assertEqual(board["rows"][0]["name"], "High")


class TestRiskRow(unittest.TestCase):
    def test_a_blocked_holding_always_appears(self):
        """
        A holding that must not be averaged into is the most consequential
        thing on the screen and must never be crowded out by opportunities.
        """
        funds = [_fund(name="F%d" % i, score=95) for i in range(5)]
        board = op.build_board(
            funds=funds,
            stocks=[_stock(symbol="ITC.NS", name="ITC", score=65, blocked=True)],
            tape=_tape())
        avoid = [r for r in board["rows"] if r["action"] == op.ROW_AVOID]
        self.assertEqual(len(avoid), 1)
        self.assertEqual(avoid[0]["name"], "ITC")

    def test_a_blocked_holding_is_never_also_a_buy(self):
        board = op.build_board(
            stocks=[_stock(symbol="X.NS", score=90, action="consider",
                           blocked=True)],
            tape=_tape())
        self.assertEqual(board["buy_count"], 0)
        self.assertEqual(board["rows"][0]["action"], op.ROW_AVOID)

    def test_risk_row_alone_still_reads_as_quiet(self):
        # Nothing to buy is still nothing to buy, even with a warning present.
        board = op.build_board(stocks=[_stock(score=60, blocked=True)],
                               tape=_tape())
        self.assertEqual(board["status"], op.STATUS_QUIET)
        self.assertEqual(board["risk_count"], 1)


class TestRowContent(unittest.TestCase):
    def test_every_row_carries_a_why(self):
        board = op.build_board(funds=[_fund(score=82)],
                               stocks=[_stock(score=79)], tape=_tape())
        for row in board["rows"]:
            self.assertTrue(row["why"], "a row with no argument behind it")

    def test_rows_carry_a_label_and_emoji(self):
        board = op.build_board(funds=[_fund(score=82)], tape=_tape())
        for row in board["rows"]:
            self.assertIn(row["action"], op.ROW_LABELS)
            self.assertTrue(row["label"])
            self.assertTrue(row["emoji"])

    def test_no_duplicate_between_buy_and_watch(self):
        board = op.build_board(funds=[_fund(name="Only", score=82)],
                               tape=_tape())
        keys = [(r["kind"], r["key"]) for r in board["rows"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_watch_slot_fills_from_the_next_best(self):
        board = op.build_board(
            funds=[_fund(name="Buy", score=82), _fund(name="Watchable", score=55)],
            tape=_tape())
        watch = [r for r in board["rows"] if r["action"] == op.ROW_WATCH]
        self.assertEqual(len(watch), 1)
        self.assertEqual(watch[0]["name"], "Watchable")


class TestPriceIsRequiredToAct(unittest.TestCase):
    """
    Found on the live board: a holding with no price and no drawdown scored
    85.6 on fundamentals alone and took the WATCH slot. Fundamentals clear the
    scoring bar by themselves, so an unpriced holding can arrive here looking
    like the best idea on the screen with no way to act on it.
    """

    def test_an_unpriced_stock_cannot_take_a_buy_slot(self):
        board = op.build_board(
            stocks=[dict(_stock(score=86, action="consider"), price=None)],
            tape=_tape())
        self.assertEqual(board["buy_count"], 0)

    def test_an_unpriced_stock_cannot_take_the_watch_slot(self):
        board = op.build_board(
            stocks=[dict(_stock(score=86, action="watch"), price=None)],
            tape=_tape())
        self.assertEqual(board["rows"], [])

    def test_an_unpriced_fund_cannot_be_recommended(self):
        board = op.build_board(funds=[dict(_fund(score=90), nav=None)],
                               tape=_tape())
        self.assertEqual(board["rows"], [])

    def test_a_risk_row_survives_without_a_price(self):
        # Deterioration is a fact about the business, not about the quote.
        board = op.build_board(
            stocks=[dict(_stock(symbol="X.NS", score=40, blocked=True),
                         price=None)],
            tape=_tape())
        self.assertEqual(board["risk_count"], 1)

    def test_a_priced_holding_is_unaffected(self):
        board = op.build_board(stocks=[_stock(score=86, action="consider")],
                               tape=_tape())
        self.assertEqual(board["buy_count"], 1)


if __name__ == "__main__":
    unittest.main()
