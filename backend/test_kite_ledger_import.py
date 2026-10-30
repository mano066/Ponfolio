"""Tests for the Console funds-ledger import (TDS) and the settlement-gap XIRR.

The provisional-TDS netting is the important one. Console blocks an amount and
reverses it days later, often for far more than was actually deducted (the
fixtures below use 10,000 blocked against 250 deducted) — so a naive "sum
every row mentioning TDS" overstates the tax many times over, from the one
export meant to make it exact.
"""
import os
import unittest
from datetime import datetime

import equity_closed
import equity_txns
import kite_ledger_import as ledger
from test_kite_pnl_import import make_xlsx


def ledger_sheet(period="Ledger for Equity from 2026-08-07 to 2026-08-14",
                 rows=(), opening="50000.0000", closing="1000.0000"):
    grid = [[], [], ["", "Client ID", "AB1234"], [], [], [], ["", period], [],
            [], [], [],
            ["", "Particulars", "Posting Date", "Cost Center", "Voucher Type",
             "Debit", "Credit", "Net Balance"],
            ["", "Opening Balance", "", "", "", "", "", opening]]
    for row in rows:
        grid.append(["", *row])
    grid.append(["", "Closing Balance", "", "", "", "", "", closing])
    return grid


TDS_ROW = ("TDS payable on Equity Intraday for 2026-08-07", "2026-08-07",
           "NSE-EQ - Z", "TDS Voucher", "250.0000", "0.0000", "49750.0000")
BLOCKED_ROW = ("Provisional TDS amount blocked for 1000001", "2026-09-02",
               "NSE-EQ - Z", "Provisional TDS Voucher", "10000.0000",
               "0.0000", "40000.0000")
REVERSED_ROW = ("Provisional TDS amount reversed for 1000001", "2026-09-03",
                "NSE-EQ - Z", "Provisional TDS Voucher", "0.0000",
                "10000.0000", "50000.0000")
SETTLEMENT_ROW = ("Net settlement for Equity with settlement number: 1000002",
                  "2026-08-07", "NSE-EQ - Z", "Book Voucher", "0.0000",
                  "1000.0000", "51000.0000")
FUNDS_ROW = ("Funds added using UPI from AB1234 with reference 1000000001",
             "2026-08-10", "NSE-EQ - Z", "Bank Receipts", "0.0000",
             "10000.0000", "60000.0000")


class LedgerParseTests(unittest.TestCase):
    def parse(self, rows, **kwargs):
        return ledger.parse_ledger_workbook(
            make_xlsx(ledger_sheet(rows=rows, **kwargs)))

    def test_period_balances_and_entries_are_read(self):
        st = self.parse([SETTLEMENT_ROW, TDS_ROW, FUNDS_ROW])
        self.assertEqual(st["period"]["from"], "2026-08-07")
        self.assertEqual(st["period"]["to"], "2026-08-14")
        self.assertEqual(st["opening_balance"], 50000.0)
        self.assertEqual(st["closing_balance"], 1000.0)
        self.assertEqual(len(st["entries"]), 3)

    def test_opening_and_closing_are_anchors_not_transactions(self):
        st = self.parse([TDS_ROW])
        kinds = [e["kind"] for e in st["entries"]]
        self.assertEqual(kinds, ["tds"])
        self.assertNotIn("other", kinds)

    def test_actual_tds_is_a_cost(self):
        st = self.parse([TDS_ROW])
        self.assertEqual(st["tds"]["deducted"], 250.0)
        self.assertEqual(st["tds"]["provisional_blocked"], 0.0)
        self.assertEqual(st["tds"]["provisional_outstanding"], 0.0)

    def test_a_blocked_and_reversed_pair_nets_to_zero(self):
        st = self.parse([BLOCKED_ROW, REVERSED_ROW])
        tds = st["tds"]
        # The whole point: 10,000 in and 10,000 back is not a 20,000 tax bill,
        # and it is not a 10,000 one either.
        self.assertEqual(tds["deducted"], 0.0)
        self.assertEqual(tds["provisional_blocked"], 10000.0)
        self.assertEqual(tds["provisional_reversed"], 10000.0)
        self.assertEqual(tds["provisional_outstanding"], 0.0)

    def test_a_block_with_no_reversal_yet_is_outstanding_not_spent(self):
        st = self.parse([BLOCKED_ROW])
        tds = st["tds"]
        self.assertEqual(tds["deducted"], 0.0)
        self.assertEqual(tds["provisional_outstanding"], 10000.0)

    def test_deducted_and_provisional_are_never_added(self):
        st = self.parse([TDS_ROW, BLOCKED_ROW, REVERSED_ROW])
        tds = st["tds"]
        self.assertEqual(tds["deducted"], 250.0)
        self.assertEqual(tds["provisional_outstanding"], 0.0)

    def test_a_refunded_deduction_nets_off(self):
        refund = ("TDS reversal on Equity Intraday", "2026-08-09",
                  "NSE-EQ - Z", "TDS Voucher", "0.0000", "250.0000", "0")
        st = self.parse([TDS_ROW, refund])
        self.assertEqual(st["tds"]["deducted"], 0.0)

    def test_settlements_and_funds_are_classified(self):
        st = self.parse([SETTLEMENT_ROW, FUNDS_ROW])
        kinds = {e["kind"] for e in st["entries"]}
        self.assertEqual(kinds, {"settlement", "funds_in"})
        self.assertEqual(st["funds"]["added"], 10000.0)
        self.assertEqual(st["funds"]["withdrawn"], 0)

    def test_a_pnl_statement_in_the_ledger_slot_is_refused(self):
        from test_kite_pnl_import import pnl_sheet
        out = ledger.parse_ledger_workbook(make_xlsx(pnl_sheet()))
        self.assertIn("no ledger table", out["error"])

    def test_the_basis_states_what_provisional_means(self):
        st = self.parse([TDS_ROW])
        self.assertIn("never counted as a cost", st["tds"]["basis"])


