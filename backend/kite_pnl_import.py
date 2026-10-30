"""Kite Console P&L statement import — pure computation layer.

Console (console.zerodha.com -> Reports -> P&L) exports the one thing the
tradebook cannot give: what the broker itself says was realised, and what it
actually charged for it. The tradebook supports a FIFO reconstruction — which
on a complete export matches Console's realised figure to the paisa — but a
reconstruction cannot know brokerage, which can be a large share of the total
charges on an active account, and a rate-card estimate can miss the real
charges by a wide margin. So where a statement exists its numbers are MEASURED
and they win; the rate-card estimate stays only as the fallback for periods
never exported.

Monthly imports
---------------
The user exports one month at a time, and Console stamps the range into the
title: "P&L Statement for Equity from 2025-10-01 to 2026-09-09". That range is
the storage key, which is what makes accumulation safe:

  * re-importing the same month REPLACES it, so a repeated upload cannot
    double a realised figure the way appending would;
  * a range that overlaps an existing one is reported rather than merged,
    because two statements covering the same day would count its charges and
    its realised P&L twice, and no arithmetic here can tell which copy is
    authoritative;
  * the book total sums the stored periods, so twelve monthly files read the
    same as one annual file.

Charges are only ever attributed where Console attributes them. The per-head
breakdown (brokerage, STT, GST, stamp duty...) is a period total with no
per-symbol split, so it is reported at period and book level and never divided
across symbols. The exception is the DP charge, which Console itemises as
"DP Charges for Sale of XYZ on 02/09/2026" — symbol and date included,
so that one is attributed exactly.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

import xlsx_reader
from xlsx_reader import cell, header_map, number

SOURCE = "console_pnl_xlsx"

# Rows in Console's summary block, mapped to the names used downstream.
_SUMMARY_KEYS = {
    "charges": "charges",
    "other credit & debit": "other_credit_debit",
    "realized p&l": "realized_pnl",
    "unrealized p&l": "unrealized_pnl",
}

_DP_PATTERN = re.compile(
    r"dp charges? for sale of\s+(?P<symbol>[A-Za-z0-9&\-\.]+)\s+on\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})", re.I)


def _iso(date_text: str) -> str:
    """'02/09/2026' -> '2026-09-02'. Console writes dd/mm/yyyy here."""
    parts = re.split(r"[/-]", date_text.strip())
    if len(parts) == 3 and len(parts[0]) == 2:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_text.strip()


def parse_pnl_workbook(blob: bytes) -> dict:
    """Parse a Console P&L .xlsx into one normalised statement.

    Raises :class:`xlsx_reader.XlsxError` when the file is not a readable
    workbook, and returns ``{"error": ...}`` when it is readable but is not a
    P&L statement — a tradebook uploaded into the wrong slot, most likely.
    """
    sheets = xlsx_reader.sheets(blob)
    ordered = list(sheets.values())
    main = ordered[0] if ordered else []
    period = xlsx_reader.period_from_title(main)

    positions_header = xlsx_reader.find_row(main, "symbol", "realized p&l")
    if positions_header < 0:
        return {
            "error": "This workbook has no P&L table. Export Console -> "
                     "Reports -> P&L as XLSX, or use the Tradebook import for "
                     "a tradebook file.",
            "period": period,
        }

    summary = _parse_summary(main)
    charges = _parse_charges(main)
    closed, open_rows = _parse_positions(main, positions_header)
    other, dp_by_symbol = _parse_other(ordered[1:] if len(ordered) > 1 else [])

    realized_sum = round(sum(r["realized_pnl"] for r in closed), 2)
    return {
        "source": SOURCE,
        "period": period,
        "summary": summary,
        "charges_actual": charges,
        "closed": closed,
        "open": open_rows,
        "other_credit_debit": other,
        "dp_charges_by_symbol": dp_by_symbol,
        # Console prints a realised total in its summary block AND a per-symbol
        # table. They should agree; if they ever do not, the statement is
        # malformed and the caller must not silently pick one.
        "checks": {
            "realized_rows_total": realized_sum,
            "realized_summary_total": summary.get("realized_pnl"),
            "realized_agrees": summary.get("realized_pnl") is None or
            abs(realized_sum - summary["realized_pnl"]) <= 1.0,
            "charges_heads_total": round(
                sum(c["amount"] for c in charges), 2),
            "charges_summary_total": summary.get("charges"),
        },
    }


def _parse_summary(rows: List[List[str]]) -> dict:
    """The four-line summary block above the charges table."""
    out: Dict[str, Optional[float]] = {v: None for v in _SUMMARY_KEYS.values()}
    for row in rows[:36]:
        label = ""
        value = None
        for item in row:
            text = str(item).strip()
            if not text:
                continue
            if not label and re.search(r"[a-z]", text, re.I):
                label = text.lower()
            elif value is None and re.search(r"\d", text):
                value = number(text)
        key = _SUMMARY_KEYS.get(label)
        if key and value is not None:
            out[key] = round(value, 2)
    return out


def _parse_charges(rows: List[List[str]]) -> List[dict]:
    """Per-head charge amounts: brokerage, STT, GST, stamp duty, IPFT..."""
    start = xlsx_reader.find_row(rows, "account head", "amount")
    if start < 0:
        return []
    out: List[dict] = []
    for row in rows[start + 1:]:
        cells = [str(c).strip() for c in row if str(c).strip()]
        if len(cells) < 2:
            if out:
                break              # blank line ends the block
            continue
        head, amount = cells[0], cells[-1]
        if not re.search(r"\d", amount):
            break
        # "Brokerage - Z" is Console's own suffix for the Zerodha entity.
        clean = re.sub(r"\s*-\s*Z$", "", head).strip()
        out.append({"head": clean, "amount": round(number(amount), 4)})
    return out


def _parse_positions(rows: List[List[str]], header_index: int) -> tuple:
    """Split Console's position table into closed and still-open rows."""
    columns = header_map(rows[header_index])

    def col(*names: str) -> int:
        for name in names:
            if name in columns:
                return columns[name]
        return -1

    c_symbol = col("symbol")
    c_isin = col("isin")
    c_qty = col("quantity")
    c_buy = col("buy_value")
    c_sell = col("sell_value")
    c_realized = col("realized_p_l", "realized_pnl")
    c_realized_pct = col("realized_p_l_pct", "realized_p_l_pct_")
    c_open_qty = col("open_quantity")
    c_open_value = col("open_value")
    c_unrealized = col("unrealized_p_l", "unrealized_pnl")
    c_prev_close = col("previous_closing_price")

    closed: List[dict] = []
    open_rows: List[dict] = []
    for row in rows[header_index + 1:]:
        symbol = cell(row, c_symbol)
        if not symbol or symbol.lower() == "symbol":
            continue
        qty = number(cell(row, c_qty))
        open_qty = number(cell(row, c_open_qty))
        realized = number(cell(row, c_realized))
        # A row with a closed quantity is a realised row. A zero quantity with
        # an open quantity is the same holding still being held, and belongs
        # to the unrealised side, which the holdings screen already owns.
        if qty > 0 or realized != 0:
            closed.append({
                "symbol": symbol.upper(),
                "isin": cell(row, c_isin).upper(),
                "qty": round(qty, 4),
                "buy_value": round(number(cell(row, c_buy)), 2),
                "sell_value": round(number(cell(row, c_sell)), 2),
                "realized_pnl": round(realized, 2),
                "realized_pnl_pct": round(number(cell(row, c_realized_pct)), 4),
            })
        if open_qty > 0:
            open_rows.append({
                "symbol": symbol.upper(),
                "isin": cell(row, c_isin).upper(),
                "open_qty": round(open_qty, 4),
                "open_value": round(number(cell(row, c_open_value)), 2),
                "unrealized_pnl": round(number(cell(row, c_unrealized)), 2),
                "previous_close": round(number(cell(row, c_prev_close)), 4),
            })
    return closed, open_rows


