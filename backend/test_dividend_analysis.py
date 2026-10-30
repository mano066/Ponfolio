"""
Unit tests for the pure dividend-analysis layer.

    python -m unittest test_dividend_analysis -v

No network, no yfinance — every input is hand-fed so the maths is pinned down.
"""

import unittest
from datetime import date

import dividend_analysis as da


class TestHistoryHelpers(unittest.TestCase):
    def test_fiscal_year_indian_convention(self):
        self.assertEqual(da.fiscal_year(date(2026, 4, 1)), 2026)
        self.assertEqual(da.fiscal_year(date(2026, 3, 31)), 2025)
        self.assertEqual(da.fiscal_year(date(2026, 12, 15)), 2026)

    def test_normalize_history_accepts_all_three_shapes(self):
        expected = [(date(2025, 8, 1), 5.0), (date(2026, 2, 1), 7.0)]
        as_tuples = [(date(2026, 2, 1), 7.0), (date(2025, 8, 1), 5.0)]
        as_dicts = [{"date": "2025-08-01", "amount": 5.0},
                    {"date": "2026-02-01", "amount": 7.0}]
        as_map = {"2026-02-01": 7.0, "2025-08-01": 5.0}
        for shape in (as_tuples, as_dicts, as_map):
            self.assertEqual(da.normalize_history(shape), expected)

    def test_normalize_history_drops_junk_and_zeros(self):
        rows = da.normalize_history([
            ("2026-01-01", 3.0),
            ("not-a-date", 4.0),
            ("2026-02-01", 0),
            ("2026-03-01", None),
            "garbage",
        ])
        self.assertEqual(rows, [(date(2026, 1, 1), 3.0)])

    def test_normalize_history_handles_timestamp_strings(self):
        rows = da.normalize_history([("2026-05-20 00:00:00+05:30", 2.5)])
        self.assertEqual(rows, [(date(2026, 5, 20), 2.5)])

    def test_trailing_12m_sums_only_last_year(self):
        hist = [
            ("2024-07-01", 10.0),   # outside window
            ("2025-09-01", 5.0),
            ("2026-02-01", 7.5),
        ]
        self.assertEqual(da.trailing_12m_dps(hist, as_of=date(2026, 8, 1)), 12.5)

    def test_trailing_12m_defaults_to_last_payout_date(self):
        hist = [("2020-06-01", 4.0), ("2020-11-01", 6.0)]
        self.assertEqual(da.trailing_12m_dps(hist), 10.0)

    def test_trailing_12m_empty_is_zero(self):
        self.assertEqual(da.trailing_12m_dps(None), 0.0)
        self.assertEqual(da.trailing_12m_dps([]), 0.0)

    def test_dps_by_fiscal_year_groups_interim_and_final(self):
        hist = [("2025-08-01", 6.5), ("2026-03-01", 8.0), ("2026-08-01", 5.5)]
        self.assertEqual(da.dps_by_fiscal_year(hist), {2025: 14.5, 2026: 5.5})

    def test_dividend_cagr_growth(self):
        # FY2020: 10 -> FY2025: 20 over 5 completed years => ~14.87%
        hist = [(f"{y}-06-01", amt) for y, amt in
                [(2020, 10.0), (2021, 12.0), (2022, 14.0),
                 (2023, 16.0), (2024, 18.0), (2025, 20.0)]]
        self.assertAlmostEqual(
            da.dividend_cagr(hist, as_of=date(2026, 8, 5)), 14.87, places=1)

    def test_dividend_cagr_decline_is_negative(self):
        hist = [("2022-06-01", 20.0), ("2023-06-01", 14.0), ("2024-06-01", 8.0)]
        self.assertLess(da.dividend_cagr(hist, as_of=date(2026, 8, 5)), -20)

    def test_dividend_cagr_ignores_the_incomplete_current_year(self):
        """
        Real Coal India shape: seven rising completed years plus a part-year.
        Including the part-year would read as a collapse; it must not.
        """
        hist = [(f"{y}-06-01", amt) for y, amt in
                [(2019, 12.00), (2020, 12.50), (2021, 17.50), (2022, 23.25),
                 (2023, 24.50), (2024, 26.35), (2025, 26.40)]]
        hist.append(("2026-06-01", 5.50))       # FY2026 interim only, so far
        cagr = da.dividend_cagr(hist, as_of=date(2026, 8, 5))
        self.assertGreater(cagr, 0, "a rising dividend must not read as falling")
        # 5-year window: FY2020 12.50 -> FY2025 26.40 => 16.13%/yr
        self.assertAlmostEqual(cagr, 16.13, places=1)

    def test_incomplete_year_does_not_flag_an_anchor_as_a_trap(self):
        hist = [(f"{y}-06-01", amt) for y, amt in
                [(2021, 17.50), (2022, 23.25), (2023, 24.50),
                 (2024, 26.35), (2025, 26.40)]]
        hist.append(("2026-06-01", 5.50))
        row = da.build_stock_row(
            {"symbol": "COALINDIA", "shares": 100, "price": 414.0,
             "avg_cost": 375.0, "sector": "Energy"},
            {"history": hist, "payout_ratio": 52},
            as_of=date(2026, 8, 5))
        self.assertNotEqual(row["tier"], da.TIER_TRAP)
        self.assertEqual(row["tier"], da.TIER_ANCHOR)

    def test_dividend_cagr_undefined_cases_return_zero(self):
        ref = date(2026, 8, 5)
        self.assertEqual(da.dividend_cagr([], as_of=ref), 0.0)
        # One completed FY only.
        self.assertEqual(da.dividend_cagr([("2025-01-01", 5.0)], as_of=ref), 0.0)
        # Everything inside the current FY -> nothing completed to compare.
        self.assertEqual(da.dividend_cagr([("2026-06-01", 5.0)], as_of=ref), 0.0)

    def test_dividend_cagr_window_is_capped(self):
        # 10 years of history, max_years=5 must only use the last 6 FYs.
        hist = [(f"{2015 + i}-06-01", 1.0 * (i + 1)) for i in range(11)]
        ref = date(2026, 8, 5)
        capped = da.dividend_cagr(hist, max_years=5, as_of=ref)
        full = da.dividend_cagr(hist, max_years=10, as_of=ref)
        self.assertNotAlmostEqual(capped, full, places=2)

    def test_years_paid(self):
        hist = [("2024-06-01", 5.0), ("2025-06-01", 5.0), ("2025-11-01", 2.0)]
        self.assertEqual(da.years_paid(hist), 2)

    def test_payout_months_averages_across_years(self):
        hist = [("2023-06-01", 10.0), ("2024-06-01", 20.0), ("2025-06-01", 30.0)]
        months = da.payout_months(hist, lookback_years=3, as_of=date(2026, 8, 5))
        self.assertEqual(months, {6: 20.0})   # (10+20+30)/3 completed FYs

    def test_payout_months_excludes_the_partial_current_year(self):
        hist = [("2024-06-01", 10.0), ("2025-06-01", 10.0), ("2026-06-01", 3.0)]
        months = da.payout_months(hist, lookback_years=2, as_of=date(2026, 8, 5))
        self.assertEqual(months, {6: 10.0})   # part-year 3.0 must not drag it down

    def test_payout_months_keeps_part_year_for_a_recent_lister(self):
        hist = [("2026-07-01", 4.0)]
        months = da.payout_months(hist, as_of=date(2026, 8, 5))
        self.assertEqual(months, {7: 4.0})


