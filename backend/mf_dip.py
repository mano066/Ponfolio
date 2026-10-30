"""
Mutual-fund dip analysis — pure computation layer.

Turns a fund's own transaction history plus its benchmark's measured drawdown
behaviour into: where today's NAV sits inside the range the user has actually
bought at, and what NAV levels would be worth adding at.

Everything here is deterministic and network-free.  ``main.py`` supplies the
fund record (with transactions), the benchmark drawdown from the tape, and the
matching study from :mod:`backtest_engine`.

Design notes
------------
* **The user's own purchase prices are NEVER treated as fair value.**  This is
  the trap the whole panel is built to avoid.  "Below my average" is a fact
  about the user's history, not about the fund being cheap — a fund can be
  below the user's average cost and still be at an expensive level, and a fund
  can be above it and be in a genuine dip.  Purchase statistics are therefore
  reported as CONTEXT, in their own block, and are deliberately kept out of the
  buy-zone arithmetic, which is driven entirely by the benchmark's drawdown.

* **This module now DOES produce a score, and that is a reversal.**  It
  previously refused to, on the grounds that :mod:`deploy_engine` already
  ranked funds and a second score built from overlapping inputs would give the
  dashboard two different answers to the same question.  That reasoning was
  sound while the allocation board sat on the dashboard; it no longer does.
  With the board gone, this is the ONLY fund score on screen, so the conflict
  it guarded against cannot arise — and the alternative, a card showing an
  action with no number behind it, is worse.  The score answers a narrower
  question than the engine's did: *how attractive is adding to this category
  right now*, not *how should I split a given amount*.

* **Buy zones are anchored to the benchmark's measured thresholds, not to
  round numbers.**  A zone is a NAV level derived from the fund's own peak NAV
  and a drawdown depth, and each one carries the backtest evidence for that
  depth on that benchmark — how many episodes, what the forward return was,
  and what the edge over simply buying on a random day was.  A zone whose
  evidence is thin says so.  Without that, "Strong buy zone: ₹412" is a number
  with no argument behind it.

* Weighted average NAV is computed from actual buy transactions, never from a
  stored ``avg_nav`` field, and redemptions are excluded from it: a sale tells
  us nothing about the price the user was willing to pay.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Sequence

# ── Position of today's NAV inside the user's own buying range ────────────
POS_BELOW_LOWEST = "below_lowest"
POS_NEAR_LOWEST = "near_lowest"
POS_BELOW_AVERAGE = "below_average"
POS_ABOVE_AVERAGE = "above_average"
POS_NEAR_HIGHEST = "near_highest"
POS_ABOVE_HIGHEST = "above_highest"
POS_UNKNOWN = "unknown"

POSITION_LABELS = {
    POS_BELOW_LOWEST: "Below everything you have ever paid",
    POS_NEAR_LOWEST: "Near your lowest purchase",
    POS_BELOW_AVERAGE: "Below your weighted average",
    POS_ABOVE_AVERAGE: "Above your weighted average",
    POS_NEAR_HIGHEST: "Near your highest purchase",
    POS_ABOVE_HIGHEST: "Above anything you have paid before",
    POS_UNKNOWN: "No purchase history",
}

# Within this much of the extreme counts as "near" it.
NEAR_EXTREME_TOLERANCE_PCT = 3.0

# The drawdown ladder buy zones are cut on. Matches backtest_engine's candidate
# thresholds so a zone can always be paired with its measured evidence.
ZONE_GOOD_PCT = 10.0
ZONE_STRONG_PCT = 15.0
ZONE_EXTREME_PCT = 20.0

ZONE_GOOD = "good"
ZONE_STRONG = "strong"
ZONE_EXTREME = "extreme"

ZONE_LABELS = {
    ZONE_GOOD: "Good buy zone",
    ZONE_STRONG: "Strong buy zone",
    ZONE_EXTREME: "Extreme buy zone",
}

ZONE_DEPTHS = (
    (ZONE_GOOD, ZONE_GOOD_PCT),
    (ZONE_STRONG, ZONE_STRONG_PCT),
    (ZONE_EXTREME, ZONE_EXTREME_PCT),
)


def _num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _as_date(value):
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════
#  PURCHASE HISTORY
# ══════════════════════════════════════════════════════════════════════════

def purchase_stats(transactions: Sequence[dict] | None) -> dict:
    """
    Lowest, highest and weighted-average NAV the user has actually bought at.

    Redemptions are excluded.  A sale says nothing about the price the user was
    willing to PAY, and letting one into the weighted average would move the
    figure in a direction that has no meaning.

    A transaction missing its NAV, or carrying a non-positive one, is skipped
    and counted in ``skipped`` so the dashboard can say the history is partial
    rather than quietly reporting a range built from half the buys.
    """
    lowest = highest = None
    total_units = 0.0
    total_cost = 0.0
    buys = 0
    skipped = 0
    first_date = last_date = None

    for txn in (transactions or []):
        if not isinstance(txn, dict):
            skipped += 1
            continue
        nav = _num(txn.get("nav"))
        units = _num(txn.get("units"))
        invested = _num(txn.get("invested"))
        redeemed = _num(txn.get("redeemed"))

        # A redemption, however it is encoded.
        if (redeemed or 0) > 0 and not (invested or 0) > 0:
            continue
        if nav is None or nav <= 0 or units is None or units <= 0:
            skipped += 1
            continue

        buys += 1
        lowest = nav if lowest is None else min(lowest, nav)
        highest = nav if highest is None else max(highest, nav)
        total_units += units
        # Prefer the recorded amount; fall back to nav * units when absent.
        total_cost += invested if invested and invested > 0 else nav * units

        when = _as_date(txn.get("date"))
        if when:
            first_date = when if first_date is None else min(first_date, when)
            last_date = when if last_date is None else max(last_date, when)

    weighted = round(total_cost / total_units, 4) if total_units > 0 else None

    return {
        "buys": buys,
        "skipped": skipped,
        "lowest_buy_nav": round(lowest, 4) if lowest is not None else None,
        "highest_buy_nav": round(highest, 4) if highest is not None else None,
        "weighted_avg_nav": weighted,
        "high_low_ratio": (round(highest / lowest, 4)
                           if lowest and highest and lowest > 0 else None),
        "total_units": round(total_units, 4) if total_units else None,
        "total_cost": round(total_cost, 2) if total_cost else None,
        "first_buy": first_date.isoformat() if first_date else None,
        "last_buy": last_date.isoformat() if last_date else None,
    }


def position_in_range(nav, stats: dict) -> dict:
    """
    Where today's NAV sits relative to what the user has paid before.

    Reported purely as context.  See the module docstring: this must never be
    read as a valuation.  The returned ``caution`` line says so explicitly for
    the case most likely to mislead — a NAV below the user's average.
    """
    nav = _num(nav)
    low = stats.get("lowest_buy_nav")
    high = stats.get("highest_buy_nav")
    avg = stats.get("weighted_avg_nav")

    out = {
        "position": POS_UNKNOWN,
        "label": POSITION_LABELS[POS_UNKNOWN],
        "vs_avg_pct": None,
        "vs_lowest_pct": None,
        "vs_highest_pct": None,
        "caution": None,
    }
    if nav is None or nav <= 0 or not stats.get("buys"):
        return out

    if avg:
        out["vs_avg_pct"] = round((nav - avg) / avg * 100, 2)
    if low:
        out["vs_lowest_pct"] = round((nav - low) / low * 100, 2)
    if high:
        out["vs_highest_pct"] = round((nav - high) / high * 100, 2)

    if low is not None and nav < low:
        pos = POS_BELOW_LOWEST
    elif low is not None and out["vs_lowest_pct"] is not None \
            and out["vs_lowest_pct"] <= NEAR_EXTREME_TOLERANCE_PCT:
        pos = POS_NEAR_LOWEST
    elif high is not None and nav > high:
        pos = POS_ABOVE_HIGHEST
    elif high is not None and out["vs_highest_pct"] is not None \
            and out["vs_highest_pct"] >= -NEAR_EXTREME_TOLERANCE_PCT:
        pos = POS_NEAR_HIGHEST
    elif avg is not None and nav < avg:
        pos = POS_BELOW_AVERAGE
    else:
        pos = POS_ABOVE_AVERAGE

    out["position"] = pos
    out["label"] = POSITION_LABELS[pos]
    if pos in (POS_BELOW_LOWEST, POS_NEAR_LOWEST, POS_BELOW_AVERAGE):
        out["caution"] = ("This compares today's NAV with what you paid before, "
                          "which says nothing about whether the fund is cheap. "
                          "Use the benchmark drawdown for that.")
    return out


# ══════════════════════════════════════════════════════════════════════════
#  BUY ZONES
# ══════════════════════════════════════════════════════════════════════════

def _evidence_for(depth_pct: float, study: dict | None,
                  horizon: str = "1y") -> dict:
    """
    What the backtest measured at this drawdown depth on this benchmark.

    Returns explicit unknowns when the study is absent or the depth was never
    tested, so a zone can never imply evidence it does not have.
    """
    blank = {"tested": False, "signals": None, "reliable": None,
             "forward_mean_pct": None, "edge_pp": None, "baseline_mean_pct": None,
             "note": "No backtest available for this benchmark."}
    if not study or study.get("status") != "ok":
        return blank

    row = next((t for t in study.get("thresholds", [])
                if abs(float(t.get("threshold_pct", -1)) - depth_pct) < 1e-9), None)
    if not row:
        return dict(blank, note=f"The {depth_pct:.0f}% depth was not tested.")

    fwd = (row.get("forward") or {}).get(horizon) or {}
    base = (study.get("baseline") or {}).get(horizon) or {}
    edge = ((row.get("edge") or {}).get(horizon) or {}).get("mean_pp")
    reliable = bool(row.get("reliable"))

    if not reliable:
        note = (f"Only {row.get('signals', 0)} separate episode(s) in "
                f"{study.get('years', '?')} years — too few to rely on.")
    elif edge is None:
        note = "Not enough completed windows to measure an edge."
    elif edge > 0:
        note = (f"Beat buying on a random day by {edge:+.1f}pp over "
                f"{horizon} across {row.get('signals')} episodes.")
    else:
        note = (f"Did NOT beat buying on a random day ({edge:+.1f}pp over "
                f"{horizon}, {row.get('signals')} episodes).")

    return {
        "tested": True,
        "signals": row.get("signals"),
        "reliable": reliable,
        "forward_mean_pct": fwd.get("mean_pct"),
        "edge_pp": edge,
        "baseline_mean_pct": base.get("mean_pct"),
        "note": note,
    }


def buy_zones(peak_nav, current_nav, study: dict | None = None) -> list[dict]:
    """
    NAV levels worth adding at, each carrying its own historical evidence.

    Anchored to the fund's own peak NAV and the drawdown ladder, NOT to the
    user's purchase history — see the module docstring for why those must stay
    separate.  Returns an empty list when the peak NAV is unknown, because a
    zone computed without one would be an invented number.
    """
    peak = _num(peak_nav)
    nav = _num(current_nav)
    if peak is None or peak <= 0:
        return []

    zones = []
    for key, depth in ZONE_DEPTHS:
        level = round(peak * (1 - depth / 100.0), 4)
        zones.append({
            "zone": key,
            "label": ZONE_LABELS[key],
            "depth_pct": depth,
            "nav_at_or_below": level,
            "reached": bool(nav is not None and nav <= level),
            "distance_pct": (round((nav - level) / level * 100, 2)
                             if nav is not None and level > 0 else None),
            "evidence": _evidence_for(depth, study),
        })
    return zones


def next_trigger(zones: Sequence[dict], current_nav) -> dict | None:
    """The shallowest zone not yet reached — the level to watch next."""
    nav = _num(current_nav)
    if nav is None:
        return None
    for zone in zones:
        if not zone["reached"]:
            return {
                "zone": zone["zone"],
                "label": zone["label"],
                "nav_at_or_below": zone["nav_at_or_below"],
                "fall_needed_pct": round(
                    (nav - zone["nav_at_or_below"]) / nav * 100, 2) if nav > 0 else None,
            }
    return None


# ══════════════════════════════════════════════════════════════════════════
#  CATEGORY
# ══════════════════════════════════════════════════════════════════════════
# The dashboard groups funds into category tiles ("SMALL CAP -14.6%"), which
# needs a normalised label.  The raw ``category`` field is whatever the source
# supplied — "Dynamic Asset Allocation or Balanced Advantage", "Fund of Funds",
# or the useless "Mutual Fund" — so the scheme NAME is matched too.  Most
# specific first, because "HDFC Gold ETF FoF" contains both "gold" and "fof",
# and "ICICI Nasdaq 100 Index" contains both "nasdaq" and "index".
CAT_LARGE = "Large Cap"
CAT_MID = "Mid Cap"
CAT_SMALL = "Small Cap"
CAT_FLEXI = "Flexi Cap"
CAT_INDEX = "Index"
CAT_INTERNATIONAL = "International"
CAT_GOLD = "Gold"
CAT_SILVER = "Silver"
CAT_HYBRID = "Hybrid"
CAT_DEBT = "Debt"
CAT_SECTORAL = "Sectoral"
CAT_OTHER = "Other"

_CATEGORY_RULES = (
    (("nasdaq", "s&p 500", "us equity", "global", "international",
      "overseas"), CAT_INTERNATIONAL),
    (("gold",), CAT_GOLD),
    (("silver",), CAT_SILVER),
    (("small cap", "smallcap"), CAT_SMALL),
    (("mid cap", "midcap"), CAT_MID),
    (("large cap", "largecap", "bluechip", "blue chip"), CAT_LARGE),
    (("flexi cap", "flexicap", "multi cap", "multicap", "focused",
      "elss", "tax saver", "value", "contra"), CAT_FLEXI),
    (("balanced", "hybrid", "dynamic asset", "asset allocation",
      "arbitrage"), CAT_HYBRID),
    (("debt", "liquid", "gilt", "bond", "money market"), CAT_DEBT),
    (("pharma", "banking", "technology", "infrastructure", "energy",
      "consumption", "psu", "sectoral", "thematic"), CAT_SECTORAL),
    (("index", "nifty", "sensex"), CAT_INDEX),
)


def classify_category(scheme_name: str, raw_category: str = "") -> str:
    """Normalise a fund into one of the dashboard's category tiles."""
    text = "{0} {1}".format(scheme_name or "", raw_category or "").lower()
    for keywords, label in _CATEGORY_RULES:
        for kw in keywords:
            if kw in text:
                return label
    return CAT_OTHER


