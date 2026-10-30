import unittest
from datetime import date

import rebalance_engine as re


class TestFundTaxCharacter(unittest.TestCase):
    def test_equity_categories(self):
        for cat in ("Large Cap", "Flexi Cap Fund", "ELSS", "Nifty 50 Index"):
            self.assertTrue(re.is_equity_oriented(cat), cat)

    def test_non_equity_categories(self):
        for cat in ("Liquid Fund", "Gilt", "Gold ETF FoF", "Corporate Bond"):
            self.assertFalse(re.is_equity_oriented(cat), cat)

    def test_international_is_not_equity_for_tax(self):
        # Equity-like in the allocation chart, debt-like in the Act. Getting
        # this wrong understates the tax by more than half.
        self.assertFalse(re.is_equity_oriented("International Equity"))
        self.assertFalse(re.is_equity_oriented("US Nasdaq 100 FoF"))

    def test_holding_horizon_follows_the_character(self):
        self.assertEqual(re.long_term_days(True), 365)
        self.assertEqual(re.long_term_days(False), 730)


class TestCapitalGainsTax(unittest.TestCase):
    def test_short_term_equity_is_twenty_percent(self):
        t = re.capital_gains_tax(100000, long_term=False, equity=True,
                                 exemption_left=re.EQUITY_LTCG_EXEMPT)
        self.assertEqual(t["base"], 20000.0)
        self.assertEqual(t["cess"], 800.0)
        self.assertEqual(t["total"], 20800.0)
        # The long-term exemption must not be spent on a short-term gain.
        self.assertEqual(t["exemption_used"], 0.0)

    def test_long_term_equity_consumes_the_exemption(self):
        t = re.capital_gains_tax(200000, long_term=True, equity=True,
                                 exemption_left=re.EQUITY_LTCG_EXEMPT)
        self.assertEqual(t["exemption_used"], 125000.0)
        self.assertEqual(t["taxable"], 75000.0)
        self.assertEqual(t["base"], 9375.0)
        self.assertEqual(t["total"], 9750.0)

    def test_a_fully_exempt_gain_costs_nothing(self):
        t = re.capital_gains_tax(100000, long_term=True, equity=True,
                                 exemption_left=re.EQUITY_LTCG_EXEMPT)
        self.assertEqual(t["total"], 0.0)
        self.assertEqual(t["exemption_used"], 100000.0)

    def test_non_equity_short_term_is_thirty_percent(self):
        t = re.capital_gains_tax(100000, long_term=False, equity=False)
        self.assertEqual(t["base"], 30000.0)

    def test_a_loss_is_reported_not_taxed(self):
        t = re.capital_gains_tax(-5000, long_term=True, equity=True)
        self.assertEqual(t["total"], 0.0)
        self.assertTrue(t["is_loss"])

    def test_surcharge_applies_above_fifty_lakh_and_is_capped(self):
        small = re.capital_gains_tax(1000000, long_term=False, equity=True)
        self.assertEqual(small["surcharge"], 0.0)
        mid = re.capital_gains_tax(6000000, long_term=False, equity=True)
        self.assertGreater(mid["surcharge"], 0.0)
        big = re.capital_gains_tax(20000000, long_term=False, equity=True)
        self.assertAlmostEqual(
            big["surcharge"] / big["base"] * 100, re.SURCHARGE_CAP_PCT, places=6)

    def test_nri_tax_is_withheld_not_billed(self):
        nri = re.capital_gains_tax(50000, long_term=False, equity=True,
                                   residency=re.NRI)
        resident = re.capital_gains_tax(50000, long_term=False, equity=True,
                                        residency=re.RESIDENT)
        self.assertTrue(nri["withheld_at_source"])
        self.assertFalse(resident["withheld_at_source"])
        self.assertEqual(nri["total"], resident["total"])


