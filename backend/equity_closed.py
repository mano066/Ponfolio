"""Closed equity positions: FIFO matching, statutory charges, realised P&L.

The dated ledger in :mod:`equity_txns` already holds every buy and sell. What
it cannot answer on its own is the question that closes a trade out: *what did
I actually make on the shares I have sold?* Holdings show unrealised gain on
what is still open; this module reports the other half.

What is measured, and what is estimated
---------------------------------------
Three different kinds of number come out of here and they are never blended:

  MEASURED   buy price, sell price, quantity, dates. Straight from the
             tradebook, so gross realised P&L is exact.
  ESTIMATED  charges. A Console tradebook carries no brokerage, STT, GST or
             stamp duty — those live on the contract note, which is not
             imported — so they are computed from the statutory rate card in
             :data:`CHARGES`. Every field derived from them is labelled
             ``estimated`` and the rate card is returned alongside the numbers
             so the figures can be checked rather than believed.
  INDICATIVE tax. Classified per lot as short or long term on the 12-month
             equity rule, then costed at the statutory rates. This is an
             arithmetic illustration of one year's equity gains, NOT a tax
             computation: it knows nothing about set-off against losses
             elsewhere, carried-forward losses, other capital assets, or the
             taxpayer's slab. It is labelled indicative for that reason.

FIFO, and what happens when the ledger is short
-----------------------------------------------
Sells consume the oldest open buy lot first, which is both the Income Tax
Act's ordering for listed equity and Zerodha's own. When a sell cannot be
matched — the tradebook starts after shares were already held, so the buy is
simply missing — the unmatched quantity is reported as ``unmatched_sell_qty``
and contributes to nothing. Seeding a cost for it would fabricate a P&L, and
this file would rather report a gap than a plausible number.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import equity_txns
import kite_ledger_import
import kite_pnl_import

# ── Statutory rate card, Indian listed equity, DELIVERY segment ──
#
# Rates as applicable for equity delivery. Kept as data, and echoed in the API
# response, so a rate change is one edit here and the UI can always show what
# it charged against. Percentages are fractions of turnover.
CHARGES = {
    "brokerage_pct": 0.0,          # Zerodha: zero brokerage on delivery
    "stt_buy_pct": 0.001,          # 0.1% on buy turnover
    "stt_sell_pct": 0.001,         # 0.1% on sell turnover
    "exchange_nse_pct": 0.0000297,  # NSE 0.00297%
    "exchange_bse_pct": 0.0000375,  # BSE 0.00375% (A group)
    "sebi_pct": 0.000001,          # SEBI turnover fee, Rs 10 per crore
    "stamp_duty_buy_pct": 0.00015,  # 0.015% on buy, buyer pays
    "gst_pct": 0.18,               # on brokerage + exchange + SEBI
    "dp_charge_per_sell": 13.5,    # per scrip per day a sale is made
    "dp_charge_gst": True,
}

SHORT_TERM_DAYS = 365              # 12 months for listed equity
TAX = {
    "stcg_pct": 0.20,              # short-term capital gains on equity
    "ltcg_pct": 0.125,             # long-term, beyond the exemption
    "ltcg_exemption": 125000.0,    # per financial year, across LTCG
}


def _num(value, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if out == out and abs(out) != float("inf") else default
    except (TypeError, ValueError):
        return default


def _exchange_pct(exchange: str) -> float:
    """BSE and NSE charge different transaction fees; default to the higher."""
    return (CHARGES["exchange_bse_pct"]
            if str(exchange or "").strip().upper().startswith("B")
            else CHARGES["exchange_nse_pct"])


def side_charges(turnover: float, *, side: str, exchange: str = "NSE") -> dict:
    """Estimated statutory charges on one side of a delivery trade.

    Returns each component rather than a total: a single "charges" figure
    cannot be checked against a contract note, and the components can.
    """
    turnover = max(_num(turnover), 0.0)
    buying = str(side).upper() == "BUY"
    brokerage = turnover * CHARGES["brokerage_pct"]
    stt = turnover * (CHARGES["stt_buy_pct"] if buying
                      else CHARGES["stt_sell_pct"])
    exchange_fee = turnover * _exchange_pct(exchange)
    sebi = turnover * CHARGES["sebi_pct"]
    stamp = turnover * CHARGES["stamp_duty_buy_pct"] if buying else 0.0
    gst = (brokerage + exchange_fee + sebi) * CHARGES["gst_pct"]
    return {
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange": round(exchange_fee, 2),
        "sebi": round(sebi, 2),
        "stamp_duty": round(stamp, 2),
        "gst": round(gst, 2),
        "total": round(brokerage + stt + exchange_fee + sebi + stamp + gst, 2),
    }


def dp_charge() -> float:
    """Depository charge on a sale: flat per scrip per day, plus GST."""
    base = CHARGES["dp_charge_per_sell"]
    return round(base * (1 + CHARGES["gst_pct"]) if CHARGES["dp_charge_gst"]
                 else base, 2)


def _rows_by_underlying(store: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """Merge every suffix bucket into one history per company.

    A position accumulated on both exchanges is one position — see
    :func:`equity_txns.txns_for`, which this mirrors for the whole store.
    """
    merged: Dict[str, List[dict]] = {}
    for key, bucket in (store or {}).items():
        merged.setdefault(equity_txns.bare_symbol(key), []).extend(bucket or [])
    for rows in merged.values():
        rows.sort(key=lambda r: (str(r.get("date") or ""),
                                 str(r.get("trade_id") or "")))
    return merged


def _term(days: int) -> str:
    return "long" if days > SHORT_TERM_DAYS else "short"


def match_fifo(txns: Iterable[dict]) -> dict:
    """Match sells against buys, oldest lot first.

    Returns ``{lots, unmatched_sell_qty, open_qty, open_cost}``. ``lots`` are
    the closed round trips, each carrying both legs and their measured P&L.
    """
    open_lots: List[dict] = []          # FIFO queue of unsold buys
    closed: List[dict] = []
    unmatched = 0.0

    for txn in txns or []:
        qty = _num(txn.get("qty"))
        price = _num(txn.get("price"))
        if qty <= 0:
            continue
        when = equity_txns.parse_date(txn.get("date"))
        side = str(txn.get("type") or "").upper()
        exchange = txn.get("exchange") or "NSE"

        if side != "SELL":
            open_lots.append({"qty": qty, "price": price, "date": when,
                              "exchange": exchange})
            continue

        remaining = qty
        while remaining > 0 and open_lots:
            lot = open_lots[0]
            take = min(remaining, lot["qty"])
            lot["qty"] -= take
            remaining -= take
            buy_value = take * lot["price"]
            sell_value = take * price
            days = ((when - lot["date"]).days
                    if when and lot["date"] else 0)
            closed.append({
                "qty": round(take, 4),
                "buy_date": lot["date"].strftime("%Y-%m-%d") if lot["date"] else None,
                "buy_price": round(lot["price"], 4),
                "buy_value": round(buy_value, 2),
                "buy_exchange": lot["exchange"],
                "sell_date": when.strftime("%Y-%m-%d") if when else None,
                "sell_price": round(price, 4),
                "sell_value": round(sell_value, 2),
                "sell_exchange": exchange,
                "gross_pnl": round(sell_value - buy_value, 2),
                "gross_pnl_pct": round((sell_value - buy_value) / buy_value * 100, 2)
                if buy_value > 0 else None,
                "days_held": days,
                "term": _term(days),
            })
            if lot["qty"] <= 1e-9:
                open_lots.pop(0)
        if remaining > 0:
            # The buy predates the imported tradebook. Report the hole.
            unmatched += remaining

    return {
        "lots": closed,
        "unmatched_sell_qty": round(unmatched, 4),
        "open_qty": round(sum(l["qty"] for l in open_lots), 4),
        "open_cost": round(sum(l["qty"] * l["price"] for l in open_lots), 2),
    }


def _cost_lot(lot: dict) -> dict:
    """Attach estimated charges and net P&L to one closed lot."""
    buy = side_charges(lot["buy_value"], side="BUY",
                       exchange=lot.get("buy_exchange"))
    sell = side_charges(lot["sell_value"], side="SELL",
                        exchange=lot.get("sell_exchange"))
    charges = round(buy["total"] + sell["total"], 2)
    # The per-component split is deliberately NOT attached to every lot. It
    # made the response 71KB for 123 round trips, nothing renders it, and the
    # rate card that produced it ships once under `charges_basis` — so a
    # reader can still reproduce any lot's figure.
    return {
        **lot,
        "charges_estimated": charges,
        "net_pnl_estimated": round(lot["gross_pnl"] - charges, 2),
    }



# Console writes the event date into the TDS narration itself — "TDS payable
# on Equity Intraday for 2026-08-07", "TDS payable on capital gains for
# 2026-08-14" — which is what makes a per-symbol figure measurable rather than
# guessed.
# Console writes the event date after "for" on a TDS voucher and after "on"
# for a DP charge, so both prepositions are accepted.
_TDS_DATE = re.compile(r"\b(?:for|on)\s+(?P<iso>\d{4}-\d{2}-\d{2})"
                       r"|\b(?:for|on)\s+(?P<dmy>\d{2}/\d{2}/\d{4})", re.I)


def _tds_event_date(particulars: str) -> Optional[str]:
    match = _TDS_DATE.search(str(particulars or ""))
    if not match:
        return None
    if match.group("iso"):
        return match.group("iso")
    day, month, year = match.group("dmy").split("/")
    return f"{year}-{month}-{day}"


def attribute_tds(per_symbol: List[dict], entries: List[dict]) -> dict:
    """Assign each TDS deduction to the position that produced it.

    Console does not name a scrip on a TDS voucher, but it does name the DATE,
    and the tradebook says what was sold that day. An intraday deduction is
    matched against lots closed the same day they were opened; anything else is
    matched against the delivery sales settling that date. Where a single
    position matches, the attribution is exact; where several traded that day
    it is split by sell value and flagged as apportioned, and where nothing
    matches the amount stays in the book total as unattributed rather than
    being spread across unrelated positions.
    """
    for row in per_symbol:
        row["tds_attributed"] = 0.0
        row["tds_source"] = "none"

    by_symbol = {row["symbol"]: row for row in per_symbol}
    attributed = 0.0
    unattributed = 0.0
    notes: List[dict] = []

    for entry in entries or []:
        if entry.get("kind") != "tds":
            continue
        amount = round(_num(entry.get("debit")) - _num(entry.get("credit")), 2)
        if abs(amount) < 0.005:
            continue
        when = _tds_event_date(entry.get("particulars"))
        intraday = "intraday" in str(entry.get("particulars") or "").lower()

        # Candidate lots: same sell date, and the right holding period for
        # what the narration says the tax was on.
        candidates: Dict[str, float] = {}
        if when:
            for row in per_symbol:
                for lot in row["lots"]:
                    if lot.get("sell_date") != when:
                        continue
                    same_day = lot.get("days_held") == 0
                    if intraday != same_day:
                        continue
                    candidates[row["symbol"]] = candidates.get(
                        row["symbol"], 0.0) + _num(lot.get("sell_value"))
            if not candidates:
                # The narration's period did not match; fall back to anything
                # sold that day rather than dropping a real deduction.
                for row in per_symbol:
                    for lot in row["lots"]:
                        if lot.get("sell_date") == when:
                            candidates[row["symbol"]] = candidates.get(
                                row["symbol"], 0.0) + _num(lot.get("sell_value"))

        if not candidates:
            unattributed = round(unattributed + amount, 2)
            notes.append({"particulars": entry.get("particulars"),
                          "date": entry.get("date"), "amount": amount,
                          "event_date": when, "matched": []})
            continue

        total_value = sum(candidates.values()) or 1.0
        source = "date_matched" if len(candidates) == 1 else "apportioned"
        assigned = 0.0
        ordered = sorted(candidates.items(), key=lambda kv: -kv[1])
        for index, (symbol, value) in enumerate(ordered):
            share = (round(amount - assigned, 2) if index == len(ordered) - 1
                     else round(amount * value / total_value, 2))
            assigned = round(assigned + share, 2)
            row = by_symbol[symbol]
            row["tds_attributed"] = round(row["tds_attributed"] + share, 2)
            row["tds_source"] = source
        attributed = round(attributed + amount, 2)
        notes.append({"particulars": entry.get("particulars"),
                      "date": entry.get("date"), "amount": amount,
                      "event_date": when, "matched": list(candidates)})

    # Net of everything measurable: realised, less estimated charges, less the
    # TDS actually withheld on that position.
    for row in per_symbol:
        net = row.get("net_pnl_estimated")
        if net is not None:
            row["net_after_tds"] = round(net - row["tds_attributed"], 2)
            invested = row.get("buy_value") or 0
            row["net_after_tds_pct"] = (round(row["net_after_tds"] / invested * 100, 2)
                                        if invested > 0 else None)
    return {"attributed": attributed, "unattributed": unattributed,
            "assignments": notes}


def closed_positions(store: Dict[str, List[dict]],
                     as_of: Optional[datetime] = None,
                     statements: Optional[Dict[str, dict]] = None,
                     ledgers: Optional[Dict[str, dict]] = None) -> dict:
    """Every closed round trip in the ledger, with rollups and a book total.

    ``statements`` is the store of imported Kite Console P&L statements. When
    one covers a symbol, the broker's own realised figure is MEASURED and
    supersedes this module's FIFO reconstruction, and the period's real
    charges supersede the rate-card estimate. Both are still computed, and
    both are reported side by side under ``reconciliation``: on a complete
    tradebook they agree to the paisa, and a disagreement is the signal that
    the ledger is missing trades.

    ``as_of`` is accepted for symmetry with the XIRR helpers and for tests;
    nothing here depends on the current date except the response stamp.
    """
    per_symbol: List[dict] = []
    all_lots: List[dict] = []
    unmatched_total = 0.0
    statement_book = (kite_pnl_import.book(statements) if statements else None)
    ledger_book = (kite_ledger_import.book(ledgers) if ledgers else None)
    broker_by_symbol = {r["symbol"]: r
                        for r in (statement_book or {}).get("by_symbol", [])}
    broker_dp = (statement_book or {}).get("dp_charges_by_symbol", {}) or {}

    for bare, rows in sorted(_rows_by_underlying(store).items()):
        matched = match_fifo(rows)
        if not matched["lots"] and not matched["unmatched_sell_qty"]:
            continue
        lots = [_cost_lot(lot) for lot in matched["lots"]]
        for lot in lots:
            lot["symbol"] = bare
        # One DP charge per scrip per day on which anything was sold, not one
        # per matched lot: three lots closed by a single sell cost one charge.
        # Console itemises the real DP charge per symbol and date, so when a
        # statement covers this symbol that measured amount is used instead.
        sell_days = {lot["sell_date"] for lot in lots if lot["sell_date"]}
        dp_actual = broker_dp.get(bare)
        dp_total = (round(dp_actual, 2) if dp_actual is not None
                    else round(dp_charge() * len(sell_days), 2))

        gross = round(sum(l["gross_pnl"] for l in lots), 2)
        charges = round(sum(l["charges_estimated"] for l in lots) + dp_total, 2)
        invested = round(sum(l["buy_value"] for l in lots), 2)
        realised = round(sum(l["sell_value"] for l in lots), 2)
        broker = broker_by_symbol.get(bare)
        broker_realized = broker["realized_pnl"] if broker else None
        per_symbol.append({
            "symbol": bare,
            "lots": lots,
            # The broker's own realised figure, when a statement covers this
            # symbol. This is measured, not reconstructed: it is what Zerodha
            # says the position made, and the UI shows it in preference to
            # `gross_pnl` while keeping both visible.
            "realized_broker": broker_realized,
            "realized_source": "broker_statement" if broker else "ledger_fifo",
            "realized_agrees": (None if broker_realized is None
                                else abs(broker_realized - gross) <= 1.0),
            "dp_charges_source": ("broker_statement" if dp_actual is not None
                                  else "estimated"),
            "trades": len(lots),
            "qty_closed": round(sum(l["qty"] for l in lots), 4),
            "buy_value": invested,
            "sell_value": realised,
            "gross_pnl": gross,
            "dp_charges_estimated": dp_total,
            "charges_estimated": charges,
            "net_pnl_estimated": round(gross - charges, 2),
            "net_pnl_pct_estimated": round((gross - charges) / invested * 100, 2)
            if invested > 0 else None,
            "unmatched_sell_qty": matched["unmatched_sell_qty"],
            "still_open_qty": matched["open_qty"],
            "first_buy": min((l["buy_date"] for l in lots if l["buy_date"]),
                             default=None),
            "last_sell": max((l["sell_date"] for l in lots if l["sell_date"]),
                             default=None),
        })
        all_lots.extend(lots)
        unmatched_total += matched["unmatched_sell_qty"]

    tds_split = (attribute_tds(per_symbol, ledger_book["tds"]["entries"])
                 if ledger_book and ledger_book.get("periods") else None)

    short_gain = round(sum(l["net_pnl_estimated"] for l in all_lots
                           if l["term"] == "short"), 2)
    long_gain = round(sum(l["net_pnl_estimated"] for l in all_lots
                          if l["term"] == "long"), 2)
    gross = round(sum(l["gross_pnl"] for l in all_lots), 2)
    charges = round(sum(s["charges_estimated"] for s in per_symbol), 2)
    net = round(gross - charges, 2)
    invested = round(sum(s["buy_value"] for s in per_symbol), 2)
    wins = sum(1 for l in all_lots if l["net_pnl_estimated"] > 0)

    taxable_long = max(long_gain - TAX["ltcg_exemption"], 0.0)
    tax_indicative = round(
        max(short_gain, 0.0) * TAX["stcg_pct"] + taxable_long * TAX["ltcg_pct"], 2)

    # Book-level measured figures, when statements have been imported.
    broker_realized = None
    charges_actual = None
    other_credit_debit = None
    period_net = None
    if statement_book and statement_book.get("periods"):
        totals_actual = statement_book["totals"]
        broker_realized = totals_actual.get("realized_pnl")
        charges_actual = totals_actual.get("charges_actual")
        other_credit_debit = totals_actual.get("other_credit_debit")
        if broker_realized is not None and charges_actual is not None:
            period_net = round(
                broker_realized - charges_actual + (other_credit_debit or 0.0), 2)

    return {
        "as_of": (as_of or datetime.now()).astimezone().isoformat(timespec="seconds"),
        "symbols": per_symbol,
        "statement": ({
            "periods": statement_book["periods"],
            "covers_from": statement_book["covers_from"],
            "covers_to": statement_book["covers_to"],
            "overlapping_periods": statement_book["overlapping_periods"],
            "charges_by_head": statement_book["charges_by_head"],
            # Console's charge total covers EVERY trade in the period,
            # including the buys of positions still held. It is therefore the
            # period's cost of trading, not the cost of these closed lots, and
            # `period_net` is named for what it is rather than being passed off
            # as net realised profit.
            "realized_pnl": broker_realized,
            "charges_actual": charges_actual,
            "other_credit_debit": other_credit_debit,
            "period_net": period_net,
            "unrealized_pnl": statement_book["totals"].get("unrealized_pnl"),
            "basis": "Measured: Zerodha Console P&L statement. Charges cover "
                     "all trades in the period, including buys of holdings "
                     "still open, so period net is not the same figure as net "
                     "realised on closed lots.",
        } if statement_book and statement_book.get("periods") else None),
        # TDS lives only in the funds ledger. It is a real deduction and is
        # reported next to the charges rather than inside them, because
        # Console bills it as a separate voucher and nothing in the P&L
        # statement's charge block includes it.
        "tds": ({
            "deducted": ledger_book["tds"]["deducted"],
            "provisional_blocked": ledger_book["tds"]["provisional_blocked"],
            "provisional_reversed": ledger_book["tds"]["provisional_reversed"],
            "provisional_outstanding": ledger_book["tds"]["provisional_outstanding"],
            "entries": ledger_book["tds"]["entries"],
            "attributed": tds_split["attributed"] if tds_split else 0.0,
            "unattributed": tds_split["unattributed"] if tds_split else 0.0,
            "assignments": tds_split["assignments"] if tds_split else [],
            "covers_from": ledger_book["covers_from"],
            "covers_to": ledger_book["covers_to"],
            "overlapping_periods": ledger_book["overlapping_periods"],
            "periods": ledger_book["periods"],
            "basis": "Measured: Console funds ledger. Deducted is TDS "
                     "actually withheld; a provisional amount is blocked "
                     "against a pending liability and normally reversed "
                     "within days, so it is never counted as a cost.",
        } if ledger_book and ledger_book.get("periods") else None),
        "reconciliation": {
            "ledger_fifo_gross": gross,
            "broker_realized": broker_realized,
            "gross_agrees": (None if broker_realized is None
                             else abs(broker_realized - gross) <= 1.0),
            "charges_estimated": charges,
            "charges_actual": charges_actual,
            "charges_estimate_error": (None if charges_actual is None
                                       else round(charges - charges_actual, 2)),
            "note": "FIFO from your tradebook against the broker's own "
                    "statement. A gap means the ledger is missing trades.",
        },
        "totals": {
            "symbols_closed": len(per_symbol),
            "trades": len(all_lots),
            "buy_value": invested,
            "sell_value": round(sum(s["sell_value"] for s in per_symbol), 2),
            "gross_pnl": gross,
            "charges_estimated": charges,
            "net_pnl_estimated": net,
            "net_pnl_pct_estimated": round(net / invested * 100, 2)
            if invested > 0 else None,
            "short_term_net": short_gain,
            "long_term_net": long_gain,
            "wins": wins,
            "losses": len(all_lots) - wins,
            "win_rate_pct": round(wins / len(all_lots) * 100, 2) if all_lots else None,
            "unmatched_sell_qty": round(unmatched_total, 4),
            "tds_attributed": tds_split["attributed"] if tds_split else None,
            "net_after_tds": (round(net - tds_split["attributed"], 2)
                              if tds_split else None),
        },
        "tax_indicative": {
            "short_term_gain": max(short_gain, 0.0),
            "long_term_gain": max(long_gain, 0.0),
            "ltcg_exemption_applied": min(max(long_gain, 0.0), TAX["ltcg_exemption"]),
            "tax": tax_indicative,
            "rates": dict(TAX),
            "basis": "Statutory rates on this ledger's gains only. Ignores "
                     "losses set off elsewhere, carried-forward losses, other "
                     "capital assets and the financial-year boundary. Not a "
                     "tax computation.",
        },
        "charges_basis": {
            "rates": dict(CHARGES),
            "dp_charge_per_sell_day": dp_charge(),
            "note": "Estimated from the statutory delivery rate card. A "
                    "tradebook carries no contract-note charges, so these are "
                    "computed, not billed amounts.",
        },
    }
