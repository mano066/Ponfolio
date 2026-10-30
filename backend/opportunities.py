"""
Today's Opportunities — the dashboard's master decision widget.

Pure computation.  ``main.py`` supplies the already-built fund rows, stock rows
and index tape; this picks the handful that deserve attention today and states
the market in one line.

Design notes
------------
* **"Nothing today" is a first-class answer.**  A dashboard that manufactures a
  BUY every morning trains its reader to ignore it, and the measured backtest
  in this app says most days genuinely offer nothing: shallow dips carried a
  NEGATIVE edge over simply buying on a random day.  :data:`STATUS_QUIET` is
  therefore a normal outcome, not an error state, and it says so plainly rather
  than surfacing the least-bad row as though it were a recommendation.

* **The bar shows at most a handful of rows.**  Its whole job is to be readable
  in five seconds. Ranking everything and truncating would put the fourth-best
  fund on screen on a day when nothing qualifies; instead each slot has an
  admission test, and an empty slot stays empty.

* **A risk row is never crowded out by opportunities.**  If a holding must not
  be averaged into, that is the most consequential thing on the screen and it
  is admitted regardless of how many buys are competing for space.

* **A buy or watch row must have a price.**  Fundamentals alone clear the
  scoring bar, so a holding whose quote never downloaded can arrive here with
  a high score and no way to act on it — a live example scored 85.6 on balance
  sheet and growth while showing "no price" and "no bench" on the card below.
  A risk row is exempt: deterioration is a fact about the business, and a
  warning stays worth showing even when the feed is down.

* Every row carries its own ``why`` line.  A score with no argument behind it
  is not something a person should act on, and the whole point of the bar is
  that it is acted on quickly.
"""

from __future__ import annotations

from typing import Sequence

# ── Market signal ─────────────────────────────────────────────────────────
MARKET_OPPORTUNITY = "opportunity"
MARKET_NORMAL = "normal"
MARKET_CORRECTION = "correction"
MARKET_HIGH_RISK = "high_risk"
MARKET_UNKNOWN = "unknown"

MARKET_LABELS = {
    MARKET_OPPORTUNITY: "Opportunity",
    MARKET_NORMAL: "Normal",
    MARKET_CORRECTION: "Correction",
    MARKET_HIGH_RISK: "High risk",
    MARKET_UNKNOWN: "Not available",
}

# Emoji follow the tape's convention: red is RISK, green is a correction worth
# buying. See market_indices.MARKET_STATUS_EMOJI for why the palette runs the
# opposite way to a P&L one.
MARKET_EMOJI = {
    MARKET_OPPORTUNITY: "\U0001f7e2",
    MARKET_NORMAL: "\U0001f7e1",
    MARKET_CORRECTION: "\U0001f7e0",
    MARKET_HIGH_RISK: "\U0001f534",
    MARKET_UNKNOWN: "—",
}

# ── Board status ──────────────────────────────────────────────────────────
STATUS_ACTIONABLE = "actionable"
STATUS_QUIET = "quiet"

QUIET_HEADLINE = "No strong dip today"
QUIET_DETAIL = ("Nothing currently meets the strategy threshold. "
                "Keep the plan running and wait.")

# ── Admission tests ───────────────────────────────────────────────────────
# A row earns its place or the slot stays empty.
MIN_SCORE_FOR_BUY = 65.0
MIN_SCORE_FOR_WATCH = 50.0
MAX_BUY_ROWS = 3
MAX_WATCH_ROWS = 1
MAX_RISK_ROWS = 1

KIND_FUND = "fund"
KIND_STOCK = "stock"

ROW_BUY = "buy"
ROW_ADD = "add"
ROW_WATCH = "watch"
ROW_AVOID = "avoid"

ROW_LABELS = {
    ROW_BUY: "BUY",
    ROW_ADD: "ADD",
    ROW_WATCH: "WATCH",
    ROW_AVOID: "AVOID",
}

