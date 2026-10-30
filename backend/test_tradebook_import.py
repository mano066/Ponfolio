"""
Unit tests for the Console tradebook CSV import.

    python -m unittest test_tradebook_import -v

Fixtures keep the exact shape of a real Console export (the values are
synthetic), because the two bugs that matter here are both invisible against
tidy data: a holding
accumulated across BOTH exchanges, and sell rows whose column Console names
``trade_type`` rather than the ``transaction_type`` the Kite path expects.
"""

import unittest

import equity_txns
import tradebook_import as tb


HEADER = ("symbol,isin,trade_date,exchange,segment,series,trade_type,auction,"
          "quantity,price,trade_id,order_id,order_execution_time")


def _csv(*lines):
    return "\n".join((HEADER,) + lines) + "\n"


# One holding built on both exchanges: 45 shares bought on BSE, 5 on NSE, 50
# total. Synthetic values in the Console export's own format.
FILL_ROWS = (
    "INFY,INE009A01021,2026-03-02,BSE,EQ,A,buy,false,20.000000,1500.000000,1000000001,2000000001,2026-03-02T10:00:00",
    "INFY,INE009A01021,2026-04-06,BSE,EQ,A,buy,false,10.000000,1520.000000,1000000002,2000000002,2026-04-06T10:00:00",
    "INFY,INE009A01021,2026-05-04,BSE,EQ,A,buy,false,5.000000,1480.000000,1000000003,2000000003,2026-05-04T10:00:00",
    "INFY,INE009A01021,2026-06-01,BSE,EQ,A,buy,false,5.000000,1490.000000,1000000004,2000000004,2026-06-01T10:00:00",
    "INFY,INE009A01021,2026-07-06,NSE,EQ,EQ,buy,false,5.000000,1510.000000,1000000005,2000000005,2026-07-06T10:00:00",
    "INFY,INE009A01021,2026-09-01,BSE,EQ,A,buy,false,5.000000,1500.000000,1000000006,2000000006,2026-09-01T10:00:00",
)

# A round trip: bought and sold the same day, so it is not a holding but it is
# real realised cashflow.
ROUND_TRIP_ROWS = (
    "SBIN,INE062A01020,2026-07-29,NSE,EQ,EQ,buy,false,100.000000,800.000000,1000000011,2000000011,2026-07-29T10:00:00",
    "SBIN,INE062A01020,2026-07-29,NSE,EQ,EQ,sell,false,100.000000,802.000000,1000000012,2000000012,2026-07-29T11:00:00",
)

PORTFOLIO = [
    {"symbol": "INFY.NS", "shares": 50, "avg_cost": 1502.0},
    {"symbol": "RELIANCE.BO", "shares": 10, "avg_cost": 1400.0},
]

KITE_HOLDINGS = [
    {"tradingsymbol": "INFY", "isin": "INE009A01021",
     "exchange": "NSE", "quantity": 50, "average_price": 1502.0},
    {"tradingsymbol": "RELIANCE", "isin": "INE002A01018",
     "exchange": "BSE", "quantity": 10, "average_price": 1400.0},
]


def _resolver():
    return tb.build_symbol_resolver(PORTFOLIO, KITE_HOLDINGS)