# ══════════════════════════════════════════════════════════════════════════
#  DIP SCORE
# ══════════════════════════════════════════════════════════════════════════
# Four factors, and why these four.
#
# benchmark_dip leads: the question the card asks is whether the CATEGORY is in
# a dip, and this is the only factor that measures it.
# backtest_support is the factor nothing else in the app has — it asks whether
# a fall this deep has historically been worth buying ON THIS BENCHMARK, and it
# is the whole difference between a number and an argument.
# own_drawdown is largely redundant with the benchmark for an index-like fund,
# but it catches a fund that has fallen harder than its category.
# below_avg_nav carries NO weight. It is a fact about the user's own history,
# not about the fund being cheap — see the module docstring — and scoring it
# rewarded exactly the habit of "buy more because it is below my average",
# which puts the most money into whatever has lost the most. It is still
# computed and returned, as context only.
#
# Every sub-score is ``float | None`` and None means UNKNOWN, never 0. The
# composite renormalises over the factors actually known and reports a
# ``confidence``, so a fund scored on one loud factor cannot outrank a fund
# scored on four.
FACTOR_BENCHMARK_DIP = "benchmark_dip"
FACTOR_BACKTEST = "backtest_support"
FACTOR_OWN_DRAWDOWN = "own_drawdown"
FACTOR_BELOW_AVG_NAV = "below_avg_nav"

