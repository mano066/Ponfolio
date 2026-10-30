"""
Capital deployment engine — pure computation layer.

Everything in this module is deterministic and network-free so it can be
unit-tested without hitting yfinance or mfapi.  ``main.py`` supplies the raw
per-holding facts (price/NAV, units, average cost, peak, benchmark symbol,
target weight) and calls :func:`build_deploy_board` to get the API payload.

The engine answers two questions:

1. *Which of my holdings most deserves new money right now?*  — scored on four
   factors and ranked.
2. *Given ₹X today, how should it actually be split?*  — quantised into real,
   placeable tickets.

Design notes
------------
* **Every sub-score is ``float | None``, and ``None`` means UNKNOWN.  Unknown is
  never coerced to ``0``.**  A fund with no target configured must not rank as
  though it were sitting perfectly at target; a freshly added holding with no
  cost basis must not read as "expensive relative to cost".  This is the single
  rule the whole module is organised around.
* The composite renormalises over the factors that are actually known and
  reports a ``confidence``, so a candidate scored on one loud factor cannot
  outrank a candidate scored on four.  Below
  :data:`MIN_CONFIDENCE_FOR_ALLOCATION` a candidate is still ranked and shown,
  but receives no money.
* Every candidate that receives nothing carries an explicit ``skip_reason``.
  For a feature whose entire job is justifying a decision, silence is the worst
  possible output.
* Allocation is quantised to tickets that can actually be placed (₹100 steps
  for funds, whole shares for equity) and the money always balances exactly:
  ``Σ allocations + unallocated == amount``.
* SIP status is derived from REAL transactions, never from a deployment log.  A
  log only knows about buys made through this feature, so a SIP debited by the
  AMC and picked up by the Kite sync would read "not done" forever and the app
  would nag the user about a SIP they actually paid.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Sequence

# ── Factor tunables ───────────────────────────────────────────────────────
# Each factor maps a real-world magnitude onto 0-100 through a dead-band (below
# which it is noise) and a saturation point (above which more is not better).

# Own drawdown from peak. 25% below peak is a full bear leg on Indian equity;
# beyond that, further drawdown increasingly signals a BROKEN holding rather
# than a bigger opportunity, and this factor cannot tell the two apart. The 2%
# dead-band stops a fund 0.4% off its peak contributing noise every single day.
OWN_DD_MIN_PCT = 2.0
OWN_DD_SATURATION_PCT = 25.0

# Index drawdown. Deliberately lower than the own-drawdown saturation: an index
# is diversified and falls far less than any single constituent. Nifty's
# non-COVID drawdowns cluster at 10-15%, so reusing 25 here would leave this
# factor asleep through exactly the corrections this feature exists for.
INDEX_DD_MIN_PCT = 1.0
INDEX_DD_SATURATION_PCT = 15.0

# Discount to the user's own average cost. A tranche bought 15% below cost
# meaningfully moves the blended average; past that the marginal information is
# nil. Never negative — being above cost is not a reason to sell.
AVG_COST_SATURATION_PCT = 15.0

# Shortfall against target weight, measured RELATIVELY. A 2pp gap against a 5%
# target means you hold 60% of what you intended; the same 2pp against a 30%
# target is noise. Scoring on absolute percentage points would funnel money into
# the largest targets forever and starve the small ones — the opposite of
# rebalancing. Holding half your intended weight is already a maximal signal.
UNDERWEIGHT_MIN_GAP_PP = 0.5
UNDERWEIGHT_SATURATION_RATIO = 0.50

FACTOR_OWN_DRAWDOWN = "own_drawdown"
FACTOR_INDEX_DIP = "index_dip"
FACTOR_BELOW_AVG_COST = "below_avg_cost"
FACTOR_UNDERWEIGHT = "underweight"

FACTOR_KEYS = (FACTOR_OWN_DRAWDOWN, FACTOR_UNDERWEIGHT,
               FACTOR_BELOW_AVG_COST, FACTOR_INDEX_DIP)

FACTOR_LABELS = {
    FACTOR_OWN_DRAWDOWN: "Fall from its own peak",
    FACTOR_INDEX_DIP: "Its market is down",
    FACTOR_BELOW_AVG_COST: "Below your average cost",
    FACTOR_UNDERWEIGHT: "Below your target share",
}

# own_drawdown leads: the most specific and most actionable signal, and the one
# the user actually described ("the fund dipped").
# underweight is nearly as heavy because it is the ONLY factor encoding the
# user's plan rather than the market's mood — it is what stops the engine
# shovelling money into whatever fell hardest until one position owns the book.
# below_avg_cost is real but substantially redundant with own_drawdown; equal
# weighting would double-count the same dip.
# index_dip is the weakest DISCRIMINATOR: in a broad selloff it is near-identical
# across every candidate and contributes nothing to the ranking. It earns its
# keep only in a sector rotation.
DEFAULT_WEIGHTS = {
    FACTOR_OWN_DRAWDOWN: 0.35,
    FACTOR_UNDERWEIGHT: 0.30,
    FACTOR_BELOW_AVG_COST: 0.20,
    FACTOR_INDEX_DIP: 0.15,
}

# A candidate resting on index_dip alone (weight 0.15 -> confidence 15) can
# score 100 and mean nothing. 40 is the point at which at least two factors, or
# one heavy one, are actually speaking.
MIN_CONFIDENCE_FOR_ALLOCATION = 40.0

# ── Allocation tunables ───────────────────────────────────────────────────
# Below the floor you are looking at something at its peak, at or above target,
# and above your cost. The right answer there is "not this one", not "a token
# amount anyway".
SCORE_FLOOR = 35.0
# ₹10,000 split five ways is ₹2,000 tickets — noise against a ₹30,000 monthly
# SIP. Four keeps tranches meaningful.
MAX_CANDIDATES_PER_DEPLOY = 4
# This is opportunistic top-up money, not a single-name bet. 40% still lets a
# clear winner take a decisive slice. Loosened automatically to 100/N when there
# are too few candidates for it to be satisfiable — see allocate() step 5.
MAX_CONCENTRATION_PCT = 40.0
MIN_TICKET_MF = 500.0
ROUNDING_STEP_MF = 100.0
# Raw score compresses: 80 vs 40 is only 2:1, so a barely-qualifying candidate
# would take a third of the money. Weighting by EXCESS over the floor gives
# 50:10 = 5:1, matching the intuition that 80 vs 40 is a big difference. The
# epsilon stops a lone candidate sitting exactly at the floor being unfundable.
SCORE_WEIGHT_EPS = 5.0
MAX_CAP_PASSES = 5
MAX_REMAINDER_PASSES = 2

# ── SIP plan tunables ─────────────────────────────────────────────────────
# AMC rounding and part-debits mean an exact match is rare.
DONE_TOLERANCE = 0.95
# Bank/AMC settlement lag before calling a leg overdue is fair.
GRACE_DAYS = 3

KIND_FUND = "fund"
KIND_STOCK = "stock"

STATUS_DONE = "done"
STATUS_PARTIAL = "partial"
STATUS_SCHEDULED = "scheduled"
STATUS_DUE = "due"
STATUS_OVERDUE = "overdue"
STATUS_UNKNOWN = "unknown"
STATUS_INACTIVE = "inactive"


# ══════════════════════════════════════════════════════════════════════════
#  SMALL HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _num(value, default=None):
    """Coerce to float. ``default`` (usually None) when it is not a number."""
    if value is None:
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return default
    return f


def _as_date(value) -> date | None:
    """Coerce str / date / datetime into a ``date``. ``None`` when unparseable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("T", " ").split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _clamp01(value: float) -> float:
    return 0.0 if value < 0 else (1.0 if value > 1 else value)


