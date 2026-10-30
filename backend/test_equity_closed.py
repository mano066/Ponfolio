import unittest
from datetime import datetime

import equity_closed
import equity_txns


def buy(date, qty, price, symbol="TEST.NS", exchange="NSE", tid=None):
    return {"symbol": symbol, "date": date, "type": "BUY", "qty": qty,
            "price": price, "amount": qty * price, "exchange": exchange,
            "trade_id": tid or f"b{date}{qty}{price}"}


def sell(date, qty, price, symbol="TEST.NS", exchange="NSE", tid=None):
    return {"symbol": symbol, "date": date, "type": "SELL", "qty": qty,
            "price": price, "amount": qty * price, "exchange": exchange,
            "trade_id": tid or f"s{date}{qty}{price}"}


class FifoTests(unittest.TestCase):
    def test_oldest_lot_is_consumed_first(self):
        m = equity_closed.match_fifo([
            buy("2024-01-01", 10, 100.0),
            buy("2024-06-01", 10, 200.0),
            sell("2024-12-01", 10, 250.0),
        ])
        self.assertEqual(len(m["lots"]), 1)
        lot = m["lots"][0]
        # The 100-rupee lot must be the one sold, not the 200-rupee one.
        self.assertEqual(lot["buy_price"], 100.0)
        self.assertEqual(lot["gross_pnl"], 1500.0)
        self.assertEqual(m["open_qty"], 10)

    def test_one_sell_splits_across_several_buys(self):
        m = equity_closed.match_fifo([
            buy("2024-01-01", 5, 100.0),
            buy("2024-02-01", 5, 120.0),
            sell("2024-03-01", 10, 150.0),
        ])
        self.assertEqual(len(m["lots"]), 2)
        self.assertEqual([l["qty"] for l in m["lots"]], [5, 5])
        self.assertEqual(sum(l["gross_pnl"] for l in m["lots"]), 400.0)
        self.assertEqual(m["open_qty"], 0)

    def test_partial_sell_leaves_the_rest_open(self):
        m = equity_closed.match_fifo([
            buy("2024-01-01", 10, 100.0),
            sell("2024-02-01", 4, 130.0),
        ])
        self.assertEqual(m["lots"][0]["qty"], 4)
        self.assertEqual(m["open_qty"], 6)
        self.assertEqual(m["open_cost"], 600.0)

    def test_sell_with_no_buy_is_reported_not_invented(self):
        m = equity_closed.match_fifo([sell("2024-02-01", 7, 130.0)])
        self.assertEqual(m["lots"], [])
        self.assertEqual(m["unmatched_sell_qty"], 7)

    def test_holding_period_decides_the_term(self):
        short = equity_closed.match_fifo([
            buy("2024-01-01", 1, 100.0), sell("2024-06-01", 1, 110.0)])
        long_ = equity_closed.match_fifo([
            buy("2023-01-01", 1, 100.0), sell("2024-06-01", 1, 110.0)])
        self.assertEqual(short["lots"][0]["term"], "short")
        self.assertEqual(long_["lots"][0]["term"], "long")

    def test_366_days_is_long_term_365_is_not(self):
        edge = equity_closed.match_fifo([
            buy("2024-01-01", 1, 100.0), sell("2024-12-31", 1, 110.0)])
        over = equity_closed.match_fifo([
            buy("2024-01-01", 1, 100.0), sell("2025-01-02", 1, 110.0)])
        self.assertEqual(edge["lots"][0]["days_held"], 365)
        self.assertEqual(edge["lots"][0]["term"], "short")
        self.assertEqual(over["lots"][0]["term"], "long")