FACTOR_KEYS = (FACTOR_BENCHMARK_DIP, FACTOR_BACKTEST,
               FACTOR_OWN_DRAWDOWN, FACTOR_BELOW_AVG_NAV)

FACTOR_LABELS = {
    FACTOR_BENCHMARK_DIP: "Its category is down",
    FACTOR_BACKTEST: "History supports this depth",
    FACTOR_OWN_DRAWDOWN: "Fall from its own NAV peak",
    FACTOR_BELOW_AVG_NAV: "Below your average NAV (context only)",
}

# The old 0.40 / 0.25 / 0.20 split, renormalised once below_avg_nav left.
DEFAULT_WEIGHTS = {
    FACTOR_BENCHMARK_DIP: 0.47,
    FACTOR_BACKTEST: 0.29,
    FACTOR_OWN_DRAWDOWN: 0.24,
    FACTOR_BELOW_AVG_NAV: 0.0,
}

# Below this share of total weight the score rests on one loud factor.
MIN_CONFIDENCE = 45.0

# A category 15% below its high is a full correction on Indian equity, and
# that is where this factor peaks.
#
# It then TAPERS rather than staying pinned at 100, and the reason is a
# contradiction found on the live dashboard: the silver ETF proxy sits 38.8%
# below its high, which market_indices.classify_market_status calls HIGH RISK
# — while this factor, saturating at 15%, scored it a flat 100 and the card
# said "Consider adding". The tape and the card were describing the same
# instrument in opposite terms.
#
# Past PLATEAU_PCT the module genuinely cannot tell a discount from a
# repricing, which is the same reasoning the tape's ladder already carries, so
# the factor gives ground instead of shouting louder. It decays to a floor
# rather than to zero: a 40% fall is still partly an opportunity, just not an
# unqualified one.
BENCH_DIP_MIN_PCT = 2.0
BENCH_DIP_SATURATION_PCT = 15.0
BENCH_DIP_PLATEAU_PCT = 30.0
BENCH_DIP_DECAY_END_PCT = 50.0
BENCH_DIP_DEEP_FLOOR = 30.0
OWN_DD_MIN_PCT = 2.0
OWN_DD_SATURATION_PCT = 20.0
BELOW_AVG_SATURATION_PCT = 12.0

