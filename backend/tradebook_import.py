"""
Zerodha Console tradebook CSV import — pure computation layer.

Console (console.zerodha.com → Reports → Tradebook) is the only place a full
dated trade history exists.  The Kite Connect / MCP API cannot supply it:
``get_trades`` is day-scoped and reports ``{"total": 0}`` on any day you have
not traded, which is why the equity ledger was empty while the mutual-fund
side had 24 dated transactions.

Everything here is deterministic and network-free.  ``main.py`` supplies the
uploaded CSV text and a symbol resolver; this returns ledger rows in exactly
the shape :mod:`equity_txns` already stores, so ``merge_trades`` does the
persisting and the de-duplication.

Design notes
------------
* **A trade is keyed to the PORTFOLIO's symbol, not to its exchange.**  This is
  the one thing that will silently corrupt the ledger if got wrong.
  ``kite_client.kite_to_yf_symbol`` appends ``.NS`` or ``.BO`` from the
  exchange, and a real holding is routinely accumulated across both (most
  shares bought on BSE, a few on NSE).  Suffixing by exchange would file those
  as ``X.BO`` and ``X.NS`` — two buckets for one position, each with a net
  quantity that matches nothing, and a purchase range computed from half the
  trades.  ISIN is the correct
  identity (it is exchange-independent) and the resolver prefers it.

* **Re-importing is safe and is the expected workflow.**  The user re-exports
  monthly, and consecutive exports overlap.  Every row carries Console's
  ``trade_id``, which :func:`equity_txns.merge_trades` de-duplicates on, so an
  overlapping month adds only what is genuinely new.  Nothing here needs to
  know which months have already been seen.

* **Sells are preserved, not filtered.**  A closed position contributes no
  holding but does contribute realised cashflows, which is what makes an honest XIRR
  possible.  Dropping sells would also break net-quantity reconciliation.

* **A row that cannot be trusted is skipped and COUNTED, with its reason.**  A
  silent skip turns "the export was malformed" into "you own less than you
  think", and the whole point of this import is to be reconcilable against the
  broker.
"""

from __future__ import annotations

import csv
import io
from typing import Callable, Dict, List, Optional, Sequence

import equity_txns
import xlsx_reader

# Console's own column names, as exported. Kept explicit so a format change
# upstream surfaces as "missing column" rather than as silently zero trades.
REQUIRED_COLUMNS = ("symbol", "trade_date", "trade_type", "quantity", "price")
OPTIONAL_COLUMNS = ("isin", "exchange", "segment", "series", "auction",
                    "trade_id", "order_id", "order_execution_time")

SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

SOURCE = "console_csv"


