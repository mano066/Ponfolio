"""
Tests for the four-category rebalance: classification, both bands, the
boom/crash/volatility readings, the trigger switchboard and asset selection.

    python -m unittest test_rebalance_categories -v

Everything is offline and every plan is built at a fixed `as_of`, so a test
that passes today passes in a year.
"""

import unittest
from datetime import date

import rebalance_engine as re

TODAY = date(2026, 9, 10)


# The rest of the market, parked at a drawdown that is deliberately neutral:
# 8% is neither within the 5% the boom breadth signal wants nor past the 12%
# the crash breadth signal wants. A single-row tape would make BOTH breadth
# readings fire for free off the benchmark alone, which quietly turns every
# two-signal tape into a three-signal one.
NEUTRAL_OFF_HIGH_PCT = 8.0
OTHER_INDICES = 9


def tape(_others=NEUTRAL_OFF_HIGH_PCT, **over):
    """The benchmark, calm by default, plus a neutral rest-of-market."""
    lead = {"symbol": "^NSEI", "label": "NIFTY 50", "status": "ok",
            "off_high_pct": 6.0, "rsi_14": 52.0, "vs_dma_200_pct": 3.0,
            "chg_1y_pct": 8.0, "vol_30d_pct": 13.0}
    lead.update(over)
    rows = [lead] + [
        {"symbol": f"^X{i}", "label": f"X{i}", "status": "ok",
         "off_high_pct": _others} for i in range(OTHER_INDICES)]
    return {"indices": rows}


def breadth(others_off_high, **lead):
    """A rest-of-market sitting `others_off_high` off its highs.

    Named so it cannot collide with an `off_high_pct=` override meant for the
    benchmark row — the two are different indices and the tests set both.
    """
    return tape(others_off_high, **lead)


class ClassificationTestCase(unittest.TestCase):
    def test_a_gold_etf_held_as_a_stock_is_gold(self):
        # It is a listed stock, but banding it against the equity sleeve would
        # mean nothing.
        self.assertEqual(
            re.classify_category("Nippon Gold BeES", "GOLDBEES.NS",
                                 is_fund=False), re.CAT_GOLD)

    def test_a_liquid_etf_held_as_a_stock_is_debt(self):
        self.assertEqual(
            re.classify_category("Nippon Liquid BeES", "LIQUIDBEES.NS",
                                 is_fund=False), re.CAT_DEBT)

    def test_an_ordinary_share_is_a_stock(self):
        self.assertEqual(
            re.classify_category("Reliance Industries", "RELIANCE.NS",
                                 is_fund=False), re.CAT_STOCKS)

    def test_a_gold_fund_of_fund_is_gold_not_a_fund(self):
        # "Gold ETF FoF" matches gold and fund-of-fund markers both; gold has
        # to win or the allocation chart loses its gold sleeve entirely.
        self.assertEqual(
            re.classify_category("HDFC Gold ETF FoF", "Gold ETF FoF",
                                 is_fund=True), re.CAT_GOLD)

    def test_silver_travels_with_gold(self):
        self.assertEqual(
            re.classify_category("Silver ETF", "Commodity", is_fund=True),
            re.CAT_GOLD)

    def test_debt_categories_land_in_debt(self):
        for cat in ("Corporate Bond", "Liquid Fund", "Gilt", "Overnight Fund",
                    "Ultra Short Duration", "Banking and PSU", "Target Maturity"):
            with self.subTest(cat=cat):
                self.assertEqual(
                    re.classify_category("Some Fund", cat, is_fund=True),
                    re.CAT_DEBT)

    def test_equity_fund_categories_land_in_mutual_funds(self):
        for cat in ("Flexi Cap", "Large Cap", "ELSS", "Mid Cap", "Nifty 50 Index"):
            with self.subTest(cat=cat):
                self.assertEqual(
                    re.classify_category("Some Fund", cat, is_fund=True),
                    re.CAT_FUNDS)

    def test_category_is_not_the_same_question_as_tax_character(self):
        # An arbitrage fund is equity for tax and behaves like cash; a gold
        # fund is non-equity for tax and is not debt. Conflating the two
        # classifications gets both answers wrong.
        self.assertEqual(re.classify_category("X", "Gold", is_fund=True),
                         re.CAT_GOLD)
        self.assertFalse(re.is_equity_oriented("Gold"))
        self.assertEqual(re.classify_category("X", "Flexi Cap", is_fund=True),
                         re.CAT_FUNDS)
        self.assertTrue(re.is_equity_oriented("Flexi Cap"))


class BandTestCase(unittest.TestCase):
    def test_the_sliders_are_clamped_into_range(self):
        self.assertEqual(re.clamp_band(-5, 250), (0.0, 100.0))

    def test_crossed_sliders_are_swapped_not_rejected(self):
        # Both run 0-100 independently, so nothing stops a user dragging the
        # minimum past the maximum. The intent is unambiguous.
        self.assertEqual(re.clamp_band(40, 10), (10.0, 40.0))

    def test_missing_sliders_fall_back_to_the_defaults(self):
        self.assertEqual(re.clamp_band(None, None),
                         (re.MIN_WEIGHT_PCT, re.MAX_WEIGHT_PCT))

    def test_a_lone_holding_in_a_category_is_never_trimmed(self):
        # It is 100% of its own sleeve by construction. Enforcing a 10%
        # ceiling would say "sell 90% of the only gold you own".
        plan = re.build_plan(
            as_of=TODAY,
            funds=[{"scheme_name": "Gold FoF", "category": "Gold",
                    "units": 1000, "nav": 300, "current_value": 300000,
                    "invested": 150000}])
        gold = next(a for a in plan["actions"] if a["key"] == "Gold FoF")
        self.assertEqual(gold["action"], "HOLD")
        self.assertEqual(gold["status"], "within")

    def test_the_ceiling_widens_to_what_the_count_allows(self):
        # Five holdings must sum to 100% of their sleeve, so the smallest
        # possible largest weight is 20%. A 10% ceiling is unachievable and
        # would mark every one of them as a breach.
        funds = [{"scheme_name": f"F{i}", "category": "Flexi Cap",
                  "units": 100, "nav": 100, "current_value": 100000,
                  "invested": 90000} for i in range(5)]
        plan = re.build_plan(as_of=TODAY, funds=funds)
        self.assertEqual(plan["sleeves"][re.CAT_FUNDS]["band"], [2.0, 20.0])
        self.assertTrue(all(a["status"] == "within"
                            for a in plan["actions"]))

    def test_the_sliders_reach_the_plan(self):
        # Twenty holdings, one of them 18.4% of the sleeve. An even split
        # would be 5% each, so both ceilings below are achievable and the
        # feasibility guard stays out of the way: 10% catches the big one and
        # 25% leaves it alone. Same portfolio, different policy.
        funds = ([{"scheme_name": "Big", "category": "Flexi Cap",
                   "units": 1000, "nav": 300, "current_value": 300000,
                   "invested": 150000}]
                 + [{"scheme_name": f"F{i}", "category": "Flexi Cap",
                     "units": 700, "nav": 100, "current_value": 70000,
                     "invested": 63000} for i in range(19)])
        tight = re.build_plan(as_of=TODAY, funds=funds,
                              min_weight_pct=1, max_weight_pct=10)
        self.assertEqual(tight["policy"]["max_weight_pct"], 10.0)
        big = next(a for a in tight["actions"] if a["key"] == "Big")
        self.assertEqual(big["status"], "over")
        self.assertEqual(big["action"], "TRIM")

        loose = re.build_plan(as_of=TODAY, funds=funds,
                              min_weight_pct=1, max_weight_pct=25)
        self.assertTrue(all(a["status"] == "within" for a in loose["actions"]))

    def test_each_category_is_banded_against_itself(self):
        # The gold fund is 30% of the gold sleeve and only 3% of the book. It
        # is the sleeve weight the ceiling applies to, or one category could
        # never breach while another could never pass.
        funds = ([{"scheme_name": "Gold Big", "category": "Gold", "units": 1000,
                   "nav": 300, "current_value": 300000, "invested": 150000}]
                 + [{"scheme_name": f"Gold {i}", "category": "Gold ETF",
                     "units": 700, "nav": 100, "current_value": 70000,
                     "invested": 63000} for i in range(10)]
                 + [{"scheme_name": f"Eq {i}", "category": "Flexi Cap",
                     "units": 700, "nav": 100, "current_value": 70000,
                     "invested": 63000} for i in range(10)])
        plan = re.build_plan(as_of=TODAY, funds=funds)
        big = next(a for a in plan["actions"] if a["key"] == "Gold Big")
        self.assertEqual(big["category"], re.CAT_FUNDS)
        self.assertEqual(big["action"], "TRIM")
        self.assertAlmostEqual(big["weight_pct"], 300000 / 1700000 * 100, places=1)
        # ...and only 17.6% of the whole book, which is NOT what was banded.
        self.assertEqual(big["portfolio_pct"], big["weight_pct"])


