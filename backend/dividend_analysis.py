"""
Dividend income analysis — pure computation layer.

Everything in this module is deterministic and network-free so it can be
unit-tested without hitting yfinance.  ``main.py`` supplies the raw per-holding
facts (price, shares, dividend-per-share, payout ratio, dividend history) and
calls :func:`build_dividend_book` to get the API payload.

Design notes
------------
* Yield is always DERIVED from DPS / price rather than read from the provider's
  ``dividendYield`` field — providers flip between fraction (0.064) and percent
  (6.4) between versions and the ambiguity is unresolvable for low yields.
* Indian fiscal years (Apr–Mar) are used for growth/streak maths because Indian
  companies declare interim + final dividends inside one FY.
* Any holding the provider has no dividend data for degrades to a zero-payer
  instead of breaking the book, so newly added stocks/funds are always safe.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Sequence

# ── Tunables ──────────────────────────────────────────────────────────────
DEFAULT_GOAL_ANNUAL = 120_000.0     # ₹1.2 L/yr  ≈ ₹10 k/month
DEFAULT_TAX_SLAB_PCT = 30.0         # dividends are slab-taxed in India
TDS_THRESHOLD_PER_COMPANY = 10_000.0  # s.194 TDS kicks in above this per payer
DEFAULT_DIVIDEND_GROWTH_PCT = 8.0   # per-year DPS growth when history is thin
DEFAULT_CAPITAL_GROWTH_PCT = 8.0    # per-year price growth for corpus path

# Yield rungs shown in the "corpus required" ladder.
CORPUS_YIELD_RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0, 6.0)

# Quality thresholds
ANCHOR_MIN_YIELD = 4.0
ANCHOR_MAX_PAYOUT = 90.0
ANCHOR_MIN_YEARS = 3
GROWER_MIN_CAGR = 8.0
GROWER_MIN_YIELD = 1.5
TRAP_PAYOUT = 100.0
TRAP_DECLINE_CAGR = -10.0

TIER_ANCHOR = "anchor"
TIER_GROWER = "grower"
TIER_MODEST = "modest"
TIER_TRAP = "trap"
TIER_NONE = "none"

TIER_LABELS = {
    TIER_ANCHOR: "Income anchor",
    TIER_GROWER: "Dividend grower",
    TIER_MODEST: "Modest payer",
    TIER_TRAP: "Yield trap risk",
    TIER_NONE: "Non-payer",
}


# ══════════════════════════════════════════════════════════════════════════
#  DATE / HISTORY HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _as_date(value) -> date | None:
    """Coerce str / date / datetime into a ``date``.  ``None`` when unparseable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Trim timestamps / timezones: "2026-05-20 00:00:00+05:30" -> "2026-05-20"
    text = text.replace("T", " ").split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def fiscal_year(d: date) -> int:
    """Indian FY start year: 20 May 2026 -> 2026, 20 Feb 2026 -> 2025."""
    return d.year if d.month >= 4 else d.year - 1


def normalize_history(history: Iterable) -> list[tuple[date, float]]:
    """
    Normalize a dividend history into a sorted ``[(ex_date, amount)]`` list.

    Accepts ``[(date, amt)]``, ``[{"date": ..., "amount": ...}]`` or a
    ``{date: amt}`` mapping — whichever shape the caller has on hand.
    """
    rows: list[tuple[date, float]] = []
    if history is None:
        return rows
    if isinstance(history, dict):
        items = history.items()
    else:
        items = history
    for item in items:
        if isinstance(item, dict):
            raw_date = item.get("date") or item.get("ex_date")
            raw_amt = item.get("amount", item.get("dividend", 0))
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            raw_date, raw_amt = item[0], item[1]
        else:
            continue
        d = _as_date(raw_date)
        try:
            amt = float(raw_amt or 0)
        except (TypeError, ValueError):
            continue
        if d is None or amt <= 0:
            continue
        rows.append((d, amt))
    rows.sort(key=lambda r: r[0])
    return rows


def trailing_12m_dps(history: Iterable, as_of: date | None = None) -> float:
    """Sum of dividends with an ex-date in the trailing 365 days."""
    rows = normalize_history(history)
    if not rows:
        return 0.0
    ref = as_of or rows[-1][0]
    cutoff_ordinal = ref.toordinal() - 365
    return round(sum(a for d, a in rows if d.toordinal() > cutoff_ordinal), 4)