class TestOpenLots(unittest.TestCase):
    TXNS = [
        {"date": "2023-01-10", "type": "BUY", "qty": 100, "price": 100},
        {"date": "2024-06-01", "type": "BUY", "qty": 50, "price": 200},
        {"date": "2024-09-01", "type": "SELL", "qty": 60, "price": 250},
    ]

    def test_fifo_consumes_the_oldest_buy_first(self):
        lots = re.open_lots(self.TXNS, date(2026, 9, 9))
        self.assertEqual(len(lots), 2)
        self.assertEqual(lots[0]["qty"], 40.0)
        self.assertEqual(lots[0]["price"], 100.0)
        self.assertEqual(lots[1]["qty"], 50.0)

    def test_holding_period_decides_long_term(self):
        lots = re.open_lots(
            [{"date": "2026-06-01", "type": "BUY", "qty": 10, "price": 100},
             {"date": "2024-01-01", "type": "BUY", "qty": 10, "price": 100}],
            date(2026, 9, 9))
        by_date = {l["date"]: l for l in lots}
        self.assertFalse(by_date["2026-06-01"]["long_term"])
        self.assertTrue(by_date["2024-01-01"]["long_term"])

    def test_days_to_long_term_counts_down(self):
        lots = re.open_lots(
            [{"date": "2025-09-09", "type": "BUY", "qty": 10, "price": 100}],
            date(2026, 9, 8))
        self.assertEqual(lots[0]["days_held"], 364)
        self.assertEqual(lots[0]["days_to_long_term"], 2)

    def test_undated_rows_are_dropped_not_guessed(self):
        lots = re.open_lots(
            [{"date": "", "type": "BUY", "qty": 10, "price": 100},
             {"date": "2024-01-01", "type": "BUY", "qty": 5, "price": 100}],
            date(2026, 9, 9))
        self.assertEqual(len(lots), 1)
        self.assertEqual(lots[0]["qty"], 5.0)

    def test_mf_rows_without_a_side_read_redemptions(self):
        lots = re.open_lots(
            [{"date": "2023-01-01", "units": 100, "nav": 10, "invested": 1000},
             {"date": "2024-01-01", "units": 40, "nav": 20, "redeemed": 800}],
            date(2026, 9, 9))
        self.assertEqual(lots[0]["qty"], 60.0)

    def test_a_synthetic_lot_assumes_short_term(self):
        lots = re.synthetic_lot(10, 100, date(2026, 9, 9))
        self.assertFalse(lots[0]["long_term"])
        self.assertTrue(lots[0]["assumed"])


class TestLotSale(unittest.TestCase):
    def lots(self):
        return re.open_lots(
            [{"date": "2023-01-01", "type": "BUY", "qty": 100, "price": 100},
             {"date": "2026-08-01", "type": "BUY", "qty": 100, "price": 180}],
            date(2026, 9, 9))

    def test_long_term_units_are_spent_first(self):
        sale = re.plan_lot_sale(self.lots(), 50, 200, equity=True,
                                residency=re.NRI, exemption_left=0)
        self.assertEqual(len(sale["lots"]), 1)
        self.assertTrue(sale["lots"][0]["long_term"])
        self.assertEqual(sale["lots"][0]["lot_date"], "2023-01-01")

    def test_spilling_into_short_term_costs_the_higher_rate(self):
        sale = re.plan_lot_sale(self.lots(), 150, 200, equity=True,
                                residency=re.NRI, exemption_left=0)
        self.assertEqual(len(sale["lots"]), 2)
        long_leg, short_leg = sale["lots"]
        self.assertGreater(short_leg["gain"], 0)
        # 50 short-term units at a ₹20 gain taxed at 20% + cess.
        self.assertAlmostEqual(short_leg["gain"], 1000.0, places=2)
        self.assertAlmostEqual(short_leg["tax"], 208.0, places=2)
        self.assertGreater(long_leg["gain"], short_leg["gain"])

    def test_net_proceeds_are_after_tax(self):
        sale = re.plan_lot_sale(self.lots(), 50, 200, equity=True,
                                residency=re.NRI, exemption_left=0)
        self.assertEqual(sale["proceeds"], 10000.0)
        self.assertAlmostEqual(sale["net_proceeds"],
                               sale["proceeds"] - sale["tax"], places=2)

    def test_a_nearly_mature_lot_is_flagged_as_deferrable(self):
        lots = re.open_lots(
            [{"date": "2025-09-20", "type": "BUY", "qty": 100, "price": 100}],
            date(2026, 9, 9))
        sale = re.plan_lot_sale(lots, 50, 200, equity=True, residency=re.NRI,
                                exemption_left=0)
        self.assertEqual(sale["deferrable_units"], 50.0)
        self.assertEqual(sale["days_to_defer"], 12)

    def test_asking_for_more_units_than_are_held_reports_the_shortfall(self):
        sale = re.plan_lot_sale(self.lots(), 500, 200, equity=True,
                                residency=re.NRI, exemption_left=0)
        self.assertEqual(sale["units"], 200.0)
        self.assertEqual(sale["units_short"], 300.0)

    def test_the_exemption_is_spent_once_across_lots(self):
        sale = re.plan_lot_sale(self.lots(), 100, 200, equity=True,
                                residency=re.NRI,
                                exemption_left=re.EQUITY_LTCG_EXEMPT)
        # A ₹10,000 long-term gain sits well inside the allowance.
        self.assertEqual(sale["tax"], 0.0)
        self.assertEqual(sale["exemption_left"], 115000.0)


