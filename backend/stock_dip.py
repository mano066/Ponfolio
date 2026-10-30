"""
Stock dip analysis — pure computation layer.

Answers the question a mutual-fund dip score must never be asked to answer:
*this share is 20% down — is that the market, or is it the company?*

Everything here is deterministic and network-free.  ``main.py`` supplies the
already-fetched facts (price history summary, yfinance ``info`` fields,
benchmark drawdown, recent headlines) and calls :func:`analyse_stock`.

Design notes
------------
* **The reason-for-fall verdict is driven by EXCESS DRAWDOWN, not by news.**
  A stock 20% below its high while its sector index is 18% below its own high
  has told us almost nothing about itself.  The same stock falling 20% while
  the sector is flat has told us a great deal.  That comparison is a
  measurement — available for every holding, every day, with no parsing and no
  vendor — and it is the backbone of the classification.  Headlines only adjust
  a verdict the numbers already reached, because headline text is the least
  reliable input in the whole system: sparse, duplicated, occasionally about a
  different company with a similar name, and trivially skewed by one
  alarmist stringer.

* **Every sub-score is ``float | None``, and ``None`` means UNKNOWN.**  Same
  rule as :mod:`deploy_engine`, for the same reason.  A stock whose fundamentals
  did not download must not score as though its fundamentals were bad.  The
  composite renormalises over the factors actually known and reports a
  ``confidence`` alongside, so a stock rated on drawdown alone cannot outrank
  one rated on all five.

* **Valuation is scored against the sector and against absolutes, never
  against the stock's own history.**  A stock's five-year average P/E requires
  a historical EPS series, and no feed in use carries one.  Applying today's
  EPS to old prices would produce a number that looks like a historical P/E and
  is not one.  The field is reported unavailable and dropped from the
  composite — see :data:`VALUATION_HISTORY_UNAVAILABLE`.

* **A high dip score is never on its own a buy.**  ``averaging_blocked`` is a
  hard gate set by the reason-for-fall verdict and the deterioration flags; it
  overrides the score, because the entire failure mode this module exists to
  prevent is a cheap-looking price on a business that is coming apart.
"""

from __future__ import annotations

import re
from typing import Sequence

import mf_dip

# ══════════════════════════════════════════════════════════════════════════
#  REASON FOR FALL
# ══════════════════════════════════════════════════════════════════════════

REASON_MARKET_WIDE = "market_wide"
REASON_COMPANY_SOFT = "company_soft"
REASON_UNCERTAIN = "uncertain"
REASON_DETERIORATION = "deterioration"
REASON_NOT_FALLING = "not_falling"
REASON_CORPORATE_ACTION = "corporate_action"
REASON_UNKNOWN = "unknown"

REASON_LABELS = {
    REASON_MARKET_WIDE: "Falling with its market",
    REASON_COMPANY_SOFT: "Company-specific, no damage visible",
    REASON_UNCERTAIN: "Company-specific, cause unclear",
    REASON_DETERIORATION: "Fundamentals deteriorating",
    REASON_NOT_FALLING: "Not meaningfully down",
    REASON_CORPORATE_ACTION: "Corporate action — figures not like-for-like",
    REASON_UNKNOWN: "Not enough information",
}

REASON_EMOJI = {
    REASON_MARKET_WIDE: "\U0001f7e2",
    REASON_COMPANY_SOFT: "\U0001f7e1",
    REASON_UNCERTAIN: "\U0001f7e0",
    REASON_DETERIORATION: "\U0001f534",
    REASON_NOT_FALLING: "⚪",
    REASON_CORPORATE_ACTION: "⚠️",
    REASON_UNKNOWN: "—",
}

# Below this drawdown there is no fall worth explaining, and the excess-vs-
# benchmark ratio gets noisy enough to produce nonsense verdicts.
MIN_DRAWDOWN_TO_CLASSIFY_PCT = 5.0

# Excess drawdown over the benchmark, in percentage points.  Under the first
# figure the stock is simply moving with its market.  Over the second, the
# market plainly is not the explanation.
EXCESS_MARKET_WIDE_PP = 4.0
EXCESS_COMPANY_SPECIFIC_PP = 15.0

# ── Headline severity ─────────────────────────────────────────────────────
# These adjust a verdict the numbers already reached; they never set one alone.
# Deliberately narrow: words that describe a change in the BUSINESS or its
# governance, not words that merely sound bad in a market report.  "Falls",
# "plunges", "drops" are excluded on purpose — they describe the price move we
# are already measuring, and matching them would let the same fact count twice.
SEVERE_HEADLINE_PATTERNS = (
    r"\bfraud\b", r"\bscam\b", r"\bprobe\b", r"\binvestigat", r"\braid\b",
    r"\bauditor (?:resign|quit)", r"\bqualified opinion\b",
    r"\bdefault(?:s|ed)?\b", r"\binsolvenc", r"\bbankrupt",
    r"\bdowngrade[sd]?\b", r"\bguidance cut\b", r"\bcuts? guidance\b",
    r"\bprofit warning\b", r"\bgoverna\w+ (?:concern|issue|lapse)",
    r"\bpledge[sd]?\b.{0,20}\bshare", r"\bpromoter\b.{0,20}\bsell",
    r"\bsebi\b.{0,30}\b(?:order|notice|ban)", r"\bresign(?:s|ed)?\b",
    r"\bfire[sd]?\b.{0,15}\bceo\b", r"\bcfo\b.{0,15}\b(?:exit|quit|resign)",
)