def _ramp(value: float, floor: float, saturation: float) -> float:
    """Map ``value`` onto 0-100 across a dead-band and a saturation point."""
    if saturation <= floor:
        return 0.0
    return round(_clamp01((value - floor) / (saturation - floor)) * 100, 2)


def normalize_weights(raw: dict | None) -> dict:
    """Sanitise a user-supplied weight map.

    Drops unknown keys and non-positive/non-numeric values, then renormalises
    the survivors to sum to exactly 1.0.  Returns a copy of
    :data:`DEFAULT_WEIGHTS` when nothing valid remains, so a corrupted settings
    file degrades to sane behaviour rather than a division by zero.
    """
    if not isinstance(raw, dict):
        return dict(DEFAULT_WEIGHTS)
    clean = {}
    for key in FACTOR_KEYS:
        w = _num(raw.get(key))
        if w is not None and w > 0:
            clean[key] = w
    total = sum(clean.values())
    if not clean or total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(v / total, 6) for k, v in clean.items()}


# ══════════════════════════════════════════════════════════════════════════
#  THE FOUR FACTORS
#
#  Each returns a 0-100 score, or None meaning "we do not know".
# ══════════════════════════════════════════════════════════════════════════

def score_own_drawdown(price, peak, *, own_dd_pct=None) -> float | None:
    """How far below its own peak this holding is trading.

    ``own_dd_pct`` is an optional pre-computed override — ``mf_analysis``
    already returns ``current_dd`` for funds, and re-deriving a peak from a NAV
    series we have already scanned is wasted work.  Sign is ignored; the
    magnitude is what matters.
    """
    dd = _num(own_dd_pct)
    if dd is None:
        p = _num(price)
        pk = _num(peak)
        if p is None or pk is None or p <= 0 or pk <= 0:
            return None
        dd = (pk - p) / pk * 100
    else:
        dd = abs(dd)
    return _ramp(max(dd, 0.0), OWN_DD_MIN_PCT, OWN_DD_SATURATION_PCT)


