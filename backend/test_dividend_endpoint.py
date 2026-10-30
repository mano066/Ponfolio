"""
Integration tests for /api/portfolio/dividend-analysis and the goal endpoint.

    python -m unittest test_dividend_endpoint -v

yfinance, price fetching and settings persistence are stubbed, so these run
offline and assert the wiring — not the market.
"""

import unittest
from unittest import mock

import dividend_analysis as da


class DividendEndpointTestCase(unittest.TestCase):
    """Base: import main once, then patch its module-level state per test."""

    @classmethod
    def setUpClass(cls):
        # Importing main starts no server; it does read settings from disk.
        import main
        cls.main = main

    def setUp(self):
        m = self.main
        self._saved = {
            "portfolio": list(m.user_portfolio),
            "mf": list(m.user_mf_portfolio),
            "settings": dict(m.app_settings),
            "prices": dict(m.live_price_cache),
            "div_cache": dict(m._dividend_facts_cache),
        }
        m.user_portfolio.clear()
        m.user_mf_portfolio.clear()
        m.live_price_cache.clear()
        m._dividend_facts_cache.clear()

    def tearDown(self):
        m = self.main
        m.user_portfolio[:] = self._saved["portfolio"]
        m.user_mf_portfolio[:] = self._saved["mf"]
        m.app_settings.clear()
        m.app_settings.update(self._saved["settings"])
        m.live_price_cache.clear()
        m.live_price_cache.update(self._saved["prices"])
        m._dividend_facts_cache.clear()
        m._dividend_facts_cache.update(self._saved["div_cache"])

    # ── fixtures ────────────────────────────────────────────────────────
    FACTS = {
        "COALINDIA.NS": {
            "history": [("2025-08-01", 21.0), ("2026-02-01", 5.5)],
            "dividend_rate": 26.5, "trailing_dividend_rate": 26.5,
            "payout_ratio": 0.70,
        },
        "ITC.NS": {
            "history": [("2025-08-01", 6.5), ("2026-02-01", 8.0)],
            "dividend_rate": 14.5, "trailing_dividend_rate": 14.5,
            "payout_ratio": 0.87,
        },
        "ITCHOTELS.NS": {"history": [], "dividend_rate": 0.0,
                         "trailing_dividend_rate": 0.0, "payout_ratio": 0.0},
    }
    PRICES = {"COALINDIA.NS": 414.10, "ITC.NS": 288.05, "ITCHOTELS.NS": 200.0,
              "RELIANCE.NS": 1400.0, "TCS.NS": 3200.0}

    def _seed_stocks(self):
        self.main.user_portfolio.extend([
            {"symbol": "COALINDIA", "shares": 100, "avg_cost": 380.0},
            {"symbol": "ITC", "shares": 100, "avg_cost": 320.0},
            {"symbol": "ITCHOTELS", "shares": 100, "avg_cost": 180.0},
        ])

    def _patches(self, facts=None, prices=None):
        """Patch the three network seams the endpoint touches."""
        facts = facts if facts is not None else self.FACTS
        prices = prices if prices is not None else self.PRICES
        return [
            mock.patch.object(self.main, "_get_dividend_facts",
                              side_effect=lambda sym, force=False: facts.get(sym, {})),
            mock.patch.object(self.main, "_fetch_price",
                              side_effect=lambda sym: (prices.get(sym), prices.get(sym))),
            mock.patch.object(self.main, "_get_stock_info",
                              side_effect=lambda sym: {
                                  "sector": {"COALINDIA": "Energy",
                                             "ITC": "FMCG"}.get(
                                      sym.replace(".NS", ""), "Other"),
                                  "industry": "Other",
                                  "mcap_class": "Large Cap"}),
        ]

    def _call(self, facts=None, prices=None, **kwargs):
        with mock.patch.multiple(
            self.main,
            _get_dividend_facts=mock.DEFAULT,
            _fetch_price=mock.DEFAULT,
            _get_stock_info=mock.DEFAULT,
        ) as mocks:
            f = facts if facts is not None else self.FACTS
            p = prices if prices is not None else self.PRICES
            mocks["_get_dividend_facts"].side_effect = \
                lambda sym, force=False: f.get(sym, {})
            mocks["_fetch_price"].side_effect = \
                lambda sym: (p.get(sym), p.get(sym))
            mocks["_get_stock_info"].side_effect = lambda sym: {
                "sector": {"COALINDIA": "Energy", "ITC": "FMCG"}.get(
                    sym.replace(".NS", "").replace(".BO", ""), "Other"),
                "industry": "Other",
                "mcap_class": "Large Cap",
            }
            return self.main.get_dividend_analysis(**kwargs)


