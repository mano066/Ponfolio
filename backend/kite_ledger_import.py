"""Kite Console funds-ledger import — pure computation layer.

The ledger is the third Console export, and the only one that carries **TDS**.
Neither the tradebook nor the P&L statement mentions it: the tradebook is
fills, the P&L charge block covers brokerage, STT, GST, stamp duty, SEBI and
IPFT, and TDS appears in none of them. It is a real deduction from the trading
account, so a "what did this cost me" figure without it is short by whatever
was withheld.

Provisional TDS is the trap
---------------------------
Console posts TDS in two shapes, and they must never be added together:

  ``TDS Voucher``              — TDS actually deducted. A cost.
  ``Provisional TDS Voucher``  — an amount BLOCKED against a pending
                                 liability, then usually REVERSED a day or
                                 two later. The pair nets to zero.

A real ledger can show both in the same month: a small amount genuinely
deducted, and a provisional block many times larger that is reversed a day
later. Summing every row whose text contains "TDS" would then overstate the
tax many times over, from the one export that is supposed to make the number
exact.
So blocked and reversed are tracked separately, netted, and what is still
outstanding is reported as outstanding rather than as spent.

Periods, as with the P&L statements
-----------------------------------
Console stamps the range into the title ("Ledger for Equity from 2026-09-02 to
2026-09-09"), so a ledger is filed under its period: re-importing a month
replaces it, and an overlap is reported instead of being double-counted. See
:mod:`kite_pnl_import`, whose storage rules this mirrors deliberately — one
mental model for all three imports.
"""

from __future__ import annotations

import re
from typing import Dict, List

import xlsx_reader
from xlsx_reader import cell, header_map, number

SOURCE = "console_ledger_xlsx"

# Voucher types, normalised to lowercase for matching.
TDS_ACTUAL = "tds voucher"
TDS_PROVISIONAL = "provisional tds voucher"

_BLOCKED = re.compile(r"\bblock(ed)?\b", re.I)
_REVERSED = re.compile(r"\brevers(ed|al)\b", re.I)


def parse_ledger_workbook(blob: bytes) -> dict:
    """Parse a Console ledger .xlsx into one normalised statement."""
    sheets = xlsx_reader.sheets(blob)
    grid = next(iter(sheets.values()), [])
    period = xlsx_reader.period_from_title(grid)

    header = xlsx_reader.find_row(grid, "particulars", "posting date")
    if header < 0:
        return {
            "error": "This workbook has no ledger table. Export Console -> "
                     "Reports -> Ledger as XLSX.",
            "period": period,
        }

    columns = header_map(grid[header])
    c_text = columns.get("particulars", -1)
    c_date = columns.get("posting_date", -1)
    c_centre = columns.get("cost_center", -1)
    c_voucher = columns.get("voucher_type", -1)
    c_debit = columns.get("debit", -1)
    c_credit = columns.get("credit", -1)
    c_balance = columns.get("net_balance", -1)

    entries: List[dict] = []
    opening = closing = None
    for row in grid[header + 1:]:
        text = cell(row, c_text)
        if not text:
            continue
        label = text.strip().lower()
        balance = number(cell(row, c_balance))
        # Opening/closing carry a balance and nothing else; they are anchors,
        # not transactions, and must not be counted as movement.
        if label.startswith("opening balance"):
            opening = round(balance, 4)
            continue
        if label.startswith("closing balance"):
            closing = round(balance, 4)
            continue
        voucher = cell(row, c_voucher)
        entries.append({
            "particulars": text,
            "date": cell(row, c_date),
            "cost_center": cell(row, c_centre),
            "voucher_type": voucher,
            "debit": round(number(cell(row, c_debit)), 4),
            "credit": round(number(cell(row, c_credit)), 4),
            "balance": round(balance, 4),
            "kind": _classify(text, voucher),
        })

    return {
        "source": SOURCE,
        "period": period,
        "opening_balance": opening,
        "closing_balance": closing,
        "entries": entries,
        "tds": summarise_tds(entries),
        "funds": _summarise_funds(entries),
    }


def _classify(particulars: str, voucher_type: str) -> str:
    """What kind of ledger line this is, for grouping in the UI."""
    voucher = str(voucher_type or "").strip().lower()
    text = str(particulars or "").strip().lower()
    if voucher == TDS_PROVISIONAL or ("provisional" in text and "tds" in text):
        if _REVERSED.search(text):
            return "tds_provisional_reversed"
        if _BLOCKED.search(text):
            return "tds_provisional_blocked"
        return "tds_provisional"
    if voucher == TDS_ACTUAL or re.search(r"\btds\b", text):
        return "tds"
    if "settlement" in text:
        return "settlement"
    if voucher.startswith("bank receipt") or "funds added" in text:
        return "funds_in"
    if voucher.startswith("bank payment") or "withdraw" in text:
        return "funds_out"
    return "other"