ROW_EMOJI = {
    ROW_BUY: "\U0001f7e2",
    ROW_ADD: "\U0001f7e2",
    ROW_WATCH: "\U0001f7e1",
    ROW_AVOID: "\U0001f534",
}


def _num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


# ══════════════════════════════════════════════════════════════════════════
#  MARKET SIGNAL
# ══════════════════════════════════════════════════════════════════════════

def market_signal(tape: dict | None) -> dict:
    """
    One word and one sentence on the market, from the broad and size indices.

    Deliberately reads the SPREAD between large caps and small/mid rather than
    a single number.  The two halves of this market routinely disagree — as
    they do today, with large caps ~9% off their highs while smallcaps sit at
    theirs — and a single average would hide exactly the fact a dip dashboard
    needs to surface.
    """
    rows = [r for r in (tape or {}).get("indices", [])
            if isinstance(r, dict) and r.get("status") == "ok"]
    by_symbol = {r.get("symbol"): r for r in rows}

    def off(symbol):
        row = by_symbol.get(symbol)
        return _num(row.get("off_high_pct")) if row else None

    broad = off("^NSEI")
    small = off("NIFTYSMLCAP250.NS")
    mid = off("NIFTYMIDCAP150.NS")

    if broad is None and small is None and mid is None:
        return {"signal": MARKET_UNKNOWN,
                "label": MARKET_LABELS[MARKET_UNKNOWN],
                "emoji": MARKET_EMOJI[MARKET_UNKNOWN],
                "summary": "Market levels are not available right now.",
                "broad_off_high_pct": None,
                "smallcap_off_high_pct": small,
                "midcap_off_high_pct": mid}

    known = [v for v in (broad, small, mid) if v is not None]
    deepest = max(known)

    if deepest >= 25:
        signal = MARKET_HIGH_RISK
    elif deepest >= 12:
        signal = MARKET_OPPORTUNITY
    elif deepest >= 6:
        signal = MARKET_CORRECTION
    else:
        signal = MARKET_NORMAL

    summary = _market_sentence(broad, small, mid)
    return {
        "signal": signal,
        "label": MARKET_LABELS[signal],
        "emoji": MARKET_EMOJI[signal],
        "summary": summary,
        "broad_off_high_pct": broad,
        "smallcap_off_high_pct": small,
        "midcap_off_high_pct": mid,
    }


def _market_sentence(broad, small, mid) -> str:
    """One sentence, and never more than one."""
    parts = []
    if broad is not None:
        parts.append("Large caps {0}".format(_phrase(broad)))
    smaller = [v for v in (small, mid) if v is not None]
    if smaller:
        worst = max(smaller)
        which = "Smallcaps" if (small is not None and small >= (mid or -1)) \
            else "Midcaps"
        parts.append("{0} {1}".format(which.lower(), _phrase(worst)))
    if not parts:
        return "Market levels are not available right now."
    return " while ".join(parts) + "."


def _phrase(off_high: float) -> str:
    if off_high <= 2:
        return "are at their highs"
    if off_high < 6:
        return "are near their highs"
    if off_high < 12:
        return "are {0:.0f}% off their highs".format(off_high)
    return "are {0:.0f}% into a correction".format(off_high)


# ══════════════════════════════════════════════════════════════════════════
#  ROWS
# ══════════════════════════════════════════════════════════════════════════

def _fund_row(fund: dict) -> dict:
    score = _num(fund.get("score"))
    dd = _num(fund.get("benchmark_drawdown_pct"))
    return {
        "kind": KIND_FUND,
        "key": fund.get("scheme_name"),
        "name": fund.get("scheme_name"),
        "subtitle": fund.get("category") or "",
        "score": score,
        "action": ROW_ADD,
        "price": _num(fund.get("nav")),
        "price_label": "NAV",
        "metric": ("{0:.1f}% off high".format(dd) if dd is not None else None),
        "why": (fund.get("reasons") or [None])[0],
        "low_confidence": fund.get("low_confidence", False),
    }