class TestEmptyPortfolio(DividendEndpointTestCase):
    def test_no_holdings_returns_a_well_formed_zero_book(self):
        book = self._call()
        self.assertEqual(book["income"]["annual_gross"], 0.0)
        self.assertEqual(book["stocks"], [])
        self.assertEqual(book["funds"], [])
        self.assertEqual(len(book["calendar"]), 12)
        self.assertIn("disclosure", book)


class TestStockLedger(DividendEndpointTestCase):
    def test_income_matches_shares_times_dps(self):
        self._seed_stocks()
        book = self._call(goal_annual=120_000)
        expected = round(26.5 * 100 + 14.5 * 100, 2)
        self.assertEqual(book["income"]["from_stocks"], expected)
        self.assertEqual(book["income"]["payer_count"], 2)
        self.assertIn("ITCHOTELS", book["income"]["non_payers"])

    def test_sectors_come_from_stock_info(self):
        self._seed_stocks()
        book = self._call()
        sectors = {s["sector"] for s in book["stocks"]}
        self.assertEqual(sectors, {"Energy", "FMCG", "Other"})

    def test_mcap_class_is_attached(self):
        self._seed_stocks()
        book = self._call()
        self.assertTrue(all("mcap_class" in s for s in book["stocks"]))

    def test_live_price_cache_is_preferred_over_fetch(self):
        self._seed_stocks()
        self.main.live_price_cache["COALINDIA"] = {"current": 500.0}
        book = self._call()
        coal = next(s for s in book["stocks"] if s["symbol"] == "COALINDIA")
        self.assertEqual(coal["price"], 500.0)
        self.assertAlmostEqual(coal["yield_pct"], 26.5 / 500 * 100, places=2)

    def test_unpriceable_holding_is_skipped_not_fatal(self):
        self.main.user_portfolio.append(
            {"symbol": "DELISTED", "shares": 10, "avg_cost": 100})
        self._seed_stocks()
        book = self._call()
        self.assertEqual(len(book["stocks"]), 3)     # DELISTED dropped

    def test_provider_with_no_dividend_data_is_a_zero_payer(self):
        self.main.user_portfolio.append(
            {"symbol": "RELIANCE", "shares": 10, "avg_cost": 1200})
        book = self._call()
        rel = next(s for s in book["stocks"] if s["symbol"] == "RELIANCE")
        self.assertEqual(rel["annual_income"], 0.0)
        self.assertEqual(rel["tier"], da.TIER_NONE)