class TestMarketBoom(unittest.TestCase):
    def tape(self, **lead):
        row = {"symbol": "^NSEI", "label": "NIFTY 50", "status": "ok",
               "off_high_pct": 1.0, "rsi_14": 75.0, "vs_dma_200_pct": 15.0,
               "chg_1y_pct": 25.0}
        row.update(lead)
        return {"indices": [row]}

    def test_a_hot_market_is_a_boom(self):
        boom = re.market_boom(self.tape())
        self.assertTrue(boom["boom"])
        self.assertGreaterEqual(boom["score"], re.BOOM_SIGNALS_REQUIRED)

    def test_a_calm_market_is_not(self):
        boom = re.market_boom(self.tape(
            off_high_pct=12.0, rsi_14=42.0, vs_dma_200_pct=-3.0, chg_1y_pct=2.0))
        self.assertFalse(boom["boom"])
        self.assertEqual(boom["heat"], "calm")

    def test_two_signals_is_warm_not_boom(self):
        # Off its high by 12%, so neither the high signal nor breadth can fire;
        # only RSI and the 200 DMA stretch are left.
        boom = re.market_boom(self.tape(
            off_high_pct=12.0, chg_1y_pct=3.0))
        self.assertEqual(boom["score"], 2)
        self.assertFalse(boom["boom"])
        self.assertEqual(boom["heat"], "warm")

    def test_missing_data_is_unknown_not_calm(self):
        # A dead feed must never read as "the market is fine", which would
        # silently suppress a trigger the user asked for.
        boom = re.market_boom({"indices": [{"symbol": "^NSEI", "status": "unavailable"}]})
        self.assertFalse(boom["available"])
        self.assertEqual(boom["heat"], "unknown")
        self.assertFalse(boom["boom"])

    def test_an_unreadable_signal_is_not_counted_as_a_hit(self):
        boom = re.market_boom(self.tape(rsi_14=None, vs_dma_200_pct=None))
        self.assertEqual(boom["known_signals"], 3)
        names = {s["name"]: s for s in boom["signals"]}
        self.assertFalse(names["overbought"]["known"])
        self.assertFalse(names["overbought"]["hit"])

    def test_breadth_reads_the_whole_tape(self):
        rows = [{"symbol": f"IDX{i}", "status": "ok", "off_high_pct": 1.0}
                for i in range(9)]
        rows.append({"symbol": "^NSEI", "label": "NIFTY 50", "status": "ok",
                     "off_high_pct": 1.0, "rsi_14": 50.0,
                     "vs_dma_200_pct": 1.0, "chg_1y_pct": 1.0})
        boom = re.market_boom({"indices": rows})
        names = {s["name"]: s for s in boom["signals"]}
        self.assertTrue(names["broad_participation"]["hit"])

    def test_ytd_stands_in_when_the_year_is_unknown(self):
        boom = re.market_boom(self.tape(chg_1y_pct=None, chg_ytd_pct=30.0))
        names = {s["name"]: s for s in boom["signals"]}
        self.assertTrue(names["strong_year"]["hit"])


