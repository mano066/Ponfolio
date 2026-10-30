"""
Market index tape — pure computation layer.

Everything in this module is deterministic and network-free so it can be
unit-tested without hitting yfinance.  ``main.py`` performs the batched download
and hands each index a plain list of daily closes; this module turns those into
the tape rows the dashboard renders and the dip magnitudes the deployment
engine scores against.

Design notes
------------
* ``off_high_pct`` is a POSITIVE magnitude: 0.0 means "sitting at its 1-year
  high", 8.2 means "8.2% below it".  A signed value would invite sign-flip bugs
  at every call site, and :mod:`deploy_engine` wants the magnitude anyway.  The
  UI is responsible for rendering it with a minus sign if it wants one.
* An index whose data did not arrive degrades to ``status="unavailable"`` with
  every numeric field ``None`` — never ``0.0``.  "The feed is down" and "the
  index is at its high" must never look alike, on the tape or in a score.
* A series shorter than :data:`MIN_POINTS_FOR_52W` still produces a row, but is
  flagged ``short_window=True`` and its ``high_52w`` is honestly labelled as a
  partial-window high rather than passed off as a real 52-week figure.
* :func:`sector_index_for` and :func:`benchmark_for_stock` are guaranteed to
  return a symbol that exists in :data:`INDEX_UNIVERSE`.  Anything else would
  produce a benchmark key that :func:`dip_map` cannot resolve, silently
  knocking the index-dip factor out of a candidate's score.
"""

from __future__ import annotations

import math
import re
import datetime as _dt
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

# ── Tunables ──────────────────────────────────────────────────────────────
# Below this many daily closes, a "52-week" high is really a short-window high.
# ~120 trading days is roughly six months.
MIN_POINTS_FOR_52W = 120

# Below this many closes there is no RANGE at all, and every figure derived
# from one is an artefact rather than a measurement.
#
# Yahoo serves exactly one bar for several NSE sector indices — ^CNXAUTO,
# ^CNXFMCG, ^CNXENERGY, ^CNXMETAL, ^CNXPSUBANK among them, and no alternative
# ticker carries the history either. With a single close the high, the low and
# the last price are the same number, so the drawdown computes as 0.0% and the
# status ladder reads that as "at its high" and prints OVERHEATED. Half the
# sector tape was flying a red valuation verdict inferred from one data point.
# Withholding the figures says "no history", which is the truth.
MIN_POINTS_FOR_RANGE = 5

# Treat anything within this of the high as "at the high" for display purposes.
AT_HIGH_TOLERANCE_PCT = 1.0

# The 52-week window, in trading days.  The series handed to this module may be
# far longer than a year (the backtest needs a decade), so every "52-week"
# statistic is computed from a SLICE rather than from the whole series.  Taking
# max() over a 10-year series and calling it a 52-week high would silently
# inflate every drawdown the deploy engine scores against.
TRADING_DAYS_52W = 252

# The largest calendar gap between two bars that can still be called "a day".
# Friday to Monday is 3; a long weekend or a mid-week holiday makes 4. Anything
# wider is not a session change.
#
# This exists because Yahoo serves several NSE sector indices sparsely: a
# one-month request for ^CNXFMCG, ^CNXMETAL, ^CNXAUTO, ^CNXSERVICE or
# NIFTY_FIN_SERVICE.NS came back with a SINGLE bar while ^NSEI and ^CNXIT
# returned 23. Spliced onto the cached decade, the previous bar on record was
# weeks old, so `(last - prev) / prev` printed a multi-week move as today's:
# FMCG showed -6.88% on a day the Nifty moved -0.34%, and METAL's "day" gain
# (+7.98%) exceeded its own one-week gain (+6.57%) — arithmetically impossible
# for a real session, and the tell that the two bars were not adjacent.
MAX_SESSION_GAP_DAYS = 4

# Trading-day offsets for the trailing-return columns.  Offsets rather than
# calendar arithmetic: the series arrives as closes, and a fixed trading-day
# step is exact and immune to holiday drift.  ~21 trading days is a month.
LOOKBACK_TRADING_DAYS = {"1w": 5, "1m": 21, "3m": 63}

# The same horizons in CALENDAR days, used whenever the series carries dates.
# A positional offset silently measures the wrong distance across a hole in
# the data, and fifteen indices on this tape have a two-month hole.
LOOKBACK_CALENDAR_DAYS = {"1w": 7, "1m": 30, "3m": 91}
# How much older than the horizon a bar may be and still answer for it:
# enough for a weekend or a holiday run, not enough to answer a week with a
# two-month-old close.
LOOKBACK_TOLERANCE_DAYS = {"1w": 5, "1m": 12, "3m": 25}

# A DMA is reported ONLY when the series actually holds that many closes.  A
# "200 DMA" computed from 120 points is a different statistic wearing the same
# name, and the tape must not print one as though it were the other.
DMA_WINDOWS = (50, 100, 200)

# Realised-volatility window, in trading days. A month of sessions is long
# enough to be a measurement rather than a reaction to one gap, and short
# enough that a regime change shows up while it still matters.
VOL_WINDOW = 30
MIN_POINTS_FOR_VOL = VOL_WINDOW + 1
# Sessions in a year, for annualising a daily standard deviation.
TRADING_DAYS_YEAR = 252

RSI_PERIOD = 14
# Wilder's RSI needs a seed period plus enough smoothing steps to shake off the
# seed. Two periods is the usual minimum before the number carries information.
MIN_POINTS_FOR_RSI = RSI_PERIOD * 2

# ── Market-status ladder ──────────────────────────────────────────────────
# Cut on drawdown from the 52-week high, which is the one input we actually
# measure for every index.
#
# NOTE ON THE TOP RUNG: it is called "extended", NOT "expensive".  Expensive is
# a claim about valuation, and historical index P/E-P/B series are not
# available from any feed this app talks to (see VALUATION_UNAVAILABLE_REASON).
# An index sitting at its own high is a statement about price position and
# nothing more; naming it "expensive" would smuggle in a valuation judgement we
# have no data to support.
# The rungs are ordered by how far the index has fallen, and the COLOUR runs
# the opposite way to a P&L palette on purpose.
#
# Red here means RISK OF BUYING, not "the market went down". An index sitting
# at its own high is the dangerous place to deploy a dip reserve, so that is
# the red rung; a genuine correction is the green one. The earlier ladder had
# this inverted — a deep dip was painted red — which told the user to feel
# alarmed at exactly the moment the whole feature exists to catch.
#
# The far end is amber rather than green again: past ~30% an index is as
# likely to be repricing something real as to be handing out a discount, and
# this module has no way to tell those apart.
MARKET_OVERHEATED = "overheated"
MARKET_NORMAL = "normal"
MARKET_DIP = "dip"
MARKET_ATTRACTIVE = "attractive"
MARKET_HIGH_RISK = "high_risk"
MARKET_UNKNOWN = "unknown"