class ChargeTests(unittest.TestCase):
    def test_buy_side_carries_stamp_duty_and_sell_side_does_not(self):
        b = equity_closed.side_charges(100000, side="BUY")
        s = equity_closed.side_charges(100000, side="SELL")
        self.assertEqual(b["stamp_duty"], 15.0)     # 0.015%
        self.assertEqual(s["stamp_duty"], 0.0)
        self.assertEqual(b["stt"], 100.0)           # 0.1% both sides
        self.assertEqual(s["stt"], 100.0)

    def test_bse_transaction_fee_exceeds_nse(self):
        nse = equity_closed.side_charges(100000, side="SELL", exchange="NSE")
        bse = equity_closed.side_charges(100000, side="SELL", exchange="BSE")
        self.assertGreater(bse["exchange"], nse["exchange"])

    def test_gst_applies_to_fees_not_to_stt_or_stamp(self):
        c = equity_closed.side_charges(100000, side="BUY")
        expected = round((c["brokerage"] + c["exchange"] + c["sebi"]) * 0.18, 2)
        self.assertEqual(c["gst"], expected)

    def test_zero_turnover_costs_nothing(self):
        self.assertEqual(equity_closed.side_charges(0, side="BUY")["total"], 0.0)

    def test_net_is_gross_minus_charges(self):
        book = equity_closed.closed_positions({"TEST.NS": [
            buy("2024-01-01", 10, 100.0), sell("2024-06-01", 10, 150.0)]})
        t = book["totals"]
        self.assertEqual(t["gross_pnl"], 500.0)
        self.assertGreater(t["charges_estimated"], 0)
        self.assertEqual(t["net_pnl_estimated"],
                         round(t["gross_pnl"] - t["charges_estimated"], 2))
        self.assertLess(t["net_pnl_estimated"], t["gross_pnl"])

    def test_one_dp_charge_per_sell_day_not_per_lot(self):
        # Two buys closed by ONE sell on one day: one DP charge, not two.
        book = equity_closed.closed_positions({"TEST.NS": [
            buy("2024-01-01", 5, 100.0), buy("2024-02-01", 5, 100.0),
            sell("2024-06-01", 10, 150.0)]})
        self.assertEqual(book["symbols"][0]["trades"], 2)
        self.assertEqual(book["symbols"][0]["dp_charges_estimated"],
                         equity_closed.dp_charge())


class BookTests(unittest.TestCase):
    def test_both_exchange_suffixes_are_one_position(self):
        # Bought on BSE, sold on NSE. Two ledger buckets, one round trip.
        book = equity_closed.closed_positions({
            "TEST.BO": [buy("2024-01-01", 10, 100.0, symbol="TEST.BO",
                            exchange="BSE")],
            "TEST.NS": [sell("2024-06-01", 10, 150.0)],
        })
        self.assertEqual(book["totals"]["symbols_closed"], 1)
        self.assertEqual(book["symbols"][0]["symbol"], "TEST")
        self.assertEqual(book["totals"]["gross_pnl"], 500.0)

    def test_a_position_never_sold_is_absent(self):
        book = equity_closed.closed_positions({
            "TEST.NS": [buy("2024-01-01", 10, 100.0)]})
        self.assertEqual(book["symbols"], [])
        self.assertEqual(book["totals"]["trades"], 0)
        self.assertIsNone(book["totals"]["win_rate_pct"])

    def test_wins_and_losses_are_counted_after_charges(self):
        book = equity_closed.closed_positions({
            "WIN.NS": [buy("2024-01-01", 10, 100.0), sell("2024-06-01", 10, 150.0)],
            "LOSS.NS": [buy("2024-01-01", 10, 100.0), sell("2024-06-01", 10, 50.0)],
        })
        t = book["totals"]
        self.assertEqual((t["wins"], t["losses"]), (1, 1))
        self.assertEqual(t["win_rate_pct"], 50.0)

    def test_ltcg_exemption_is_applied_before_tax(self):
        # A long-term gain under the exemption must attract no LTCG.
        book = equity_closed.closed_positions({"TEST.NS": [
            buy("2022-01-01", 100, 100.0), sell("2024-06-01", 100, 200.0)]})
        tax = book["tax_indicative"]
        self.assertEqual(tax["short_term_gain"], 0.0)
        self.assertGreater(tax["long_term_gain"], 0)
        if tax["long_term_gain"] <= equity_closed.TAX["ltcg_exemption"]:
            self.assertEqual(tax["tax"], 0.0)

    def test_short_term_gain_is_taxed_at_the_stcg_rate(self):
        book = equity_closed.closed_positions({"TEST.NS": [
            buy("2024-01-01", 100, 100.0), sell("2024-06-01", 100, 200.0)]})
        tax = book["tax_indicative"]
        net_short = book["totals"]["short_term_net"]
        self.assertEqual(tax["tax"], round(net_short * 0.20, 2))

    def test_a_loss_is_never_taxed(self):
        book = equity_closed.closed_positions({"TEST.NS": [
            buy("2024-01-01", 10, 200.0), sell("2024-06-01", 10, 100.0)]})
        self.assertEqual(book["tax_indicative"]["tax"], 0.0)
        self.assertLess(book["totals"]["net_pnl_estimated"], 0)

    def test_charge_and_tax_bases_are_disclosed(self):
        book = equity_closed.closed_positions({})
        self.assertIn("rates", book["charges_basis"])
        self.assertIn("not a tax computation",
                      book["tax_indicative"]["basis"].lower())

    def test_empty_ledger_is_a_clean_empty_answer(self):
        book = equity_closed.closed_positions({})
        self.assertEqual(book["symbols"], [])
        self.assertEqual(book["totals"]["net_pnl_estimated"], 0)
        self.assertEqual(book["totals"]["unmatched_sell_qty"], 0)


