"""
Conviction & position-size discipline — pure computation layer.

The dip panels answer "has this fallen?". This module answers the questions
that should come BEFORE that one, taken from two lessons that kept recurring
in the user's own trading:

  1. **Never decide on the share price or on your own average cost.** What
     moves a share over time is how fast the business grows its earnings, and
     how the market feels about it. So the app scores the BUSINESS (growth,
     quality, safety, price-versus-growth) separately from the price fall, and
     never offers "below your average" as a reason to buy.
  2. **Borrowed conviction is the costliest mistake.** A stock bought because
     someone mentioned it gets sold too early when it wins and averaged down
     when it loses. So every holding carries a written thesis — what the
     company does, why earnings can grow, what business event would make you
     sell — and adding more is gated on that thesis being met by the latest
     quarterly result, never on the price having fallen.

Everything here is deterministic and network-free. ``main.py`` supplies the
fundamentals (yfinance, cached daily), the holdings and their values, and the
user's saved ``conviction.json``; this module turns them into one row per
holding and per watchlist name.

Design notes
------------
* **Unknown is never zero.** A ratio that did not download is reported as
  unknown and drops out of the health score, which then carries a coverage
  figure — the same rule the dip modules follow.
* **Banks are judged as banks.** Debt-to-equity and current ratio describe a
  bank's deposits, not its risk, so they are not scored for lenders.
* **Quarterly snapshots, not daily ticks.** yfinance only ever reports the
  LATEST growth figure, so the trend lessons ("sales falling three quarters
  running") need history the feed does not keep. One snapshot per calendar
  quarter is stored and updated in place during that quarter; comparing
  quarters is then possible after the first results season.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence

# ══════════════════════════════════════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════════════════════════════════════

DEFAULT_SETTINGS = {
    # Position-size bands, as % of the equity portfolio's market value.
    "exit_or_grow_below_pct": 1.0,   # under this: exit it or grow it
    "min_position_pct": 2.0,         # a "real" position starts here
    "initial_position_pct": 1.0,     # first buy after the checklist passes
    "max_position_pct": 10.0,        # never more than this in one stock
    # A new name waits on the watchlist this long before it may be bought —
    # roughly one quarterly results season.
    "watch_min_days": 45,
    # A thesis older than this must be re-answered.
    "thesis_max_age_days": 365,
    # Consecutive missed quarters before the app suggests reducing.
    "misses_before_reduce": 2,
    # Business health below this blocks adding.
    "min_health_to_add": 50.0,
}


def merge_settings(saved: dict | None) -> dict:
    """Defaults overlaid with whatever valid numbers the user saved."""
    out = dict(DEFAULT_SETTINGS)
    for key, default in DEFAULT_SETTINGS.items():
        value = _num((saved or {}).get(key))
        if value is not None and value >= 0:
            out[key] = type(default)(value)
    return out


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def bare_symbol(symbol: str) -> str:
    """'ITC.NS' -> 'ITC'. Conviction data is keyed exchange-free."""
    return re.sub(r"\.(NS|BO)$", "", (symbol or "").strip().upper())


# ══════════════════════════════════════════════════════════════════════════
#  BUSINESS HEALTH
# ══════════════════════════════════════════════════════════════════════════
# Each check returns good / warn / bad / unknown and a 0-100 sub-score.
# Thresholds are starting points for Indian equities, not laws; they are named
# constants so a change is one edit and a test.

STATUS_GOOD = "good"
STATUS_WARN = "warn"
STATUS_BAD = "bad"
STATUS_UNKNOWN = "unknown"

EPS_GROWTH_GOOD = 12.0
EPS_GROWTH_BAD = 0.0
SALES_GROWTH_GOOD = 10.0
SALES_GROWTH_BAD = 0.0
ROE_GOOD = 15.0
ROE_BAD = 10.0
OPM_GOOD = 15.0
OPM_BAD = 5.0
DE_GOOD = 100.0       # yfinance reports debt/equity as a percentage: 1.0x
DE_BAD = 200.0        # 2.0x
CURRENT_RATIO_GOOD = 1.2
CURRENT_RATIO_BAD = 1.0
PEG_GOOD = 1.5
PEG_BAD = 2.5

GROUP_GROWTH = "growth"
GROUP_QUALITY = "quality"
GROUP_SAFETY = "safety"
GROUP_VALUE = "value"

GROUP_WEIGHTS = {
    GROUP_GROWTH: 0.35,
    GROUP_QUALITY: 0.30,
    GROUP_SAFETY: 0.15,
    GROUP_VALUE: 0.20,
}

GROUP_LABELS = {
    GROUP_GROWTH: "Growth",
    GROUP_QUALITY: "Quality",
    GROUP_SAFETY: "Safety",
    GROUP_VALUE: "Price vs growth",
}

# Below this share of the total weight, the score is reported but flagged.
HEALTH_MIN_COVERAGE = 50.0

GRADE_STRONG = "strong"
GRADE_GOOD = "good"
GRADE_WEAK = "weak"
GRADE_POOR = "poor"
GRADE_UNKNOWN = "unknown"

GRADE_LABELS = {
    GRADE_STRONG: "Strong",
    GRADE_GOOD: "Good",
    GRADE_WEAK: "Weak",
    GRADE_POOR: "Poor",
    GRADE_UNKNOWN: "Not enough data",
}

_BANK_WORDS = ("bank", "financial services", "credit services", "nbfc",
               "capital markets", "insurance")


def is_financial(sector: str = "", industry: str = "", name: str = "") -> bool:
    """Lenders and insurers, whose leverage ratios mean something else."""
    text = f"{sector} {industry} {name}".lower()
    return any(w in text for w in _BANK_WORDS)


def _ramp_up(value, bad, good) -> float:
    """0 at `bad`, 100 at `good`, linear between, clamped."""
    if good == bad:
        return 100.0 if value >= good else 0.0
    return round(max(0.0, min(1.0, (value - bad) / (good - bad))) * 100.0, 1)


def _ramp_down(value, good, bad) -> float:
    """100 at `good`, 0 at `bad`, for metrics where lower is better."""
    if good == bad:
        return 100.0 if value <= good else 0.0
    return round(max(0.0, min(1.0, (bad - value) / (bad - good))) * 100.0, 1)


def _status(score: float | None) -> str:
    if score is None:
        return STATUS_UNKNOWN
    if score >= 70:
        return STATUS_GOOD
    if score >= 35:
        return STATUS_WARN
    return STATUS_BAD


def peg_ratio(pe, eps_growth_pct) -> float | None:
    """P/E divided by EPS growth. Undefined when growth is not positive."""
    pe, g = _num(pe), _num(eps_growth_pct)
    if pe is None or g is None or pe <= 0 or g <= 0:
        return None
    return round(pe / g, 2)


def health_checks(f: dict | None, *, financial: bool = False) -> list[dict]:
    """The individual checks behind the health score, in display order."""
    f = f or {}
    eps_g = _num(f.get("earnings_growth_pct"))
    sales_g = _num(f.get("revenue_growth_pct"))
    roe = _num(f.get("roe_pct"))
    opm = _num(f.get("operating_margin_pct"))
    fcf = _num(f.get("free_cashflow"))
    de = _num(f.get("debt_to_equity"))
    cr = _num(f.get("current_ratio"))
    pe = _num(f.get("pe"))
    peg = peg_ratio(pe, eps_g)

    def check(key, label, group, value, score, rule, unit="%"):
        return {"key": key, "label": label, "group": group,
                "value": round(value, 2) if value is not None else None,
                "unit": unit, "score": score, "status": _status(score),
                "rule": rule}

    out = [
        check("eps_growth", "Profit (EPS) growth", GROUP_GROWTH, eps_g,
              None if eps_g is None else _ramp_up(eps_g, EPS_GROWTH_BAD, EPS_GROWTH_GOOD),
              f"Good above {EPS_GROWTH_GOOD:.0f}%, bad below {EPS_GROWTH_BAD:.0f}%"),
        check("sales_growth", "Sales growth", GROUP_GROWTH, sales_g,
              None if sales_g is None else _ramp_up(sales_g, SALES_GROWTH_BAD, SALES_GROWTH_GOOD),
              f"Good above {SALES_GROWTH_GOOD:.0f}%, bad below {SALES_GROWTH_BAD:.0f}%"),
        check("roe", "Return on equity", GROUP_QUALITY, roe,
              None if roe is None else _ramp_up(roe, ROE_BAD, ROE_GOOD),
              f"Good above {ROE_GOOD:.0f}%, bad below {ROE_BAD:.0f}%"),
    ]
    if not financial:
        out.append(check(
            "operating_margin", "Operating margin", GROUP_QUALITY, opm,
            None if opm is None else _ramp_up(opm, OPM_BAD, OPM_GOOD),
            f"Good above {OPM_GOOD:.0f}%, bad below {OPM_BAD:.0f}%"))
        out.append(check(
            "free_cashflow", "Free cash flow", GROUP_QUALITY,
            None if fcf is None else fcf / 1e7,
            None if fcf is None else (100.0 if fcf > 0 else 0.0),
            "Positive is good", unit="Cr"))
        out.append(check(
            "debt_to_equity", "Debt to equity", GROUP_SAFETY,
            None if de is None else de / 100.0,
            None if de is None else _ramp_down(de, DE_GOOD, DE_BAD),
            "Good below 1.0x, bad above 2.0x", unit="x"))
        out.append(check(
            "current_ratio", "Current ratio", GROUP_SAFETY, cr,
            None if cr is None else _ramp_up(cr, CURRENT_RATIO_BAD, CURRENT_RATIO_GOOD),
            f"Good above {CURRENT_RATIO_GOOD}, bad below {CURRENT_RATIO_BAD}",
            unit="x"))
    out.append(check(
        "peg", "PEG (P/E ÷ growth)", GROUP_VALUE, peg,
        None if peg is None else _ramp_down(peg, PEG_GOOD, PEG_BAD),
        f"Good below {PEG_GOOD}, bad above {PEG_BAD}", unit="x"))
    return out


def business_health(f: dict | None, *, financial: bool = False) -> dict:
    """0-100 business health from growth, quality, safety and price-vs-growth.

    Deliberately blind to the share price's recent move and to the user's
    average cost: this is the "is it a good business at a sane price" number,
    shown beside — never blended into — the dip score.
    """
    checks = health_checks(f, financial=financial)
    groups = {}
    for g in GROUP_WEIGHTS:
        known = [c["score"] for c in checks if c["group"] == g and c["score"] is not None]
        groups[g] = round(sum(known) / len(known), 1) if known else None
    weights = dict(GROUP_WEIGHTS)
    if financial:
        # Safety is not measured for lenders; its weight is not "missing data".
        weights.pop(GROUP_SAFETY)
        groups[GROUP_SAFETY] = None
    total = sum(weights.values())
    known_w = {g: w for g, w in weights.items() if groups.get(g) is not None}
    covered = sum(known_w.values())
    score = (round(sum(groups[g] * w for g, w in known_w.items()) / covered, 1)
             if covered > 0 else None)
    coverage = round(covered / total * 100.0, 1) if total else 0.0

    if score is None:
        grade = GRADE_UNKNOWN
    elif score >= 75:
        grade = GRADE_STRONG
    elif score >= 55:
        grade = GRADE_GOOD
    elif score >= 35:
        grade = GRADE_WEAK
    else:
        grade = GRADE_POOR

    return {
        "score": score,
        "grade": grade,
        "grade_label": GRADE_LABELS[grade],
        "coverage": coverage,
        "low_coverage": coverage < HEALTH_MIN_COVERAGE,
        "financial": financial,
        "groups": groups,
        "group_labels": GROUP_LABELS,
        "checks": checks,
    }


# ══════════════════════════════════════════════════════════════════════════
#  POSITION SIZE
# ══════════════════════════════════════════════════════════════════════════

SIZE_EXIT_OR_GROW = "exit_or_grow"
SIZE_BELOW_MIN = "below_min"
SIZE_OK = "ok"
SIZE_OVER_MAX = "over_max"
SIZE_UNKNOWN = "unknown"

SIZE_LABELS = {
    SIZE_EXIT_OR_GROW: "Too small — exit it or grow it",
    SIZE_BELOW_MIN: "Below a real position",
    SIZE_OK: "Sized right",
    SIZE_OVER_MAX: "Over the maximum",
    SIZE_UNKNOWN: "Value unknown",
}


def position_band(weight_pct, settings: dict) -> str:
    w = _num(weight_pct)
    if w is None:
        return SIZE_UNKNOWN
    if w > settings["max_position_pct"]:
        return SIZE_OVER_MAX
    if w < settings["exit_or_grow_below_pct"]:
        return SIZE_EXIT_OR_GROW
    if w < settings["min_position_pct"]:
        return SIZE_BELOW_MIN
    return SIZE_OK


def weights_by_symbol(holdings: Iterable[dict]) -> tuple[dict, float]:
    """{bare symbol: weight %} over the equity book's market value."""
    values = {}
    for h in holdings or []:
        v = _num(h.get("total_value"))
        if v is None or v <= 0:
            continue
        key = bare_symbol(h.get("symbol"))
        values[key] = values.get(key, 0.0) + v
    total = sum(values.values())
    if total <= 0:
        return {}, 0.0
    return {k: round(v / total * 100.0, 2) for k, v in values.items()}, total


