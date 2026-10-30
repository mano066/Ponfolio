"""
Integration tests for the capital-deployment endpoints.

    python -m unittest test_deploy_endpoint -v

yfinance, price fetching, NAV history and settings persistence are all stubbed,
so these run offline and assert the WIRING — not the market.
"""

import unittest
from unittest import mock


class DeployEndpointTestCase(unittest.TestCase):
    """Base: import main once, then patch its module-level state per test."""

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
            "log": list(m.user_deploy_log),
            "settings": dict(m.app_settings),
            "tape": dict(m._index_tape_cache),
        }
        m.user_portfolio.clear()
        m.user_mf_portfolio.clear()
        m.user_equity_txns.clear()
        m.user_deploy_log.clear()
        m._stock_52w_cache.clear()
        m._fund_peak_cache.clear()

        for name in ("_save_portfolio", "_save_mf_portfolio", "_save_equity_txns",
                     "_save_deploy_log", "_save_settings"):
            p = mock.patch.object(m, name)
            p.start()
            self.addCleanup(p.stop)

        # A stable tape: Nifty 9% off its high, IT 22% off.
        p = mock.patch.object(m, "_get_index_tape", return_value={
            "market_mood": "falling",
            "summary": "Nifty 50 is 9.0% below its 1-year high.",
            "indices": [
                {"symbol": "^NSEI", "status": "ok", "off_high_pct": 9.0},
                {"symbol": "^CNXIT", "status": "ok", "off_high_pct": 22.0},
                {"symbol": "^CRSLDX", "status": "ok", "off_high_pct": 3.0},
                {"symbol": "^BSESN", "status": "unavailable", "off_high_pct": None},
            ],
        })
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        m = self.main
        m.user_portfolio[:] = self._saved["portfolio"]
        m.user_mf_portfolio[:] = self._saved["mf"]
        m.user_equity_txns.clear(); m.user_equity_txns.update(self._saved["txns"])
        m.user_deploy_log[:] = self._saved["log"]
        m.app_settings.clear(); m.app_settings.update(self._saved["settings"])
        m._index_tape_cache.clear(); m._index_tape_cache.update(self._saved["tape"])

    # ── fixtures ────────────────────────────────────────────────────────
    def seed_fund(self, name="ICICI Tech Fund", nav=145.0, units=250.0,
                  avg_nav=170.0, value=36250.0, txns=None, category="Sectoral"):
        fund = {"scheme_name": name, "category": category, "nav": nav,
                "units": units, "avg_nav": avg_nav, "current_value": value,
                "invested": units * avg_nav, "transactions": txns or []}
        self.main.user_mf_portfolio.append(fund)
        return fund

    def seed_stock(self, sym="ITC.NS", shares=100, avg_cost=340.0):
        h = {"symbol": sym, "name": sym, "shares": shares, "avg_cost": avg_cost}
        self.main.user_portfolio.append(h)
        return h

    def patch_market(self, price=288.0, high_52w=370.0, nav_peak=195.0):
        m = self.main
        for target, value in (("_fetch_price", (price, "test")),
                              ("_stock_52w_high", high_52w),
                              ("_fund_nav_peak", nav_peak)):
            p = mock.patch.object(m, target, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(m, "_get_stock_info",
                              return_value={"sector": "Consumer Defensive",
                                            "mcap_class": "Large Cap"})
        p.start()
        self.addCleanup(p.stop)


# ══════════════════════════════════════════════════════════════════════════
#  BOARD
# ══════════════════════════════════════════════════════════════════════════

class TestDeployBoard(DeployEndpointTestCase):
    def test_empty_portfolio_returns_a_well_formed_board(self):
        board = self.main.get_deploy_board(amount=20000)
        self.assertEqual(board["candidates"], [])
        self.assertEqual(board["suggestion"]["unallocated"], 20000.0)
        self.assertIn("disclosure", board)

    def test_funds_and_stocks_both_become_candidates(self):
        self.seed_fund()
        self.seed_stock()
        self.patch_market()
        board = self.main.get_deploy_board()
        kinds = {c["kind"] for c in board["candidates"]}
        self.assertEqual(kinds, {"fund", "stock"})

    def test_index_dip_is_joined_by_benchmark(self):
        """A sectoral tech fund must pick up the Nifty IT dip, not Nifty 50."""
        self.seed_fund(name="ICICI Technology Fund", category="Technology")
        self.patch_market()
        board = self.main.get_deploy_board()
        cand = board["candidates"][0]
        self.assertEqual(cand["benchmark"], "^CNXIT")
        self.assertEqual(cand["factors"]["index_dip"]["value"], 22.0)

    def test_stock_benchmark_comes_from_its_sector(self):
        self.seed_stock()
        self.patch_market()
        board = self.main.get_deploy_board()
        self.assertEqual(board["candidates"][0]["benchmark"], "^CNXFMCG")

    def test_targets_from_settings_drive_the_underweight_factor(self):
        self.seed_fund()
        self.patch_market()
        self.main.app_settings["deploy_targets"] = {"ICICI Tech Fund": 40.0}
        board = self.main.get_deploy_board()
        cand = board["candidates"][0]
        self.assertEqual(cand["target_pct"], 40.0)
        self.assertIsNotNone(cand["factors"]["underweight"]["score"])

    def test_missing_nav_peak_degrades_to_unknown_not_zero(self):
        self.seed_fund()
        self.patch_market(nav_peak=None)
        board = self.main.get_deploy_board()
        self.assertIsNone(board["candidates"][0]["factors"]["own_drawdown"]["score"])

    def test_amount_zero_still_ranks(self):
        self.seed_fund()
        self.patch_market()
        board = self.main.get_deploy_board(amount=0)
        self.assertEqual(len(board["candidates"]), 1)
        self.assertEqual(board["suggestion"]["allocations"], [])

    def test_suggestion_balances_the_money(self):
        self.seed_fund()
        self.seed_stock()
        self.patch_market()
        board = self.main.get_deploy_board(amount=20000)
        s = board["suggestion"]
        self.assertAlmostEqual(s["allocated"] + s["unallocated"], 20000.0, places=2)

    def test_query_overrides_do_not_persist(self):
        self.seed_fund()
        self.patch_market()
        before = dict(self.main.app_settings)
        self.main.get_deploy_board(amount=20000, score_floor=99.0)
        self.assertEqual(self.main.app_settings, before)

    def test_mood_and_summary_are_attached(self):
        board = self.main.get_deploy_board()
        self.assertEqual(board["market_mood"], "falling")
        self.assertIn("below its 1-year high", board["indices_summary"])

    def test_sip_plan_is_included(self):
        fund = self.seed_fund()
        self.patch_market()
        self.main.app_settings["deploy_sip_legs"] = [
            {"id": "l1", "kind": "fund", "key": fund["scheme_name"],
             "label": fund["scheme_name"], "amount": 5000, "due_day": 5,
             "active": True}]
        board = self.main.get_deploy_board()
        self.assertEqual(len(board["sip_plan"]["legs"]), 1)


# ══════════════════════════════════════════════════════════════════════════
#  PLAN CONFIG
# ══════════════════════════════════════════════════════════════════════════

class TestDeployPlan(DeployEndpointTestCase):
    def test_get_returns_suggestions_and_valid_keys(self):
        self.seed_fund()
        self.seed_stock()
        plan = self.main.get_deploy_plan()
        self.assertEqual(plan["holdings"]["funds"], ["ICICI Tech Fund"])
        self.assertEqual(plan["holdings"]["stocks"], ["ITC.NS"])
        self.assertEqual(len(plan["suggested_legs"]), 1)
        self.assertIn("weights", plan["defaults"])

    def test_put_saves_legs_and_generates_ids(self):
        fund = self.seed_fund()
        m = self.main
        res = m.set_deploy_plan(m.DeployPlanRequest(sip_legs=[
            m.DeployLegModel(kind="fund", key=fund["scheme_name"],
                             amount=10000, due_day=5)]))
        legs = res["settings"]["deploy_sip_legs"]
        self.assertEqual(len(legs), 1)
        self.assertTrue(legs[0]["id"].startswith("leg_"))
        self.assertEqual(legs[0]["amount"], 10000.0)

    def test_put_preserves_a_supplied_id(self):
        fund = self.seed_fund()
        m = self.main
        res = m.set_deploy_plan(m.DeployPlanRequest(sip_legs=[
            m.DeployLegModel(id="leg_keepme", kind="fund",
                             key=fund["scheme_name"], amount=1000)]))
        self.assertEqual(res["settings"]["deploy_sip_legs"][0]["id"], "leg_keepme")

    def test_put_rejects_a_key_not_in_the_portfolio(self):
        m = self.main
        with self.assertRaises(m.HTTPException) as ctx:
            m.set_deploy_plan(m.DeployPlanRequest(sip_legs=[
                m.DeployLegModel(kind="fund", key="Ghost Fund", amount=1000)]))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Ghost Fund", ctx.exception.detail)

    def test_put_rejects_an_unknown_kind(self):
        self.seed_fund()
        m = self.main
        with self.assertRaises(m.HTTPException):
            m.set_deploy_plan(m.DeployPlanRequest(sip_legs=[
                m.DeployLegModel(kind="crypto", key="ICICI Tech Fund")]))

    def test_due_day_is_clamped(self):
        fund = self.seed_fund()
        m = self.main
        res = m.set_deploy_plan(m.DeployPlanRequest(sip_legs=[
            m.DeployLegModel(kind="fund", key=fund["scheme_name"], due_day=99)]))
        self.assertEqual(res["settings"]["deploy_sip_legs"][0]["due_day"], 31)

    def test_stock_leg_key_is_normalised_to_yf_symbol(self):
        self.seed_stock("ITC.NS")
        m = self.main
        res = m.set_deploy_plan(m.DeployPlanRequest(sip_legs=[
            m.DeployLegModel(kind="stock", key="ITC", amount=5000)]))
        self.assertEqual(res["settings"]["deploy_sip_legs"][0]["key"], "ITC.NS")

    def test_targets_are_clamped_and_validated(self):
        fund = self.seed_fund()
        m = self.main
        res = m.set_deploy_plan(m.DeployPlanRequest(
            targets={fund["scheme_name"]: 150.0}))
        self.assertEqual(res["settings"]["deploy_targets"][fund["scheme_name"]], 100.0)

    def test_zero_targets_are_dropped(self):
        fund = self.seed_fund()
        m = self.main
        res = m.set_deploy_plan(m.DeployPlanRequest(targets={fund["scheme_name"]: 0}))
        self.assertEqual(res["settings"]["deploy_targets"], {})

    def test_weights_are_normalised_on_save(self):
        m = self.main
        res = m.set_deploy_plan(m.DeployPlanRequest(
            weights={"own_drawdown": 3, "underweight": 1}))
        saved = res["settings"]["deploy_weights"]
        self.assertAlmostEqual(sum(saved.values()), 1.0, places=6)

    def test_partial_update_leaves_other_keys_alone(self):
        m = self.main
        m.app_settings["deploy_targets"] = {"keep": 10.0}
        m.set_deploy_plan(m.DeployPlanRequest(score_floor=50.0))
        self.assertEqual(m.app_settings["deploy_targets"], {"keep": 10.0})
        self.assertEqual(m.app_settings["deploy_score_floor"], 50.0)

    def test_empty_body_is_rejected(self):
        m = self.main
        with self.assertRaises(m.HTTPException) as ctx:
            m.set_deploy_plan(m.DeployPlanRequest())
        self.assertEqual(ctx.exception.status_code, 400)


# ══════════════════════════════════════════════════════════════════════════
#  EXECUTE
# ══════════════════════════════════════════════════════════════════════════

class TestDeployExecute(DeployEndpointTestCase):
    def _req(self, items, request_id="req-1"):
        m = self.main
        return m.DeployExecuteRequest(request_id=request_id, items=items)

    def test_records_a_fund_buy(self):
        fund = self.seed_fund(nav=145.0)
        m = self.main
        res = m.deploy_execute(self._req([
            m.DeployItem(kind="fund", key=fund["scheme_name"], amount=10000,
                         date="2026-09-20")]))
        self.assertEqual(res["status"], "recorded")
        self.assertEqual(res["totals"]["count"], 1)
        txn = fund["transactions"][-1]
        self.assertEqual(txn["invested"], 10000.0)
        self.assertEqual(txn["ref"], "deploy:req-1:0")

    def test_fund_buy_preserves_existing_cost_basis(self):
        """Ties the opening-balance guard into the deploy path."""
        fund = self.seed_fund(units=250.0, avg_nav=170.0, txns=[])
        fund["invested"] = 42500.0
        m = self.main
        m.deploy_execute(self._req([
            m.DeployItem(kind="fund", key=fund["scheme_name"], amount=10000)]))
        self.assertAlmostEqual(fund["invested"], 52500.0, places=2)

    def test_records_a_stock_buy_into_the_ledger(self):
        self.seed_stock(shares=100, avg_cost=340.0)
        m = self.main
        res = m.deploy_execute(self._req([
            m.DeployItem(kind="stock", key="ITC.NS", shares=20, price=288.0,
                         date="2026-09-20")]))
        self.assertEqual(res["status"], "recorded")
        self.assertEqual(m.user_portfolio[0]["shares"], 120)
        rows = m.user_equity_txns["ITC.NS"]
        self.assertEqual(rows[0]["trade_id"], "deploy:req-1:0")
        self.assertEqual(rows[0]["source"], "deploy")

    def test_batch_of_both_kinds(self):
        fund = self.seed_fund()
        self.seed_stock()
        m = self.main
        res = m.deploy_execute(self._req([
            m.DeployItem(kind="fund", key=fund["scheme_name"], amount=8000),
            m.DeployItem(kind="stock", key="ITC.NS", shares=10, price=288.0)]))
        self.assertEqual(res["totals"]["count"], 2)
        self.assertAlmostEqual(res["totals"]["amount"], 8000 + 2880.0, places=2)

    def test_replaying_the_same_request_id_is_a_duplicate(self):
        fund = self.seed_fund()
        m = self.main
        first = m.deploy_execute(self._req([
            m.DeployItem(kind="fund", key=fund["scheme_name"], amount=10000)]))
        second = m.deploy_execute(self._req([
            m.DeployItem(kind="fund", key=fund["scheme_name"], amount=10000)]))

        self.assertEqual(first["status"], "recorded")
        self.assertEqual(second["status"], "duplicate")
        # Only ONE real transaction was written.
        self.assertEqual(sum(1 for t in fund["transactions"]
                             if t.get("ref") == "deploy:req-1:0"), 1)
        self.assertAlmostEqual(fund["invested"], 42500.0 + 10000.0, places=2)

    def test_a_different_request_id_records_again(self):
        fund = self.seed_fund()
        m = self.main
        m.deploy_execute(self._req([m.DeployItem(
            kind="fund", key=fund["scheme_name"], amount=10000)], "req-1"))
        res = m.deploy_execute(self._req([m.DeployItem(
            kind="fund", key=fund["scheme_name"], amount=10000)], "req-2"))
        self.assertEqual(res["status"], "recorded")

    def test_whole_batch_is_rejected_when_one_item_is_bad(self):
        fund = self.seed_fund()
        m = self.main
        with self.assertRaises(m.HTTPException) as ctx:
            m.deploy_execute(self._req([
                m.DeployItem(kind="fund", key=fund["scheme_name"], amount=10000),
                m.DeployItem(kind="fund", key="Ghost Fund", amount=5000)]))
        self.assertEqual(ctx.exception.status_code, 422)
        # Nothing at all was written.
        self.assertEqual(fund["transactions"], [])
        self.assertEqual(m.user_deploy_log, [])

    def test_rejects_zero_amount_and_zero_shares(self):
        fund = self.seed_fund()
        self.seed_stock()
        m = self.main
        with self.assertRaises(m.HTTPException):
            m.deploy_execute(self._req([m.DeployItem(
                kind="fund", key=fund["scheme_name"], amount=0)]))
        with self.assertRaises(m.HTTPException):
            m.deploy_execute(self._req([m.DeployItem(
                kind="stock", key="ITC.NS", shares=0, price=100)], "req-2"))

    def test_rejects_an_unknown_kind(self):
        m = self.main
        with self.assertRaises(m.HTTPException) as ctx:
            m.deploy_execute(self._req([m.DeployItem(kind="gold", key="X",
                                                     amount=100)]))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_rejects_an_empty_batch(self):
        m = self.main
        with self.assertRaises(m.HTTPException) as ctx:
            m.deploy_execute(self._req([]))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_stock_price_is_resolved_when_not_supplied(self):
        self.seed_stock()
        m = self.main
        with mock.patch.object(m, "_fetch_price", return_value=(288.0, "test")):
            res = m.deploy_execute(self._req([
                m.DeployItem(kind="stock", key="ITC.NS", shares=10)]))
        self.assertEqual(res["recorded"][0]["price"], 288.0)

    def test_unpriceable_stock_is_rejected(self):
        self.seed_stock()
        m = self.main
        with mock.patch.object(m, "_fetch_price", return_value=(None, "none")):
            with self.assertRaises(m.HTTPException) as ctx:
                m.deploy_execute(self._req([
                    m.DeployItem(kind="stock", key="ITC.NS", shares=10)]))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_log_entry_is_written(self):
        fund = self.seed_fund()
        m = self.main
        m.deploy_execute(self._req([m.DeployItem(
            kind="fund", key=fund["scheme_name"], amount=10000)]))
        self.assertEqual(len(m.user_deploy_log), 1)
        self.assertEqual(m.user_deploy_log[0]["request_id"], "req-1")
        self.assertIn("at", m.user_deploy_log[0])


class TestDeployHistory(DeployEndpointTestCase):
    def test_newest_first_and_limited(self):
        m = self.main
        for i in range(5):
            m.user_deploy_log.append({"request_id": f"r{i}", "at": "x", "result": {}})
        hist = m.get_deploy_history(limit=3)
        self.assertEqual(hist["total"], 5)
        self.assertEqual([e["request_id"] for e in hist["entries"]],
                         ["r4", "r3", "r2"])

    def test_empty_log(self):
        hist = self.main.get_deploy_history()
        self.assertEqual(hist["entries"], [])
        self.assertEqual(hist["total"], 0)


if __name__ == "__main__":
    unittest.main()