# Words that describe a fall the market is doing TO the stock rather than
# something the company did. Their presence supports a market-wide reading.
MARKET_HEADLINE_PATTERNS = (
    r"\bsector\b", r"\bnifty\b", r"\bsensex\b", r"\bmarket[- ]wide\b",
    r"\bselloff\b", r"\bsell[- ]off\b", r"\bcorrection\b", r"\bfii\b",
    r"\bglobal cues\b", r"\bbroader market\b",
)

_SEVERE_RE = re.compile("|".join(SEVERE_HEADLINE_PATTERNS), re.I)
_MARKET_RE = re.compile("|".join(MARKET_HEADLINE_PATTERNS), re.I)


def headline_signal(headlines: Sequence[str] | None) -> dict:
    """
    Classify recent headlines into severe / market-flavoured / neither.

    Returns counts and the matched strings so the dashboard can show the user
    exactly which headline drove an adjustment.  An unexplained verdict is
    worth very little, and an unexplained NEGATIVE verdict is worth less than
    nothing — the user needs to be able to check it against reality.
    """
    severe: list[str] = []
    market: list[str] = []
    for line in (headlines or []):
        text = str(line or "").strip()
        if not text:
            continue
        if _SEVERE_RE.search(text):
            severe.append(text)
        elif _MARKET_RE.search(text):
            market.append(text)
    return {
        "severe_count": len(severe),
        "market_count": len(market),
        "severe_headlines": severe[:5],
        "market_headlines": market[:5],
        "checked": len([h for h in (headlines or []) if str(h or "").strip()]),
    }


# ── Deterioration materiality ─────────────────────────────────────────────
# A flag has to clear a materiality bar before it means anything. A revenue
# move of -0.3% year on year is arithmetically a decline, and completely
# meaningless. Blocking a holding on that is how a
# safety gate turns into noise the user learns to ignore, which is worse than
# not having one.
REVENUE_DECLINE_MILD_PCT = -5.0
EARNINGS_DECLINE_MILD_PCT = -10.0
EARNINGS_COLLAPSE_PCT = -25.0
DEBT_EQUITY_MILD = 200.0        # 2x, as a yfinance percentage
DEBT_EQUITY_SEVERE = 300.0      # 3x

SEVERITY_SEVERE = "severe"
SEVERITY_MILD = "mild"


def deterioration_flags(f: dict | None) -> list[dict]:
    """
    Hard, checkable signs that the business itself is weakening.

    Each flag carries a severity, because the flags are not equal.  A company
    losing money at the net line is in a different category from one whose free
    cash flow went negative for a year — the second is routine in a capex
    cycle and, on its own, says nothing.  :func:`blocks_averaging` applies the
    rule; this function only reports what is true.

    Only facts that are unambiguous in isolation appear here.  A high P/E does
    not: an expensive stock is a valuation problem, not a deteriorating one,
    and conflating the two is how a perfectly healthy compounder ends up
    flagged as a falling knife.
    """
    out: list[dict] = []
    f = f or {}

    def num(key):
        v = f.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def flag(text, severity):
        out.append({"text": text, "severity": severity})

    margin = num("profit_margin_pct")
    if margin is not None and margin < 0:
        flag("Loss-making at the net level", SEVERITY_SEVERE)

    roe = num("roe_pct")
    if roe is not None and roe < 0:
        flag(f"Return on equity negative ({roe:.1f}%)", SEVERITY_SEVERE)

    eps = num("earnings_growth_pct")
    if eps is not None:
        if eps <= EARNINGS_COLLAPSE_PCT:
            flag(f"Earnings down sharply ({eps:.1f}%)", SEVERITY_SEVERE)
        elif eps <= EARNINGS_DECLINE_MILD_PCT:
            flag(f"Earnings shrinking ({eps:.1f}%)", SEVERITY_MILD)

    de = num("debt_to_equity")
    # yfinance reports debtToEquity as a percentage (200 == 2.0x).
    if de is not None:
        if de > DEBT_EQUITY_SEVERE:
            flag(f"Debt/equity above 3x ({de / 100:.1f}x)", SEVERITY_SEVERE)
        elif de > DEBT_EQUITY_MILD:
            flag(f"Debt/equity above 2x ({de / 100:.1f}x)", SEVERITY_MILD)

    rev = num("revenue_growth_pct")
    if rev is not None and rev <= REVENUE_DECLINE_MILD_PCT:
        flag(f"Revenue shrinking ({rev:.1f}%)", SEVERITY_MILD)

    fcf = num("free_cashflow")
    if fcf is not None and fcf < 0:
        # Mild on purpose: a single year of negative free cash flow is routine
        # in a capex cycle and is not evidence of a failing business.
        flag("Free cash flow negative", SEVERITY_MILD)

    return out


def blocks_averaging(flags: Sequence[dict] | None) -> bool:
    """
    Whether the flags are together strong enough to refuse averaging down.

    One severe flag is enough.  One mild flag is not — a lone soft reading is a
    thing to watch, and a gate that fires on every one of them stops being
    information.  Two mild flags pointing the same way are.
    """
    flags = flags or []
    severe = sum(1 for f in flags if f.get("severity") == SEVERITY_SEVERE)
    mild = sum(1 for f in flags if f.get("severity") == SEVERITY_MILD)
    return severe >= 1 or mild >= 2


