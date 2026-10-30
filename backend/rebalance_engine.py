"""
Rebalancing engine — what to trim, what to add, and what it costs to do it.

The policy this implements, in one paragraph: every direct stock is held
between MIN_WEIGHT_PCT and MAX_WEIGHT_PCT of the direct-stock sleeve, and every
fund between the same bounds of the fund sleeve. The book is only OPENED on a
trigger — a calendar date, a market boom, or a position leaving its band — and
even then a trade is only proposed for the positions that are actually outside
their band. That last part is the whole point: calendar-only rebalancing sells
things that did not need selling, and band-only rebalancing never looks at the
portfolio unless a price move forces it. Checking on a schedule and trading on
a band is the combination that keeps drift bounded at the lowest turnover.

Two things make this different from the textbook version, and both are tax:

  1. A sell is sized in LOTS, not in rupees. Units held over LONG_TERM_DAYS are
     taxed at a different rate from units bought last month, so the engine
     matches FIFO, spends long-term units first, and reports what each lot
     costs. Selling the same rupee value out of the wrong lots is a real and
     avoidable loss.
  2. Gains are computed for an NRI by default, where the tax is not a bill at
     filing time but TDS withheld at source by the broker or AMC. Money that
     never reaches the account cannot be reinvested into the underweight, so
     the plan reports net proceeds, not gross.

Every function here is pure: dicts in, dicts out, no network and no clock of
its own. `as_of` is always passed in so the tests can stand anywhere in time.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ── Position bands ──
# The floor exists because a position too small to matter still costs attention
# and brokerage; below it, either commit or close. The ceiling is single-stock
# concentration risk.
MIN_WEIGHT_PCT = 2.0
MAX_WEIGHT_PCT = 10.0

# How close to its own 12-month high a holding must still be for a trim to
# count as early rather than late. 0.95 = within 5% of the high.
#
# Measured on the ten-stock basket, monthly, 2011-2026, at a 20% ceiling: the
# guard fired 9 times and moved the run from 16.84% to 17.60% pre-tax and
# 15.99% to 16.49% after tax. Chosen wide enough that ordinary noise cannot
# veto a legitimate trim, tight enough to catch a sale made after the fall.
TRIM_PEAK_BAND = 0.95

# A band edge crossed by a hair is noise. Requiring a real breach stops the
# engine proposing a ₹400 trade every time a price ticks.
BAND_TOLERANCE_PCT = 0.25
# Nor is it worth a contract note.
MIN_TRADE_VALUE = 5000.0

# ── Cadence ──
SEMIANNUAL_DAYS = 182
ANNUAL_DAYS = 365
CADENCES = {"semiannual": SEMIANNUAL_DAYS, "annual": ANNUAL_DAYS}

# ── Holding period ──
# Listed equity and equity-oriented funds turn long-term after 12 months.
LONG_TERM_DAYS = 365
# Non-equity (debt, gold, international) needs 24 months to be long-term.
LONG_TERM_DAYS_NON_EQUITY = 730
# A lot this close to maturing is worth waiting for rather than taxing now.
RIPENING_WINDOW_DAYS = 45


# ══════════════════════════════════════════════════════════════
#  TAX  (India, on or after 23 July 2024)
# ══════════════════════════════════════════════════════════════
#
# Rates are stated here rather than inline so a Budget change is a one-line
# edit and the tests can name what they are asserting. These are INDICATIVE:
# surcharge depends on total income, which this engine does not know, and the
# LTCG exemption is per financial year across every equity disposal, which it
# only knows about within a single plan.

EQUITY_STCG_PCT = 20.0          # s.111A, STT-paid, held <= 12 months
EQUITY_LTCG_PCT = 12.5          # s.112A, held > 12 months
EQUITY_LTCG_EXEMPT = 125000.0   # s.112A annual exemption, available to NRIs too
NON_EQUITY_STCG_PCT = 30.0      # NRI TDS on short-term non-equity units
NON_EQUITY_LTCG_PCT = 12.5      # listed/specified units, no indexation
CESS_PCT = 4.0
# Surcharge on 111A/112A gains is capped at 15% however large the gain.
SURCHARGE_BANDS = ((10000000.0, 15.0), (5000000.0, 10.0))
SURCHARGE_CAP_PCT = 15.0

RESIDENT = "resident"
NRI = "nri"

# Fund categories that are equity-oriented for tax. Note what is NOT here:
# international and fund-of-fund exposure is taxed as non-equity in India
# however equity-like it looks in the allocation chart, and gold is never
# equity. Getting this wrong understates the tax by more than half.
_EQUITY_FUND_MARKERS = (
    "large", "mid", "small", "flexi", "multi", "index", "elss", "bluechip",
    "value", "focused", "contra", "dividend yield", "sectoral", "thematic",
    "aggressive hybrid", "equity savings", "nifty", "sensex",
)
_NON_EQUITY_FUND_MARKERS = (
    "debt", "liquid", "gilt", "bond", "money", "credit", "corporate",
    "overnight", "ultra short", "short duration", "banking and psu",
    "gold", "silver", "commodity", "international", "global", "us ",
    "nasdaq", "overseas", "fund of fund", "fof", "conservative hybrid",
)


def is_equity_oriented(category: str) -> bool:
    """Whether a fund category is equity-oriented for capital-gains purposes."""
    cat = (category or "").strip().lower()
    if not cat:
        return True
    for marker in _NON_EQUITY_FUND_MARKERS:
        if marker in cat:
            return False
    for marker in _EQUITY_FUND_MARKERS:
        if marker in cat:
            return True
    return True


def long_term_days(equity: bool) -> int:
    return LONG_TERM_DAYS if equity else LONG_TERM_DAYS_NON_EQUITY


# ══════════════════════════════════════════════════════════════
#  ASSET CATEGORIES
# ══════════════════════════════════════════════════════════════
#
# Four buckets, because they are the four things a user actually rebalances
# BETWEEN. They are not the tax classification and must not be confused with
# it: a gold fund and a debt fund are both non-equity in the Act but they are
# not interchangeable in a portfolio, and an arbitrage fund is equity for tax
# while behaving like cash. `is_equity_oriented` answers the tax question;
# this answers the allocation one.

CAT_STOCKS = "stocks"
CAT_FUNDS = "mutual_funds"
CAT_GOLD = "gold"
CAT_DEBT = "debt"
CATEGORIES = (CAT_STOCKS, CAT_FUNDS, CAT_GOLD, CAT_DEBT)

CATEGORY_LABELS = {
    CAT_STOCKS: "Stocks",
    CAT_FUNDS: "Mutual Funds",
    CAT_GOLD: "Gold",
    CAT_DEBT: "Debt",
}

# Precious metals travel together. Silver is not gold, but a silver ETF put in
# with the equity funds would be banded against an equity sleeve it has nothing
# to do with, which is the more wrong of the two answers.
_GOLD_MARKERS = ("gold", "goldbees", "silver", "silverbees", "precious",
                 "sovereign gold", "sgb")
_DEBT_MARKERS = (
    "debt", "liquid", "liquidbees", "gilt", "bond", "money market",
    "credit risk", "corporate bond", "overnight", "ultra short",
    "short duration", "medium duration", "long duration", "banking and psu",
    "dynamic bond", "floater", "income fund", "psu debt", "target maturity",
)


def classify_category(name: str = "", category: str = "",
                      *, is_fund: bool) -> str:
    """Which of the four buckets a holding belongs in.

    `is_fund` decides only the DEFAULT. A gold ETF is a listed stock and a
    liquid ETF is a listed stock, but neither belongs with the direct equity —
    so the markers are checked for both, and only what matches nothing falls
    back to stocks-or-funds.
    """
    text = f"{category or ''} {name or ''}".strip().lower()
    for marker in _GOLD_MARKERS:
        if marker in text:
            return CAT_GOLD
    for marker in _DEBT_MARKERS:
        if marker in text:
            return CAT_DEBT
    return CAT_FUNDS if is_fund else CAT_STOCKS


def _surcharge_pct(gain: float) -> float:
    for threshold, pct in SURCHARGE_BANDS:
        if gain > threshold:
            return min(pct, SURCHARGE_CAP_PCT)
    return 0.0


def capital_gains_tax(gain: float, *, long_term: bool, equity: bool,
                      residency: str = NRI,
                      exemption_left: float = 0.0, tax_rates: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Tax on one realised gain, with the exemption actually consumed.

    Returns `exemption_used` so a caller walking several lots can subtract it
    and stop double-spending a single ₹1.25L allowance across the whole plan —
    which is how a rebalance that looks free on paper arrives with a bill.
    A loss returns zero tax and is reported as such; it is not netted off here
    because set-off rules depend on the rest of the year's disposals.
    """
    if gain <= 0:
        return {"gain": round(gain, 2), "taxable": 0.0, "base": 0.0,
                "surcharge": 0.0, "cess": 0.0, "total": 0.0,
                "rate_pct": 0.0, "exemption_used": 0.0,
                "is_loss": gain < 0}

    taxable = gain
    exemption_used = 0.0
    if equity and long_term and exemption_left > 0:
        exemption_used = min(gain, exemption_left)
        taxable = gain - exemption_used

    if equity:
        rate = EQUITY_LTCG_PCT if long_term else EQUITY_STCG_PCT
    else:
        rate = NON_EQUITY_LTCG_PCT if long_term else NON_EQUITY_STCG_PCT

    rate = (tax_rates or {}).get(("equity" if equity else "non_equity") + ("_long_term" if long_term else "_short_term"), rate)
    base = taxable * rate / 100.0
    surcharge = base * _surcharge_pct(gain) / 100.0
    cess = (base + surcharge) * CESS_PCT / 100.0
    total = base + surcharge + cess
    return {
        "gain": round(gain, 2),
        "taxable": round(taxable, 2),
        "base": round(base, 2),
        "surcharge": round(surcharge, 2),
        "cess": round(cess, 2),
        "total": round(total, 2),
        "rate_pct": rate,
        "effective_pct": round(total / gain * 100.0, 2) if gain else 0.0,
        "exemption_used": round(exemption_used, 2),
        # For an NRI this is not a bill to settle later: the broker or AMC
        # withholds it, so the cash never arrives.
        "withheld_at_source": residency == NRI,
        "is_loss": False,
    }


# ══════════════════════════════════════════════════════════════
#  LOTS
# ══════════════════════════════════════════════════════════════

def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def open_lots(txns: Iterable[Dict[str, Any]], as_of: date, *,
              equity: bool = True) -> List[Dict[str, Any]]:
    """FIFO-match sells against buys and return what is still held.

    Undated rows are dropped rather than guessed at: a lot with no date has no
    holding period, and inventing one would put units in the wrong tax bucket.
    """
    buys: List[Dict[str, Any]] = []
    rows = []
    for t in txns or []:
        when = _as_date(t.get("date") or t.get("executed_at"))
        qty = float(t.get("qty") or t.get("units") or 0)
        if when is None or qty <= 0:
            continue
        side = str(t.get("type") or t.get("side") or "").upper()
        if not side:
            side = "SELL" if float(t.get("redeemed") or 0) > 0 else "BUY"
        price = float(t.get("price") or t.get("nav") or 0)
        rows.append((when, side, qty, price))
    rows.sort(key=lambda r: r[0])

    for when, side, qty, price in rows:
        if side.startswith("B") or side in ("PURCHASE", "SIP"):
            buys.append({"date": when, "qty": qty, "price": price})
            continue
        remaining = qty
        for lot in buys:
            if remaining <= 0:
                break
            take = min(lot["qty"], remaining)
            lot["qty"] -= take
            remaining -= take
        buys = [lot for lot in buys if lot["qty"] > 1e-9]

    horizon = long_term_days(equity)
    out = []
    for lot in buys:
        held = (as_of - lot["date"]).days
        out.append({
            "date": lot["date"].isoformat(),
            "qty": round(lot["qty"], 4),
            "price": round(lot["price"], 4),
            "days_held": held,
            "long_term": held > horizon,
            "days_to_long_term": max(0, horizon + 1 - held),
        })
    return out


