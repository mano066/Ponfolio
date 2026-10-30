"""
Unit tests for the pure stock dip layer.

    python -m unittest test_stock_dip -v

The tests that matter most here are the ones asserting a cheap price on a
deteriorating business is refused, and that a fall in line with the market is
not mistaken for a company problem.
"""

import unittest

import stock_dip as sd


HEALTHY = {
    "pe": 22.0,
    "pb": 3.0,
    "roe_pct": 18.0,
    "debt_to_equity": 30.0,
    "profit_margin_pct": 14.0,
    "free_cashflow": 5_000_000_000.0,
    "revenue_growth_pct": 14.0,
    "earnings_growth_pct": 17.0,
}

BROKEN = {
    "pe": 8.0,
    "pb": 0.6,
    "roe_pct": -4.0,
    "debt_to_equity": 320.0,
    "profit_margin_pct": -6.0,
    "free_cashflow": -2_000_000_000.0,
    "revenue_growth_pct": -11.0,
    "earnings_growth_pct": -40.0,
}


class TestDeteriorationFlags(unittest.TestCase):
    def test_healthy_company_raises_nothing(self):
        self.assertEqual(sd.deterioration_flags(HEALTHY), [])

    def test_broken_company_raises_every_flag(self):
        flags = sd.deterioration_flags(BROKEN)
        self.assertEqual(len(flags), 6)

    def test_missing_fundamentals_raise_nothing(self):
        # Absence of data is not evidence of damage.
        self.assertEqual(sd.deterioration_flags({}), [])
        self.assertEqual(sd.deterioration_flags(None), [])

    def test_expensive_is_not_deteriorating(self):
        # A high P/E is a valuation problem, not a broken business. Conflating
        # them would flag healthy compounders as falling knives.
        self.assertEqual(sd.deterioration_flags(dict(HEALTHY, pe=90.0)), [])


class TestHeadlineSignal(unittest.TestCase):
    def test_severe_words_are_caught(self):
        sig = sd.headline_signal(["SEBI probe into ABC Ltd accounts"])
        self.assertEqual(sig["severe_count"], 1)

    def test_price_move_words_are_deliberately_not_severe(self):
        # "Falls 8%" describes the drawdown we already measure. Matching it
        # would let one fact count twice.
        sig = sd.headline_signal(["ABC Ltd falls 8%", "ABC Ltd plunges", "XYZ drops"])
        self.assertEqual(sig["severe_count"], 0)

    def test_market_flavoured_headlines_are_separated(self):
        sig = sd.headline_signal(["ABC slips as sector selloff deepens"])
        self.assertEqual(sig["market_count"], 1)
        self.assertEqual(sig["severe_count"], 0)

    def test_blank_and_none_entries_are_ignored(self):
        self.assertEqual(sd.headline_signal(["", None, "  "])["checked"], 0)
        self.assertEqual(sd.headline_signal(None)["checked"], 0)