class MarketBoomTestCase(unittest.TestCase):
    """The boom conditions, exercised at the thresholds the user picks."""

    def test_a_calm_tape_is_not_a_boom(self):
        m = re.market_boom(tape())
        self.assertTrue(m["available"])
        self.assertFalse(m["boom"])
        self.assertEqual(m["heat"], "calm")

    def test_market_up_20_percent_fires_the_default(self):
        m = re.market_boom(tape(off_high_pct=0.5, rsi_14=74.0,
                                vs_dma_200_pct=14.0, chg_1y_pct=22.0))
        self.assertTrue(m["boom"])
        self.assertGreaterEqual(m["score"], 3)
        self.assertIn("strong_year",
                      [s["name"] for s in m["signals"] if s["hit"]])

    def test_market_up_15_percent_fires_only_at_the_15_setting(self):
        # The same tape, two policies. This is the whole point of making the
        # threshold a setting: +16% is a boom to one user and not to another.
        hot15 = tape(off_high_pct=0.5, rsi_14=72.0, chg_1y_pct=16.0,
                     vs_dma_200_pct=6.0)
        at15 = re.market_boom(hot15, year_gain_pct=15.0)
        at20 = re.market_boom(hot15, year_gain_pct=20.0)
        self.assertTrue(at15["boom"], at15["signals"])
        self.assertFalse(at20["boom"])
        self.assertEqual(at15["year_gain_pct"], 15.0)

    def test_three_of_five_is_the_bar(self):
        two = re.market_boom(tape(off_high_pct=0.5, rsi_14=75.0))
        self.assertEqual(two["score"], 2)
        self.assertFalse(two["boom"])
        self.assertEqual(two["heat"], "warm")

        three = re.market_boom(tape(off_high_pct=0.5, rsi_14=75.0,
                                    vs_dma_200_pct=15.0))
        self.assertEqual(three["score"], 3)
        self.assertTrue(three["boom"])

    def test_all_five_reads_as_euphoric(self):
        m = re.market_boom(breadth(1.0, off_high_pct=0.2, rsi_14=80.0,
                                   vs_dma_200_pct=20.0, chg_1y_pct=35.0))
        self.assertEqual(m["score"], 5)
        self.assertEqual(m["heat"], "euphoric")

    def test_broad_participation_needs_the_whole_market(self):
        # One index at its high is not participation; nine of ten is.
        narrow = re.market_boom(breadth(20.0, off_high_pct=0.5))
        self.assertNotIn("broad_participation",
                         [s["name"] for s in narrow["signals"] if s["hit"]])
        wide = re.market_boom(breadth(1.0, off_high_pct=0.5))
        self.assertIn("broad_participation",
                      [s["name"] for s in wide["signals"] if s["hit"]])

    def test_a_dead_feed_is_unknown_and_never_calm(self):
        # A missing feed must not silently suppress a trigger the user armed.
        m = re.market_boom({"indices": [{"symbol": "^NSEI",
                                         "status": "unavailable"}]})
        self.assertFalse(m["available"])
        self.assertFalse(m["boom"])
        self.assertEqual(m["heat"], "unknown")

    def test_an_unreadable_signal_is_not_a_negative_one(self):
        m = re.market_boom(tape(rsi_14=None, vs_dma_200_pct=None))
        unknown = [s for s in m["signals"] if not s["known"]]
        self.assertEqual(len(unknown), 2)
        self.assertEqual(m["known_signals"], 3)


class MarketCrashTestCase(unittest.TestCase):
    def test_a_calm_tape_is_not_a_crash(self):
        m = re.market_crash(tape())
        self.assertTrue(m["available"])
        self.assertFalse(m["crash"])
        self.assertEqual(m["severity"], "stable")

    def test_a_real_fall_fires(self):
        m = re.market_crash(tape(off_high_pct=22.0, rsi_14=28.0,
                                 vs_dma_200_pct=-12.0, chg_1y_pct=-18.0))
        self.assertTrue(m["crash"])
        self.assertGreaterEqual(m["score"], 3)

    def test_the_drawdown_threshold_is_the_users_dial(self):
        falling = tape(off_high_pct=17.0, rsi_14=32.0, vs_dma_200_pct=-2.0,
                       chg_1y_pct=-4.0)
        at15 = re.market_crash(falling, drop_pct=15.0)
        at20 = re.market_crash(falling, drop_pct=20.0)
        self.assertIn("deep_drawdown",
                      [s["name"] for s in at15["signals"] if s["hit"]])
        self.assertNotIn("deep_drawdown",
                         [s["name"] for s in at20["signals"] if s["hit"]])

    def test_capitulation_is_all_five(self):
        m = re.market_crash(breadth(30.0, off_high_pct=35.0, rsi_14=22.0,
                                    vs_dma_200_pct=-25.0, chg_1y_pct=-30.0))
        self.assertEqual(m["score"], 5)
        self.assertEqual(m["severity"], "capitulation")

    def test_a_dead_feed_is_unknown_and_never_stable(self):
        m = re.market_crash({"indices": []})
        self.assertFalse(m["available"])
        self.assertFalse(m["crash"])
        self.assertEqual(m["severity"], "unknown")

    def test_boom_and_crash_cannot_both_fire_on_one_tape(self):
        for row in (tape(off_high_pct=0.5, rsi_14=75.0, vs_dma_200_pct=15.0,
                         chg_1y_pct=30.0),
                    tape(off_high_pct=25.0, rsi_14=25.0, vs_dma_200_pct=-15.0,
                         chg_1y_pct=-25.0)):
            with self.subTest():
                self.assertFalse(re.market_boom(row)["boom"]
                                 and re.market_crash(row)["crash"])


class VolatilityTestCase(unittest.TestCase):
    def test_a_quiet_tape_is_not_elevated(self):
        v = re.market_volatility(tape(vol_30d_pct=12.0))
        self.assertTrue(v["available"])
        self.assertFalse(v["elevated"])

    def test_a_disturbed_tape_is(self):
        v = re.market_volatility(tape(vol_30d_pct=31.0))
        self.assertTrue(v["elevated"])
        self.assertEqual(v["vol_pct"], 31.0)

    def test_the_threshold_is_a_setting(self):
        self.assertTrue(re.market_volatility(tape(vol_30d_pct=18.0),
                                             threshold_pct=15.0)["elevated"])
        self.assertFalse(re.market_volatility(tape(vol_30d_pct=18.0),
                                              threshold_pct=25.0)["elevated"])

    def test_no_reading_is_unavailable_not_calm(self):
        v = re.market_volatility(tape(vol_30d_pct=None))
        self.assertFalse(v["available"])
        self.assertFalse(v["elevated"])
        self.assertIsNone(v["vol_pct"])