class TestResolveDps(unittest.TestCase):
    def test_manual_override_wins(self):
        dps, src = da.resolve_dps(history=[("2026-01-01", 5.0)],
                                 info_rate=9.0, manual_override=12.0)
        self.assertEqual((dps, src), (12.0, "manual"))

    def test_history_beats_provider(self):
        dps, src = da.resolve_dps(history=[("2026-01-01", 5.0)], info_rate=9.0,
                                 as_of=date(2026, 8, 5))
        self.assertEqual((dps, src), (5.0, "history_ttm"))

    def test_last_fy_basis_survives_the_anniversary_cliff(self):
        # Interim 1 Aug 2025 + final 1 Feb 2026 = FY2025 total of 26.5.
        # On 5 Aug 2026 a strict 365-day window would see only the 5.5 final.
        hist = [("2025-08-01", 21.0), ("2026-02-01", 5.5)]
        dps, src = da.resolve_dps(history=hist, as_of=date(2026, 8, 5))
        self.assertEqual((dps, src), (26.5, "history_last_fy"))

    def test_fresh_hike_beats_the_stale_fiscal_year(self):
        # FY2025 paid 10; the new FY has already paid 18 -> take the higher.
        hist = [("2025-06-01", 10.0), ("2026-06-01", 18.0)]
        dps, src = da.resolve_dps(history=hist, as_of=date(2026, 8, 5))
        self.assertEqual((dps, src), (18.0, "history_ttm"))

    def test_stopped_paying_years_ago_is_zero_not_stale(self):
        hist = [("2019-06-01", 12.0), ("2020-06-01", 12.0)]
        dps, src = da.resolve_dps(history=hist, as_of=date(2026, 8, 5))
        self.assertEqual((dps, src), (0.0, "none"))

    def test_falls_back_to_provider_rate(self):
        dps, src = da.resolve_dps(history=[], info_rate=9.0, trailing_rate=8.0)
        self.assertEqual((dps, src), (9.0, "provider_rate"))

    def test_falls_back_to_trailing_rate(self):
        dps, src = da.resolve_dps(history=None, info_rate=0, trailing_rate=8.0)
        self.assertEqual((dps, src), (8.0, "provider_trailing"))

    def test_no_data_is_zero_payer(self):
        dps, src = da.resolve_dps()
        self.assertEqual((dps, src), (0.0, "none"))

    def test_non_numeric_provider_values_do_not_crash(self):
        dps, src = da.resolve_dps(info_rate="n/a", trailing_rate=None)
        self.assertEqual((dps, src), (0.0, "none"))