class TestCrossExchangeSymbol(unittest.TestCase):
    """
    The bug that would silently corrupt the ledger.

    kite_client.kite_to_yf_symbol suffixes from the exchange, so a holding's
    BSE shares would file under X.BO and its NSE shares under X.NS — two
    buckets for one position, neither reconciling against the total the
    broker reports, and a purchase range built from a fraction of the trades.
    """

    def test_both_exchanges_land_on_one_portfolio_symbol(self):
        rows, report = tb.parse_tradebook_csv(_csv(*FILL_ROWS), _resolver())
        self.assertEqual(report["parsed"], 6)
        self.assertEqual({r["symbol"] for r in rows}, {"INFY.NS"})

    def test_the_exchange_of_each_fill_is_still_recorded(self):
        # Collapsing the key must not lose the fact, only stop it splitting.
        rows, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS), _resolver())
        self.assertEqual({r["exchange"] for r in rows}, {"BSE", "NSE"})

    def test_execution_time_and_order_details_are_preserved(self):
        rows, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS), _resolver())
        first = rows[0]
        self.assertEqual(first["executed_at"], "2026-03-02T10:00:00")
        self.assertEqual(first["order_id"], "2000000001")
        self.assertEqual(first["segment"], "EQ")
        self.assertEqual(first["series"], "A")

    def test_net_quantity_matches_the_broker(self):
        rows, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS), _resolver())
        self.assertEqual(sum(r["qty"] for r in rows), 50)

    def test_weighted_average_matches_the_broker(self):
        # 75,100 paid for 50 shares: the 1502.0 Kite reports.
        rows, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS), _resolver())
        cost = sum(r["amount"] for r in rows)
        qty = sum(r["qty"] for r in rows)
        self.assertAlmostEqual(cost / qty, 1502.0, places=2)

    def test_isin_resolves_even_when_the_bare_symbol_is_unknown(self):
        resolve = _resolver()
        self.assertEqual(resolve("RENAMED", "INE009A01021", "BSE"), "INFY.NS")

    def test_an_unheld_symbol_is_canonical_across_exchanges(self):
        """
        A stock bought on NSE and sold on BSE: suffixing by exchange would
        split the closed position into X.NS (a buy with no sell) and X.BO (a
        sell with no buy) — and realised P&L and XIRR are computed per bucket,
        so both would be wrong.
        """
        resolve = _resolver()
        self.assertEqual(resolve("BEL", "INE263A01024", "NSE"),
                         resolve("BEL", "INE263A01024", "BSE"))
        self.assertEqual(resolve("NTPC", "INE733E01010", "NSE"), "NTPC.NS")

    def test_a_cross_exchange_round_trip_nets_to_zero_in_one_bucket(self):
        rows, _ = tb.parse_tradebook_csv(_csv(
            "BEL,INE263A01024,2026-09-01,NSE,EQ,EQ,buy,false,10,300,1,1,2026-09-01T11:03:21",
            "BEL,INE263A01024,2026-09-02,BSE,EQ,A,sell,false,10,290,2,2,2026-09-02T09:17:53",
        ), _resolver())
        self.assertEqual(len({r["symbol"] for r in rows}), 1)
        net = sum(r["qty"] if r["type"] == "BUY" else -r["qty"] for r in rows)
        self.assertEqual(net, 0)


class TestSides(unittest.TestCase):
    def test_sells_are_read_from_console_s_own_column_name(self):
        """
        Console names the column `trade_type`; normalize_kite_trade looks for
        `transaction_type` and defaults to BUY when absent. Reusing that path
        would have turned every sell in the file into a purchase.
        """
        rows, report = tb.parse_tradebook_csv(_csv(*ROUND_TRIP_ROWS), _resolver())
        self.assertEqual(report["buys"], 1)
        self.assertEqual(report["sells"], 1)
        self.assertEqual({r["type"] for r in rows}, {"BUY", "SELL"})

    def test_a_closed_position_is_kept_not_filtered(self):
        # No holding results, but the realised cashflows are what make an
        # honest XIRR possible.
        rows, _ = tb.parse_tradebook_csv(_csv(*ROUND_TRIP_ROWS), _resolver())
        self.assertEqual(len(rows), 2)
        net = sum(r["qty"] if r["type"] == "BUY" else -r["qty"] for r in rows)
        self.assertEqual(net, 0)

    def test_an_unrecognised_side_is_skipped_never_assumed(self):
        bad = ("XYZ,INE000A01001,2026-01-01,NSE,EQ,EQ,,false,10,100,1,1,"
               "2026-01-01T10:00:00")
        rows, report = tb.parse_tradebook_csv(_csv(bad), _resolver())
        self.assertEqual(rows, [])
        self.assertEqual(report["skipped"], 1)
        self.assertIn("unknown trade_type '(blank)'", report["skip_reasons"])


class TestIdempotentReimport(unittest.TestCase):
    """
    The user re-exports monthly and consecutive exports overlap. Importing the
    same trade twice must not double the position.
    """

    def test_reimporting_the_same_file_adds_nothing(self):
        rows, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS), _resolver())
        store = {}
        first = equity_txns.merge_trades(store, rows)
        second = equity_txns.merge_trades(store, rows)
        self.assertEqual(first, 6)
        self.assertEqual(second, 0)
        self.assertEqual(len(store["INFY.NS"]), 6)

    def test_an_overlapping_month_adds_only_the_new_rows(self):
        store = {}
        old, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS[:4]), _resolver())
        equity_txns.merge_trades(store, old)
        # Next month's export repeats everything and adds two fills.
        new, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS), _resolver())
        added = equity_txns.merge_trades(store, new)
        self.assertEqual(added, 2)
        self.assertEqual(len(store["INFY.NS"]), 6)

    def test_the_ledger_stays_in_date_order(self):
        store = {}
        rows, _ = tb.parse_tradebook_csv(_csv(*reversed(FILL_ROWS)), _resolver())
        equity_txns.merge_trades(store, rows)
        dates = [r["date"] for r in store["INFY.NS"]]
        self.assertEqual(dates, sorted(dates))

    def test_an_old_cross_exchange_split_is_repaired_before_reimport(self):
        resolve = _resolver()
        rows, _ = tb.parse_tradebook_csv(_csv(
            "BEL,INE263A01024,2026-09-01,NSE,EQ,EQ,buy,false,10,300,1,1,2026-09-01T11:03:21",
            "BEL,INE263A01024,2026-09-02,BSE,EQ,A,sell,false,10,290,2,2,2026-09-02T09:17:53",
        ), resolve)
        # Recreate the shape persisted by the interrupted importer.
        old_sell = dict(rows[1], symbol="BEL.BO")
        store = {"BEL.NS": [rows[0]], "BEL.BO": [old_sell]}

        moved = tb.canonicalize_store(store, resolve)
        added = equity_txns.merge_trades(store, rows)

        self.assertEqual(moved, 1)
        self.assertEqual(added, 0)
        self.assertNotIn("BEL.BO", store)
        self.assertEqual(len(store["BEL.NS"]), 2)