def _stock_row(stock: dict, action: str) -> dict:
    score = _num(stock.get("score"))
    dd = _num(stock.get("drawdown_pct"))
    return {
        "kind": KIND_STOCK,
        "key": stock.get("symbol"),
        "name": stock.get("name") or stock.get("symbol"),
        "subtitle": stock.get("benchmark_label") or "",
        "score": score,
        "action": action,
        "price": _num(stock.get("price")),
        "price_label": "Price",
        "metric": ("{0:.1f}% off high".format(dd) if dd is not None else None),
        "why": (stock.get("reasons") or [None])[0],
        "low_confidence": stock.get("low_confidence", False),
    }


def _sort_key(row: dict):
    # Unknown scores sort last; they were never candidates for a buy slot.
    return -(row.get("score") if row.get("score") is not None else -1)


def build_board(funds: Sequence[dict] = (), stocks: Sequence[dict] = (),
                tape: dict | None = None) -> dict:
    """
    Assemble the master bar.

    Each slot applies its own admission test, so a quiet day produces a short
    board or an empty one rather than the least-bad row dressed up as advice.
    """
    funds = list(funds or [])
    stocks = list(stocks or [])

    # ── Risk first: the most consequential row on the screen ──────────────
    risk_rows = [
        _stock_row(s, ROW_AVOID) for s in stocks if s.get("averaging_blocked")
    ]
    risk_rows.sort(key=lambda r: -(r["score"] or 0))
    risk_rows = risk_rows[:MAX_RISK_ROWS]

    # ── Buys and adds ────────────────────────────────────────────────────
    buyable_funds = [
        _fund_row(f) for f in funds
        if (_num(f.get("score")) or 0) >= MIN_SCORE_FOR_BUY
        and not f.get("low_confidence")
        and _num(f.get("nav")) is not None
    ]
    buyable_stocks = [
        _stock_row(s, ROW_BUY) for s in stocks
        if (_num(s.get("score")) or 0) >= MIN_SCORE_FOR_BUY
        and s.get("action") in ("accumulate", "consider")
        and not s.get("averaging_blocked")
        and _num(s.get("price")) is not None
    ]
    buys = sorted(buyable_funds + buyable_stocks, key=_sort_key)[:MAX_BUY_ROWS]

    # ── One watch item, excluding anything already shown ─────────────────
    shown = {(r["kind"], r["key"]) for r in buys + risk_rows}

    def watch_candidates():
        for f in funds:
            score = _num(f.get("score"))
            if score is None or score < MIN_SCORE_FOR_WATCH:
                continue
            if _num(f.get("nav")) is None:
                continue
            row = _fund_row(f)
            row["action"] = ROW_WATCH
            if (row["kind"], row["key"]) not in shown:
                yield row
        for s in stocks:
            score = _num(s.get("score"))
            if score is None or score < MIN_SCORE_FOR_WATCH:
                continue
            if s.get("averaging_blocked"):
                continue
            if _num(s.get("price")) is None:
                continue
            row = _stock_row(s, ROW_WATCH)
            if (row["kind"], row["key"]) not in shown:
                yield row

    watches = sorted(watch_candidates(), key=_sort_key)[:MAX_WATCH_ROWS]

    rows = buys + watches + risk_rows
    for row in rows:
        row["label"] = ROW_LABELS[row["action"]]
        row["emoji"] = ROW_EMOJI[row["action"]]

    status = STATUS_ACTIONABLE if buys else STATUS_QUIET
    return {
        "status": status,
        "headline": None if buys else QUIET_HEADLINE,
        "detail": None if buys else QUIET_DETAIL,
        "market": market_signal(tape),
        "rows": rows,
        "buy_count": len(buys),
        "risk_count": len(risk_rows),
    }