def synthetic_lot(qty: float, price: float, as_of: date,
                  since: Any = None, *, equity: bool = True) -> List[Dict]:
    """One lot standing in for a position with no transaction history.

    Marked short-term unless a date is supplied, because assuming the cheaper
    tax rate on unknown units is the expensive direction to be wrong in.
    """
    when = _as_date(since) or as_of
    held = (as_of - when).days
    horizon = long_term_days(equity)
    return [{
        "date": when.isoformat(),
        "qty": round(qty, 4),
        "price": round(price, 4),
        "days_held": held,
        "long_term": held > horizon,
        "days_to_long_term": max(0, horizon + 1 - held),
        "assumed": True,
    }]


def plan_lot_sale(lots: List[Dict[str, Any]], units_wanted: float,
                  price: float, *, equity: bool, residency: str,
                  exemption_left: float, tax_rates: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Choose which units to sell, cheapest tax first, and price the decision.

    Long-term lots go first — same units, same rupees, a materially smaller
    bill — then short-term lots oldest-first so the remaining inventory keeps
    ripening. Lots inside RIPENING_WINDOW_DAYS of maturing are reported as
    deferrable so the caller can offer "wait N days" instead of taxing them.
    """
    ordered = sorted(
        lots, key=lambda l: (not l["long_term"], l["date"]))
    remaining = units_wanted
    picked: List[Dict[str, Any]] = []
    tax_total = 0.0
    gain_total = 0.0
    exemption = exemption_left
    deferrable_units = 0.0
    soonest_ripe = None

    for lot in ordered:
        if remaining <= 1e-9:
            if not lot["long_term"] and lot["days_to_long_term"] <= RIPENING_WINDOW_DAYS:
                soonest_ripe = min(soonest_ripe or 10**6, lot["days_to_long_term"])
            continue
        take = min(lot["qty"], remaining)
        remaining -= take
        gain = (price - lot["price"]) * take
        tax = capital_gains_tax(gain, long_term=lot["long_term"], equity=equity,
                                residency=residency, exemption_left=exemption, tax_rates=tax_rates)
        exemption = max(0.0, exemption - tax["exemption_used"])
        tax_total += tax["total"]
        gain_total += gain
        if not lot["long_term"] and lot["days_to_long_term"] <= RIPENING_WINDOW_DAYS:
            deferrable_units += take
            soonest_ripe = min(soonest_ripe or 10**6, lot["days_to_long_term"])
        picked.append({
            "lot_date": lot["date"],
            "units": round(take, 4),
            "buy_price": lot["price"],
            "days_held": lot["days_held"],
            "long_term": lot["long_term"],
            "gain": round(gain, 2),
            "tax": tax["total"],
            "days_to_long_term": lot["days_to_long_term"],
        })

    proceeds = (units_wanted - remaining) * price
    return {
        "units": round(units_wanted - remaining, 4),
        "units_short": round(remaining, 4),
        "proceeds": round(proceeds, 2),
        "gain": round(gain_total, 2),
        "tax": round(tax_total, 2),
        "net_proceeds": round(proceeds - tax_total, 2),
        "exemption_left": round(exemption, 2),
        "lots": picked,
        # Actionable, not decorative: this is the "sell it next month instead"
        # number, and it is usually worth more than the drift it leaves.
        "deferrable_units": round(deferrable_units, 4),
        "days_to_defer": soonest_ripe,
    }


# ══════════════════════════════════════════════════════════════
#  MARKET BOOM
# ══════════════════════════════════════════════════════════════
#
# "Rebalance during a boom" needs a definition that cannot be argued with after
# the fact, otherwise it becomes "rebalance when it feels high" — which in
# practice means selling after the fall. Five independent readings, each a
# plain threshold on data already on the tape. Three of five is a boom.

BOOM_NEAR_HIGH_PCT = 2.0        # benchmark within 2% of its 52-week high
BOOM_RSI = 70.0                 # 14-day RSI in overbought territory
BOOM_ABOVE_DMA200_PCT = 12.0    # stretched this far above its 200 DMA
BOOM_YEAR_GAIN_PCT = 20.0       # a year (or YTD) this strong
BOOM_BREADTH_PCT = 60.0         # this share of indices also near their highs
BOOM_BREADTH_NEAR_PCT = 5.0
BOOM_SIGNALS_REQUIRED = 3
BENCHMARK_SYMBOL = "^NSEI"


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN check


def _lead_row(tape: Optional[Dict[str, Any]], benchmark: str):
    """The benchmark row and every usable row, or (None, []) if the feed is dead."""
    rows = (tape or {}).get("indices") or []
    usable = [r for r in rows if r.get("status") == "ok"]
    if not usable:
        return None, []
    lead = next((r for r in usable if r.get("symbol") == benchmark), usable[0])
    return lead, usable


def _year_change(row: Dict[str, Any]) -> Optional[float]:
    """One-year change, falling back to year-to-date.

    The tape does not carry `chg_1y_pct` today, so in practice this reads YTD.
    Written as a fallback rather than as YTD outright so the signal upgrades
    itself the day a one-year column is added.
    """
    year = _num(row.get("chg_1y_pct"))
    return year if year is not None else _num(row.get("chg_ytd_pct"))


def _score(signals: List[Dict[str, Any]], required: int):
    score = sum(1 for s in signals if s["hit"])
    known = sum(1 for s in signals if s["known"])
    return score, known, score >= required


def market_boom(tape: Optional[Dict[str, Any]],
                benchmark: str = BENCHMARK_SYMBOL,
                *, year_gain_pct: float = BOOM_YEAR_GAIN_PCT) -> Dict[str, Any]:
    """Score the market's heat from the index tape.

    `year_gain_pct` is the "market up 15%" / "market up 20%" dial. It is a
    parameter rather than a constant because where the user puts it changes
    whether this reading fires at all, and that is a policy choice, not a fact
    about the market.

    Returns `boom=False` with `available=False` when the tape cannot answer,
    which is a different fact from a calm market and must not be allowed to
    read as one — a missing feed should never silently suppress a trigger the
    user asked for.
    """
    lead, usable = _lead_row(tape, benchmark)
    if lead is None:
        return {"available": False, "boom": False, "score": 0,
                "required": BOOM_SIGNALS_REQUIRED, "signals": [],
                "heat": "unknown", "year_gain_pct": year_gain_pct,
                "reason": "No index data, so market heat is unknown."}

    signals = []

    def add(name: str, hit: Optional[bool], detail: str):
        signals.append({"name": name, "hit": bool(hit),
                        "known": hit is not None, "detail": detail})

    off_high = _num(lead.get("off_high_pct"))
    add("near_52w_high",
        None if off_high is None else off_high <= BOOM_NEAR_HIGH_PCT,
        f"{lead.get('label', benchmark)} is {off_high:.1f}% off its 52-week high"
        if off_high is not None else "52-week high unknown")

    rsi = _num(lead.get("rsi_14"))
    add("overbought", None if rsi is None else rsi >= BOOM_RSI,
        f"RSI {rsi:.0f}" if rsi is not None else "RSI unknown")

    vs200 = _num(lead.get("vs_dma_200_pct"))
    add("stretched_above_200dma",
        None if vs200 is None else vs200 >= BOOM_ABOVE_DMA200_PCT,
        f"{vs200:+.1f}% vs its 200-day average"
        if vs200 is not None else "200 DMA unknown")

    year = _year_change(lead)
    add("strong_year", None if year is None else year >= year_gain_pct,
        f"{year:+.1f}% over the year (trigger at +{year_gain_pct:g}%)"
        if year is not None else "1-year change unknown")

    near = [r for r in usable if _num(r.get("off_high_pct")) is not None]
    breadth_pct = None
    if near:
        hits = sum(1 for r in near
                   if _num(r["off_high_pct"]) <= BOOM_BREADTH_NEAR_PCT)
        breadth_pct = hits / len(near) * 100.0
    add("broad_participation",
        None if breadth_pct is None else breadth_pct >= BOOM_BREADTH_PCT,
        f"{breadth_pct:.0f}% of indices within {BOOM_BREADTH_NEAR_PCT:.0f}% of their highs"
        if breadth_pct is not None else "breadth unknown")

    score, known, boom = _score(signals, BOOM_SIGNALS_REQUIRED)
    heat = ("euphoric" if score >= 5 else "boom" if boom
            else "warm" if score == 2 else "calm")
    return {
        "available": True,
        "boom": boom,
        "score": score,
        "known_signals": known,
        "required": BOOM_SIGNALS_REQUIRED,
        "heat": heat,
        "year_gain_pct": year_gain_pct,
        "benchmark": lead.get("label") or lead.get("symbol"),
        "signals": signals,
        "reason": (f"{score} of {known} boom signals are firing."
                   if known else "No boom signal could be read."),
    }


# ══════════════════════════════════════════════════════════════
#  MARKET CRASH
# ══════════════════════════════════════════════════════════════
#
# The mirror of the boom test, and it exists for the opposite trade. A boom is
# when the ceiling is worth enforcing; a crash is when the FLOOR is, because
# what a fall does to a portfolio is push the winners back into their band and
# the survivors below it. Rebalancing into a crash is buying the underweight,
# which is the half of the discipline nobody enjoys and the half that pays.
#
# Deliberately NOT the same thing as `market_status == "attractive"` on the
# tape: that ladder cuts one index on drawdown alone, while this asks whether
# the whole market is down, oversold, below trend and broadly weak at once.

CRASH_DRAWDOWN_PCT = 15.0       # benchmark this far below its 52-week high
CRASH_RSI = 35.0                # 14-day RSI in oversold territory
CRASH_BELOW_DMA200_PCT = 5.0    # trading this far under its 200 DMA
CRASH_YEAR_LOSS_PCT = 10.0      # a year (or YTD) this weak
CRASH_BREADTH_PCT = 60.0        # this share of indices also in a real drawdown
CRASH_BREADTH_OFF_PCT = 12.0
CRASH_SIGNALS_REQUIRED = 3


def market_crash(tape: Optional[Dict[str, Any]],
                 benchmark: str = BENCHMARK_SYMBOL,
                 *, drop_pct: float = CRASH_DRAWDOWN_PCT) -> Dict[str, Any]:
    """Score how far the market has fallen, on the same five-reading pattern.

    `drop_pct` is the "market down 15%" / "market down 20%" dial. As with the
    boom, `available=False` means the tape could not answer — never that the
    market is fine.
    """
    lead, usable = _lead_row(tape, benchmark)
    if lead is None:
        return {"available": False, "crash": False, "score": 0,
                "required": CRASH_SIGNALS_REQUIRED, "signals": [],
                "severity": "unknown", "drop_pct": drop_pct,
                "reason": "No index data, so a market fall cannot be measured."}

    signals = []

    def add(name: str, hit: Optional[bool], detail: str):
        signals.append({"name": name, "hit": bool(hit),
                        "known": hit is not None, "detail": detail})

    off_high = _num(lead.get("off_high_pct"))
    add("deep_drawdown",
        None if off_high is None else off_high >= drop_pct,
        f"{lead.get('label', benchmark)} is {off_high:.1f}% off its 52-week high "
        f"(trigger at {drop_pct:g}%)"
        if off_high is not None else "52-week high unknown")

    rsi = _num(lead.get("rsi_14"))
    add("oversold", None if rsi is None else rsi <= CRASH_RSI,
        f"RSI {rsi:.0f}" if rsi is not None else "RSI unknown")

    vs200 = _num(lead.get("vs_dma_200_pct"))
    add("below_200dma",
        None if vs200 is None else vs200 <= -CRASH_BELOW_DMA200_PCT,
        f"{vs200:+.1f}% vs its 200-day average"
        if vs200 is not None else "200 DMA unknown")

    year = _year_change(lead)
    add("weak_year", None if year is None else year <= -CRASH_YEAR_LOSS_PCT,
        f"{year:+.1f}% over the year" if year is not None
        else "1-year change unknown")

    off = [r for r in usable if _num(r.get("off_high_pct")) is not None]
    breadth_pct = None
    if off:
        hits = sum(1 for r in off
                   if _num(r["off_high_pct"]) >= CRASH_BREADTH_OFF_PCT)
        breadth_pct = hits / len(off) * 100.0
    add("broad_weakness",
        None if breadth_pct is None else breadth_pct >= CRASH_BREADTH_PCT,
        f"{breadth_pct:.0f}% of indices are {CRASH_BREADTH_OFF_PCT:.0f}%+ "
        "off their highs"
        if breadth_pct is not None else "breadth unknown")

    score, known, crash = _score(signals, CRASH_SIGNALS_REQUIRED)
    severity = ("capitulation" if score >= 5 else "crash" if crash
                else "correction" if score == 2 else "stable")
    return {
        "available": True,
        "crash": crash,
        "score": score,
        "known_signals": known,
        "required": CRASH_SIGNALS_REQUIRED,
        "severity": severity,
        "drop_pct": drop_pct,
        "benchmark": lead.get("label") or lead.get("symbol"),
        "signals": signals,
        "reason": (f"{score} of {known} crash signals are firing."
                   if known else "No crash signal could be read."),
    }


# The Nifty's long-run realised volatility sits around 13–16% annualised, and
# spends most of its time under 20%. A trigger at 22% therefore fires in a
# genuinely disturbed tape rather than in an ordinary quarter.
DEFAULT_VOL_TRIGGER_PCT = 22.0


def market_volatility(tape: Optional[Dict[str, Any]],
                      benchmark: str = BENCHMARK_SYMBOL,
                      *, threshold_pct: float = DEFAULT_VOL_TRIGGER_PCT
                      ) -> Dict[str, Any]:
    """Annualised realised volatility on the benchmark, against a threshold.

    Its own reading rather than a boom/crash signal because volatility does not
    have a direction: it spikes at tops and at bottoms, and what it argues for
    is a wider tolerance and fewer trades, not a trim or an add.
    """
    lead, _ = _lead_row(tape, benchmark)
    vol = _num((lead or {}).get("vol_30d_pct"))
    if vol is None:
        return {"available": False, "elevated": False, "vol_pct": None,
                "threshold_pct": threshold_pct,
                "reason": "No volatility reading on the tape."}
    return {
        "available": True,
        "elevated": vol >= threshold_pct,
        "vol_pct": vol,
        "threshold_pct": threshold_pct,
        "benchmark": (lead or {}).get("label") or benchmark,
        "reason": (f"{(lead or {}).get('label', benchmark)} is running at "
                   f"{vol:.1f}% annualised volatility "
                   f"(trigger at {threshold_pct:g}%)."),
    }


# ══════════════════════════════════════════════════════════════
#  TRIGGERS
# ══════════════════════════════════════════════════════════════

# Every rule that can open the book, and which of them stand switched on when
# the user has not said otherwise. The four defaults-off ones all need a
# threshold that only the user can supply, and firing them against a guessed
# percentage would be worse than not offering them.
TRIGGER_CALENDAR = "calendar"
TRIGGER_BOOM = "market_boom"
TRIGGER_CRASH = "market_crash"
TRIGGER_BAND = "band_breach"
TRIGGER_DEVIATION = "allocation_deviation"
TRIGGER_GAIN = "portfolio_gain"
TRIGGER_LOSS = "portfolio_loss"
TRIGGER_VOLATILITY = "volatility"
TRIGGER_MATURED = "holding_matured"

ALL_TRIGGERS = (TRIGGER_CALENDAR, TRIGGER_BOOM, TRIGGER_CRASH, TRIGGER_BAND,
                TRIGGER_DEVIATION, TRIGGER_GAIN, TRIGGER_LOSS,
                TRIGGER_VOLATILITY, TRIGGER_MATURED)
DEFAULT_TRIGGERS = (TRIGGER_CALENDAR, TRIGGER_BOOM, TRIGGER_CRASH,
                    TRIGGER_BAND, TRIGGER_DEVIATION, TRIGGER_MATURED)

TRIGGER_LABELS = {
    # Not a switchable rule, but it still needs a name: without this the
    # baseline run is announced to the user as "first_run".
    "first_run": "First run",
    TRIGGER_CALENDAR: "Calendar review",
    TRIGGER_BOOM: "Market boom",
    TRIGGER_CRASH: "Market crash",
    TRIGGER_BAND: "Band breach",
    TRIGGER_DEVIATION: "Allocation drift",
    TRIGGER_GAIN: "Portfolio gain",
    TRIGGER_LOSS: "Portfolio loss",
    TRIGGER_VOLATILITY: "Volatility",
    TRIGGER_MATURED: "Holding matured",
}

# Who decides that the book opens. In AUTO the triggers do, and a plan with
# nothing firing is reported as not due. In MANUAL the user has said "look
# now" and the plan is always produced — the recommendations are identical
# either way, because what to trade is a fact about the portfolio and only
# WHETHER to trade today is a matter of policy.
MODE_AUTO = "auto"
MODE_MANUAL = "manual"


# ══════════════════════════════════════════════════════════════
#  STRATEGY PRESETS
# ══════════════════════════════════════════════════════════════
#
# The ten strategies from the 2011-2026 backtest, plus the master assembled
# from the mechanisms that replicated, exposed as selectable policies. A preset
# sets three things and nothing else:
#
#   trim_pct        the ceiling at which a holding is trimmed back to its
#                   target, or None for a strategy that never sells
#   deploy          the ORDER in which underweights are funded
#   reinvest_income whether accrued dividends are treated as money to deploy
#
# `measured` carries the backtested result so the UI can show what each rule
# actually did. Those figures come from a MONTHLY Rs 10,000 contribution into a
# ten-stock NSE basket, 2011-2026, after NRI tax — they are the record of that
# basket on that path, NOT a forecast for the user's own portfolio, and the UI
# has to say so wherever it prints them.

DEPLOY_EQUAL = "equal"
DEPLOY_GAP = "gap"
DEPLOY_MOMENTUM = "momentum"
DEPLOY_LAGGARD = "laggard"
# How each order reads in a sentence. One copy, because the preset card and
# the reason on a funded row have to say the same thing.
# How many names a tilt concentrates into. Three is the study's own figure —
# S5 fed the three best performers and S9 the three worst.
TILT_PICKS = 3
DEPLOY_LABELS = {
    DEPLOY_GAP: "largest shortfall first",
    DEPLOY_LAGGARD: "weakest return on cost first",
    DEPLOY_MOMENTUM: "strongest return on cost first",
    DEPLOY_EQUAL: "evenly, in name order",
}
STRATEGY_CUSTOM = "CUSTOM"
# S10 is the default because it was the best of the ten on the measured
# schedule. M1 beat it there but lost on an annual calendar, so it is offered
# rather than defaulted to.
DEFAULT_STRATEGY = "M4"

STRATEGIES = [
    {"id": "S1", "name": "Equal buying", "trim_pct": None,
     "deploy": DEPLOY_EQUAL, "reinvest_income": False,
     "tagline": "Split new money equally across every holding. Never sells.",
     "measured": {"xirr_pct": 13.33, "sells": 0}},
    {"id": "S2", "name": "Cash-flow rebalance", "trim_pct": None,
     "deploy": DEPLOY_GAP, "reinvest_income": False,
     "tagline": "Send new money to whatever is furthest below target. "
                "Never sells.",
     "measured": {"xirr_pct": 14.20, "sells": 0}},
    {"id": "S3", "name": "Band rebalance", "trim_pct": 12.5,
     "deploy": DEPLOY_GAP, "reinvest_income": False,
     "tagline": "Trim anything above 12.5% back to target, then fund the "
                "underweights.",
     "measured": {"xirr_pct": 13.80, "sells": 40}},
    {"id": "S4", "name": "Price-rule proxy", "trim_pct": 10.0,
     "deploy": DEPLOY_GAP, "reinvest_income": False,
     "tagline": "Trim hard on any large gain. The most active rule, and the "
                "worst measured.",
     "measured": {"xirr_pct": 10.74, "sells": 120}},
    {"id": "S5", "name": "Momentum tilt", "trim_pct": None,
     "deploy": DEPLOY_MOMENTUM, "reinvest_income": False,
     "tagline": "Fund the strongest performers first. Never sells.",
     "measured": {"xirr_pct": 11.27, "sells": 0}},
    {"id": "S6", "name": "Cash-flow + dividends", "trim_pct": None,
     "deploy": DEPLOY_GAP, "reinvest_income": True,
     "tagline": "S2, plus put the dividends back to work. Never sells.",
     "measured": {"xirr_pct": 15.82, "sells": 0}},
    {"id": "S7", "name": "Wide band 20%", "trim_pct": 20.0,
     "deploy": DEPLOY_GAP, "reinvest_income": False,
     "tagline": "Trim only past 20%, so a winner is left to run.",
     "measured": {"xirr_pct": 14.44, "sells": 3}},
    {"id": "S8", "name": "Band 12.5% + dividends", "trim_pct": 12.5,
     "deploy": DEPLOY_GAP, "reinvest_income": True,
     "tagline": "Best before tax, and not after it — the trims are taxed.",
     "measured": {"xirr_pct": 15.19, "sells": 32}},
    {"id": "S9", "name": "Laggard tilt", "trim_pct": None,
     "deploy": DEPLOY_LAGGARD, "reinvest_income": False,
     "tagline": "Fund the weakest performers first. Never sells.",
     "measured": {"xirr_pct": 14.99, "sells": 0}},
    {"id": "S10", "name": "Wide band + dividends", "trim_pct": 20.0,
     "deploy": DEPLOY_GAP, "reinvest_income": True,
     "tagline": "Reinvest income, trim only past 20%. Best of the ten on the "
                "measured schedule.",
     "measured": {"xirr_pct": 15.97, "sells": 3}},
    {"id": "M1", "name": "Master", "trim_pct": 25.0,
     "deploy": DEPLOY_LAGGARD, "reinvest_income": True,
     "tagline": "Reinvest income, fund the weakest first, cap at 25%. Best "
                "measured — but its edge did not survive an annual schedule.",
     "measured": {"xirr_pct": 16.53, "sells": 1}},
    {"id": "M2", "name": "Master control: shortfall order", "trim_pct": 25.0,
     "deploy": DEPLOY_GAP, "reinvest_income": True,
     "tagline": "M1 with the money offered to the biggest shortfall instead "
                "of the weakest name. Isolates what the ordering is worth.",
     "measured": {"xirr_pct": 16.32, "sells": 1}},
    {"id": "M3", "name": "Master control: no cap", "trim_pct": None,
     "deploy": DEPLOY_LAGGARD, "reinvest_income": True,
     "tagline": "M1 with no ceiling at all. Never sells, and still beats "
                "every band narrower than 20%.",
     "measured": {"xirr_pct": 16.31, "sells": 0}},
    {"id": "M4", "name": "Master + peak guard", "trim_pct": 25.0,
     "deploy": DEPLOY_LAGGARD, "reinvest_income": True, "peak_guard": True,
     "tagline": "M1, but it refuses to trim a holding already well below its "
                "own 12-month high. Best measured of all sixteen.",
     "measured": {"xirr_pct": 17.05, "sells": 1}},
    {"id": "M5", "name": "Tight band + peak guard", "trim_pct": 12.5,
     "deploy": DEPLOY_LAGGARD, "reinvest_income": True, "peak_guard": True,
     "tagline": "The guard on a 12.5% band, where it fires 33 times. Weaker "
                "than M4, but the guard's evidence here is far stronger.",
     "measured": {"xirr_pct": 15.53, "sells": 31}},
    {"id": "M6", "name": "Tight band, no guard", "trim_pct": 12.5,
     "deploy": DEPLOY_LAGGARD, "reinvest_income": True,
     "tagline": "M5 without the guard — the control that shows trading more "
                "costs more than it earns.",
     "measured": {"xirr_pct": 15.42, "sells": 37}},
    {"id": STRATEGY_CUSTOM, "name": "Custom", "trim_pct": None,
     "deploy": DEPLOY_GAP, "reinvest_income": False,
     "tagline": "Your own band and triggers, set with the sliders below.",
     "measured": None},
]

# Rank by what the backtest measured AFTER TAX, best first. Computed rather
# than written down: a hand-kept rank goes stale the first time a measured
# figure is corrected, and then the screen argues with itself.
for _s in STRATEGIES:
    _s.setdefault("peak_guard", False)
for _rank, _s in enumerate(
        sorted((x for x in STRATEGIES if x.get("measured")),
               key=lambda x: -x["measured"]["xirr_pct"]), 1):
    _s["rank"] = _rank
    _s["rank_of"] = sum(1 for x in STRATEGIES if x.get("measured"))
for _s in STRATEGIES:
    _s.setdefault("rank", None)
    _s.setdefault("rank_of", sum(1 for x in STRATEGIES if x.get("measured")))

STRATEGY_BY_ID = {s["id"]: s for s in STRATEGIES}


def get_strategy(strategy_id: Optional[str]) -> Dict[str, Any]:
    """The named preset, or the default when the id is unknown or missing."""
    return STRATEGY_BY_ID.get(strategy_id or "",
                              STRATEGY_BY_ID[DEFAULT_STRATEGY])


def due_triggers(as_of: date, *, last_rebalanced: Any = None,
                 cadence: str = "semiannual",
                 boom: Optional[Dict[str, Any]] = None,
                 crash: Optional[Dict[str, Any]] = None,
                 volatility: Optional[Dict[str, Any]] = None,
                 breaches: int = 0,
                 matured: int = 0,
                 drifted: int = 0,
                 worst_drift_pct: float = 0.0,
                 portfolio_gain_pct: Optional[float] = None,
                 gain_trigger_pct: Optional[float] = None,
                 loss_trigger_pct: Optional[float] = None,
                 enabled: Optional[Iterable[str]] = None,
                 mode: str = MODE_AUTO,
                 band: Optional[Tuple[float, float]] = None) -> Dict[str, Any]:
    """Which of the standing rules say the book should be opened today.

    Every rule is reported in `considered` whether it fired or not, and with
    whether it was even switched on. A trigger that is off and a trigger that
    is on and quiet are different states, and collapsing them is how a user
    ends up believing a crash rule is watching the market when it is not.
    """
    switched_on = set(ALL_TRIGGERS if enabled is None else enabled)
    low, high = band or (MIN_WEIGHT_PCT, MAX_WEIGHT_PCT)
    window = CADENCES.get(cadence, SEMIANNUAL_DAYS)
    last = _as_date(last_rebalanced)
    days_since = (as_of - last).days if last else None
    considered: List[Dict[str, Any]] = []

    def rule(name: str, hit: bool, detail: str, *, always_on: bool = False):
        on = always_on or name in switched_on
        considered.append({"name": name, "hit": bool(hit and on), "enabled": on,
                           "label": TRIGGER_LABELS.get(name, name),
                           "detail": detail})

    if last is None:
        # Not a rule the user can switch off: with no baseline there is
        # nothing to measure drift or a calendar window against.
        rule("first_run", True,
             "No rebalance on record, so this is the baseline.", always_on=True)
    else:
        rule(TRIGGER_CALENDAR, days_since >= window,
             f"{days_since} days since the last rebalance (every {window}).")

    rule(TRIGGER_BOOM, bool(boom and boom.get("boom")),
         (boom or {}).get("reason", "Market heat not measured."))
    rule(TRIGGER_CRASH, bool(crash and crash.get("crash")),
         (crash or {}).get("reason", "Market fall not measured."))
    rule(TRIGGER_BAND, bool(breaches),
         f"{breaches} position(s) outside the {low:g}–{high:g}% band."
         if breaches else f"Every position is inside {low:g}–{high:g}%.")
    rule(TRIGGER_DEVIATION, bool(drifted),
         f"{drifted} categor{'y' if drifted == 1 else 'ies'} off target by up "
         f"to {worst_drift_pct:.1f} points." if drifted
         else "Every category is inside its allowed drift.")

    gain_hit = (portfolio_gain_pct is not None and gain_trigger_pct is not None
                and portfolio_gain_pct >= gain_trigger_pct)
    rule(TRIGGER_GAIN, gain_hit,
         f"Portfolio is {portfolio_gain_pct:+.1f}% against a "
         f"+{gain_trigger_pct:g}% trigger."
         if portfolio_gain_pct is not None and gain_trigger_pct is not None
         else "No gain trigger set.")

    loss_hit = (portfolio_gain_pct is not None and loss_trigger_pct is not None
                and portfolio_gain_pct <= -abs(loss_trigger_pct))
    rule(TRIGGER_LOSS, loss_hit,
         f"Portfolio is {portfolio_gain_pct:+.1f}% against a "
         f"-{abs(loss_trigger_pct):g}% trigger."
         if portfolio_gain_pct is not None and loss_trigger_pct is not None
         else "No loss trigger set.")

    rule(TRIGGER_VOLATILITY, bool(volatility and volatility.get("elevated")),
         (volatility or {}).get("reason", "Volatility not measured."))

    rule(TRIGGER_MATURED, bool(matured),
         f"{matured} position(s) hold long-term units that can be trimmed at "
         "the lower rate." if matured
         else "No position is holding matured units worth trimming.")

    fired = [{"name": r["name"], "label": r["label"], "detail": r["detail"]}
             for r in considered if r["hit"]]
    # The calendar rule carries its cadence in its name for the UI's benefit,
    # and because "calendar" alone does not say which window elapsed.
    for f in fired:
        if f["name"] == TRIGGER_CALENDAR:
            f["name"] = f"calendar_{cadence}"

    next_due = (last + timedelta(days=window)).isoformat() if last else None
    return {
        "due": bool(fired) or mode == MODE_MANUAL,
        "mode": mode,
        "fired": fired,
        "considered": considered,
        "enabled": sorted(switched_on),
        "cadence": cadence,
        "window_days": window,
        "days_since_last": days_since,
        "next_calendar_due": next_due,
    }


# ══════════════════════════════════════════════════════════════
#  SLEEVE PLAN
# ══════════════════════════════════════════════════════════════

def clamp_band(min_pct: Any, max_pct: Any) -> Tuple[float, float]:
    """Coerce a pair of slider values into a usable band.

    Both sliders run 0–100 independently, so nothing stops a user dragging the
    minimum above the maximum. Swapping beats rejecting: the intent is
    unambiguous and an error message here would just block the screen.
    """
    low = min(100.0, max(0.0, float(min_pct if min_pct is not None
                                    else MIN_WEIGHT_PCT)))
    high = min(100.0, max(0.0, float(max_pct if max_pct is not None
                                     else MAX_WEIGHT_PCT)))
    return (high, low) if low > high else (low, high)


def _band_verdict(weight_pct: float, low: float = MIN_WEIGHT_PCT,
                  high: float = MAX_WEIGHT_PCT) -> Tuple[str, Optional[float]]:
    if weight_pct > high + BAND_TOLERANCE_PCT:
        return "over", high
    if weight_pct < low - BAND_TOLERANCE_PCT:
        return "under", low
    return "within", None


def plan_sleeve(positions: List[Dict[str, Any]], *, as_of: date,
                sleeve: str, equity_for_tax: bool = True,
                residency: str = NRI,
                exemption_left: float = EQUITY_LTCG_EXEMPT,
                min_weight_pct: float = MIN_WEIGHT_PCT,
                max_weight_pct: float = MAX_WEIGHT_PCT,
                asset_limits: Optional[Dict[str, float]] = None,
                long_term_only: bool = False,
                tax_rates: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Price every band breach in one sleeve.

    `positions` need `key`, `value`, `price`, `units` and either `lots` or
    enough to synthesise one. Weights are of THIS sleeve, not of the whole
    portfolio: a 10% cap on the total book would let one stock be most of the
    stock sleeve and still pass.
    """
    low, high = clamp_band(min_weight_pct, max_weight_pct)
    total = sum(max(0.0, float(p.get("value") or 0)) for p in positions)
    held = sum(1 for p in positions if float(p.get("value") or 0) > 0)
    # A band has to be ACHIEVABLE before it can be enforced. N holdings must
    # sum to 100% of their own sleeve, so the smallest possible largest weight
    # is 100/N: a 10% ceiling is arithmetically impossible with fewer than ten
    # holdings, and with one holding it says "trim the only gold you own by
    # 90%" — which is what a per-asset band means when applied to a sleeve of
    # one. Widening the edges to what the count allows keeps the ceiling
    # meaningful in a large category and inert in a small one, instead of
    # generating a breach the user cannot possibly clear.
    if held:
        even = 100.0 / held
        high = max(high, even)
        low = min(low, even)
    actions: List[Dict[str, Any]] = []
    exemption = exemption_left
    matured = 0

    for p in positions:
        value = float(p.get("value") or 0)
        weight = (value / total * 100.0) if total > 0 else 0.0
        ceiling = float((asset_limits or {}).get(p.get("key"), high))
        verdict, edge = _band_verdict(weight, min(low, ceiling), ceiling)
        price = float(p.get("price") or 0)
        lots = p.get("lots") or []
        has_lt = any(l.get("long_term") for l in lots)
        if has_lt:
            matured += 1
        # Tax character is a property of the HOLDING, not of the sleeve. A gold
        # or international fund sitting in the equity sleeve is still non-equity
        # in the Act, and taxing it at the equity rate understates the bill by
        # more than half.
        equity = bool(p.get("equity_for_tax", equity_for_tax))

        row = {
            "key": p.get("key"),
            "name": p.get("name") or p.get("key"),
            "sleeve": sleeve,
            "value": round(value, 2),
            "price": round(price, 4),
            "weight_pct": round(weight, 2),
            "band": [min(low, ceiling), ceiling],
            "status": verdict,
            "equity_for_tax": equity,
            "has_long_term_units": has_lt,
            # What is actually HELD, and how much of it has aged past the
            # 365-day line. Without the second number a "Wait for long term"
            # row is an assertion the user cannot check: holding 100 with 10
            # long-term and holding 100 with 99 long-term read identically.
            "held_units": round(float(p.get("units") or 0), 4),
            "long_term_units": round(
                sum(l["qty"] for l in lots if l.get("long_term")), 4),
        }

        if verdict == "within" or total <= 0 or price <= 0:
            row.update({"action": "HOLD", "amount": 0.0, "units": 0.0,
                        "reason": "Inside its band."})
            actions.append(row)
            continue

        if p.get('selected') is False:
            row.update(action='SKIP', amount=0.0, units=0.0,
                       reason='Excluded from this rebalance; allocation still counts.')
            actions.append(row)
            continue
        target_value = total * edge / 100.0

        if verdict == "under":
            # Buying to the floor uses new money and realises nothing, so
            # there is no tax leg to compute — this is the cheap side of the
            # trade and the reason cash flow is directed here first.
            amount = target_value - value
            row.update({
                "action": "ADD" if amount >= MIN_TRADE_VALUE else "HOLD",
                "amount": round(amount, 2),
                "units": round(amount / price, 4),
                "target_weight_pct": edge,
                "reason": (f"{weight:.1f}% of the {sleeve} sleeve, below the "
                           f"{low:g}% floor."
                           if amount >= MIN_TRADE_VALUE else
                           "Below its floor, but the top-up is too small to trade."),
            })
            actions.append(row)
            continue

        # Over the ceiling: size the trim, then decide which units pay for it.
        amount = value - target_value
        if amount < MIN_TRADE_VALUE:
            row.update({"action": "HOLD", "amount": round(amount, 2),
                        "units": 0.0, "target_weight_pct": edge,
                        "reason": "Over its ceiling, but the trim is too small to trade."})
            actions.append(row)
            continue

        if long_term_only:
            eligible = []
            for lot in sorted(lots, key=lambda lot: lot['date']):
                if not lot.get('long_term'):
                    break
                eligible.append(lot)
            amount = min(amount, sum(lot['qty'] for lot in eligible) * price)
            lots = eligible
            if amount < MIN_TRADE_VALUE:
                row.update(action='WAIT', amount=0.0, units=0.0,
                           reason='Wait: insufficient verified long-term FIFO units. Short-term sales are disabled.',
                           note='Verify purchase dates before selling. Short-term or unknown-age holdings are protected.')
                actions.append(row)
                continue
        sale = plan_lot_sale(lots, amount / price, price, equity=equity,
                             residency=residency, exemption_left=exemption, tax_rates=tax_rates)
        exemption = sale["exemption_left"]
        row.update({
            "action": "TRIM",
            "amount": round(amount, 2),
            "units": sale["units"],
            "target_weight_pct": edge,
            "gain": sale["gain"],
            "tax": sale["tax"],
            "net_proceeds": sale["net_proceeds"],
            "lots": sale["lots"],
            "deferrable_units": sale["deferrable_units"],
            "days_to_defer": sale["days_to_defer"],
            "reason": (f"{weight:.1f}% of the {sleeve} sleeve, above the "
                       f"{ceiling:g}% ceiling."),
        })
        if sale["days_to_defer"] and sale["deferrable_units"] > 0:
            row["note"] = (
                f"{sale['deferrable_units']:g} of these units turn long-term in "
                f"{sale['days_to_defer']} days. Waiting drops their rate from "
                f"{EQUITY_STCG_PCT:g}% to {EQUITY_LTCG_PCT:g}%.")
        actions.append(row)

    return {
        "sleeve": sleeve,
        "total_value": round(total, 2),
        "positions": len(positions),
        "actions": actions,
        "band": [low, high],
        "breaches": sum(1 for a in actions if a["status"] != "within"),
        "matured_positions": matured,
        "exemption_left": round(exemption, 2),
    }


def _pnl_pct(value: float, invested: float) -> Optional[float]:
    """Gain/loss as a percentage of cost, or None when cost is unknown.

    None rather than 0.0: a holding whose cost never made it into the app has
    no return, and printing 0% would read as "flat" for something that may be
    up or down a third.
    """
    if invested <= 0:
        return None
    return round((value - invested) / invested * 100.0, 2)


def base_symbol(symbol: Any) -> str:
    """The company, without the exchange it happens to be quoted on.

    NSE and BSE listings of one company are one position. A Console tradebook
    writes IOC.NS where a Kite holding says IOC.BO, and matching the full
    ticker silently loses that holding's entire purchase history — which in
    turn means no verified long-term units, which in turn means the plan can
    never propose selling it.
    """
    return str(symbol or "").split(".")[0].strip().upper()


def _ledger_for(txns_by_symbol: Dict[str, List], symbol: Any) -> List:
    """This holding's transactions, whichever exchange they were filed under.

    The exact ticker wins when it is present. The base match is a fallback, and
    it is only taken when exactly one ledger claims that company — if the book
    holds both listings separately, merging them would double-count.
    """
    ledgers = txns_by_symbol or {}
    exact = ledgers.get(symbol)
    if exact:
        return exact
    base = base_symbol(symbol)
    hits = [rows for key, rows in ledgers.items()
            if base_symbol(key) == base and rows]
    return hits[0] if len(hits) == 1 else []


def _stock_positions(stocks: List[Dict[str, Any]], txns_by_symbol: Dict[str, List],
                     as_of: date) -> List[Dict[str, Any]]:
    out = []
    for s in stocks or []:
        symbol = s.get("symbol")
        shares = float(s.get("shares") or 0)
        if shares <= 0:
            continue
        price = float(s.get("current_price") or s.get("price") or 0)
        value = float(s.get("total_value") or 0) or shares * price
        lots = open_lots(_ledger_for(txns_by_symbol, symbol), as_of, equity=True)
        held = sum(l["qty"] for l in lots)
        if abs(held - shares) > max(1.0, shares * 0.02):
            # The ledger disagrees with the holding, so it cannot be trusted to
            # say which units are long-term. Fall back rather than tax a lot
            # that may not exist.
            lots = synthetic_lot(shares, float(s.get("avg_cost") or price),
                                 as_of, s.get("first_buy"), equity=True)
        invested = (float(s.get("invested") or 0)
                    or shares * float(s.get("avg_cost") or 0))
        # A gold or liquid ETF is a listed stock but it is not direct equity,
        # and banding it against the equity sleeve would mean nothing.
        category = classify_category(s.get("name") or "", symbol or "",
                                     is_fund=False)
        if category == CAT_GOLD:
            category = CAT_FUNDS
        out.append({
            "key": symbol, "name": s.get("name") or symbol,
            "value": value, "price": price, "units": shares, "lots": lots,
            "sector": s.get("sector"),
            "category": category,
            "equity_for_tax": category == CAT_STOCKS,
            "invested": round(invested, 2),
            "gain_pct": _pnl_pct(value, invested),
            "tradable": True,
        })
    return out


def _fund_positions(funds: List[Dict[str, Any]], as_of: date) -> List[Dict[str, Any]]:
    out = []
    for f in funds or []:
        units = float(f.get("units") or 0)
        nav = float(f.get("nav") or 0)
        value = float(f.get("current_value") or 0) or units * nav
        if value <= 0:
            continue
        category = f.get("category") or ""
        equity = is_equity_oriented(category + " " + str(f.get("scheme_name") or ""))
        lots = open_lots(f.get("transactions") or [], as_of, equity=equity)
        held = sum(l["qty"] for l in lots)
        if units > 0 and abs(held - units) > max(0.5, units * 0.02):
            lots = synthetic_lot(units, float(f.get("avg_nav") or nav), as_of,
                                 f.get("first_purchase"), equity=equity)
        name = f.get("scheme_name")
        invested = (float(f.get("invested") or 0)
                    or units * float(f.get("avg_nav") or 0))
        out.append({
            "key": name, "name": name,
            "value": value, "price": nav, "units": units, "lots": lots,
            "fund_category": category,
            "category": CAT_FUNDS,
            "equity_for_tax": equity,
            "invested": round(invested, 2),
            "gain_pct": _pnl_pct(value, invested),
            "tradable": True,
        })
    return out


def _manual_positions(manual_assets: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Gold and debt typed in on the allocation screen rather than held here.

    These count towards the category weights — leaving them out would make
    every other category look heavier than it is — but they carry no units, no
    price and no purchase date, so no priced trade can be proposed against
    them. They are marked `tradable=False` and the plan says so, rather than
    inventing a lot to sell.
    """
    out = []
    for category, amount in (manual_assets or {}).items():
        key = str(category).strip().lower()
        if key not in CATEGORIES:
            continue
        try:
            value = float(amount or 0)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        out.append({
            "key": f"manual:{key}",
            "name": f"{CATEGORY_LABELS[key]} (entered manually)",
            "value": value, "price": 0.0, "units": 0.0, "lots": [],
            "category": key,
            "equity_for_tax": False,
            "invested": 0.0,
            "gain_pct": None,
            "tradable": False,
        })
    return out


# ══════════════════════════════════════════════════════════════
#  CATEGORY ALLOCATION
# ══════════════════════════════════════════════════════════════
#
# The second of the two bands, and a different question from the first. The
# per-asset band asks "is any one holding too big a part of its own category";
# this asks "is the MIX still the mix I chose". Both have to hold: a portfolio
# can have every stock inside 2–10% of the stock sleeve while stocks have grown
# to 80% of the book, and it can have exactly the right four-way split while
# one name is a third of the equity.
#
# Note that the category band is a TOLERANCE AROUND A TARGET, not the same
# 0–100 min/max the per-asset sliders use. Four categories cannot each be held
# between 2% and 10% of the portfolio — that sums to at most 40% — so the only
# arithmetically coherent category band is target ± drift.

DEFAULT_CATEGORY_TARGETS = {
    CAT_STOCKS: 50.0,
    CAT_FUNDS: 30.0,
    CAT_GOLD: 10.0,
    CAT_DEBT: 10.0,
}
# How far a category may drift from its target before it is worth a trade, in
# PERCENTAGE POINTS of the whole book. Five points on a 50% target is a tenth
# of the sleeve, which is about where the drift outweighs the tax of fixing it.
DEFAULT_DEVIATION_PCT = 5.0


def normalise_targets(targets: Optional[Dict[str, Any]]) -> Tuple[Dict[str, float], bool]:
    """Coerce category targets into four numbers summing to 100.

    Rescaled rather than rejected: four sliders that add up to 96 express a
    perfectly clear intention, and a target set that does not sum to 100 makes
    every drift figure wrong by the shortfall.
    """
    raw = {}
    for cat in CATEGORIES:
        try:
            raw[cat] = max(0.0, float((targets or {}).get(
                cat, DEFAULT_CATEGORY_TARGETS[cat])))
        except (TypeError, ValueError):
            raw[cat] = DEFAULT_CATEGORY_TARGETS[cat]
    total = sum(raw.values())
    if total <= 0:
        return dict(DEFAULT_CATEGORY_TARGETS), True
    if abs(total - 100.0) < 0.01:
        return {k: round(v, 2) for k, v in raw.items()}, False
    return {k: round(v / total * 100.0, 2) for k, v in raw.items()}, True


def _implied_targets(values: Dict[str, float], total: float) -> Dict[str, float]:
    """Today's split, standing in for a target the user has not chosen yet.

    Deliberately NOT :data:`DEFAULT_CATEGORY_TARGETS`. Handing a brand-new user
    a 50/30/10/10 target they never asked for makes the drift trigger fire on
    day one — an all-equity portfolio is 50 points "over" against a gold target
    it does not know it has — and a plan that is permanently due is a plan the
    reader learns to ignore. With the current split as the target, drift is
    zero until the user states an intention, and then it measures the thing
    they actually said.
    """
    if total <= 0:
        return {cat: round(100.0 / len(CATEGORIES), 2) for cat in CATEGORIES}
    return {cat: round(values.get(cat, 0.0) / total * 100.0, 2)
            for cat in CATEGORIES}


def plan_categories(by_category: Dict[str, List[Dict[str, Any]]], *,
                    targets: Optional[Dict[str, Any]] = None,
                    deviation_pct: float = DEFAULT_DEVIATION_PCT
                    ) -> Dict[str, Any]:
    """Each category's share of the whole book, against its target.

    All four categories are always reported, empty ones included: a 10% gold
    target with nothing in it is exactly the finding the user needs, and
    dropping the row would hide it.
    """
    tolerance = max(0.0, float(deviation_pct if deviation_pct is not None
                               else DEFAULT_DEVIATION_PCT))
    values = {cat: sum(max(0.0, float(p.get("value") or 0))
                       for p in by_category.get(cat, []))
              for cat in CATEGORIES}
    total = sum(values.values())
    targets_set = bool(targets)
    if targets_set:
        target_pct, rescaled = normalise_targets(targets)
    else:
        target_pct, rescaled = _implied_targets(values, total), False

    rows = []
    for cat in CATEGORIES:
        value = values[cat]
        current = (value / total * 100.0) if total > 0 else 0.0
        target = target_pct[cat]
        drift = current - target
        tradable = sum(max(0.0, float(p.get("value") or 0))
                       for p in by_category.get(cat, []) if p.get("tradable"))
        if total <= 0:
            status, action = "within", "HOLD"
        elif drift > tolerance:
            status, action = "over", "REDUCE"
        elif drift < -tolerance:
            status, action = "under", "INCREASE"
        else:
            status, action = "within", "HOLD"
        amount = (target - current) / 100.0 * total if status != "within" else 0.0
        rows.append({
            "category": cat,
            "label": CATEGORY_LABELS[cat],
            "value": round(value, 2),
            "tradable_value": round(tradable, 2),
            "manual_value": round(value - tradable, 2),
            "positions": len(by_category.get(cat, [])),
            "current_pct": round(current, 2),
            "target_pct": target,
            "drift_pct": round(drift, 2),
            "tolerance_pct": tolerance,
            "band": [round(max(0.0, target - tolerance), 2),
                     round(min(100.0, target + tolerance), 2)],
            "status": status,
            "action": action,
            # Signed: positive is money to move IN, negative is money to take
            # out. One number, so the UI never has to pair it with a verb.
            "amount": round(amount, 2),
        })

    drifted = [r for r in rows if r["status"] != "within"]
    return {
        "total_value": round(total, 2),
        # False means the targets shown are just today's split, so every drift
        # is zero by construction. The UI must say so rather than presenting
        # them as a policy the user chose.
        "targets_set": targets_set,
        "targets_rescaled": rescaled,
        "tolerance_pct": tolerance,
        "rows": rows,
        "drifted": len(drifted),
        "worst_drift_pct": round(max((abs(r["drift_pct"]) for r in drifted),
                                     default=0.0), 2),
    }


# ══════════════════════════════════════════════════════════════
#  PLAN
# ══════════════════════════════════════════════════════════════

def _selection(selected_categories: Optional[Iterable[str]],
               selected_assets: Optional[Iterable[str]]):
    """A predicate saying whether one position is in scope for trading today.

    Weights are always computed over the WHOLE portfolio and only the
    recommendation is gated, because a weight that changes when you tick a
    checkbox is not a weight. Deselecting a holding means "do not trade this
    one today", not "pretend I do not own it".
    """
    cats = None if selected_categories is None else set(selected_categories)
    keys = None if selected_assets is None else set(selected_assets)

    def selected(position: Dict[str, Any]) -> bool:
        if cats is not None and position.get("category") not in cats:
            return False
        if keys is not None and position.get("key") not in keys:
            return False
        return True

    return selected


def _deploy_cash(actions: List[Dict[str, Any]], cash: float,
                 order: str) -> Dict[str, Any]:
    """Place a contribution the way the chosen strategy would place it.

    This is the study's `deploy` step. Every holding aims at an equal share of
    its OWN category, because equal weight is the target the backtest measured
    against; the preset changes the ORDER money is offered in, not where it is
    ultimately headed — largest shortfall first, or strongest, or weakest.

    Money is split across categories by their current share of the book, so a
    contribution cannot quietly turn a 46/54 stock-fund split into something
    else. Whole shares for stocks, fractional units for funds, and a residual
    sweep afterwards because integer share counts always leave change behind.

    Runs only when there is something to place. With no contribution the band
    plan stands exactly as it did before, which is what every caller that
    predates contributions expects.
    """
    empty = {"amount": round(max(0.0, cash), 2), "deployed": 0.0,
             "left": round(max(0.0, cash), 2), "positions": 0}
    if cash <= 0:
        return empty

    # A trim is already a decision to reduce that holding. Offering it the new
    # money as well would propose buying and selling the same name on one page.
    eligible = [r for r in actions
                if r.get("selected") and r.get("tradable")
                and float(r.get("price") or 0) > 0
                and r.get("action") in ("HOLD", "ADD")]
    if not eligible:
        return empty

    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for row in eligible:
        by_cat.setdefault(row["category"], []).append(row)
    live = {c: sum(r["value"] for r in rows) for c, rows in by_cat.items()}
    book = sum(live.values())
    if book <= 0:
        return empty

    buys: Dict[str, float] = {}
    left = 0.0
    for cat, rows in by_cat.items():
        pot = cash * live[cat] / book
        whole = cat == CAT_STOCKS
        target = (live[cat] + pot) / len(rows)

        def shortfall(r: Dict[str, Any]) -> float:
            return target - float(r["value"])

        if order == DEPLOY_MOMENTUM:
            seq = sorted(rows, key=lambda r: -(r["gain_pct"]
                                               if r.get("gain_pct") is not None
                                               else -1e9))[:TILT_PICKS]
        elif order == DEPLOY_LAGGARD:
            seq = sorted(rows, key=lambda r: (r["gain_pct"]
                                              if r.get("gain_pct") is not None
                                              else 1e9))[:TILT_PICKS]
        elif order == DEPLOY_EQUAL:
            seq = sorted(rows, key=lambda r: str(r.get("name") or r.get("key")))
        else:
            seq = sorted(rows, key=lambda r: -shortfall(r))
        # A tilt CONCENTRATES: S5 and S9 were measured pushing the whole
        # contribution into their three picks, regardless of how far under
        # target anything else was. Filling shortfalls in tilt order instead
        # would make them behave like S2 whenever the winners are already big,
        # which is the opposite of the rule.
        concentrate = order in (DEPLOY_MOMENTUM, DEPLOY_LAGGARD, DEPLOY_EQUAL)

        def place(row: Dict[str, Any], budget: float) -> float:
            """Buy what `budget` affords of one holding; return what it spent."""
            price = float(row["price"])
            n = min(budget, pot) / price
            if whole:
                n = float(int(n))
            if n <= 0:
                return 0.0
            buys[row["key"]] = buys.get(row["key"], 0.0) + n
            return n * price

        for row in seq:
            if pot <= 0:
                break
            # An even share ignores the shortfall by definition — that IS the
            # rule S1, S5 and S9 were measured on, and correcting it here
            # would quietly turn each of them into S2.
            want = (pot / len(seq)) if concentrate \
                else max(0.0, shortfall(row))
            if want > 0:
                pot -= place(row, want)

        for _ in range(3):
            afford = [r for r in seq if pot >= float(r["price"])]
            if not afford:
                break
            portion = pot / len(afford)
            for row in afford:
                if pot < float(row["price"]):
                    continue
                pot -= place(row, portion)
        left += pot

    deployed = 0.0
    for row in eligible:
        units = buys.get(row["key"], 0.0)
        if units <= 0:
            if row["action"] == "ADD":
                # The band wanted money here and the contribution did not
                # reach it. Saying so beats leaving a row that looks funded.
                row.update(action="HOLD", amount=0.0, units=0.0,
                           reason="Below its target, but this contribution "
                                  "did not reach it.")
            continue
        amount = units * float(row["price"])
        deployed += amount
        row.update(action="ADD", units=round(units, 4),
                   amount=round(amount, 2), funded_from_contribution=True,
                   reason=f"Funded from the contribution: "
                          f"{DEPLOY_LABELS.get(order, order)}.")

    return {"amount": round(cash, 2), "deployed": round(deployed, 2),
            "left": round(left, 2),
            "positions": sum(1 for u in buys.values() if u > 0)}


def _settle(actions: List[Dict[str, Any]]) -> None:
    """Replay the plan onto the book so each row can show its AFTER state.

    Every row is decided against the book as it stands today, which means the
    weights it quotes are opening weights. Once the trades land the book is a
    different book: selling 42 shares of one holding lifts the weight of every
    holding that was left alone. Closing weights therefore have to be measured
    on the settled quantities, not inferred from the decision.

    Share counts are floored for stocks, because a plan that says "sell 42.83
    shares" cannot be executed. Fund units stay fractional, which is how they
    actually trade. Flooring here rather than in `units` keeps the rupee figure
    the tax calculation was built on untouched.

    Net cash is the gross trade value, positive for a sale. Tax already has its
    own column on the row; folding it in here would net two different things
    into one number and make the cash line unreconcilable against the ledger.
    """
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for row in actions:
        by_cat.setdefault(row["category"], []).append(row)

    for cat, rows in by_cat.items():
        whole = cat == CAT_STOCKS
        for row in rows:
            price = float(row.get("price") or 0.0)
            held = float(row.get("held_units") or 0.0)
            units = float(row.get("units") or 0.0)
            if whole:
                units = float(int(units))
            bought = units if row["action"] == "ADD" else 0.0
            sold = min(units, held) if row["action"] == "TRIM" else 0.0
            after = held - sold + bought
            row["units_bought"] = round(bought, 4)
            row["units_sold"] = round(sold, 4)
            row["sold_pct_of_held"] = round(sold / held * 100.0, 2) if held else 0.0
            row["held_after"] = round(after, 4)
            row["value_after"] = round(after * price, 2)
            row["net_cash"] = round((sold - bought) * price, 2)

        # Weights close against the settled book, and only over holdings that
        # can actually be priced — a hand-entered position has no price, so
        # including it would put a hole in the denominator.
        after_total = sum(r["value_after"] for r in rows if r.get("tradable", True))
        for row in rows:
            row["weight_after_pct"] = (
                round(row["value_after"] / after_total * 100.0, 2)
                if after_total > 0 and row.get("tradable", True) else 0.0)


def _target_weight(row: Dict[str, Any], low: float, high: float) -> float:
    """The weight-of-category this holding is being steered to.

    A breach is steered to the edge it crossed; anything inside the band is
    already where it should be, so its target IS its current weight. Printing
    one mid-band number for everything would show a target the policy never
    asks for and imply trades it does not want.
    """
    if row.get("status") == "over":
        return high
    if row.get("status") == "under":
        return low
    return round(float(row.get("weight_pct") or 0), 2)


def build_plan(*, stocks: List[Dict[str, Any]] = None,
               funds: List[Dict[str, Any]] = None,
               txns_by_symbol: Dict[str, List] = None,
               manual_assets: Optional[Dict[str, Any]] = None,
               as_of: Any = None,
               last_rebalanced: Any = None,
               cadence: str = "semiannual",
               tape: Optional[Dict[str, Any]] = None,
               residency: str = NRI,
               exemption_left: float = EQUITY_LTCG_EXEMPT,
               min_weight_pct: Optional[float] = None,
               max_weight_pct: Optional[float] = None,
               category_targets: Optional[Dict[str, Any]] = None,
               deviation_pct: float = DEFAULT_DEVIATION_PCT,
               triggers_enabled: Optional[Iterable[str]] = None,
               boom_gain_pct: float = BOOM_YEAR_GAIN_PCT,
               crash_drop_pct: float = CRASH_DRAWDOWN_PCT,
               gain_trigger_pct: Optional[float] = None,
               loss_trigger_pct: Optional[float] = None,
               vol_trigger_pct: float = DEFAULT_VOL_TRIGGER_PCT,
               mode: str = MODE_AUTO,
               selected_categories: Optional[Iterable[str]] = None,
               selected_assets: Optional[Iterable[str]] = None,
               asset_limits: Optional[Dict[str, float]] = None,
               long_term_only: bool = False,
               tax_rates: Optional[Dict[str, float]] = None,
               strategy: Optional[str] = None,
               new_money: float = 0.0,
               # key -> last close / highest close of the past year. Supplied by
               # the caller because the engine holds no price history.
               peak_ratios: Optional[Dict[str, float]] = None
               ) -> Dict[str, Any]:
    """The whole answer: is it due, what moves, and what does moving cost."""
    today = _as_date(as_of) or date.today()
    # Band precedence, strictest first: an EXPLICIT argument always wins, then
    # the preset's ceiling, then the module default. An earlier version let the
    # preset override an explicit `max_weight_pct`, which silently ignored the
    # user's own slider and broke every caller that sets the band directly.
    policy = get_strategy(strategy) if strategy else None
    preset_ceiling = (policy["trim_pct"]
                      if policy and policy["id"] != STRATEGY_CUSTOM else None)
    if max_weight_pct is None:
        max_weight_pct = (preset_ceiling if preset_ceiling is not None
                          else MAX_WEIGHT_PCT)
    if min_weight_pct is None:
        min_weight_pct = MIN_WEIGHT_PCT
    low, high = clamp_band(min_weight_pct, max_weight_pct)
    # "Never sells" is a property of the RULE, not of the band, so it holds
    # even when the caller has set a ceiling of its own.
    never_sells = bool(policy and policy["id"] != STRATEGY_CUSTOM
                       and policy["trim_pct"] is None)
    boom = market_boom(tape, year_gain_pct=boom_gain_pct)
    crash = market_crash(tape, drop_pct=crash_drop_pct)
    volatility = market_volatility(tape, threshold_pct=vol_trigger_pct)

    positions = (_stock_positions(stocks or [], txns_by_symbol or {}, today)
                 + _fund_positions(funds or [], today)
                 + _manual_positions(manual_assets))
    by_category: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for p in positions:
        by_category[p["category"]].append(p)

    allocation = plan_categories(by_category, targets=category_targets,
                                 deviation_pct=deviation_pct)
    in_scope = _selection(selected_categories, selected_assets)
    for position in positions:
        position["selected"] = in_scope(position)

    # Each category is banded against ITSELF, so a 10% ceiling means "a tenth
    # of the gold I hold", not "a tenth of everything".
    exemption = exemption_left
    sleeves: Dict[str, Any] = {}
    for cat in CATEGORIES:
        sleeve = plan_sleeve(
            by_category[cat], as_of=today, sleeve=cat,
            equity_for_tax=(cat == CAT_STOCKS), residency=residency,
            exemption_left=exemption, min_weight_pct=low, max_weight_pct=high,
            asset_limits=asset_limits, long_term_only=long_term_only, tax_rates=tax_rates)
        exemption = sleeve["exemption_left"]
        sleeve["label"] = CATEGORY_LABELS[cat]
        sleeves[cat] = sleeve

    total_value = allocation["total_value"]
    by_key = {p["key"]: p for p in positions}
    actions: List[Dict[str, Any]] = []
    for cat in CATEGORIES:
        for row in sleeves[cat]["actions"]:
            source = by_key.get(row["key"], {})
            row["category"] = cat
            row["category_label"] = CATEGORY_LABELS[cat]
            row["invested"] = source.get("invested")
            row["gain_pct"] = source.get("gain_pct")
            row["tradable"] = bool(source.get("tradable", True))
            # Two allocation figures, because they answer different questions:
            # the share of the whole book is what the pie chart shows, and the
            # share of the category is what the band is enforced against.
            row["portfolio_pct"] = (round(row["value"] / total_value * 100.0, 2)
                                    if total_value > 0 else 0.0)
            row["target_pct"] = _target_weight(row, *row["band"])
            row["selected"] = in_scope(source) if source else True
            # A weight ceiling can be breached two ways, and only one of
            # them is a reason to sell.
            #
            # Worked example from the 2020 ledger: SCI sat at 17.96% of the
            # book in December 2019 and 20.44% in July 2020, so the 20% band
            # fired and sold 51% of the position at Rs 57. SCI had FALLEN 5.6%
            # over that stretch — the rest of the book fell 17.7% in the COVID
            # crash, and the weight breached from the denominator. The rule
            # sold a holding that had not grown, well below where the same
            # position had sat unsold at the previous review.
            #
            # So a breach is only acted on while the sale is still EARLY. Two
            # ways to ask that, and the backtest is clear about which is worth
            # having (monthly, ten-stock basket, 2011-2026, at S10's own 20%
            # ceiling):
            #
            #   no guard      16.84% pre / 15.99% after tax,  3 sells
            #   cost basis    16.84% / 15.99%,  fires 0 times   <- inert
            #   trailing peak 17.60% / 16.49%,  fires 9 times   <- the real one
            #
            # The cost-basis version is inert because a monthly SIP builds a
            # low average cost, so a holding is almost never under water even
            # when it is well off its own high. The peak rule measures the
            # thing that matters: is this sale late?
            #
            # `peak_ratio` has to be supplied by the caller — the engine has no
            # price history of its own. When it is missing the cost rule still
            # applies, because a weak guard beats none.
            # Only the presets that were MEASURED with the guard carry it.
            # Applying it to S10 as well would improve the plan and invalidate
            # the 15.97% printed beside S10 on the picker, which was measured
            # without it. A number on screen has to describe what the button
            # actually does.
            if row["action"] == "TRIM" and policy and policy.get("peak_guard"):
                ratio = (peak_ratios or {}).get(row["key"])
                if ratio is not None and ratio < TRIM_PEAK_BAND:
                    row.update({
                        "action": "HOLD", "amount": 0.0, "units": 0.0,
                        "suppressed_trim": True,
                        "reason": (
                            f"{row['weight_pct']:.1f}% of the "
                            f"{row['category_label'].lower()} sleeve, above its "
                            f"ceiling — but it is {(1 - ratio) * 100:.1f}% below "
                            f"its own 12-month high, so this sale is late. Top "
                            f"up the rest instead."),
                    })
                elif (ratio is None and row.get("gain_pct") is not None
                        and row["gain_pct"] <= 0):
                    row.update({
                        "action": "HOLD", "amount": 0.0, "units": 0.0,
                        "suppressed_trim": True,
                        "reason": (
                            f"{row['weight_pct']:.1f}% of the "
                            f"{row['category_label'].lower()} sleeve, above its "
                            f"ceiling — but it is down "
                            f"{abs(row['gain_pct']):.1f}%, so the breach is "
                            f"other holdings falling, not this one growing. "
                            f"Top up the rest instead of selling at a loss."),
                    })
            if never_sells and row["action"] == "TRIM":
                # The preset's defining property. The breach is still REPORTED
                # — hiding it would misrepresent the portfolio — but no sale is
                # proposed, and the row says which rule suppressed it.
                row.update({
                    "action": "HOLD", "amount": 0.0, "units": 0.0,
                    "suppressed_trim": True,
                    "reason": f"Above its ceiling, but "
                              f"{policy['name'] if policy else 'this rule'} "
                              f"never sells — direct new money elsewhere "
                              f"instead.",
                })
            if not row["tradable"] and row["status"] != "within":
                row.update({
                    "action": "REVIEW", "amount": 0.0, "units": 0.0,
                    "reason": "Entered by hand, so there are no units or price "
                              "here to trade. Adjust it where you hold it.",
                })
            elif not row["selected"] and row["action"] in ("TRIM", "ADD"):
                row.update({
                    "action": "SKIP",
                    "reason": "Outside its band, but not selected for this "
                              "rebalance. " + row["reason"],
                })
            # Signed share count: positive buys, negative sells, zero for a
            # row proposing nothing. Computed HERE, after every rewrite above,
            # because the action can still change: a never-sells preset turns
            # a TRIM into a HOLD, and deriving the count earlier left a
            # negative share figure sitting under a "BUY ONLY" heading.
            row["trade_units"] = (row.get("units") or 0.0) * (
                -1 if row["action"] == "TRIM" else
                1 if row["action"] == "ADD" else 0)
            actions.append(row)

    # Which underweight to fund FIRST. The preset only reorders the top-ups —
    # it never changes which holdings are underweight, or by how much.
    order = policy["deploy"] if policy else DEPLOY_GAP
    adds_only = [a for a in actions if a["action"] == "ADD"]
    if order == DEPLOY_MOMENTUM:
        # Explicit None check, not `or`: a holding sitting exactly at its cost
        # has a gain of 0.0, which is falsy, and `or` sent it to the bottom of
        # the list as though its return were unknown.
        adds_only.sort(key=lambda a: -(a["gain_pct"] if a.get("gain_pct")
                                       is not None else -1e9))
    elif order == DEPLOY_LAGGARD:
        adds_only.sort(key=lambda a: (a.get("gain_pct") if a.get("gain_pct")
                                      is not None else 1e9))
    elif order == DEPLOY_EQUAL:
        adds_only.sort(key=lambda a: str(a.get("name") or a.get("key")))
    else:
        adds_only.sort(key=lambda a: -a["amount"])
    for rank, a in enumerate(adds_only, 1):
        a["fund_rank"] = rank

    # Rank EVERY tradable holding within its own category by the metric the
    # preset deploys on — not just the ones being funded. Under a tilt the
    # question a reader has is "why this name and not that one", and a rank
    # that only covers the winners cannot answer it.
    for cat in CATEGORIES:
        ranked = [a for a in actions if a["category"] == cat and a["tradable"]]
        if order == DEPLOY_MOMENTUM:
            ranked.sort(key=lambda a: -(a["gain_pct"]
                                        if a.get("gain_pct") is not None
                                        else -1e9))
        elif order == DEPLOY_LAGGARD:
            ranked.sort(key=lambda a: (a["gain_pct"]
                                       if a.get("gain_pct") is not None
                                       else 1e9))
        elif order == DEPLOY_EQUAL:
            ranked.sort(key=lambda a: str(a.get("name") or a.get("key")))
        else:
            ranked.sort(key=lambda a: -a["value"])
        for rank, a in enumerate(ranked, 1):
            a["deploy_rank"] = rank

    # A contribution replaces the band's advisory top-ups with an allocation of
    # actual money: "you are below target" becomes "this is where the 1,000
    # goes". With no contribution the band plan stands untouched.
    contribution = _deploy_cash(actions, float(new_money or 0.0), order)

    # Settle LAST: every rewrite above can still change an action, and a closing
    # weight computed before a never-sells preset cancels a trim would describe
    # a book that is never going to exist.
    _settle(actions)

    moves = [a for a in actions if a["selected"] and a["tradable"]]
    trims = [a for a in moves if a["action"] == "TRIM"]
    adds = [a for a in moves if a["action"] == "ADD"]
    sell_value = sum(a["amount"] for a in trims)
    tax_total = sum(a.get("tax", 0.0) for a in trims)
    buy_value = sum(a["amount"] for a in adds)

    # Return is measured only over holdings whose cost is actually known, so an
    # imported position with no cost basis cannot drag the figure to zero.
    invested = sum(float(p.get("invested") or 0) for p in positions
                   if p.get("tradable") and float(p.get("invested") or 0) > 0)
    priced = sum(float(p.get("value") or 0) for p in positions
                 if p.get("tradable") and float(p.get("invested") or 0) > 0)
    portfolio_gain_pct = _pnl_pct(priced, invested)

    breaches = sum(1 for a in actions
                   if a["status"] != "within" and a["tradable"] and a["selected"])
    matured = sum(sleeves[c]["matured_positions"] for c in CATEGORIES)
    triggers = due_triggers(
        today, last_rebalanced=last_rebalanced, cadence=cadence, boom=boom,
        crash=crash, volatility=volatility, breaches=breaches, matured=matured,
        drifted=allocation["drifted"],
        worst_drift_pct=allocation["worst_drift_pct"],
        portfolio_gain_pct=portfolio_gain_pct,
        gain_trigger_pct=gain_trigger_pct, loss_trigger_pct=loss_trigger_pct,
        enabled=triggers_enabled, mode=mode, band=(low, high))

    return {
        "as_of": today.isoformat(),
        "residency": residency,
        "policy": {
            "min_weight_pct": low,
            "max_weight_pct": high,
            "tolerance_pct": BAND_TOLERANCE_PCT,
            "min_trade_value": MIN_TRADE_VALUE,
            "cadence": cadence,
            "deviation_pct": allocation["tolerance_pct"],
            "boom_gain_pct": boom_gain_pct,
            "crash_drop_pct": crash_drop_pct,
            "gain_trigger_pct": gain_trigger_pct,
            "loss_trigger_pct": loss_trigger_pct,
            "vol_trigger_pct": vol_trigger_pct,
            "mode": mode,
            "long_term_days": LONG_TERM_DAYS,
            "long_term_days_non_equity": LONG_TERM_DAYS_NON_EQUITY,
        },
        # What the contribution did: how much was asked for, how much whole
        # units could actually absorb, and what is left over as cash.
        "contribution": contribution,
        # NOT "strategy" — that key already carries `strategy_notes`, the
        # advice list the UI renders under "How to run this".
        "strategy_preset": {
            **(policy or {"id": None, "name": "None",
                          "tagline": "No preset — the bands and triggers "
                                     "below are in force as set.",
                          "trim_pct": None, "deploy": DEPLOY_GAP,
                          "reinvest_income": False, "measured": None}),
            "effective_max_weight_pct": high,
            "never_sells": never_sells,
            "deploy_label": DEPLOY_LABELS[order],
            # The live book has no contribution schedule, so the backtest's
            # twelve-month price momentum has no counterpart here. Ordering
            # uses return on COST, a different quantity — saying so is the
            # difference between a label and a claim.
            "deploy_note": ("Ordered by return on cost, not by the 12-month "
                            "price momentum the backtest used: a live holding "
                            "has no contribution history to measure that on."
                            if order in (DEPLOY_LAGGARD, DEPLOY_MOMENTUM)
                            else None),
            "income_note": ("This rule puts income back to work — add "
                            "dividends received to the next top-up rather "
                            "than leaving them in cash."
                            if policy and policy["reinvest_income"]
                            else None),
            # What the chosen rule can act on, so the table can show only the
            # columns that mean something under it. A ceiling column under a
            # never-sells rule, or a momentum rank under a gap-ordered one, is
            # a number the reader cannot use.
            "rank": (policy or {}).get("rank"),
            "rank_of": (policy or {}).get("rank_of"),
            "shows_long_term_units": not never_sells,
            "shows_rank": order in (DEPLOY_MOMENTUM, DEPLOY_LAGGARD),
            "rank_label": ("Strongest first" if order == DEPLOY_MOMENTUM
                           else "Weakest first" if order == DEPLOY_LAGGARD
                           else None),
            "measured_note": ("Backtested on a monthly Rs 10,000 contribution "
                              "into a ten-stock NSE basket, 2011-2026, after "
                              "NRI tax. That is the record of that basket on "
                              "that path, not a forecast for this portfolio."),
        },
        "triggers": triggers,
        "market": boom,
        "crash": crash,
        "volatility": volatility,
        "allocation": allocation,
        "sleeves": sleeves,
        "actions": actions,
        "portfolio_value": total_value,
        "portfolio_gain_pct": portfolio_gain_pct,
        "selection": {
            "categories": (None if selected_categories is None
                           else sorted(set(selected_categories))),
            "assets": (None if selected_assets is None
                       else sorted(set(selected_assets))),
        },
        "totals": {
            "sell_value": round(sell_value, 2),
            "buy_value": round(buy_value, 2),
            "tax_estimated": round(tax_total, 2),
            "net_proceeds": round(sell_value - tax_total, 2),
            # What the trims leave over after funding the top-ups. Negative
            # means the plan needs new money rather than being self-funding.
            "cash_after_plan": round(sell_value - tax_total - buy_value, 2),
            "trims": len(trims),
            "adds": len(adds),
            "skipped": sum(1 for a in actions if a["action"] == "SKIP"),
            "manual_review": sum(1 for a in actions if a["action"] == "REVIEW"),
        },
        "strategy": funding_notes(actions, boom, crash, volatility) + strategy_notes(triggers, boom, buy_value,
                                   sell_value - tax_total, crash=crash,
                                   allocation=allocation, band=(low, high)),
    }


def strategy_notes(triggers: Dict[str, Any], boom: Dict[str, Any],
                   buy_value: float, net_proceeds: float, *,
                   crash: Optional[Dict[str, Any]] = None,
                   allocation: Optional[Dict[str, Any]] = None,
                   band: Optional[Tuple[float, float]] = None
                   ) -> List[Dict[str, str]]:
    """The standing advice, stated against this plan rather than in general."""
    low, high = band or (MIN_WEIGHT_PCT, MAX_WEIGHT_PCT)
    notes = [{
        "title": "Fund the floor with new money first",
        "body": "Topping up an underweight with fresh cash or the next SIP "
                "realises nothing and is taxed at nothing. Only sell for the "
                "part new money cannot cover.",
    }, {
        "title": "Check on the calendar, trade on the band",
        "body": f"Looking every {triggers['window_days']} days but only trading "
                f"positions outside {low:g}–{high:g}% keeps "
                "drift bounded at far lower turnover than rebalancing "
                "everything on a date.",
    }, {
        "title": "Spend long-term units first",
        "body": f"Units held past {LONG_TERM_DAYS} days are taxed at "
                f"{EQUITY_LTCG_PCT:g}% against {EQUITY_STCG_PCT:g}% for newer "
                f"ones, with the first ₹{EQUITY_LTCG_EXEMPT:,.0f} of long-term "
                "gain each year exempt. Same trade, smaller bill.",
    }]
    if boom.get("boom"):
        notes.append({
            "title": "This is the trim, not the exit",
            "body": "A boom is the moment the ceiling is worth enforcing, "
                    "because it is what put the position over. Trim back to "
                    f"{high:g}% — do not sell out of a holding "
                    "because it went up.",
        })
    if (crash or {}).get("crash"):
        notes.append({
            "title": "A crash is the buy side of the same rule",
            "body": "What a fall does to a portfolio is push holdings BELOW "
                    f"their {low:g}% floor, so the plan turns into a list of "
                    "top-ups. Fund them from new money and from the debt or "
                    "gold sleeve, not by selling equity into the fall.",
        })
    drifted = (allocation or {}).get("drifted") or 0
    if drifted:
        worst = (allocation or {}).get("worst_drift_pct") or 0
        notes.append({
            "title": "The mix has moved, not just the names",
            "body": f"{drifted} categor{'y' if drifted == 1 else 'ies'} sit up "
                    f"to {worst:.1f} points away from target. Correct this with "
                    "where the next contribution goes before correcting it "
                    "with a sale — a category is brought back by months of "
                    "buying far more cheaply than by one taxed trim.",
        })
    if buy_value > net_proceeds:
        notes.append({
            "title": "This plan is not self-funding",
            "body": f"The top-ups need ₹{buy_value - net_proceeds:,.0f} more "
                    "than the trims leave after tax. Stage it over the next "
                    "contributions rather than selling further.",
        })
    return notes


def funding_notes(actions, boom, crash, volatility):
    """Fund selected underweights from estimated net sales, never gross sales."""
    sales = [a for a in actions if a.get('selected') and a.get('action') == 'TRIM']
    buys = [a for a in actions if a.get('selected') and a.get('action') == 'ADD']
    cash = sum(a.get('net_proceeds', 0) for a in sales)
    notes = []
    for sale in sales:
        notes.append({'title': 'Trim ' + str(sale['name']),
                      'body': f"Sell {sale['amount']:.0f}; estimated tax {sale.get('tax', 0):.0f}; available to reinvest {sale.get('net_proceeds', 0):.0f}."})
    stressed = crash.get('crash') or volatility.get('elevated')
    if not boom.get('available'):
        context = 'Market data unavailable: allocation-only recommendation.'
    elif stressed:
        context = 'Crash or elevated volatility: stage the top-up; review market conditions before the remaining half.'
    elif boom.get('boom'):
        context = 'Market boom: top up only holdings below their floor; keep excess proceeds as cash.'
    else:
        context = 'Calm market: restore holdings below their allocation floor.'
    notes.append({'title': 'Where to place the proceeds', 'body': context})
    for buy in sorted(buys, key=lambda a: a.get('weight_pct', 0)):
        desired = buy['amount'] * (0.5 if stressed else 1)
        funded = min(cash, desired)
        cash -= funded
        notes.append({'title': 'Top up ' + str(buy['name']),
                      'body': f"Allocation gap {buy['amount']:.0f}. Suggested now {desired:.0f}: {funded:.0f} from net trims, {desired-funded:.0f} additional money required."})
    if not buys or cash > 0:
        notes.append({'title': 'Cash remaining', 'body': f"Keep {cash:.0f} unallocated. No additional selected holding below its floor qualifies for a top-up."})
    return notes