# Edge over buying on a random day, in points, at which the historical case is
# as strong as this factor can report.
BACKTEST_EDGE_SATURATION_PP = 5.0

ACTION_ADD = "add"
ACTION_ATTRACTIVE = "attractive"
ACTION_WATCH = "watch"
ACTION_WAIT = "wait"
ACTION_NONE = "none"

ACTION_LABELS = {
    ACTION_ADD: "Consider adding",
    ACTION_ATTRACTIVE: "Attractive",
    ACTION_WATCH: "Watch",
    ACTION_WAIT: "Wait for a deeper dip",
    ACTION_NONE: "No opportunity",
}

ACTION_EMOJI = {
    ACTION_ADD: "\U0001f7e2",
    ACTION_ATTRACTIVE: "\U0001f7e2",
    ACTION_WATCH: "\U0001f7e1",
    ACTION_WAIT: "\U0001f7e0",
    ACTION_NONE: "\u26aa",
}


def _ramp(value, floor, saturation) -> float:
    if saturation <= floor:
        return 0.0
    return max(0.0, min(1.0, (value - floor) / (saturation - floor))) * 100.0


def score_benchmark_dip(drawdown_pct) -> float | None:
    """
    How far the fund's category has fallen, scored 0-100.

    Rises to full marks at :data:`BENCH_DIP_SATURATION_PCT`, holds to
    :data:`BENCH_DIP_PLATEAU_PCT`, then decays — see the tunables above for
    why a deeper fall stops being a better signal.
    """
    dd = _num(drawdown_pct)
    if dd is None:
        return None
    if dd <= BENCH_DIP_PLATEAU_PCT:
        return round(_ramp(dd, BENCH_DIP_MIN_PCT, BENCH_DIP_SATURATION_PCT), 1)
    span = BENCH_DIP_DECAY_END_PCT - BENCH_DIP_PLATEAU_PCT
    over = min(1.0, (dd - BENCH_DIP_PLATEAU_PCT) / span)
    return round(100.0 - over * (100.0 - BENCH_DIP_DEEP_FLOOR), 1)