class TestClassifyReason(unittest.TestCase):
    def test_falling_with_the_market_is_market_wide(self):
        """The core discrimination: down 20% while the sector is down 18%."""
        r = sd.classify_reason(20.0, 18.0, HEALTHY, [])
        self.assertEqual(r["reason"], sd.REASON_MARKET_WIDE)
        self.assertAlmostEqual(r["excess_drawdown_pp"], 2.0)

    def test_falling_alone_is_company_specific(self):
        """Same 20% fall, flat sector — a completely different situation."""
        r = sd.classify_reason(20.0, 1.0, HEALTHY, [])
        self.assertEqual(r["reason"], sd.REASON_UNCERTAIN)
        self.assertAlmostEqual(r["excess_drawdown_pp"], 19.0)

    def test_mild_excess_with_clean_numbers_is_company_soft(self):
        r = sd.classify_reason(20.0, 12.0, HEALTHY, [])
        self.assertEqual(r["reason"], sd.REASON_COMPANY_SOFT)

    def test_deterioration_overrides_a_falling_market(self):
        """
        The rule that stops the market being used as an excuse: a business with
        shrinking earnings and negative cash flow is not rescued by the
        observation that its sector fell too.
        """
        r = sd.classify_reason(20.0, 19.0, BROKEN, [])
        self.assertEqual(r["reason"], sd.REASON_DETERIORATION)
        self.assertTrue(r["deterioration_flags"])

    def test_severe_news_lifts_an_in_line_fall_to_uncertain(self):
        r = sd.classify_reason(20.0, 18.0, HEALTHY, ["Auditor resigns at ABC Ltd"])
        self.assertEqual(r["reason"], sd.REASON_UNCERTAIN)

    def test_small_fall_is_not_classified(self):
        r = sd.classify_reason(2.0, 0.0, HEALTHY, [])
        self.assertEqual(r["reason"], sd.REASON_NOT_FALLING)

    def test_missing_benchmark_is_unknown_not_company_specific(self):
        """
        Without a benchmark there is no excess to measure. Treating the raw
        drawdown as excess would blame the company for a market-wide fall —
        exactly the error the module exists to prevent, in reverse.
        """
        r = sd.classify_reason(20.0, None, HEALTHY, [])
        self.assertEqual(r["reason"], sd.REASON_UNKNOWN)
        self.assertIsNone(r["excess_drawdown_pp"])

    def test_missing_price_history_is_unknown(self):
        self.assertEqual(sd.classify_reason(None, 10.0)["reason"], sd.REASON_UNKNOWN)

    def test_every_reason_has_a_label_and_emoji(self):
        for key in sd.REASON_LABELS:
            self.assertIn(key, sd.REASON_EMOJI)


class TestSubScores(unittest.TestCase):
    def test_drawdown_deadband_and_saturation(self):
        self.assertEqual(sd.score_drawdown(3.0), 0.0)      # inside dead-band
        self.assertEqual(sd.score_drawdown(40.0), 100.0)   # saturated
        self.assertEqual(sd.score_drawdown(60.0), 100.0)   # no extra credit
        self.assertIsNone(sd.score_drawdown(None))

    def test_valuation_against_sector(self):
        self.assertEqual(sd.score_valuation(10.0, 20.0), 100.0)   # half sector
        self.assertEqual(sd.score_valuation(30.0, 20.0), 0.0)     # 1.5x sector
        mid = sd.score_valuation(20.0, 20.0)
        self.assertGreater(mid, 0.0)
        self.assertLess(mid, 100.0)

    def test_loss_making_scores_zero_not_unknown(self):
        # A negative P/E is a known fact, not missing data.
        self.assertEqual(sd.score_valuation(-5.0, 20.0), 0.0)

    def test_valuation_unknown_when_nothing_to_compare(self):
        self.assertIsNone(sd.score_valuation(None, None, None))
        self.assertIsNone(sd.score_valuation(20.0, None, None))

    def test_valuation_falls_back_to_price_to_book(self):
        self.assertEqual(sd.score_valuation(None, None, 0.8), 100.0)

    def test_fundamental_averages_only_known_parts(self):
        # Only ROE known: the score must reflect ROE alone, not be diluted.
        self.assertEqual(sd.score_fundamental({"roe_pct": 25.0}), 100.0)
        self.assertIsNone(sd.score_fundamental({}))

    def test_growth_scoring(self):
        self.assertEqual(sd.score_growth({"revenue_growth_pct": 20.0,
                                          "earnings_growth_pct": 20.0}), 100.0)
        self.assertEqual(sd.score_growth({"revenue_growth_pct": -5.0}), 0.0)
        self.assertIsNone(sd.score_growth({}))

    def test_news_score_is_none_when_no_headlines_were_checked(self):
        # Silence is not good news.
        r = sd.classify_reason(20.0, 18.0, HEALTHY, [])
        self.assertIsNone(sd.score_news(r))

    def test_news_score_follows_the_verdict(self):
        good = sd.classify_reason(20.0, 18.0, HEALTHY, ["sector selloff drags ABC"])
        self.assertEqual(sd.score_news(good), 100.0)
        bad = sd.classify_reason(20.0, 18.0, BROKEN, ["ABC hit by fraud probe"])
        self.assertEqual(sd.score_news(bad), 0.0)