class TestTriggers(unittest.TestCase):
    def test_no_history_is_a_first_run(self):
        t = re.due_triggers(date(2026, 9, 9))
        self.assertTrue(t["due"])
        self.assertEqual(t["fired"][0]["name"], "first_run")

    def test_semiannual_fires_after_the_window(self):
        t = re.due_triggers(date(2026, 9, 9), last_rebalanced="2026-01-01")
        self.assertTrue(t["due"])
        self.assertIn("calendar_semiannual", [f["name"] for f in t["fired"]])

    def test_annual_does_not_fire_at_six_months(self):
        t = re.due_triggers(date(2026, 9, 9), last_rebalanced="2026-06-01",
                            cadence="annual")
        self.assertFalse(t["due"])
        self.assertEqual(t["next_calendar_due"], "2027-06-01")

    def test_a_boom_opens_the_book_off_schedule(self):
        t = re.due_triggers(date(2026, 9, 9), last_rebalanced="2026-08-01",
                            boom={"boom": True, "reason": "hot"})
        self.assertTrue(t["due"])
        self.assertIn("market_boom", [f["name"] for f in t["fired"]])

    def test_a_band_breach_opens_it_too(self):
        t = re.due_triggers(date(2026, 9, 9), last_rebalanced="2026-08-01",
                            breaches=2)
        self.assertTrue(t["due"])
        self.assertIn("band_breach", [f["name"] for f in t["fired"]])

    def test_maturity_is_its_own_trigger(self):
        t = re.due_triggers(date(2026, 9, 9), last_rebalanced="2026-08-01",
                            matured=1)
        self.assertIn("holding_matured", [f["name"] for f in t["fired"]])

    def test_a_quiet_in_window_portfolio_is_not_due(self):
        t = re.due_triggers(date(2026, 9, 9), last_rebalanced="2026-08-01")
        self.assertFalse(t["due"])
        self.assertEqual(t["fired"], [])


def _pos(key, value, price, lots):
    return {"key": key, "name": key, "value": value, "price": price,
            "units": value / price, "lots": lots}


def _lt_lots(qty, price, as_of=date(2026, 9, 9)):
    return re.open_lots(
        [{"date": "2020-01-01", "type": "BUY", "qty": qty, "price": price}],
        as_of)


def _filler(count, value, price=100):
    """Positions that all sit inside the band.

    Without these a two-name sleeve makes the counterweight 95% of itself, so
    every fixture would breach its own ceiling and no test could isolate the
    one position it is actually about.
    """
    return [_pos(f"FILL{i}", value, price, _lt_lots(value / price, price * 0.5))
            for i in range(count)]