# ══════════════════════════════════════════════════════════════════════════
#  THESIS
# ══════════════════════════════════════════════════════════════════════════

THESIS_MISSING = "missing"
THESIS_INCOMPLETE = "incomplete"
THESIS_OK = "ok"
THESIS_STALE = "stale"

THESIS_LABELS = {
    THESIS_MISSING: "No thesis — borrowed conviction?",
    THESIS_INCOMPLETE: "Thesis incomplete",
    THESIS_OK: "Thesis written",
    THESIS_STALE: "Thesis over a year old — re-answer it",
}

# The metrics a sell trigger may watch automatically, and how they read.
TRIGGER_METRICS = {
    "revenue_growth_pct": "Sales growth %",
    "earnings_growth_pct": "Profit (EPS) growth %",
    "operating_margin_pct": "Operating margin %",
    "roe_pct": "Return on equity %",
    "debt_to_equity": "Debt to equity (%, 100 = 1x)",
}
TRIGGER_OPS = ("<", "<=", ">", ">=")

MAX_TEXT = 600
MAX_TRIGGERS = 6


def clean_thesis(raw: dict | None, today: date | None = None) -> dict:
    """Validate and normalise a thesis submitted from the app.

    Raises ValueError with a readable message on bad input, so the endpoint
    can return it as a 400 rather than storing something unusable.
    """
    raw = raw or {}
    today = today or date.today()

    def text(key):
        v = raw.get(key)
        return (str(v).strip()[:MAX_TEXT]) if v is not None else ""

    triggers = []
    for t in (raw.get("sell_triggers") or [])[:MAX_TRIGGERS]:
        if isinstance(t, str):
            t = {"text": t}
        if not isinstance(t, dict):
            continue
        label = str(t.get("text") or "").strip()[:200]
        metric = t.get("metric") or None
        op = t.get("op") or None
        value = _num(t.get("value"))
        if metric is not None:
            if metric not in TRIGGER_METRICS:
                raise ValueError(f"Unknown trigger metric '{metric}'")
            if op not in TRIGGER_OPS:
                raise ValueError(f"Trigger operator must be one of {TRIGGER_OPS}")
            if value is None:
                raise ValueError("An automatic trigger needs a number")
        else:
            op = value = None
        if not label and metric is None:
            continue
        triggers.append({"text": label, "metric": metric, "op": op,
                         "value": value})

    review = _as_date(raw.get("next_review"))
    out = {
        "what_it_does": text("what_it_does"),
        "growth_reason": text("growth_reason"),
        "expected_eps_growth_pct": _num(raw.get("expected_eps_growth_pct")),
        "expected_sales_growth_pct": _num(raw.get("expected_sales_growth_pct")),
        "sell_triggers": triggers,
        "next_review": review.isoformat() if review else None,
        "source": text("source")[:120],
        "updated_at": today.isoformat(),
    }
    out["written_at"] = (_as_date(raw.get("written_at")) or today).isoformat()
    return out