class TestAnalyseStock(unittest.TestCase):
    def _holding(self, dd=25.0):
        return {"symbol": "ABC.NS", "name": "ABC Ltd", "price": 850.0,
                "avg_cost": 1000.0, "drawdown_pct": dd,
                "benchmark": "^CNXIT", "benchmark_label": "IT"}

    def test_healthy_stock_in_a_sector_selloff_is_accumulable(self):
        r = sd.analyse_stock(self._holding(26.0), benchmark_drawdown_pct=24.0,
                             fundamentals=HEALTHY, sector_pe=31.0,
                             headlines=["IT sector selloff deepens on global cues"])
        self.assertEqual(r["reason_for_fall"]["reason"], sd.REASON_MARKET_WIDE)
        self.assertFalse(r["averaging_blocked"])
        self.assertIn(r["action"], (sd.ACTION_ACCUMULATE, sd.ACTION_CONSIDER))

    def test_broken_business_is_blocked_however_cheap_it_looks(self):
        """
        The single most important test in this file.

        BROKEN is down 45% with a P/E of 8 against a sector on 31 — every
        cheapness factor screams buy. The deterioration gate must override all
        of it, because this is exactly the falling knife the panel exists to
        refuse.
        """
        r = sd.analyse_stock(self._holding(45.0), benchmark_drawdown_pct=10.0,
                             fundamentals=BROKEN, sector_pe=31.0,
                             headlines=[])
        self.assertTrue(r["averaging_blocked"])
        self.assertEqual(r["action"], sd.ACTION_DO_NOT_AVERAGE)
        self.assertEqual(r["reason_for_fall"]["reason"], sd.REASON_DETERIORATION)

    def test_block_holds_even_when_the_numeric_score_is_high(self):
        r = sd.analyse_stock(self._holding(45.0), benchmark_drawdown_pct=10.0,
                             fundamentals=BROKEN, sector_pe=31.0)
        # Whatever the arithmetic said, the instruction is unambiguous.
        self.assertEqual(r["action"], sd.ACTION_DO_NOT_AVERAGE)

    def test_unknown_factors_are_dropped_not_zeroed(self):
        """
        A stock with no fundamentals must not be scored as though its
        fundamentals were bad — it must be scored on what is known, and say so.
        """
        r = sd.analyse_stock(self._holding(30.0), benchmark_drawdown_pct=28.0)
        self.assertIsNone(r["factors"][sd.FACTOR_FUNDAMENTAL])
        self.assertIsNone(r["factors"][sd.FACTOR_GROWTH])
        self.assertIsNotNone(r["factors"][sd.FACTOR_DRAWDOWN])
        self.assertLess(r["confidence"], 100.0)

    def test_low_confidence_caps_the_action_at_watch(self):
        # Drawdown alone (weight .25 -> confidence 25) cannot buy anything.
        r = sd.analyse_stock(self._holding(45.0))
        self.assertTrue(r["low_confidence"])
        self.assertEqual(r["action"], sd.ACTION_WATCH)

    def test_confidence_reflects_the_weight_of_known_factors(self):
        full = sd.analyse_stock(self._holding(30.0), benchmark_drawdown_pct=10.0,
                                fundamentals=HEALTHY, sector_pe=31.0,
                                headlines=["sector selloff"])
        self.assertAlmostEqual(full["confidence"], 100.0, places=1)

    def test_score_is_none_when_nothing_is_known(self):
        r = sd.analyse_stock({"symbol": "X.NS"})
        self.assertIsNone(r["score"])
        self.assertEqual(r["confidence"], 0.0)
        self.assertEqual(r["action"], sd.ACTION_WATCH)

    def test_valuation_history_limitation_is_stated_on_every_result(self):
        r = sd.analyse_stock(self._holding())
        self.assertTrue(r["valuation_history_note"])

    def test_result_shape_is_stable_regardless_of_input_completeness(self):
        rich = sd.analyse_stock(self._holding(), benchmark_drawdown_pct=10.0,
                                fundamentals=HEALTHY, sector_pe=31.0,
                                headlines=["x"])
        bare = sd.analyse_stock({"symbol": "X.NS"})
        self.assertEqual(set(rich), set(bare))