def flag_texts(flags: Sequence[dict] | None) -> list[str]:
    """Plain strings for display."""
    return [str(f.get("text", "")) for f in (flags or []) if f.get("text")]


def classify_reason(drawdown_pct: float | None,
                    benchmark_drawdown_pct: float | None,
                    fundamentals: dict | None = None,
                    headlines: Sequence[str] | None = None,
                    corporate_action: bool = False) -> dict:
    """
    Decide WHY a stock is down: the market, or the company.

    The ladder, in order of authority:

    1. Not meaningfully down -> nothing to explain.
    2. Deterioration flags present -> the company, regardless of the tape.
       A business with shrinking earnings and negative cash flow is not
       rescued by the observation that its sector also fell.
    3. Excess drawdown under :data:`EXCESS_MARKET_WIDE_PP` -> the market.
    4. Excess over :data:`EXCESS_COMPANY_SPECIFIC_PP`, or a severe headline ->
       company-specific and material.
    5. Otherwise company-specific but unexplained.

    Benchmark unknown collapses the verdict to ``unknown`` rather than letting
    the stock's raw drawdown masquerade as excess drawdown — without the
    benchmark there is no excess to measure, and guessing here would defeat the
    entire purpose of the module.
    """
    flags = deterioration_flags(fundamentals)
    news = headline_signal(headlines)
    excess = None
    if drawdown_pct is not None and benchmark_drawdown_pct is not None:
        excess = round(drawdown_pct - benchmark_drawdown_pct, 2)

    def result(reason, why):
        return {
            "reason": reason,
            "label": REASON_LABELS[reason],
            "emoji": REASON_EMOJI[reason],
            "excess_drawdown_pp": excess,
            "deterioration_flags": flag_texts(flags),
            "deterioration_detail": flags,
            "news": news,
            "why": why,
        }

    # Checked before everything else, because a demerger or a split makes BOTH
    # the drawdown and the year-on-year fundamentals meaningless in the same
    # stroke. A stock that fell 65% in one day when its business was spun out
    # has not fallen 65%, and its revenue did not "shrink" — the demerged
    # entity simply left the accounts. Reading either as a verdict on the
    # company is the worst kind of confident wrongness, so this refuses to
    # judge at all and says why.
    if corporate_action:
        return result(REASON_CORPORATE_ACTION,
                      "A split, demerger or similar action in the last year "
                      "means the price history and the year-on-year figures "
                      "are not comparing like with like. Check this one by "
                      "hand rather than trusting the drawdown.")

    # Deterioration is checked BEFORE anything price-shaped, because it is a
    # fact about the business and does not depend on the quote arriving. A
    # company with shrinking revenue and negative cash flow must not escape the
    # block merely because its price failed to download — "we could not price
    # it" is not a reason to soften "do not average into this".
    if blocks_averaging(flags):
        return result(REASON_DETERIORATION,
                      "The business itself is weakening: "
                      + "; ".join(flag_texts(flags)) + ".")

    if drawdown_pct is None:
        return result(REASON_UNKNOWN, "No price history for this holding.")

    if drawdown_pct < MIN_DRAWDOWN_TO_CLASSIFY_PCT:
        return result(REASON_NOT_FALLING,
                      f"Only {drawdown_pct:.1f}% below its high — nothing to explain.")

    if excess is None:
        return result(REASON_UNKNOWN,
                      "No benchmark available, so the fall cannot be separated "
                      "from its market.")

    if excess <= EXCESS_MARKET_WIDE_PP:
        if news["severe_count"]:
            return result(REASON_UNCERTAIN,
                          f"Down roughly in line with its market "
                          f"({excess:+.1f}pp), but recent news is serious.")
        return result(REASON_MARKET_WIDE,
                      f"Down {drawdown_pct:.1f}% while its benchmark is down "
                      f"{benchmark_drawdown_pct:.1f}% — a market move, not a "
                      f"company one ({excess:+.1f}pp of difference).")

    if excess >= EXCESS_COMPANY_SPECIFIC_PP or news["severe_count"]:
        detail = (f"{excess:+.1f}pp worse than its benchmark")
        if news["severe_count"]:
            detail += f", with {news['severe_count']} serious headline(s)"
        return result(REASON_UNCERTAIN,
                      f"This is the company, not the market: {detail}. No "
                      f"deterioration visible in the numbers yet, so the cause "
                      f"needs checking before adding.")

    return result(REASON_COMPANY_SOFT,
                  f"{excess:+.1f}pp worse than its benchmark, but the "
                  f"fundamentals show no damage.")


# ══════════════════════════════════════════════════════════════════════════
#  SUB-SCORES
# ══════════════════════════════════════════════════════════════════════════

FACTOR_DRAWDOWN = "drawdown"
FACTOR_VALUATION = "valuation"
FACTOR_FUNDAMENTAL = "fundamental"
FACTOR_GROWTH = "growth"
FACTOR_NEWS = "news"

FACTOR_KEYS = (FACTOR_DRAWDOWN, FACTOR_VALUATION, FACTOR_FUNDAMENTAL,
               FACTOR_GROWTH, FACTOR_NEWS)

FACTOR_LABELS = {
    FACTOR_DRAWDOWN: "Price fall from its high",
    FACTOR_VALUATION: "Valuation",
    FACTOR_FUNDAMENTAL: "Balance sheet & returns",
    FACTOR_GROWTH: "Growth",
    FACTOR_NEWS: "News tone",
}