class TestClassification(unittest.TestCase):
    def test_anchor(self):
        tier, _ = da.classify_dividend(6.4, 70, 10.6, 8)
        self.assertEqual(tier, da.TIER_ANCHOR)

    def test_grower(self):
        tier, _ = da.classify_dividend(2.0, 35, 15.0, 6)
        self.assertEqual(tier, da.TIER_GROWER)

    def test_trap_on_excess_payout(self):
        tier, reason = da.classify_dividend(7.0, 130, 5.0, 6)
        self.assertEqual(tier, da.TIER_TRAP)
        self.assertIn("130%", reason)

    def test_trap_on_collapsing_dps(self):
        tier, _ = da.classify_dividend(5.5, 60, -25.0, 5)
        self.assertEqual(tier, da.TIER_TRAP)

    def test_high_yield_short_history_is_not_an_anchor(self):
        tier, _ = da.classify_dividend(6.0, 50, 0.0, 1)
        self.assertEqual(tier, da.TIER_MODEST)

    def test_zero_yield_is_non_payer(self):
        tier, _ = da.classify_dividend(0.0, 0, 0.0, 0)
        self.assertEqual(tier, da.TIER_NONE)

    def test_every_tier_has_a_label(self):
        for tier in (da.TIER_ANCHOR, da.TIER_GROWER, da.TIER_MODEST,
                     da.TIER_TRAP, da.TIER_NONE):
            self.assertIn(tier, da.TIER_LABELS)