class TestCorporateActionGuard(unittest.TestCase):
    """
    A demerger drops the price by 40-65% in one session and simultaneously
    removes the spun-off entity's revenue from the year-on-year comparison.
    Both the drawdown and the "revenue shrinking" flag then describe an
    accounting event, not a business in trouble. Judging either way here is
    confident wrongness, so the module must decline to judge.
    """

    ACTION = {"corporate_action_suspected": True, "max_1d_move_pct": -60.0}

    def test_verdict_is_corporate_action_not_deterioration(self):
        r = sd.analyse_stock(
            {"symbol": "DEMERGED.NS", "price": 300.0, "drawdown_pct": 60.0},
            benchmark_drawdown_pct=4.0, fundamentals=BROKEN,
            price_integrity=self.ACTION)
        self.assertEqual(r["reason_for_fall"]["reason"], sd.REASON_CORPORATE_ACTION)
        self.assertTrue(r["corporate_action_suspected"])

    def test_drawdown_factor_is_dropped_not_scored(self):
        r = sd.analyse_stock(
            {"symbol": "DEMERGED.NS", "price": 300.0, "drawdown_pct": 60.0},
            benchmark_drawdown_pct=4.0, fundamentals=HEALTHY,
            price_integrity=self.ACTION)
        self.assertIsNone(r["factors"][sd.FACTOR_DRAWDOWN])

    def test_action_is_never_a_buy_on_an_unmeasurable_price(self):
        r = sd.analyse_stock(
            {"symbol": "DEMERGED.NS", "price": 300.0, "drawdown_pct": 60.0},
            benchmark_drawdown_pct=4.0, fundamentals=HEALTHY, sector_pe=20.0,
            price_integrity=self.ACTION)
        self.assertEqual(r["action"], sd.ACTION_WATCH)

    def test_clean_history_is_unaffected(self):
        clean = {"corporate_action_suspected": False, "max_1d_move_pct": -8.0}
        r = sd.analyse_stock(
            {"symbol": "INFY.NS", "price": 1500.0, "drawdown_pct": 33.0},
            benchmark_drawdown_pct=21.0, fundamentals=HEALTHY, sector_pe=31.0,
            price_integrity=clean)
        self.assertNotEqual(r["reason_for_fall"]["reason"],
                            sd.REASON_CORPORATE_ACTION)
        self.assertIsNotNone(r["factors"][sd.FACTOR_DRAWDOWN])