def _parse_other(extra_sheets: List[List[List[str]]]) -> tuple:
    """Other debits and credits, and the DP charges hidden inside them."""
    entries: List[dict] = []
    dp: Dict[str, float] = {}
    for rows in extra_sheets:
        start = xlsx_reader.find_row(rows, "particulars")
        if start < 0:
            continue
        columns = header_map(rows[start])
        c_text = columns.get("particulars", 0)
        c_date = columns.get("posting_date", -1)
        c_debit = columns.get("debit", -1)
        c_credit = columns.get("credit", -1)
        for row in rows[start + 1:]:
            text = cell(row, c_text)
            if not text:
                continue
            debit = number(cell(row, c_debit))
            credit = number(cell(row, c_credit))
            entry = {
                "particulars": text,
                "date": cell(row, c_date),
                "debit": round(debit, 4),
                "credit": round(credit, 4),
            }
            match = _DP_PATTERN.search(text)
            if match:
                symbol = match.group("symbol").upper()
                entry["symbol"] = symbol
                entry["date"] = _iso(match.group("date"))
                entry["kind"] = "dp_charge"
                dp[symbol] = round(dp.get(symbol, 0.0) + debit, 4)
            entries.append(entry)
    return entries, dp


# ── Storage across monthly imports ────────────────────────────────────────

def period_key(period: dict) -> str:
    return f"{period.get('from', '')}..{period.get('to', '')}"