class TestPlanDetection(unittest.TestCase):
    def test_growth_plans_do_not_distribute(self):
        for name in ["Parag Parikh Flexi Cap Growth Direct Plan",
                     "HDFC Mid Cap Opportunities - Direct Growth",
                     "SBI Gold ETF"]:
            self.assertFalse(da.is_idcw_plan(name), name)

    def test_idcw_plans_distribute(self):
        for name in ["ICICI Pru Value Discovery - IDCW",
                     "HDFC Dividend Yield Fund - Direct Payout",
                     "Aditya Birla Income Distribution cum capital withdrawal"]:
            self.assertTrue(da.is_idcw_plan(name), name)

    def test_growth_token_wins_over_dividend_token(self):
        # "Dividend Yield Fund - Growth" is a growth plan despite the word.
        self.assertFalse(da.is_idcw_plan("HDFC Dividend Yield Fund - Growth"))

    def test_blank_name_is_not_idcw(self):
        self.assertFalse(da.is_idcw_plan(""))
        self.assertFalse(da.is_idcw_plan(None))


class TestBuildStockRow(unittest.TestCase):
    def setUp(self):
        self.holding = {"symbol": "COALINDIA.NS", "shares": 100,
                        "price": 414.10, "avg_cost": 380.0, "sector": "Energy"}
        self.facts = {
            "history": [("2024-08-01", 20.0), ("2025-02-01", 5.0),
                        ("2025-08-01", 21.0), ("2026-02-01", 5.5)],
            "payout_ratio": 0.70,      # fraction from provider
        }

    def test_income_and_yield_are_derived_from_dps(self):
        row = da.build_stock_row(self.holding, self.facts, as_of=date(2026, 8, 5))
        self.assertEqual(row["dps"], 26.5)                 # FY2025: 21.0 + 5.5
        self.assertEqual(row["annual_income"], round(26.5 * 100, 2))
        self.assertAlmostEqual(row["yield_pct"], 6.4, places=1)
        self.assertAlmostEqual(row["yield_on_cost"], 6.97, places=1)
        self.assertEqual(row["symbol"], "COALINDIA")       # suffix stripped

    def test_fractional_payout_ratio_is_scaled_to_percent(self):
        row = da.build_stock_row(self.holding, self.facts)
        self.assertEqual(row["payout_ratio"], 70.0)

    def test_percent_payout_ratio_is_left_alone(self):
        row = da.build_stock_row(self.holding, {"payout_ratio": 87.0,
                                                "dividend_rate": 14.5})
        self.assertEqual(row["payout_ratio"], 87.0)

    def test_unknown_symbol_degrades_to_zero_payer(self):
        row = da.build_stock_row({"symbol": "NEWCO", "shares": 10, "price": 100})
        self.assertEqual(row["annual_income"], 0.0)
        self.assertEqual(row["tier"], da.TIER_NONE)
        self.assertEqual(row["dps_source"], "none")
        self.assertEqual(row["value"], 1000.0)

    def test_zero_price_does_not_divide_by_zero(self):
        row = da.build_stock_row({"symbol": "X", "shares": 5, "price": 0},
                                 {"dividend_rate": 2.0})
        self.assertEqual(row["yield_pct"], 0.0)
        self.assertEqual(row["annual_income"], 10.0)

    def test_explicit_value_overrides_shares_times_price(self):
        row = da.build_stock_row({"symbol": "X", "shares": 5, "price": 100,
                                  "value": 999})
        self.assertEqual(row["value"], 999.0)

    def test_tds_flag_trips_above_threshold(self):
        big = da.build_stock_row({"symbol": "X", "shares": 10_000, "price": 100},
                                 {"dividend_rate": 5.0})
        small = da.build_stock_row({"symbol": "Y", "shares": 10, "price": 100},
                                   {"dividend_rate": 5.0})
        self.assertTrue(big["tds_applicable"])
        self.assertFalse(small["tds_applicable"])