def score_index_dip(benchmark: str | None, index_dips: dict) -> float | None:
    """How far this holding's benchmark index is below its own 1-year high.

    ``None`` when there is no benchmark, or the tape had no reading for it.
    Crucially NOT ``0`` — "the feed is down" and "the index is at its high" must
    not produce the same score.
    """
    if not benchmark or not isinstance(index_dips, dict):
        return None
    dip = _num(index_dips.get(benchmark))
    if dip is None:
        return None
    return _ramp(max(dip, 0.0), INDEX_DD_MIN_PCT, INDEX_DD_SATURATION_PCT)


def score_below_avg_cost(price, avg_cost) -> float | None:
    """Discount of the current price/NAV to the user's own average cost.

    Zero when trading above cost — never negative.  This factor is a reason to
    buy; letting it go negative would let a winning position drag down its own
    composite.  ``None`` when there is no cost basis at all, which is a
    genuinely different statement from "no discount".
    """
    p = _num(price)
    cost = _num(avg_cost)
    if p is None or cost is None or p <= 0 or cost <= 0:
        return None
    discount = (cost - p) / cost * 100
    if discount <= 0:
        return 0.0
    return round(_clamp01(discount / AVG_COST_SATURATION_PCT) * 100, 2)


def score_underweight(value, total_value, target_pct) -> float | None:
    """How far below its target share of the book this holding sits.

    Measured as a RELATIVE shortfall (see the module tunables).  ``None`` when
    no target is configured — which must not be confused with "exactly on
    target".
    """
    target = _num(target_pct)
    total = _num(total_value)
    val = _num(value, 0.0) or 0.0
    if target is None or target <= 0 or total is None or total <= 0:
        return None
    actual = val / total * 100
    gap = target - actual
    if gap <= UNDERWEIGHT_MIN_GAP_PP:
        return 0.0
    return round(_clamp01((gap / target) / UNDERWEIGHT_SATURATION_RATIO) * 100, 2)


# ══════════════════════════════════════════════════════════════════════════
#  COMPOSITE SCORING
# ══════════════════════════════════════════════════════════════════════════

def _why(kind: str, factors: dict, gap_pp, target_pct, benchmark_label) -> list[str]:
    """Plain-English reasons, strongest first. Only for factors that fired."""
    out = []
    noun = "NAV" if kind == KIND_FUND else "price"

    dd = factors[FACTOR_OWN_DRAWDOWN]
    if dd["score"] and dd["value"]:
        out.append(f"{dd['value']:.1f}% below its own {noun} peak")

    uw = factors[FACTOR_UNDERWEIGHT]
    if uw["score"] and gap_pp and target_pct:
        out.append(f"{gap_pp:.1f} points below your {target_pct:.0f}% target")

    bc = factors[FACTOR_BELOW_AVG_COST]
    if bc["score"] and bc["value"]:
        out.append(f"{bc['value']:.1f}% below what you paid")

    idx = factors[FACTOR_INDEX_DIP]
    if idx["score"] and idx["value"]:
        label = benchmark_label or "its index"
        out.append(f"{label} is {idx['value']:.1f}% off its 1-year high")

    return out