def score_own_drawdown(nav, peak_nav) -> float | None:
    nav, peak = _num(nav), _num(peak_nav)
    if nav is None or peak is None or peak <= 0:
        return None
    return round(_ramp((peak - nav) / peak * 100, OWN_DD_MIN_PCT,
                       OWN_DD_SATURATION_PCT), 1)


def score_below_avg_nav(nav, weighted_avg) -> float | None:
    """
    How far below the user's own weighted average the NAV sits.

    Never negative: being above your average is not a reason to sell, and this
    factor must not drag a score down for it.  Returns None with no purchase
    history rather than 0, which would read as "sitting exactly at your
    average" — a different and much more specific claim.
    """
    nav, avg = _num(nav), _num(weighted_avg)
    if nav is None or avg is None or avg <= 0:
        return None
    discount = (avg - nav) / avg * 100
    return round(_ramp(discount, 0.0, BELOW_AVG_SATURATION_PCT), 1)


# A deeper, thinner threshold counts as contradicting the evidence once it has
# at least this many separate episodes; one or two could be a single event.
MIN_CONTRA_SIGNALS = 3
# How much of the support survives a contradiction from deeper episodes.
CONTRADICTED_SUPPORT_FACTOR = 0.5


def backtest_evidence_depth(study: dict | None, benchmark_drawdown_pct,
                            horizon: str = "1y") -> dict | None:
    """The deepest RELIABLE tested depth the benchmark has actually reached.

    The study measures the BENCHMARK's drawdowns, so it has to be read at the
    benchmark's depth. It used to be read at the zone the FUND's own NAV had
    reached, which is a different number: a balanced-advantage fund 5.7% off
    its peak while Nifty sat 13.8% down reached no zone at all, and the ten
    years of Nifty evidence at 10% were never consulted. Every fund on the
    board showed this factor as unknown.

    Deepest reliable rather than deepest reached: a depth with too few
    episodes says nothing either way, while the shallower threshold the fall
    has also crossed has real evidence behind it. Returns None when nothing
    reliable has been crossed.
    """
    depth = _num(benchmark_drawdown_pct)
    if not study or study.get("status") != "ok" or depth is None:
        return None
    crossed = sorted((t for t in study.get("thresholds", [])
                      if _num(t.get("threshold_pct")) is not None
                      and float(t["threshold_pct"]) <= depth),
                     key=lambda t: -float(t["threshold_pct"]))
    def edge_of(row):
        return _num(((row.get("edge") or {}).get(horizon) or {}).get("mean_pp"))

    for i, row in enumerate(crossed):
        edge = edge_of(row)
        if row.get("reliable") and edge is not None:
            # Deeper depths the fall has ALSO crossed, too thin to stand on
            # their own, can still point the other way: gold 17.5% down had
            # +8.7pp at 5% (14 episodes) but -20pp at 10% and 15% (4 and 3).
            # Ignoring that would be reporting only the flattering half.
            contra = None
            for deeper in crossed[:i]:
                d_edge = edge_of(deeper)
                if (d_edge is not None
                        and int(deeper.get("signals") or 0) >= MIN_CONTRA_SIGNALS
                        and (d_edge < 0) != (edge < 0)):
                    contra = {"depth_pct": float(deeper["threshold_pct"]),
                              "signals": deeper.get("signals"),
                              "edge_pp": d_edge}
                    break
            return {"depth_pct": float(row["threshold_pct"]),
                    "signals": row.get("signals"),
                    "edge_pp": edge, "horizon": horizon,
                    "contradicted_by": contra}
    return None