class TestBuildFundRow(unittest.TestCase):
    def test_growth_plan_income_is_not_spendable(self):
        row = da.build_fund_row(
            {"scheme_name": "Parag Parikh Flexi Cap Growth Direct Plan",
             "current_value": 500_000, "invested": 400_000},
            lookthrough_yield_pct=1.2)
        self.assertEqual(row["plan"], "Growth")
        self.assertEqual(row["cash_income"], 0.0)
        self.assertEqual(row["lookthrough_income"], 6000.0)

    def test_idcw_plan_income_counts(self):
        row = da.build_fund_row(
            {"scheme_name": "HDFC Dividend Yield - IDCW",
             "current_value": 200_000},
            lookthrough_yield_pct=3.0)
        self.assertEqual(row["plan"], "IDCW")
        self.assertEqual(row["cash_income"], 6000.0)
        self.assertEqual(row["monthly_income"], 500.0)

    def test_declared_income_overrides_estimate(self):
        row = da.build_fund_row(
            {"scheme_name": "HDFC Dividend Yield - IDCW",
             "current_value": 200_000, "declared_annual_income": 7500},
            lookthrough_yield_pct=3.0)
        self.assertEqual(row["cash_income"], 7500.0)

    def test_missing_fields_do_not_crash(self):
        row = da.build_fund_row({})
        self.assertEqual(row["value"], 0.0)
        self.assertEqual(row["cash_income"], 0.0)


class TestLookthroughYield(unittest.TestCase):
    def test_weighted_by_disclosed_weight(self):
        holdings = [{"stock": "ITC.NS", "pct": 50}, {"stock": "TCS.NS", "pct": 50}]
        y = da.lookthrough_yield(holdings, {"ITC.NS": 5.0, "TCS.NS": 1.0})
        self.assertEqual(y, 3.0)

    def test_suffix_stripped_symbols_also_match(self):
        holdings = [{"stock": "ITC.NS", "pct": 100}]
        self.assertEqual(da.lookthrough_yield(holdings, {"ITC": 5.0}), 5.0)

    def test_unknown_holdings_dilute_rather_than_inflate(self):
        holdings = [{"stock": "ITC.NS", "pct": 50}, {"stock": "MYSTERY.NS", "pct": 50}]
        self.assertEqual(da.lookthrough_yield(holdings, {"ITC.NS": 5.0}), 2.5)

    def test_no_holdings_is_zero(self):
        self.assertEqual(da.lookthrough_yield([], {}), 0.0)
        self.assertEqual(da.lookthrough_yield(None, {"ITC": 5}), 0.0)


class TestCorpusLadder(unittest.TestCase):
    def test_corpus_is_goal_over_yield(self):
        ladder = da.corpus_required(120_000, rungs=(4.0,))
        self.assertEqual(ladder[0]["corpus_required"], 3_000_000.0)

    def test_ladder_is_monotonically_cheaper_as_yield_rises(self):
        ladder = da.corpus_required(120_000)
        values = [r["corpus_required"] for r in ladder]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_zero_and_negative_rungs_are_skipped(self):
        self.assertEqual(da.corpus_required(120_000, rungs=(0, -1)), [])