class TriggerSwitchboardTestCase(unittest.TestCase):
    def base(self, **kw):
        kw.setdefault("last_rebalanced", "2026-09-01")  # nothing on the clock
        return re.due_triggers(TODAY, **kw)

    def test_every_rule_is_reported_whether_it_fired_or_not(self):
        t = self.base()
        self.assertEqual({r["name"] for r in t["considered"]} - {"first_run"},
                         set(re.ALL_TRIGGERS))

    def test_a_switched_off_trigger_does_not_fire_on_its_own_condition(self):
        boom = {"boom": True, "reason": "hot"}
        on = self.base(boom=boom, enabled=[re.TRIGGER_BOOM])
        self.assertIn("market_boom", [f["name"] for f in on["fired"]])

        off = self.base(boom=boom, enabled=[re.TRIGGER_CALENDAR])
        self.assertNotIn("market_boom", [f["name"] for f in off["fired"]])
        # ...and the user can still see it was the switch, not the market.
        row = next(r for r in off["considered"] if r["name"] == re.TRIGGER_BOOM)
        self.assertFalse(row["enabled"])
        self.assertFalse(row["hit"])

    def test_the_crash_trigger_fires_on_a_crash(self):
        t = self.base(crash={"crash": True, "reason": "down 22%"})
        self.assertIn("market_crash", [f["name"] for f in t["fired"]])

    def test_a_custom_gain_threshold_fires(self):
        self.assertIn(re.TRIGGER_GAIN, [f["name"] for f in self.base(
            portfolio_gain_pct=31.0, gain_trigger_pct=25.0)["fired"]])
        self.assertNotIn(re.TRIGGER_GAIN, [f["name"] for f in self.base(
            portfolio_gain_pct=19.0, gain_trigger_pct=25.0)["fired"]])

    def test_a_custom_loss_threshold_fires_on_a_fall(self):
        # Stated as a magnitude by the user and compared against a negative
        # return, so "15" means "down 15% or worse".
        self.assertIn(re.TRIGGER_LOSS, [f["name"] for f in self.base(
            portfolio_gain_pct=-16.0, loss_trigger_pct=15.0)["fired"]])
        self.assertNotIn(re.TRIGGER_LOSS, [f["name"] for f in self.base(
            portfolio_gain_pct=-9.0, loss_trigger_pct=15.0)["fired"]])
        # A gain must never fire the loss rule.
        self.assertNotIn(re.TRIGGER_LOSS, [f["name"] for f in self.base(
            portfolio_gain_pct=40.0, loss_trigger_pct=15.0)["fired"]])

    def test_no_threshold_set_means_the_rule_cannot_fire(self):
        t = self.base(portfolio_gain_pct=200.0)
        self.assertNotIn(re.TRIGGER_GAIN, [f["name"] for f in t["fired"]])

    def test_allocation_drift_fires(self):
        t = self.base(drifted=2, worst_drift_pct=11.5)
        fired = next(f for f in t["fired"] if f["name"] == re.TRIGGER_DEVIATION)
        self.assertIn("11.5", fired["detail"])

    def test_a_volatility_spike_fires(self):
        t = self.base(volatility={"elevated": True, "reason": "31% vol"})
        self.assertIn(re.TRIGGER_VOLATILITY, [f["name"] for f in t["fired"]])

    def test_the_calendar_rule_names_its_window(self):
        t = re.due_triggers(TODAY, last_rebalanced="2026-01-01",
                            cadence="semiannual")
        self.assertIn("calendar_semiannual", [f["name"] for f in t["fired"]])
        annual = re.due_triggers(TODAY, last_rebalanced="2025-01-01",
                                 cadence="annual")
        self.assertIn("calendar_annual", [f["name"] for f in annual["fired"]])

    def test_auto_mode_with_nothing_firing_is_not_due(self):
        t = self.base(mode=re.MODE_AUTO)
        self.assertEqual(t["fired"], [])
        self.assertFalse(t["due"])

    def test_manual_mode_is_always_due(self):
        # The user asked to look. The recommendations are the same either way;
        # only whether today is a day to act is a matter of policy.
        t = self.base(mode=re.MODE_MANUAL)
        self.assertEqual(t["fired"], [])
        self.assertTrue(t["due"])

    def test_a_first_run_cannot_be_switched_off(self):
        # With no baseline there is nothing to measure a window against.
        t = re.due_triggers(TODAY, last_rebalanced=None, enabled=[])
        self.assertIn("first_run", [f["name"] for f in t["fired"]])


class CategoryAllocationTestCase(unittest.TestCase):
    def book(self, **values):
        return {cat: ([{"value": v, "tradable": True}] if v else [])
                for cat, v in
                {re.CAT_STOCKS: values.get("stocks", 0),
                 re.CAT_FUNDS: values.get("funds", 0),
                 re.CAT_GOLD: values.get("gold", 0),
                 re.CAT_DEBT: values.get("debt", 0)}.items()}

    def test_all_four_categories_are_always_reported(self):
        # A 10% gold target with nothing in it is exactly the finding the user
        # needs; dropping the empty row would hide it.
        a = re.plan_categories(self.book(stocks=100000))
        self.assertEqual([r["category"] for r in a["rows"]],
                         list(re.CATEGORIES))

    def test_unset_targets_mean_no_drift(self):
        # Handing a new user a target they never chose would fire the drift
        # rule on day one and make the plan permanently due.
        a = re.plan_categories(self.book(stocks=100000))
        self.assertFalse(a["targets_set"])
        self.assertEqual(a["drifted"], 0)
        self.assertTrue(all(r["drift_pct"] == 0 for r in a["rows"]))

    def test_a_stated_target_is_measured_against(self):
        a = re.plan_categories(
            self.book(stocks=800000, funds=120000, gold=30000, debt=50000),
            targets={re.CAT_STOCKS: 50, re.CAT_FUNDS: 30,
                     re.CAT_GOLD: 10, re.CAT_DEBT: 10})
        self.assertTrue(a["targets_set"])
        stocks = next(r for r in a["rows"] if r["category"] == re.CAT_STOCKS)
        self.assertEqual(stocks["current_pct"], 80.0)
        self.assertEqual(stocks["target_pct"], 50.0)
        self.assertEqual(stocks["drift_pct"], 30.0)
        self.assertEqual(stocks["status"], "over")
        self.assertEqual(stocks["action"], "REDUCE")
        # Signed: negative is money to take OUT of this category.
        self.assertEqual(stocks["amount"], -300000.0)

        gold = next(r for r in a["rows"] if r["category"] == re.CAT_GOLD)
        self.assertEqual(gold["current_pct"], 3.0)
        self.assertEqual(gold["drift_pct"], -7.0)
        self.assertEqual(gold["status"], "under")
        self.assertEqual(gold["action"], "INCREASE")
        self.assertEqual(gold["amount"], 70000.0)

    def test_drift_inside_the_tolerance_is_left_alone(self):
        a = re.plan_categories(
            self.book(stocks=520000, funds=280000, gold=100000, debt=100000),
            targets={re.CAT_STOCKS: 50, re.CAT_FUNDS: 30,
                     re.CAT_GOLD: 10, re.CAT_DEBT: 10},
            deviation_pct=5.0)
        self.assertEqual(a["drifted"], 0)

    def test_the_tolerance_is_a_setting(self):
        book = self.book(stocks=560000, funds=240000, gold=100000, debt=100000)
        targets = {re.CAT_STOCKS: 50, re.CAT_FUNDS: 30,
                   re.CAT_GOLD: 10, re.CAT_DEBT: 10}
        self.assertEqual(re.plan_categories(book, targets=targets,
                                            deviation_pct=10.0)["drifted"], 0)
        self.assertEqual(re.plan_categories(book, targets=targets,
                                            deviation_pct=2.0)["drifted"], 2)

    def test_targets_that_do_not_sum_to_100_are_rescaled(self):
        # Four sliders adding up to 200 express a perfectly clear intention.
        targets, rescaled = re.normalise_targets(
            {re.CAT_STOCKS: 100, re.CAT_FUNDS: 60, re.CAT_GOLD: 20,
             re.CAT_DEBT: 20})
        self.assertTrue(rescaled)
        self.assertAlmostEqual(sum(targets.values()), 100.0, places=2)
        self.assertEqual(targets[re.CAT_STOCKS], 50.0)

    def test_an_empty_book_does_not_divide_by_zero(self):
        a = re.plan_categories(self.book())
        self.assertEqual(a["total_value"], 0.0)
        self.assertEqual(a["drifted"], 0)