class TestFundLedger(DividendEndpointTestCase):
    def test_growth_plan_contributes_no_spendable_income(self):
        self.main.user_mf_portfolio.append({
            "scheme_name": "Parag Parikh Flexi Cap Growth Direct Plan",
            "current_value": 500_000, "invested": 400_000, "category": "Flexi Cap",
        })
        book = self._call()
        self.assertEqual(book["income"]["from_funds"], 0.0)
        self.assertEqual(book["funds"][0]["plan"], "Growth")

    def test_idcw_plan_contributes_income_from_lookthrough(self):
        self.main.user_mf_portfolio.append({
            "scheme_name": "Some Dividend Yield Fund - IDCW",
            "current_value": 100_000, "invested": 90_000, "category": "Dividend Yield",
        })
        with mock.patch.object(self.main, "_get_mf_top_holdings",
                               return_value=[{"stock": "ITC.NS", "pct": 100}]):
            book = self._call()
        fund = book["funds"][0]
        self.assertEqual(fund["plan"], "IDCW")
        # ITC yield = 14.5 / 288.05 = 5.03%
        self.assertGreater(fund["cash_income"], 4900)
        self.assertEqual(book["income"]["from_funds"], fund["cash_income"])

    def test_fund_with_no_disclosed_holdings_yields_zero(self):
        self.main.user_mf_portfolio.append({
            "scheme_name": "Mystery Fund - IDCW", "current_value": 100_000})
        with mock.patch.object(self.main, "_get_mf_top_holdings", return_value=[]):
            book = self._call()
        self.assertEqual(book["funds"][0]["lookthrough_yield"], 0.0)
        self.assertEqual(book["funds"][0]["cash_income"], 0.0)


class TestOverrides(DividendEndpointTestCase):
    def test_manual_dps_override_is_applied(self):
        self.main.user_portfolio.append(
            {"symbol": "NEWCO", "shares": 100, "avg_cost": 90})
        self.main.app_settings["dividend_overrides"] = {"NEWCO": 5.0}
        book = self._call(prices={**self.PRICES, "NEWCO.NS": 100.0})
        row = book["stocks"][0]
        self.assertEqual(row["dps"], 5.0)
        self.assertEqual(row["dps_source"], "manual")
        self.assertEqual(row["annual_income"], 500.0)

    def test_override_key_is_suffix_insensitive(self):
        self.main.user_portfolio.append(
            {"symbol": "NEWCO.NS", "shares": 10, "avg_cost": 90})
        self.main.app_settings["dividend_overrides"] = {"newco": 5.0}
        book = self._call(prices={**self.PRICES, "NEWCO.NS": 100.0})
        self.assertEqual(book["stocks"][0]["dps"], 5.0)

    def test_fund_declared_payout_override_is_applied(self):
        self.main.user_mf_portfolio.append({
            "scheme_name": "My IDCW Fund", "current_value": 100_000})
        self.main.app_settings["dividend_fund_overrides"] = {"My IDCW Fund": 8000}
        with mock.patch.object(self.main, "_get_mf_top_holdings", return_value=[]):
            book = self._call()
        self.assertEqual(book["funds"][0]["cash_income"], 8000.0)
        self.assertEqual(book["income"]["from_funds"], 8000.0)

    def test_disclosure_counts_overrides(self):
        self.main.app_settings["dividend_overrides"] = {"A": 1.0, "B": 2.0}
        self.main.app_settings["dividend_fund_overrides"] = {"F": 3.0}
        book = self._call()
        self.assertEqual(book["disclosure"]["override_count"], 3)


class TestGoalWiring(DividendEndpointTestCase):
    def test_saved_goal_is_used_by_default(self):
        self._seed_stocks()
        self.main.app_settings["dividend_goal_annual"] = 60_000
        book = self._call()
        self.assertEqual(book["goal"]["annual"], 60_000)

    def test_query_param_overrides_saved_goal_without_persisting(self):
        self._seed_stocks()
        self.main.app_settings["dividend_goal_annual"] = 60_000
        book = self._call(goal_annual=240_000)
        self.assertEqual(book["goal"]["annual"], 240_000)
        self.assertEqual(self.main.app_settings["dividend_goal_annual"], 60_000)

    def test_monthly_investment_param_feeds_the_projection(self):
        self._seed_stocks()
        with_sip = self._call(goal_annual=120_000, monthly_investment=20_000)
        without = self._call(goal_annual=120_000, monthly_investment=0)
        self.assertGreater(with_sip["projection"][-1]["annual_income"],
                           without["projection"][-1]["annual_income"])

    def test_other_assets_dilute_blended_yield(self):
        self._seed_stocks()
        plain = self._call()
        with_gold = self._call(other_assets_value=1_000_000)
        self.assertLess(with_gold["income"]["blended_yield"],
                        plain["income"]["blended_yield"])
        self.assertEqual(with_gold["income"]["annual_gross"],
                         plain["income"]["annual_gross"])

    def test_tax_slab_setting_is_honoured(self):
        self._seed_stocks()
        self.main.app_settings["dividend_tax_slab_pct"] = 20
        book = self._call()
        self.assertAlmostEqual(book["income"]["annual_net"],
                               book["income"]["annual_gross"] * 0.8, places=1)