def thesis_status(thesis: dict | None, settings: dict,
                  today: date | None = None) -> str:
    """missing / incomplete / ok / stale — the three questions answered?"""
    today = today or date.today()
    if not thesis:
        return THESIS_MISSING
    answered = (bool(thesis.get("what_it_does"))
                and bool(thesis.get("growth_reason"))
                and bool(thesis.get("sell_triggers")))
    if not answered:
        return THESIS_INCOMPLETE
    updated = _as_date(thesis.get("updated_at")) or _as_date(thesis.get("written_at"))
    if updated and (today - updated).days > settings["thesis_max_age_days"]:
        return THESIS_STALE
    return THESIS_OK


def _compare(value, op, threshold) -> bool:
    return {"<": value < threshold, "<=": value <= threshold,
            ">": value > threshold, ">=": value >= threshold}[op]


def fired_triggers(thesis: dict | None, fundamentals: dict | None) -> list[dict]:
    """Automatic sell triggers whose condition the latest numbers meet."""
    out = []
    for t in (thesis or {}).get("sell_triggers") or []:
        metric = t.get("metric")
        if not metric:
            continue
        current = _num((fundamentals or {}).get(metric))
        threshold = _num(t.get("value"))
        if current is None or threshold is None or t.get("op") not in TRIGGER_OPS:
            continue
        if _compare(current, t["op"], threshold):
            out.append({**t, "current": round(current, 2)})
    return out