class ManualAssetTestCase(unittest.TestCase):
    def plan(self, **kw):
        return re.build_plan(
            as_of=TODAY,
            funds=[{"scheme_name": f"F{i}", "category": "Flexi Cap",
                    "units": 100, "nav": 100, "current_value": 100000,
                    "invested": 90000} for i in range(9)],
            **kw)

    def test_manual_gold_counts_towards_the_weights(self):
        # Leaving it out would make every other category look heavier.
        plan = self.plan(manual_assets={re.CAT_GOLD: 100000})
        gold = next(r for r in plan["allocation"]["rows"]
                    if r["category"] == re.CAT_GOLD)
        self.assertEqual(gold["value"], 100000.0)
        self.assertEqual(plan["portfolio_value"], 1000000.0)
        self.assertEqual(gold["current_pct"], 10.0)

    def test_manual_assets_are_flagged_as_untradable(self):
        plan = self.plan(manual_assets={re.CAT_GOLD: 100000})
        row = next(a for a in plan["actions"]
                   if a["key"] == f"manual:{re.CAT_GOLD}")
        self.assertFalse(row["tradable"])
        self.assertIsNone(row["gain_pct"])

    def test_a_manual_asset_is_never_given_a_priced_trade(self):
        # It has no units, no price and no purchase date, so there is no lot
        # to sell and no tax to compute. Saying REVIEW is honest; printing a
        # rupee amount would not be.
        plan = self.plan(manual_assets={re.CAT_GOLD: 100000,
                                        re.CAT_DEBT: 500000})
        for cat in (re.CAT_GOLD, re.CAT_DEBT):
            row = next(a for a in plan["actions"] if a["key"] == f"manual:{cat}")
            self.assertIn(row["action"], ("HOLD", "REVIEW"))
            self.assertEqual(row["amount"], 0.0)
        self.assertEqual(plan["totals"]["sell_value"], 0.0)

    def test_manual_value_is_reported_apart_from_tradable_value(self):
        plan = self.plan(manual_assets={re.CAT_GOLD: 100000})
        gold = next(r for r in plan["allocation"]["rows"]
                    if r["category"] == re.CAT_GOLD)
        self.assertEqual(gold["manual_value"], 100000.0)
        self.assertEqual(gold["tradable_value"], 0.0)

    def test_an_unknown_manual_category_is_ignored(self):
        plan = self.plan(manual_assets={"crypto": 100000, "": 5})
        self.assertEqual(plan["portfolio_value"], 900000.0)


class SelectionTestCase(unittest.TestCase):
    def book(self):
        stocks = [{"symbol": "BIG.NS", "name": "Big", "shares": 3000,
                   "avg_cost": 50, "current_price": 100,
                   "total_value": 300000, "invested": 150000}]
        stocks += [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 700,
                    "avg_cost": 90, "current_price": 100,
                    "total_value": 70000, "invested": 63000}
                   for i in range(10)]
        funds = [{"scheme_name": "Big Fund", "category": "Flexi Cap",
                  "units": 1000, "nav": 300, "avg_nav": 150,
                  "current_value": 300000, "invested": 150000}]
        funds += [{"scheme_name": f"F{i}", "category": "Large Cap",
                   "units": 700, "nav": 100, "avg_nav": 90,
                   "current_value": 70000, "invested": 63000}
                  for i in range(10)]
        return stocks, funds

    def plan(self, **kw):
        stocks, funds = self.book()
        return re.build_plan(as_of=TODAY, stocks=stocks, funds=funds, **kw)

    def test_everything_is_in_scope_by_default(self):
        plan = self.plan()
        self.assertTrue(all(a["selected"] for a in plan["actions"]))
        self.assertEqual(plan["totals"]["skipped"], 0)
        self.assertEqual(plan["totals"]["trims"], 2)

    def test_selecting_one_category_skips_the_other(self):
        plan = self.plan(selected_categories=[re.CAT_STOCKS])
        big_fund = next(a for a in plan["actions"] if a["key"] == "Big Fund")
        big_stock = next(a for a in plan["actions"] if a["key"] == "BIG.NS")
        self.assertEqual(big_stock["action"], "TRIM")
        self.assertEqual(big_fund["action"], "SKIP")
        self.assertEqual(plan["totals"]["trims"], 1)

    def test_deselecting_does_not_change_a_single_weight(self):
        # A weight that moves when you tick a checkbox is not a weight.
        full = {a["key"]: a["weight_pct"] for a in self.plan()["actions"]}
        narrowed = {a["key"]: a["weight_pct"] for a in
                    self.plan(selected_categories=[re.CAT_STOCKS])["actions"]}
        self.assertEqual(full, narrowed)

    def test_an_explicit_asset_list_narrows_further(self):
        plan = self.plan(selected_assets=["BIG.NS"])
        self.assertEqual(
            [a["key"] for a in plan["actions"] if a["action"] == "TRIM"],
            ["BIG.NS"])
        self.assertEqual(plan["totals"]["skipped"], 1)

    def test_the_totals_only_count_what_was_selected(self):
        everything = self.plan()["totals"]
        narrowed = self.plan(selected_assets=["BIG.NS"])["totals"]
        self.assertLess(narrowed["sell_value"], everything["sell_value"])
        self.assertLess(narrowed["tax_estimated"], everything["tax_estimated"])

    def test_a_skipped_breach_does_not_open_the_book(self):
        # If nothing selected is out of band, the band rule has nothing to say.
        plan = self.plan(selected_categories=[re.CAT_GOLD],
                         last_rebalanced="2026-09-01")
        self.assertNotIn(re.TRIGGER_BAND,
                         [f["name"] for f in plan["triggers"]["fired"]])


class AssetDisplayTestCase(unittest.TestCase):
    """Every row must carry the six columns the screen is specified to show."""

    def plan(self):
        return re.build_plan(
            as_of=TODAY,
            stocks=[{"symbol": "BIG.NS", "name": "Big Co", "shares": 3000,
                     "avg_cost": 50, "current_price": 100,
                     "total_value": 300000, "invested": 150000}]
            + [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 700,
                "avg_cost": 90, "current_price": 100, "total_value": 70000,
                "invested": 63000} for i in range(10)],
            funds=[{"scheme_name": "Gold FoF", "category": "Gold",
                    "units": 1000, "nav": 300, "current_value": 300000,
                    "invested": 150000}],
            manual_assets={re.CAT_DEBT: 200000})

    def test_every_row_has_the_specified_columns(self):
        for row in self.plan()["actions"]:
            with self.subTest(key=row["key"]):
                for field in ("name", "category", "category_label",
                              "weight_pct", "portfolio_pct", "target_pct",
                              "value", "gain_pct", "action", "reason"):
                    self.assertIn(field, row)

    def test_gain_loss_percent_is_computed_from_cost(self):
        big = next(a for a in self.plan()["actions"] if a["key"] == "BIG.NS")
        # Bought at 50, worth 100.
        self.assertEqual(big["gain_pct"], 100.0)

    def test_a_holding_with_no_cost_reports_no_return_rather_than_zero(self):
        # 0% would read as "flat" for something that may be up a third.
        plan = re.build_plan(
            as_of=TODAY,
            stocks=[{"symbol": "X.NS", "name": "X", "shares": 10,
                     "avg_cost": 0, "current_price": 100, "total_value": 1000}])
        row = next(a for a in plan["actions"] if a["key"] == "X.NS")
        self.assertIsNone(row["gain_pct"])

    def test_the_target_is_the_edge_a_breach_is_steered_to(self):
        plan = self.plan()
        big = next(a for a in plan["actions"] if a["key"] == "BIG.NS")
        self.assertEqual(big["status"], "over")
        self.assertEqual(big["target_pct"], plan["policy"]["max_weight_pct"])

    def test_a_holding_inside_its_band_targets_where_it_already_is(self):
        # Printing a mid-band number would imply a trade the policy does not
        # want.
        plan = self.plan()
        row = next(a for a in plan["actions"] if a["key"] == "S0.NS")
        self.assertEqual(row["status"], "within")
        self.assertEqual(row["target_pct"], row["weight_pct"])

    def test_portfolio_return_ignores_holdings_with_no_cost_basis(self):
        plan = re.build_plan(
            as_of=TODAY,
            stocks=[{"symbol": "A.NS", "name": "A", "shares": 10,
                     "avg_cost": 50, "current_price": 100, "total_value": 1000,
                     "invested": 500},
                    {"symbol": "B.NS", "name": "B", "shares": 10,
                     "avg_cost": 0, "current_price": 100, "total_value": 1000}])
        # Only A is measurable: 1000 against 500 is +100%.
        self.assertEqual(plan["portfolio_gain_pct"], 100.0)