class TestGoalPersistence(DividendEndpointTestCase):
    def _save(self, payload):
        with mock.patch.object(self.main, "_save_settings") as saver:
            result = self.main.set_dividend_goal(payload)
        return result, saver

    def test_saves_goal_and_assumptions(self):
        result, saver = self._save({"goal_annual": 240_000, "tax_slab_pct": 20,
                                    "monthly_investment": 15_000})
        self.assertEqual(result["status"], "saved")
        self.assertEqual(self.main.app_settings["dividend_goal_annual"], 240_000)
        self.assertEqual(self.main.app_settings["dividend_tax_slab_pct"], 20)
        self.assertEqual(self.main.app_settings["dividend_monthly_investment"], 15_000)
        saver.assert_called_once()

    def test_normalises_override_keys_and_drops_zeros(self):
        self._save({"overrides": {"coalindia.ns": 26.5, "junk": 0}})
        self.assertEqual(self.main.app_settings["dividend_overrides"],
                         {"COALINDIA": 26.5})

    def test_clamps_out_of_range_values(self):
        self._save({"goal_annual": -100, "tax_slab_pct": 500,
                    "monthly_investment": -50})
        self.assertEqual(self.main.app_settings["dividend_goal_annual"], 0.0)
        self.assertEqual(self.main.app_settings["dividend_tax_slab_pct"], 100.0)
        self.assertEqual(self.main.app_settings["dividend_monthly_investment"], 0.0)

    def test_empty_payload_is_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self._save({})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_partial_payload_leaves_other_keys_alone(self):
        self.main.app_settings["dividend_tax_slab_pct"] = 30
        self._save({"goal_annual": 500_000})
        self.assertEqual(self.main.app_settings["dividend_tax_slab_pct"], 30)


class TestFactsCache(DividendEndpointTestCase):
    def test_facts_are_cached_after_first_fetch(self):
        with mock.patch.object(self.main, "_fetch_dividend_facts",
                               return_value={"history": []}) as fetch:
            self.main._get_dividend_facts("ITC")
            self.main._get_dividend_facts("ITC")
        self.assertEqual(fetch.call_count, 1)

    def test_force_bypasses_the_cache(self):
        with mock.patch.object(self.main, "_fetch_dividend_facts",
                               return_value={"history": []}) as fetch:
            self.main._get_dividend_facts("ITC")
            self.main._get_dividend_facts("ITC", force=True)
        self.assertEqual(fetch.call_count, 2)

    def test_cache_key_is_the_yahoo_symbol(self):
        with mock.patch.object(self.main, "_fetch_dividend_facts",
                               return_value={"history": []}) as fetch:
            self.main._get_dividend_facts("ITC")
            self.main._get_dividend_facts("ITC.NS")
        self.assertEqual(fetch.call_count, 1)

    def test_stale_entries_are_refetched(self):
        with mock.patch.object(self.main, "_fetch_dividend_facts",
                               return_value={"history": []}) as fetch:
            self.main._get_dividend_facts("ITC")
            self.main._dividend_facts_cache["ITC.NS"]["fetched_at"] -= \
                self.main.DIVIDEND_CACHE_TTL + 1
            self.main._get_dividend_facts("ITC")
        self.assertEqual(fetch.call_count, 2)


