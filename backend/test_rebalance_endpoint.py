"""
Integration tests for /api/portfolio/rebalance and its mark-done companion.

    python -m unittest test_rebalance_endpoint -v

Prices, the index tape and settings persistence are all stubbed, so these run
offline and assert the WIRING — that the endpoint reads the real portfolio
globals, survives a dead index feed, and does not write to disk unasked.
"""

import unittest
from unittest import mock

import rebalance_engine as re


class RebalanceEndpointTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    def setUp(self):
        m = self.main
        self._saved = {
            "portfolio": list(m.user_portfolio),
            "mf": list(m.user_mf_portfolio),
            "txns": dict(m.user_equity_txns),
            "settings": dict(m.app_settings),
            "prices": dict(m.live_price_cache),
        }
        m.app_settings.clear()
        m.app_settings.update(m.DEFAULT_SETTINGS)
        m.app_settings["rebalance_long_term_only"] = False
        m.user_portfolio.clear()
        m.user_mf_portfolio.clear()
        m.user_equity_txns.clear()
        m.live_price_cache.clear()

    def tearDown(self):
        m = self.main
        m.user_portfolio[:] = self._saved["portfolio"]
        m.user_mf_portfolio[:] = self._saved["mf"]
        m.user_equity_txns.clear()
        m.user_equity_txns.update(self._saved["txns"])
        m.app_settings.clear()
        m.app_settings.update(self._saved["settings"])
        m.live_price_cache.clear()
        m.live_price_cache.update(self._saved["prices"])

    def load(self, holdings):
        """Seed the portfolio and pin every price, so nothing reaches the network."""
        m = self.main
        for sym, shares, avg, price in holdings:
            m.user_portfolio.append({"symbol": sym, "name": sym,
                                     "shares": shares, "avg_cost": avg})
            m.live_price_cache[sym] = {"current": price, "prev": price,
                                       "source": "test", "observed_at": None}

    def plan(self, tape=None, **kw):
        with mock.patch.object(self.main, "_get_index_tape", return_value=tape):
            return self.main.get_rebalance_plan(**kw)

    # ── wiring ──

    def test_the_plan_reads_the_live_portfolio(self):
        self.load([("BIG.NS", 3000, 50, 100)]
                  + [(f"F{i}.NS", 700, 90, 100) for i in range(10)])
        plan = self.plan(as_of="2026-09-09")
        by_key = {a["key"]: a for a in plan["actions"]}
        self.assertEqual(by_key["BIG.NS"]["action"], "TRIM")
        self.assertEqual(plan["portfolio_value"], 1000000.0)

    def test_a_dead_index_feed_does_not_kill_the_plan(self):
        # The band and calendar triggers stand on their own; losing the tape
        # must cost the boom signal only.
        self.load([("BIG.NS", 3000, 50, 100)]
                  + [(f"F{i}.NS", 700, 90, 100) for i in range(10)])
        with mock.patch.object(self.main, "_get_index_tape",
                               side_effect=RuntimeError("feed down")):
            plan = self.main.get_rebalance_plan(as_of="2026-09-09")
        self.assertFalse(plan["market"]["available"])
        self.assertEqual(plan["market"]["heat"], "unknown")
        self.assertTrue(any(a["action"] == "TRIM" for a in plan["actions"]))

    def test_a_hot_tape_fires_the_boom_trigger(self):
        self.load([("A.NS", 100, 100, 100)])
        tape = {"indices": [{"symbol": "^NSEI", "label": "NIFTY 50",
                             "status": "ok", "off_high_pct": 0.5,
                             "rsi_14": 78.0, "vs_dma_200_pct": 18.0,
                             "chg_1y_pct": 30.0}]}
        plan = self.plan(tape=tape, as_of="2026-09-09")
        self.assertTrue(plan["market"]["boom"])
        self.assertIn("market_boom", [f["name"] for f in plan["triggers"]["fired"]])

    def test_holdings_with_no_price_are_left_out_of_the_weights(self):
        # A holding with no price has no value, and letting it through as 0
        # would inflate every other position's weight past its ceiling.
        self.load([(f"F{i}.NS", 700, 90, 100) for i in range(10)])
        m = self.main
        m.user_portfolio.append(
            {"symbol": "DEAD.NS", "name": "Dead", "shares": 100, "avg_cost": 50})

        def priced(item):
            cached = m.live_price_cache.get(item["symbol"])
            if not cached:
                return None, None, "none"
            return cached["current"], cached["prev"], cached["source"]

        # Answer from the seeded cache only: reaching yfinance for a symbol
        # invented by the test would make this suite slow and online.
        with mock.patch.object(m, "_resolve_price", side_effect=priced):
            plan = self.plan(as_of="2026-09-09")
        self.assertNotIn("DEAD.NS", {a["key"] for a in plan["actions"]})
        self.assertEqual(plan["sleeves"][re.CAT_STOCKS]["total_value"], 700000.0)

    def test_the_dated_ledger_drives_the_tax_leg(self):
        self.load([("BIG.NS", 3000, 50, 100)]
                  + [(f"F{i}.NS", 700, 90, 100) for i in range(10)])
        self.main.user_equity_txns["BIG.NS"] = [
            {"date": "2020-01-01", "type": "BUY", "qty": 3000, "price": 50}]
        self.main.app_settings["ltcg_exemption_left"] = 0
        # Pin the ceiling: this asserts the tax on a trim, not the default
        # preset's band, and the two must not be coupled.
        plan = self.plan(as_of="2026-09-09", max_weight_pct=10.0)
        big = next(a for a in plan["actions"] if a["key"] == "BIG.NS")
        self.assertTrue(big["has_long_term_units"])
        self.assertTrue(all(l["long_term"] for l in big["lots"]))
        self.assertAlmostEqual(big["tax"], 13000.0, places=2)

    def test_the_saved_exemption_is_honoured(self):
        self.load([("BIG.NS", 3000, 50, 100)]
                  + [(f"F{i}.NS", 700, 90, 100) for i in range(10)])
        self.main.user_equity_txns["BIG.NS"] = [
            {"date": "2020-01-01", "type": "BUY", "qty": 3000, "price": 50}]
        self.main.app_settings["ltcg_exemption_left"] = re.EQUITY_LTCG_EXEMPT
        plan = self.plan(as_of="2026-09-09")
        big = next(a for a in plan["actions"] if a["key"] == "BIG.NS")
        # A ₹1L long-term gain sits entirely inside the ₹1.25L allowance.
        self.assertEqual(big["tax"], 0.0)

    def test_residency_and_cadence_reach_the_engine(self):
        self.load([("A.NS", 100, 100, 100)])
        plan = self.plan(as_of="2026-09-09", residency=re.RESIDENT,
                         cadence="annual")
        self.assertEqual(plan["residency"], re.RESIDENT)
        self.assertEqual(plan["triggers"]["cadence"], "annual")
        self.assertEqual(plan["triggers"]["window_days"], re.ANNUAL_DAYS)

    def test_funds_are_planned_alongside_stocks(self):
        self.load([("A.NS", 100, 100, 100)])
        self.main.user_mf_portfolio.append(
            {"scheme_name": "Big Fund", "category": "Flexi Cap", "units": 1000,
             "nav": 300, "current_value": 300000,
             "transactions": [{"date": "2020-01-01", "units": 1000, "nav": 150}]})
        plan = self.plan(as_of="2026-09-09")
        self.assertEqual(plan["sleeves"][re.CAT_FUNDS]["total_value"], 300000.0)
        self.assertEqual(plan["portfolio_value"], 310000.0)

    def test_an_empty_portfolio_answers_instead_of_raising(self):
        plan = self.plan(as_of="2026-09-09")
        self.assertEqual(plan["actions"], [])
        self.assertEqual(plan["portfolio_value"], 0.0)
        self.assertTrue(plan["triggers"]["due"])

    # ── mark-done ──

    def test_marking_done_restarts_the_calendar(self):
        m = self.main
        with mock.patch.object(m, "_save_settings") as save:
            out = m.mark_rebalance_done(m.RebalanceMarkRequest(date="2026-09-01"))
        self.assertEqual(out["last_rebalanced_at"], "2026-09-01")
        self.assertEqual(m.app_settings["last_rebalanced_at"], "2026-09-01")
        save.assert_called_once()

        self.load([(f"F{i}.NS", 700, 90, 100) for i in range(10)])
        plan = self.plan(as_of="2026-09-09")
        self.assertFalse(plan["triggers"]["due"])
        self.assertEqual(plan["triggers"]["next_calendar_due"], "2027-03-02")

    def test_marking_done_with_no_body_stamps_today(self):
        m = self.main
        with mock.patch.object(m, "_save_settings"):
            out = m.mark_rebalance_done(None)
        self.assertRegex(out["last_rebalanced_at"], r"^\d{4}-\d{2}-\d{2}$")