class TestSleevePlan(unittest.TestCase):
    def lt_lots(self, qty, price):
        return _lt_lots(qty, price)

    def test_a_position_over_the_ceiling_is_trimmed_to_it(self):
        plan = re.plan_sleeve([
            _pos("BIG", 300000, 100, self.lt_lots(3000, 50)),
        ] + _filler(10, 70000), as_of=date(2026, 9, 9), sleeve="stocks",
            exemption_left=0)
        big = plan["actions"][0]
        self.assertEqual(big["action"], "TRIM")
        self.assertEqual(big["weight_pct"], 30.0)
        # 30% of a ₹10L sleeve down to 10% is ₹2L off the table.
        self.assertEqual(big["amount"], 200000.0)

    def test_a_position_under_the_floor_is_topped_up(self):
        plan = re.plan_sleeve([
            _pos("TINY", 10000, 100, self.lt_lots(100, 50)),
        ] + _filler(10, 99000), as_of=date(2026, 9, 9), sleeve="stocks",
            exemption_left=0)
        tiny = plan["actions"][0]
        self.assertEqual(tiny["action"], "ADD")
        self.assertEqual(tiny["amount"], 10000.0)
        # Adding money realises nothing, so there is no tax leg at all.
        self.assertNotIn("tax", tiny)

    def test_a_position_inside_the_band_is_left_alone(self):
        plan = re.plan_sleeve([
            _pos("OK", 50000, 100, self.lt_lots(500, 50)),
        ] + _filler(10, 95000), as_of=date(2026, 9, 9), sleeve="stocks",
            exemption_left=0)
        self.assertEqual(plan["actions"][0]["action"], "HOLD")
        self.assertEqual(plan["actions"][0]["status"], "within")
        self.assertEqual(plan["breaches"], 0)

    def test_a_hair_over_the_edge_is_not_a_trade(self):
        # 10.1% is inside the tolerance; proposing a trade here would churn
        # the book every time a price ticked.
        plan = re.plan_sleeve([
            _pos("EDGE", 101000, 100, self.lt_lots(1010, 50)),
        ] + _filler(10, 89900), as_of=date(2026, 9, 9), sleeve="stocks",
            exemption_left=0)
        self.assertEqual(plan["actions"][0]["status"], "within")

    def test_a_breach_too_small_to_trade_is_held(self):
        plan = re.plan_sleeve([
            _pos("SMALL", 1000, 100, self.lt_lots(10, 50)),
        ] + _filler(10, 9900), as_of=date(2026, 9, 9), sleeve="stocks",
            exemption_left=0)
        small = plan["actions"][0]
        self.assertEqual(small["status"], "under")
        self.assertEqual(small["action"], "HOLD")
        self.assertIn("too small", small["reason"])

    def test_the_trim_reports_its_tax_and_net_proceeds(self):
        plan = re.plan_sleeve([
            _pos("BIG", 300000, 100, self.lt_lots(3000, 50)),
        ] + _filler(10, 70000), as_of=date(2026, 9, 9), sleeve="stocks",
            exemption_left=0)
        big = plan["actions"][0]
        # 2000 long-term units sold at ₹100 against a ₹50 cost = ₹1L gain.
        self.assertEqual(big["units"], 2000.0)
        self.assertEqual(big["gain"], 100000.0)
        self.assertAlmostEqual(big["tax"], 13000.0, places=2)
        self.assertAlmostEqual(big["net_proceeds"], 187000.0, places=2)

    def test_an_empty_sleeve_does_not_divide_by_zero(self):
        plan = re.plan_sleeve([], as_of=date(2026, 9, 9), sleeve="stocks")
        self.assertEqual(plan["total_value"], 0.0)
        self.assertEqual(plan["actions"], [])