def score_backtest_support(zones: Sequence[dict] | None = None, *,
                           study: dict | None = None,
                           benchmark_drawdown_pct=None) -> float | None:
    """
    Whether history backs buying at the depth the benchmark has reached.

    See :func:`backtest_evidence_depth` for which depth is read. ``zones`` is
    the fallback when no study is passed, for callers that only hold zones.

    "Too few episodes" returns None, not 0.  That distinction is the point of
    the factor: an absence of evidence is not evidence that the depth is bad,
    and scoring it as bad would penalise exactly the rare deep corrections the
    dashboard exists to catch.
    """
    if study is not None:
        ev = backtest_evidence_depth(study, benchmark_drawdown_pct)
        if ev is None:
            return None
        support = max(0.0, min(1.0, ev["edge_pp"] / BACKTEST_EDGE_SATURATION_PP))
        if ev.get("contradicted_by"):
            support *= CONTRADICTED_SUPPORT_FACTOR
        return round(support * 100.0, 1)
    else:
        reached = [z for z in (zones or []) if z.get("reached")]
        if not reached:
            return None
        deepest = max(reached, key=lambda z: z.get("depth_pct", 0))
        zev = deepest.get("evidence") or {}
        if not zev.get("tested") or not zev.get("reliable"):
            return None
        edge = _num(zev.get("edge_pp"))
        if edge is None:
            return None
    return round(max(0.0, min(1.0, edge / BACKTEST_EDGE_SATURATION_PP)) * 100.0, 1)