class TestProjection(unittest.TestCase):
    def test_income_compounds_at_growth_rate_without_new_money(self):
        path = da.project_income(10_000, 250_000, 120_000,
                                 dividend_growth_pct=10, years=2)
        self.assertAlmostEqual(path[0]["annual_income"], 11_000, places=0)
        self.assertAlmostEqual(path[1]["annual_income"], 12_100, places=0)

    def test_new_money_earns_nothing_in_its_first_year(self):
        # ₹1000/m for year 1 = ₹12k invested; it must not pay a dividend until y2.
        path = da.project_income(0, 0, 120_000, monthly_investment=1000,
                                 dividend_growth_pct=0, new_money_yield_pct=5,
                                 years=2)
        self.assertEqual(path[0]["annual_income"], 0.0)
        self.assertAlmostEqual(path[1]["annual_income"], 600, places=0)  # 12k * 5%

    def test_corpus_grows_with_contributions_and_appreciation(self):
        path = da.project_income(0, 100_000, 120_000, monthly_investment=1000,
                                 capital_growth_pct=10, years=1)
        self.assertAlmostEqual(path[0]["corpus"], 110_000 + 12_000, places=0)

    def test_goal_reached_flag_and_years(self):
        path = da.project_income(100_000, 2_500_000, 120_000,
                                 dividend_growth_pct=10, years=5)
        first = next(p for p in path if p["goal_reached"])
        self.assertEqual(first["offset"], 2)   # 110k, then 121k

    def test_years_floor_is_one(self):
        self.assertEqual(len(da.project_income(0, 0, 1, years=0)), 1)

    def test_start_year_labels_calendar_years(self):
        path = da.project_income(0, 0, 120_000, years=2, start_year=2026)
        self.assertEqual([p["year"] for p in path], [2027, 2028])


class TestSipForGoal(unittest.TestCase):
    def test_zero_when_already_there(self):
        self.assertEqual(da.monthly_investment_for_goal(150_000, 120_000, 5), 0.0)

    def test_solution_actually_reaches_the_goal(self):
        sip = da.monthly_investment_for_goal(10_000, 120_000, 10,
                                             dividend_growth_pct=8,
                                             new_money_yield_pct=4)
        self.assertGreater(sip, 0)
        path = da.project_income(10_000, 0, 120_000, monthly_investment=sip,
                                 dividend_growth_pct=8, capital_growth_pct=0,
                                 new_money_yield_pct=4, years=10)
        self.assertGreaterEqual(path[-1]["annual_income"], 120_000 * 0.999)

    def test_shorter_horizon_needs_a_bigger_sip(self):
        three = da.monthly_investment_for_goal(10_000, 120_000, 3)
        ten = da.monthly_investment_for_goal(10_000, 120_000, 10)
        self.assertGreater(three, ten)

    def test_zero_yield_is_unreachable(self):
        self.assertEqual(
            da.monthly_investment_for_goal(0, 120_000, 5, new_money_yield_pct=0),
            float("inf"))

    def test_degenerate_inputs(self):
        self.assertEqual(da.monthly_investment_for_goal(0, 0, 5), 0.0)
        self.assertEqual(da.monthly_investment_for_goal(0, 120_000, 0), 0.0)