def _num(value, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _clean(value) -> str:
    return str(value or "").strip()


# ══════════════════════════════════════════════════════════════════════════
#  SYMBOL RESOLUTION
# ══════════════════════════════════════════════════════════════════════════

def build_symbol_resolver(
    portfolio: Sequence[dict] = (),
    kite_holdings: Sequence[dict] = (),
) -> Callable[[str, str, str], str]:
    """
    Build ``resolve(bare_symbol, isin, exchange) -> portfolio symbol``.

    Three lookups, most reliable first:

    1. **ISIN**, from Kite's holdings, which carry both ``isin`` and
       ``tradingsymbol``.  Exchange-independent and unambiguous.
    2. **Bare symbol**, against the portfolio's own keys with the suffix
       stripped.  Catches everything ISIN misses when holdings are unavailable.
    3. **Exchange suffix**, as a last resort for symbols the user does not
       hold — closed positions, which still belong in the ledger.

    The point of 1 and 2 is that a trade lands on the symbol the PORTFOLIO
    uses, so trades executed on either exchange accumulate in one bucket.
    """
    by_isin: Dict[str, str] = {}
    by_bare: Dict[str, str] = {}

    bare_to_portfolio: Dict[str, str] = {}
    for h in (portfolio or []):
        sym = _clean(h.get("symbol"))
        if not sym:
            continue
        bare_to_portfolio[_bare(sym).upper()] = sym

    # Kite holdings give the isin -> tradingsymbol bridge.
    for h in (kite_holdings or []):
        isin = _clean(h.get("isin")).upper()
        tsym = _clean(h.get("tradingsymbol")).upper()
        if not tsym:
            continue
        target = bare_to_portfolio.get(tsym)
        if target:
            if isin:
                by_isin[isin] = target
            by_bare[tsym] = target

    by_bare.update({k: v for k, v in bare_to_portfolio.items()
                    if k not in by_bare})

    def resolve(bare_symbol: str, isin: str = "", exchange: str = "NSE") -> str:
        key_isin = _clean(isin).upper()
        if key_isin and key_isin in by_isin:
            return by_isin[key_isin]
        key_bare = _clean(bare_symbol).upper()
        if key_bare in by_bare:
            return by_bare[key_bare]
        # Not held: a closed position. Canonicalise to one symbol regardless
        # of the exchange used for each fill. A position can be bought on NSE
        # and sold on BSE; splitting those trades into separate buckets would
        # corrupt realised P&L, net quantity, and XIRR. The original exchange
        # remains available on every imported ledger row.
        return f"{key_bare}.NS" if key_bare else ""

    return resolve


def _bare(symbol: str) -> str:
    """Strip a Yahoo exchange suffix: 'HDFCBANK.NS' -> 'HDFCBANK'."""
    s = _clean(symbol)
    for suffix in (".NS", ".BO"):
        if s.upper().endswith(suffix):
            return s[: -len(suffix)]
    return s


def canonicalize_store(
    store: Dict[str, List[dict]],
    resolve_symbol: Callable[[str, str, str], str],
) -> int:
    """Move previously imported Console rows to their current canonical key.

    This repairs ledgers written by older importer versions that keyed an
    unheld symbol by execution exchange. It deliberately touches only
    ``console_csv`` rows; manual and Kite-sourced history keeps its existing
    ownership. Returns the number of rows moved between buckets.
    """
    moved = 0
    console_rows: List[dict] = []

    for bucket_name in list(store):
        keep = []
        for row in store.get(bucket_name) or []:
            if _clean(row.get("source")) != SOURCE:
                keep.append(row)
                continue
            bare = (_clean(row.get("tradingsymbol"))
                    or _bare(_clean(row.get("symbol")) or bucket_name))
            target = resolve_symbol(
                bare,
                _clean(row.get("isin")),
                _clean(row.get("exchange")) or "NSE",
            )
            if target and target != bucket_name:
                row = dict(row)
                row["symbol"] = target
                moved += 1
            console_rows.append(row)
        if keep:
            store[bucket_name] = keep
        else:
            store.pop(bucket_name, None)

    # De-duplicate across the old buckets while rebuilding. Trade IDs are
    # broker-unique; the fallback covers exports that omit them.
    seen = set()
    for row in console_rows:
        trade_id = _clean(row.get("trade_id"))
        key = (("id", trade_id) if trade_id else (
            "fill", row.get("date"), row.get("type"), row.get("qty"),
            row.get("price"), row.get("tradingsymbol"), row.get("exchange")))
        if key in seen:
            continue
        seen.add(key)
        store.setdefault(row["symbol"], []).append(row)

    for rows in store.values():
        rows.sort(key=lambda r: (r.get("date", ""), r.get("trade_id", "")))
    return moved


# ══════════════════════════════════════════════════════════════════════════
#  PARSING
# ══════════════════════════════════════════════════════════════════════════

def _blank_report() -> dict:
    return {
        "rows_read": 0,
        "parsed": 0,
        "skipped": 0,
        "skip_reasons": {},
        "buys": 0,
        "sells": 0,
        "symbols": [],
        "date_from": None,
        "date_to": None,
        "missing_columns": [],
        "error": None,
    }



def parse_tradebook_csv(
    text: str,
    resolve_symbol: Optional[Callable[[str, str, str], str]] = None,
) -> tuple[List[dict], dict]:
    """
    Parse a Console tradebook CSV export into ledger rows.

    Returns ``(rows, report)``.  ``rows`` are in :mod:`equity_txns` shape and
    ready for ``merge_trades``; ``report`` says what happened, including every
    skipped line and why, because a malformed export must not read as a smaller
    portfolio.
    """
    report = _blank_report()
    if not _clean(text):
        report["error"] = "The file is empty."
        return [], report

    # utf-8-sig: Console exports sometimes carry a BOM, which would otherwise
    # become part of the first column name and make every column "missing".
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    field_names = [(_clean(f) or "").lower() for f in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in field_names]
    if missing:
        report["missing_columns"] = missing
        report["error"] = ("Not a Console tradebook export — missing column(s): "
                           + ", ".join(missing))
        return [], report
    return _rows_from_records(reader, resolve_symbol, report)


def parse_tradebook_xlsx(
    blob: bytes,
    resolve_symbol: Optional[Callable[[str, str, str], str]] = None,
) -> tuple[List[dict], dict]:
    """Parse a Console tradebook .xlsx into the same ledger rows.

    Console offers the tradebook as XLSX as well as CSV, and the XLSX is what
    the download button gives by default. The grid is identical once the
    client-id and title preamble is skipped, so the header is located by its
    columns and the rows go through exactly the same validation — an XLSX
    import can never accept a trade the CSV path would have rejected.
    """
    report = _blank_report()
    try:
        sheets = xlsx_reader.sheets(blob)
    except xlsx_reader.XlsxError as exc:
        report["error"] = str(exc)
        return [], report

    grid = next(iter(sheets.values()), [])
    period = xlsx_reader.period_from_title(grid)
    if period.get("from"):
        report["period"] = period
    header = xlsx_reader.find_row(grid, "symbol", "trade date", "quantity")
    if header < 0:
        report["error"] = ("Not a Console tradebook export — no trade table "
                           "found. A P&L statement goes to the P&L import.")
        return [], report

    columns = xlsx_reader.header_map(grid[header])
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        report["missing_columns"] = missing
        report["error"] = ("Not a Console tradebook export — missing column(s): "
                           + ", ".join(missing))
        return [], report

    records = []
    for row in grid[header + 1:]:
        record = {name: xlsx_reader.cell(row, index)
                  for name, index in columns.items()}
        if any(str(v).strip() for v in record.values()):
            records.append(record)
    return _rows_from_records(records, resolve_symbol, report)


def _rows_from_records(
    records,
    resolve_symbol: Optional[Callable[[str, str, str], str]],
    report: dict,
) -> tuple[List[dict], dict]:
    """Validate and normalise raw tradebook records, whatever read them."""
    resolve = resolve_symbol or build_symbol_resolver()

    def skip(reason: str) -> None:
        report["skipped"] += 1
        report["skip_reasons"][reason] = report["skip_reasons"].get(reason, 0) + 1

    rows: List[dict] = []
    seen_symbols = set()

    for raw in records:
        report["rows_read"] += 1
        row = {(_clean(k) or "").lower(): v for k, v in (raw or {}).items()}

        bare = _clean(row.get("symbol")).upper()
        if not bare:
            skip("no symbol")
            continue

        # Console gives a plain date plus a full execution timestamp. Prefer
        # the timestamp: two fills on the same day at different prices are
        # separate lots, and the time is what orders them.
        when = _clean(row.get("order_execution_time")) or _clean(row.get("trade_date"))
        if not when:
            skip("no date")
            continue
        date_only = when[:10]
        if len(date_only) != 10 or date_only[4] != "-":
            skip("unreadable date")
            continue

        qty = abs(_num(row.get("quantity")))
        if qty <= 0:
            skip("zero quantity")
            continue
        price = _num(row.get("price"))
        if price <= 0:
            skip("zero price")
            continue

        side_raw = _clean(row.get("trade_type")).upper()
        if side_raw.startswith("S"):
            side = SIDE_SELL
        elif side_raw.startswith("B"):
            side = SIDE_BUY
        else:
            # Never guessed. normalize_kite_trade defaults an unknown side to
            # BUY, which would turn every sell in this file into a purchase and
            # silently inflate the position.
            skip(f"unknown trade_type '{side_raw or '(blank)'}'")
            continue

        exchange = _clean(row.get("exchange")).upper() or "NSE"
        isin = _clean(row.get("isin")).upper()
        symbol = resolve(bare, isin, exchange)
        if not symbol:
            skip("could not resolve symbol")
            continue

        trade_id = _clean(row.get("trade_id")) or _clean(row.get("order_id"))

        rows.append({
            "symbol": symbol,
            "tradingsymbol": bare,
            "exchange": exchange,
            "isin": isin,
            "date": date_only,
            "executed_at": when.replace(" ", "T"),
            "type": side,
            "qty": round(qty, 4),
            "price": round(price, 4),
            "amount": round(qty * price, 2),
            "trade_id": trade_id,
            "order_id": _clean(row.get("order_id")),
            "segment": _clean(row.get("segment")),
            "series": _clean(row.get("series")),
            "auction": _clean(row.get("auction")),
            "source": SOURCE,
        })
        report["parsed"] += 1
        report["buys" if side == SIDE_BUY else "sells"] += 1
        seen_symbols.add(symbol)
        if report["date_from"] is None or date_only < report["date_from"]:
            report["date_from"] = date_only
        if report["date_to"] is None or date_only > report["date_to"]:
            report["date_to"] = date_only

    report["symbols"] = sorted(seen_symbols)
    return rows, report


# ══════════════════════════════════════════════════════════════════════════
#  RECONCILIATION
# ══════════════════════════════════════════════════════════════════════════

def reconcile(store: Dict[str, List[dict]],
              holdings: Sequence[dict]) -> List[dict]:
    """
    Compare the ledger against what the broker says you hold.

    This is the check that makes an import trustworthy rather than merely
    complete-looking. A complete CSV reproduces Kite's quantity and average
    price exactly, so a mismatch means the export is partial, which the user is told rather than left to
    discover through a wrong purchase range.
    """
    out: List[dict] = []
    for h in (holdings or []):
        sym = _clean(h.get("symbol"))
        if not sym:
            continue
        held = _num(h.get("shares") or h.get("quantity"))
        avg_held = _num(h.get("avg_cost") or h.get("average_price"))
        # Same-underlying, different-suffix lookup. Keyed exactly, this
        # reported "no_history" for holdings whose ledger was filed under the
        # other exchange, which sent the user back to re-import a tradebook
        # that was already complete.
        txns = equity_txns.txns_for(store, sym, h.get("isin") or "")

        buys = [t for t in txns if _clean(t.get("type")).upper() == SIDE_BUY]
        sells = [t for t in txns if _clean(t.get("type")).upper() == SIDE_SELL]
        ledger_qty = (sum(_num(t.get("qty")) for t in buys)
                      - sum(_num(t.get("qty")) for t in sells))

        cost = sum(_num(t.get("amount")) for t in buys)
        units = sum(_num(t.get("qty")) for t in buys)
        avg_ledger = round(cost / units, 4) if units else None

        if not txns:
            status = "no_history"
        elif abs(ledger_qty - held) <= max(1.0, held * 0.02):
            status = "exact"
        elif ledger_qty < held:
            status = "partial"
        else:
            status = "over"

        out.append({
            "symbol": sym,
            "held_qty": held,
            "ledger_qty": round(ledger_qty, 4),
            "buys": len(buys),
            "sells": len(sells),
            "avg_cost_held": avg_held or None,
            "avg_cost_ledger": avg_ledger,
            "status": status,
        })
    out.sort(key=lambda r: (r["status"] != "no_history", r["symbol"]))
    return out