class PlanShapeTestCase(unittest.TestCase):
    def test_an_empty_portfolio_answers_instead_of_raising(self):
        plan = re.build_plan(as_of=TODAY)
        self.assertEqual(plan["actions"], [])
        self.assertEqual(plan["portfolio_value"], 0.0)
        self.assertIsNone(plan["portfolio_gain_pct"])
        self.assertEqual(len(plan["allocation"]["rows"]), 4)

    def test_the_policy_echoes_back_every_setting(self):
        plan = re.build_plan(
            as_of=TODAY, min_weight_pct=3, max_weight_pct=15,
            deviation_pct=7, boom_gain_pct=15, crash_drop_pct=25,
            gain_trigger_pct=30, loss_trigger_pct=20, vol_trigger_pct=28,
            mode=re.MODE_MANUAL, cadence="annual")
        p = plan["policy"]
        self.assertEqual((p["min_weight_pct"], p["max_weight_pct"]), (3.0, 15.0))
        self.assertEqual(p["deviation_pct"], 7.0)
        self.assertEqual(p["boom_gain_pct"], 15)
        self.assertEqual(p["crash_drop_pct"], 25)
        self.assertEqual(p["gain_trigger_pct"], 30)
        self.assertEqual(p["loss_trigger_pct"], 20)
        self.assertEqual(p["vol_trigger_pct"], 28)
        self.assertEqual(p["mode"], re.MODE_MANUAL)
        self.assertEqual(p["cadence"], "annual")

    def test_a_dead_tape_leaves_the_band_rules_standing(self):
        plan = re.build_plan(
            as_of=TODAY, tape=None,
            stocks=[{"symbol": "BIG.NS", "name": "Big", "shares": 3000,
                     "avg_cost": 50, "current_price": 100,
                     "total_value": 300000, "invested": 150000}]
            + [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 700,
                "avg_cost": 90, "current_price": 100, "total_value": 70000,
                "invested": 63000} for i in range(10)])
        self.assertFalse(plan["market"]["available"])
        self.assertFalse(plan["crash"]["available"])
        self.assertFalse(plan["volatility"]["available"])
        self.assertTrue(any(a["action"] == "TRIM" for a in plan["actions"]))

    def test_a_crash_adds_the_buy_side_note(self):
        plan = re.build_plan(
            as_of=TODAY,
            tape=tape(off_high_pct=25.0, rsi_14=25.0, vs_dma_200_pct=-15.0,
                      chg_1y_pct=-25.0))
        self.assertTrue(plan["crash"]["crash"])
        self.assertIn("A crash is the buy side of the same rule",
                      [n["title"] for n in plan["strategy"]])



class StrategyPresetTestCase(unittest.TestCase):
    """The selectable presets that drive the plan from the allocation screen."""

    def book(self, n=9):
        """One oversized name, a band of mid-sized ones, and three genuinely
        underweight names.

        The underweights are the point: an earlier version of this fixture had
        none, so the deployment-order tests compared two empty lists and passed
        without testing anything. Each tiny holding also carries a different
        cost basis, so `gain_pct` differs and an ordering is observable.
        """
        big = [{"symbol": "BIG.NS", "name": "Big", "shares": 3000,
                "avg_cost": 50, "current_price": 100,
                "total_value": 300000, "invested": 150000}]
        mid = [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 700,
                "avg_cost": 80 + i * 4, "current_price": 100,
                "total_value": 70000, "invested": (80 + i * 4) * 700}
               for i in range(n)]
        # Below the 2% floor of a ~Rs 9.5L book, so each draws a top-up.
        tiny = [{"symbol": "T1.NS", "name": "T1", "shares": 50,
                 "avg_cost": 200, "current_price": 100,
                 "total_value": 5000, "invested": 10000},     # -50%
                {"symbol": "T2.NS", "name": "T2", "shares": 80,
                 "avg_cost": 100, "current_price": 100,
                 "total_value": 8000, "invested": 8000},      # 0%
                {"symbol": "T3.NS", "name": "T3", "shares": 120,
                 "avg_cost": 50, "current_price": 100,
                 "total_value": 12000, "invested": 6000}]     # +100%
        return big + mid + tiny

    def plan(self, sid, **kw):
        return re.build_plan(as_of=TODAY, stocks=self.book(), strategy=sid, **kw)

    def test_every_preset_is_selectable_and_round_trips(self):
        for s in re.STRATEGIES:
            with self.subTest(s["id"]):
                got = self.plan(s["id"])["strategy_preset"]
                self.assertEqual(got["id"], s["id"])

    def test_the_default_is_the_best_measured(self):
        # Whichever preset ranks first after tax IS the default. Pinning the
        # id alone would let the two drift apart the moment a figure moves.
        best = min((x for x in re.STRATEGIES if x.get("rank")),
                   key=lambda x: x["rank"])
        self.assertEqual(re.DEFAULT_STRATEGY, best["id"])
        self.assertEqual(re.get_strategy(None)["id"], best["id"])
        self.assertEqual(re.get_strategy("nonsense")["id"], best["id"])

    def test_ranks_run_one_to_sixteen_with_no_gaps_or_ties(self):
        ranked = sorted(x["rank"] for x in re.STRATEGIES if x.get("rank"))
        self.assertEqual(ranked, list(range(1, 17)))
        for x in re.STRATEGIES:
            with self.subTest(x["id"]):
                # Custom has no measured result, so it has no rank.
                self.assertEqual(x["rank"] is None, x["measured"] is None)
                if x["rank"]:
                    self.assertEqual(x["rank_of"], 16)

    def test_rank_order_follows_the_measured_after_tax_return(self):
        ranked = sorted((x for x in re.STRATEGIES if x.get("rank")),
                        key=lambda x: x["rank"])
        xirrs = [x["measured"]["xirr_pct"] for x in ranked]
        self.assertEqual(xirrs, sorted(xirrs, reverse=True))
        self.assertEqual(ranked[0]["id"], "M4")

    def test_only_the_presets_measured_with_it_carry_the_guard(self):
        guarded = {x["id"] for x in re.STRATEGIES if x.get("peak_guard")}
        self.assertEqual(guarded, {"M4", "M5"})

    def test_a_preset_sets_the_ceiling(self):
        for sid, ceiling in (("S3", 12.5), ("S7", 20.0), ("S10", 20.0),
                             ("M1", 25.0)):
            with self.subTest(sid):
                p = self.plan(sid)
                self.assertEqual(p["policy"]["max_weight_pct"], ceiling)

    def test_an_explicit_ceiling_beats_the_preset(self):
        # The user's own slider must win, or setting it does nothing.
        p = self.plan("S10", max_weight_pct=12.0)
        self.assertEqual(p["policy"]["max_weight_pct"], 12.0)

    def test_a_never_sells_preset_proposes_no_trim(self):
        for sid in ("S1", "S2", "S5", "S6", "S9"):
            with self.subTest(sid):
                p = self.plan(sid)
                self.assertTrue(p["strategy_preset"]["never_sells"])
                self.assertEqual(
                    [a for a in p["actions"] if a["action"] == "TRIM"], [])

    def test_a_suppressed_trim_still_reports_the_breach(self):
        # Hiding it would misrepresent the portfolio; only the SALE is dropped.
        p = self.plan("S2", max_weight_pct=10.0)
        over = [a for a in p["actions"] if a["status"] == "over"]
        self.assertTrue(over)
        self.assertTrue(all(a["action"] == "HOLD" for a in over))
        self.assertTrue(all(a.get("suppressed_trim") for a in over))

    def test_a_trimming_preset_does_propose_the_sale(self):
        p = self.plan("S4")      # 10% ceiling, the tightest offered
        self.assertFalse(p["strategy_preset"]["never_sells"])
        self.assertTrue([a for a in p["actions"] if a["action"] == "TRIM"])

    def test_the_deploy_order_changes_which_top_up_is_first(self):
        ranks = {}
        for sid in ("S9", "S5", "S2"):
            adds = [a for a in self.plan(sid)["actions"] if a["action"] == "ADD"]
            adds.sort(key=lambda a: a["fund_rank"])
            self.assertTrue(adds, f"{sid}: the fixture produced no top-ups")
            ranks[sid] = adds[0]["key"]
        # Laggard and momentum must not agree on the first name to fund, or
        # the ordering is not being applied at all.
        self.assertNotEqual(ranks["S9"], ranks["S5"])
        self.assertEqual(ranks["S9"], "T1.NS")   # worst return on cost
        self.assertEqual(ranks["S5"], "T3.NS")   # best return on cost

    def test_laggard_order_funds_the_worst_return_first(self):
        adds = [a for a in self.plan("S9")["actions"] if a["action"] == "ADD"]
        adds.sort(key=lambda a: a["fund_rank"])
        gains = [a["gain_pct"] for a in adds if a["gain_pct"] is not None]
        self.assertGreaterEqual(len(gains), 3)
        self.assertEqual(gains, sorted(gains))

    def test_momentum_order_funds_the_best_return_first(self):
        adds = [a for a in self.plan("S5")["actions"] if a["action"] == "ADD"]
        adds.sort(key=lambda a: a["fund_rank"])
        gains = [a["gain_pct"] for a in adds if a["gain_pct"] is not None]
        self.assertGreaterEqual(len(gains), 3)
        self.assertEqual(gains, sorted(gains, reverse=True))

    def test_income_reinvestment_is_advised_only_where_the_rule_says_so(self):
        for sid in ("S6", "S8", "S10", "M1"):
            with self.subTest(sid):
                self.assertIsNotNone(
                    self.plan(sid)["strategy_preset"]["income_note"])
        for sid in ("S1", "S2", "S3", "S9"):
            with self.subTest(sid):
                self.assertIsNone(
                    self.plan(sid)["strategy_preset"]["income_note"])

    def test_the_momentum_proxy_is_disclosed(self):
        # The live book has no 12-month price momentum, so the ordering uses
        # return on cost. Saying so is the difference between a label and a
        # claim, and it must travel with the plan.
        for sid in ("S5", "S9", "M1"):
            with self.subTest(sid):
                note = self.plan(sid)["strategy_preset"]["deploy_note"]
                self.assertIsNotNone(note)
                self.assertIn("return on cost", note)

    def test_the_measured_figure_is_labelled_as_a_backtest(self):
        note = self.plan("S10")["strategy_preset"]["measured_note"]
        self.assertIn("not a forecast", note)

    def test_custom_leaves_the_sliders_alone(self):
        p = self.plan(re.STRATEGY_CUSTOM, min_weight_pct=3, max_weight_pct=14)
        self.assertEqual(p["policy"]["min_weight_pct"], 3.0)
        self.assertEqual(p["policy"]["max_weight_pct"], 14.0)
        self.assertFalse(p["strategy_preset"]["never_sells"])

    def test_no_preset_behaves_as_before(self):
        # Callers that never pass a strategy must be unaffected by all of this.
        p = re.build_plan(as_of=TODAY, stocks=self.book())
        self.assertEqual(p["policy"]["max_weight_pct"], re.MAX_WEIGHT_PCT)
        self.assertFalse(p["strategy_preset"]["never_sells"])

    def test_a_never_sells_preset_reports_no_share_count_to_sell(self):
        """The regression this guards: `trade_units` was derived before the
        action was rewritten, so a never-sells preset turned a TRIM into a HOLD
        and left a NEGATIVE share count behind it — a sell quantity sitting
        under a heading that reads BUY ONLY."""
        for sid in ("S1", "S2", "S5", "S6", "S9"):
            with self.subTest(sid):
                p = re.build_plan(as_of=TODAY, stocks=self.book(),
                                  strategy=sid)
                self.assertTrue(p["strategy_preset"]["never_sells"])
                for a in p["actions"]:
                    self.assertGreaterEqual(
                        a["trade_units"], 0,
                        f"{sid}/{a['key']} proposes selling {a['trade_units']}")

    def test_the_share_count_always_agrees_with_the_action(self):
        for s in re.STRATEGIES:
            p = re.build_plan(as_of=TODAY, stocks=self.book(),
                              strategy=s["id"])
            for a in p["actions"]:
                with self.subTest(f"{s['id']}/{a['key']}"):
                    if a["action"] == "TRIM":
                        self.assertLess(a["trade_units"], 0)
                    elif a["action"] == "ADD":
                        self.assertGreater(a["trade_units"], 0)
                    else:
                        self.assertEqual(a["trade_units"], 0)

    def test_the_column_flags_never_contradict_the_rule(self):
        for s in re.STRATEGIES:
            p = re.build_plan(as_of=TODAY, stocks=self.book(),
                              strategy=s["id"])
            sp = p["strategy_preset"]
            with self.subTest(s["id"]):
                # The long-term column exists exactly when a sale is possible.
                self.assertEqual(sp["shows_long_term_units"],
                                 not sp["never_sells"])
                # A rank is only shown with a label to read it by.
                self.assertEqual(sp["shows_rank"],
                                 sp["rank_label"] is not None)

    def test_a_rank_covers_every_tradable_holding_in_the_category(self):
        # A rank that only covered the funded names could not answer "why this
        # one and not that one", which is the whole question under a tilt.
        p = re.build_plan(as_of=TODAY, stocks=self.book(), strategy="S9")
        stocks = [a for a in p["actions"] if a["category"] == re.CAT_STOCKS]
        ranks = sorted(a["deploy_rank"] for a in stocks)
        self.assertEqual(ranks, list(range(1, len(stocks) + 1)))