class LedgerStoreTests(unittest.TestCase):
    def statement(self, start, end, rows):
        return ledger.parse_ledger_workbook(make_xlsx(ledger_sheet(
            period=f"Ledger for Equity from {start} to {end}", rows=rows)))

    def test_re_importing_a_period_replaces_it(self):
        store = {}
        ledger.merge_ledger(store, self.statement("2026-08-01", "2026-08-31",
                                                  [TDS_ROW]))
        again = ledger.merge_ledger(store, self.statement(
            "2026-08-01", "2026-08-31", [TDS_ROW]))
        self.assertTrue(again["replaced"])
        self.assertEqual(len(store), 1)
        self.assertEqual(ledger.book(store)["tds"]["deducted"], 250.0)

    def test_separate_periods_accumulate_tds(self):
        store = {}
        ledger.merge_ledger(store, self.statement("2026-08-01", "2026-08-31",
                                                  [TDS_ROW]))
        ledger.merge_ledger(store, self.statement("2026-09-01", "2026-09-30",
                                                  [TDS_ROW]))
        book = ledger.book(store)
        self.assertEqual(book["tds"]["deducted"], 500.0)
        self.assertEqual(book["covers_from"], "2026-08-01")
        self.assertEqual(book["covers_to"], "2026-09-30")

    def test_a_block_in_one_period_reversed_in_the_next_still_nets(self):
        store = {}
        ledger.merge_ledger(store, self.statement("2026-09-01", "2026-09-02",
                                                  [BLOCKED_ROW]))
        ledger.merge_ledger(store, self.statement("2026-09-03", "2026-09-04",
                                                  [REVERSED_ROW]))
        self.assertEqual(ledger.book(store)["tds"]["provisional_outstanding"],
                         0.0)

    def test_an_overlapping_ledger_is_reported(self):
        store = {}
        ledger.merge_ledger(store, self.statement("2026-08-01", "2026-08-31",
                                                  [TDS_ROW]))
        result = ledger.merge_ledger(store, self.statement(
            "2026-08-15", "2026-09-15", [TDS_ROW]))
        self.assertEqual(result["conflicts"], ["2026-08-01..2026-08-31"])
        self.assertTrue(ledger.book(store)["overlapping_periods"])

    def test_tds_entries_come_back_in_date_order(self):
        store = {}
        ledger.merge_ledger(store, self.statement("2026-09-01", "2026-09-04",
                                                  [REVERSED_ROW, BLOCKED_ROW]))
        dates = [e["date"] for e in ledger.book(store)["tds"]["entries"]]
        self.assertEqual(dates, sorted(dates))


