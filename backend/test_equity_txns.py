"""
Unit tests for the equity transaction ledger and its XIRR.

    python -m unittest test_equity_txns -v

No network, no Kite — every trade is hand-fed and every ``as_of`` is pinned,
so the annualised numbers are deterministic.
"""

import unittest
from datetime import datetime

import equity_txns as et

AS_OF = datetime(2026, 8, 28)


def buy(date, qty, price):
    return {"symbol": "X.NS", "date": date, "type": "BUY", "qty": qty,
            "price": price, "amount": round(qty * price, 2)}


def sell(date, qty, price):
    return {**buy(date, qty, price), "type": "SELL"}


class TestParseDate(unittest.TestCase):
    def test_accepts_the_shapes_kite_actually_sends(self):
        for raw in ("2026-08-28", "2026-08-28 15:04:05", "2026-08-28T15:04:05",
                    "28-08-2026", "2026/08/28"):
            self.assertEqual(et.parse_date(raw).date(), datetime(2026, 8, 28).date(), raw)

    def test_strips_timezone_offset(self):
        self.assertEqual(et.parse_date("2026-08-28T15:04:05+05:30").date(),
                         datetime(2026, 8, 28).date())

    def test_rejects_junk_and_zero_dates(self):
        # Kite sends "0000-00-00" for an unset authorised_date; it must not
        # become a 1st-century cashflow that wrecks the rate.
        for raw in (None, "", "  ", "0000-00-00", "not a date"):
            self.assertIsNone(et.parse_date(raw))


class TestNormalizeKiteTrade(unittest.TestCase):
    def yf(self, sym, exchange="NSE"):
        return f"{sym}.NS" if exchange == "NSE" else f"{sym}.BO"

    def test_maps_a_full_trade(self):
        row = et.normalize_kite_trade({
            "tradingsymbol": "RELIANCE", "exchange": "NSE",
            "transaction_type": "BUY", "quantity": 10, "average_price": 2340.5,
            "fill_timestamp": "2023-04-12 10:15:00", "trade_id": "77",
        }, self.yf)
        self.assertEqual(row["symbol"], "RELIANCE.NS")
        self.assertEqual(row["date"], "2023-04-12")
        self.assertEqual(row["type"], "BUY")
        self.assertEqual(row["amount"], 23405.0)
        self.assertEqual(row["trade_id"], "77")

    def test_falls_back_through_the_date_keys(self):
        row = et.normalize_kite_trade({
            "tradingsymbol": "TCS", "quantity": 5, "average_price": 3180.0,
            "trade_date": "2022-11-03",
        }, self.yf)
        self.assertEqual(row["date"], "2022-11-03")

    def test_sell_side_is_recognised(self):
        row = et.normalize_kite_trade({
            "tradingsymbol": "TCS", "quantity": 5, "average_price": 3180.0,
            "trade_date": "2022-11-03", "transaction_type": "SELL",
        }, self.yf)
        self.assertEqual(row["type"], "SELL")

    def test_drops_unusable_rows(self):
        base = {"tradingsymbol": "TCS", "quantity": 5, "average_price": 3180.0,
                "trade_date": "2022-11-03"}
        self.assertIsNone(et.normalize_kite_trade({**base, "tradingsymbol": ""}, self.yf))
        self.assertIsNone(et.normalize_kite_trade({**base, "trade_date": None}, self.yf))
        self.assertIsNone(et.normalize_kite_trade({**base, "quantity": 0}, self.yf))
        self.assertIsNone(et.normalize_kite_trade({**base, "average_price": 0}, self.yf))
        self.assertIsNone(et.normalize_kite_trade("not a dict", self.yf))