MARKET_STATUS_LABELS = {
    MARKET_OVERHEATED: "Overheated",
    MARKET_NORMAL: "Normal",
    MARKET_DIP: "Dip",
    MARKET_ATTRACTIVE: "Attractive",
    MARKET_HIGH_RISK: "High risk",
    MARKET_UNKNOWN: "Not available",
}

MARKET_STATUS_EMOJI = {
    MARKET_OVERHEATED: "🔴",
    MARKET_NORMAL: "🟡",
    MARKET_DIP: "🟠",
    MARKET_ATTRACTIVE: "🟢",
    MARKET_HIGH_RISK: "⚠️",
    MARKET_UNKNOWN: "—",
}

# Drawdown-from-52w-high cut points, in percent.
STATUS_OVERHEATED_MAX_DD = 2.0
STATUS_NORMAL_MAX_DD = 8.0
STATUS_DIP_MAX_DD = 15.0
STATUS_ATTRACTIVE_MAX_DD = 30.0

# Valuation is requested by the dashboard spec but cannot be sourced: none of
# yfinance, mfapi, FinAPI or Kite serves a historical P/E or P/B series for an
# index, and a current P/E with no history to compare it against answers no
# question worth asking.  The fields are emitted as None with this reason
# attached rather than being filled with a guess.
VALUATION_UNAVAILABLE = "unavailable"
VALUATION_UNAVAILABLE_REASON = (
    "No feed in use carries historical index P/E or P/B, so there is nothing "
    "to compare today's valuation against."
)

GROUP_BROAD = "broad"
GROUP_SIZE = "size"
GROUP_BANK = "bank"
GROUP_SECTOR = "sector"
GROUP_COMMODITY = "commodity"
GROUP_GLOBAL = "global"

GROUP_LABELS = {
    GROUP_BROAD: "Broad market",
    GROUP_SIZE: "Midcap & smallcap",
    GROUP_BANK: "Banks & financials",
    GROUP_SECTOR: "Sectors",
    GROUP_COMMODITY: "Gold & silver",
    GROUP_GLOBAL: "Global",
}

GROUP_ORDER = (GROUP_BROAD, GROUP_SIZE, GROUP_BANK, GROUP_SECTOR,
               GROUP_COMMODITY, GROUP_GLOBAL)

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"

# ══════════════════════════════════════════════════════════════════════════
#  THE UNIVERSE
# ══════════════════════════════════════════════════════════════════════════
# Every symbol here was verified against a live 1-year daily download to return
# at least ~200 closes, so none of them lands in the short_window path by
# default.  Symbols that Yahoo carries but only quotes intraday (BSE MIDCAP,
# NIFTY TOTAL MARKET, NIFTY MICROCAP 250, NIFTY HEALTHCARE, NIFTY OIL & GAS,
# NIFTY CONSUMER DURABLES) are deliberately excluded: one close is not a
# 52-week high, and a chip claiming "at 1-year high" off a single point is
# exactly the fabricated reading this module exists to prevent.
#
# ^NSMIDCP is a Yahoo misnomer — its level tracks NIFTY NEXT 50, not a midcap
# index, which is why the midcap group uses ^NSEMDCP50 instead.
#
# Gold and silver are ETF proxies, not metal spot prices — the tape says so.
# Yahoo symbol -> Kite instrument, as `exchange:tradingsymbol`.
#
# The two feeds are used for what each is actually good at. Kite is the
# authoritative live source for NSE's own indices and, critically, its OHLC
# response carries the PREVIOUS close — which is the whole day-change figure,
# available even for the sector indices Yahoo has no history for at all.
# Yahoo supplies the long series behind the 52-week range, where it has one.
#
# BSE SENSEX and the two US indices have no NSE instrument, so they stay
# Yahoo-only and are absent here on purpose rather than by omission.
KITE_INDEX = {
    "^NSEI": "NSE:NIFTY 50",
    "^NSMIDCP": "NSE:NIFTY NEXT 50",
    "^CNX100": "NSE:NIFTY 100",
    "^CNX200": "NSE:NIFTY 200",
    "^CRSLDX": "NSE:NIFTY 500",
    "^NSEMDCP50": "NSE:NIFTY MIDCAP 50",
    "NIFTY_MIDCAP_100.NS": "NSE:NIFTY MIDCAP 100",
    "NIFTYMIDCAP150.NS": "NSE:NIFTY MIDCAP 150",
    "NIFTYSMLCAP250.NS": "NSE:NIFTY SMLCAP 250",
    "^NSEBANK": "NSE:NIFTY BANK",
    "NIFTY_FIN_SERVICE.NS": "NSE:NIFTY FIN SERVICE",
    "NIFTY_PVT_BANK.NS": "NSE:NIFTY PVT BANK",
    "^CNXPSUBANK": "NSE:NIFTY PSU BANK",
    "^CNXIT": "NSE:NIFTY IT",
    "^CNXPHARMA": "NSE:NIFTY PHARMA",
    "^CNXAUTO": "NSE:NIFTY AUTO",
    "^CNXFMCG": "NSE:NIFTY FMCG",
    "^CNXENERGY": "NSE:NIFTY ENERGY",
    "^CNXMETAL": "NSE:NIFTY METAL",
    "^CNXREALTY": "NSE:NIFTY REALTY",
    "^CNXINFRA": "NSE:NIFTY INFRA",
    "^CNXMEDIA": "NSE:NIFTY MEDIA",
    "^CNXCONSUM": "NSE:NIFTY CONSUMPTION",
    "^CNXCMDT": "NSE:NIFTY COMMODITIES",
    "^CNXSERVICE": "NSE:NIFTY SERV SECTOR",
    "^CNXPSE": "NSE:NIFTY PSE",
    "GOLDBEES.NS": "NSE:GOLDBEES",
    "SILVERBEES.NS": "NSE:SILVERBEES",
}
KITE_TO_YAHOO = {v: k for k, v in KITE_INDEX.items()}


def parse_candles(candles):
    """Kite daily candles -> (dates, closes), oldest first.

    Kite returns either a list of dicts or the bare array form
    `[timestamp, open, high, low, close, volume]`. Both are accepted because
    the shape has varied between builds and a KeyError here would cost the
    whole tape.

    Only the DATE part of the timestamp is kept. An index has one close a day,
    and keeping the time would make two bars on the same day look like two
    sessions to everything downstream that counts points.
    """
    out = {}
    for row in candles or []:
        stamp = close = None
        if isinstance(row, dict):
            stamp = row.get("date") or row.get("timestamp")
            close = row.get("close")
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            stamp, close = row[0], row[4]
        if stamp is None or close is None:
            continue
        try:
            value = float(close)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        text = str(stamp)[:10]
        try:
            day = _dt.date.fromisoformat(text)
        except ValueError:
            continue
        out[day] = value          # last write wins within a day
    days = sorted(out)
    return days, [out[d] for d in days]