class ShareCountTestCase(unittest.TestCase):
    """Held units, long-term units, and the trade as a signed share count."""

    def plan(self, **kw):
        stocks = ([{"symbol": "BIG.NS", "name": "Big", "shares": 1000,
                    "avg_cost": 50, "current_price": 300,
                    "total_value": 300000, "invested": 50000}]
                  + [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 700,
                      "avg_cost": 90, "current_price": 100,
                      "total_value": 70000, "invested": 63000}
                     for i in range(9)]
                  + [{"symbol": "TINY.NS", "name": "Tiny", "shares": 50,
                      "avg_cost": 100, "current_price": 100,
                      "total_value": 5000, "invested": 5000}])
        # 600 of the 1,000 BIG shares are past a year; 400 are not.
        txns = {"BIG.NS": [
            {"date": "2020-01-01", "type": "BUY", "qty": 600, "price": 50},
            {"date": "2026-08-01", "type": "BUY", "qty": 400, "price": 50}]}
        return re.build_plan(as_of=TODAY, stocks=stocks, txns_by_symbol=txns,
                             max_weight_pct=10, **kw)

    def rows(self, **kw):
        return {a["key"]: a for a in self.plan(**kw)["actions"]}

    def test_held_units_are_the_actual_position(self):
        self.assertEqual(self.rows()["BIG.NS"]["held_units"], 1000)
        self.assertEqual(self.rows()["TINY.NS"]["held_units"], 50)

    def test_long_term_units_count_only_what_has_aged_past_a_year(self):
        # The example the user gave: hold 1,000, of which some smaller number
        # is sellable at the long-term rate.
        self.assertEqual(self.rows()["BIG.NS"]["long_term_units"], 600)

    def test_a_position_with_no_dated_history_shows_no_long_term_units(self):
        # A synthetic lot is dated today, so nothing is long-term. Reporting
        # otherwise would claim a tax treatment the ledger cannot support.
        self.assertEqual(self.rows()["S0.NS"]["long_term_units"], 0)

    def test_a_trim_is_a_negative_share_count(self):
        big = self.rows()["BIG.NS"]
        self.assertEqual(big["action"], "TRIM")
        self.assertLess(big["trade_units"], 0)
        self.assertAlmostEqual(abs(big["trade_units"]), big["units"], places=4)

    def test_a_top_up_is_a_positive_share_count(self):
        tiny = self.rows()["TINY.NS"]
        self.assertEqual(tiny["action"], "ADD")
        self.assertGreater(tiny["trade_units"], 0)
        self.assertAlmostEqual(tiny["trade_units"], tiny["units"], places=4)

    def test_a_row_proposing_nothing_trades_nothing(self):
        for key in (f"S{i}.NS" for i in range(9)):
            with self.subTest(key):
                self.assertEqual(self.rows()[key]["trade_units"], 0)

    def test_the_trade_never_exceeds_the_position(self):
        for a in self.plan()["actions"]:
            if a["trade_units"] < 0:
                with self.subTest(a["key"]):
                    self.assertLessEqual(abs(a["trade_units"]), a["held_units"])

    def test_long_term_only_caps_the_sale_at_the_aged_units(self):
        # With the restriction on, BIG cannot sell more than its 600 aged
        # shares however far over the ceiling it is.
        big = self.rows(long_term_only=True)["BIG.NS"]
        if big["action"] == "TRIM":
            self.assertLessEqual(abs(big["trade_units"]),
                                 big["long_term_units"])

    def test_every_row_carries_the_counts(self):
        for a in self.plan()["actions"]:
            with self.subTest(a["key"]):
                for field in ("held_units", "long_term_units", "trade_units"):
                    self.assertIn(field, a)
                    self.assertIsInstance(a[field], (int, float))


