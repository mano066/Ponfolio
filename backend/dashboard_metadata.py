"""Pure provenance helpers; never substitute a retrieval time for a market date."""
from datetime import datetime, timezone
import math


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def freshness(stamps, max_age=900):
    stamps = list(stamps)
    if not stamps or any(not s for s in stamps):
        return {"last_updated": None, "stale": True}
    try:
        dates = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps]
        dates = [d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d for d in dates]
        oldest = min(dates)
        age = (datetime.now(timezone.utc) - oldest).total_seconds()
        return {"last_updated": oldest.isoformat(timespec="seconds"),
                "stale": not 0 <= age <= max_age}
    except (ValueError, TypeError):
        return {"last_updated": None, "stale": True}


def monthly_buys(rows, now=None):
    """Gross purchases in the recorded ledger, not all-time cost or net transfers."""
    now = now or datetime.now(timezone.utc)
    total = 0.0
    for row in rows:
        date = str(row.get("date") or "")[:10]
        try:
            parsed = datetime.strptime(date, "%Y-%m-%d").date()
            if parsed.year != now.year or parsed.month != now.month or parsed > now.date():
                continue
            if row.get("type") == "SELL":
                continue
            amount = float(row.get("invested") or row.get("amount") or 0)
            if math.isfinite(amount) and amount > 0:
                total += amount
        except (ValueError, TypeError):
            continue
    return round(total, 2)
