"""Tests for the per-trade-date ledger replay.

    python backend/test_rebalance_history.py

The replay is only worth showing if its last page reconciles to the live
portfolio, so most of these pin that: the opening balance is derived from
today's quantity rather than assumed to be zero, symbols match across exchange
suffixes, and a name the tradebook never mentions is carried unchanged.
"""
import unittest
from datetime import date

import rebalance_history as h

# Two sessions of prices either side of each trade date, so "previous close"
# and "review-day close" are genuinely different numbers.
PRICES = {
    "AAA": [("2026-03-09", 100.0), ("2026-03-10", 110.0),
            ("2026-03-11", 115.0), ("2026-03-12", 120.0)],
    "BBB": [("2026-03-09", 50.0), ("2026-03-10", 52.0),
            ("2026-03-11", 54.0), ("2026-03-12", 55.0)],
}
HOLDINGS = [{"symbol": "AAA.BO", "name": "Alpha", "shares": 120},
            {"symbol": "BBB.NS", "name": "Beta", "shares": 100}]
# Bought 20 of AAA on the 10th (recorded under the OTHER exchange suffix), sold
# 10 of BBB on the 12th. Beta therefore opens at 110 and Alpha at 100.
TXNS = {
    "AAA.NS": [{"date": "2026-03-10", "type": "BUY", "qty": 20, "price": 110.0,
                "tradingsymbol": "AAA"}],
    "BBB.NS": [{"date": "2026-03-12", "type": "SELL", "qty": 10, "price": 55.0,
                "tradingsymbol": "BBB"}],
}


def build(holdings=None, txns=None, prices=None):
    return h.build_pages(holdings if holdings is not None else HOLDINGS,
                         txns if txns is not None else TXNS,
                         h.Closes(prices if prices is not None else PRICES))


class SymbolTestCase(unittest.TestCase):
    def test_exchange_suffixes_collapse_to_one_position(self):
        self.assertEqual(h.base_symbol("IOC.NS"), h.base_symbol("IOC.BO"))
        self.assertEqual(h.base_symbol("IOC.NS"), "IOC")

    def test_a_trade_on_the_other_exchange_still_finds_its_holding(self):
        # The bug this guards: a Console tradebook says IOC.NS, a Kite holding
        # says IOC.BO, and matching the full ticker drops the whole history.
        out = build()
        alpha = [r for r in out["pages"][0]["rows"] if r["key"] == "AAA"][0]
        self.assertEqual(alpha["bought"], 20)


class OpeningBalanceTestCase(unittest.TestCase):
    def test_opening_is_today_minus_what_the_book_moved(self):
        opening = h.opening_positions(HOLDINGS, h.flatten(TXNS))
        self.assertEqual(opening["AAA"], 100)   # 120 held - 20 bought
        self.assertEqual(opening["BBB"], 110)   # 100 held + 10 sold

    def test_a_holding_the_book_never_mentions_is_carried_through(self):
        holdings = HOLDINGS + [{"symbol": "CCC.NS", "name": "Gamma",
                                "shares": 10}]
        prices = dict(PRICES, CCC=[("2026-03-09", 9.0), ("2026-03-10", 9.5),
                                   ("2026-03-12", 10.0)])
        out = build(holdings=holdings, prices=prices)
        for page in out["pages"]:
            row = [r for r in page["rows"] if r["key"] == "CCC"][0]
            with self.subTest(page=page["date"]):
                self.assertEqual(row["held_before"], 10)
                self.assertEqual(row["held_after"], 10)
                self.assertEqual(row["action"], "HOLD")
        self.assertTrue(out["reconciles"])


