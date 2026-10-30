"""One ledger page per trade date, replayed from the tradebook.

The rebalance screen answers "what should I do now". This answers the other
half of the same question — "what did I actually do, and what did it do to the
weights" — in the same table shape, one page per date you traded.

Two things make the replay trustworthy rather than decorative:

  * It runs FORWARD from a computed opening position, where opening = what is
    held today minus everything the tradebook moved. The final page therefore
    reconciles to the live portfolio by construction, instead of hoping that a
    replay from zero lands on it.
  * Symbols are matched on their base, not their full ticker. The same holding
    appears as IOC.NS in a Console tradebook and IOC.BO in a Kite holding, and
    matching the full string silently drops the history of every such name.

Prices come in as closing series; this module never fetches. That keeps the
replay pure and lets the tests state a price history in four lines instead of
standing up a network.
"""
from bisect import bisect_left
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# One definition, shared with the planner. If the two modules disagreed about
# what counts as the same company, a page could show a holding whose ledger
# the plan cannot find.
from rebalance_engine import base_symbol

# A holding that cannot be priced on a page is still HELD — it just cannot be
# weighed. Dropping it would silently change the denominator every other
# holding's weight is measured against, so it stays in the table with an empty
# weight instead.
UNPRICED = None


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


class Closes:
    """Closing prices per symbol, answering "as of" rather than "on"."""

    def __init__(self, series: Dict[str, Iterable[Tuple[Any, float]]]):
        self._days: Dict[str, List[date]] = {}
        self._px: Dict[str, List[float]] = {}
        for symbol, rows in (series or {}).items():
            clean = sorted(
                (d, float(p)) for d, p in
                ((_as_date(d), p) for d, p in rows)
                if d is not None and p is not None and float(p) > 0)
            key = base_symbol(symbol)
            self._days[key] = [d for d, _ in clean]
            self._px[key] = [p for _, p in clean]

    def on_or_before(self, symbol: str, day: date) -> Optional[float]:
        """The last close at or before `day` — a holiday is not a price gap."""
        key = base_symbol(symbol)
        days = self._days.get(key)
        if not days:
            return UNPRICED
        i = bisect_left(days, day)
        if i < len(days) and days[i] == day:
            return self._px[key][i]
        return self._px[key][i - 1] if i > 0 else UNPRICED

    def before(self, symbol: str, day: date) -> Optional[float]:
        """The previous session's close, which is what a page opens on."""
        key = base_symbol(symbol)
        days = self._days.get(key)
        if not days:
            return UNPRICED
        i = bisect_left(days, day)
        return self._px[key][i - 1] if i > 0 else UNPRICED