# The spec's weights. drawdown/valuation/fundamental carry equal authority so
# that no single one can carry a recommendation; news is smallest because it is
# the least reliable input.
DEFAULT_WEIGHTS = {
    FACTOR_DRAWDOWN: 0.25,
    FACTOR_VALUATION: 0.25,
    FACTOR_FUNDAMENTAL: 0.25,
    FACTOR_GROWTH: 0.15,
    FACTOR_NEWS: 0.10,
}

# A stock scored on drawdown alone (weight .25 -> confidence 25) can hit 100 and
# mean nothing. 45 is the point at which at least two substantive factors speak.
MIN_CONFIDENCE = 45.0

# Drawdown scoring. Past 40% the fall stops being a discount and starts being
# information, and this factor cannot tell which — the reason-for-fall verdict
# and the deterioration gate handle that.
DRAWDOWN_MIN_PCT = 5.0
DRAWDOWN_SATURATION_PCT = 40.0

# Valuation is scored against the SECTOR, which is the only comparison a feed
# can actually supply. Cheap is capped: a P/E at a quarter of the sector's is
# more often a warning than a bargain.
PE_DISCOUNT_SATURATION = 0.50      # half the sector P/E == full marks
PE_PREMIUM_ZERO = 1.50             # 50% above sector == zero marks

VALUATION_HISTORY_UNAVAILABLE = (
    "A stock's own 5-year average P/E needs a historical EPS series, which no "
    "feed in use carries. Valuation here is measured against the sector and "
    "against absolute levels, not against the stock's own past."
)


def _num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _ramp(value, floor, saturation) -> float:
    """Map a magnitude onto 0-100 through a dead-band and a ceiling."""
    if saturation <= floor:
        return 0.0
    return max(0.0, min(1.0, (value - floor) / (saturation - floor))) * 100.0


def score_drawdown(drawdown_pct) -> float | None:
    dd = _num(drawdown_pct)
    if dd is None:
        return None
    return round(_ramp(dd, DRAWDOWN_MIN_PCT, DRAWDOWN_SATURATION_PCT), 1)


def score_valuation(pe, sector_pe, pb=None) -> float | None:
    """
    Cheapness against the sector, with P/B as a fallback.

    Returns None when neither comparison can be made — an unknown valuation
    must not read as an average one.  A negative P/E (loss-making) scores 0
    rather than None: that is a known fact about the company, not missing data.
    """
    pe, sector_pe, pb = _num(pe), _num(sector_pe), _num(pb)

    if pe is not None and pe <= 0:
        return 0.0

    if pe is not None and sector_pe is not None and sector_pe > 0:
        ratio = pe / sector_pe
        if ratio <= PE_DISCOUNT_SATURATION:
            return 100.0
        if ratio >= PE_PREMIUM_ZERO:
            return 0.0
        span = PE_PREMIUM_ZERO - PE_DISCOUNT_SATURATION
        return round((PE_PREMIUM_ZERO - ratio) / span * 100.0, 1)

    # No sector comparison available. P/B is a weak but real absolute anchor:
    # under 1x is cheap on assets, over 8x is not cheap on any reading.
    if pb is not None and pb > 0:
        if pb <= 1.0:
            return 100.0
        if pb >= 8.0:
            return 0.0
        return round((8.0 - pb) / 7.0 * 100.0, 1)

    return None


def score_fundamental(f: dict | None) -> float | None:
    """
    Balance-sheet and returns quality, 0-100.

    Averaged over whichever of the four components are known, so a stock
    missing its cash-flow line is scored on the other three rather than
    penalised for the gap.  None only when nothing at all is known.
    """
    f = f or {}
    parts: list[float] = []

    roe = _num(f.get("roe_pct"))
    if roe is not None:
        # 0% -> 0, 25%+ -> 100.
        parts.append(_ramp(roe, 0.0, 25.0))

    de = _num(f.get("debt_to_equity"))
    if de is not None:
        # yfinance reports a percentage: 0 -> 100 marks, 200 (2x) -> 0 marks.
        parts.append(max(0.0, min(1.0, (200.0 - de) / 200.0)) * 100.0)

    margin = _num(f.get("profit_margin_pct"))
    if margin is not None:
        parts.append(_ramp(margin, 0.0, 20.0))

    fcf = _num(f.get("free_cashflow"))
    if fcf is not None:
        # Binary by design: the sign is the fact worth scoring, and the
        # magnitude is not comparable across companies of different sizes.
        parts.append(100.0 if fcf > 0 else 0.0)

    if not parts:
        return None
    return round(sum(parts) / len(parts), 1)


def score_growth(f: dict | None) -> float | None:
    """Revenue and earnings growth, 0-100. 0% -> 0 marks, 20%+ -> full."""
    f = f or {}
    parts: list[float] = []
    for key in ("revenue_growth_pct", "earnings_growth_pct"):
        v = _num(f.get(key))
        if v is not None:
            parts.append(_ramp(v, 0.0, 20.0))
    if not parts:
        return None
    return round(sum(parts) / len(parts), 1)