def overlaps(a: dict, b: dict) -> bool:
    """Do two statement periods cover any common day?"""
    a_from, a_to = a.get("from", ""), a.get("to", "")
    b_from, b_to = b.get("from", ""), b.get("to", "")
    if not all([a_from, a_to, b_from, b_to]):
        return False
    return a_from <= b_to and b_from <= a_to


def merge_statement(store: Dict[str, dict], statement: dict) -> dict:
    """Store one statement under its period. Returns what happened.

    ``replaced`` means the same period was already held and has been updated —
    the safe, expected path for re-exporting a month. ``conflicts`` lists
    stored periods that overlap this one without matching it; the statement is
    still stored (the user may be deliberately replacing a year with months)
    but the caller must surface them, because a book total that sums
    overlapping periods is wrong.
    """
    period = statement.get("period") or {}
    key = period_key(period)
    if not period.get("from") or not period.get("to"):
        return {"stored": False,
                "error": "The workbook has no date range in its title, so it "
                         "cannot be filed by period. Re-export it from "
                         "Console without editing the header rows."}
    conflicts = [k for k, held in store.items()
                 if k != key and overlaps(period, held.get("period") or {})]
    replaced = key in store
    store[key] = statement
    return {"stored": True, "period": key, "replaced": replaced,
            "conflicts": conflicts,
            "periods_held": sorted(store.keys())}


def book(store: Dict[str, dict]) -> dict:
    """Everything the stored statements say, summed across periods.

    Per-symbol realised figures add up across months: a stock sold in two
    different months is realised twice, and both are real.
    """
    by_symbol: Dict[str, dict] = {}
    charges_by_head: Dict[str, float] = {}
    dp_by_symbol: Dict[str, float] = {}
    totals = {"charges_actual": 0.0, "other_credit_debit": 0.0,
              "realized_pnl": 0.0, "unrealized_pnl": None}
    periods: List[dict] = []

    for key in sorted(store):
        statement = store[key] or {}
        period = statement.get("period") or {}
        summary = statement.get("summary") or {}
        periods.append({
            "period": key,
            "from": period.get("from"),
            "to": period.get("to"),
            "realized_pnl": summary.get("realized_pnl"),
            "charges_actual": summary.get("charges"),
            "symbols_closed": len(statement.get("closed") or []),
        })
        for row in statement.get("closed") or []:
            agg = by_symbol.setdefault(row["symbol"], {
                "symbol": row["symbol"], "isin": row.get("isin", ""),
                "qty": 0.0, "buy_value": 0.0, "sell_value": 0.0,
                "realized_pnl": 0.0, "periods": []})
            agg["qty"] = round(agg["qty"] + row["qty"], 4)
            agg["buy_value"] = round(agg["buy_value"] + row["buy_value"], 2)
            agg["sell_value"] = round(agg["sell_value"] + row["sell_value"], 2)
            agg["realized_pnl"] = round(
                agg["realized_pnl"] + row["realized_pnl"], 2)
            agg["periods"].append(key)
        for charge in statement.get("charges_actual") or []:
            charges_by_head[charge["head"]] = round(
                charges_by_head.get(charge["head"], 0.0) + charge["amount"], 4)
        for symbol, amount in (statement.get("dp_charges_by_symbol") or {}).items():
            dp_by_symbol[symbol] = round(dp_by_symbol.get(symbol, 0.0) + amount, 4)
        if summary.get("charges") is not None:
            totals["charges_actual"] = round(
                totals["charges_actual"] + summary["charges"], 2)
        if summary.get("other_credit_debit") is not None:
            totals["other_credit_debit"] = round(
                totals["other_credit_debit"] + summary["other_credit_debit"], 2)
        if summary.get("realized_pnl") is not None:
            totals["realized_pnl"] = round(
                totals["realized_pnl"] + summary["realized_pnl"], 2)
        # Unrealised is a point-in-time figure, not a sum: only the latest
        # statement's value means anything, and adding months would be
        # nonsense.
        if summary.get("unrealized_pnl") is not None:
            totals["unrealized_pnl"] = summary["unrealized_pnl"]

    conflicts = []
    keys = sorted(store)
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            if overlaps((store[left] or {}).get("period") or {},
                        (store[right] or {}).get("period") or {}):
                conflicts.append([left, right])

    return {
        "periods": periods,
        "by_symbol": sorted(by_symbol.values(), key=lambda r: r["symbol"]),
        "charges_by_head": [{"head": h, "amount": a}
                            for h, a in sorted(charges_by_head.items())],
        "dp_charges_by_symbol": dp_by_symbol,
        "totals": totals,
        "overlapping_periods": conflicts,
        "covers_from": min((p["from"] for p in periods if p["from"]), default=None),
        "covers_to": max((p["to"] for p in periods if p["to"]), default=None),
    }
