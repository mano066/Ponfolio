"""Equity transaction store and XIRR for Ponfolio.

Equity holdings from Kite arrive as a *position snapshot* - symbol, quantity,
average price - with no dates on them, so an annualised return cannot be
derived from a holding alone. This module keeps the missing half: a dated
buy/sell ledger per symbol, fed from the Kite MCP tradebook, from which a real
XIRR falls out.

Coverage matters and is reported honestly. Zerodha's tradebook is day-scoped on
the classic Connect API, so on day one the ledger may cover only a slice of a
position that was accumulated over years. Three states come out of `xirr_for`:

  exact    - ledger quantity matches the held quantity; plain XIRR.
  partial  - ledger covers only part of it. The uncovered shares are seeded as
             an opening lot at avg_cost, dated at the earliest known trade. A
             real number, but anchored on a guessed date: always flagged.
  none     - nothing dated for this symbol. No number is invented.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import sip_simulator

# A position counts as fully covered when the ledger accounts for at least this
# share of it. Without a minimum absolute slack, rounding on fractional/bonus
# quantities would flip an otherwise complete ledger into "partial".
COVERAGE_TOLERANCE = 0.02   # 2% of held quantity
COVERAGE_MIN_SLACK = 1.0    # ...or one whole share, whichever is larger

_DATE_KEYS = ("fill_timestamp", "exchange_timestamp", "trade_date",
              "order_timestamp", "timestamp", "date")
_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                 "%d-%m-%Y", "%Y/%m/%d")


def parse_date(value) -> Optional[datetime]:
    """Best-effort parse of the assorted date shapes Kite and CSV exports use."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    s = str(value).strip()
    if not s or s.startswith("0000"):
        return None
    if s.endswith("Z"):
        s = s[:-1]
    if "+" in s[10:]:                      # strip a trailing timezone offset
        s = s[: 10 + s[10:].index("+")]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s[: len(fmt) + 4], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_kite_trade(trade: dict, to_yf_symbol) -> Optional[dict]:
    """Turn one Kite MCP tradebook entry into a stored ledger row.

    ``to_yf_symbol(tradingsymbol, exchange)`` maps into the portfolio's key
    space so the ledger and the holdings agree on what a symbol is called.
    Returns None for anything unusable (no symbol, no date, no quantity).
    """
    if not isinstance(trade, dict):
        return None
    tsym = (trade.get("tradingsymbol") or trade.get("symbol") or "").strip()
    if not tsym:
        return None

    when = None
    for key in _DATE_KEYS:
        when = parse_date(trade.get(key))
        if when:
            break
    if not when:
        return None

    qty = abs(_num(trade.get("quantity") or trade.get("filled_quantity") or trade.get("qty")))
    if qty <= 0:
        return None
    price = _num(trade.get("average_price") or trade.get("price"))
    if price <= 0:
        return None

    side = str(trade.get("transaction_type") or trade.get("type") or "BUY").strip().upper()
    side = "SELL" if side.startswith("S") else "BUY"
    exchange = (trade.get("exchange") or "NSE").strip() or "NSE"

    return {
        "symbol": to_yf_symbol(tsym, exchange),
        "tradingsymbol": tsym,
        "exchange": exchange,
        "date": when.strftime("%Y-%m-%d"),
        "executed_at": when.isoformat(timespec="seconds"),
        "type": side,
        "qty": round(qty, 4),
        "price": round(price, 4),
        "amount": round(qty * price, 2),
        "trade_id": str(trade.get("trade_id") or trade.get("order_id") or ""),
        "order_id": str(trade.get("order_id") or ""),
        "source": "kite",
    }


def _dedupe_key(row: dict) -> str:
    """Identity of a ledger row. Falls back to the economics when there is no id."""
    if row.get("trade_id"):
        return "id:" + row["trade_id"]
    return "|".join(str(row.get(k)) for k in ("symbol", "date", "type", "qty", "price"))


def merge_trades(store: Dict[str, List[dict]], rows: List[dict]) -> int:
    """Append rows into ``store`` (mutated in place), skipping duplicates.

    Returns the number of genuinely new rows. Re-syncing the same tradebook is
    a no-op, which is what makes it safe to call on every Kite sync.
    """
    added = 0
    for row in rows:
        if not row:
            continue
        bucket = store.setdefault(row["symbol"], [])
        keys = {_dedupe_key(existing) for existing in bucket}
        if _dedupe_key(row) in keys:
            continue
        bucket.append(row)
        added += 1
    for symbol in store:
        store[symbol].sort(key=lambda r: (r.get("date", ""), r.get("trade_id", "")))
    return added