def score_news(reason: dict | None) -> float | None:
    """
    News tone, 0-100, derived from the reason-for-fall verdict.

    Deliberately NOT an independent sentiment read: the verdict already
    weighed the headlines against the price evidence, and scoring the same
    headlines again on their own would double-count the weakest input in the
    system.  ``None`` when no headlines were checked at all — silence is not
    good news.
    """
    if not reason:
        return None
    if not (reason.get("news") or {}).get("checked"):
        return None
    return {
        REASON_MARKET_WIDE: 100.0,
        REASON_NOT_FALLING: 70.0,
        REASON_COMPANY_SOFT: 60.0,
        REASON_UNCERTAIN: 25.0,
        REASON_DETERIORATION: 0.0,
        # Not a judgement on the news — the verdict simply is not about news.
        REASON_CORPORATE_ACTION: None,
    }.get(reason.get("reason"))


# ══════════════════════════════════════════════════════════════════════════
#  COMPOSITE
# ══════════════════════════════════════════════════════════════════════════

ACTION_ACCUMULATE = "accumulate"
ACTION_CONSIDER = "consider"
ACTION_WATCH = "watch"
ACTION_AVOID = "avoid"
ACTION_DO_NOT_AVERAGE = "do_not_average"

ACTION_LABELS = {
    ACTION_ACCUMULATE: "Strong accumulation candidate",
    ACTION_CONSIDER: "Consider accumulating",
    ACTION_WATCH: "Watch / small buy only",
    ACTION_AVOID: "Avoid averaging for now",
    ACTION_DO_NOT_AVERAGE: "Do not average down",
}

ACTION_EMOJI = {
    ACTION_ACCUMULATE: "\U0001f7e2",
    ACTION_CONSIDER: "\U0001f7e2",
    ACTION_WATCH: "\U0001f7e1",
    ACTION_AVOID: "\U0001f7e0",
    ACTION_DO_NOT_AVERAGE: "\U0001f534",
}


def classify_action(score: float | None, *, blocked: bool,
                    confidence: float, drawdown_known: bool = True,
                    cause_unclear: bool = False,
                    not_falling: bool = False) -> str:
    """
    Turn a score into an instruction.

    The block gate is checked FIRST and cannot be outvoted.  A deteriorating
    business can still post a high dip score — a collapsing price makes the
    drawdown factor scream and can drag the valuation factor up with it — and
    that combination is precisely the falling knife this module exists to
    refuse.

    ``drawdown_known`` is the second gate, and it is not optional.  Strong
    fundamentals alone are enough to clear the confidence bar, which means a
    holding whose PRICE never downloaded can otherwise arrive at "accumulate"
    on growth and balance-sheet marks — a dip recommendation for something
    whose dip is unmeasured.  A panel about falls must not advise buying when
    it does not know whether the thing has fallen.
    """
    if blocked:
        return ACTION_DO_NOT_AVERAGE
    if score is None or confidence < MIN_CONFIDENCE or not drawdown_known:
        return ACTION_WATCH
    # An "uncertain" verdict means the fall is the company's own and we cannot
    # say why. That is not a reason to refuse — nothing is actually broken —
    # but it is emphatically not a reason to call something a strong
    # accumulation candidate. The verdict's own text says the cause needs
    # checking before adding, and the instruction beside it must not contradict
    # that: a live holding down 22.8pp more than its sector with clean
    # fundamentals was reaching "accumulate" on the strength of the score alone.
    if cause_unclear:
        return ACTION_WATCH
    # This panel answers "where should I buy a DIP". A holding that has not
    # fallen has no dip to buy, however good it looks otherwise — the drawdown
    # factor sits at zero and the score is carried entirely by valuation and
    # fundamentals. A live holding 0.4% below its high reached the master bar
    # as a BUY on exactly that arithmetic, which is a perfectly sound quality
    # score answering a question nobody asked here.
    if not_falling:
        return ACTION_WATCH
    if score >= 80:
        return ACTION_ACCUMULATE
    if score >= 65:
        return ACTION_CONSIDER
    if score >= 50:
        return ACTION_WATCH
    return ACTION_AVOID


# ══════════════════════════════════════════════════════════════════════════
#  CARD STATUS CHIPS
# ══════════════════════════════════════════════════════════════════════════
# The card shows three one-word verdicts rather than a wall of ratios. Each is
# derived from a sub-score that already exists, so a chip can never disagree
# with the number it was computed from.
#
# Every one of these can return an "unknown" state. That is not a formality:
# for several holdings in a real portfolio the fundamentals simply do not
# download, and a chip reading "STABLE" for a company nobody measured would be
# the single most misleading thing on the screen.

HEALTH_STRONG = "strong"
HEALTH_STABLE = "stable"
HEALTH_WEAKENING = "weakening"
HEALTH_DETERIORATING = "deteriorating"
HEALTH_UNKNOWN = "unknown"

HEALTH_LABELS = {
    HEALTH_STRONG: "Strong",
    HEALTH_STABLE: "Stable",
    HEALTH_WEAKENING: "Weakening",
    HEALTH_DETERIORATING: "Deteriorating",
    HEALTH_UNKNOWN: "Not available",
}

VALUATION_CHEAP = "cheap"
VALUATION_FAIR = "fair"
VALUATION_EXPENSIVE = "expensive"
VALUATION_UNKNOWN = "unknown"

VALUATION_LABELS = {
    VALUATION_CHEAP: "Cheap",
    VALUATION_FAIR: "Fair",
    VALUATION_EXPENSIVE: "Expensive",
    VALUATION_UNKNOWN: "Not available",
}