class ResolverTests(unittest.TestCase):
    """The suffix bug that hid XIRR on most holdings."""

    def test_ledger_under_the_other_suffix_is_still_found(self):
        store = {"TCS.NS": [buy("2024-01-01", 5, 3000.0, symbol="TCS.NS")]}
        self.assertEqual(len(equity_txns.txns_for(store, "TCS.BO")), 1)

    def test_both_suffixes_merge_into_one_history(self):
        store = {
            "INFY.BO": [buy("2024-01-01", 30, 1500.0, symbol="INFY.BO")],
            "INFY.NS": [buy("2024-02-01", 20, 1550.0, symbol="INFY.NS")],
        }
        rows = equity_txns.txns_for(store, "INFY.BO")
        self.assertEqual(len(rows), 2)
        self.assertEqual(equity_txns.net_qty(rows), 50)

    def test_isin_matches_when_the_symbol_was_renamed(self):
        store = {"OLDNAME.NS": [{**buy("2024-01-01", 5, 100.0),
                                 "isin": "INE467B01029"}]}
        rows = equity_txns.txns_for(store, "NEWNAME.NS", isin="INE467B01029")
        self.assertEqual(len(rows), 1)

    def test_an_unrelated_symbol_is_not_borrowed(self):
        store = {"ITC.BO": [buy("2024-01-01", 5, 400.0, symbol="ITC.BO")]}
        self.assertEqual(equity_txns.txns_for(store, "TCS.BO"), [])

    def test_single_buy_position_now_has_an_xirr(self):
        # The exact symptom reported: one buy, ledger filed under .NS, holding
        # under .BO, XIRR blank.
        store = {"TCS.NS": [buy("2024-01-01", 5, 3000.0, symbol="TCS.NS")]}
        rows = equity_txns.txns_for(store, "TCS.BO")
        res = equity_txns.xirr_for(rows, current_value=20000.0, held_qty=5,
                                   avg_cost=3000.0,
                                   as_of=datetime(2025, 1, 1))
        self.assertEqual(res["basis"], "exact")
        self.assertIsNotNone(res["xirr"])

    def test_a_position_bought_today_reports_same_day_not_a_bogus_rate(self):
        today = datetime(2026, 9, 9)
        store = {"NEW.NS": [buy("2026-09-09", 10, 100.0, symbol="NEW.NS")]}
        res = equity_txns.xirr_for(equity_txns.txns_for(store, "NEW.NS"),
                                   current_value=1010.0, held_qty=10,
                                   avg_cost=100.0, as_of=today)
        self.assertEqual(res["basis"], "same_day")
        self.assertIsNone(res["xirr"])

    def test_a_genuinely_flat_book_reports_zero_not_missing(self):
        store = {"FLAT.NS": [buy("2024-01-01", 10, 100.0, symbol="FLAT.NS")]}
        book = equity_txns.portfolio_xirr(
            store, [{"symbol": "FLAT.NS", "shares": 10, "total_value": 1000.0}],
            as_of=datetime(2025, 1, 1))
        self.assertIsNotNone(book["xirr"])
        self.assertAlmostEqual(book["xirr"], 0.0, places=1)


if __name__ == "__main__":
    unittest.main()