class ClosedWithTdsTests(unittest.TestCase):
    def ledger_store(self, rows=(TDS_ROW,)):
        store = {}
        ledger.merge_ledger(store, ledger.parse_ledger_workbook(
            make_xlsx(ledger_sheet(rows=rows))))
        return store

    def txns(self):
        return {"BETA.NS": [
            {"symbol": "BETA.NS", "date": "2026-01-02", "type": "BUY",
             "qty": 10, "price": 100.0, "amount": 1000.0, "trade_id": "b1"},
            {"symbol": "BETA.NS", "date": "2026-08-14", "type": "SELL",
             "qty": 10, "price": 150.0, "amount": 1500.0, "trade_id": "s1"},
        ]}

    def test_without_a_ledger_there_is_no_tds_block(self):
        book = equity_closed.closed_positions(self.txns())
        self.assertIsNone(book["tds"])

    def test_with_a_ledger_tds_is_reported_separately_from_charges(self):
        book = equity_closed.closed_positions(
            self.txns(), ledgers=self.ledger_store())
        tds = book["tds"]
        self.assertEqual(tds["deducted"], 250.0)
        # It must NOT have been folded into the charge estimate.
        self.assertNotAlmostEqual(book["totals"]["charges_estimated"], 250.0)
        self.assertIn("funds ledger", tds["basis"])

    def test_provisional_amounts_travel_but_stay_separate(self):
        book = equity_closed.closed_positions(
            self.txns(),
            ledgers=self.ledger_store((TDS_ROW, BLOCKED_ROW, REVERSED_ROW)))
        tds = book["tds"]
        self.assertEqual(tds["deducted"], 250.0)
        self.assertEqual(tds["provisional_blocked"], 10000.0)
        self.assertEqual(tds["provisional_outstanding"], 0.0)

    def test_the_covered_period_and_entries_travel(self):
        book = equity_closed.closed_positions(
            self.txns(), ledgers=self.ledger_store())
        self.assertEqual(book["tds"]["covers_from"], "2026-08-07")
        self.assertEqual(len(book["tds"]["entries"]), 1)


class UnsettledXirrTests(unittest.TestCase):
    """A buy made today must not delete the holding's XIRR."""

    NOW = datetime(2026, 9, 9, 13, 0)

    def txns(self, extra=()):
        rows = [
            {"symbol": "X.NS", "date": "2026-03-30", "type": "BUY",
             "qty": 20, "price": 700.0, "amount": 14000.0, "trade_id": "b1"},
            {"symbol": "X.NS", "date": "2026-08-10", "type": "BUY",
             "qty": 20, "price": 730.0, "amount": 14600.0, "trade_id": "b2"},
        ]
        return rows + list(extra)

    def test_a_same_day_buy_no_longer_blanks_the_xirr(self):
        # 43 in the ledger against 40 held: today's 3 have not settled into
        # the broker's holdings snapshot yet. This used to return None.
        today = {"symbol": "X.NS", "date": "2026-09-09", "type": "BUY",
                 "qty": 3, "price": 700.0, "amount": 2100.0,
                 "trade_id": "b3"}
        result = equity_txns.xirr_for(self.txns([today]), current_value=28000.0,
                                      held_qty=40, avg_cost=720.0,
                                      as_of=self.NOW)
        self.assertIsNotNone(result["xirr"])
        self.assertEqual(result["basis"], "unsettled")
        self.assertFalse(result["exact"])

    def test_an_old_unexplained_excess_is_partial_not_unsettled(self):
        # Ledger over holdings, but nothing was bought recently: a sale is
        # missing from the ledger. Still valued, still flagged, but not
        # blamed on settlement.
        old = {"symbol": "X.NS", "date": "2026-05-01", "type": "BUY",
               "qty": 3, "price": 700.0, "amount": 2100.0, "trade_id": "b4"}
        result = equity_txns.xirr_for(self.txns([old]), current_value=28000.0,
                                      held_qty=40, avg_cost=720.0,
                                      as_of=self.NOW)
        self.assertIsNotNone(result["xirr"])
        self.assertEqual(result["basis"], "partial")

    def test_a_ledger_short_of_the_holding_still_seeds_as_before(self):
        result = equity_txns.xirr_for(self.txns(), current_value=40000.0,
                                      held_qty=60, avg_cost=700.0,
                                      as_of=self.NOW)
        self.assertIsNotNone(result["xirr"])
        self.assertEqual(result["basis"], "partial")

    def test_an_exactly_covered_holding_is_still_exact(self):
        result = equity_txns.xirr_for(self.txns(), current_value=28000.0,
                                      held_qty=40, avg_cost=715.0,
                                      as_of=self.NOW)
        self.assertEqual(result["basis"], "exact")
        self.assertTrue(result["exact"])

    def test_the_terminal_value_scales_to_the_ledger_quantity(self):
        # 43 traced shares valued at the same per-share price as the 40 held,
        # so the rate reflects the money actually traced.
        today = {"symbol": "X.NS", "date": "2026-09-09", "type": "BUY",
                 "qty": 3, "price": 700.0, "amount": 2100.0,
                 "trade_id": "b3"}
        scaled = equity_txns.xirr_for(self.txns([today]), current_value=28000.0,
                                      held_qty=40, avg_cost=720.0,
                                      as_of=self.NOW)
        equal = equity_txns.xirr_for(self.txns([today]),
                                      current_value=28000.0 * 43 / 40,
                                      held_qty=43, avg_cost=720.0,
                                      as_of=self.NOW)
        self.assertAlmostEqual(scaled["xirr"], equal["xirr"], places=1)

    def test_recent_buys_are_counted_only_inside_the_window(self):
        rows = [{"symbol": "X.NS", "date": "2026-09-08", "type": "BUY",
                 "qty": 5, "price": 100.0, "amount": 500.0, "trade_id": "r1"},
                {"symbol": "X.NS", "date": "2026-01-01", "type": "BUY",
                 "qty": 7, "price": 100.0, "amount": 700.0, "trade_id": "r2"}]
        self.assertEqual(equity_txns._bought_recently(rows, self.NOW), 5)

    def test_a_sell_never_counts_as_a_recent_buy(self):
        rows = [{"symbol": "X.NS", "date": "2026-09-09", "type": "SELL",
                 "qty": 5, "price": 100.0, "amount": 500.0, "trade_id": "s1"}]
        self.assertEqual(equity_txns._bought_recently(rows, self.NOW), 0)