NEWS_POSITIVE = "positive"
NEWS_NEUTRAL = "neutral"
NEWS_CONCERN = "concern"
NEWS_MAJOR_RISK = "major_risk"
NEWS_UNKNOWN = "unknown"

NEWS_LABELS = {
    NEWS_POSITIVE: "Positive",
    NEWS_NEUTRAL: "Neutral",
    NEWS_CONCERN: "Concern",
    NEWS_MAJOR_RISK: "Major risk",
    NEWS_UNKNOWN: "Not checked",
}


def health_status(fundamental_score, flags: Sequence[dict] | None) -> str:
    """
    One word for the balance sheet.

    A severe flag drops it to deteriorating regardless of the score, because
    the score averages over four components and a single catastrophic one —
    losses, negative equity returns — can be diluted by three healthy ones.
    """
    flags = flags or []
    if any(f.get("severity") == SEVERITY_SEVERE for f in flags):
        return HEALTH_DETERIORATING
    if blocks_averaging(flags):
        return HEALTH_WEAKENING
    score = _num(fundamental_score)
    if score is None:
        return HEALTH_UNKNOWN
    if flags:
        return HEALTH_WEAKENING
    if score >= 70:
        return HEALTH_STRONG
    if score >= 45:
        return HEALTH_STABLE
    return HEALTH_WEAKENING


def valuation_status(valuation_score) -> str:
    score = _num(valuation_score)
    if score is None:
        return VALUATION_UNKNOWN
    if score >= 65:
        return VALUATION_CHEAP
    if score >= 35:
        return VALUATION_FAIR
    return VALUATION_EXPENSIVE


def news_status(reason: dict | None) -> str:
    """
    News tone, taken from the reason-for-fall verdict rather than re-read.

    Scoring the headlines a second time here would double-count the least
    reliable input in the system; the verdict already weighed them against the
    price evidence.
    """
    if not reason:
        return NEWS_UNKNOWN
    news = reason.get("news") or {}
    if not news.get("checked"):
        return NEWS_UNKNOWN
    if news.get("severe_count"):
        return NEWS_MAJOR_RISK
    return {
        REASON_MARKET_WIDE: NEWS_POSITIVE,
        REASON_NOT_FALLING: NEWS_NEUTRAL,
        REASON_COMPANY_SOFT: NEWS_NEUTRAL,
        REASON_UNCERTAIN: NEWS_CONCERN,
        REASON_DETERIORATION: NEWS_MAJOR_RISK,
        REASON_CORPORATE_ACTION: NEWS_NEUTRAL,
    }.get(reason.get("reason"), NEWS_UNKNOWN)


def main_risk(reason: dict | None, fundamentals: dict | None) -> str | None:
    """
    The single thing most likely to break this holding, in one line.

    Returns None when there is nothing specific to say, rather than inventing a
    generic caution. A risk line that appears on every card teaches the reader
    to skip it.
    """
    reason = reason or {}
    flags = reason.get("deterioration_detail") or []
    severe = [f for f in flags if f.get("severity") == SEVERITY_SEVERE]
    if severe:
        return severe[0].get("text")
    if reason.get("reason") == REASON_CORPORATE_ACTION:
        return "A split or demerger makes the last year's figures unreliable"
    news = reason.get("news") or {}
    if news.get("severe_count"):
        return news.get("severe_headlines", [None])[0]
    if flags:
        return flags[0].get("text")
    if reason.get("reason") == REASON_UNCERTAIN:
        return "Falling well ahead of its sector with no visible cause"
    de = _num((fundamentals or {}).get("debt_to_equity"))
    if de is not None and de > DEBT_EQUITY_MILD:
        return "Carries more than 2x debt to equity"
    return None


def build_reasons(reason: dict | None, drawdown_pct, factors: dict) -> list[str]:
    """
    The two or three checkable lines the card shows under its score.

    Ordered by what actually drove the number, and allowed to include the
    unflattering line — a card that can only agree with its own score is
    decoration rather than an instrument.
    """
    out: list[str] = []
    reason = reason or {}
    dd = _num(drawdown_pct)
    if dd is not None and dd >= DRAWDOWN_MIN_PCT:
        out.append("{0:.1f}% below its 52-week high".format(dd))

    excess = _num(reason.get("excess_drawdown_pp"))
    if excess is not None:
        if excess <= EXCESS_MARKET_WIDE_PP:
            out.append("Falling with its market, not ahead of it")
        else:
            out.append("{0:+.1f}pp worse than its own sector".format(excess))

    val = _num(factors.get(FACTOR_VALUATION))
    if val is not None and val >= 65:
        out.append("Cheap against its sector")
    fund = _num(factors.get(FACTOR_FUNDAMENTAL))
    if fund is not None and fund >= 70 and len(out) < 3:
        out.append("Balance sheet and returns are healthy")

    flags = reason.get("deterioration_flags") or []
    if flags:
        out = [flags[0]] + out
    return out[:3]