def classify_action(score: float | None, confidence: float) -> str:
    """Turn a score into one instruction, capped when confidence is thin."""
    if score is None or confidence < MIN_CONFIDENCE:
        return ACTION_WATCH
    if score >= 80:
        return ACTION_ADD
    if score >= 65:
        return ACTION_ATTRACTIVE
    if score >= 50:
        return ACTION_WATCH
    if score >= 35:
        return ACTION_WAIT
    return ACTION_NONE


def build_reasons(*, category, benchmark_label, benchmark_drawdown_pct,
                  position: dict, zones: Sequence[dict] | None,
                  own_dd_pct=None, evidence: dict | None = None) -> list[str]:
    """
    The two or three lines the card shows beneath its score.

    A bare "82" is not something anyone should act on. Each line is a fact the
    user can check, in the order that actually drove the number — and the
    backtest line is allowed to argue AGAINST the score it sits under, because
    a card that can only agree with itself is decoration.
    """
    out: list[str] = []
    dd = _num(benchmark_drawdown_pct)
    if dd is not None and dd >= BENCH_DIP_MIN_PCT:
        out.append("{0} is {1:.1f}% off its high".format(
            benchmark_label or category, dd))

    reached = [z for z in (zones or []) if z.get("reached")]
    if evidence and _num(evidence.get("edge_pp")) is not None:
        # The line matches the factor: read at the benchmark's depth.
        edge = evidence["edge_pp"]
        verb = "favoured" if edge > 0 else "did NOT favour"
        line = ("History {0} buying {1} at {2:.0f}% down "
                "({3:+.1f}pp vs any day, {4} episodes)".format(
                    verb, benchmark_label or category,
                    evidence["depth_pct"], edge, evidence.get("signals")))
        contra = evidence.get("contradicted_by")
        if contra:
            line += " — but {0} deeper episodes at {1:.0f}% went {2:+.1f}pp".format(
                contra.get("signals"), contra["depth_pct"], contra["edge_pp"])
        out.append(line)
    elif reached:
        deepest = max(reached, key=lambda z: z.get("depth_pct", 0))
        ev = deepest.get("evidence") or {}
        edge = _num(ev.get("edge_pp"))
        if ev.get("reliable") and edge is not None:
            if edge > 0:
                out.append("History favoured this depth "
                           "(+{0:.1f}pp vs any day)".format(edge))
            else:
                out.append("History did NOT favour this depth "
                           "({0:+.1f}pp vs any day)".format(edge))
        elif ev.get("tested"):
            out.append("Too few past episodes at this depth to rely on")

    # "NAV is X% below your average" used to be a reason here. Your own
    # average cost says nothing about whether the fund is a good buy today, so
    # it is no longer offered as one.
    own = _num(own_dd_pct)
    if not out and own is not None and own >= OWN_DD_MIN_PCT:
        out.append("NAV is {0:.1f}% below its own peak".format(own))
    if not out:
        out.append("Nothing here is meaningfully down")
    return out[:3]