# ══════════════════════════════════════════════════════════════════════════
#  QUARTERLY SNAPSHOTS & REVIEW
# ══════════════════════════════════════════════════════════════════════════

SNAPSHOT_FIELDS = ("earnings_growth_pct", "revenue_growth_pct",
                   "operating_margin_pct", "roe_pct", "debt_to_equity", "pe")
MAX_SNAPSHOTS = 16  # four years of quarters


def quarter_key(day: date) -> str:
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def record_snapshot(snapshots: list | None, fundamentals: dict | None,
                    today: date | None = None) -> tuple[list, bool]:
    """Store or refresh this quarter's snapshot. Returns (list, changed)."""
    today = today or date.today()
    snaps = [dict(s) for s in (snapshots or []) if isinstance(s, dict)]
    values = {k: _num((fundamentals or {}).get(k)) for k in SNAPSHOT_FIELDS}
    if all(v is None for v in values.values()):
        return snaps, False
    values = {k: (round(v, 4) if v is not None else None) for k, v in values.items()}
    key = quarter_key(today)
    entry = {"quarter": key, "taken_at": today.isoformat(), **values}
    if snaps and snaps[-1].get("quarter") == key:
        before = {k: snaps[-1].get(k) for k in SNAPSHOT_FIELDS}
        if before == values:
            return snaps, False
        snaps[-1] = entry
    else:
        snaps.append(entry)
    return snaps[-MAX_SNAPSHOTS:], True