def analyse_stock(holding: dict, *, benchmark_drawdown_pct=None,
                  fundamentals: dict | None = None,
                  headlines: Sequence[str] | None = None,
                  sector_pe=None, weights: dict | None = None,
                  price_integrity: dict | None = None) -> dict:
    """
    Full dip analysis for one stock.

    ``holding`` carries what the app already knows: symbol, name, price,
    avg_cost, drawdown_pct (from its own 52-week high), benchmark symbol/label.
    Everything else is optional and degrades to unknown rather than to zero.

    The returned ``score`` renormalises over the factors that are actually
    known and is reported beside a ``confidence`` — the share of total weight
    those factors represent.  Below :data:`MIN_CONFIDENCE` the action is capped
    at "watch" no matter how high the score, because a confident-looking number
    computed from one factor is worse than no number at all.
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        for k, v in weights.items():
            if k in w:
                val = _num(v)
                if val is not None and val >= 0:
                    w[k] = val

    integrity = price_integrity or {}
    corporate_action = bool(integrity.get("corporate_action_suspected"))

    dd = _num(holding.get("drawdown_pct"))
    reason = classify_reason(dd, _num(benchmark_drawdown_pct),
                             fundamentals, headlines,
                             corporate_action=corporate_action)

    # A drawdown measured across a demerger is not a drawdown. Dropping the
    # factor is the same treatment any other unmeasurable input gets.
    scored_dd = None if corporate_action else dd

    factors = {
        FACTOR_DRAWDOWN: score_drawdown(scored_dd),
        FACTOR_VALUATION: score_valuation(
            (fundamentals or {}).get("pe"), sector_pe,
            (fundamentals or {}).get("pb")),
        FACTOR_FUNDAMENTAL: score_fundamental(fundamentals),
        FACTOR_GROWTH: score_growth(fundamentals),
        FACTOR_NEWS: score_news(reason),
    }

    known = {k: v for k, v in factors.items() if v is not None}
    total_weight = sum(w[k] for k in known) or 0.0
    if total_weight > 0:
        score = round(sum(known[k] * w[k] for k in known) / total_weight, 1)
    else:
        score = None
    confidence = round(total_weight * 100.0, 1)

    blocked = reason["reason"] == REASON_DETERIORATION
    action = classify_action(score, blocked=blocked, confidence=confidence,
                             drawdown_known=scored_dd is not None,
                             cause_unclear=reason["reason"] == REASON_UNCERTAIN,
                             not_falling=reason["reason"] == REASON_NOT_FALLING)

    return {
        "symbol": holding.get("symbol"),
        "name": holding.get("name") or holding.get("symbol"),
        "price": _num(holding.get("price")),
        "avg_cost": _num(holding.get("avg_cost")),
        "drawdown_pct": dd,
        "benchmark": holding.get("benchmark"),
        "benchmark_label": holding.get("benchmark_label"),
        "benchmark_drawdown_pct": _num(benchmark_drawdown_pct),
        "factors": factors,
        "factor_labels": FACTOR_LABELS,
        "weights": w,
        "score": score,
        "confidence": confidence,
        "reason_for_fall": reason,
        "averaging_blocked": blocked,
        "corporate_action_suspected": corporate_action,
        "health": health_status(factors[FACTOR_FUNDAMENTAL],
                                reason.get("deterioration_detail")),
        "health_label": HEALTH_LABELS[
            health_status(factors[FACTOR_FUNDAMENTAL],
                          reason.get("deterioration_detail"))],
        "valuation": valuation_status(factors[FACTOR_VALUATION]),
        "valuation_label": VALUATION_LABELS[
            valuation_status(factors[FACTOR_VALUATION])],
        "news_sentiment": news_status(reason),
        "news_label": NEWS_LABELS[news_status(reason)],
        "main_risk": main_risk(reason, fundamentals),
        "reasons": build_reasons(reason, dd, factors),
        "price_integrity": integrity,
        "action": action,
        "action_label": ACTION_LABELS[action],
        "action_emoji": ACTION_EMOJI[action],
        "valuation_history_note": VALUATION_HISTORY_UNAVAILABLE,
        # Named explicitly so the UI can say WHY a stock is only "watch".
        "low_confidence": confidence < MIN_CONFIDENCE,
    }


# ══════════════════════════════════════════════════════════════════════════
#  ETFs
# ══════════════════════════════════════════════════════════════════════════
# An ETF's "business" is its index. Valuation, balance sheet, growth and
# company news do not exist for it, and scoring it on them produced a zero
# with 25% confidence. What does decide an ETF is how far its index has fallen
# and whether, over ten years, buying that index at such a depth beat buying
# it on any day — the same evidence the mutual-fund cards use.

FACTOR_BACKTEST = "backtest_support"
ETF_WEIGHTS = {FACTOR_DRAWDOWN: 0.6, FACTOR_BACKTEST: 0.4}
ETF_FACTOR_LABELS = {
    FACTOR_DRAWDOWN: "Fall from its high",
    FACTOR_BACKTEST: "History at this depth",
}
# Below this many daily bars the ETF's own series is not a 52-week record, and
# the tracked index's drawdown stands in for it.
ETF_MIN_OWN_POINTS = 60


def analyse_etf(holding: dict, *, benchmark_drawdown_pct=None,
                study: dict | None = None,
                price_integrity: dict | None = None) -> dict:
    """Dip analysis for an ETF, in the same shape as :func:`analyse_stock`.

    The ETF's own drawdown is used when its price history is real; when the
    feed only served a handful of bars (BSE-listed ETFs on Yahoo), the tracked
    index's drawdown stands in — the two differ only by tracking error.
    """
    integrity = price_integrity or {}
    bench_dd = _num(benchmark_drawdown_pct)
    own_dd = _num(holding.get("drawdown_pct"))
    thin = int(integrity.get("points") or 0) < ETF_MIN_OWN_POINTS
    dd = bench_dd if (own_dd is None or thin) else own_dd
    label = holding.get("benchmark_label") or "its index"

    factors = {
        FACTOR_DRAWDOWN: score_drawdown(dd),
        FACTOR_BACKTEST: mf_dip.score_backtest_support(
            study=study or {}, benchmark_drawdown_pct=bench_dd),
    }
    known = {k: v for k, v in factors.items() if v is not None}
    total_weight = sum(ETF_WEIGHTS[k] for k in known)
    score = (round(sum(known[k] * ETF_WEIGHTS[k] for k in known)
                   / total_weight, 1) if total_weight > 0 else None)
    confidence = round(total_weight * 100.0, 1)

    not_falling = dd is None or dd < MIN_DRAWDOWN_TO_CLASSIFY_PCT
    reason_key = REASON_NOT_FALLING if not_falling else REASON_MARKET_WIDE
    if dd is None:
        why = "No price history to measure a fall."
    elif not_falling:
        why = "Only {0:.1f}% below its high — no dip to buy.".format(dd)
    else:
        why = ("An index fund falls with its index: {0} is {1:.1f}% off its "
               "high.".format(label, bench_dd if bench_dd is not None else dd))
    reason = {
        "reason": reason_key, "label": REASON_LABELS[reason_key],
        "emoji": REASON_EMOJI[reason_key], "excess_drawdown_pp": None,
        "deterioration_flags": [], "deterioration_detail": [],
        "news": {"severe_count": 0, "market_count": 0, "severe_headlines": [],
                 "market_headlines": [], "checked": 0},
        "why": why,
    }
    action = classify_action(score, blocked=False, confidence=confidence,
                             drawdown_known=dd is not None,
                             not_falling=not_falling)

    evidence = mf_dip.backtest_evidence_depth(study, bench_dd)
    # For a stock, a low score reads "avoid averaging" because something about
    # the company argues against it. An index fund has no such case to answer:
    # a low score only means the dip is shallow. "Avoid" is kept for when the
    # index's own history says buying at this depth has lost to any day.
    if action == ACTION_AVOID and not (evidence and evidence["edge_pp"] < 0):
        action = ACTION_WATCH
    reasons = ["ETF tracking {0}".format(label)]
    if dd is not None and dd >= DRAWDOWN_MIN_PCT:
        reasons.append("{0:.1f}% below its 52-week high".format(dd))
    if evidence:
        line = ("History {0} buying at {1:.0f}% down ({2:+.1f}pp vs any day, "
                "{3} episodes)".format(
                    "favoured" if evidence["edge_pp"] > 0 else "did NOT favour",
                    evidence["depth_pct"], evidence["edge_pp"],
                    evidence.get("signals")))
        contra = evidence.get("contradicted_by")
        if contra:
            line += " — but {0} deeper episodes went {1:+.1f}pp".format(
                contra.get("signals"), contra["edge_pp"])
        reasons.append(line)

    deep = bench_dd is not None and bench_dd >= mf_dip.BENCH_DIP_PLATEAU_PCT
    return {
        "symbol": holding.get("symbol"),
        "name": holding.get("name") or holding.get("symbol"),
        "instrument": "etf",
        "price": _num(holding.get("price")),
        "avg_cost": _num(holding.get("avg_cost")),
        "drawdown_pct": dd,
        "benchmark": holding.get("benchmark"),
        "benchmark_label": holding.get("benchmark_label"),
        "benchmark_drawdown_pct": bench_dd,
        "factors": factors,
        "factor_labels": ETF_FACTOR_LABELS,
        "weights": ETF_WEIGHTS,
        "score": score,
        "confidence": confidence,
        "reason_for_fall": reason,
        "averaging_blocked": False,
        "corporate_action_suspected": False,
        "health": HEALTH_UNKNOWN,
        "health_label": "Index fund",
        "valuation": VALUATION_UNKNOWN,
        "valuation_label": "Tracks {0}".format(label),
        "news_sentiment": NEWS_UNKNOWN,
        "news_label": "Not applicable",
        "main_risk": ("{0} is in a deep fall — a discount and a repricing "
                      "look the same from here".format(label) if deep else None),
        "reasons": reasons[:3],
        "price_integrity": integrity,
        "action": action,
        "action_label": ACTION_LABELS[action],
        "action_emoji": ACTION_EMOJI[action],
        "backtest_evidence": evidence,
        "valuation_history_note": VALUATION_HISTORY_UNAVAILABLE,
        "low_confidence": confidence < MIN_CONFIDENCE,
    }


# Board order: what to DO first, then how strongly. Sorting by score alone put
# a 79.8 "watch" (cause of the fall unclear) above a 78.6 "consider".
ACTION_RANK = {
    ACTION_ACCUMULATE: 0,
    ACTION_CONSIDER: 1,
    ACTION_WATCH: 2,
    ACTION_AVOID: 3,
    ACTION_DO_NOT_AVERAGE: 4,
}


def board_sort_key(row: dict):
    """Sort key for the stock board: confident rows first, then action, score.

    Do-not-average rows always sink to the bottom, confident or not.
    """
    score = _num(row.get("score"))
    action = row.get("action")
    return (action == ACTION_DO_NOT_AVERAGE,
            bool(row.get("low_confidence")),
            ACTION_RANK.get(action, 5),
            -(score if score is not None else -1),
            -(_num(row.get("confidence")) or 0))