class TestFactsFetchResilience(DividendEndpointTestCase):
    def test_ticker_blowing_up_returns_an_empty_shape(self):
        with mock.patch.object(self.main.yf, "Ticker",
                               side_effect=RuntimeError("network down")):
            facts = self.main._fetch_dividend_facts("ITC.NS")
        self.assertEqual(facts["history"], [])
        self.assertEqual(facts["dividend_rate"], 0.0)

    def test_missing_info_does_not_lose_history(self):
        class FakeSeries:
            def __len__(self): return 1
            def items(self):
                import datetime
                return [(datetime.datetime(2026, 2, 1), 5.5)]

        class FakeTicker:
            dividends = FakeSeries()
            @property
            def info(self): raise RuntimeError("info blocked")

        with mock.patch.object(self.main.yf, "Ticker", return_value=FakeTicker()):
            facts = self.main._fetch_dividend_facts("ITC.NS")
        self.assertEqual(facts["history"], [("2026-02-01", 5.5)])
        self.assertEqual(facts["dividend_rate"], 0.0)


class TestNewHoldingsNeedNoConfiguration(DividendEndpointTestCase):
    def test_a_stock_added_later_appears_in_the_ledger(self):
        self._seed_stocks()
        before = self._call()["income"]["from_stocks"]
        self.main.user_portfolio.append(
            {"symbol": "HDFCBANK", "shares": 50, "avg_cost": 1500})
        facts = {**self.FACTS, "HDFCBANK.NS": {
            "history": [("2025-06-01", 20.0), ("2026-06-01", 24.0)],
            "payout_ratio": 0.25}}
        after = self._call(facts=facts, prices={**self.PRICES, "HDFCBANK.NS": 1800.0})
        self.assertEqual(after["income"]["from_stocks"], round(before + 24.0 * 50, 2))
        self.assertIn("HDFCBANK", [s["symbol"] for s in after["stocks"]])

    def test_a_fund_added_later_appears_in_the_ledger(self):
        self.main.user_mf_portfolio.append({
            "scheme_name": "Brand New Hybrid - IDCW", "current_value": 200_000,
            "invested": 180_000, "category": "Hybrid"})
        with mock.patch.object(self.main, "_get_mf_top_holdings",
                               return_value=[{"stock": "ITC.NS", "pct": 50},
                                             {"stock": "COALINDIA.NS", "pct": 50}]):
            book = self._call()
        self.assertEqual(len(book["funds"]), 1)
        self.assertGreater(book["funds"][0]["lookthrough_yield"], 5.0)

    def test_lookthrough_prices_unknown_underlyings_on_demand(self):
        """A fund holding a stock the user does not own directly still yields."""
        self.main.user_mf_portfolio.append({
            "scheme_name": "Growthy Fund - IDCW", "current_value": 100_000})
        facts = {**self.FACTS, "TCS.NS": {
            "history": [("2025-07-01", 60.0), ("2026-07-01", 64.0)],
            "payout_ratio": 0.5}}
        with mock.patch.object(self.main, "_get_mf_top_holdings",
                               return_value=[{"stock": "TCS.NS", "pct": 100}]):
            book = self._call(facts=facts)
        # TCS 64 / 3200 = 2.0%
        self.assertAlmostEqual(book["funds"][0]["lookthrough_yield"], 2.0, places=1)

    def test_international_underlyings_are_skipped(self):
        self.main.user_mf_portfolio.append({
            "scheme_name": "Global Fund - IDCW", "current_value": 100_000})
        with mock.patch.object(self.main, "_get_mf_top_holdings",
                               return_value=[{"stock": "AAPL", "pct": 100}]):
            book = self._call()
        self.assertEqual(book["funds"][0]["lookthrough_yield"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