def score_candidate(cand: dict, *, index_dips: dict = None,
                    total_value: float = 0.0, weights: dict = None) -> dict:
    """Score one candidate on all four factors and blend them.

    The composite is renormalised over the factors that are known, so a
    candidate missing two factors is judged on the two it has rather than being
    quietly penalised for the gap.  ``confidence`` reports how much of the total
    weight was actually available.
    """
    weights = weights or DEFAULT_WEIGHTS
    index_dips = index_dips or {}

    kind = cand.get("kind") or KIND_FUND
    price = _num(cand.get("price"))
    units = _num(cand.get("units"), 0.0) or 0.0
    value = _num(cand.get("value"))
    if value is None:
        value = (price or 0) * units
    avg_cost = _num(cand.get("avg_cost"))
    target_pct = _num(cand.get("target_pct"))
    benchmark = cand.get("benchmark")

    # ── raw factor magnitudes, kept alongside the scores so the UI can show
    #    the real number rather than an abstract 0-100 ──
    dd_value = _num(cand.get("own_dd_pct"))
    if dd_value is not None:
        dd_value = abs(dd_value)
    else:
        peak = _num(cand.get("peak"))
        if peak and price and peak > 0 and price > 0:
            dd_value = max((peak - price) / peak * 100, 0.0)

    idx_value = _num(index_dips.get(benchmark)) if benchmark else None
    cost_value = None
    if price and avg_cost and price > 0 and avg_cost > 0:
        cost_value = max((avg_cost - price) / avg_cost * 100, 0.0)

    actual_pct = None
    gap_pp = None
    if total_value and total_value > 0:
        actual_pct = round(value / total_value * 100, 2)
        if target_pct is not None and target_pct > 0:
            gap_pp = round(target_pct - actual_pct, 2)

    factors = {
        FACTOR_OWN_DRAWDOWN: {
            "score": score_own_drawdown(price, cand.get("peak"),
                                        own_dd_pct=cand.get("own_dd_pct")),
            "value": round(dd_value, 2) if dd_value is not None else None,
            "unit": "% below peak",
        },
        FACTOR_INDEX_DIP: {
            "score": score_index_dip(benchmark, index_dips),
            "value": round(idx_value, 2) if idx_value is not None else None,
            "unit": "% below 1y high",
        },
        FACTOR_BELOW_AVG_COST: {
            "score": score_below_avg_cost(price, avg_cost),
            "value": round(cost_value, 2) if cost_value is not None else None,
            "unit": "% below avg cost",
        },
        FACTOR_UNDERWEIGHT: {
            "score": score_underweight(value, total_value, target_pct),
            "value": gap_pp,
            "unit": "pp below target",
        },
    }

    known = [(weights.get(k, 0.0), factors[k]["score"])
             for k in FACTOR_KEYS
             if factors[k]["score"] is not None and weights.get(k, 0.0) > 0]
    known_weight = sum(w for w, _ in known)
    total_weight = sum(weights.get(k, 0.0) for k in FACTOR_KEYS) or 1.0

    if known:
        score = round(sum(w * s for w, s in known) / known_weight, 2)
        confidence = round(known_weight / total_weight * 100)
    else:
        # Nothing is known. Report that honestly rather than scoring zero.
        score = None
        confidence = 0

    missing = [k for k in FACTOR_KEYS if factors[k]["score"] is None]

    return {
        "kind": kind,
        "key": cand.get("key"),
        "name": cand.get("name") or cand.get("key"),
        "sector": cand.get("sector") or "",
        "price": round(price, 4) if price is not None else None,
        "units": round(units, 4),
        "value": round(value, 2),
        "avg_cost": round(avg_cost, 4) if avg_cost is not None else None,
        "peak": _num(cand.get("peak")),
        "peak_basis": cand.get("peak_basis"),
        "benchmark": benchmark,
        "benchmark_label": cand.get("benchmark_label"),
        "target_pct": target_pct,
        "actual_pct": actual_pct,
        "gap_pp": gap_pp,
        "at_or_over_target": bool(gap_pp is not None and gap_pp <= 0),
        "factors": factors,
        "score": score,
        "confidence": confidence,
        "eligible": score is not None and confidence >= MIN_CONFIDENCE_FOR_ALLOCATION,
        "known_factors": [k for k in FACTOR_KEYS if factors[k]["score"] is not None],
        "missing_factors": missing,
        "why": _why(kind, factors, gap_pp, target_pct, cand.get("benchmark_label")),
        "skip_reason": None,
        "rank": None,
    }


def _sort_key(row: dict):
    """Deterministic ordering: score, confidence, drawdown, then key.

    The final ``key`` tiebreak is what makes the output stable between calls —
    without it two equally-scored funds swap places and every snapshot test
    flakes intermittently.
    """
    dd = row["factors"][FACTOR_OWN_DRAWDOWN]["score"]
    return (
        -(row["score"] if row["score"] is not None else -1),
        -(row["confidence"] or 0),
        -(dd if dd is not None else -1),
        str(row.get("key") or ""),
    )


def rank_candidates(cands: Sequence[dict], *, index_dips: dict = None,
                    total_value: float = 0.0, weights: dict = None) -> list[dict]:
    """Score every candidate and return them in ranked order."""
    rows = [score_candidate(c, index_dips=index_dips, total_value=total_value,
                            weights=weights)
            for c in (cands or []) if isinstance(c, dict)]
    rows.sort(key=_sort_key)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return rows


# ══════════════════════════════════════════════════════════════════════════
#  ALLOCATION
# ══════════════════════════════════════════════════════════════════════════