class TestBuildDividendBook(unittest.TestCase):
    def _book(self, **kw):
        stocks = [
            da.build_stock_row(
                {"symbol": "COALINDIA", "shares": 100, "price": 414.10,
                 "avg_cost": 380.0, "sector": "Energy"},
                {"history": [("2025-08-01", 21.0), ("2026-02-01", 5.5)],
                 "payout_ratio": 70},
                as_of=date(2026, 8, 5)),
            da.build_stock_row(
                {"symbol": "ITC", "shares": 100, "price": 288.05,
                 "avg_cost": 320.0, "sector": "FMCG"},
                {"history": [("2025-08-01", 6.5), ("2026-02-01", 8.0)],
                 "payout_ratio": 87},
                as_of=date(2026, 8, 5)),
            da.build_stock_row(
                {"symbol": "ITCHOTELS", "shares": 100, "price": 200.0,
                 "avg_cost": 180.0, "sector": "Hotels"},
                {}, as_of=date(2026, 8, 5)),
        ]
        funds = [
            da.build_fund_row({"scheme_name": "PPFAS Flexi Cap Growth",
                               "current_value": 500_000, "invested": 400_000}, 1.2),
        ]
        kw.setdefault("as_of", date(2026, 8, 5))
        return da.build_dividend_book(stocks, funds, **kw)

    def test_totals_add_up(self):
        b = self._book()
        expected = round(26.5 * 100 + 14.5 * 100, 2)
        self.assertEqual(b["income"]["annual_gross"], expected)
        self.assertEqual(b["income"]["from_funds"], 0.0)          # growth plan
        self.assertEqual(b["income"]["reinvested_in_funds"], 6000.0)
        self.assertAlmostEqual(b["income"]["monthly_gross"], expected / 12, places=1)

    def test_net_of_tax(self):
        b = self._book(tax_slab_pct=30)
        self.assertAlmostEqual(b["income"]["annual_net"],
                               b["income"]["annual_gross"] * 0.7, places=1)

    def test_blended_yield_uses_whole_portfolio_not_just_payers(self):
        b = self._book()
        total_value = b["income"]["total_value"]
        self.assertAlmostEqual(
            b["income"]["blended_yield"],
            b["income"]["annual_gross"] / total_value * 100, places=2)
        # Non-payers and the growth fund drag the blended yield below the
        # yield of the payers themselves.
        self.assertLess(b["income"]["blended_yield"], 6.4)

    def test_other_assets_are_counted_in_total_value(self):
        without = self._book()["income"]["total_value"]
        with_gold = self._book(other_assets_value=100_000)["income"]["total_value"]
        self.assertAlmostEqual(with_gold - without, 100_000, places=1)

    def test_goal_gap(self):
        b = self._book(goal_annual=120_000)
        gross = b["income"]["annual_gross"]
        self.assertAlmostEqual(b["goal"]["gap_annual"], 120_000 - gross, places=1)
        self.assertAlmostEqual(b["goal"]["achieved_pct"],
                               round(gross / 120_000 * 100, 1), places=1)
        self.assertFalse(b["goal"]["on_track"])

    def test_goal_gap_never_negative_when_ahead(self):
        b = self._book(goal_annual=1000)
        self.assertEqual(b["goal"]["gap_annual"], 0.0)
        self.assertTrue(b["goal"]["on_track"])

    def test_non_payers_are_listed(self):
        b = self._book()
        self.assertEqual(b["income"]["non_payer_count"], 1)
        self.assertIn("ITCHOTELS", b["income"]["non_payers"])
        self.assertEqual(b["income"]["payer_count"], 2)

    def test_stocks_ranked_by_income(self):
        b = self._book()
        incomes = [s["annual_income"] for s in b["stocks"]]
        self.assertEqual(incomes, sorted(incomes, reverse=True))

    def test_sector_split_sums_to_100(self):
        b = self._book()
        self.assertAlmostEqual(sum(s["pct"] for s in b["by_sector"]), 100.0, places=0)

    def test_calendar_covers_twelve_months_and_matches_annual(self):
        b = self._book()
        self.assertEqual([c["month"] for c in b["calendar"]], list(range(1, 13)))
        total = sum(c["amount"] for c in b["calendar"])
        self.assertAlmostEqual(total, b["income"]["from_stocks"], delta=1.0)

    def test_concentration_alert_fires(self):
        b = self._book()
        self.assertTrue(any("COALINDIA" in a["msg"] for a in b["alerts"]))

    def test_growth_plan_reinvestment_alert_fires(self):
        b = self._book()
        self.assertTrue(any("reinvested" in a["msg"] for a in b["alerts"]))

    def test_projection_has_ten_years_and_rises(self):
        b = self._book()
        proj = b["projection"]
        self.assertEqual(len(proj), 10)
        self.assertGreater(proj[-1]["annual_income"], proj[0]["annual_income"])

    def test_sip_needed_shrinks_with_horizon(self):
        g = self._book()["goal"]
        self.assertGreater(g["sip_needed_3y"], g["sip_needed_5y"])
        self.assertGreater(g["sip_needed_5y"], g["sip_needed_10y"])

    def test_new_money_yield_is_clamped_to_realistic_band(self):
        g = self._book()["goal"]
        self.assertGreaterEqual(g["assumed_new_money_yield_pct"], 3.0)
        self.assertLessEqual(g["assumed_new_money_yield_pct"], 6.0)

    def test_monthly_investment_pulls_the_goal_year_closer(self):
        slow = self._book(monthly_investment=0)["goal"]["years_to_goal"]
        fast = self._book(monthly_investment=15_000)["goal"]["years_to_goal"]
        self.assertIsNotNone(fast)
        self.assertTrue(slow is None or fast <= slow)

    def test_tax_slab_is_clamped(self):
        self.assertEqual(self._book(tax_slab_pct=500)["income"]["tax_slab_pct"], 100.0)
        self.assertEqual(self._book(tax_slab_pct=-5)["income"]["tax_slab_pct"], 0.0)