def last_complete_fy_dps(history: Iterable, as_of: date | None = None) -> float:
    """
    Total DPS of the most recently *completed* Indian fiscal year.

    Needed because a strict trailing-365-day window has an anniversary cliff:
    on 5 Aug 2026 a stock that paid its interim on 1 Aug 2025 and its final in
    Feb 2026 shows only the final, understating annual DPS by ~80%.
    """
    ref = as_of or date.today()
    return dps_by_fiscal_year(history).get(fiscal_year(ref) - 1, 0.0)


def dps_by_fiscal_year(history: Iterable) -> dict[int, float]:
    """Total DPS grouped by Indian fiscal year start-year."""
    out: dict[int, float] = {}
    for d, amt in normalize_history(history):
        fy = fiscal_year(d)
        out[fy] = round(out.get(fy, 0.0) + amt, 4)
    return out


def dividend_cagr(history: Iterable, max_years: int = 5,
                  as_of: date | None = None) -> float:
    """
    DPS CAGR (%) across *completed* fiscal years, window capped at ``max_years``.

    The current fiscal year is excluded deliberately.  Indian companies declare
    interims through the year and the final after year-end, so a part-year total
    is always lower than the full year — ending the window on it turns a rising
    dividend into an apparent collapse.  (Coal India in Aug 2026: FY2019–25 runs
    12.00 → 26.40, about +14%/yr, but FY2026-to-date is a single ₹5.50 interim,
    which would read as −21%/yr and flag a healthy anchor as a yield trap.)

    Returns 0.0 when fewer than two completed years remain, or when the base
    year paid nothing (CAGR from zero is undefined, not infinite).
    """
    current_fy = fiscal_year(as_of or date.today())
    by_fy = {fy: dps for fy, dps in dps_by_fiscal_year(history).items()
             if fy < current_fy}
    if len(by_fy) < 2:
        return 0.0
    years = sorted(by_fy)[-(max_years + 1):]
    first, last = by_fy[years[0]], by_fy[years[-1]]
    span = years[-1] - years[0]
    if first <= 0 or last <= 0 or span <= 0:
        return 0.0
    return round(((last / first) ** (1.0 / span) - 1.0) * 100, 2)


def years_paid(history: Iterable) -> int:
    """Number of distinct fiscal years with at least one payout."""
    return len(dps_by_fiscal_year(history))


def payout_months(history: Iterable, lookback_years: int = 3,
                  as_of: date | None = None) -> dict[int, float]:
    """
    Average payout by calendar month over the last ``lookback_years`` completed
    FYs — drives the "when does the cash actually land" calendar.

    Completed years only, for the same reason as :func:`dividend_cagr`: a
    part-year would flatten the shape and understate every month's average. A
    company whose only payouts fall in the current FY (a recent lister) keeps
    those rather than dropping out of the calendar entirely.
    """
    rows = normalize_history(history)
    if not rows:
        return {}
    current_fy = fiscal_year(as_of or date.today())
    complete = [(d, a) for d, a in rows if fiscal_year(d) < current_fy]
    if not complete:
        complete = rows              # only part-year data exists — use it
    newest_fy = fiscal_year(complete[-1][0])
    cutoff_fy = newest_fy - (lookback_years - 1)
    buckets: dict[int, float] = {}
    fys: set[int] = set()
    for d, amt in complete:
        fy = fiscal_year(d)
        if fy < cutoff_fy:
            continue
        fys.add(fy)
        buckets[d.month] = buckets.get(d.month, 0.0) + amt
    n = max(len(fys), 1)
    return {m: round(v / n, 4) for m, v in sorted(buckets.items())}


# ══════════════════════════════════════════════════════════════════════════
#  PER-HOLDING RESOLUTION & CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════