class TestUnknownPriceCannotBuy(unittest.TestCase):
    """
    The regression that prompted this gate: a holding whose price never
    downloaded still has fundamentals, and fundamentals alone clear the
    confidence bar. Without the gate it reached "accumulate" — a dip
    recommendation for something whose dip was never measured.
    """

    def test_strong_fundamentals_with_no_price_cannot_reach_accumulate(self):
        r = sd.analyse_stock(
            {"symbol": "BANKCO.BO", "price": None, "drawdown_pct": None},
            benchmark_drawdown_pct=7.1, fundamentals=HEALTHY, sector_pe=20.0,
            headlines=["sector selloff"])
        self.assertGreaterEqual(r["confidence"], sd.MIN_CONFIDENCE)
        self.assertIsNone(r["factors"][sd.FACTOR_DRAWDOWN])
        self.assertEqual(r["action"], sd.ACTION_WATCH)

    def test_same_stock_with_a_price_can_be_recommended(self):
        # Same holding, but now the fall is measured AND in line with its
        # market, which is the combination the panel is meant to reward.
        r = sd.analyse_stock(
            {"symbol": "BANKCO.BO", "price": 25.0, "drawdown_pct": 30.0},
            benchmark_drawdown_pct=28.0, fundamentals=HEALTHY, sector_pe=20.0,
            headlines=["banking sector selloff deepens"])
        self.assertEqual(r["reason_for_fall"]["reason"], sd.REASON_MARKET_WIDE)
        self.assertIn(r["action"], (sd.ACTION_ACCUMULATE, sd.ACTION_CONSIDER))

    def test_deterioration_still_outranks_the_price_gate(self):
        # Blocked must stay blocked, not soften to "watch".
        r = sd.analyse_stock({"symbol": "X.NS", "drawdown_pct": None},
                             benchmark_drawdown_pct=5.0, fundamentals=BROKEN)
        self.assertEqual(r["action"], sd.ACTION_DO_NOT_AVERAGE)


class TestFlagMateriality(unittest.TestCase):
    """
    The regression that prompted the severity model: a holding's revenue
    moved -0.3% year on year and the gate blocked averaging into it. A safety gate
    that fires on noise is one the user learns to ignore, which is worse than
    having none.
    """

    def test_trivial_revenue_decline_raises_no_flag(self):
        self.assertEqual(sd.deterioration_flags(dict(HEALTHY,
                                                     revenue_growth_pct=-0.3)), [])

    def test_material_revenue_decline_raises_a_mild_flag(self):
        flags = sd.deterioration_flags(dict(HEALTHY, revenue_growth_pct=-11.0))
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["severity"], sd.SEVERITY_MILD)

    def test_one_mild_flag_does_not_block(self):
        flags = sd.deterioration_flags(dict(HEALTHY, revenue_growth_pct=-11.0))
        self.assertFalse(sd.blocks_averaging(flags))

    def test_two_mild_flags_do_block(self):
        flags = sd.deterioration_flags(dict(HEALTHY, revenue_growth_pct=-11.0,
                                            earnings_growth_pct=-16.0))
        self.assertEqual(len(flags), 2)
        self.assertTrue(sd.blocks_averaging(flags))

    def test_one_severe_flag_blocks_alone(self):
        flags = sd.deterioration_flags(dict(HEALTHY, profit_margin_pct=-6.0))
        self.assertEqual(flags[0]["severity"], sd.SEVERITY_SEVERE)
        self.assertTrue(sd.blocks_averaging(flags))

    def test_lone_capex_year_does_not_block_a_healthy_company(self):
        # Negative free cash flow on its own is routine in a capex cycle.
        flags = sd.deterioration_flags(dict(HEALTHY, free_cashflow=-1e9))
        self.assertEqual(len(flags), 1)
        self.assertFalse(sd.blocks_averaging(flags))

    def test_earnings_collapse_is_severe_not_mild(self):
        flags = sd.deterioration_flags(dict(HEALTHY, earnings_growth_pct=-40.0))
        self.assertEqual(flags[0]["severity"], sd.SEVERITY_SEVERE)

    def test_no_flags_never_block(self):
        self.assertFalse(sd.blocks_averaging([]))
        self.assertFalse(sd.blocks_averaging(None))

    def test_reason_reports_display_text_and_graded_detail(self):
        r = sd.classify_reason(20.0, 19.0, BROKEN, [])
        self.assertEqual(r["reason"], sd.REASON_DETERIORATION)
        self.assertTrue(all(isinstance(x, str) for x in r["deterioration_flags"]))
        self.assertTrue(all("severity" in x for x in r["deterioration_detail"]))