class RebalanceSettingsTestCase(unittest.TestCase):
    """The policy the plan is built from: saved, validated, and echoed back."""

    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    def setUp(self):
        m = self.main
        self._saved = {
            "settings": dict(m.app_settings),
            "portfolio": list(m.user_portfolio),
            "prices": dict(m.live_price_cache),
            "mf": list(m.user_mf_portfolio),
        }
        m.user_portfolio.clear()
        m.user_mf_portfolio.clear()
        m.live_price_cache.clear()
        self._patch = mock.patch.object(m, "_save_settings")
        self.save = self._patch.start()

    def tearDown(self):
        m = self.main
        self._patch.stop()
        m.app_settings.clear()
        m.app_settings.update(self._saved["settings"])
        m.user_portfolio[:] = self._saved["portfolio"]
        m.user_mf_portfolio[:] = self._saved["mf"]
        m.live_price_cache.clear()
        m.live_price_cache.update(self._saved["prices"])

    def put(self, **kw):
        return self.main.save_rebalance_settings(
            self.main.RebalanceSettingsRequest(**kw))

    def load(self, holdings):
        m = self.main
        for sym, shares, avg, price in holdings:
            m.user_portfolio.append({"symbol": sym, "name": sym,
                                     "shares": shares, "avg_cost": avg})
            m.live_price_cache[sym] = {"current": price, "prev": price,
                                       "source": "test", "observed_at": None}

    def plan(self, **kw):
        with mock.patch.object(self.main, "_get_index_tape", return_value=None):
            return self.main.get_rebalance_plan(**kw)

    # ── defaults ──

    def test_the_defaults_are_the_documented_ones(self):
        # Reset to the shipped defaults first. `app_settings` is loaded from
        # the real settings file at import, so without this the test asserts
        # the developer's own saved preferences and fails on any machine where
        # the app has actually been used.
        self.main.app_settings.clear()
        self.main.app_settings.update(self.main.DEFAULT_SETTINGS)
        out = self.main.get_rebalance_settings()
        self.assertEqual(out["min_weight_pct"], 2.0)
        self.assertEqual(out["max_weight_pct"], 20.0)  # S10's ceiling
        self.assertEqual(out["mode"], re.MODE_AUTO)
        self.assertIsNone(out["category_targets"])
        self.assertFalse(out["category_targets_set"])

    def test_the_vocabulary_travels_with_the_settings(self):
        # So the UI never has to hard-code a trigger name or a category label.
        out = self.main.get_rebalance_settings()
        self.assertEqual([t["name"] for t in out["all_triggers"]],
                         list(re.ALL_TRIGGERS))
        self.assertEqual([c["name"] for c in out["all_categories"]],
                         list(re.CATEGORIES))

    # ── saving ──

    def test_the_sliders_round_trip(self):
        out = self.put(min_weight_pct=5, max_weight_pct=20)
        self.assertEqual((out["min_weight_pct"], out["max_weight_pct"]),
                         (5.0, 20.0))
        self.save.assert_called_once()

    def test_crossed_sliders_are_read_back_the_right_way_round(self):
        out = self.put(min_weight_pct=30, max_weight_pct=10)
        self.assertEqual((out["min_weight_pct"], out["max_weight_pct"]),
                         (10.0, 30.0))

    def test_a_partial_save_leaves_the_rest_alone(self):
        # The settings screen saves one control at a time; requiring a full
        # round trip would let it clobber a change made elsewhere.
        self.put(min_weight_pct=4, mode=re.MODE_MANUAL)
        out = self.put(deviation_pct=9)
        self.assertEqual(out["min_weight_pct"], 4.0)
        self.assertEqual(out["mode"], re.MODE_MANUAL)
        self.assertEqual(out["deviation_pct"], 9.0)

    def test_an_unknown_trigger_is_rejected_not_dropped(self):
        # Silently dropping it leaves the user looking at a rule they believe
        # is armed and is not.
        with self.assertRaises(self.main.HTTPException) as caught:
            self.put(triggers=[re.TRIGGER_BOOM, "market_vibes"])
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("market_vibes", caught.exception.detail)

    def test_an_unknown_category_target_is_rejected(self):
        with self.assertRaises(self.main.HTTPException):
            self.put(category_targets={"crypto": 50})

    def test_triggers_are_deduplicated(self):
        out = self.put(triggers=[re.TRIGGER_BOOM, re.TRIGGER_BOOM,
                                 re.TRIGGER_CRASH])
        self.assertEqual(out["triggers"], [re.TRIGGER_BOOM, re.TRIGGER_CRASH])

    def test_a_custom_threshold_can_be_cleared(self):
        # None already means "leave this alone" on a partial update, so
        # clearing needs its own flag or a trigger could never be unset.
        self.put(gain_trigger_pct=30)
        self.assertEqual(
            self.main.get_rebalance_settings()["gain_trigger_pct"], 30.0)
        out = self.put(clear_gain_trigger=True)
        self.assertIsNone(out["gain_trigger_pct"])

    def test_a_selection_can_be_cleared_back_to_everything(self):
        out = self.put(selected_categories=[re.CAT_STOCKS])
        self.assertEqual(out["selected_categories"], [re.CAT_STOCKS])
        out = self.put(clear_selected_categories=True)
        self.assertIsNone(out["selected_categories"])

    def test_saved_category_targets_are_normalised_on_read(self):
        out = self.put(category_targets={re.CAT_STOCKS: 100, re.CAT_FUNDS: 60,
                                         re.CAT_GOLD: 20, re.CAT_DEBT: 20})
        self.assertTrue(out["category_targets_set"])
        self.assertAlmostEqual(sum(out["category_targets"].values()), 100.0,
                               places=2)

    def test_choosing_a_preset_moves_the_ceiling_with_it(self):
        out = self.put(strategy="S3")
        self.assertEqual(out["strategy"], "S3")
        self.assertEqual(out["max_weight_pct"], 12.5)
        out = self.put(strategy="M1")
        self.assertEqual(out["max_weight_pct"], 25.0)

    def test_setting_the_ceiling_by_hand_switches_to_custom(self):
        # Otherwise the screen names a rule the plan is not following.
        self.put(strategy="S10")
        out = self.put(max_weight_pct=14)
        self.assertEqual(out["strategy"], re.STRATEGY_CUSTOM)
        self.assertEqual(out["max_weight_pct"], 14.0)

    def test_a_never_sells_preset_is_also_dropped_by_setting_a_ceiling(self):
        # S6 has no ceiling at all, so any ceiling contradicts it rather than
        # merely differing from it.
        self.put(strategy="S6")
        out = self.put(max_weight_pct=18)
        self.assertEqual(out["strategy"], re.STRATEGY_CUSTOM)

    def test_an_unknown_preset_is_rejected(self):
        with self.assertRaises(self.main.HTTPException) as caught:
            self.put(strategy="S99")
        self.assertEqual(caught.exception.status_code, 400)

    def test_the_strategy_list_carries_its_measurement_basis(self):
        out = self.main.get_rebalance_strategies()
        self.assertEqual(out["default"], "S10")
        self.assertIn("not a forecast", out["measured_basis"])
        self.assertEqual([s["id"] for s in out["strategies"]][:3],
                         ["S1", "S2", "S3"])


    # ── reaching the plan ──

    def test_the_saved_policy_reaches_the_plan(self):
        self.load([("BIG.NS", 3000, 50, 100)]
                  + [(f"F{i}.NS", 700, 90, 100) for i in range(19)])
        self.put(min_weight_pct=1, max_weight_pct=25, mode=re.MODE_MANUAL,
                 triggers=[re.TRIGGER_BAND])
        plan = self.plan(as_of="2026-09-09")
        self.assertEqual(plan["policy"]["max_weight_pct"], 25.0)
        self.assertEqual(plan["policy"]["mode"], re.MODE_MANUAL)
        self.assertEqual(plan["triggers"]["enabled"], [re.TRIGGER_BAND])
        # 18.4% of the sleeve is inside a 25% ceiling.
        big = next(a for a in plan["actions"] if a["key"] == "BIG.NS")
        self.assertEqual(big["status"], "within")

    def test_a_query_override_previews_without_saving(self):
        self.load([("BIG.NS", 3000, 50, 100)]
                  + [(f"F{i}.NS", 700, 90, 100) for i in range(19)])
        plan = self.plan(as_of="2026-09-09", max_weight_pct=25)
        self.assertEqual(plan["policy"]["max_weight_pct"], 25.0)
        # ...and nothing was written: the saved ceiling is still the default
        # preset's 20%, not the 25% previewed on the query.
        self.assertEqual(
            self.main.get_rebalance_settings()["max_weight_pct"], 20.0)
        self.assertEqual(
            self.main.get_rebalance_settings()["strategy"],
            re.DEFAULT_STRATEGY)
        self.save.assert_not_called()

    def test_manual_gold_and_debt_travel_on_the_request(self):
        # They live in the client's local store, so the plan can only see them
        # if they are sent; leaving them out inflates every other category.
        self.load([("A.NS", 1000, 50, 100)])
        plan = self.plan(as_of="2026-09-09", manual_gold=50000,
                         manual_debt=50000)
        self.assertEqual(plan["portfolio_value"], 200000.0)
        rows = {r["category"]: r for r in plan["allocation"]["rows"]}
        self.assertEqual(rows[re.CAT_GOLD]["current_pct"], 25.0)
        self.assertEqual(rows[re.CAT_DEBT]["manual_value"], 50000.0)

    def test_a_bad_enum_is_a_422_not_a_crash(self):
        for kw in ({"cadence": "weekly"}, {"residency": "martian"},
                   {"mode": "sometimes"}):
            with self.subTest(**kw):
                with self.assertRaises(self.main.HTTPException) as caught:
                    self.plan(as_of="2026-09-09", **kw)
                self.assertEqual(caught.exception.status_code, 422)

    def test_the_plan_carries_the_settings_it_used(self):
        plan = self.plan(as_of="2026-09-09")
        self.assertIn("settings", plan)
        self.assertEqual(plan["settings"]["min_weight_pct"],
                         plan["policy"]["min_weight_pct"])


if __name__ == "__main__":
    unittest.main()