def resolve_dps(
    *,
    history=None,
    info_rate: float | None = None,
    trailing_rate: float | None = None,
    manual_override: float | None = None,
    as_of: date | None = None,
) -> tuple[float, str]:
    """
    Pick the most trustworthy annual DPS available and say where it came from.

    Priority: user override > real ex-date history > provider's forward
    ``dividendRate`` > provider's ``trailingAnnualDividendRate``.

    Within the history basis we take the HIGHER of the trailing 12 months and
    the last completed fiscal year.  Trailing-12m alone loses an interim payout
    right after its anniversary; last-FY alone misses a fresh dividend hike.
    Taking the max keeps the annual run-rate stable across both edges, and the
    returned source says which basis won so the UI can disclose it.
    """
    if manual_override is not None and float(manual_override) > 0:
        return round(float(manual_override), 4), "manual"
    ref = as_of or date.today()
    ttm = trailing_12m_dps(history, as_of=ref)
    last_fy = last_complete_fy_dps(history, as_of=ref)
    if ttm > 0 or last_fy > 0:
        if ttm >= last_fy:
            return ttm, "history_ttm"
        return round(last_fy, 4), "history_last_fy"
    for value, source in ((info_rate, "provider_rate"),
                          (trailing_rate, "provider_trailing")):
        try:
            v = float(value or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > 0:
            return round(v, 4), source
    return 0.0, "none"


def classify_dividend(
    yield_pct: float,
    payout_ratio: float,
    growth_cagr: float,
    n_years: int,
) -> tuple[str, str]:
    """Return ``(tier, plain-English reason)`` for one holding."""
    if yield_pct <= 0:
        return TIER_NONE, "No dividend in the trailing 12 months — capital position only"
    if payout_ratio > TRAP_PAYOUT:
        return (TIER_TRAP,
                f"Paying out {payout_ratio:.0f}% of earnings — the dividend is "
                "being funded from reserves, not profit")
    if growth_cagr <= TRAP_DECLINE_CAGR and yield_pct >= ANCHOR_MIN_YIELD:
        return (TIER_TRAP,
                f"High {yield_pct:.1f}% yield but DPS falling {abs(growth_cagr):.0f}%/yr "
                "— the yield is high because the payout is shrinking")
    if (yield_pct >= ANCHOR_MIN_YIELD
            and payout_ratio <= ANCHOR_MAX_PAYOUT
            and n_years >= ANCHOR_MIN_YEARS):
        return (TIER_ANCHOR,
                f"{yield_pct:.1f}% yield paid across {n_years} years with a "
                f"{payout_ratio:.0f}% payout — keep as an income anchor")
    if growth_cagr >= GROWER_MIN_CAGR and yield_pct >= GROWER_MIN_YIELD:
        return (TIER_GROWER,
                f"{yield_pct:.1f}% today but DPS compounding {growth_cagr:.0f}%/yr "
                "— income grows into the position")
    return (TIER_MODEST,
            f"{yield_pct:.1f}% yield — contributes income but won't move the goal alone")


def is_idcw_plan(scheme_name: str) -> bool:
    """
    True when a fund actually pays cash out.  Growth-plan funds reinvest
    internally, so their underlying dividends are NOT spendable income.
    """
    name = (scheme_name or "").lower()
    if "growth" in name:
        return False
    return any(tag in name for tag in ("idcw", "dividend", "payout", "income distribution"))


def build_stock_row(
    holding: dict,
    dividend_facts: dict | None = None,
    as_of: date | None = None,
) -> dict:
    """
    Turn one direct-equity holding + its dividend facts into a ledger row.

    ``holding`` needs ``symbol``, ``shares``, ``price``; ``avg_cost``,
    ``sector`` and ``value`` are optional.  ``dividend_facts`` is whatever the
    provider gave us — every field is optional, so an unknown newly-added
    symbol still produces a valid (zero-income) row.
    """
    facts = dividend_facts or {}
    symbol = str(holding.get("symbol", "")).replace(".NS", "").replace(".BO", "")
    shares = float(holding.get("shares", 0) or 0)
    price = float(holding.get("price", 0) or 0)
    avg_cost = float(holding.get("avg_cost", 0) or 0)
    value = float(holding.get("value") or (shares * price))

    history = facts.get("history")
    dps, dps_source = resolve_dps(
        history=history,
        info_rate=facts.get("dividend_rate"),
        trailing_rate=facts.get("trailing_dividend_rate"),
        manual_override=facts.get("manual_dps"),
        as_of=as_of,
    )

    annual_income = round(dps * shares, 2)
    yield_pct = round(dps / price * 100, 2) if price > 0 else 0.0
    yield_on_cost = round(dps / avg_cost * 100, 2) if avg_cost > 0 else 0.0

    payout_ratio = float(facts.get("payout_ratio") or 0)
    if 0 < payout_ratio <= 1.5:          # provider gave a fraction, not a percent
        payout_ratio *= 100
    payout_ratio = round(payout_ratio, 1)

    ref = as_of or date.today()
    cagr = dividend_cagr(history, as_of=ref)
    n_years = years_paid(history)
    tier, reason = classify_dividend(yield_pct, payout_ratio, cagr, n_years)

    return {
        "symbol": symbol,
        "sector": holding.get("sector") or "Other",
        "shares": shares,
        "price": round(price, 2),
        "avg_cost": round(avg_cost, 2),
        "value": round(value, 2),
        "dps": dps,
        "dps_source": dps_source,
        "annual_income": annual_income,
        "monthly_income": round(annual_income / 12, 2),
        "yield_pct": yield_pct,
        "yield_on_cost": yield_on_cost,
        "payout_ratio": payout_ratio,
        "growth_cagr": cagr,
        "years_paid": n_years,
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "reason": reason,
        "tds_applicable": annual_income > TDS_THRESHOLD_PER_COMPANY,
        "payout_months": payout_months(history, as_of=ref),
    }


def build_fund_row(fund: dict, lookthrough_yield_pct: float = 0.0) -> dict:
    """
    Turn one mutual-fund holding into a ledger row.

    Growth plans are marked ``distributes=False``: their look-through yield is
    reported for transparency but excluded from spendable income, which is the
    single most common way dividend-income plans get overstated.
    """
    scheme = str(fund.get("scheme_name", ""))
    value = float(fund.get("current_value", 0) or 0)
    invested = float(fund.get("invested", 0) or 0)
    distributes = is_idcw_plan(scheme)
    lt_yield = round(float(lookthrough_yield_pct or 0), 2)

    declared = fund.get("declared_annual_income")
    if declared is not None:
        cash_income = round(float(declared or 0), 2)
    elif distributes:
        cash_income = round(value * lt_yield / 100, 2)
    else:
        cash_income = 0.0

    return {
        "scheme_name": scheme,
        "category": fund.get("category") or "Unknown",
        "plan": "IDCW" if distributes else "Growth",
        "distributes": distributes,
        "value": round(value, 2),
        "invested": round(invested, 2),
        "lookthrough_yield": lt_yield,
        "lookthrough_income": round(value * lt_yield / 100, 2),
        "cash_income": cash_income,
        "monthly_income": round(cash_income / 12, 2),
        "note": ("Pays out — counts as spendable income"
                 if distributes
                 else "Growth plan — underlying dividends are reinvested, not paid to you"),
    }


def lookthrough_yield(top_holdings: Sequence[dict], stock_yields: dict) -> float:
    """
    Weighted dividend yield inside a fund from its disclosed top holdings.

    ``top_holdings`` is ``[{"stock": "ITC.NS", "pct": 8.5}]``; ``stock_yields``
    maps symbol (either raw or suffix-stripped) to a yield percent.  Scaled by
    disclosed weight so a fund that only discloses 40% of its book is not
    treated as 60% cash.
    """
    total_weight = 0.0
    weighted = 0.0
    for h in top_holdings or []:
        sym = str(h.get("stock", ""))
        pct = float(h.get("pct", 0) or 0)
        if pct <= 0:
            continue
        y = stock_yields.get(sym)
        if y is None:
            y = stock_yields.get(sym.replace(".NS", "").replace(".BO", ""))
        total_weight += pct
        if y:
            weighted += pct * float(y)
    if total_weight <= 0:
        return 0.0
    return round(weighted / total_weight, 2)


# ══════════════════════════════════════════════════════════════════════════
#  GOAL MATHS
# ══════════════════════════════════════════════════════════════════════════

def corpus_required(goal_annual: float, rungs: Sequence[float] = CORPUS_YIELD_RUNGS) -> list[dict]:
    """Corpus needed to throw off ``goal_annual`` at each blended-yield rung."""
    out = []
    for y in rungs:
        if y <= 0:
            continue
        out.append({
            "yield_pct": round(float(y), 2),
            "corpus_required": round(goal_annual / (y / 100), 2),
            "realism": ("achievable" if y <= 4.0
                        else "high-yield only" if y <= 5.0
                        else "deep-value / PSU concentration"),
        })
    return out


def project_income(
    current_income: float,
    current_corpus: float,
    goal_annual: float,
    *,
    monthly_investment: float = 0.0,
    dividend_growth_pct: float = DEFAULT_DIVIDEND_GROWTH_PCT,
    capital_growth_pct: float = DEFAULT_CAPITAL_GROWTH_PCT,
    new_money_yield_pct: float = 0.0,
    years: int = 10,
    start_year: int | None = None,
) -> list[dict]:
    """
    Year-by-year path of dividend income and corpus.

    Existing income compounds at the DPS growth rate; each year's fresh money
    is credited at ``new_money_yield_pct`` from the FOLLOWING year (money
    invested during a year does not earn a full year of dividends).
    """
    base_year = start_year if start_year is not None else 0
    income = float(current_income)
    corpus = float(current_corpus)
    annual_new = max(float(monthly_investment), 0.0) * 12
    g = dividend_growth_pct / 100
    cg = capital_growth_pct / 100
    ny = max(float(new_money_yield_pct), 0.0) / 100

    rows = []
    pending_new_money = 0.0
    for i in range(1, max(int(years), 1) + 1):
        income = income * (1 + g) + pending_new_money * ny
        corpus = corpus * (1 + cg) + annual_new
        pending_new_money += annual_new
        rows.append({
            "year": base_year + i if base_year else i,
            "offset": i,
            "annual_income": round(income, 2),
            "monthly_income": round(income / 12, 2),
            "corpus": round(corpus, 2),
            "goal_pct": round(income / goal_annual * 100, 1) if goal_annual > 0 else 0.0,
            "goal_reached": goal_annual > 0 and income >= goal_annual,
        })
    return rows


def monthly_investment_for_goal(
    current_income: float,
    goal_annual: float,
    horizon_years: int,
    *,
    dividend_growth_pct: float = DEFAULT_DIVIDEND_GROWTH_PCT,
    new_money_yield_pct: float = 4.0,
) -> float:
    """
    Monthly SIP needed to hit ``goal_annual`` within ``horizon_years``.

    Solved by bisection against :func:`project_income` so the answer always
    matches the projection the UI draws — no second, divergent formula.
    """
    if goal_annual <= 0 or horizon_years <= 0:
        return 0.0

    def income_at(monthly: float) -> float:
        path = project_income(
            current_income, 0.0, goal_annual,
            monthly_investment=monthly,
            dividend_growth_pct=dividend_growth_pct,
            capital_growth_pct=0.0,
            new_money_yield_pct=new_money_yield_pct,
            years=horizon_years,
        )
        return path[-1]["annual_income"]

    if income_at(0.0) >= goal_annual:
        return 0.0
    if new_money_yield_pct <= 0:
        return float("inf")

    lo, hi = 0.0, 1000.0
    for _ in range(60):                       # grow the bracket until it covers the goal
        if income_at(hi) >= goal_annual:
            break
        hi *= 2
        if hi > 1e9:
            return float("inf")
    for _ in range(80):                       # then bisect
        mid = (lo + hi) / 2
        if income_at(mid) >= goal_annual:
            hi = mid
        else:
            lo = mid
    return round(hi, 0)


# ══════════════════════════════════════════════════════════════════════════
#  BOOK ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════

def _income_alerts(
    stock_rows: Sequence[dict],
    fund_rows: Sequence[dict],
    total_income: float,
    blended_yield: float,
    goal_pct: float,
) -> list[dict]:
    alerts: list[dict] = []

    traps = [s for s in stock_rows if s["tier"] == TIER_TRAP]
    for t in traps:
        alerts.append({
            "level": "critical",
            "msg": f"{t['symbol']}: {t['reason']}",
        })

    if total_income > 0:
        top = max(stock_rows, key=lambda s: s["annual_income"], default=None)
        if top and top["annual_income"] / total_income > 0.4:
            share = top["annual_income"] / total_income * 100
            alerts.append({
                "level": "warning",
                "msg": f"{share:.0f}% of your dividend income comes from "
                       f"{top['symbol']} alone — one payout cut halves the ledger",
            })

        by_sector: dict[str, float] = {}
        for s in stock_rows:
            by_sector[s["sector"]] = by_sector.get(s["sector"], 0.0) + s["annual_income"]
        if by_sector:
            sec, amt = max(by_sector.items(), key=lambda kv: kv[1])
            if amt / total_income > 0.5:
                alerts.append({
                    "level": "warning",
                    "msg": f"{amt / total_income * 100:.0f}% of income is {sec} — "
                           "the ledger is a sector bet, not a diversified income book",
                })

    tds_hits = [s["symbol"] for s in stock_rows if s["tds_applicable"]]
    if tds_hits:
        alerts.append({
            "level": "info",
            "msg": f"TDS applies on {', '.join(tds_hits)} — annual payout exceeds "
                   f"₹{TDS_THRESHOLD_PER_COMPANY:,.0f} from a single company",
        })

    growth_funds = [f for f in fund_rows if not f["distributes"] and f["value"] > 0]
    if growth_funds:
        hidden = sum(f["lookthrough_income"] for f in growth_funds)
        if hidden > 0:
            alerts.append({
                "level": "info",
                "msg": f"₹{hidden:,.0f}/yr of dividends is earned inside "
                       f"{len(growth_funds)} growth-plan fund(s) and reinvested — "
                       "it raises NAV but never reaches your bank account",
            })

    if blended_yield > 5.5:
        alerts.append({
            "level": "warning",
            "msg": f"Blended yield of {blended_yield:.1f}% is only reachable through "
                   "PSU/commodity concentration — check the growth side of the book",
        })

    if goal_pct < 25 and total_income > 0:
        alerts.append({
            "level": "info",
            "msg": f"Income covers {goal_pct:.0f}% of the goal — the gap closes with "
                   "fresh capital far faster than with yield-chasing",
        })

    return alerts


def build_dividend_book(
    stock_rows: Sequence[dict],
    fund_rows: Sequence[dict],
    *,
    goal_annual: float = DEFAULT_GOAL_ANNUAL,
    tax_slab_pct: float = DEFAULT_TAX_SLAB_PCT,
    monthly_investment: float = 0.0,
    other_assets_value: float = 0.0,
    as_of: date | None = None,
) -> dict:
    """
    Assemble the full dividend payload from already-built stock and fund rows.

    ``stock_rows``/``fund_rows`` come from :func:`build_stock_row` /
    :func:`build_fund_row`, so this function is pure arithmetic over them and
    stays valid whatever mix of stocks and funds the user adds later.
    """
    goal_annual = max(float(goal_annual or 0), 0.0)

    stock_income = sum(s["annual_income"] for s in stock_rows)
    fund_income = sum(f["cash_income"] for f in fund_rows)
    total_income = round(stock_income + fund_income, 2)

    stock_value = sum(s["value"] for s in stock_rows)
    fund_value = sum(f["value"] for f in fund_rows)
    total_value = round(stock_value + fund_value + float(other_assets_value or 0), 2)
    income_bearing_value = stock_value + sum(f["value"] for f in fund_rows if f["distributes"])

    stock_cost = sum(s["shares"] * s["avg_cost"] for s in stock_rows)

    blended_yield = round(total_income / total_value * 100, 2) if total_value > 0 else 0.0
    yield_on_cost = round(stock_income / stock_cost * 100, 2) if stock_cost > 0 else 0.0
    payers = [s for s in stock_rows if s["annual_income"] > 0]
    non_payers = [s for s in stock_rows if s["annual_income"] <= 0]

    tax_slab_pct = min(max(float(tax_slab_pct or 0), 0.0), 100.0)
    net_income = round(total_income * (1 - tax_slab_pct / 100), 2)

    gap = round(max(goal_annual - total_income, 0.0), 2)
    goal_pct = round(total_income / goal_annual * 100, 1) if goal_annual > 0 else 0.0

    # Weighted DPS growth of the actual book, used to drive the projection.
    if stock_income > 0:
        wtd_growth = sum(s["growth_cagr"] * s["annual_income"] for s in payers) / stock_income
    else:
        wtd_growth = DEFAULT_DIVIDEND_GROWTH_PCT
    wtd_growth = round(max(min(wtd_growth, 20.0), 0.0), 2)

    # Yield credited to fresh money: what this book actually achieves, floored
    # at a realistic 3% and capped at 6% so the plan is not a fantasy.
    new_money_yield = round(min(max(blended_yield, 3.0), 6.0), 2)

    projection = project_income(
        total_income, total_value, goal_annual,
        monthly_investment=monthly_investment,
        dividend_growth_pct=wtd_growth or DEFAULT_DIVIDEND_GROWTH_PCT,
        new_money_yield_pct=new_money_yield,
        years=10,
        start_year=(as_of or date.today()).year,
    )
    reached = next((p for p in projection if p["goal_reached"]), None)

    # Income by sector
    sector_income: dict[str, float] = {}
    for s in stock_rows:
        if s["annual_income"] > 0:
            sector_income[s["sector"]] = round(
                sector_income.get(s["sector"], 0.0) + s["annual_income"], 2)
    by_sector = [
        {
            "sector": sec,
            "income": amt,
            "pct": round(amt / total_income * 100, 1) if total_income > 0 else 0.0,
        }
        for sec, amt in sorted(sector_income.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # Cash-flow calendar (direct equity only — funds have no reliable schedule)
    calendar = {m: 0.0 for m in range(1, 13)}
    for s in stock_rows:
        for month, dps in (s.get("payout_months") or {}).items():
            calendar[int(month)] = round(calendar[int(month)] + dps * s["shares"], 2)

    ranked = sorted(stock_rows, key=lambda s: (-s["annual_income"], s["symbol"]))

    return {
        "as_of": (as_of or date.today()).isoformat(),
        "goal": {
            "annual": goal_annual,
            "monthly": round(goal_annual / 12, 2),
            "achieved_pct": goal_pct,
            "gap_annual": gap,
            "gap_monthly": round(gap / 12, 2),
            "on_track": goal_annual > 0 and total_income >= goal_annual,
            "years_to_goal": reached["offset"] if reached else None,
            "goal_year": reached["year"] if reached else None,
            "assumed_dividend_growth_pct": wtd_growth,
            "assumed_new_money_yield_pct": new_money_yield,
            "monthly_investment": round(float(monthly_investment or 0), 2),
            "sip_needed_3y": monthly_investment_for_goal(
                total_income, goal_annual, 3, dividend_growth_pct=wtd_growth,
                new_money_yield_pct=new_money_yield),
            "sip_needed_5y": monthly_investment_for_goal(
                total_income, goal_annual, 5, dividend_growth_pct=wtd_growth,
                new_money_yield_pct=new_money_yield),
            "sip_needed_10y": monthly_investment_for_goal(
                total_income, goal_annual, 10, dividend_growth_pct=wtd_growth,
                new_money_yield_pct=new_money_yield),
        },
        "income": {
            "annual_gross": total_income,
            "monthly_gross": round(total_income / 12, 2),
            "annual_net": net_income,
            "monthly_net": round(net_income / 12, 2),
            "tax_slab_pct": tax_slab_pct,
            "from_stocks": round(stock_income, 2),
            "from_funds": round(fund_income, 2),
            "reinvested_in_funds": round(
                sum(f["lookthrough_income"] for f in fund_rows if not f["distributes"]), 2),
            "blended_yield": blended_yield,
            "yield_on_cost": yield_on_cost,
            "total_value": total_value,
            "income_bearing_value": round(income_bearing_value, 2),
            "income_bearing_pct": round(income_bearing_value / total_value * 100, 1)
            if total_value > 0 else 0.0,
            "payer_count": len(payers),
            "non_payer_count": len(non_payers),
            "non_payers": [s["symbol"] for s in non_payers],
        },
        "corpus_ladder": corpus_required(goal_annual),
        "projection": projection,
        "stocks": ranked,
        "funds": sorted(fund_rows, key=lambda f: -f["value"]),
        "by_sector": by_sector,
        "anchors": [s for s in ranked if s["tier"] == TIER_ANCHOR],
        "growers": [s for s in ranked if s["tier"] == TIER_GROWER],
        "traps": [s for s in ranked if s["tier"] == TIER_TRAP],
        "calendar": [{"month": m, "amount": calendar[m]} for m in range(1, 13)],
        "alerts": _income_alerts(stock_rows, fund_rows, total_income, blended_yield, goal_pct),
    }


def empty_book(goal_annual: float = DEFAULT_GOAL_ANNUAL,
               tax_slab_pct: float = DEFAULT_TAX_SLAB_PCT) -> dict:
    """A well-formed, all-zero book — used when there are no holdings yet."""
    return build_dividend_book([], [], goal_annual=goal_annual, tax_slab_pct=tax_slab_pct)