class TestEmptyPortfolio(unittest.TestCase):
    def test_empty_book_is_well_formed(self):
        b = da.empty_book()
        self.assertEqual(b["income"]["annual_gross"], 0.0)
        self.assertEqual(b["income"]["blended_yield"], 0.0)
        self.assertEqual(b["goal"]["achieved_pct"], 0.0)
        self.assertEqual(b["stocks"], [])
        self.assertEqual(b["funds"], [])
        self.assertEqual(len(b["calendar"]), 12)
        self.assertEqual(len(b["corpus_ladder"]), len(da.CORPUS_YIELD_RUNGS))
        self.assertIsNone(b["goal"]["years_to_goal"])

    def test_zero_goal_does_not_divide_by_zero(self):
        b = da.build_dividend_book([], [], goal_annual=0)
        self.assertEqual(b["goal"]["achieved_pct"], 0.0)
        self.assertEqual(b["goal"]["gap_annual"], 0.0)
        self.assertFalse(b["goal"]["on_track"])


class TestFutureHoldingsSupport(unittest.TestCase):
    """A newly added stock or fund must flow through with zero configuration."""

    def test_arbitrary_new_stock_joins_the_book(self):
        rows = [da.build_stock_row(
            {"symbol": "SOMENEWCO.NS", "shares": 50, "price": 250,
             "avg_cost": 200, "sector": "Chemicals"},
            {"dividend_rate": 10.0, "payout_ratio": 40,
             "history": [("2024-07-01", 8.0), ("2025-07-01", 9.0),
                         ("2026-07-01", 10.0)]},
            as_of=date(2026, 8, 5))]
        b = da.build_dividend_book(rows, [], goal_annual=120_000)
        self.assertEqual(b["income"]["from_stocks"], 500.0)      # 10 * 50
        self.assertEqual(b["stocks"][0]["symbol"], "SOMENEWCO")
        self.assertEqual(b["by_sector"][0]["sector"], "Chemicals")

    def test_arbitrary_new_fund_joins_the_book(self):
        rows = [da.build_fund_row(
            {"scheme_name": "Brand New Balanced Advantage - IDCW",
             "current_value": 300_000, "invested": 250_000,
             "category": "Hybrid"}, 2.5)]
        b = da.build_dividend_book([], rows, goal_annual=120_000)
        self.assertEqual(b["income"]["from_funds"], 7500.0)
        self.assertEqual(b["funds"][0]["plan"], "IDCW")

    def test_mixed_stocks_and_funds_totals(self):
        stocks = [da.build_stock_row({"symbol": "A", "shares": 100, "price": 100},
                                     {"dividend_rate": 4.0})]
        funds = [da.build_fund_row({"scheme_name": "F - IDCW",
                                    "current_value": 100_000}, 3.0)]
        b = da.build_dividend_book(stocks, funds, goal_annual=10_000)
        self.assertEqual(b["income"]["annual_gross"], 400.0 + 3000.0)
        self.assertAlmostEqual(b["income"]["blended_yield"],
                               3400 / 110_000 * 100, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
