"""Tests for the Kite Console XLSX imports.

These build real .xlsx bytes with zipfile rather than mocking the reader, so
the format handling is exercised end to end. Real Console exports are
covered by a separate check that runs only when KITE_EXPORT_DIR is set.
"""
import io
import os
import unittest
import zipfile

import equity_closed
import kite_pnl_import
import tradebook_import
import xlsx_reader

SHEET_NS = ('xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"')


def _sheet_xml(rows):
    """Build a worksheet with every cell as an inline string."""
    out = [f'<worksheet {SHEET_NS}><sheetData>']
    for r, row in enumerate(rows, start=1):
        out.append(f'<row r="{r}">')
        for c, value in enumerate(row):
            if value is None or value == "":
                continue
            ref = f"{chr(65 + c)}{r}"
            text = (str(value).replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))
            out.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        out.append('</row>')
    out.append('</sheetData></worksheet>')
    return "".join(out)


def make_xlsx(*sheets):
    """Minimal but valid workbook: content types, workbook, worksheets."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxml'
                   'formats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", f'<workbook {SHEET_NS}/>')
        for i, rows in enumerate(sheets, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows))
    return buf.getvalue()


def pnl_sheet(period="P&L Statement for Equity from 2026-08-01 to 2026-08-31",
              closed=(("ALPHA", "INE000A01011", "100", "10000.00",
                       "11000.00", "1000.00", "10.0000"),),
              charges=(("Brokerage - Z", "100.0000"),
                       ("Securities Transaction Tax - Z", "50.0000")),
              realized="1000.00", charges_total="150.00"):
    rows = [[], [], ["", "Client ID", "AB1234"], [], [], [], ["", period], [],
            ["", "Summary"], [],
            ["", "Charges", charges_total],
            ["", "Other Credit & Debit", "-50.0000"],
            ["", "Realized P&L", realized],
            ["", "Unrealized P&L", "-1000.0000"], [],
            ["", "Charges"], [],
            ["", "Account Head", "Amount"]]
    for head, amount in charges:
        rows.append(["", head, amount])
    rows += [[], [],
             ["", "Symbol", "ISIN", "Quantity", "Buy Value", "Sell Value",
              "Realized P&L", "Realized P&L Pct.", "Previous Closing Price",
              "Open Quantity", "Open Quantity Type", "Open Value",
              "Unrealized P&L", "Unrealized P&L Pct."]]
    for row in closed:
        rows.append(["", *row, "0.0000", "0.0000", "", "0.0000", "0.0000",
                     "0.0000"])
    # One still-held position, which must land on the open side only.
    rows.append(["", "BETA", "INE000B01012", "0.0000", "0.0000", "0.0000",
                 "0.0000", "0.0000", "100.00", "50.0000", "", "5000.00",
                 "-1000.00", "-16.67"])
    return rows


def other_sheet():
    return [[], [], ["", "Client ID", "AB1234"], [], [], [],
            ["", "Other Debits and Credits for EQ from 2026-08-01 to 2026-08-31"],
            [], [], [],
            ["", "Particulars", "Posting Date", "Debit", "Credit"],
            ["", "DP Charges for Sale of ALPHA on 14/08/2026", "2026-08-14",
             "15.0000", "0.0000"],
            ["", "Delayed payment charges for July - 2026", "2026-08-05",
             "1.0000", "0.0000"]]


def tradebook_sheet(rows=(("GAMMA", "INE000C01013", "2026-08-10", "NSE", "EQ",
                           "EQ", "buy", "0", "20.0000", "100.0000",
                           "1000000001", "1000000002",
                           "2026-08-10T10:24:09"),)):
    grid = [[], [], ["", "Client ID", "AB1234"], [], [], [],
            ["", "Tradebook for Equity from 2026-08-01 to 2026-08-31"], [], [],
            [], ["", "Symbol", "ISIN", "Trade Date", "Exchange", "Segment",
                 "Series", "Trade Type", "Auction", "Quantity", "Price",
                 "Trade ID", "Order ID", "Order Execution Time"]]
    for row in rows:
        grid.append(["", *row])
    return grid


class XlsxReaderTests(unittest.TestCase):
    def test_a_non_zip_upload_is_rejected_with_advice(self):
        with self.assertRaises(xlsx_reader.XlsxError) as caught:
            xlsx_reader.sheets(b"symbol,trade_date\nITC,2026-01-01\n")
        self.assertIn("Export it again", str(caught.exception))

    def test_column_letters_map_past_z(self):
        self.assertEqual(xlsx_reader._column_index("A1"), 0)
        self.assertEqual(xlsx_reader._column_index("Z9"), 25)
        self.assertEqual(xlsx_reader._column_index("AA1"), 26)

    def test_sheets_are_ordered_by_number_not_by_name(self):
        blob = make_xlsx([["one"]], [["two"]])
        names = list(xlsx_reader.sheets(blob))
        self.assertEqual(names[0], "xl/worksheets/sheet1.xml")

    def test_the_header_row_is_found_by_content(self):
        rows = pnl_sheet()
        self.assertGreater(xlsx_reader.find_row(rows, "symbol", "realized p&l"), 0)
        self.assertEqual(xlsx_reader.find_row(rows, "nothing here"), -1)

    def test_numbers_survive_commas_currency_and_brackets(self):
        self.assertEqual(xlsx_reader.number("1,234.50"), 1234.5)
        self.assertEqual(xlsx_reader.number("₹ 2,000"), 2000.0)
        self.assertEqual(xlsx_reader.number("(500.25)"), -500.25)
        self.assertEqual(xlsx_reader.number(""), 0.0)
        self.assertEqual(xlsx_reader.number("-"), 0.0)
        self.assertEqual(xlsx_reader.number("junk"), 0.0)

    def test_the_period_comes_from_the_title(self):
        period = xlsx_reader.period_from_title(pnl_sheet())
        self.assertEqual(period["from"], "2026-08-01")
        self.assertEqual(period["to"], "2026-08-31")


class PnlParseTests(unittest.TestCase):
    def statement(self, **kwargs):
        return kite_pnl_import.parse_pnl_workbook(
            make_xlsx(pnl_sheet(**kwargs), other_sheet()))

    def test_summary_charges_and_positions_are_read(self):
        st = self.statement()
        self.assertEqual(st["period"]["from"], "2026-08-01")
        self.assertEqual(st["summary"]["realized_pnl"], 1000.0)
        self.assertEqual(st["summary"]["charges"], 150.0)
        self.assertEqual(len(st["closed"]), 1)
        self.assertEqual(st["closed"][0]["symbol"], "ALPHA")
        self.assertEqual(st["closed"][0]["realized_pnl"], 1000.0)
        self.assertEqual(len(st["charges_actual"]), 2)

    def test_a_still_held_position_is_open_not_closed(self):
        st = self.statement()
        self.assertEqual([r["symbol"] for r in st["open"]], ["BETA"])
        self.assertNotIn("BETA", [r["symbol"] for r in st["closed"]])

    def test_the_zerodha_entity_suffix_is_stripped_from_charge_heads(self):
        st = self.statement()
        self.assertEqual(st["charges_actual"][0]["head"], "Brokerage")

    def test_dp_charges_are_attributed_to_their_symbol_and_date(self):
        st = self.statement()
        self.assertEqual(st["dp_charges_by_symbol"], {"ALPHA": 15.0})
        dp = [e for e in st["other_credit_debit"] if e.get("kind") == "dp_charge"]
        self.assertEqual(dp[0]["date"], "2026-08-14")

    def test_the_rows_are_checked_against_the_summary_total(self):
        self.assertTrue(self.statement()["checks"]["realized_agrees"])
        # A statement whose per-symbol rows contradict its own summary must
        # not silently pick one of the two.
        bad = self.statement(realized="9999.00")
        self.assertFalse(bad["checks"]["realized_agrees"])

    def test_a_tradebook_in_the_pnl_slot_is_refused(self):
        out = kite_pnl_import.parse_pnl_workbook(make_xlsx(tradebook_sheet()))
        self.assertIn("no P&L table", out["error"])


class PeriodStoreTests(unittest.TestCase):
    def statement(self, start, end, realized="1000.00"):
        return kite_pnl_import.parse_pnl_workbook(make_xlsx(pnl_sheet(
            period=f"P&L Statement for Equity from {start} to {end}",
            realized=realized,
            closed=(("ALPHA", "INE000A01011", "10", "1000.00", f"{1000 + float(realized)}",
                     realized, "1.0"),)), other_sheet()))

    def test_re_importing_a_month_replaces_it_rather_than_doubling(self):
        store = {}
        first = kite_pnl_import.merge_statement(
            store, self.statement("2026-08-01", "2026-08-31"))
        again = kite_pnl_import.merge_statement(
            store, self.statement("2026-08-01", "2026-08-31"))
        self.assertFalse(first["replaced"])
        self.assertTrue(again["replaced"])
        self.assertEqual(len(store), 1)
        self.assertEqual(kite_pnl_import.book(store)["totals"]["realized_pnl"],
                         1000.0)

    def test_separate_months_accumulate(self):
        store = {}
        kite_pnl_import.merge_statement(
            store, self.statement("2026-07-01", "2026-07-31", "400.00"))
        kite_pnl_import.merge_statement(
            store, self.statement("2026-08-01", "2026-08-31", "600.00"))
        book = kite_pnl_import.book(store)
        self.assertEqual(len(store), 2)
        self.assertEqual(book["totals"]["realized_pnl"], 1000.0)
        self.assertEqual(book["covers_from"], "2026-07-01")
        self.assertEqual(book["covers_to"], "2026-08-31")
        self.assertEqual(book["overlapping_periods"], [])

    def test_a_symbol_sold_in_two_months_realises_twice(self):
        store = {}
        kite_pnl_import.merge_statement(
            store, self.statement("2026-07-01", "2026-07-31", "400.00"))
        kite_pnl_import.merge_statement(
            store, self.statement("2026-08-01", "2026-08-31", "600.00"))
        rows = kite_pnl_import.book(store)["by_symbol"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["realized_pnl"], 1000.0)
        self.assertEqual(len(rows[0]["periods"]), 2)

    def test_an_overlapping_period_is_reported_not_swallowed(self):
        store = {}
        kite_pnl_import.merge_statement(
            store, self.statement("2025-10-01", "2026-09-09"))
        result = kite_pnl_import.merge_statement(
            store, self.statement("2026-08-01", "2026-08-31"))
        self.assertEqual(result["conflicts"], ["2025-10-01..2026-09-09"])
        self.assertTrue(kite_pnl_import.book(store)["overlapping_periods"])

    def test_unrealised_is_the_latest_figure_not_a_sum(self):
        store = {}
        kite_pnl_import.merge_statement(
            store, self.statement("2026-07-01", "2026-07-31"))
        kite_pnl_import.merge_statement(
            store, self.statement("2026-08-01", "2026-08-31"))
        # Both statements carry -1000; summing would report -2000.
        self.assertEqual(kite_pnl_import.book(store)["totals"]["unrealized_pnl"],
                         -1000.0)

    def test_overlap_detection_is_symmetric_and_bounds_inclusive(self):
        a = {"from": "2026-01-01", "to": "2026-01-31"}
        b = {"from": "2026-01-31", "to": "2026-02-28"}
        c = {"from": "2026-02-01", "to": "2026-02-28"}
        self.assertTrue(kite_pnl_import.overlaps(a, b))
        self.assertTrue(kite_pnl_import.overlaps(b, a))
        self.assertFalse(kite_pnl_import.overlaps(a, c))


class TradebookXlsxTests(unittest.TestCase):
    def test_an_xlsx_tradebook_parses_like_the_csv(self):
        rows, report = tradebook_import.parse_tradebook_xlsx(
            make_xlsx(tradebook_sheet()))
        self.assertIsNone(report["error"])
        self.assertEqual(report["parsed"], 1)
        self.assertEqual(report["buys"], 1)
        self.assertEqual(rows[0]["type"], "BUY")
        self.assertEqual(rows[0]["qty"], 20)
        self.assertEqual(rows[0]["date"], "2026-08-10")
        self.assertEqual(report["period"]["from"], "2026-08-01")

    def test_a_sell_stays_a_sell(self):
        rows, _ = tradebook_import.parse_tradebook_xlsx(make_xlsx(
            tradebook_sheet((("GAMMA", "INE000C01013", "2026-08-11", "NSE", "EQ",
                              "EQ", "sell", "0", "5.0000", "170.0000", "t2",
                              "o2", "2026-08-11T10:00:00"),))))
        self.assertEqual(rows[0]["type"], "SELL")

    def test_an_unreadable_side_is_skipped_with_its_reason(self):
        rows, report = tradebook_import.parse_tradebook_xlsx(make_xlsx(
            tradebook_sheet((("GAMMA", "INE000C01013", "2026-08-11", "NSE", "EQ",
                              "EQ", "", "0", "5.0000", "170.0000", "t3", "o3",
                              "2026-08-11T10:00:00"),))))
        self.assertEqual(rows, [])
        self.assertEqual(report["skipped"], 1)

    def test_a_pnl_statement_in_the_tradebook_slot_is_refused(self):
        _, report = tradebook_import.parse_tradebook_xlsx(
            make_xlsx(pnl_sheet()))
        self.assertIn("no trade table", report["error"])

    def test_a_csv_uploaded_as_xlsx_is_refused_clearly(self):
        _, report = tradebook_import.parse_tradebook_xlsx(b"symbol,price\n")
        self.assertIn("Not a readable .xlsx", report["error"])


class ClosedWithStatementTests(unittest.TestCase):
    """The statement must supersede the estimate without hiding either."""

    def ledger(self):
        return {"ALPHA.NS": [
            {"symbol": "ALPHA.NS", "date": "2026-01-02", "type": "BUY",
             "qty": 10, "price": 100.0, "amount": 1000.0, "trade_id": "b1",
             "exchange": "NSE"},
            {"symbol": "ALPHA.NS", "date": "2026-08-14", "type": "SELL",
             "qty": 10, "price": 150.0, "amount": 1500.0, "trade_id": "s1",
             "exchange": "NSE"},
        ]}

    def statements(self, realized="500.00"):
        store = {}
        kite_pnl_import.merge_statement(store, kite_pnl_import.parse_pnl_workbook(
            make_xlsx(pnl_sheet(
                closed=(("ALPHA", "INE000A01011", "10", "1000.00", "1500.00",
                         realized, "50.0"),),
                realized=realized, charges_total="80.00"), other_sheet())))
        return store

    def test_without_a_statement_everything_is_an_estimate(self):
        book = equity_closed.closed_positions(self.ledger())
        self.assertIsNone(book["statement"])
        self.assertIsNone(book["reconciliation"]["broker_realized"])
        self.assertIsNone(book["symbols"][0]["realized_broker"])
        self.assertEqual(book["symbols"][0]["realized_source"], "ledger_fifo")

    def test_with_a_statement_the_broker_figure_is_carried(self):
        book = equity_closed.closed_positions(
            self.ledger(), statements=self.statements())
        symbol = book["symbols"][0]
        self.assertEqual(symbol["realized_broker"], 500.0)
        self.assertEqual(symbol["realized_source"], "broker_statement")
        self.assertTrue(symbol["realized_agrees"])
        # The reconstruction is still reported beside it, never overwritten.
        self.assertEqual(symbol["gross_pnl"], 500.0)

    def test_a_disagreement_with_the_broker_is_flagged(self):
        book = equity_closed.closed_positions(
            self.ledger(), statements=self.statements(realized="900.00"))
        self.assertFalse(book["symbols"][0]["realized_agrees"])
        self.assertFalse(book["reconciliation"]["gross_agrees"])

    def test_the_itemised_dp_charge_replaces_the_estimate(self):
        book = equity_closed.closed_positions(
            self.ledger(), statements=self.statements())
        symbol = book["symbols"][0]
        self.assertEqual(symbol["dp_charges_estimated"], 15.0)
        self.assertEqual(symbol["dp_charges_source"], "broker_statement")

    def test_actual_charges_and_the_estimate_error_are_both_reported(self):
        book = equity_closed.closed_positions(
            self.ledger(), statements=self.statements())
        rec = book["reconciliation"]
        self.assertEqual(rec["charges_actual"], 80.0)
        self.assertIsNotNone(rec["charges_estimated"])
        self.assertEqual(rec["charges_estimate_error"],
                         round(rec["charges_estimated"] - 80.0, 2))

    def test_period_net_is_realised_minus_all_charges(self):
        book = equity_closed.closed_positions(
            self.ledger(), statements=self.statements())
        st = book["statement"]
        self.assertEqual(st["realized_pnl"], 500.0)
        self.assertEqual(st["charges_actual"], 80.0)
        # 500 - 80 + (-50) other credit/debit
        self.assertEqual(st["period_net"], 370.0)
        self.assertIn("not the same figure as net realised", st["basis"])

    def test_the_covered_period_travels_with_the_book(self):
        book = equity_closed.closed_positions(
            self.ledger(), statements=self.statements())
        self.assertEqual(book["statement"]["covers_from"], "2026-08-01")
        self.assertEqual(book["statement"]["covers_to"], "2026-08-31")
        self.assertEqual(book["statement"]["overlapping_periods"], [])


EXPORT_DIR = os.environ.get("KITE_EXPORT_DIR", "")


def _real_export(prefix):
    """The newest Console export named <prefix>*.xlsx in $KITE_EXPORT_DIR."""
    if not EXPORT_DIR or not os.path.isdir(EXPORT_DIR):
        return None
    found = [os.path.join(EXPORT_DIR, name) for name in os.listdir(EXPORT_DIR)
             if name.lower().startswith(prefix) and name.lower().endswith(".xlsx")]
    return max(found, key=os.path.getmtime) if found else None


class RealExportTests(unittest.TestCase):
    """Runs against real Console exports when KITE_EXPORT_DIR points at them."""

    PNL = _real_export("pnl")
    TRADEBOOK = _real_export("tradebook")

    @unittest.skipUnless(PNL, "set KITE_EXPORT_DIR to a folder with a P&L export")
    def test_the_real_pnl_export_parses_and_agrees_with_itself(self):
        with open(self.PNL, "rb") as handle:
            st = kite_pnl_import.parse_pnl_workbook(handle.read())
        self.assertIsNone(st.get("error"))
        self.assertTrue(st["checks"]["realized_agrees"])
        self.assertEqual(st["checks"]["charges_heads_total"],
                         st["checks"]["charges_summary_total"])

    @unittest.skipUnless(TRADEBOOK,
                         "set KITE_EXPORT_DIR to a folder with a tradebook export")
    def test_the_real_tradebook_export_parses_without_skips(self):
        with open(self.TRADEBOOK, "rb") as handle:
            rows, report = tradebook_import.parse_tradebook_xlsx(handle.read())
        self.assertIsNone(report["error"])
        self.assertEqual(report["skipped"], 0)
        self.assertEqual(len(rows), report["parsed"])
        self.assertGreater(report["parsed"], 0)

    @unittest.skipUnless(PNL and TRADEBOOK,
                         "set KITE_EXPORT_DIR to a folder with both exports")
    def test_fifo_reconstruction_matches_the_broker_on_the_real_account(self):
        """The claim the whole design rests on, checked against real data."""
        with open(self.TRADEBOOK, "rb") as handle:
            rows, _ = tradebook_import.parse_tradebook_xlsx(handle.read())
        store = {}
        import equity_txns
        equity_txns.merge_trades(store, rows)
        with open(self.PNL, "rb") as handle:
            statement = kite_pnl_import.parse_pnl_workbook(handle.read())
        statements = {}
        kite_pnl_import.merge_statement(statements, statement)

        book = equity_closed.closed_positions(store, statements=statements)
        self.assertTrue(book["reconciliation"]["gross_agrees"],
                        f"FIFO {book['reconciliation']['ledger_fifo_gross']} vs "
                        f"broker {book['reconciliation']['broker_realized']}")
        for symbol in book["symbols"]:
            self.assertTrue(symbol["realized_agrees"], symbol["symbol"])


if __name__ == "__main__":
    unittest.main()