def opening_positions(holdings: Sequence[Dict[str, Any]],
                      trades: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """What was held before the first trade in the book.

    Today's quantity is the one number that is certainly true, so the replay
    is anchored there and wound backwards through the tradebook. A name the
    book never mentions was simply held the whole way through.
    """
    qty = {base_symbol(h.get("symbol")): float(h.get("shares") or 0)
           for h in holdings or []}
    for t in trades or []:
        key = base_symbol(t.get("symbol"))
        moved = float(t.get("qty") or 0)
        if str(t.get("type", "")).upper() == "BUY":
            qty[key] = qty.get(key, 0.0) - moved
        else:
            qty[key] = qty.get(key, 0.0) + moved
    return qty


def flatten(txns_by_symbol: Dict[str, List[Dict[str, Any]]]
            ) -> List[Dict[str, Any]]:
    """The per-symbol ledger as one date-ordered stream."""
    out = []
    for symbol, rows in (txns_by_symbol or {}).items():
        for row in rows or []:
            when = _as_date(row.get("date"))
            if when is None or not float(row.get("qty") or 0):
                continue
            out.append({"symbol": symbol, "date": when,
                        "type": str(row.get("type", "")).upper(),
                        "qty": float(row["qty"]),
                        "price": float(row.get("price") or 0),
                        "name": row.get("tradingsymbol") or base_symbol(symbol)})
    out.sort(key=lambda r: (r["date"], r["symbol"]))
    return out


def build_pages(holdings: Sequence[Dict[str, Any]],
                txns_by_symbol: Dict[str, List[Dict[str, Any]]],
                closes: Closes,
                names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """One page per date the book was traded, oldest first."""
    trades = flatten(txns_by_symbol)
    if not trades:
        return {"pages": [], "count": 0, "reconciles": True, "unmatched": []}

    label = dict(names or {})
    for t in trades:
        label.setdefault(base_symbol(t["symbol"]), t["name"])
    for h in holdings or []:
        label[base_symbol(h.get("symbol"))] = (
            h.get("name") or base_symbol(h.get("symbol")))

    qty = opening_positions(holdings, trades)
    # A name the tradebook sells more of than the portfolio ever held cannot be
    # replayed; say so rather than printing a negative opening balance.
    unmatched = sorted(k for k, v in qty.items() if v < -1e-6)

    by_day: Dict[date, List[Dict[str, Any]]] = {}
    for t in trades:
        by_day.setdefault(t["date"], []).append(t)
    days = sorted(by_day)

    pages = []
    for index, day in enumerate(days, 1):
        # Fills are netted per symbol per day: three buys of the same name on
        # one date is one line in a ledger, at the average price paid.
        moved: Dict[str, Dict[str, float]] = {}
        for t in by_day[day]:
            key = base_symbol(t["symbol"])
            m = moved.setdefault(key, {"bought": 0.0, "sold": 0.0, "cash": 0.0})
            if t["type"] == "BUY":
                m["bought"] += t["qty"]
                m["cash"] -= t["qty"] * t["price"]
            else:
                m["sold"] += t["qty"]
                m["cash"] += t["qty"] * t["price"]

        live = [k for k, v in qty.items() if v > 1e-9 or k in moved]
        before_px = {k: closes.before(k, day) for k in live}
        after_px = {k: closes.on_or_before(k, day) for k in live}

        rows = []
        total_before = 0.0
        total_after = 0.0
        for key in live:
            held_before = qty.get(key, 0.0)
            m = moved.get(key, {"bought": 0.0, "sold": 0.0, "cash": 0.0})
            held_after = held_before + m["bought"] - m["sold"]
            # Carry the close of this page into the open of the next one. A
            # replay that forgets to do this shows every page opening from the
            # same position and still looks plausible page by page.
            qty[key] = held_after
            traded = m["bought"] + m["sold"]
            # The fill the ledger recorded, which is the price this page is
            # written at. A row that did not trade has no fill.
            fill = (abs(m["cash"]) / traded) if traded else UNPRICED
            bpx, apx = before_px.get(key), after_px.get(key)
            value_before = held_before * bpx if bpx is not None else UNPRICED
            value_after = held_after * apx if apx is not None else UNPRICED
            total_before += value_before or 0.0
            total_after += value_after or 0.0
            rows.append({
                "key": key,
                "name": label.get(key, key),
                "held_before": round(held_before, 4),
                "fill": round(fill, 2) if fill is not None else None,
                "value_before": (round(value_before, 2)
                                 if value_before is not None else None),
                "action": ("BUY" if m["bought"] and not m["sold"] else
                           "SELL" if m["sold"] and not m["bought"] else
                           "BOTH" if m["bought"] else "HOLD"),
                "bought": round(m["bought"], 4),
                "sold": round(m["sold"], 4),
                "sold_pct_of_held": (round(m["sold"] / held_before * 100.0, 2)
                                     if held_before > 0 else 0.0),
                "held_after": round(held_after, 4),
                "value_after": (round(value_after, 2)
                                if value_after is not None else None),
                "net_cash": round(m["cash"], 2),
            })

        for row in rows:
            row["weight_before_pct"] = (
                round(row["value_before"] / total_before * 100.0, 2)
                if total_before > 0 and row["value_before"] is not None else None)
            row["weight_after_pct"] = (
                round(row["value_after"] / total_after * 100.0, 2)
                if total_after > 0 and row["value_after"] is not None else None)

        rows.sort(key=lambda r: -(r["value_before"] or 0.0))
        pages.append({
            "index": index,
            "date": day.isoformat(),
            "rows": rows,
            "totals": {
                "value_before": round(total_before, 2),
                "value_after": round(total_after, 2),
                "bought": round(sum(r["bought"] for r in rows), 4),
                "sold": round(sum(r["sold"] for r in rows), 4),
                "net_cash": round(sum(r["net_cash"] for r in rows), 2),
                "positions": len(rows),
                "traded": sum(1 for r in rows if r["action"] != "HOLD"),
                # Rows with no PRICE, which is a data gap. A null weight is a
                # weaker claim — on the first page nothing is weighable because
                # nothing priced was held yet, and counting those as unpriced
                # reports a gap that is not there.
                "unpriced": sum(1 for r in rows if r["value_before"] is None),
                "unpriced_keys": sorted(r["key"] for r in rows
                                        if r["value_before"] is None),
            },
        })

    # The closing replay must land on the live portfolio, or every weight on
    # every page is measured against a book that was never held.
    final = {r["key"]: r["held_after"] for r in pages[-1]["rows"]}
    drift = []
    for h in holdings or []:
        key = base_symbol(h.get("symbol"))
        want = float(h.get("shares") or 0)
        if abs(final.get(key, 0.0) - want) > 1e-6:
            drift.append({"key": key, "replayed": final.get(key, 0.0),
                          "held": want})

    for page in pages:
        page["count"] = len(pages)
    return {"pages": pages, "count": len(pages), "reconciles": not drift,
            "drift": drift, "unmatched": unmatched}