EXPORT_DIR = os.environ.get("KITE_EXPORT_DIR", "")


def _real_ledgers():
    """Console ledger exports (ledger*.xlsx) in $KITE_EXPORT_DIR, if set."""
    if not EXPORT_DIR or not os.path.isdir(EXPORT_DIR):
        return []
    return sorted(os.path.join(EXPORT_DIR, name)
                  for name in os.listdir(EXPORT_DIR)
                  if name.lower().startswith("ledger")
                  and name.lower().endswith(".xlsx"))


class RealLedgerTests(unittest.TestCase):
    """Against real Console exports, when KITE_EXPORT_DIR points at them."""

    @unittest.skipUnless(_real_ledgers(),
                         "set KITE_EXPORT_DIR to a folder of ledger exports")
    def test_real_ledgers_parse_and_net_provisional_tds(self):
        store = {}
        for path in _real_ledgers():
            with open(path, "rb") as handle:
                statement = ledger.parse_ledger_workbook(handle.read())
            self.assertIsNone(statement.get("error"))
            ledger.merge_ledger(store, statement)
        tds = ledger.book(store)["tds"]
        self.assertGreaterEqual(tds["deducted"], 0.0)
        # Provisional amounts never leak into the deducted cost.
        self.assertEqual(tds["provisional_outstanding"],
                         round(tds["provisional_blocked"]
                               - tds["provisional_reversed"], 2))


if __name__ == "__main__":
    unittest.main()