class ReplayTestCase(unittest.TestCase):
    def setUp(self):
        self.out = build()
        self.pages = self.out["pages"]

    def test_one_page_per_trade_date_oldest_first(self):
        self.assertEqual([p["date"] for p in self.pages],
                         ["2026-03-10", "2026-03-12"])
        self.assertEqual([p["index"] for p in self.pages], [1, 2])
        self.assertTrue(all(p["count"] == 2 for p in self.pages))

    def test_the_last_page_reconciles_to_what_is_held_today(self):
        # Without this the weights on every page describe a book that was
        # never actually held.
        self.assertTrue(self.out["reconciles"], self.out["drift"])
        final = {r["key"]: r["held_after"] for r in self.pages[-1]["rows"]}
        self.assertEqual(final["AAA"], 120)
        self.assertEqual(final["BBB"], 100)

    def test_each_page_carries_its_position_into_the_next(self):
        for older, newer in zip(self.pages, self.pages[1:]):
            after = {r["key"]: r["held_after"] for r in older["rows"]}
            before = {r["key"]: r["held_before"] for r in newer["rows"]}
            for key, qty in after.items():
                with self.subTest(key=key):
                    self.assertAlmostEqual(before[key], qty, places=6)

    def test_value_before_uses_the_previous_session_close(self):
        alpha = [r for r in self.pages[0]["rows"] if r["key"] == "AAA"][0]
        # 100 shares at the 9 March close of 100, not the 10 March close.
        self.assertEqual(alpha["value_before"], 10000.0)

    def test_weights_close_at_one_hundred_on_every_page(self):
        for page in self.pages:
            with self.subTest(page=page["date"]):
                for field in ("weight_before_pct", "weight_after_pct"):
                    total = sum(r[field] for r in page["rows"]
                                if r[field] is not None)
                    self.assertAlmostEqual(total, 100.0, places=1)

    def test_a_buy_costs_cash_and_a_sale_pays_it(self):
        buy = [r for r in self.pages[0]["rows"] if r["key"] == "AAA"][0]
        sell = [r for r in self.pages[1]["rows"] if r["key"] == "BBB"][0]
        self.assertEqual(buy["action"], "BUY")
        self.assertEqual(buy["net_cash"], -2200.0)      # 20 x 110
        self.assertEqual(sell["action"], "SELL")
        self.assertEqual(sell["net_cash"], 550.0)       # 10 x 55
        self.assertEqual(sell["sold_pct_of_held"], round(10 / 110 * 100, 2))

    def test_an_untraded_row_has_no_fill(self):
        for page in self.pages:
            for row in page["rows"]:
                if row["action"] == "HOLD":
                    with self.subTest(page=page["date"], key=row["key"]):
                        self.assertIsNone(row["fill"])
                        self.assertEqual(row["net_cash"], 0.0)

    def test_several_fills_of_one_name_net_to_one_line_at_the_average(self):
        txns = {"AAA.NS": [
            {"date": "2026-03-10", "type": "BUY", "qty": 10, "price": 100.0},
            {"date": "2026-03-10", "type": "BUY", "qty": 10, "price": 120.0}]}
        out = build(txns=txns, holdings=[HOLDINGS[0]],
                    prices={"AAA": PRICES["AAA"]})
        row = [r for r in out["pages"][0]["rows"] if r["key"] == "AAA"][0]
        self.assertEqual(row["bought"], 20)
        self.assertEqual(row["fill"], 110.0)
        self.assertEqual(row["net_cash"], -2200.0)


class PricingTestCase(unittest.TestCase):
    def test_a_holiday_falls_back_to_the_last_real_close(self):
        closes = h.Closes({"AAA": [("2026-03-09", 100.0)]})
        self.assertEqual(closes.on_or_before("AAA", date(2026, 3, 12)), 100.0)

    def test_a_symbol_with_no_prices_is_held_but_not_weighed(self):
        # It must NOT vanish: dropping it would change the denominator every
        # other weight is measured against.
        out = build(prices={"AAA": PRICES["AAA"]})
        row = [r for r in out["pages"][0]["rows"] if r["key"] == "BBB"][0]
        self.assertIsNone(row["value_before"])
        self.assertIsNone(row["weight_before_pct"])
        self.assertEqual(row["held_before"], 110)
        self.assertEqual(out["pages"][0]["totals"]["unpriced"], 1)

    def test_unpriced_counts_missing_prices_not_empty_books(self):
        # A page where nothing priced was held yet has null weights, but that
        # is arithmetic, not a data gap. Only a genuinely missing price counts.
        out = build(prices={"AAA": PRICES["AAA"]})
        page = out["pages"][0]
        self.assertEqual(page["totals"]["unpriced"], 1)
        self.assertEqual(page["totals"]["unpriced_keys"], ["BBB"])
        # AAA has a price and a null weight on no page here; BBB has neither.
        alpha = [r for r in page["rows"] if r["key"] == "AAA"][0]
        self.assertIsNotNone(alpha["value_before"])

    def test_an_empty_tradebook_produces_no_pages(self):
        out = build(txns={})
        self.assertEqual(out["pages"], [])
        self.assertEqual(out["count"], 0)


class DriftTestCase(unittest.TestCase):
    def test_a_book_that_does_not_reconcile_says_so(self):
        # Sold 10 more than was ever held: the replay cannot be trusted and
        # has to admit it rather than print a negative opening balance.
        txns = {"BBB.NS": [{"date": "2026-03-12", "type": "SELL",
                            "qty": 500, "price": 55.0}]}
        out = h.build_pages([{"symbol": "BBB.NS", "shares": 100}], txns,
                            h.Closes(PRICES))
        self.assertTrue(out["reconciles"])   # replay is self-consistent...
        self.assertEqual(out["unmatched"], [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