class TestBuildPlan(unittest.TestCase):
    AS_OF = date(2026, 9, 9)

    STOCKS = [
        {"symbol": "BIG.NS", "name": "Big", "shares": 3000, "avg_cost": 50,
         "current_price": 100, "total_value": 300000},
        {"symbol": "MID.NS", "name": "Mid", "shares": 600, "avg_cost": 90,
         "current_price": 100, "total_value": 60000},
        {"symbol": "TINY.NS", "name": "Tiny", "shares": 100, "avg_cost": 90,
         "current_price": 100, "total_value": 10000},
    ] + [
        {"symbol": f"F{i}.NS", "name": f"F{i}", "shares": 660, "avg_cost": 90,
         "current_price": 100, "total_value": 66000}
        for i in range(10)
    ]
    TXNS = {
        s["symbol"]: [{"date": "2020-01-01", "type": "BUY",
                       "qty": s["shares"], "price": s["avg_cost"]}]
        for s in STOCKS
    }

    def plan(self, **kw):
        kw.setdefault("stocks", self.STOCKS)
        kw.setdefault("txns_by_symbol", self.TXNS)
        kw.setdefault("as_of", self.AS_OF)
        kw.setdefault("exemption_left", 0)
        return re.build_plan(**kw)

    def test_the_plan_trims_the_overweight_and_tops_up_the_underweight(self):
        p = self.plan()
        by_key = {a["key"]: a for a in p["actions"]}
        self.assertEqual(by_key["BIG.NS"]["action"], "TRIM")
        self.assertEqual(by_key["TINY.NS"]["action"], "ADD")
        self.assertEqual(by_key["MID.NS"]["action"], "HOLD")

    def test_totals_are_net_of_tax(self):
        p = self.plan()
        t = p["totals"]
        self.assertGreater(t["tax_estimated"], 0)
        self.assertAlmostEqual(
            t["net_proceeds"], t["sell_value"] - t["tax_estimated"], places=2)
        self.assertAlmostEqual(
            t["cash_after_plan"], t["net_proceeds"] - t["buy_value"], places=2)

    def test_a_boom_appears_in_the_triggers(self):
        tape = {"indices": [{"symbol": "^NSEI", "label": "NIFTY 50",
                             "status": "ok", "off_high_pct": 0.5,
                             "rsi_14": 78.0, "vs_dma_200_pct": 18.0,
                             "chg_1y_pct": 30.0}]}
        p = self.plan(tape=tape, last_rebalanced="2026-08-15")
        self.assertTrue(p["market"]["boom"])
        self.assertIn("market_boom", [f["name"] for f in p["triggers"]["fired"]])

    def test_funds_are_banded_in_their_own_sleeve(self):
        funds = [
            {"scheme_name": "Big Fund", "category": "Flexi Cap", "units": 1000,
             "nav": 300, "current_value": 300000,
             "transactions": [{"date": "2020-01-01", "units": 1000, "nav": 150}]},
        ] + [
            {"scheme_name": f"Fund {i}", "category": "Large Cap", "units": 700,
             "nav": 100, "current_value": 70000,
             "transactions": [{"date": "2020-01-01", "units": 700, "nav": 90}]}
            for i in range(10)
        ]
        p = self.plan(stocks=[], txns_by_symbol={}, funds=funds)
        by_key = {a["key"]: a for a in p["actions"]}
        self.assertEqual(by_key["Big Fund"]["action"], "TRIM")
        self.assertEqual(by_key["Big Fund"]["sleeve"], re.CAT_FUNDS)
        self.assertEqual(by_key["Fund 0"]["action"], "HOLD")

    def test_a_non_equity_fund_keeps_its_tax_character(self):
        funds = [
            {"scheme_name": "Gold FoF", "category": "Gold", "units": 1000,
             "nav": 300, "current_value": 300000,
             "transactions": [{"date": "2020-01-01", "units": 1000, "nav": 150}]},
            {"scheme_name": "Rest Fund", "category": "Large Cap", "units": 7000,
             "nav": 100, "current_value": 700000,
             "transactions": [{"date": "2020-01-01", "units": 7000, "nav": 90}]},
        ]
        p = self.plan(stocks=[], txns_by_symbol={}, funds=funds)
        by_key = {a["key"]: a for a in p["actions"]}
        self.assertFalse(by_key["Gold FoF"]["equity_for_tax"])
        self.assertTrue(by_key["Rest Fund"]["equity_for_tax"])

    def test_a_non_equity_fund_is_taxed_at_its_own_rate(self):
        # The character must reach the SALE, not just the label on the row.
        # Held since 2020, so long-term either way — but a gold fund needs 24
        # months, and both legs happen to clear it here; what differs is that
        # nothing about it may be priced through the equity exemption.
        # Every fund here is a GOLD fund, because the band is enforced within
        # a category: a lone gold holding is 100% of the gold sleeve by
        # construction and correctly proposes no trade at all.
        funds = [
            {"scheme_name": "Gold FoF", "category": "Gold", "units": 1000,
             "nav": 300, "current_value": 300000,
             "transactions": [{"date": "2026-06-01", "units": 1000, "nav": 150}]},
        ] + [
            {"scheme_name": f"Gold Fund {i}", "category": "Gold ETF FoF",
             "units": 700, "nav": 100, "current_value": 70000,
             "transactions": [{"date": "2026-06-01", "units": 700, "nav": 90}]}
            for i in range(10)
        ]
        p = self.plan(stocks=[], txns_by_symbol={}, funds=funds)
        gold = next(a for a in p["actions"] if a["key"] == "Gold FoF")
        self.assertFalse(gold["equity_for_tax"])
        self.assertEqual(gold["action"], "TRIM")
        # 30% of a ₹10L GOLD sleeve trimmed to 10% sells ₹2L, which at NAV 300
        # is 666.67 units carrying a ₹150 gain each.
        self.assertEqual(gold["amount"], 200000.0)
        self.assertEqual(gold["gain"], 100000.0)
        expected = re.capital_gains_tax(
            100000.0, long_term=False, equity=False)["total"]
        self.assertAlmostEqual(gold["tax"], expected, places=2)
        # Non-equity short-term is 30%, not the 20% an equity fund would pay.
        self.assertGreater(
            gold["tax"],
            re.capital_gains_tax(100000.0, long_term=False, equity=True)["total"])

    def test_a_ledger_that_disagrees_with_the_holding_is_not_trusted(self):
        # The ledger says 10 shares, the holding says 3000. Believing it would
        # tax 2990 units that have no purchase date behind them.
        p = self.plan(txns_by_symbol={
            "BIG.NS": [{"date": "2020-01-01", "type": "BUY", "qty": 10, "price": 50}],
            "MID.NS": self.TXNS["MID.NS"],
            "TINY.NS": self.TXNS["TINY.NS"],
        })
        big = next(a for a in p["actions"] if a["key"] == "BIG.NS")
        self.assertFalse(big["has_long_term_units"])

    def test_the_policy_is_reported_with_the_plan(self):
        p = self.plan()
        self.assertEqual(p["policy"]["min_weight_pct"], 2.0)
        self.assertEqual(p["policy"]["max_weight_pct"], 10.0)
        self.assertEqual(p["residency"], re.NRI)

    def test_an_empty_portfolio_is_a_plan_with_no_actions(self):
        p = re.build_plan(stocks=[], funds=[], as_of=self.AS_OF)
        self.assertEqual(p["actions"], [])
        self.assertEqual(p["totals"]["sell_value"], 0.0)

    def test_strategy_notes_flag_a_plan_that_needs_new_money(self):
        # Two positions under the floor and nothing over the ceiling: there is
        # nothing to sell, so the top-ups can only come from new money.
        stocks = [
            {"symbol": "A.NS", "shares": 50, "avg_cost": 100,
             "current_price": 100, "total_value": 5000},
            {"symbol": "B.NS", "shares": 50, "avg_cost": 100,
             "current_price": 100, "total_value": 5000},
        ] + [
            {"symbol": f"F{i}.NS", "shares": 495, "avg_cost": 100,
             "current_price": 100, "total_value": 49500}
            for i in range(20)
        ]
        p = self.plan(stocks=stocks, txns_by_symbol={})
        self.assertEqual(p["totals"]["sell_value"], 0.0)
        self.assertGreater(p["totals"]["buy_value"], 0.0)
        self.assertLess(p["totals"]["cash_after_plan"], 0)
        titles = [n["title"] for n in p["strategy"]]
        self.assertIn("This plan is not self-funding", titles)
        self.assertIn("Fund the floor with new money first", titles)


if __name__ == "__main__":
    unittest.main()