def apply_live_quotes(rows, quotes):
    """Overlay Kite's live level and previous close onto tape rows.

    `quotes` is {kite instrument: {"last_price": x, "ohlc": {"close": y, ...}}}
    — the shape Kite's OHLC endpoint returns, where `ohlc.close` is the PREVIOUS
    session's close.

    This is the fix for the sector cards that read "no history". Their level was
    already live; what was missing was a prior close to compare it against, and
    Kite ships one in the same response. The 52-week figures still need a real
    series and are left exactly as they were — a day change is not a range, and
    filling one from the other would be inventing history.
    """
    by_symbol = {r.get("symbol"): r for r in rows or []}
    touched = 0
    for instrument, quote in (quotes or {}).items():
        sym = KITE_TO_YAHOO.get(instrument)
        row = by_symbol.get(sym)
        if row is None or not isinstance(quote, dict):
            continue
        last = quote.get("last_price")
        prev = (quote.get("ohlc") or {}).get("close")
        try:
            last = float(last) if last is not None else None
            prev = float(prev) if prev is not None else None
        except (TypeError, ValueError):
            continue
        if not last or last <= 0:
            continue
        row["last"] = round(last, 2)
        row["live_source"] = "kite"
        if prev and prev > 0:
            row["prev_close"] = round(prev, 2)
            row["day_chg"] = round(last - prev, 2)
            row["day_chg_pct"] = round((last - prev) / prev * 100, 2)
            row["day_chg_span_days"] = 1
            row["stale_history"] = False
        touched += 1
    return touched


IST = timezone(timedelta(hours=5, minutes=30))
# NSE cash session. Pre-open (09:00-09:15) prints are indicative, so live
# polling starts at the open proper. Exchange holidays are not modelled: on one
# the live calls simply return yesterday's figures, which is harmless.
SESSION_OPEN = (9, 15)
SESSION_CLOSE = (15, 30)