class TestMergeTrades(unittest.TestCase):
    def test_merge_is_idempotent_on_trade_id(self):
        # Kite's tradebook is re-pulled on every sync; a second pull of the same
        # fills must not double the ledger.
        rows = [{**buy("2024-01-08", 5, 2710.0), "trade_id": "1"}]
        store = {}
        self.assertEqual(et.merge_trades(store, rows), 1)
        self.assertEqual(et.merge_trades(store, rows), 0)
        self.assertEqual(len(store["X.NS"]), 1)

    def test_dedupes_on_economics_when_there_is_no_trade_id(self):
        rows = [buy("2024-01-08", 5, 2710.0)]
        store = {}
        et.merge_trades(store, rows)
        et.merge_trades(store, rows)
        self.assertEqual(len(store["X.NS"]), 1)

    def test_distinct_trades_same_day_both_land(self):
        store = {}
        et.merge_trades(store, [{**buy("2024-01-08", 5, 2710.0), "trade_id": "1"},
                                {**buy("2024-01-08", 5, 2710.0), "trade_id": "2"}])
        self.assertEqual(len(store["X.NS"]), 2)

    def test_rows_end_up_sorted_by_date(self):
        store = {}
        et.merge_trades(store, [buy("2024-01-08", 5, 2710.0)])
        et.merge_trades(store, [buy("2023-04-12", 10, 2340.5)])
        self.assertEqual([r["date"] for r in store["X.NS"]],
                         ["2023-04-12", "2024-01-08"])


class TestCashflowSigns(unittest.TestCase):
    def test_buys_are_outflows_and_sells_are_inflows(self):
        flows = et.cashflows([buy("2023-04-12", 10, 100.0), sell("2024-04-12", 4, 150.0)])
        self.assertEqual([amt for _, amt in flows], [-1000.0, 600.0])

    def test_flows_come_back_in_date_order(self):
        flows = et.cashflows([buy("2024-01-08", 5, 100.0), buy("2023-04-12", 10, 100.0)])
        self.assertEqual([d.year for d, _ in flows], [2023, 2024])


class TestXirrFor(unittest.TestCase):
    def test_exact_coverage_solves_a_known_rate(self):
        # 100 shares at 100 on 2024-08-28, worth 121 each exactly two years on.
        # 1.21x over 2y is 10% a year - a hand-checkable end-to-end solve.
        res = et.xirr_for([buy("2024-08-28", 100, 100.0)],
                          current_value=12100.0, held_qty=100, as_of=AS_OF)
        self.assertEqual(res["basis"], "exact")
        self.assertTrue(res["exact"])
        self.assertAlmostEqual(res["xirr"], 10.0, delta=0.1)

    def test_a_doubling_in_one_year_is_a_hundred_percent(self):
        res = et.xirr_for([buy("2025-08-28", 10, 100.0)],
                          current_value=2000.0, held_qty=10, as_of=AS_OF)
        self.assertAlmostEqual(res["xirr"], 100.0, delta=0.2)

    def test_a_later_buy_at_a_higher_price_drags_the_rate_below_the_first_lot(self):
        early = et.xirr_for([buy("2024-08-28", 10, 100.0)], 2000.0, 10, as_of=AS_OF)
        added = et.xirr_for([buy("2024-08-28", 10, 100.0), buy("2026-02-28", 10, 190.0)],
                            4000.0, 20, as_of=AS_OF)
        self.assertLess(added["xirr"], early["xirr"])

    def test_no_transactions_yields_no_number(self):
        res = et.xirr_for([], current_value=45000.0, held_qty=15)
        self.assertIsNone(res["xirr"])
        self.assertEqual(res["basis"], "none")

    def test_partial_coverage_is_seeded_and_flagged(self):
        # Ledger covers 15 of 25 held shares. A number comes back, but it is
        # marked inexact because the missing 10 were anchored on a guessed date.
        txns = [buy("2023-04-12", 10, 2340.5), buy("2024-01-08", 5, 2710.0)]
        res = et.xirr_for(txns, current_value=75000.0, held_qty=25,
                          avg_cost=2463.5, as_of=AS_OF)
        self.assertEqual(res["basis"], "partial")
        self.assertFalse(res["exact"])
        self.assertIsNotNone(res["xirr"])
        self.assertEqual(res["covered_qty"], 15.0)

    def test_partial_coverage_without_avg_cost_refuses_to_guess(self):
        res = et.xirr_for([buy("2023-04-12", 10, 2340.5)],
                          current_value=75000.0, held_qty=25, avg_cost=0)
        self.assertIsNone(res["xirr"])
        self.assertEqual(res["basis"], "partial")

    def test_small_quantity_drift_still_counts_as_exact(self):
        # A bonus or fractional share must not knock a complete ledger into the
        # flagged path.
        res = et.xirr_for([buy("2024-08-28", 100, 100.0)],
                          current_value=12100.0, held_qty=101, avg_cost=100.0,
                          as_of=AS_OF)
        self.assertEqual(res["basis"], "exact")

    def test_zero_value_or_zero_qty_yields_nothing(self):
        txns = [buy("2024-08-28", 10, 100.0)]
        self.assertIsNone(et.xirr_for(txns, 0, 10)["xirr"])
        self.assertIsNone(et.xirr_for(txns, 1000.0, 0)["xirr"])

    def test_a_flat_position_reports_zero_not_missing(self):
        # Bought and unchanged: 0% is the right answer, and must not be confused
        # with the non-convergence case that also produces 0.
        res = et.xirr_for([buy("2024-08-28", 10, 100.0)],
                          current_value=1000.0, held_qty=10, as_of=AS_OF)
        self.assertEqual(res["basis"], "exact")
        self.assertEqual(res["xirr"], 0)