RESULT_MET = "met"
RESULT_MISSED = "missed"
RESULT_UNKNOWN = "unknown"

RESULT_LABELS = {
    RESULT_MET: "Met the thesis",
    RESULT_MISSED: "Missed the thesis",
    RESULT_UNKNOWN: "No result to judge yet",
}


def judge_quarter(thesis: dict | None, snapshot: dict | None) -> str:
    """Did this quarter's growth meet what the thesis expected?"""
    if not thesis or not snapshot:
        return RESULT_UNKNOWN
    checks = []
    for expected_key, actual_key in (("expected_eps_growth_pct", "earnings_growth_pct"),
                                     ("expected_sales_growth_pct", "revenue_growth_pct")):
        expected = _num(thesis.get(expected_key))
        actual = _num(snapshot.get(actual_key))
        if expected is None or actual is None:
            continue
        checks.append(actual >= expected)
    if not checks:
        return RESULT_UNKNOWN
    return RESULT_MET if all(checks) else RESULT_MISSED


def quarter_results(thesis: dict | None, snapshots: Sequence[dict] | None,
                    manual: dict | None = None) -> list[dict]:
    """Per-quarter verdicts, newest last. A manual verdict overrides."""
    out = []
    for s in snapshots or []:
        q = s.get("quarter")
        override = (manual or {}).get(q) if q else None
        result = (override.get("result") if isinstance(override, dict)
                  and override.get("result") in (RESULT_MET, RESULT_MISSED)
                  else judge_quarter(thesis, s))
        out.append({"quarter": q, "result": result,
                    "manual": bool(override),
                    "note": (override or {}).get("note") if isinstance(override, dict) else None})
    return out