class TestUnclearCauseIsNotABuy(unittest.TestCase):
    """
    Caught by looking at the running dashboard: a bank down 29.6% while its
    sector was down 6.8% — 22.8pp of its own — showed "Company-specific, cause
    unclear ... needs checking before adding" and, immediately beside it,
    "STRONG ACCUMULATION CANDIDATE". The verdict and the instruction must not
    contradict each other.
    """

    def _holding(self, dd):
        return {"symbol": "HDFCBANK.NS", "price": 706.7, "avg_cost": 900.0,
                "drawdown_pct": dd}

    def test_uncertain_caps_at_watch_however_high_the_score(self):
        r = sd.analyse_stock(self._holding(29.6), benchmark_drawdown_pct=6.8,
                             fundamentals=HEALTHY, sector_pe=25.0,
                             headlines=["bank stocks slip"])
        self.assertEqual(r["reason_for_fall"]["reason"], sd.REASON_UNCERTAIN)
        self.assertGreaterEqual(r["score"], 65)      # would have been a buy
        self.assertEqual(r["action"], sd.ACTION_WATCH)

    def test_the_same_fall_in_line_with_its_sector_still_accumulates(self):
        # The control: identical company, identical fall, but the market
        # explains it. This must still be recommendable.
        r = sd.analyse_stock(self._holding(29.6), benchmark_drawdown_pct=27.0,
                             fundamentals=HEALTHY, sector_pe=25.0,
                             headlines=["banking sector selloff"])
        self.assertEqual(r["reason_for_fall"]["reason"], sd.REASON_MARKET_WIDE)
        self.assertIn(r["action"],
                      (sd.ACTION_ACCUMULATE, sd.ACTION_CONSIDER))

    def test_deterioration_still_outranks_an_unclear_cause(self):
        r = sd.analyse_stock(self._holding(45.0), benchmark_drawdown_pct=5.0,
                             fundamentals=BROKEN, sector_pe=25.0)
        self.assertEqual(r["action"], sd.ACTION_DO_NOT_AVERAGE)


class TestNotFallingIsNotABuy(unittest.TestCase):
    """
    Found on the live master bar: a bank 0.4% below its 52-week high appeared
    as a BUY. Its drawdown factor was zero and the score was carried entirely
    by valuation and fundamentals — a sound quality score answering a question
    this panel does not ask.
    """

    def test_a_holding_at_its_high_is_capped_at_watch(self):
        r = sd.analyse_stock(
            {"symbol": "BANKCO.NS", "price": 300.0, "drawdown_pct": 0.4},
            benchmark_drawdown_pct=7.1, fundamentals=HEALTHY, sector_pe=20.0,
            headlines=["banking sector update"])
        self.assertEqual(r["reason_for_fall"]["reason"], sd.REASON_NOT_FALLING)
        self.assertEqual(r["action"], sd.ACTION_WATCH)

    def test_the_gate_overrides_a_score_that_would_otherwise_buy(self):
        """
        Asserted on classify_action directly rather than on a composite score.
        A not-falling holding cannot reach a high composite anyway — its
        drawdown factor is zero and that alone caps it near 75 — so asserting
        a number here would be testing the arithmetic, not the gate.
        """
        qualifying = 78.0
        self.assertEqual(
            sd.classify_action(qualifying, blocked=False, confidence=100.0,
                               not_falling=False),
            sd.ACTION_CONSIDER)
        self.assertEqual(
            sd.classify_action(qualifying, blocked=False, confidence=100.0,
                               not_falling=True),
            sd.ACTION_WATCH)

    def test_the_same_company_after_a_real_fall_can_be_bought(self):
        r = sd.analyse_stock(
            {"symbol": "BANKCO.NS", "price": 220.0, "drawdown_pct": 26.0},
            benchmark_drawdown_pct=24.0, fundamentals=HEALTHY, sector_pe=20.0,
            headlines=["banking sector selloff"])
        self.assertEqual(r["reason_for_fall"]["reason"], sd.REASON_MARKET_WIDE)
        self.assertIn(r["action"], (sd.ACTION_ACCUMULATE, sd.ACTION_CONSIDER))


if __name__ == "__main__":
    unittest.main()