def analyse_fund(fund: dict, *, peak_nav=None, benchmark=None,
                 benchmark_label=None, benchmark_drawdown_pct=None,
                 study: dict | None = None) -> dict:
    """
    Full dip context for one fund.

    Produces the whole card: a 0-100 dip score with its confidence, one
    action, the two or three reasons behind it, the user's own buying range,
    the NAV levels worth acting at, and what a decade of history says about
    each.  See the module docstring for why a score lives here now when it
    deliberately did not before.
    """
    nav = _num(fund.get("nav"))
    stats = purchase_stats(fund.get("transactions"))

    # Prefer the fund's real all-time NAV peak. Falling back to the user's
    # highest purchase is weaker, and it can be OUTRIGHT WRONG when today's NAV
    # is above anything they ever paid — a "peak" sitting below the current
    # price is not a peak, and zones cut from it would sit below today's level
    # while claiming to describe a fall. Taking the higher of the two keeps the
    # anchor coherent; peak_is_purchase_high tells the UI not to oversell it.
    anchor = _num(peak_nav)
    fallback = anchor is None
    if fallback:
        candidates = [v for v in (stats.get("highest_buy_nav"), nav)
                      if v is not None]
        anchor = max(candidates) if candidates else None

    zones = buy_zones(anchor, nav, study)

    own_dd_pct = None
    if anchor and nav is not None and anchor > 0:
        own_dd_pct = round((anchor - nav) / anchor * 100, 2)

    position = position_in_range(nav, stats)
    category = classify_category(fund.get("scheme_name") or "",
                                 fund.get("category") or "")

    factors = {
        FACTOR_BENCHMARK_DIP: score_benchmark_dip(benchmark_drawdown_pct),
        FACTOR_BACKTEST: score_backtest_support(
            zones, study=study, benchmark_drawdown_pct=benchmark_drawdown_pct),
        FACTOR_OWN_DRAWDOWN: score_own_drawdown(nav, anchor),
        FACTOR_BELOW_AVG_NAV: score_below_avg_nav(
            nav, stats.get("weighted_avg_nav")),
    }
    known = {k: v for k, v in factors.items() if v is not None}
    total_weight = sum(DEFAULT_WEIGHTS[k] for k in known)
    score = (round(sum(known[k] * DEFAULT_WEIGHTS[k] for k in known)
                   / total_weight, 1) if total_weight > 0 else None)
    confidence = round(total_weight * 100.0, 1)
    action = classify_action(score, confidence)

    return {
        "scheme_name": fund.get("scheme_name"),
        "category": category,
        "raw_category": fund.get("category") or "",
        "factors": factors,
        "factor_labels": FACTOR_LABELS,
        "weights": DEFAULT_WEIGHTS,
        "score": score,
        "confidence": confidence,
        "low_confidence": confidence < MIN_CONFIDENCE,
        "action": action,
        "action_label": ACTION_LABELS[action],
        "action_emoji": ACTION_EMOJI[action],
        "reasons": build_reasons(
            category=category, benchmark_label=benchmark_label,
            benchmark_drawdown_pct=benchmark_drawdown_pct,
            position=position, zones=zones, own_dd_pct=own_dd_pct,
            evidence=backtest_evidence_depth(study, benchmark_drawdown_pct)),
        "own_drawdown_pct": own_dd_pct,
        # True when the category has fallen far enough that a discount and a
        # repricing look the same from here. The card must show this beside
        # the score, not instead of it.
        "deep_fall_risk": (_num(benchmark_drawdown_pct) is not None
                           and _num(benchmark_drawdown_pct)
                           >= BENCH_DIP_PLATEAU_PCT),
        "nav": nav,
        "units": _num(fund.get("units")),
        "invested": _num(fund.get("invested")),
        "current_value": _num(fund.get("current_value")),
        "return_pct": _num(fund.get("return_pct")),
        "benchmark": benchmark,
        "benchmark_label": benchmark_label,
        "benchmark_drawdown_pct": _num(benchmark_drawdown_pct),
        "purchase": stats,
        "position": position,
        "peak_nav": anchor,
        # True when the peak is only the user's own highest purchase rather
        # than the fund's actual NAV peak — a weaker anchor, and the UI must
        # not present zones built on it as though they were the real thing.
        "peak_is_purchase_high": fallback,
        "zones": zones,
        "next_trigger": next_trigger(zones, nav),
        # Which measured depth the backtest factor was read at, so the card
        # can say "history at 10% on Nifty 50" rather than imply the
        # benchmark's exact current depth was tested.
        "backtest_evidence": backtest_evidence_depth(
            study, benchmark_drawdown_pct),
        "backtest_status": (study or {}).get("status"),
        "backtest_years": (study or {}).get("years"),
    }


# Board order: what to DO first, then how strongly. The API used to sort by
# benchmark depth, so a fund whose category had crashed led the list even when
# its score said "watch".
ACTION_RANK = {
    ACTION_ADD: 0,
    ACTION_ATTRACTIVE: 1,
    ACTION_WATCH: 2,
    ACTION_WAIT: 3,
    ACTION_NONE: 4,
}


def board_sort_key(row: dict):
    """Sort key for the fund board: confident rows first, then action, then score.

    A "watch" that is only a watch because the inputs are missing must not
    outrank a measured "wait".
    """
    score = _num(row.get("score"))
    return (bool(row.get("low_confidence")),
            ACTION_RANK.get(row.get("action"), 5),
            -(score if score is not None else -1))