def missed_streak(results: Sequence[dict]) -> int:
    """Consecutive missed quarters, counting back from the latest judged one."""
    streak = 0
    for r in reversed(list(results)):
        if r["result"] == RESULT_UNKNOWN:
            continue
        if r["result"] != RESULT_MISSED:
            break
        streak += 1
    return streak


def trend_flags(snapshots: Sequence[dict] | None, quarters: int = 3) -> list[str]:
    """Business deterioration visible only across quarters."""
    snaps = list(snapshots or [])[-quarters:]
    if len(snaps) < quarters:
        return []
    flags = []

    def series(key):
        vals = [_num(s.get(key)) for s in snaps]
        return None if any(v is None for v in vals) else vals

    sales = series("revenue_growth_pct")
    if sales and all(b < a for a, b in zip(sales, sales[1:])):
        flags.append(f"Sales growth slowed {quarters} quarters in a row "
                     f"({sales[0]:.1f}% → {sales[-1]:.1f}%)")
    margin = series("operating_margin_pct")
    if margin and all(b < a for a, b in zip(margin, margin[1:])):
        flags.append(f"Operating margin fell {quarters} quarters in a row "
                     f"({margin[0]:.1f}% → {margin[-1]:.1f}%)")
    return flags


# ══════════════════════════════════════════════════════════════════════════
#  RESULTS CALENDAR
# ══════════════════════════════════════════════════════════════════════════
# Listed Indian companies report within 45 days of a quarter's end (60 for the
# March quarter, which is audited). These are the windows the reviews follow.

def results_windows(year: int) -> list[tuple[str, date, date]]:
    return [
        (f"Jan–Mar {year} results", date(year, 4, 15), date(year, 5, 30)),
        (f"Apr–Jun {year} results", date(year, 7, 15), date(year, 8, 14)),
        (f"Jul–Sep {year} results", date(year, 10, 15), date(year, 11, 14)),
        (f"Oct–Dec {year} results", date(year + 1, 1, 15), date(year + 1, 2, 14)),
    ]


def results_season(today: date | None = None) -> dict:
    """The current results window, or the next one, with days until it."""
    today = today or date.today()
    windows = results_windows(today.year - 1) + results_windows(today.year)
    for label, start, end in sorted(windows, key=lambda w: w[1]):
        if start <= today <= end:
            return {"label": label, "start": start.isoformat(),
                    "end": end.isoformat(), "in_season": True, "days_until": 0}
        if start > today:
            return {"label": label, "start": start.isoformat(),
                    "end": end.isoformat(), "in_season": False,
                    "days_until": (start - today).days}
    return {"label": None, "start": None, "end": None, "in_season": False,
            "days_until": None}


def review_due(thesis: dict | None, today: date | None = None) -> bool:
    today = today or date.today()
    review = _as_date((thesis or {}).get("next_review"))
    return bool(review and review <= today)


# ══════════════════════════════════════════════════════════════════════════
#  THE ADD-MORE GATE AND THE ACTION
# ══════════════════════════════════════════════════════════════════════════

ACTION_EXIT_OR_GROW = "exit_or_grow"
ACTION_WRITE_THESIS = "write_thesis"
ACTION_SELL_REVIEW = "sell_review"
ACTION_REDUCE = "reduce"
ACTION_TRIM = "trim_over_max"
ACTION_REVIEW = "review_due"
ACTION_ADD = "add_allowed"
ACTION_HOLD = "hold"

ACTION_LABELS = {
    ACTION_EXIT_OR_GROW: "Under 1% — exit it or grow it",
    ACTION_WRITE_THESIS: "Write your thesis first",
    ACTION_SELL_REVIEW: "Sell trigger hit — review",
    ACTION_REDUCE: "Thesis missed — reduce or exit",
    ACTION_TRIM: "Over the maximum — don't add",
    ACTION_REVIEW: "Review due",
    ACTION_ADD: "Adding allowed",
    ACTION_HOLD: "Hold",
}

