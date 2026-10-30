"""
Regression tests for the two shared portfolio write helpers.

    python -m unittest test_write_helpers -v

Both helpers exist to fix bugs that silently corrupted data:

* ``_upsert_holding`` — ``/api/portfolio/add`` used to write only
  ``portfolio.json``, so a manually added holding never entered the dated
  ledger and its XIRR stayed unsolvable forever.
* ``_seed_opening_balance`` — ``_recalc_mf_fund`` rebuilds a fund's totals from
  its transaction list alone, so the first top-up on a Kite-synced fund (which
  arrives with a real ``invested`` but no transactions) used to wipe the whole
  cost basis.

Disk writes and price lookups are stubbed, so these run offline.
"""

import unittest
from datetime import datetime
from unittest import mock


class WriteHelperTestCase(unittest.TestCase):
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
        }
        m.user_portfolio.clear()
        m.user_mf_portfolio.clear()
        m.user_equity_txns.clear()

        # Never touch disk from a test.
        for name in ("_save_portfolio", "_save_mf_portfolio", "_save_equity_txns"):
            patcher = mock.patch.object(m, name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        m = self.main
        m.user_portfolio[:] = self._saved["portfolio"]
        m.user_mf_portfolio[:] = self._saved["mf"]
        m.user_equity_txns.clear()
        m.user_equity_txns.update(self._saved["txns"])


# ══════════════════════════════════════════════════════════════════════════
#  BUG 1 — manual equity buys never reached the ledger
# ══════════════════════════════════════════════════════════════════════════

class TestUpsertHolding(WriteHelperTestCase):
    def test_new_holding_is_created_and_ledgered(self):
        m = self.main
        res = m._upsert_holding("ITC.NS", 10, 400.0, date="2026-09-03")

        self.assertEqual(res["status"], "added")
        self.assertEqual(m.user_portfolio[0]["shares"], 10)
        self.assertEqual(m.user_portfolio[0]["avg_cost"], 400.0)

        rows = m.user_equity_txns["ITC.NS"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "BUY")
        self.assertEqual(rows[0]["qty"], 10)
        self.assertEqual(rows[0]["price"], 400.0)
        self.assertEqual(rows[0]["amount"], 4000.0)
        self.assertEqual(rows[0]["date"], "2026-09-03")
        self.assertEqual(rows[0]["source"], "manual")
        self.assertEqual(rows[0]["tradingsymbol"], "ITC")

    def test_topping_up_weight_averages_and_appends_a_second_row(self):
        m = self.main
        m._upsert_holding("ITC.NS", 10, 400.0, date="2026-08-01")
        res = m._upsert_holding("ITC.NS", 10, 500.0, date="2026-09-01")

        self.assertEqual(res["status"], "updated")
        self.assertEqual(m.user_portfolio[0]["shares"], 20)
        self.assertEqual(m.user_portfolio[0]["avg_cost"], 450.0)
        self.assertEqual(len(m.user_equity_txns["ITC.NS"]), 2)

    def test_two_identical_same_day_buys_are_both_recorded(self):
        """The dedupe key falls back to economics, so the ids must differ."""
        m = self.main
        m._upsert_holding("ITC.NS", 5, 400.0, date="2026-09-03")
        m._upsert_holding("ITC.NS", 5, 400.0, date="2026-09-03")
        self.assertEqual(len(m.user_equity_txns["ITC.NS"]), 2)
        self.assertEqual(m.user_portfolio[0]["shares"], 10)

    def test_same_trade_id_is_idempotent(self):
        m = self.main
        m._upsert_holding("ITC.NS", 5, 400.0, date="2026-09-03", trade_id="deploy:abc:0")
        second = m._upsert_holding("ITC.NS", 5, 400.0, date="2026-09-03",
                                   trade_id="deploy:abc:0")
        # The ledger refuses the duplicate row...
        self.assertEqual(len(m.user_equity_txns["ITC.NS"]), 1)
        self.assertEqual(second["ledger_rows_added"], 0)
        # ...which is precisely why the deploy endpoint must guard the whole
        # request before calling this, not rely on the ledger alone.

    def test_zero_price_writes_no_ledger_row(self):
        """A zero-price row would poison the XIRR solve it exists to feed."""
        m = self.main
        res = m._upsert_holding("ITC.NS", 10, 0.0)
        self.assertEqual(m.user_portfolio[0]["shares"], 10)
        self.assertEqual(m.user_equity_txns, {})
        self.assertEqual(res["ledger_rows_added"], 0)

    def test_ledger_row_is_xirr_solvable(self):
        """The end this whole fix serves: a manual buy must produce an XIRR."""
        import equity_txns
        m = self.main
        m._upsert_holding("ITC.NS", 100, 400.0, date="2025-09-03")
        rows = m.user_equity_txns["ITC.NS"]

        self.assertEqual(equity_txns.net_qty(rows), 100)
        result = equity_txns.xirr_for(rows, current_value=48000.0, held_qty=100,
                                      avg_cost=400.0)
        self.assertEqual(result["basis"], "exact")
        self.assertIsNotNone(result["xirr"])
        self.assertGreater(result["xirr"], 0)   # 40000 -> 48000 over a year

    def test_steep_recent_loss_is_xirr_solvable(self):
        """A valid negative rate must not disappear when Newton overshoots -1."""
        import equity_txns
        rows = [{
            "date": "2026-03-10",
            "type": "BUY",
            "qty": 10,
            "price": 700.0,
            "amount": 7000.0,
        }]
        result = equity_txns.xirr_for(
            rows,
            current_value=2700.0,
            held_qty=10,
            avg_cost=700.0,
            as_of=datetime(2026, 9, 4),
        )
        self.assertEqual(result["basis"], "exact")
        self.assertIsNotNone(result["xirr"])
        self.assertLess(result["xirr"], 0)


class TestAddToPortfolioEndpoint(WriteHelperTestCase):
    """The public endpoint must inherit the ledger write, not bypass it."""

    def test_endpoint_writes_the_ledger(self):
        m = self.main
        with mock.patch.object(m, "_fetch_price", return_value=(400.0, "test")):
            res = m.add_to_portfolio(m.AddStockRequest(symbol="ITC", shares=10))

        self.assertEqual(res["status"], "added")
        self.assertEqual(res["new_shares"], 10)
        self.assertIn("ITC.NS", m.user_equity_txns)
        self.assertEqual(m.user_equity_txns["ITC.NS"][0]["price"], 400.0)

    def test_endpoint_response_shape_is_unchanged(self):
        """Existing clients read exactly these three keys."""
        m = self.main
        with mock.patch.object(m, "_fetch_price", return_value=(400.0, "test")):
            res = m.add_to_portfolio(
                m.AddStockRequest(symbol="ITC", shares=10, avg_cost=390.0))
        self.assertEqual(set(res), {"status", "symbol", "new_shares"})

    def test_explicit_avg_cost_is_used_verbatim(self):
        m = self.main
        m.add_to_portfolio(m.AddStockRequest(symbol="ITC", shares=10, avg_cost=350.0))
        self.assertEqual(m.user_portfolio[0]["avg_cost"], 350.0)
        self.assertEqual(m.user_equity_txns["ITC.NS"][0]["price"], 350.0)


# ══════════════════════════════════════════════════════════════════════════
#  BUG 2 — the first top-up wiped a synced fund's cost basis
# ══════════════════════════════════════════════════════════════════════════

def _synced_fund(**over):
    """A Kite-synced fund: real money in it, no transaction history."""
    fund = {
        "scheme_name": "Parag Parikh Flexi Cap Direct Growth",
        "category": "Flexi Cap",
        "invested": 300000.0,
        "current_value": 360000.0,
        "units": 5000.0,
        "nav": 72.0,
        "avg_nav": 60.0,
        "transactions": [],
    }
    fund.update(over)
    return fund


class TestOpeningBalanceGuard(WriteHelperTestCase):
    def test_top_up_preserves_existing_cost_basis(self):
        """THE regression: without the guard, invested became 10000."""
        m = self.main
        fund = _synced_fund()
        m.user_mf_portfolio.append(fund)

        m.add_mf_transaction(m.MFTransactionRequest(
            scheme_name=fund["scheme_name"], date="2026-09-03",
            invested=10000.0, redeemed=0, units=138.889, nav=72.0))

        self.assertAlmostEqual(fund["invested"], 310000.0, places=2)
        self.assertAlmostEqual(fund["units"], 5138.889, places=3)
        self.assertNotEqual(fund["invested"], 10000.0)

    def test_opening_row_is_seeded_and_marked(self):
        m = self.main
        fund = _synced_fund()
        m.user_mf_portfolio.append(fund)
        result = m._append_mf_txn(fund, {"date": "2026-09-03", "invested": 10000.0,
                                         "redeemed": 0, "units": 138.889, "nav": 72.0})

        self.assertTrue(result["seeded_opening_balance"])
        self.assertEqual(len(fund["transactions"]), 2)
        opening = fund["transactions"][0]
        self.assertEqual(opening["ref"], "opening-balance")
        self.assertTrue(opening["seeded"])
        self.assertEqual(opening["invested"], 300000.0)
        self.assertEqual(opening["units"], 5000.0)

    def test_opening_row_sorts_before_real_transactions(self):
        m = self.main
        fund = _synced_fund()
        m.user_mf_portfolio.append(fund)
        m._append_mf_txn(fund, {"date": "2020-01-01", "invested": 5000.0,
                                "redeemed": 0, "units": 100.0, "nav": 50.0})
        self.assertEqual(fund["transactions"][0]["ref"], "opening-balance")

    def test_avg_nav_is_recomputed_correctly_after_seeding(self):
        m = self.main
        fund = _synced_fund()
        m.user_mf_portfolio.append(fund)
        m._append_mf_txn(fund, {"date": "2026-09-03", "invested": 10000.0,
                                "redeemed": 0, "units": 138.889, "nav": 72.0})
        # 310000 / 5138.889 units
        self.assertAlmostEqual(fund["avg_nav"], 60.3243, places=3)

    def test_seeding_happens_only_once(self):
        m = self.main
        fund = _synced_fund()
        m.user_mf_portfolio.append(fund)
        first = m._append_mf_txn(fund, {"date": "2026-09-03", "invested": 10000.0,
                                        "redeemed": 0, "units": 138.889, "nav": 72.0})
        second = m._append_mf_txn(fund, {"date": "2026-10-03", "invested": 10000.0,
                                         "redeemed": 0, "units": 138.889, "nav": 72.0})
        self.assertTrue(first["seeded_opening_balance"])
        self.assertFalse(second["seeded_opening_balance"])
        self.assertEqual(sum(1 for t in fund["transactions"]
                             if t.get("ref") == "opening-balance"), 1)
        self.assertAlmostEqual(fund["invested"], 320000.0, places=2)

    def test_fund_with_existing_transactions_is_untouched(self):
        m = self.main
        fund = _synced_fund(transactions=[
            {"date": "2025-01-01", "invested": 300000.0, "redeemed": 0,
             "units": 5000.0, "nav": 60.0}])
        m.user_mf_portfolio.append(fund)
        result = m._append_mf_txn(fund, {"date": "2026-09-03", "invested": 10000.0,
                                         "redeemed": 0, "units": 138.889, "nav": 72.0})
        self.assertFalse(result["seeded_opening_balance"])
        self.assertEqual(len(fund["transactions"]), 2)
        self.assertAlmostEqual(fund["invested"], 310000.0, places=2)

    def test_brand_new_empty_fund_is_not_seeded(self):
        """Nothing to preserve — seeding would invent a phantom position."""
        m = self.main
        fund = _synced_fund(invested=0, units=0, current_value=0, avg_nav=0)
        m.user_mf_portfolio.append(fund)
        result = m._append_mf_txn(fund, {"date": "2026-09-03", "invested": 10000.0,
                                         "redeemed": 0, "units": 138.889, "nav": 72.0})
        self.assertFalse(result["seeded_opening_balance"])
        self.assertEqual(len(fund["transactions"]), 1)
        self.assertAlmostEqual(fund["invested"], 10000.0, places=2)

    def test_seeded_nav_falls_back_when_avg_nav_missing(self):
        m = self.main
        fund = _synced_fund(avg_nav=0)
        m.user_mf_portfolio.append(fund)
        m._append_mf_txn(fund, {"date": "2026-09-03", "invested": 10000.0,
                                "redeemed": 0, "units": 138.889, "nav": 72.0})
        # Falls back to the fund's current nav rather than writing a zero.
        self.assertGreater(fund["transactions"][0]["nav"], 0)

    def test_unknown_fund_still_404s(self):
        m = self.main
        with self.assertRaises(m.HTTPException) as ctx:
            m.add_mf_transaction(m.MFTransactionRequest(
                scheme_name="Nope", date="2026-09-03", invested=1000.0,
                redeemed=0, units=10.0, nav=100.0))
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