class ExchangeMatchTestCase(unittest.TestCase):
    """NSE and BSE listings of one company are one position.

    A Console tradebook files IOC under IOC.NS while the Kite holding is
    IOC.BO. Matching the full ticker loses that holding's purchase history,
    which means no verified long-term units, which means the plan can never
    propose selling it — silently, and only once the units are old enough to
    matter.
    """

    def plan(self, holding_symbol, ledger_symbol):
        stocks = [{"symbol": holding_symbol, "name": "Big", "shares": 1000,
                   "avg_cost": 50, "current_price": 300,
                   "total_value": 300000, "invested": 50000}]
        stocks += [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 700,
                    "avg_cost": 90, "current_price": 100,
                    "total_value": 70000, "invested": 63000}
                   for i in range(9)]
        txns = {ledger_symbol: [
            {"date": "2020-01-01", "type": "BUY", "qty": 1000, "price": 50}]}
        return {a["key"]: a for a in re.build_plan(
            as_of=TODAY, stocks=stocks, txns_by_symbol=txns,
            max_weight_pct=10, long_term_only=True)["actions"]}

    def test_base_symbol_strips_the_exchange(self):
        self.assertEqual(re.base_symbol("IOC.BO"), re.base_symbol("IOC.NS"))
        self.assertEqual(re.base_symbol("ioc.ns"), "IOC")
        self.assertEqual(re.base_symbol(None), "")

    def test_a_ledger_filed_on_the_other_exchange_still_counts(self):
        cross = self.plan("BIG.BO", "BIG.NS")["BIG.BO"]
        same = self.plan("BIG.NS", "BIG.NS")["BIG.NS"]
        self.assertEqual(cross["long_term_units"], 1000)
        self.assertEqual(cross["long_term_units"], same["long_term_units"])
        self.assertEqual(cross["action"], same["action"])

    def test_the_exact_ticker_still_wins_when_it_is_present(self):
        rows = self.plan("BIG.NS", "BIG.NS")
        self.assertEqual(rows["BIG.NS"]["long_term_units"], 1000)

    def test_holding_both_listings_does_not_double_count(self):
        # If the book genuinely holds both, a base match would attach one
        # ledger to both positions and claim twice the aged units.
        ledgers = {"BIG.NS": [{"date": "2020-01-01", "type": "BUY",
                               "qty": 1000, "price": 50}],
                   "BIG.BO": [{"date": "2020-01-01", "type": "BUY",
                               "qty": 5, "price": 50}]}
        self.assertEqual(len(re._ledger_for(ledgers, "BIG.NS")), 1)
        self.assertEqual(re._ledger_for(ledgers, "OTHER.BO"), [])


class DenominatorBreachTestCase(unittest.TestCase):
    """A weight ceiling breached by OTHER holdings falling is not a sell.

    From the 2020 ledger: SCI was 17.96% of the book in Dec 2019 and 20.44% in
    Jul 2020, so the 20% band sold 51% of it at Rs 57 — while SCI itself was
    DOWN 5.6%. The rest of the book had fallen 17.7% in the crash. The rule
    realised a loss on a loser because its neighbours crashed harder.
    """

    def plan(self, big_price, big_cost, rest_price, **kw):
        # Sized so the trim clears the Rs 5,000 minimum; below it the row is
        # already HOLD for an unrelated reason and proves nothing.
        stocks = [{"symbol": "BIG.NS", "name": "Big", "shares": 1000,
                   "avg_cost": big_cost, "current_price": big_price,
                   "total_value": 1000 * big_price,
                   "invested": 1000 * big_cost}]
        stocks += [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 1000,
                    "avg_cost": 100, "current_price": rest_price,
                    "total_value": 1000 * rest_price, "invested": 100000}
                   for i in range(4)]
        # M4 is the preset that CARRIES the guard. Passing no strategy means
        # no preset is in force at all, and then there is no guard to test.
        kw.setdefault("strategy", "M4")
        return {a["key"]: a for a in re.build_plan(
            as_of=TODAY, stocks=stocks, txns_by_symbol={},
            max_weight_pct=20, long_term_only=False, **kw)["actions"]}

    def test_a_holding_down_on_cost_is_not_trimmed(self):
        # BIG is over the 20% ceiling but under water; the others collapsed.
        big = self.plan(big_price=95, big_cost=100, rest_price=40)["BIG.NS"]
        self.assertEqual(big["status"], "over")
        self.assertLess(big["gain_pct"], 0)
        self.assertEqual(big["action"], "HOLD")
        self.assertTrue(big["suppressed_trim"])
        self.assertEqual(big["units_sold"], 0)
        self.assertIn("other holdings falling", big["reason"])

    def test_a_holding_that_actually_grew_is_still_trimmed(self):
        # The guard must not disable the band. Same breach, but BIG is up.
        big = self.plan(big_price=300, big_cost=100, rest_price=100)["BIG.NS"]
        self.assertEqual(big["status"], "over")
        self.assertGreater(big["gain_pct"], 0)
        self.assertEqual(big["action"], "TRIM")
        self.assertGreater(big["units_sold"], 0)

    def test_the_breach_is_still_reported_either_way(self):
        # Suppressing the SALE must not hide the fact from the reader.
        big = self.plan(big_price=95, big_cost=100, rest_price=40)["BIG.NS"]
        self.assertEqual(big["status"], "over")
        self.assertGreater(big["weight_pct"], 20)

    def test_a_late_sale_is_held_when_the_peak_is_known(self):
        # The guard the backtest actually rewarded: at a 20% ceiling on the
        # ten-stock basket it fired 9 times and moved the monthly run from
        # 16.84% to 17.60% pre-tax. A holding 12% below its own 12-month high
        # is not being harvested.
        rows = self.plan(big_price=300, big_cost=100, rest_price=100,
                         peak_ratios={"BIG.NS": 0.88})
        big = rows["BIG.NS"]
        self.assertEqual(big["status"], "over")
        self.assertEqual(big["action"], "HOLD")
        self.assertTrue(big["suppressed_trim"])
        self.assertIn("below its own 12-month high", big["reason"])

    def test_a_holding_still_near_its_high_is_trimmed(self):
        # Within the band, so the sale is early and the ceiling still applies.
        big = self.plan(big_price=300, big_cost=100, rest_price=100,
                        peak_ratios={"BIG.NS": 0.99})["BIG.NS"]
        self.assertEqual(big["action"], "TRIM")
        self.assertGreater(big["units_sold"], 0)

    def test_the_peak_rule_wins_over_the_cost_rule(self):
        # Up 200% on cost but far off its high: the cost rule would sell, the
        # peak rule holds. The backtest says the peak rule is the one to trust,
        # so when both are available it decides.
        big = self.plan(big_price=300, big_cost=100, rest_price=100,
                        peak_ratios={"BIG.NS": 0.70})["BIG.NS"]
        self.assertGreater(big["gain_pct"], 0)
        self.assertEqual(big["action"], "HOLD")
        self.assertIn("12-month high", big["reason"])

    def test_the_cost_rule_only_applies_when_no_peak_is_known(self):
        # Weak but free. With a peak supplied it must not double-decide.
        down = self.plan(big_price=95, big_cost=100, rest_price=40)["BIG.NS"]
        self.assertEqual(down["action"], "HOLD")
        self.assertIn("other holdings falling", down["reason"])
        known = self.plan(big_price=95, big_cost=100, rest_price=40,
                          peak_ratios={"BIG.NS": 0.99})["BIG.NS"]
        self.assertEqual(known["action"], "TRIM")

    def test_a_preset_without_the_guard_still_trims_a_loser(self):
        # S10 was measured WITHOUT the guard, so it must not quietly acquire
        # one — the 15.97% printed beside it describes the unguarded rule.
        rows = self.plan(big_price=95, big_cost=100, rest_price=40,
                         strategy="S10")
        self.assertEqual(rows["BIG.NS"]["action"], "TRIM")

    def test_a_holding_with_no_cost_basis_keeps_the_old_behaviour(self):
        # Unknown return is not evidence of a loss, so the band still applies.
        stocks = [{"symbol": "BIG.NS", "name": "Big", "shares": 1000,
                   "current_price": 300, "total_value": 300000}]
        stocks += [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 1000,
                    "current_price": 100, "total_value": 100000,
                    "avg_cost": 100, "invested": 100000} for i in range(4)]
        rows = {a["key"]: a for a in re.build_plan(
            as_of=TODAY, stocks=stocks, txns_by_symbol={},
            max_weight_pct=20, long_term_only=False)["actions"]}
        self.assertEqual(rows["BIG.NS"]["action"], "TRIM")