def is_market_open(now: datetime | None = None) -> bool:
    """Whether the NSE cash market is in session at `now` (default: now)."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return (SESSION_OPEN[0] * 60 + SESSION_OPEN[1]
            <= minutes < SESSION_CLOSE[0] * 60 + SESSION_CLOSE[1])


def refresh_live_rows(rows, quotes):
    """Copies of built tape `rows` with Kite's live level laid over them.

    Between full tape rebuilds (every few minutes) this is what keeps the tape
    moving with the market: one batched quotes call instead of a history pass.
    The 52-week window is not re-fetched, so the distance from its high and low
    is re-derived from the live level against the stored extremes — and a live
    print beyond either extreme moves that extreme, as the next rebuild would.

    Returns (new_rows, touched). Rows without a quote are copied unchanged.
    """
    fresh = [dict(r) for r in rows or [] if isinstance(r, dict)]
    touched = apply_live_quotes(fresh, quotes)
    if not touched:
        return fresh, 0
    for row in fresh:
        if row.get("live_source") != "kite":
            continue
        last = row.get("last")
        high = row.get("high_52w")
        low = row.get("low_52w")
        if not isinstance(last, (int, float)) or last <= 0:
            continue
        if isinstance(high, (int, float)) and high > 0:
            high = max(high, last)
            row["high_52w"] = round(high, 2)
            row["off_high_pct"] = round((high - last) / high * 100, 2)
        if isinstance(low, (int, float)) and low > 0:
            low = min(low, last)
            row["low_52w"] = round(low, 2)
            row["above_low_pct"] = round((last - low) / low * 100, 2)
    return fresh, touched


INDEX_UNIVERSE = (
    {"symbol": "^NSEI", "label": "NIFTY 50", "group": GROUP_BROAD},
    {"symbol": "^BSESN", "label": "SENSEX", "group": GROUP_BROAD},
    {"symbol": "^NSMIDCP", "label": "NIFTY NEXT 50", "group": GROUP_BROAD},
    {"symbol": "^CNX100", "label": "NIFTY 100", "group": GROUP_BROAD},
    {"symbol": "^CNX200", "label": "NIFTY 200", "group": GROUP_BROAD},
    {"symbol": "^CRSLDX", "label": "NIFTY 500", "group": GROUP_BROAD},

    {"symbol": "^NSEMDCP50", "label": "MIDCAP 50", "group": GROUP_SIZE},
    {"symbol": "NIFTY_MIDCAP_100.NS", "label": "MIDCAP 100", "group": GROUP_SIZE},
    {"symbol": "NIFTYMIDCAP150.NS", "label": "MIDCAP 150", "group": GROUP_SIZE},
    {"symbol": "NIFTYSMLCAP250.NS", "label": "SMALLCAP 250", "group": GROUP_SIZE},

    {"symbol": "^NSEBANK", "label": "BANK NIFTY", "group": GROUP_BANK},
    {"symbol": "NIFTY_FIN_SERVICE.NS", "label": "FIN SERVICES", "group": GROUP_BANK},
    {"symbol": "NIFTY_PVT_BANK.NS", "label": "PRIVATE BANK", "group": GROUP_BANK},
    {"symbol": "^CNXPSUBANK", "label": "PSU BANK", "group": GROUP_BANK},

    {"symbol": "^CNXIT", "label": "IT", "group": GROUP_SECTOR},
    {"symbol": "^CNXPHARMA", "label": "PHARMA", "group": GROUP_SECTOR},
    {"symbol": "^CNXAUTO", "label": "AUTO", "group": GROUP_SECTOR},
    {"symbol": "^CNXFMCG", "label": "FMCG", "group": GROUP_SECTOR},
    {"symbol": "^CNXENERGY", "label": "ENERGY", "group": GROUP_SECTOR},
    {"symbol": "^CNXMETAL", "label": "METAL", "group": GROUP_SECTOR},
    {"symbol": "^CNXREALTY", "label": "REALTY", "group": GROUP_SECTOR},
    {"symbol": "^CNXINFRA", "label": "INFRA", "group": GROUP_SECTOR},
    {"symbol": "^CNXMEDIA", "label": "MEDIA", "group": GROUP_SECTOR},
    {"symbol": "^CNXCONSUM", "label": "CONSUMPTION", "group": GROUP_SECTOR},
    {"symbol": "^CNXCMDT", "label": "COMMODITIES", "group": GROUP_SECTOR},
    {"symbol": "^CNXSERVICE", "label": "SERVICES", "group": GROUP_SECTOR},
    {"symbol": "^CNXPSE", "label": "PSE", "group": GROUP_SECTOR},

    {"symbol": "GOLDBEES.NS", "label": "GOLD (ETF)", "group": GROUP_COMMODITY},
    {"symbol": "SILVERBEES.NS", "label": "SILVER (ETF)", "group": GROUP_COMMODITY},

    {"symbol": "^GSPC", "label": "S&P 500", "group": GROUP_GLOBAL},
    {"symbol": "^IXIC", "label": "NASDAQ", "group": GROUP_GLOBAL},
)

UNIVERSE_SYMBOLS = tuple(m["symbol"] for m in INDEX_UNIVERSE)

_META_BY_SYMBOL = {m["symbol"]: m for m in INDEX_UNIVERSE}

# The broad-market fallback for anything we cannot place more precisely.
DEFAULT_BENCHMARK = ("^NSEI", "NIFTY 50")


# ══════════════════════════════════════════════════════════════════════════
#  SECTOR → INDEX MAPPING
# ══════════════════════════════════════════════════════════════════════════
# Keyword rules, most specific first.  Deliberately accepts BOTH the Indian
# sector vocabulary the app uses internally ("Banking", "FMCG", "Metals") and
# the US-centric sector names yfinance's ``info["sector"]`` returns
# ("Financial Services", "Consumer Defensive", "Basic Materials"), because
# _get_stock_info feeds us the latter.
#
# Every target MUST be a symbol present in INDEX_UNIVERSE — see the module
# docstring.  _assert_universe_targets() below enforces that at import time.
_SECTOR_RULES: tuple[tuple[tuple[str, ...], tuple[str, str]], ...] = (
    (("bank", "banking", "psu bank", "financial", "finance", "nbfc",
      "insurance"), ("^NSEBANK", "BANK NIFTY")),
    (("it", "software", "infotech", "information technology", "technology",
      "tech", "digital", "communication services"), ("^CNXIT", "IT")),
    (("pharma", "pharmaceutical", "healthcare", "health", "drug",
      "life sciences"), ("^CNXPHARMA", "PHARMA")),
    (("auto", "automobile", "automotive", "consumer cyclical",
      "consumer durables"), ("^CNXAUTO", "AUTO")),
    (("fmcg", "consumer defensive", "consumer staples", "consumption",
      "consumer goods"), ("^CNXFMCG", "FMCG")),
    (("energy", "oil", "gas", "petroleum", "power", "utilities",
      "utility"), ("^CNXENERGY", "ENERGY")),
    (("metal", "metals", "mining", "steel", "basic materials",
      "materials"), ("^CNXMETAL", "METAL")),
    (("realty", "real estate", "property", "housing"),
     ("^CNXREALTY", "REALTY")),
    (("media", "entertainment", "broadcasting", "publishing"),
     ("^CNXMEDIA", "MEDIA")),
    (("infrastructure", "infra", "cement", "construction", "engineering"),
     ("^CNXINFRA", "INFRA")),
    (("telecom", "telecommunication"), ("^CNXSERVICE", "SERVICES")),
)


def _assert_universe_targets() -> None:
    """Fail loudly at import if a rule points outside :data:`INDEX_UNIVERSE`."""
    targets = {b[0] for _, b in _SECTOR_RULES} | {DEFAULT_BENCHMARK[0]}
    missing = targets - set(UNIVERSE_SYMBOLS)
    if missing:
        raise AssertionError(
            f"benchmark target(s) missing from INDEX_UNIVERSE: {sorted(missing)}"
        )


_assert_universe_targets()


def sector_index_for(sector: str) -> tuple[str, str]:
    """
    Map a sector name to its index, as ``(symbol, label)``.

    Falls back to :data:`DEFAULT_BENCHMARK` for an unknown or empty sector —
    the broad market is always a defensible benchmark, and it keeps the
    index-dip factor alive rather than dropping it to unknown.
    """
    text = (sector or "").strip().lower()
    if not text:
        return DEFAULT_BENCHMARK
    tokens = set(re.split(r"[^a-z0-9]+", text))
    tokens.discard("")
    for keywords, bench in _SECTOR_RULES:
        for kw in keywords:
            # Multi-word keywords match as a phrase; single words match a token
            # so "IT" does not fire on "capital" or "unit".
            if (" " in kw and kw in text) or (kw in tokens):
                return bench
    return DEFAULT_BENCHMARK


# Exchange-traded funds held as "stocks", keyed by base symbol (no .NS/.BO),
# mapped to the tape index each one tracks. An ETF has no P/E, balance sheet or
# earnings of its own, so the stock scorer found nothing to score and ranked
# sector ETFs at 0 with "low confidence" — while the thing that
# actually decides whether an ETF is cheap, its index's drawdown and ten years
# of backtest at that depth, sat unused one module over.
ETF_INDEX = {
    "NIFTYBEES": "^NSEI", "NIFTY1": "^NSEI", "SETFNIF50": "^NSEI",
    "UTINIFTETF": "^NSEI", "NIFTYIETF": "^NSEI", "ICICINIFTY": "^NSEI",
    "HDFCNIFTY": "^NSEI", "NIF100BEES": "^CNX100",
    "JUNIORBEES": "^NSMIDCP", "SETFNN50": "^NSMIDCP",
    "BANKBEES": "^NSEBANK", "SETFNIFBK": "^NSEBANK", "BANKIETF": "^NSEBANK",
    "PSUBNKBEES": "^CNXPSUBANK", "PSUBANK": "^CNXPSUBANK",
    "ITBEES": "^CNXIT", "ITIETF": "^CNXIT", "NETFIT": "^CNXIT",
    "PHARMABEES": "^CNXPHARMA", "HEALTHIETF": "^CNXPHARMA",
    "AUTOBEES": "^CNXAUTO", "AUTOIETF": "^CNXAUTO",
    "INFRABEES": "^CNXINFRA", "CONSUMBEES": "^CNXCONSUM",
    "FMCGIETF": "^CNXFMCG", "METALIETF": "^CNXMETAL",
    "MID150BEES": "NIFTYMIDCAP150.NS", "MIDCAPETF": "NIFTYMIDCAP150.NS",
    "HDFCSML250": "NIFTYSMLCAP250.NS", "SMALLCAP": "NIFTYSMLCAP250.NS",
    "GOLDBEES": "GOLDBEES.NS", "GOLD1": "GOLDBEES.NS", "GOLDIETF": "GOLDBEES.NS",
    "HDFCGOLD": "GOLDBEES.NS", "SETFGOLD": "GOLDBEES.NS", "AXISGOLD": "GOLDBEES.NS",
    "SILVERBEES": "SILVERBEES.NS", "SILVERIETF": "SILVERBEES.NS",
    "HDFCSILVER": "SILVERBEES.NS", "SILVER1": "SILVERBEES.NS",
    # Nasdaq-100 trackers, and MAFANG (NYSE FANG+) for which NASDAQ is the
    # nearest index on the tape — labelled as a proxy, not as the real thing.
    "MON100": "^IXIC", "N100": "^IXIC", "MAFANG": "^IXIC",
}
ETF_PROXY = {"MAFANG"}


def etf_benchmark(symbol: str) -> tuple[str, str] | None:
    """(tape symbol, label) of the index an ETF tracks, or None if not an ETF."""
    base = re.sub(r"\.(NS|BO)$", "", (symbol or "").strip().upper())
    bench = ETF_INDEX.get(base)
    if not bench:
        return None
    label = next((m["label"] for m in INDEX_UNIVERSE if m["symbol"] == bench),
                 bench)
    if base in ETF_PROXY:
        label = f"{label} (proxy)"
    return bench, label


def benchmark_for_stock(symbol: str, sector: str,
                        mcap_class: str = "") -> tuple[str, str]:
    """
    Pick the index a single stock should be judged against.

    Sector wins when we know it: a pharma stock's fortunes track Nifty Pharma
    far more closely than they track a midcap index.  ``mcap_class`` is only
    consulted when the sector is unknown, where size is the next-best proxy.
    """
    if sector:
        bench = sector_index_for(sector)
        if bench != DEFAULT_BENCHMARK:
            return bench

    size = (mcap_class or "").strip().lower()
    if size:
        if "small" in size:
            return ("NIFTYSMLCAP250.NS", "SMALLCAP 250")
        if "mid" in size:
            return ("NIFTY_MIDCAP_100.NS", "MIDCAP 100")

    _ = symbol  # reserved: a per-symbol override table would slot in here
    return DEFAULT_BENCHMARK


# ══════════════════════════════════════════════════════════════════════════
#  ROW BUILDING
# ══════════════════════════════════════════════════════════════════════════

def _clean_closes(closes: Sequence[float] | None) -> list[float]:
    """Drop NaN / non-numeric / non-positive values, preserving order."""
    out: list[float] = []
    if not closes:
        return out
    for value in closes:
        try:
            f = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f) or f <= 0:
            continue
        out.append(f)
    return out


# A one-day move this large in an INDEX or a broad ETF is not a market event.
#
# The two populations, measured on this universe:
#   * Genuine moves. Nifty 50's worst decade day was -13.0% (23 Mar 2020,
#     COVID). The largest genuine move found anywhere in the universe was
#     ^CNXPSUBANK +30% on 2017-10-25 — the government's Rs 2.11 lakh crore bank
#     recapitalisation announcement. Real, and it must be kept.
#   * Splits. GOLDBEES.NS steps +9,900% on 2019-12-23 (a unit split). The
#     SMALLEST step a split can produce is a 2:1, at exactly -50%.
#
# So the boundary has to sit above 30% and at or below 50%. An earlier 25% cut
# threw away 280 real bars of PSU Bank history for the recap rally; 40% keeps
# that and still catches every split, since no index has ever fallen 40% in a
# session. Left untrimmed, the GOLDBEES split alone gave the dip backtest a
# one-year "mean forward return" of 6,463% at the -15% threshold.
#
# Individual STOCKS are a different population and are checked separately, at a
# tighter bound, in main._price_integrity — a share can legitimately fall
# further in a day than an index can, and a false positive there is harmless
# (the holding is flagged for manual review rather than losing history).
CORPORATE_ACTION_1D_MOVE_PCT = 40.0


def trim_corporate_actions(closes, dates=None,
                           threshold_pct: float = CORPORATE_ACTION_1D_MOVE_PCT):
    """
    Drop everything up to and including the last split-like discontinuity.

    A split, bonus or consolidation puts a step change in the price series that
    is not a price move.  Every statistic computed ACROSS that step is wrong:
    drawdowns measured from a pre-split peak, forward returns spanning it, and
    the full-series low.  Truncating to the clean tail keeps whatever history
    is still usable — GOLDBEES retains about six good years — rather than
    discarding a benchmark entirely or, worse, reporting its corrupted numbers.

    Returns ``(closes, dates, info)``.  ``info["events"]`` lists what was found
    so the dashboard can say why a benchmark's history is shorter than the
    decade it asked for.
    """
    values = list(closes or [])
    date_list = list(dates) if dates is not None else None
    info = {"trimmed": False, "dropped": 0, "events": [],
            "threshold_pct": threshold_pct}
    if len(values) < 2:
        return values, date_list, info

    cut = -1
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        if prev <= 0:
            continue
        move = (cur - prev) / prev * 100.0
        if abs(move) >= threshold_pct:
            when = None
            if date_list is not None and i < len(date_list):
                d = date_list[i]
                when = d.isoformat() if hasattr(d, "isoformat") else str(d)
            info["events"].append({"index": i, "move_pct": round(move, 2),
                                   "date": when})
            cut = i

    if cut >= 0:
        info["trimmed"] = True
        info["dropped"] = cut
        values = values[cut:]
        if date_list is not None:
            date_list = date_list[cut:]
    return values, date_list, info


def merge_series(base_dates, base_closes, recent_dates, recent_closes):
    """
    Splice a short, fresh window onto a long, cached history.

    The tape needs two different things from Yahoo that have opposite refresh
    economics: a decade of closes (for the 200 DMA, the full-history high and
    the backtest) which barely changes, and today's close, which does.
    Re-downloading ten years every two minutes to keep the day-change fresh
    would be absurd and would get us rate-limited; letting the whole tape go
    stale for six hours would be worse.  So the long history is cached for
    hours, a five-day window is refetched constantly, and this function joins
    them.

    Merging is BY DATE, not by position.  A positional append would duplicate
    the overlapping bars — the recent window always re-covers the tail of the
    history — and every trailing-return offset downstream would then be
    measuring the wrong distance back.  On a date collision the recent value
    wins, because that is the one that was fetched a moment ago.

    Returns ``(dates, closes)`` in chronological order.
    """
    merged: dict = {}
    for seq_dates, seq_closes in ((base_dates, base_closes),
                                  (recent_dates, recent_closes)):
        if not seq_dates or not seq_closes:
            continue
        for d, c in zip(seq_dates, seq_closes):
            if d is None:
                continue
            try:
                f = float(c)
            except (TypeError, ValueError):
                continue
            if math.isnan(f) or math.isinf(f) or f <= 0:
                continue
            merged[d] = f
    if not merged:
        return [], []
    try:
        keys = sorted(merged)
    except TypeError:
        # Mixed/unorderable date types: sort by string form so the series is at
        # least deterministic rather than arbitrary.
        keys = sorted(merged, key=str)
    return keys, [merged[k] for k in keys]


def _as_bar_date(value):
    """Coerce a bar's date to ``date``, or None.

    Accepts ``date``, ``datetime`` or an ISO-ish string, because the series
    arrives from a cached JSON round trip in one path and straight from pandas
    in the other.
    """
    if hasattr(value, "date") and not isinstance(value, date):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _calendar_gap(earlier, later) -> int | None:
    """Calendar days between two bar dates, or None if they cannot be compared."""
    first, second = _as_bar_date(earlier), _as_bar_date(later)
    if first is None or second is None:
        return None
    return abs((second - first).days)


def _clean_paired(closes, dates):
    """
    Clean ``closes`` while keeping ``dates`` aligned to the survivors.

    :func:`_clean_closes` drops bad values, which would silently desynchronise a
    parallel date list and put the year boundary in the wrong place for the YTD
    column.  When ``dates`` is None the second element comes back None, and
    every date-dependent field degrades to unknown rather than to a wrong
    number.
    """
    values: list[float] = []
    kept: list = []
    have_dates = dates is not None
    seq = list(closes or [])
    dseq = list(dates or [])
    for i, value in enumerate(seq):
        try:
            f = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f) or f <= 0:
            continue
        values.append(f)
        if have_dates and i < len(dseq):
            kept.append(dseq[i])
    if not have_dates or len(kept) != len(values):
        # A ragged date list is worse than none: it would misplace the year
        # boundary without any visible symptom.
        return values, None
    return values, kept


def _pct_back(series, offset: int) -> float | None:
    """
    Percentage change from ``offset`` trading days ago to the last close.

    ``None`` when the series is too short to look that far back — a 3-month
    column filled from a 40-day series would be a 40-day return mislabelled.

    Positional, and therefore only correct on a series with no holes. Prefer
    :func:`_pct_back_dated` whenever dates are available; this remains for
    callers (the backtest) that feed closes with no dates at all.
    """
    if offset <= 0 or len(series) <= offset:
        return None
    past = series[-1 - offset]
    if past <= 0:
        return None
    return round((series[-1] - past) / past * 100, 2)


def _pct_back_dated(series, dates, horizon_days: int,
                    tolerance_days: int) -> float | None:
    """Change over a CALENDAR horizon, from the newest bar at or before it.

    A positional offset assumes every step back is one trading day, which is
    false the moment a series has a hole. Yahoo froze the daily history of
    fifteen NSE indices on 2026-07-17 while still quoting them live, so five
    positions back from today's bar was a date in mid-July: the "1-week"
    column on those tiles was really a two-month return.

    Returns None when no bar sits near the requested horizon, so the column
    reads as unavailable rather than as a number measuring the wrong distance.
    """
    if not dates or len(series) < 2 or len(dates) != len(series):
        return None
    last_date = _as_bar_date(dates[-1])
    if last_date is None:
        return None
    target = last_date - timedelta(days=horizon_days)

    index = None
    for i in range(len(dates) - 2, -1, -1):
        bar_date = _as_bar_date(dates[i])
        if bar_date is not None and bar_date <= target:
            index = i
            break
    if index is None:
        return None
    gap = (last_date - _as_bar_date(dates[index])).days
    if gap > horizon_days + tolerance_days:
        return None
    past = series[index]
    if past <= 0:
        return None
    return round((series[-1] - past) / past * 100, 2)


def _window_52w(series, dates):
    """The trailing 52 weeks of closes: by date when possible, else by count."""
    if dates and len(dates) == len(series):
        last_date = _as_bar_date(dates[-1])
        if last_date is not None:
            cutoff = last_date - timedelta(days=365)
            window = [c for c, d in zip(series, dates)
                      if (_as_bar_date(d) or last_date) >= cutoff]
            if window:
                return window
    return series[-TRADING_DAYS_52W:]


def _trailing(series, dates, horizon: str) -> float | None:
    """Trailing return over ``horizon``: by date when dates exist, else by position."""
    if dates:
        return _pct_back_dated(series, dates,
                               LOOKBACK_CALENDAR_DAYS[horizon],
                               LOOKBACK_TOLERANCE_DAYS[horizon])
    return _pct_back(series, LOOKBACK_TRADING_DAYS[horizon])


def _year_of(value) -> int | None:
    """Year from a date, datetime, or ISO-ish string; None if unreadable."""
    if value is None:
        return None
    year = getattr(value, "year", None)
    if isinstance(year, int):
        return year
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _ytd_pct(series, dates) -> float | None:
    """
    Year-to-date change, measured from the LAST CLOSE OF THE PREVIOUS YEAR.

    That is the convention every quote screen uses, and it is why this needs
    real dates: there is no trading-day offset that lands on the year boundary
    for every index in the universe.  Without dates, or when the series does
    not reach back into last year, the answer is unknown rather than a
    year-to-date figure computed from an arbitrary starting point.
    """
    if not dates or len(dates) != len(series) or len(series) < 2:
        return None
    current = _year_of(dates[-1])
    if current is None:
        return None
    # Walk back to the last bar belonging to an earlier year.
    for i in range(len(series) - 2, -1, -1):
        year = _year_of(dates[i])
        if year is None:
            return None
        if year < current:
            base = series[i]
            if base <= 0:
                return None
            return round((series[-1] - base) / base * 100, 2)
    return None


def _sma(series, window: int) -> float | None:
    """Simple moving average, or None when the series is shorter than window."""
    if window <= 0 or len(series) < window:
        return None
    return sum(series[-window:]) / window


def _rsi(series, period: int = RSI_PERIOD) -> float | None:
    """
    Wilder's RSI.

    Returns None below :data:`MIN_POINTS_FOR_RSI` closes rather than a value
    still dominated by its own seed average.
    """
    if len(series) < MIN_POINTS_FOR_RSI:
        return None
    gains, losses = [], []
    for prev, cur in zip(series, series[1:]):
        delta = cur - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss <= 0:
        # No down-moves across the whole smoothed window: RSI is pinned at 100.
        return 100.0 if avg_gain > 0 else None
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _realised_vol_pct(series, window: int = VOL_WINDOW) -> float | None:
    """Annualised realised volatility over the last `window` sessions, in %.

    Simple returns rather than log returns, and the population standard
    deviation rather than the sample one: the difference is immaterial at
    n=30 daily bars and this way the number matches what every broker screen
    quotes. Annualised by sqrt(252) so it can be read against the usual
    "Nifty runs at 13–15%" reference points.

    Returns None below :data:`MIN_POINTS_FOR_VOL` closes instead of a figure
    computed from a handful of bars, which would swing wildly enough to fire a
    volatility trigger on noise.
    """
    if len(series) < MIN_POINTS_FOR_VOL:
        return None
    closes = series[-(window + 1):]
    rets = [(cur - prev) / prev for prev, cur in zip(closes, closes[1:])
            if prev]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / len(rets)
    return round(variance ** 0.5 * (TRADING_DAYS_YEAR ** 0.5) * 100, 2)


def classify_market_status(off_high_pct: float | None) -> str:
    """
    Map 52-week drawdown onto the status ladder.

    Drawdown alone decides the rung.  Moving averages and RSI are reported on
    the row beside it, but they are deliberately NOT folded in here: DMA
    position and drawdown are the same fact measured twice, and letting a
    momentum oscillator move an index between "normal" and "dip" would make the
    label flip on noise the user cannot act on.  Valuation, which genuinely
    would add information, is not available at all.
    """
    if off_high_pct is None:
        return MARKET_UNKNOWN
    if off_high_pct <= STATUS_OVERHEATED_MAX_DD:
        return MARKET_OVERHEATED
    if off_high_pct < STATUS_NORMAL_MAX_DD:
        return MARKET_NORMAL
    if off_high_pct < STATUS_DIP_MAX_DD:
        return MARKET_DIP
    if off_high_pct < STATUS_ATTRACTIVE_MAX_DD:
        return MARKET_ATTRACTIVE
    return MARKET_HIGH_RISK


# Every metric field a tape row carries, with the value it takes when unknown.
# BOTH row builders start from this dict, so an ok row and an unavailable row
# can never drift out of shape.  That invariant is what lets the dashboard bind
# one set of fields for every chip and lets "the feed is down" render
# differently from "the index is at its high" without a second code path.
_EMPTY_METRICS = {
    "last": None,
    "prev_close": None,
    "day_chg": None,
    "day_chg_pct": None,
    # Calendar days between the last two bars actually on record. A day change
    # is only reported when this is small enough to be one session apart; see
    # MAX_SESSION_GAP_DAYS.
    "day_chg_span_days": None,
    # The move since the previous close on record, over whatever period that
    # turns out to be. Equals day_chg when the bars are adjacent.
    "span_chg": None,
    "span_chg_pct": None,
    "last_bar_date": None,
    "prev_bar_date": None,
    # True when the feed is still quoting a live level but stopped serving
    # daily bars, so every trailing figure on the row is older than it looks.
    "stale_history": False,
    "chg_1w_pct": None,
    "chg_1m_pct": None,
    "chg_3m_pct": None,
    "chg_ytd_pct": None,
    # 52-week statistics, computed from the trailing TRADING_DAYS_52W slice.
    "high_52w": None,
    "low_52w": None,
    "off_high_pct": None,
    "above_low_pct": None,
    # Full-series statistics. NOT labelled all-time: the series is only as long
    # as the caller's download, so the UI must describe this by its actual span
    # (available in "points") rather than claim a record the data cannot prove.
    "high_max": None,
    "low_max": None,
    "off_max_high_pct": None,
    "dma_50": None,
    "dma_100": None,
    "dma_200": None,
    "vs_dma_50_pct": None,
    "vs_dma_100_pct": None,
    "vs_dma_200_pct": None,
    "rsi_14": None,
    # Annualised realised volatility over VOL_WINDOW sessions, in percent.
    "vol_30d_pct": None,
    # Valuation is specified by the dashboard but not obtainable — see
    # VALUATION_UNAVAILABLE_REASON. Emitted as explicit unknowns, never filled.
    "pe": None,
    "pb": None,
    "pe_avg_5y": None,
    "pb_avg_5y": None,
    "valuation_status": VALUATION_UNAVAILABLE,
    "valuation_note": VALUATION_UNAVAILABLE_REASON,
    "market_status": MARKET_UNKNOWN,
    "at_high": False,
    "short_window": False,
    # True until a series long enough to HAVE a high and a low proves otherwise.
    "history_unavailable": True,
    "points": 0,
    "points_52w": 0,
}


def _base_row(meta: dict, status: str) -> dict:
    """Identity fields plus a full set of unknown metrics."""
    row = {
        "symbol": meta["symbol"],
        "label": meta["label"],
        "group": meta["group"],
        "status": status,
    }
    row.update(_EMPTY_METRICS)
    return row


def _unavailable_row(meta: dict) -> dict:
    """A well-formed row for an index whose data never arrived."""
    return _base_row(meta, STATUS_UNAVAILABLE)


def summarize_index(meta: dict, closes: Sequence[float] | None,
                    as_of: date | None = None,
                    dates: Sequence | None = None) -> dict:
    """
    Turn one index's daily closes into a tape row.

    ``closes`` must be in chronological order, oldest first, and may be far
    longer than a year — the backtest feeds a decade through the same path.
    Every 52-week statistic is therefore taken from the trailing
    :data:`TRADING_DAYS_52W` slice, never from the whole series.

    ``dates`` is optional and only powers the year-to-date column, which has no
    correct trading-day offset.  Supply it aligned 1:1 with ``closes``; if it is
    ragged or absent, ``chg_ytd_pct`` comes back None.

    An empty or all-invalid series yields an ``unavailable`` row rather than
    raising, so one dead symbol can never take down the whole tape.
    """
    _ = as_of  # rows are positional, not dated; kept for signature symmetry
    series, kept_dates = _clean_paired(closes, dates)
    if not series:
        return _unavailable_row(meta)

    last = series[-1]
    prev = series[-2] if len(series) >= 2 else None

    # The 52-week window is a SLICE. Using max(series) here would turn a
    # ten-year high into a "52-week high" and inflate every drawdown the
    # deploy engine scores against.
    #
    # By date when dates exist: 252 positions back is 52 weeks only on a series
    # with no holes, and on an index whose history froze in July it reaches a
    # year further back than it claims to.
    window = _window_52w(series, kept_dates)
    high = max(window)
    low = min(window)

    # A day change needs two ADJACENT sessions, which is a statement about
    # dates and not about positions in a list. When the dates say the previous
    # bar on record is weeks old, there is no same-day comparison to report and
    # the field stays None — the trailing-return columns still describe the
    # move over their own stated horizons.
    span_days = None
    if kept_dates and len(kept_dates) >= 2:
        span_days = _calendar_gap(kept_dates[-2], kept_dates[-1])

    # The move since the previous close ON RECORD, whatever its age. For a
    # densely-served index this IS the day change; for one whose history froze
    # it is a multi-week move, and the span travels with it so the UI can say
    # "-6.88% over 54 days" instead of leaving the tile blank. A real number
    # over a stated period beats both a dash and a lie.
    span_chg = None
    span_chg_pct = None
    if prev is not None and prev > 0:
        span_chg = round(last - prev, 2)
        span_chg_pct = round((last - prev) / prev * 100, 2)

    day_chg = None
    day_chg_pct = None
    comparable = (prev is not None and prev > 0
                  and (span_days is None or span_days <= MAX_SESSION_GAP_DAYS))
    if comparable:
        day_chg = span_chg
        day_chg_pct = span_chg_pct

    # One close is not a range. Everything below is a distance FROM a high, and
    # a high that equals today's price makes every one of them zero — which the
    # status ladder then reads as "at its high".
    ranged = len(series) >= MIN_POINTS_FOR_RANGE

    # Positive magnitude: how far below the window high we are sitting.
    off_high_pct = (round((high - last) / high * 100, 2)
                    if ranged and high > 0 else None)
    above_low_pct = (round((last - low) / low * 100, 2)
                     if ranged and low > 0 else None)

    high_max = max(series)
    low_max = min(series)
    off_max_high_pct = (round((high_max - last) / high_max * 100, 2)
                        if ranged and high_max > 0 else None)

    row = _base_row(meta, STATUS_OK)
    row.update({
        "last": round(last, 2),
        # prev_close is reported even when it is too old to compare against,
        # so the UI can say WHY there is no day change instead of just
        # withholding one.
        "prev_close": round(prev, 2) if prev is not None else None,
        "day_chg": day_chg,
        "day_chg_pct": day_chg_pct,
        "day_chg_span_days": span_days,
        "span_chg": span_chg,
        "span_chg_pct": span_chg_pct,
        "stale_history": bool(span_days is not None
                              and span_days > MAX_SESSION_GAP_DAYS),
        "last_bar_date": str(kept_dates[-1]) if kept_dates else None,
        "prev_bar_date": (str(kept_dates[-2])
                          if kept_dates and len(kept_dates) >= 2 else None),
        "chg_1w_pct": _trailing(series, kept_dates, "1w"),
        "chg_1m_pct": _trailing(series, kept_dates, "1m"),
        "chg_3m_pct": _trailing(series, kept_dates, "3m"),
        "chg_ytd_pct": _ytd_pct(series, kept_dates),
        "high_52w": round(high, 2) if ranged else None,
        "low_52w": round(low, 2) if ranged else None,
        "off_high_pct": off_high_pct,
        "above_low_pct": above_low_pct,
        "high_max": round(high_max, 2) if ranged else None,
        "low_max": round(low_max, 2) if ranged else None,
        "off_max_high_pct": off_max_high_pct,
        "rsi_14": _rsi(series),
        "vol_30d_pct": _realised_vol_pct(series),
        "at_high": off_high_pct is not None and off_high_pct <= AT_HIGH_TOLERANCE_PCT,
        # Explicit, so the tape can label the card instead of drawing a blank.
        "history_unavailable": not ranged,
        # A partial window is still useful, but the caller must know the
        # "52-week" high is really an N-day high.
        "short_window": len(window) < MIN_POINTS_FOR_52W,
        "points": len(series),
        "points_52w": len(window),
        "market_status": classify_market_status(off_high_pct),
    })

    for win in DMA_WINDOWS:
        dma = _sma(series, win)
        row[f"dma_{win}"] = round(dma, 2) if dma is not None else None
        row[f"vs_dma_{win}_pct"] = (round((last - dma) / dma * 100, 2)
                                    if dma and dma > 0 else None)

    return row


# ══════════════════════════════════════════════════════════════════════════
#  TAPE ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════

def build_tape(rows: Sequence[dict], as_of: date | None = None) -> dict:
    """
    Assemble tape rows into the API payload.

    Rows are returned in :data:`INDEX_UNIVERSE` order, not the order supplied,
    so the dashboard's chip layout is stable between refreshes.  Groups are
    always emitted in :data:`GROUP_ORDER`, and a group whose every member is
    unavailable still appears with its rows — the UI decides whether to hide it.
    """
    by_symbol = {r.get("symbol"): r for r in (rows or []) if isinstance(r, dict)}

    ordered: list[dict] = []
    for meta in INDEX_UNIVERSE:
        row = by_symbol.get(meta["symbol"])
        ordered.append(row if row else _unavailable_row(meta))

    ok_rows = [r for r in ordered if r["status"] == STATUS_OK]
    # Breadth counts only indices with a real session-over-session move. A
    # sparsely-served index has no day change at all, and treating its null as
    # a flat day would quietly pad "unchanged" with indices that simply were
    # not comparable.
    comparable_rows = [r for r in ok_rows if r.get("day_chg_pct") is not None]
    up = sum(1 for r in comparable_rows if r["day_chg_pct"] > 0)
    down = sum(1 for r in comparable_rows if r["day_chg_pct"] < 0)

    groups = []
    for key in GROUP_ORDER:
        members = [r for r in ordered if r["group"] == key]
        if not members:
            continue
        groups.append({
            "key": key,
            "label": GROUP_LABELS[key],
            "symbols": [r["symbol"] for r in members],
        })

    return {
        "as_of": (as_of or date.today()).isoformat(),
        "indices": ordered,
        "groups": groups,
        "breadth": {
            "up": up,
            "down": down,
            # Flat means genuinely unchanged, so it counts only comparable
            # rows; indices with no prior session are reported separately
            # rather than being folded in as unchanged.
            "flat": len(comparable_rows) - up - down,
            "comparable": len(comparable_rows),
            "no_prior_session": len(ok_rows) - len(comparable_rows),
            "available": len(ok_rows),
            "total": len(ordered),
        },
        "market_mood": _market_mood(ordered),
        "summary": _summary_line(ordered),
    }


def dip_map(tape: dict) -> dict[str, float | None]:
    """
    Extract ``{symbol: off_high_pct}`` for :mod:`deploy_engine`.

    Unavailable indices map to ``None``, not ``0.0``.  ``score_index_dip``
    treats ``None`` as "unknown" and drops the factor from that candidate's
    composite, which is the honest answer when the feed is down.
    """
    out: dict[str, float | None] = {}
    for row in (tape or {}).get("indices", []):
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        if not symbol:
            continue
        out[symbol] = row.get("off_high_pct") if row.get("status") == STATUS_OK else None
    return out


def _market_mood(rows: Sequence[dict]) -> str:
    """
    A one-word read on the broad market, driven by the Nifty 50 row alone.

    Deliberately NOT an average across the universe: a tape that is 8 sector
    indices and 2 metal ETFs would let commodities outvote the equity market
    the user actually invests in.
    """
    nifty = next((r for r in rows if r["symbol"] == "^NSEI"
                  and r["status"] == STATUS_OK), None)
    if not nifty or nifty.get("off_high_pct") is None:
        return "unknown"
    off = nifty["off_high_pct"]
    if off >= 12:
        return "deep-fall"
    if off >= 6:
        return "falling"
    if off >= 2:
        return "soft"
    return "near-high"


def _summary_line(rows: Sequence[dict]) -> str:
    """Plain-English one-liner for the dashboard header."""
    nifty = next((r for r in rows if r["symbol"] == "^NSEI"
                  and r["status"] == STATUS_OK), None)
    if not nifty or nifty.get("off_high_pct") is None:
        return "Market levels are not available right now."
    off = nifty["off_high_pct"]
    if off <= AT_HIGH_TOLERANCE_PCT:
        return "Nifty 50 is at its 1-year high."
    return f"Nifty 50 is {off:.1f}% below its 1-year high."


def empty_tape(as_of: date | None = None) -> dict:
    """
    A well-formed tape with every index unavailable.

    Built through :func:`build_tape` so the empty payload can never drift out
    of shape from the populated one.
    """
    return build_tape([], as_of=as_of)