class TdsAttributionTests(unittest.TestCase):
    """Per-symbol TDS, from the date Console writes into its own narration."""

    def lots(self):
        """Two intraday closes on different days, plus one delivery sale."""
        return {
            "ALPHA.NS": [
                {"symbol": "ALPHA.NS", "date": "2026-08-05", "type": "BUY",
                 "qty": 100, "price": 200.0, "amount": 20000.0,
                 "trade_id": "g1"},
                {"symbol": "ALPHA.NS", "date": "2026-08-05", "type": "SELL",
                 "qty": 100, "price": 210.0, "amount": 21000.0,
                 "trade_id": "g2"},
            ],
            "BETA.NS": [
                {"symbol": "BETA.NS", "date": "2026-08-13", "type": "BUY",
                 "qty": 100, "price": 300.0, "amount": 30000.0,
                 "trade_id": "c1"},
                {"symbol": "BETA.NS", "date": "2026-08-14", "type": "SELL",
                 "qty": 100, "price": 310.0, "amount": 31000.0,
                 "trade_id": "c2"},
            ],
        }

    def ledger_with(self, *rows):
        store = {}
        ledger.merge_ledger(store, ledger.parse_ledger_workbook(
            make_xlsx(ledger_sheet(rows=rows))))
        return store

    def book(self, *rows):
        return equity_closed.closed_positions(
            self.lots(), ledgers=self.ledger_with(*rows))

    def test_an_intraday_deduction_lands_on_the_position_traded_that_day(self):
        row = ("TDS payable on Equity Intraday for 2026-08-05", "2026-08-05",
               "NSE-EQ - Z", "TDS Voucher", "100.00", "0.0000", "0")
        book = self.book(row)
        by_symbol = {s["symbol"]: s for s in book["symbols"]}
        self.assertEqual(by_symbol["ALPHA"]["tds_attributed"], 100.0)
        self.assertEqual(by_symbol["ALPHA"]["tds_source"], "date_matched")
        self.assertEqual(by_symbol["BETA"]["tds_attributed"], 0.0)
        self.assertEqual(book["tds"]["unattributed"], 0.0)

    def test_a_capital_gains_deduction_lands_on_the_delivery_sale(self):
        row = ("TDS payable on capital gains for 2026-08-14", "2026-08-17",
               "NSE-EQ - Z", "TDS Voucher", "200.00", "0.0000", "0")
        by_symbol = {s["symbol"]: s for s in self.book(row)["symbols"]}
        self.assertEqual(by_symbol["BETA"]["tds_attributed"], 200.0)
        self.assertEqual(by_symbol["ALPHA"]["tds_attributed"], 0.0)

    def test_the_net_drops_by_the_tax_withheld_on_that_position(self):
        row = ("TDS payable on Equity Intraday for 2026-08-05", "2026-08-05",
               "NSE-EQ - Z", "TDS Voucher", "100.00", "0.0000", "0")
        alpha = next(s for s in self.book(row)["symbols"]
                    if s["symbol"] == "ALPHA")
        self.assertEqual(alpha["net_after_tds"],
                         round(alpha["net_pnl_estimated"] - 100.0, 2))

    def test_a_deduction_naming_a_date_with_no_trade_stays_unattributed(self):
        row = ("TDS payable on Equity Intraday for 2026-01-01", "2026-01-01",
               "NSE-EQ - Z", "TDS Voucher", "100.00", "0.0000", "0")
        book = self.book(row)
        self.assertEqual(book["tds"]["unattributed"], 100.0)
        self.assertEqual(book["tds"]["attributed"], 0.0)
        # Still counted in the deducted total: it was really withheld.
        self.assertEqual(book["tds"]["deducted"], 100.0)
        for row_out in book["symbols"]:
            self.assertEqual(row_out["tds_attributed"], 0.0)

    def test_two_positions_closed_the_same_day_split_by_sell_value(self):
        store = self.lots()
        store["OTHER.NS"] = [
            {"symbol": "OTHER.NS", "date": "2026-08-05", "type": "BUY",
             "qty": 100, "price": 100.0, "amount": 10000.0, "trade_id": "o1"},
            {"symbol": "OTHER.NS", "date": "2026-08-05", "type": "SELL",
             "qty": 100, "price": 100.0, "amount": 10000.0, "trade_id": "o2"},
        ]
        row = ("TDS payable on Equity Intraday for 2026-08-05", "2026-08-05",
               "NSE-EQ - Z", "TDS Voucher", "99.00", "0.0000", "0")
        book = equity_closed.closed_positions(
            store, ledgers=self.ledger_with(row))
        by_symbol = {s["symbol"]: s for s in book["symbols"]}
        self.assertEqual(by_symbol["ALPHA"]["tds_source"], "apportioned")
        # Split by sell value: 21,000 against 10,000.
        self.assertGreater(by_symbol["ALPHA"]["tds_attributed"],
                           by_symbol["OTHER"]["tds_attributed"])
        self.assertAlmostEqual(
            by_symbol["ALPHA"]["tds_attributed"]
            + by_symbol["OTHER"]["tds_attributed"], 99.0, places=2)

    def test_provisional_amounts_are_never_attributed(self):
        book = self.book(BLOCKED_ROW, REVERSED_ROW)
        self.assertEqual(book["tds"]["attributed"], 0.0)
        for row in book["symbols"]:
            self.assertEqual(row["tds_attributed"], 0.0)

    def test_the_event_date_is_read_from_either_format(self):
        self.assertEqual(
            equity_closed._tds_event_date("TDS for 2026-08-05"), "2026-08-05")
        self.assertEqual(
            equity_closed._tds_event_date("DP Charges for Sale on 14/08/2026"),
            "2026-08-14")
        self.assertIsNone(equity_closed._tds_event_date("TDS payable"))

    def test_the_book_total_matches_the_sum_of_the_rows(self):
        rows = (
            ("TDS payable on Equity Intraday for 2026-08-05", "2026-08-05",
             "NSE-EQ - Z", "TDS Voucher", "100.00", "0.0000", "0"),
            ("TDS payable on capital gains for 2026-08-14", "2026-08-17",
             "NSE-EQ - Z", "TDS Voucher", "200.00", "0.0000", "0"),
        )
        book = self.book(*rows)
        per_row = round(sum(s["tds_attributed"] for s in book["symbols"]), 2)
        self.assertEqual(per_row, 300.0)
        self.assertEqual(book["totals"]["tds_attributed"], 300.0)
        self.assertEqual(book["tds"]["deducted"], 300.0)