class TestMalformedInput(unittest.TestCase):
    def test_a_non_tradebook_file_is_refused_by_name(self):
        rows, report = tb.parse_tradebook_csv("a,b,c\n1,2,3\n", _resolver())
        self.assertEqual(rows, [])
        self.assertTrue(report["error"])
        self.assertIn("symbol", report["missing_columns"])

    def test_an_empty_file_says_so(self):
        rows, report = tb.parse_tradebook_csv("   ", _resolver())
        self.assertEqual(rows, [])
        self.assertEqual(report["error"], "The file is empty.")

    def test_a_byte_order_mark_does_not_break_the_header(self):
        # Console exports sometimes carry a BOM; without stripping it the
        # first column name becomes "﻿symbol" and EVERY column reads as
        # missing, which would look like "not a tradebook".
        rows, report = tb.parse_tradebook_csv(
            "﻿" + _csv(*FILL_ROWS), _resolver())
        self.assertIsNone(report["error"])
        self.assertEqual(len(rows), 6)

    def test_bad_rows_are_counted_with_reasons_not_silently_dropped(self):
        bad = (
            ",INE1,2026-01-01,NSE,EQ,EQ,buy,false,10,100,1,1,2026-01-01T10:00:00",
            "AAA,INE2,,NSE,EQ,EQ,buy,false,10,100,2,2,",
            "BBB,INE3,2026-01-01,NSE,EQ,EQ,buy,false,0,100,3,3,2026-01-01T10:00:00",
            "CCC,INE4,2026-01-01,NSE,EQ,EQ,buy,false,10,0,4,4,2026-01-01T10:00:00",
        )
        rows, report = tb.parse_tradebook_csv(_csv(*bad), _resolver())
        self.assertEqual(rows, [])
        self.assertEqual(report["skipped"], 4)
        self.assertEqual(set(report["skip_reasons"]),
                         {"no symbol", "no date", "zero quantity", "zero price"})


class TestReport(unittest.TestCase):
    def test_report_covers_the_date_span_and_symbols(self):
        rows, report = tb.parse_tradebook_csv(
            _csv(*(FILL_ROWS + ROUND_TRIP_ROWS)), _resolver())
        self.assertEqual(report["date_from"], "2026-03-02")
        self.assertEqual(report["date_to"], "2026-09-01")
        self.assertEqual(report["symbols"], ["INFY.NS", "SBIN.NS"])
        self.assertEqual(report["parsed"], len(rows))


class TestReconcile(unittest.TestCase):
    def test_a_complete_ledger_reads_as_exact(self):
        store = {}
        rows, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS), _resolver())
        equity_txns.merge_trades(store, rows)
        out = tb.reconcile(store, PORTFOLIO)
        held = next(r for r in out if r["symbol"] == "INFY.NS")
        self.assertEqual(held["status"], "exact")
        self.assertEqual(held["ledger_qty"], 50)
        self.assertAlmostEqual(held["avg_cost_ledger"], 1502.0, places=1)

    def test_a_partial_export_is_flagged_not_presented_as_complete(self):
        # Only the first two fills: 30 of 50 shares.
        store = {}
        rows, _ = tb.parse_tradebook_csv(_csv(*FILL_ROWS[:2]), _resolver())
        equity_txns.merge_trades(store, rows)
        held = next(r for r in tb.reconcile(store, PORTFOLIO)
                    if r["symbol"] == "INFY.NS")
        self.assertEqual(held["status"], "partial")
        self.assertEqual(held["ledger_qty"], 30)

    def test_a_symbol_with_no_trades_reads_as_no_history_not_zero(self):
        out = tb.reconcile({}, PORTFOLIO)
        self.assertTrue(all(r["status"] == "no_history" for r in out))
        # And its ledger average must be absent, not 0 — 0 would render as a
        # free share.
        self.assertTrue(all(r["avg_cost_ledger"] is None for r in out))


if __name__ == "__main__":
    unittest.main()