# Most urgent first; also the board's sort order.
ACTION_RANK = {
    ACTION_SELL_REVIEW: 0,
    ACTION_REDUCE: 1,
    ACTION_EXIT_OR_GROW: 2,
    ACTION_WRITE_THESIS: 3,
    ACTION_TRIM: 4,
    ACTION_REVIEW: 5,
    ACTION_ADD: 6,
    ACTION_HOLD: 7,
}


# Blockers that only mean "the data is not there yet". An index fund has no
# earnings or business score of its own, so the caller drops these for ETFs.
NO_RESULT_BLOCKER = "No quarterly result yet to check your thesis against"
NO_HEALTH_BLOCKER = "No business data available to check"
DATA_ONLY_BLOCKERS = (NO_RESULT_BLOCKER, NO_HEALTH_BLOCKER)


def add_gate(*, thesis_state: str, last_result: str, streak: int,
             fired: Sequence[dict], band: str, health: dict,
             settings: dict) -> dict:
    """May new money go into this holding? Every reason it may not, listed.

    The price having fallen is NOT among the conditions, in either direction:
    a fall is neither a reason to add nor a reason to refuse.
    """
    blockers = []
    if thesis_state in (THESIS_MISSING, THESIS_INCOMPLETE):
        blockers.append("No complete thesis — answer the three questions first")
    elif thesis_state == THESIS_STALE:
        blockers.append("Thesis is over a year old — re-answer it")
    if fired:
        blockers.append("A sell trigger has fired")
    if last_result == RESULT_MISSED:
        blockers.append("The latest quarter missed your expected growth")
    elif last_result == RESULT_UNKNOWN:
        # "Add only when a result has met the thesis" — so no result means no
        # proof yet, not a pass. A holding the feed knows nothing about was
        # reading "Adding allowed".
        blockers.append(NO_RESULT_BLOCKER)
    if streak >= settings["misses_before_reduce"]:
        blockers.append(f"{streak} quarters missed in a row")
    if band == SIZE_OVER_MAX:
        blockers.append(f"Already above the {settings['max_position_pct']:.0f}% maximum")
    score = _num(health.get("score"))
    if score is None:
        blockers.append(NO_HEALTH_BLOCKER)
    elif score < settings["min_health_to_add"]:
        blockers.append(f"Business health {score:.0f} is below "
                        f"{settings['min_health_to_add']:.0f}")
    return {"allowed": not blockers, "blockers": blockers}


def choose_action(*, thesis_state: str, band: str, fired: Sequence[dict],
                  streak: int, gate: dict, due: bool, settings: dict) -> str:
    if fired:
        return ACTION_SELL_REVIEW
    if streak >= settings["misses_before_reduce"]:
        return ACTION_REDUCE
    if band == SIZE_EXIT_OR_GROW:
        return ACTION_EXIT_OR_GROW
    if thesis_state in (THESIS_MISSING, THESIS_INCOMPLETE, THESIS_STALE):
        return ACTION_WRITE_THESIS
    if band == SIZE_OVER_MAX:
        return ACTION_TRIM
    if due:
        return ACTION_REVIEW
    if gate["allowed"]:
        return ACTION_ADD
    return ACTION_HOLD