def _alloc_row(row: dict, amount: float, skip_reason: str = None,
               units: float = None) -> dict:
    return {
        "kind": row["kind"],
        "key": row["key"],
        "name": row["name"],
        "label": row["name"],
        "price": row["price"],
        "score": row["score"],
        "confidence": row["confidence"],
        "amount": round(amount, 2),
        "units": units,
        "shares": int(units) if units is not None and row["kind"] == KIND_STOCK else None,
        "reason": "; ".join(row["why"][:2]) if row["why"] else "",
        "skip_reason": skip_reason,
    }


def allocate(amount: float, ranked: Sequence[dict], *,
             score_floor: float = SCORE_FLOOR,
             max_candidates: int = MAX_CANDIDATES_PER_DEPLOY,
             max_concentration_pct: float = MAX_CONCENTRATION_PCT,
             min_ticket_mf: float = MIN_TICKET_MF,
             rounding_step: float = ROUNDING_STEP_MF,
             min_confidence: float = MIN_CONFIDENCE_FOR_ALLOCATION) -> dict:
    """Split ``amount`` across ranked candidates into placeable tickets.

    Guarantees ``Σ allocations + unallocated == amount`` exactly.  Every
    candidate that receives nothing appears in ``skipped`` with a reason.
    """
    amount = max(_num(amount, 0.0) or 0.0, 0.0)
    ranked = list(ranked or [])

    # ── Step 1: filter, recording a reason for everything excluded ──
    eligible: list[dict] = []
    skipped: list[dict] = []
    for row in ranked:
        if row.get("score") is None:
            skipped.append(_alloc_row(row, 0, "unscored"))
        elif not row.get("price") or row["price"] <= 0:
            skipped.append(_alloc_row(row, 0, "no_price"))
        elif row["score"] < score_floor:
            skipped.append(_alloc_row(row, 0, "below_score_floor"))
        elif (row.get("confidence") or 0) < min_confidence:
            skipped.append(_alloc_row(row, 0, "low_confidence"))
        elif row.get("at_or_over_target") and row["score"] < score_floor:
            skipped.append(_alloc_row(row, 0, "at_or_over_target"))
        else:
            eligible.append(row)

    # ── Step 2: truncate to the top N ──
    selected = eligible[:max(int(max_candidates), 0)]
    for row in eligible[len(selected):]:
        skipped.append(_alloc_row(row, 0, "not_selected"))

    def _result(allocations, unallocated, reason=None, extra=None):
        out = {
            "amount": round(amount, 2),
            "allocations": allocations,
            "skipped": skipped,
            "allocated": round(sum(a["amount"] for a in allocations), 2),
            "unallocated": round(unallocated, 2),
            "unallocated_reason": reason,
            "count": len(allocations),
        }
        if extra:
            out.update(extra)
        return out

    if amount <= 0:
        return _result([], 0.0, "no_amount" if not selected else None)
    if not selected:
        return _result([], amount, "no_eligible_candidate")

    # ── Step 3: weight by EXCESS score over the floor ──
    weights = [max(r["score"] - score_floor, 0.0) + SCORE_WEIGHT_EPS
               for r in selected]
    weight_sum = sum(weights) or float(len(selected))

    # ── Step 4: provisional split ──
    raw = [amount * w / weight_sum for w in weights]

    # ── Step 5: concentration cap, applied iteratively ──
    # The cap can never be tighter than an equal split. With N candidates, a cap
    # below 100/N makes the money unplaceable BY CONSTRUCTION: two candidates
    # under a 40% cap can absorb at most 80% of the amount, stranding the rest
    # for no reason the user could ever act on. Taking the looser of the two
    # also disables the cap entirely for a single candidate, which is the
    # behaviour we want there anyway.
    effective_cap_pct = max(max_concentration_pct, 100.0 / len(selected))
    apply_cap = effective_cap_pct < 100.0
    cap = amount * effective_cap_pct / 100 if apply_cap else amount
    if apply_cap:
        for _ in range(MAX_CAP_PASSES):
            over = [i for i, v in enumerate(raw) if v > cap + 1e-9]
            if not over:
                break
            surplus = sum(raw[i] - cap for i in over)
            for i in over:
                raw[i] = cap
            room = [i for i in range(len(raw)) if raw[i] < cap - 1e-9]
            if not room or surplus <= 0:
                break
            room_weight = sum(weights[i] for i in room) or float(len(room))
            for i in room:
                raw[i] += surplus * weights[i] / room_weight

    # ── Step 6: quantise to real tickets ──
    allocations: list[dict] = []
    for row, want in zip(selected, raw):
        price = row["price"]
        if row["kind"] == KIND_STOCK:
            shares = int(want // price)
            if shares < 1:
                skipped.append(_alloc_row(row, 0, "below_one_share"))
                continue
            allocations.append(_alloc_row(row, shares * price, units=float(shares)))
        else:
            alloc = (want // rounding_step) * rounding_step
            if alloc < min_ticket_mf:
                skipped.append(_alloc_row(row, 0, "below_min_ticket"))
                continue
            units = round(alloc / price, 3) if price else None
            allocations.append(_alloc_row(row, alloc, units=units))

    # ── Step 7: greedy remainder top-up, still respecting the cap ──
    by_key = {r["key"]: r for r in selected}
    for _ in range(MAX_REMAINDER_PASSES):
        remainder = amount - sum(a["amount"] for a in allocations)
        if remainder <= 0:
            break
        progressed = False

        # Nothing funded yet? A single ticket may still fit — this is how a ₹700
        # deployment finds its one ₹500 fund ticket.
        targets = allocations if allocations else []
        if not targets:
            for row in selected:
                price = row["price"]
                if row["kind"] == KIND_STOCK and remainder >= price:
                    shares = int(remainder // price)
                    allocations.append(_alloc_row(row, shares * price,
                                                  units=float(shares)))
                    progressed = True
                    break
                if row["kind"] == KIND_FUND:
                    alloc = (remainder // rounding_step) * rounding_step
                    if alloc >= min_ticket_mf:
                        allocations.append(_alloc_row(
                            row, alloc,
                            units=round(alloc / price, 3) if price else None))
                        progressed = True
                        break
            if not progressed:
                break
            continue

        for entry in targets:
            remainder = amount - sum(a["amount"] for a in allocations)
            if remainder <= 0:
                break
            row = by_key.get(entry["key"])
            if not row:
                continue
            price = row["price"]
            headroom = (cap - entry["amount"]) if apply_cap else remainder
            budget = min(remainder, max(headroom, 0.0))
            if budget <= 0:
                continue
            if row["kind"] == KIND_STOCK:
                extra_shares = int(budget // price)
                if extra_shares < 1:
                    continue
                entry["amount"] = round(entry["amount"] + extra_shares * price, 2)
                entry["units"] = (entry["units"] or 0) + extra_shares
                entry["shares"] = int(entry["units"])
            else:
                extra = (budget // rounding_step) * rounding_step
                if extra <= 0:
                    continue
                entry["amount"] = round(entry["amount"] + extra, 2)
                entry["units"] = round(entry["amount"] / price, 3) if price else None
            progressed = True
        if not progressed:
            break

    allocated = sum(a["amount"] for a in allocations)
    unallocated = round(amount - allocated, 2)

    reason = None
    extra = {}
    if unallocated > 0:
        if not allocations:
            reason = "amount_below_min_ticket"
            tickets = []
            for row in selected:
                tickets.append(row["price"] if row["kind"] == KIND_STOCK
                               else min_ticket_mf)
            if tickets:
                extra["min_ticket_needed"] = round(min(tickets), 2)
        else:
            reason = "below_min_ticket"

    return _result(allocations, unallocated, reason, extra)


# ══════════════════════════════════════════════════════════════════════════
#  SIP PLAN STATUS
# ══════════════════════════════════════════════════════════════════════════

def _month_bounds(as_of: date) -> tuple[date, date]:
    last = calendar.monthrange(as_of.year, as_of.month)[1]
    return date(as_of.year, as_of.month, 1), date(as_of.year, as_of.month, last)


def _paid_for_fund(mf_portfolio, key, start: date, end: date) -> float:
    for fund in mf_portfolio or []:
        if fund.get("scheme_name") != key:
            continue
        total = 0.0
        for txn in fund.get("transactions", []) or []:
            when = _as_date(txn.get("date"))
            invested = _num(txn.get("invested"), 0.0) or 0.0
            if when and start <= when <= end and invested > 0:
                total += invested
        return round(total, 2)
    return None  # fund not found at all


def _paid_for_stock(ledger, key, start: date, end: date) -> float:
    rows = (ledger or {}).get(key)
    if rows is None:
        return None
    total = 0.0
    for row in rows:
        when = _as_date(row.get("date"))
        if not when or not (start <= when <= end):
            continue
        # A sale does not undo a SIP, so SELL rows are ignored outright.
        if str(row.get("type", "")).upper() != "BUY":
            continue
        total += _num(row.get("amount"), 0.0) or 0.0
    return round(total, 2)


def plan_status(legs: Sequence[dict], *, mf_portfolio: Sequence[dict] = (),
                equity_ledger: dict = None, as_of: date = None) -> dict:
    """Work out, for the calendar month containing ``as_of``, what is done.

    Driven entirely by real recorded transactions — see the module docstring for
    why a separate deployment log is deliberately not consulted here.
    """
    today = as_of or date.today()
    start, end = _month_bounds(today)
    days_in_month = end.day

    out_legs = []
    due_total = done_total = 0.0
    counts = {STATUS_DONE: 0, STATUS_PARTIAL: 0, STATUS_SCHEDULED: 0,
              STATUS_DUE: 0, STATUS_OVERDUE: 0, STATUS_UNKNOWN: 0,
              STATUS_INACTIVE: 0}

    for leg in legs or []:
        if not isinstance(leg, dict):
            continue
        kind = leg.get("kind") or KIND_FUND
        key = leg.get("key")
        amount = _num(leg.get("amount"), 0.0) or 0.0
        due_day = int(_num(leg.get("due_day"), 1) or 1)
        # A due_day of 31 must still fire in February.
        effective_due = min(max(due_day, 1), days_in_month)
        active = leg.get("active", True)

        row = {
            "id": leg.get("id"),
            "kind": kind,
            "key": key,
            "label": leg.get("label") or key,
            "amount": round(amount, 2),
            "due_day": due_day,
            "effective_due_day": effective_due,
            "active": bool(active),
            "note": leg.get("note", ""),
        }

        if not active:
            row.update({"status": STATUS_INACTIVE, "deployed_this_month": 0.0,
                        "shortfall": 0.0, "days_to_due": None,
                        "days_overdue": None, "missing_holding": False})
            counts[STATUS_INACTIVE] += 1
            out_legs.append(row)
            continue

        if kind == KIND_STOCK:
            paid = _paid_for_stock(equity_ledger, key, start, end)
        else:
            paid = _paid_for_fund(mf_portfolio, key, start, end)

        missing = paid is None
        paid = paid or 0.0

        if missing:
            status = STATUS_UNKNOWN
        elif amount > 0 and paid >= amount * DONE_TOLERANCE:
            status = STATUS_DONE
        elif paid > 0:
            status = STATUS_PARTIAL
        elif today.day < effective_due:
            status = STATUS_SCHEDULED
        elif today.day <= effective_due + GRACE_DAYS:
            status = STATUS_DUE
        else:
            status = STATUS_OVERDUE

        row.update({
            "status": status,
            "deployed_this_month": round(paid, 2),
            "shortfall": round(max(amount - paid, 0.0), 2),
            "days_to_due": max(effective_due - today.day, 0)
                           if today.day < effective_due else None,
            "days_overdue": max(today.day - effective_due, 0)
                            if status == STATUS_OVERDUE else None,
            "missing_holding": missing,
        })
        counts[status] += 1
        due_total += amount
        done_total += min(paid, amount) if amount > 0 else paid
        out_legs.append(row)

    return {
        "month": today.strftime("%Y-%m"),
        "as_of": today.isoformat(),
        "legs": out_legs,
        "budget_total": round(due_total, 2),
        "deployed_total": round(done_total, 2),
        "remaining": round(max(due_total - done_total, 0.0), 2),
        "counts": counts,
        "done_count": counts[STATUS_DONE],
        "total_count": len([l for l in out_legs if l["active"]]),
    }


# ══════════════════════════════════════════════════════════════════════════
#  DEFAULTS — first-run suggestions
# ══════════════════════════════════════════════════════════════════════════

def default_legs_from_portfolio(mf_portfolio: Sequence[dict] = (),
                                portfolio: Sequence[dict] = (),
                                monthly_budget: float = 30000.0) -> list[dict]:
    """Suggest one leg per fund, splitting a budget evenly, all due on the 5th.

    A starting point for the plan dialog, not a saved plan.  Funds only —
    proposing a monthly leg for every stock a user happens to hold would be
    presumptuous.
    """
    funds = [f for f in (mf_portfolio or []) if f.get("scheme_name")]
    if not funds:
        return []
    per = round((monthly_budget or 0) / len(funds) / 100) * 100
    return [{
        "id": None,
        "kind": KIND_FUND,
        "key": f["scheme_name"],
        "label": f["scheme_name"],
        "amount": float(per),
        "due_day": 5,
        "active": True,
        "note": "",
    } for f in funds]


def default_targets_from_portfolio(mf_portfolio: Sequence[dict] = (),
                                   portfolio: Sequence[dict] = (),
                                   prices: dict = None) -> dict:
    """Suggest targets equal to each holding's CURRENT weight.

    Deliberately a no-op rebalance: it hands the user a complete, already-summing
    map to edit rather than a blank form, and until they change something the
    underweight factor stays silent instead of inventing drift.
    """
    prices = prices or {}
    values: dict[str, float] = {}
    for fund in mf_portfolio or []:
        key = fund.get("scheme_name")
        if key:
            values[key] = _num(fund.get("current_value"), 0.0) or 0.0
    for holding in portfolio or []:
        key = holding.get("symbol")
        if not key:
            continue
        price = _num(prices.get(key), None)
        if price is None:
            price = _num(holding.get("avg_cost"), 0.0) or 0.0
        values[key] = (_num(holding.get("shares"), 0.0) or 0.0) * price

    total = sum(values.values())
    if total <= 0:
        return {}
    return {k: round(v / total * 100, 2) for k, v in values.items() if v > 0}


# ══════════════════════════════════════════════════════════════════════════
#  BOARD ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════

def _targets_block(rows: Sequence[dict]) -> dict:
    configured = [r for r in rows if r.get("target_pct")]
    total = round(sum(r["target_pct"] for r in configured), 2)
    warning = None
    if configured and abs(total - 100.0) > 1.0:
        warning = (f"Your targets add up to {total:.0f}%, not 100%. "
                   "The engine still works, but the shares will not be what you expect.")
    return {
        "configured": bool(configured),
        "configured_count": len(configured),
        "sum_pct": total,
        "warning": warning,
    }


def _alerts(rows: Sequence[dict], plan: dict, targets: dict) -> list[dict]:
    out = []
    overdue = [l for l in plan.get("legs", []) if l.get("status") == STATUS_OVERDUE]
    if overdue:
        names = ", ".join(l["label"] for l in overdue[:3])
        out.append({"level": "warn",
                    "msg": f"{len(overdue)} SIP line(s) are overdue: {names}."})
    if targets.get("warning"):
        out.append({"level": "info", "msg": targets["warning"]})
    if not targets.get("configured"):
        out.append({"level": "info",
                    "msg": "No target shares set yet, so the 'below target' "
                           "check is switched off. Set them in Edit plan."})
    unknown = [l for l in plan.get("legs", []) if l.get("missing_holding")]
    if unknown:
        names = ", ".join(l["label"] for l in unknown[:3])
        out.append({"level": "warn",
                    "msg": f"Plan line(s) point at holdings you no longer have: {names}."})
    return out


def build_deploy_board(candidates: Sequence[dict] = (), *,
                       index_dips: dict = None,
                       amount: float = 0.0,
                       weights: dict = None,
                       legs: Sequence[dict] = (),
                       mf_portfolio: Sequence[dict] = (),
                       equity_ledger: dict = None,
                       total_value: float = None,
                       as_of: date = None,
                       **alloc_opts) -> dict:
    """Assemble the full deployment board — the API payload.

    ``amount=0`` is a valid, useful call: the ranking stands on its own without
    a deployment attached to it.
    """
    weights = normalize_weights(weights) if weights else dict(DEFAULT_WEIGHTS)
    candidates = list(candidates or [])

    if total_value is None:
        total_value = sum(
            (_num(c.get("value")) if c.get("value") is not None
             else (_num(c.get("price"), 0.0) or 0.0) * (_num(c.get("units"), 0.0) or 0.0))
            for c in candidates if isinstance(c, dict))

    rows = rank_candidates(candidates, index_dips=index_dips,
                           total_value=total_value, weights=weights)
    suggestion = allocate(amount, rows, **alloc_opts)
    plan = plan_status(legs, mf_portfolio=mf_portfolio,
                       equity_ledger=equity_ledger, as_of=as_of)
    targets = _targets_block(rows)

    needs_data = [{"key": r["key"], "name": r["name"],
                   "missing": r["missing_factors"]}
                  for r in rows if r["missing_factors"]]

    return {
        "as_of": (as_of or date.today()).isoformat(),
        "amount": round(_num(amount, 0.0) or 0.0, 2),
        "total_value": round(total_value or 0.0, 2),
        "weights": weights,
        "candidates": rows,
        "suggestion": suggestion,
        "sip_plan": plan,
        "targets": targets,
        "needs_data": needs_data,
        "alerts": _alerts(rows, plan, targets),
        "disclosure": {
            "dip_basis": "funds vs their all-time NAV peak, stocks vs their 52-week high",
            "index_basis": "each holding's benchmark index vs its own 1-year high",
            "target_basis": "% of the whole deployable book (funds + equity)",
            "weights": weights,
            "score_floor": alloc_opts.get("score_floor", SCORE_FLOOR),
            "min_confidence": alloc_opts.get("min_confidence",
                                             MIN_CONFIDENCE_FOR_ALLOCATION),
            "note": "Recording a buy updates this app only. It places no broker order.",
        },
    }


def empty_board(amount: float = 0.0, as_of: date = None) -> dict:
    """A well-formed board with no holdings.

    Built through :func:`build_deploy_board` so the empty payload can never
    drift out of shape from the populated one.
    """
    return build_deploy_board([], amount=amount, as_of=as_of)