def bare_symbol(symbol) -> str:
    """'TCS.NS' -> 'TCS'. An exchange suffix is a venue, not an identity."""
    s = str(symbol or "").strip().upper()
    for suffix in (".NS", ".BO"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def txns_for(store: Dict[str, List[dict]], symbol, isin: str = "") -> List[dict]:
    """Every dated row for one underlying, whatever suffix it is filed under.

    The ledger is keyed by the portfolio's symbol as it stood when the
    tradebook was imported, but a Kite portfolio sync rewrites a holding's
    suffix from the exchange of its latest fill. So a ledger bucket named
    ``TCS.NS`` and a holding named ``TCS.BO`` are routine, and they are the
    same company. An exact-key lookup left most holdings with no XIRR at all
    — including simple single-buy positions, which is what "XIRR does not
    show" meant.

    Buckets are merged rather than picked: a position accumulated across both
    exchanges (some shares on BSE, some on NSE) is one position, and
    its XIRR needs every flow. ISIN is checked first because it is
    exchange-independent; the bare symbol is the fallback for older rows
    imported before ISIN was recorded.
    """
    if not store:
        return []
    want_bare = bare_symbol(symbol)
    want_isin = str(isin or "").strip().upper()
    rows: List[dict] = []
    for key, bucket in store.items():
        if not bucket:
            continue
        if want_isin and any(
            str(r.get("isin") or "").strip().upper() == want_isin for r in bucket
        ):
            rows.extend(bucket)
            continue
        if want_bare and bare_symbol(key) == want_bare:
            rows.extend(bucket)
    # One row can only be reached through one bucket, but a caller may pass a
    # symbol whose ISIN and bare name resolve to different buckets, so dedupe.
    seen, unique = set(), []
    for row in rows:
        key = _dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    unique.sort(key=lambda r: (str(r.get("date") or ""), str(r.get("trade_id") or "")))
    return unique


def net_qty(txns: List[dict]) -> float:
    """Shares the ledger accounts for: buys minus sells."""
    return sum(_num(t.get("qty")) * (-1 if t.get("type") == "SELL" else 1)
               for t in (txns or []))


def cashflows(txns: List[dict]) -> List[Tuple[datetime, float]]:
    """Dated cashflows for XIRR: buys are outflows, sells are inflows."""
    flows = []
    for t in txns or []:
        when = parse_date(t.get("date"))
        if not when:
            continue
        amount = _num(t.get("amount")) or _num(t.get("qty")) * _num(t.get("price"))
        if amount <= 0:
            continue
        flows.append((when, amount if t.get("type") == "SELL" else -amount))
    flows.sort(key=lambda f: f[0])
    return flows


def _bought_recently(txns: List[dict], as_of: datetime = None,
                     days: int = 3) -> float:
    """Quantity bought within the last [days], newest trades first.

    Used to tell an unsettled purchase from a missing sale. Equity settles on
    T+1, so a buy can legitimately sit in the tradebook while the holdings
    snapshot still predates it; three days covers a Friday buy read on Monday.
    """
    now = as_of or datetime.now()
    total = 0.0
    for txn in txns or []:
        if str(txn.get("type") or "").upper() == "SELL":
            continue
        when = parse_date(txn.get("date"))
        if when and 0 <= (now - when).days <= days:
            total += _num(txn.get("qty"))
    return total


def is_covered(ledger_qty: float, held_qty: float) -> bool:
    """Does the ledger account for the whole position, within tolerance?"""
    slack = max(held_qty * COVERAGE_TOLERANCE, COVERAGE_MIN_SLACK)
    return abs(ledger_qty - held_qty) <= slack


def xirr_for(txns: List[dict], current_value: float, held_qty: float,
             avg_cost: float = 0.0, as_of: datetime = None) -> dict:
    """Annualised return for one position.

    Returns ``{xirr, basis, exact, covered_qty, held_qty}``. ``xirr`` is None
    whenever no honest number exists; ``exact`` is False when the uncovered
    part of the position had to be seeded at ``avg_cost``.
    """
    blank = {"xirr": None, "basis": "none", "exact": False,
             "covered_qty": 0.0, "held_qty": round(held_qty, 4)}
    if not txns or current_value <= 0 or held_qty <= 0:
        return blank

    flows = cashflows(txns)
    if not flows:
        return blank

    ledger_qty = net_qty(txns)
    covered = is_covered(ledger_qty, held_qty)
    basis_when_partial = "partial"
    if not covered:
        missing = held_qty - ledger_qty
        if missing > 0 and avg_cost > 0:
            # Seed the unexplained shares as an opening lot on the earliest
            # known trade date. The rate is real, the anchor date is a guess.
            flows.insert(0, (flows[0][0], -missing * avg_cost))
        elif missing < 0:
            # The ledger holds MORE than the broker snapshot. The usual cause
            # is settlement, not a bookkeeping error: a buy made today is in
            # the tradebook immediately but only reaches the holdings snapshot
            # on T+1. Treating that as unexplainable dropped the XIRR of any
            # stock bought that morning (e.g. 43 in the ledger, 40 held, 3
            # bought today) — it simply went blank.
            #
            # The per-share price is known, so the ledger's own position can be
            # valued at it. That is an assumption — those shares are presumed
            # still held — so it is never reported as exact.
            excess = -missing
            current_value = current_value * ledger_qty / held_qty
            basis_when_partial = (
                "unsettled" if _bought_recently(txns, as_of) >= excess - 1e-9
                else "partial")
        else:
            # Uncovered with nothing to value it by: no cost to seed the gap
            # and no quantity to scale. No number is invented.
            return {**blank, "basis": "partial", "covered_qty": round(ledger_qty, 4)}

    flows.append((as_of or datetime.now(), current_value))
    if len(flows) < 2:
        return blank

    # XIRR is undefined over a zero-length period: every flow discounts by
    # the same factor, so no rate solves it. A buy made today used to fall
    # through the solver and come back as -99.99% (Newton hitting the domain
    # edge) or as "unsolved", both of which read as a broken number rather
    # than as "there is no annual rate for a position held for zero days".
    span_days = (max(f[0] for f in flows) - min(f[0] for f in flows)).days
    if span_days < 1:
        return {**blank, "basis": "same_day",
                "covered_qty": round(ledger_qty, 4)}

    try:
        rate = sip_simulator._xirr(flows)
    except Exception:
        return blank
    if not rate:
        # _xirr returns 0.0 on non-convergence, indistinguishable from a real
        # 0%. Only call it unsolved when the position clearly did move.
        invested = sum(-a for _, a in flows if a < 0)
        if invested > 0 and abs(current_value - invested) / invested > 0.005:
            return {**blank, "basis": "unsolved", "covered_qty": round(ledger_qty, 4)}

    return {
        "xirr": round(rate, 2),
        "basis": "exact" if covered else basis_when_partial,
        "exact": covered,
        "covered_qty": round(ledger_qty, 4),
        "held_qty": round(held_qty, 4),
    }


def portfolio_xirr(store: Dict[str, List[dict]], holdings: List[dict],
                   as_of: datetime = None) -> dict:
    """Book-level XIRR across every holding the ledger covers exactly.

    Only exactly-covered holdings contribute - mixing in seeded opening lots
    would let one badly-anchored position distort the whole book. The result
    reports how much of the book's value the number actually speaks for.
    """
    flows: List[Tuple[datetime, float]] = []
    covered_value = 0.0
    total_value = 0.0
    covered_symbols = []

    for h in holdings:
        value = _num(h.get("total_value"))
        total_value += value
        txns = txns_for(store, h.get("symbol"), h.get("isin") or "")
        if not txns or value <= 0:
            continue
        if not is_covered(net_qty(txns), _num(h.get("shares"))):
            continue
        flows.extend(cashflows(txns))
        covered_value += value
        covered_symbols.append(h.get("symbol"))

    if not flows or covered_value <= 0:
        return {"xirr": None, "covered_value": 0.0,
                "total_value": round(total_value, 2),
                "covered_pct": 0.0, "covered_symbols": []}

    flows.sort(key=lambda f: f[0])
    flows.append((as_of or datetime.now(), covered_value))
    if (flows[-1][0] - flows[0][0]).days < 1:
        return {"xirr": None, "covered_value": round(covered_value, 2),
                "total_value": round(total_value, 2),
                "covered_pct": round(covered_value / total_value * 100, 2)
                if total_value > 0 else 0.0,
                "covered_symbols": covered_symbols}
    try:
        rate = sip_simulator._xirr(flows)
    except Exception:
        rate = None

    return {
        # `if rate else None` would erase a genuine flat book: _xirr returns
        # 0.0 both for "no movement" and for non-convergence, and only the
        # second one is missing data.
        "xirr": round(rate, 2) if rate is not None else None,
        "covered_value": round(covered_value, 2),
        "total_value": round(total_value, 2),
        "covered_pct": round(covered_value / total_value * 100, 2) if total_value > 0 else 0.0,
        "covered_symbols": covered_symbols,
    }