class TestPortfolioXirr(unittest.TestCase):
    def holding(self, symbol, shares, value):
        return {"symbol": symbol, "shares": shares, "total_value": value}

    def test_pools_covered_holdings_into_one_rate(self):
        store = {
            "A.NS": [{**buy("2025-08-28", 10, 100.0), "symbol": "A.NS"}],
            "B.NS": [{**buy("2025-08-28", 10, 100.0), "symbol": "B.NS"}],
        }
        res = et.portfolio_xirr(store, [self.holding("A.NS", 10, 2000.0),
                                        self.holding("B.NS", 10, 2000.0)], as_of=AS_OF)
        self.assertAlmostEqual(res["xirr"], 100.0, delta=0.2)
        self.assertEqual(res["covered_pct"], 100.0)

    def test_uncovered_holdings_are_excluded_from_both_rate_and_coverage(self):
        # The book figure must not quietly fold an un-dated position's value
        # into the terminal amount — that would inflate the rate.
        store = {"A.NS": [{**buy("2025-08-28", 10, 100.0), "symbol": "A.NS"}]}
        res = et.portfolio_xirr(store, [self.holding("A.NS", 10, 2000.0),
                                        self.holding("B.NS", 50, 2000.0)], as_of=AS_OF)
        self.assertEqual(res["covered_symbols"], ["A.NS"])
        self.assertEqual(res["covered_value"], 2000.0)
        self.assertEqual(res["total_value"], 4000.0)
        self.assertEqual(res["covered_pct"], 50.0)
        self.assertAlmostEqual(res["xirr"], 100.0, delta=0.2)

    def test_partially_covered_holdings_do_not_contribute(self):
        store = {"A.NS": [{**buy("2025-08-28", 10, 100.0), "symbol": "A.NS"}]}
        res = et.portfolio_xirr(store, [self.holding("A.NS", 40, 8000.0)], as_of=AS_OF)
        self.assertIsNone(res["xirr"])
        self.assertEqual(res["covered_pct"], 0.0)

    def test_empty_book_is_not_an_error(self):
        res = et.portfolio_xirr({}, [])
        self.assertIsNone(res["xirr"])
        self.assertEqual(res["covered_symbols"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