class SettledLedgerTestCase(unittest.TestCase):
    """The AFTER half of each row: what the trade leaves behind.

    The plan decides every row against the book as it stands now, so the
    weights it quotes are opening weights. These pin the closing side, which
    is computed by replaying the trades in `_settle`.
    """

    def plan(self, **kw):
        stocks = [{"symbol": "BIG.NS", "name": "Big", "shares": 1000,
                   "avg_cost": 50, "current_price": 300,
                   "total_value": 300000, "invested": 50000}]
        stocks += [{"symbol": f"S{i}.NS", "name": f"S{i}", "shares": 700,
                    "avg_cost": 90, "current_price": 100,
                    "total_value": 70000, "invested": 63000}
                   for i in range(9)]
        return re.build_plan(as_of=TODAY, stocks=stocks, txns_by_symbol={},
                             max_weight_pct=10, long_term_only=False, **kw)

    def rows(self, **kw):
        return {a["key"]: a for a in self.plan(**kw)["actions"]}

    def test_closing_weights_total_one_hundred_per_category(self):
        by_cat = {}
        for a in self.plan()["actions"]:
            by_cat.setdefault(a["category"], []).append(a)
        for cat, rows in by_cat.items():
            priced = [r for r in rows if r["tradable"]]
            if not priced:
                continue
            with self.subTest(cat):
                self.assertAlmostEqual(
                    sum(r["weight_after_pct"] for r in priced), 100.0, places=1)

    def test_a_trim_reduces_the_holding_and_pays_cash_in(self):
        big = self.rows()["BIG.NS"]
        self.assertEqual(big["action"], "TRIM")
        self.assertGreater(big["units_sold"], 0)
        self.assertEqual(big["units_bought"], 0)
        self.assertAlmostEqual(big["held_after"],
                               big["held_units"] - big["units_sold"], places=4)
        self.assertGreater(big["net_cash"], 0)

    def test_stock_trades_are_whole_shares(self):
        # A plan that says "sell 693.33 shares" cannot be executed.
        for a in self.plan()["actions"]:
            if a["category"] != re.CAT_STOCKS:
                continue
            with self.subTest(a["key"]):
                self.assertEqual(a["units_sold"], int(a["units_sold"]))
                self.assertEqual(a["units_bought"], int(a["units_bought"]))

    def test_fund_units_stay_fractional(self):
        funds = [{"scheme_name": "Alpha Fund", "units": 1234.567, "nav": 243.0,
                  "current_value": 300000, "invested": 250000},
                 {"scheme_name": "Beta Fund", "units": 500.0, "nav": 140.0,
                  "current_value": 70000, "invested": 70000}]
        plan = re.build_plan(as_of=TODAY, stocks=[], funds=funds,
                             txns_by_symbol={}, max_weight_pct=10,
                             long_term_only=False)
        rows = [a for a in plan["actions"] if a["action"] == "TRIM"]
        self.assertTrue(rows, "expected the oversized fund to be trimmed")
        self.assertNotEqual(rows[0]["units_sold"], int(rows[0]["units_sold"]))

    def test_nothing_is_sold_beyond_what_is_held(self):
        for a in self.plan()["actions"]:
            with self.subTest(a["key"]):
                self.assertLessEqual(a["units_sold"], a["held_units"])
                self.assertGreaterEqual(a["held_after"], 0)

    def test_a_suppressed_trim_leaves_the_holding_untouched(self):
        # S1 never sells. The breach is still reported, but the closing state
        # has to match the action actually proposed, not the one cancelled.
        big = self.rows(strategy="S1")["BIG.NS"]
        self.assertEqual(big["action"], "HOLD")
        self.assertEqual(big["units_sold"], 0)
        self.assertEqual(big["held_after"], big["held_units"])
        self.assertEqual(big["net_cash"], 0)

    def test_a_hold_moves_no_units_but_its_weight_still_shifts(self):
        # Trimming BIG shrinks the book, so every untouched holding finishes
        # at a HIGHER weight than it opened. A closing weight copied from the
        # opening one would hide that entirely.
        rows = self.rows()
        self.assertEqual(rows["BIG.NS"]["action"], "TRIM")
        quiet = rows["S0.NS"]
        self.assertEqual(quiet["units_sold"], 0)
        self.assertEqual(quiet["units_bought"], 0)
        self.assertEqual(quiet["held_after"], quiet["held_units"])
        self.assertGreater(quiet["weight_after_pct"], quiet["weight_pct"])

    def test_a_contribution_is_reported_as_placed_plus_left_over(self):
        plan = self.plan(new_money=10000)
        c = plan["contribution"]
        self.assertEqual(c["amount"], 10000)
        self.assertAlmostEqual(c["deployed"] + c["left"], 10000, places=0)
        self.assertGreater(c["positions"], 0)

    def test_no_contribution_leaves_the_band_plan_untouched(self):
        # Every caller that predates contributions must see what it always saw.
        before = {a["key"]: (a["action"], a["units"]) for a in self.plan()["actions"]}
        after = {a["key"]: (a["action"], a["units"])
                 for a in self.plan(new_money=0)["actions"]}
        self.assertEqual(before, after)
        self.assertEqual(self.plan()["contribution"]["deployed"], 0.0)

    def test_the_contribution_never_overspends(self):
        for money in (1000, 5000, 100000):
            plan = self.plan(new_money=money)
            spent = sum(a["units_bought"] * a["price"] for a in plan["actions"])
            with self.subTest(money=money):
                self.assertLessEqual(round(spent, 2), money)
                self.assertGreaterEqual(plan["contribution"]["left"], -1e-6)

    def test_a_contribution_buys_whole_shares_only(self):
        for a in self.plan(new_money=10000)["actions"]:
            if a["category"] == re.CAT_STOCKS:
                with self.subTest(a["key"]):
                    self.assertEqual(a["units_bought"], int(a["units_bought"]))

    def test_a_tilt_concentrates_where_gap_filling_spreads(self):
        # S5 feeds winners, S9 feeds losers, S2 fills the biggest shortfalls.
        # If all three placed the money identically the preset would be a label
        # rather than a rule.
        def funded(sid):
            return {a["name"] for a in self.plan(strategy=sid, new_money=10000)
                    ["actions"] if a["units_bought"] > 0}
        gap, best, worst = funded("S2"), funded("S5"), funded("S9")
        self.assertTrue(best)
        self.assertTrue(worst)
        self.assertNotEqual(best, worst)
        self.assertNotEqual(best, gap)
        self.assertLessEqual(len(best), re.TILT_PICKS)
        self.assertLessEqual(len(worst), re.TILT_PICKS)

    def test_a_tilt_picks_by_return_not_by_shortfall(self):
        rows = {a["name"]: a for a in self.plan(new_money=10000)["actions"]}
        best = max(rows.values(), key=lambda r: r["gain_pct"])
        funded = {a["name"] for a in self.plan(strategy="S5", new_money=10000)
                  ["actions"] if a["units_bought"] > 0}
        self.assertIn(best["name"], funded)

    def test_a_contribution_never_buys_what_it_is_also_selling(self):
        for a in self.plan(strategy="CUSTOM", new_money=50000)["actions"]:
            with self.subTest(a["key"]):
                self.assertFalse(a["units_bought"] > 0 and a["units_sold"] > 0)

    def test_sold_percentage_matches_the_units(self):
        for a in self.plan()["actions"]:
            if not a["held_units"]:
                continue
            with self.subTest(a["key"]):
                self.assertAlmostEqual(
                    a["sold_pct_of_held"],
                    a["units_sold"] / a["held_units"] * 100.0, places=2)


if __name__ == "__main__":
    unittest.main()