def analyse_holding(holding: dict, *, weight_pct, fundamentals: dict | None,
                    financial: bool, thesis: dict | None,
                    snapshots: Sequence[dict] | None,
                    manual_results: dict | None, settings: dict,
                    today: date | None = None) -> dict:
    """One conviction row for one equity holding."""
    today = today or date.today()
    health = business_health(fundamentals, financial=financial)
    band = position_band(weight_pct, settings)
    state = thesis_status(thesis, settings, today)
    results = quarter_results(thesis, snapshots, manual_results)
    judged = [r for r in results if r["result"] != RESULT_UNKNOWN]
    last = judged[-1]["result"] if judged else RESULT_UNKNOWN
    streak = missed_streak(results)
    fired = fired_triggers(thesis, fundamentals)
    gate = add_gate(thesis_state=state, last_result=last, streak=streak,
                    fired=fired, band=band, health=health, settings=settings)
    due = review_due(thesis, today)
    action = choose_action(thesis_state=state, band=band, fired=fired,
                           streak=streak, gate=gate, due=due, settings=settings)
    return {
        "symbol": holding.get("symbol"),
        "key": bare_symbol(holding.get("symbol")),
        "name": holding.get("name") or holding.get("symbol"),
        "weight_pct": _num(weight_pct),
        "size_band": band,
        "size_label": SIZE_LABELS[band],
        "health": health,
        "thesis": thesis,
        "thesis_state": state,
        "thesis_label": THESIS_LABELS[state],
        "borrowed_conviction": state in (THESIS_MISSING, THESIS_INCOMPLETE),
        "quarters": results,
        "last_result": last,
        "last_result_label": RESULT_LABELS[last],
        "missed_streak": streak,
        "fired_triggers": fired,
        "trend_flags": trend_flags(snapshots),
        "review_due": due,
        "next_review": (thesis or {}).get("next_review"),
        "add_gate": gate,
        "action": action,
        "action_label": ACTION_LABELS[action],
    }


# ══════════════════════════════════════════════════════════════════════════
#  WATCHLIST PIPELINE
# ══════════════════════════════════════════════════════════════════════════

STAGE_WAITING = "waiting"
STAGE_NEEDS_THESIS = "needs_thesis"
STAGE_FAILS_CHECK = "fails_check"
STAGE_READY = "ready"

STAGE_LABELS = {
    STAGE_WAITING: "Watching — don't buy yet",
    STAGE_NEEDS_THESIS: "Answer the three questions",
    STAGE_FAILS_CHECK: "Business check not passed",
    STAGE_READY: "Ready for a first position",
}


def watch_stage(entry: dict, *, thesis: dict | None, health: dict,
                settings: dict, today: date | None = None) -> dict:
    """Where a watchlist name stands on the way to a first buy."""
    today = today or date.today()
    added = _as_date(entry.get("added_at"))
    days = (today - added).days if added else None
    wait = int(settings["watch_min_days"])
    state = thesis_status(thesis, settings, today)
    score = _num(health.get("score"))

    if days is not None and days < wait:
        stage = STAGE_WAITING
    elif state != THESIS_OK:
        stage = STAGE_NEEDS_THESIS
    elif score is None or score < settings["min_health_to_add"] or health.get("low_coverage"):
        stage = STAGE_FAILS_CHECK
    else:
        stage = STAGE_READY

    return {
        "symbol": entry.get("symbol"),
        "key": bare_symbol(entry.get("symbol")),
        "name": entry.get("name") or entry.get("symbol"),
        "added_at": added.isoformat() if added else None,
        "days_watched": days,
        "ready_after": ((added + timedelta(days=wait)).isoformat()
                        if added else None),
        "thesis": thesis,
        "thesis_state": state,
        "health": health,
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "initial_position_pct": settings["initial_position_pct"],
    }


def board_sort_key(row: dict):
    return (ACTION_RANK.get(row.get("action"), 9),
            -(_num(row.get("weight_pct")) or 0))


def summarise(rows: Sequence[dict], watch: Sequence[dict]) -> dict:
    count = lambda pred: sum(1 for r in rows if pred(r))  # noqa: E731
    return {
        "holdings": len(rows),
        "with_thesis": count(lambda r: r["thesis_state"] in (THESIS_OK, THESIS_STALE)),
        "borrowed_conviction": count(lambda r: r["borrowed_conviction"]),
        "under_exit_line": count(lambda r: r["size_band"] == SIZE_EXIT_OR_GROW),
        "below_min": count(lambda r: r["size_band"] == SIZE_BELOW_MIN),
        "over_max": count(lambda r: r["size_band"] == SIZE_OVER_MAX),
        "add_allowed": count(lambda r: r["action"] == ACTION_ADD),
        "needs_action": count(lambda r: r["action"] in (
            ACTION_SELL_REVIEW, ACTION_REDUCE, ACTION_EXIT_OR_GROW)),
        "review_due": count(lambda r: r["review_due"]),
        "watching": len(watch),
        "ready_to_buy": sum(1 for w in watch if w["stage"] == STAGE_READY),
    }