def summarise_tds(entries: List[dict]) -> dict:
    """Split TDS into deducted, blocked and reversed, and net them honestly.

    ``deducted`` is the only figure that is a cost. ``provisional_outstanding``
    is money currently withheld that has not been reversed *yet*; it is
    reported so it can be seen, never folded into a cost.
    """
    deducted = 0.0
    blocked = 0.0
    reversed_ = 0.0
    rows: List[dict] = []
    for entry in entries:
        kind = entry["kind"]
        if not kind.startswith("tds"):
            continue
        rows.append(entry)
        # A debit takes money out; a credit gives it back. Netting per row
        # keeps a refunded deduction from reading as a charge.
        net = entry["debit"] - entry["credit"]
        if kind == "tds":
            deducted += net
        elif kind == "tds_provisional_reversed":
            reversed_ += entry["credit"] - entry["debit"]
        elif kind in ("tds_provisional_blocked", "tds_provisional"):
            blocked += net

    outstanding = round(blocked - reversed_, 2)
    return {
        "deducted": round(deducted, 2),
        "provisional_blocked": round(blocked, 2),
        "provisional_reversed": round(reversed_, 2),
        # Negative would mean more was reversed than this period blocked, which
        # happens when the block and its reversal fall in different exports.
        "provisional_outstanding": outstanding,
        "entries": rows,
        "basis": "Deducted is TDS actually withheld. Provisional amounts are "
                 "blocked against a pending liability and normally reversed "
                 "within days; they are shown separately and never counted as "
                 "a cost.",
    }


def _summarise_funds(entries: List[dict]) -> dict:
    added = sum(e["credit"] for e in entries if e["kind"] == "funds_in")
    withdrawn = sum(e["debit"] for e in entries if e["kind"] == "funds_out")
    return {"added": round(added, 2), "withdrawn": round(withdrawn, 2)}


# ── Storage across monthly imports (mirrors kite_pnl_import) ──────────────

def period_key(period: dict) -> str:
    return f"{period.get('from', '')}..{period.get('to', '')}"


def overlaps(a: dict, b: dict) -> bool:
    a_from, a_to = a.get("from", ""), a.get("to", "")
    b_from, b_to = b.get("from", ""), b.get("to", "")
    if not all([a_from, a_to, b_from, b_to]):
        return False
    return a_from <= b_to and b_from <= a_to


def merge_ledger(store: Dict[str, dict], statement: dict) -> dict:
    """File one ledger under its period. Same rules as the P&L statements."""
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
            "conflicts": conflicts, "periods_held": sorted(store.keys())}


def book(store: Dict[str, dict]) -> dict:
    """Everything the stored ledgers say, summed across periods."""
    periods: List[dict] = []
    deducted = blocked = reversed_ = 0.0
    added = withdrawn = 0.0
    tds_rows: List[dict] = []

    for key in sorted(store):
        statement = store[key] or {}
        period = statement.get("period") or {}
        tds = statement.get("tds") or {}
        funds = statement.get("funds") or {}
        periods.append({
            "period": key,
            "from": period.get("from"),
            "to": period.get("to"),
            "tds_deducted": tds.get("deducted"),
            "provisional_outstanding": tds.get("provisional_outstanding"),
            "entries": len(statement.get("entries") or []),
        })
        deducted += tds.get("deducted") or 0.0
        blocked += tds.get("provisional_blocked") or 0.0
        reversed_ += tds.get("provisional_reversed") or 0.0
        added += funds.get("added") or 0.0
        withdrawn += funds.get("withdrawn") or 0.0
        tds_rows.extend(tds.get("entries") or [])

    conflicts = []
    keys = sorted(store)
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            if overlaps((store[left] or {}).get("period") or {},
                        (store[right] or {}).get("period") or {}):
                conflicts.append([left, right])

    tds_rows.sort(key=lambda r: str(r.get("date") or ""))
    return {
        "periods": periods,
        "tds": {
            "deducted": round(deducted, 2),
            "provisional_blocked": round(blocked, 2),
            "provisional_reversed": round(reversed_, 2),
            "provisional_outstanding": round(blocked - reversed_, 2),
            "entries": tds_rows,
        },
        "funds": {"added": round(added, 2), "withdrawn": round(withdrawn, 2)},
        "overlapping_periods": conflicts,
        "covers_from": min((p["from"] for p in periods if p["from"]), default=None),
        "covers_to": max((p["to"] for p in periods if p["to"]), default=None),
    }
