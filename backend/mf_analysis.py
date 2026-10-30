"""
Mutual Fund Research Engine — valuation-aware, consistency-first screener.

Implements a research-analyst framework:
  - Category-aware benchmark selection (per-fund, from AMFI scheme category)
  - Rolling 3Y return distribution (avg/median/min/max, % positive, % >= 8/10/12/15/20)
  - % of rolling windows beating the benchmark
  - SIP XIRR (3Y/5Y), Sharpe, Sortino, Jensen's alpha, beta, information ratio
  - Max drawdown + recovery, downside/upside capture, current drawdown
  - Weighted 0-100 composite score, renormalized over data-available components
  - Decision labels: ENTER NOW / ENTER GRADUALLY / SIP ONLY / WAIT / AVOID FRESH ENTRY
  - Explicit DATA GAP handling: TER, AUM, manager and portfolio P/E-P/B are not
    published by the free NAV feeds used here and are never estimated.

Data sources: mfapi.in (NAV history), Yahoo Finance (benchmark indices —
price-return, NOT TRI; alpha/outperformance vs PR indices runs ~1-1.5%/yr
generous and is labeled as such).
"""
import bisect, math, re, logging, requests, yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger("mf_analysis")
MFAPI = "https://api.mfapi.in/mf"
FINAPI = "https://finapi.upvaly.com/api"
KUVERA = "https://api.kuvera.in/mf/api"
UA = {"User-Agent": "Mozilla/5.0"}
RF = 6.5  # Risk-free rate %
ROLL_START = datetime(2020, 1, 1)  # rolling-return observation window start

# ── Search: returns ALL matching Direct-Growth funds for the user to pick ──
def _search_finapi(category: str, seen: set, out: list) -> None:
    """Primary search source. FinAPI returns structured plan/option/category
    fields, so Direct-Growth filtering is exact (not string-matching), and it
    stays up when mfapi.in is flaky. One call, generous timeout."""
    try:
        r = requests.get(f"{FINAPI}/mf/search",
                         params={"schemeName": category}, timeout=25, headers=UA)
        if r.status_code != 200:
            return
        d = r.json()
        rows = d.get("data") if isinstance(d, dict) else d
        for f in rows or []:
            code = str(f.get("schemeCode", ""))
            if not code.isdigit():
                continue
            code = int(code)
            if code in seen:
                continue
            plan = (f.get("planName") or "").lower()
            opt = (f.get("optionName") or "").lower()
            name = f.get("schemeName", "")
            # Exact Direct-Growth filter; exclude Regular and IDCW/dividend plans
            if "direct" not in plan or "growth" not in opt or "idcw" in opt or "dividend" in opt:
                continue
            seen.add(code)
            out.append({
                "scheme_code": code,
                "scheme_name": name,
                "amc": (f.get("fundHouse") or name.split(" ")[0]),
                "category": f.get("schemeCategory"),
                "source": "finapi",
            })
    except Exception as e:
        logger.error(f"finapi search error for '{category}': {e}")


def _search_mfapi(category: str, seen: set, out: list) -> None:
    """Fallback search source (mfapi.in). Direct-Growth is inferred from the
    scheme-name string since mfapi has no structured plan/option fields."""
    for q in (f"{category} direct growth", f"{category} direct plan growth"):
        try:
            r = requests.get(f"{MFAPI}/search", params={"q": q}, timeout=8)
            if r.status_code != 200:
                continue
            for f in r.json():
                code = f["schemeCode"]
                name = f.get("schemeName", "")
                nu = name.upper()
                if code in seen or "DIRECT" not in nu or "IDCW" in nu or "DIVIDEND" in nu:
                    continue
                seen.add(code)
                out.append({
                    "scheme_code": code,
                    "scheme_name": name,
                    "amc": name.split(" ")[0] if name else "",
                    "source": "mfapi",
                })
        except Exception as e:
            logger.error(f"mfapi search error for '{q}': {e}")


def search_funds(category: str, kite_client=None) -> List[Dict]:
    """Search Direct-Growth funds by name/category. FinAPI first, mfapi.in as
    fallback so search still works when either provider is down."""
    results: List[Dict] = []
    seen: set = set()

    _search_finapi(category, seen, results)
    if not results:  # FinAPI down or no hit — fall back to mfapi.in
        _search_mfapi(category, seen, results)

    results.sort(key=lambda x: x["scheme_name"])
    return results[:40]


# ── NAV Fetch (mfapi.in primary, FinAPI fallback) ──
# Both are normalized to the mfapi shape {"meta": {...}, "data": [{date, nav}]}
# so downstream parsing is source-agnostic. Either provider going down no
# longer breaks the analysis.
def _fetch_navs_mfapi(code: int) -> Optional[Dict]:
    try:
        r = requests.get(f"{MFAPI}/{code}", timeout=15)
        if r.status_code != 200:
            return None
        d = r.json()
        return d if d.get("status") == "SUCCESS" and d.get("data") else None
    except Exception:
        return None

def _fetch_navs_finapi(code: int) -> Optional[Dict]:
    try:
        r = requests.get(f"{FINAPI}/mf/scheme-code/{code}/nav",
                         params={"startDate": "2005-01-01", "endDate": "2100-01-01"},
                         timeout=45, headers=UA)
        if r.status_code != 200:
            return None
        d = r.json()
        data = d.get("data") if isinstance(d, dict) else None
        hist = (data or {}).get("navHistory") or []
        if not hist:
            return None
        # FinAPI: navDate 'YYYY-MM-DD' → mfapi 'DD-MM-YYYY' string for parse_navs
        out_data = []
        for h in hist:
            dd = str(h.get("navDate", ""))
            if len(dd) == 10 and dd[4] == "-":
                out_data.append({"date": f"{dd[8:10]}-{dd[5:7]}-{dd[0:4]}", "nav": h.get("nav")})
        return {
            "meta": {
                "scheme_name": data.get("schemeName", f"Fund {code}"),
                "fund_house": data.get("fundHouse", ""),
                "scheme_category": "",  # supplied by the FinAPI compare batch
            },
            "data": out_data,
        }
    except Exception as e:
        logger.error(f"finapi nav error for {code}: {e}")
        return None

def fetch_navs(code: int) -> Optional[Dict]:
    return _fetch_navs_mfapi(code) or _fetch_navs_finapi(code)

def parse_navs(raw) -> list:
    """Parse a NAV history into sorted ``[{date, nav}]``.

    Accepts EITHER the raw payload from :func:`fetch_navs` (a dict carrying a
    "data" list) or that list directly.  Both fetchers return the dict, and a
    caller that forgot to unwrap it used to iterate the dict's KEYS — walking
    the strings "meta", "data", "status", failing on each, and returning an
    empty list.  That failure is completely silent: the caller sees no history
    and concludes the fund has no NAV peak.  It cost every mutual fund its
    own-drawdown factor in the deployment engine before it was noticed, so the
    shape is normalised here rather than trusted at each call site.
    """
    if isinstance(raw, dict):
        raw = raw.get("data") or []
    out = []
    for item in (raw or []):
        if not isinstance(item, dict):
            continue
        try:
            dt = datetime.strptime(item["date"], "%d-%m-%Y")
            out.append({"date": dt, "nav": float(item["nav"])})
        except Exception:
            pass
    out.sort(key=lambda x: x["date"])
    return out

# ── Benchmark selection & fetch ──
# Yahoo Finance symbols are price-return (PR) indices; TRI is not freely
# available. Ordering matters: more specific matches first.
_BENCHMARK_RULES = [
    # International and commodity funds come FIRST: a "Nasdaq 100 Index Fund"
    # contains the token "index", and a gold FoF contains "fund of funds", so
    # any broad rule placed above these would swallow them and benchmark a US
    # tech index against the Nifty 50.
    (("nasdaq", "ndq"),                            ("^IXIC",      "NASDAQ")),
    (("s&p 500", "sp 500", "s&p500", "us equity",
      "america", "american"),                      ("^GSPC",      "S&P 500")),
    (("gold",),                                    ("GOLDBEES.NS", "Gold (ETF)")),
    (("silver",),                                  ("SILVERBEES.NS", "Silver (ETF)")),

    (("next 50", "junior"),                        ("^NSMIDCP",   "Nifty Next 50")),
    # Verified live: NIFTYSMLCAP250.NS returns ~2,465 daily closes over 9.8
    # years, so the old "no free smallcap feed exists" note is out of date and
    # the Nifty 500 proxy is no longer needed. market_indices already tapes
    # this symbol.
    (("smallcap", "small cap", "small"),           ("NIFTYSMLCAP250.NS", "Nifty Smallcap 250")),
    (("midcap", "mid"),                            ("NIFTY_MIDCAP_100.NS", "Nifty Midcap 100")),
    (("bank", "banking", "financial"),             ("^NSEBANK",   "Nifty Bank")),
    (("technology", "digital", "infotech"),        ("^CNXIT",     "Nifty IT")),
    (("pharma", "healthcare", "health"),           ("^CNXPHARMA", "Nifty Pharma")),
    (("auto",),                                    ("^CNXAUTO",   "Nifty Auto")),
    (("fmcg", "consumption", "consumer"),          ("^CNXFMCG",   "Nifty FMCG")),
    (("infrastructure", "infra"),                  ("^CNXINFRA",  "Nifty Infrastructure")),
    (("energy",),                                  ("^CNXENERGY", "Nifty Energy")),
    (("metal",),                                   ("^CNXMETAL",  "Nifty Metal")),
    (("realty",),                                  ("^CNXREALTY", "Nifty Realty")),
    (("flexi", "multi", "elss", "tax", "focused",
      "value", "contra", "500"),                   ("^CRSLDX",    "Nifty 500")),
]

def _assert_benchmarks_are_taped() -> None:
    """Fail loudly at import if a rule points outside the taped universe.

    pick_benchmark's symbols are used as keys into market_indices.dip_map().  A
    symbol that is not in INDEX_UNIVERSE resolves to nothing there, silently
    knocking the index-dip factor out of every fund mapped to it — the same
    class of silent hole this module already guards against for stocks.
    """
    try:
        import market_indices
    except Exception:
        return  # import-order safety; the dedicated test still covers this
    universe = set(market_indices.UNIVERSE_SYMBOLS)
    targets = {sym for _kw, (sym, _label) in _BENCHMARK_RULES} | {"^NSEI"}
    missing = targets - universe
    if missing:
        raise AssertionError(
            f"benchmark target(s) missing from INDEX_UNIVERSE: {sorted(missing)}")


_assert_benchmarks_are_taped()


def pick_benchmark(text: str) -> tuple:
    """Map a scheme category / name to the closest Yahoo benchmark symbol."""
    t = (text or "").lower()
    tokens = set(re.split(r"[^a-z0-9]+", t))
    for keywords, bench in _BENCHMARK_RULES:
        for kw in keywords:
            if (" " in kw and kw in t) or (kw in tokens):
                return bench
    return ("^NSEI", "Nifty 50")

# ── Fund extras via FinAPI (finapi.upvaly.com) — primary source ──
# One batched call per analysis, joined by the same scheme codes as mfapi.in.
# Supplies TER, exit load, AUM, managers, Morningstar rating, official TRI
# benchmark name, portfolio P/E-P/B + category averages, concentration,
# sector/market-cap splits, category ranks and stock-level holdings.
def _fnum(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("₹", "").strip())
    except (ValueError, TypeError):
        return None

def fetch_finapi_batch(codes: List[int]) -> Dict[int, Dict]:
    try:
        r = requests.get(f"{FINAPI}/mf/compare",
                         params={"funds": ",".join(str(c) for c in codes),
                                 "fields": "portfolio,ranks,fundamentals,sectors,holdings"},
                         timeout=60, headers=UA)
        if r.status_code != 200:
            return {}
        data = r.json().get("data") or []
        return {int(f["schemeCode"]): f for f in data if str(f.get("schemeCode", "")).isdigit()}
    except Exception as e:
        logger.error(f"finapi batch error: {e}")
        return {}

def _finapi_extras(fund: Dict) -> Dict:
    """Normalize one FinAPI compare record. Includes '_holdings' (popped by
    the caller for overlap math). Only present values are returned."""
    fdm = fund.get("fundamentals") or {}
    pf = fund.get("portfolio") or {}
    conc = pf.get("concentration") or {}
    alloc = pf.get("assetAllocation") or {}
    mcap = pf.get("marketCapWeightage") or {}
    pe, cat_pe = _fnum(fdm.get("pe")), _fnum(fdm.get("categoryAveragePe"))
    pb, cat_pb = _fnum(fdm.get("pb")), _fnum(fdm.get("categoryAveragePb"))
    rel_pe = round(pe / cat_pe, 2) if pe and cat_pe else None
    valuation = None
    if rel_pe is not None:
        valuation = ("Relatively undervalued" if rel_pe < 0.90 else
                     "Fairly valued" if rel_pe <= 1.10 else
                     "Slightly overvalued" if rel_pe <= 1.25 else "Overvalued")
    ranks = {r.get("timeframe"): r for r in (fund.get("ranks") or [])}
    def cat_avg(tf):
        return _fnum((ranks.get(tf) or {}).get("categoryAverage"))
    def cat_rank(tf):
        return (ranks.get(tf) or {}).get("rankInCategory")
    holdings = [(h["name"], _fnum(h.get("weightage")) or 0.0)
                for h in (fund.get("holdings") or []) if h.get("name")]
    out = {
        "ter": _fnum(fund.get("expenseRatio")),
        "aum_cr": _fnum(fund.get("aum")),
        "managers": fund.get("schemeFundManagers"),
        "fund_rating": fund.get("morningStarRating"),
        "exit_load": fund.get("exitLoadMessage"),
        "benchmark_official": fund.get("benchmarkIndex"),
        "portfolio_pe": pe, "portfolio_pb": pb,
        "category_pe": cat_pe, "category_pb": cat_pb,
        "relative_pe": rel_pe, "valuation": valuation,
        "div_yield": _fnum(fdm.get("dividendYield")),
        "roe": _fnum(fdm.get("roe")),
        "holdings_count": conc.get("numberOfHoldings"),
        "top5_weight": _fnum(conc.get("top5StocksWeight")),
        "top10_weight": _fnum(conc.get("top10StocksWeight")),
        "top3_sector_weight": _fnum(conc.get("top3SectorWeight")),
        "cash_pct": _fnum(alloc.get("cashAllocation")),
        "large_cap_pct": _fnum(mcap.get("largeCap")),
        "mid_cap_pct": _fnum(mcap.get("midCap")),
        "small_cap_pct": _fnum(mcap.get("smallCap")),
        "cat_avg_1y": cat_avg("1Y"), "cat_avg_3y": cat_avg("3Y"), "cat_avg_5y": cat_avg("5Y"),
        "cat_rank_1y": cat_rank("1Y"), "cat_rank_3y": cat_rank("3Y"), "cat_rank_5y": cat_rank("5Y"),
        "top_holdings": [n for n, _ in holdings[:5]] or None,
        "extras_source": "FinAPI",
        "_holdings": holdings,
    }
    return {k: v for k, v in out.items() if v is not None}


# ── Fund extras (TER, AUM, managers) via Kuvera public API — fallback ──
# Kuvera has no ISIN lookup, so funds are matched by normalized-name token
# overlap. Matching is conservative: an ambiguous match returns nothing
# (DATA GAP) rather than risking another fund's TER/AUM.
_kuvera_list_cache: Optional[list] = None
_STOP_TOKENS = {"fund", "plan", "option", "scheme", "the", "of", "an", ""}

def _name_tokens(name: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t not in _STOP_TOKENS}

def _kuvera_direct_growth_list() -> list:
    """Flat [(code, name)] of Direct-Growth schemes from Kuvera's fund list."""
    global _kuvera_list_cache
    if _kuvera_list_cache is None:
        flat = []
        try:
            d = requests.get(f"{KUVERA}/v4/fund_schemes/list.json", timeout=25, headers=UA).json()
            for cats in d.values():
                for houses in cats.values():
                    for funds in houses.values():
                        for f in funds:
                            code, name = f.get("c", ""), f.get("n", "")
                            if code.endswith("-GR") and "direct" in name.lower():
                                flat.append((code, name))
        except Exception as e:
            logger.error(f"kuvera list error: {e}")
        _kuvera_list_cache = flat
    return _kuvera_list_cache

def fetch_fund_extras(scheme_name: str) -> Dict:
    """TER, AUM (₹ Cr), manager names and ratings for a scheme, or {} on no
    confident match. All values are provider-reported (Kuvera), with dates."""
    toks = _name_tokens(scheme_name)
    if not toks:
        return {}
    brand = re.split(r"[^a-z0-9]+", scheme_name.lower().strip())[0]
    best_code, best_j = None, 0.0
    for code, name in _kuvera_direct_growth_list():
        kt = _name_tokens(name)
        if brand not in kt:
            continue
        j = len(toks & kt) / len(toks | kt)
        if j > best_j:
            best_j, best_code = j, code
    if best_code is None or best_j < 0.8:
        return {}
    try:
        det = requests.get(f"{KUVERA}/v5/fund_schemes/{best_code}.json", timeout=15, headers=UA).json()
        if not det:
            return {}
        d = det[0]
        ter = float(d["expense_ratio"]) if d.get("expense_ratio") else None
        # Kuvera reports AUM in ₹ millions (verified vs known fund sizes) → ₹ Cr
        aum_cr = round(d["aum"] / 10) if d.get("aum") else None
        return {
            "ter": ter,
            "ter_date": d.get("expense_ratio_date"),
            "aum_cr": aum_cr,
            "managers": d.get("fund_manager"),
            "fund_rating": d.get("fund_rating"),
            "crisil_rating": d.get("crisil_rating"),
            "kuvera_name": d.get("name"),
            "extras_source": "Kuvera",
        }
    except Exception as e:
        logger.error(f"kuvera detail error for {best_code}: {e}")
        return {}

def fetch_benchmark(symbol="^NSEI", period="10y") -> list:
    try:
        h = yf.Ticker(symbol).history(period=period)
        if h.empty:
            return []
        return [{"date": d.to_pydatetime().replace(tzinfo=None), "nav": float(v)} for d, v in h["Close"].items()]
    except:
        return []

# ── Helpers ──
def _find_nav(target, data, max_days=30):
    best, best_d = None, timedelta(days=max_days)
    for item in data:
        d = abs(item["date"] - target)
        if d < best_d:
            best_d = d; best = item
    return best

def _nearest_factory(data, max_days=30):
    """O(log n) nearest-date lookup over a date-sorted NAV series."""
    dates = [x["date"] for x in data]
    limit = timedelta(days=max_days)
    def nearest(target, max_days_override=None):
        lim = timedelta(days=max_days_override) if max_days_override else limit
        i = bisect.bisect_left(dates, target)
        best, best_d = None, lim
        for j in (i - 1, i):
            if 0 <= j < len(dates):
                d = abs(dates[j] - target)
                if d < best_d:
                    best_d = d; best = data[j]
        return best
    return nearest

def _cagr(s, e, y):
    return ((e / s) ** (1 / y) - 1) * 100 if s > 0 and y > 0 else 0

def _clamp01(x):
    return max(0.0, min(1.0, x))

def _median(vals):
    s = sorted(vals); n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

def _sip_xirr(navs, nearest, months, amount=10000.0):
    """XIRR of a monthly SIP over the trailing `months`, valued at latest NAV."""
    end = navs[-1]
    if (end["date"] - navs[0]["date"]).days < months * 30 + 25:
        return None  # history too short — DATA GAP, do not estimate
    flows, units = [], 0.0
    for k in range(months, 0, -1):
        dt = end["date"] - timedelta(days=round(30.44 * k))
        n = nearest(dt, 12)
        if not n:
            return None
        units += amount / n["nav"]
        flows.append((n["date"], amount))
    fv = units * end["nav"]
    # FV(r) = Σ amt·(1+r)^t − final value, monotonic in r → bisection
    def f(r):
        return sum(a * (1 + r) ** ((end["date"] - d).days / 365.25) for d, a in flows) - fv
    lo, hi = -0.95, 4.0
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(90):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2 * 100, 2)

# ── Core Metrics ──
def calc_metrics(navs: list, bm: list = None, bm_name: str = None) -> Dict:
    if len(navs) < 100:
        return {"error": "Insufficient data (need 100+ NAV points)"}

    nearest = _nearest_factory(navs)
    bm_nearest = _nearest_factory(bm) if bm else None

    cur = navs[-1]; cd = cur["date"]; cn = cur["nav"]
    y1 = cd - timedelta(365)
    y3 = cd - timedelta(365 * 3)
    y5 = cd - timedelta(365 * 5)
    y7 = cd - timedelta(round(365.25 * 7))
    y10 = cd - timedelta(round(365.25 * 10))

    def point_cagr(target, years, max_days=30):
        n = nearest(target, max_days)
        # Guard against a young fund matching its own inception for a long window
        if n and abs((cd - n["date"]).days / 365.25 - years) < 0.25:
            return round(_cagr(n["nav"], cn, (cd - n["date"]).days / 365.25), 2)
        return None

    n3 = nearest(y3)
    c1 = point_cagr(y1, 1)
    c3 = point_cagr(y3, 3)
    c5 = point_cagr(y5, 5)
    c7 = point_cagr(y7, 7, 45)
    c10 = point_cagr(y10, 10, 45)

    # SIP XIRR — calculated, not provider-reported
    xirr3 = _sip_xirr(navs, nearest, 36)
    xirr5 = _sip_xirr(navs, nearest, 60)

    # Daily returns (3Y window)
    d3 = [d for d in navs if d["date"] >= y3]
    rets = [(d3[i]["nav"] / d3[i - 1]["nav"]) - 1 for i in range(1, len(d3))] if len(d3) > 20 else []

    ann_ret = 0; vol = 0; sharpe = None; sortino = None
    if rets:
        avg_r = sum(rets) / len(rets)
        ann_ret = ((1 + avg_r) ** 252 - 1) * 100
        var = sum((r - avg_r) ** 2 for r in rets) / len(rets)
        vol = math.sqrt(var) * math.sqrt(252) * 100
        sharpe = round((ann_ret - RF) / vol, 2) if vol > 0 else 0
        down = [r for r in rets if r < 0]
        if down:
            dd_ = math.sqrt(sum(r ** 2 for r in down) / len(rets)) * math.sqrt(252) * 100
            sortino = round((ann_ret - RF) / dd_, 2) if dd_ > 0 else 99
        else:
            sortino = 99

    # ── Rolling 3Y returns from 2020 (weekly-ish sampling for speed) ──
    pts = [x for x in navs if x["date"] >= ROLL_START]
    step = max(1, len(pts) // 500)
    rolls = []
    ge = {8: 0, 10: 0, 12: 0, 15: 0, 20: 0}
    neg = 0
    bm_cmp = 0; bm_beat = 0
    for item in pts[::step]:
        p = nearest(item["date"] - timedelta(365 * 3))
        if not (p and (item["date"] - p["date"]).days > 900):
            continue
        yrs = (item["date"] - p["date"]).days / 365.25
        rc = _cagr(p["nav"], item["nav"], yrs)
        rolls.append(rc)
        if rc < 0:
            neg += 1
        for k in ge:
            if rc >= k:
                ge[k] += 1
        if bm_nearest:
            be = bm_nearest(item["date"], 10)
            bs = bm_nearest(p["date"], 10)
            if be and bs and (be["date"] - bs["date"]).days > 900:
                brc = _cagr(bs["nav"], be["nav"], (be["date"] - bs["date"]).days / 365.25)
                bm_cmp += 1
                if rc > brc:
                    bm_beat += 1

    nroll = len(rolls)
    r_avg = round(sum(rolls) / nroll, 2) if nroll else None
    r_med = round(_median(rolls), 2) if nroll else None
    r_min = round(min(rolls), 2) if nroll else None
    r_max = round(max(rolls), 2) if nroll else None
    r_pos = round((nroll - neg) / nroll * 100, 1) if nroll else None
    roll_ge = {k: (round(v / nroll * 100, 1) if nroll else None) for k, v in ge.items()}
    beat_bm = round(bm_beat / bm_cmp * 100, 1) if bm_cmp >= 20 else None

    # ── Max drawdown, recovery, current drawdown (full history) ──
    peak = -1.0; max_dd = 0.0
    mdd_peak_nav = None; mdd_trough_idx = None
    for i, x in enumerate(navs):
        if x["nav"] > peak:
            peak = x["nav"]
        dd = (x["nav"] / peak - 1) * 100
        if dd < max_dd:
            max_dd = dd
            mdd_peak_nav = peak
            mdd_trough_idx = i
    recovery_days = None
    if mdd_trough_idx is not None and mdd_peak_nav:
        for x in navs[mdd_trough_idx:]:
            if x["nav"] >= mdd_peak_nav:
                recovery_days = (x["date"] - navs[mdd_trough_idx]["date"]).days
                break
    current_dd = round((cn / peak - 1) * 100, 2)
    max_dd = round(max_dd, 2)

    # ── Benchmark-relative: beta, TE, Jensen's alpha, IR, capture ratios ──
    alpha, bm3, beta, tracking_error, info_ratio = None, None, None, None, None
    down_capture, up_capture = None, None
    if bm and n3:
        bc = bm_nearest(cd); b3 = bm_nearest(y3)
        if bc and b3:
            bm3 = round(_cagr(b3["nav"], bc["nav"], (bc["date"] - b3["date"]).days / 365.25), 2)

        # Align fund & benchmark on shared trading days over the 3Y window
        bm_map = {b["date"].date(): b["nav"] for b in bm}
        aligned = [(d["date"], d["nav"], bm_map[d["date"].date()])
                   for d in d3 if d["date"].date() in bm_map and d["nav"] > 0]
        if len(aligned) > 60:
            fr, br = [], []
            for i in range(1, len(aligned)):
                _, pf, pb = aligned[i - 1]
                _, cf, cb = aligned[i]
                if pf > 0 and pb > 0:
                    fr.append(cf / pf - 1)
                    br.append(cb / pb - 1)
            n = len(fr)
            if n > 60:
                mf_ = sum(fr) / n
                mb_ = sum(br) / n
                var_b = sum((x - mb_) ** 2 for x in br) / n
                cov = sum((fr[i] - mf_) * (br[i] - mb_) for i in range(n)) / n
                beta = round(cov / var_b, 2) if var_b > 0 else None
                active = [fr[i] - br[i] for i in range(n)]
                ma = sum(active) / n
                te_var = sum((a - ma) ** 2 for a in active) / n
                tracking_error = round(math.sqrt(te_var) * math.sqrt(252) * 100, 2)
                fund_ann = ((1 + mf_) ** 252 - 1) * 100
                bm_ann = ((1 + mb_) ** 252 - 1) * 100
                if beta is not None:
                    alpha = round(fund_ann - (RF + beta * (bm_ann - RF)), 2)
                if tracking_error and tracking_error > 0:
                    info_ratio = round((fund_ann - bm_ann) / tracking_error, 2)

            # Monthly capture ratios from the aligned window
            by_month = {}
            for dt, f, b in aligned:
                by_month[(dt.year, dt.month)] = (f, b)  # last obs of month wins
            mk = sorted(by_month)
            mfr, mbr = [], []
            for i in range(1, len(mk)):
                pf, pb = by_month[mk[i - 1]]
                cf, cb = by_month[mk[i]]
                mfr.append(cf / pf - 1)
                mbr.append(cb / pb - 1)
            downs = [(mfr[i], mbr[i]) for i in range(len(mbr)) if mbr[i] < 0]
            ups = [(mfr[i], mbr[i]) for i in range(len(mbr)) if mbr[i] > 0]
            if len(downs) >= 6:
                fd = sum(f for f, _ in downs) / len(downs)
                bd = sum(b for _, b in downs) / len(downs)
                if bd < 0:
                    down_capture = round(fd / bd * 100, 1)
            if len(ups) >= 6:
                fu = sum(f for f, _ in ups) / len(ups)
                bu = sum(b for _, b in ups) / len(ups)
                if bu > 0:
                    up_capture = round(fu / bu * 100, 1)

        # Fallback: simple excess return if a regression was not possible
        if alpha is None and bm3 is not None and c3 is not None:
            alpha = round(c3 - bm3, 2)

    # ── Underperformance duration: consecutive months (from today, walking
    # back) in which the fund's trailing-1Y return lagged the benchmark's ──
    underperf_months = None
    if bm_nearest:
        k = 0
        while k <= 36:
            end_t = cd - timedelta(days=round(30.44 * k))
            f_e = nearest(end_t, 10); f_s = nearest(end_t - timedelta(365), 15)
            b_e = bm_nearest(end_t, 10); b_s = bm_nearest(end_t - timedelta(365), 15)
            if not (f_e and f_s and b_e and b_s):
                break
            if f_e["nav"] / f_s["nav"] >= b_e["nav"] / b_s["nav"]:
                break
            k += 1
        underperf_months = k

    # Fund age / inception
    inception = navs[0]["date"].strftime("%d %b %Y")
    data_years = round((navs[-1]["date"] - navs[0]["date"]).days / 365.25, 1)

    return {
        "nav": round(cn, 4), "nav_date": cd.strftime("%d %b %Y"),
        "inception": inception, "years": data_years,
        "cagr_1y": c1, "cagr_3y": c3, "cagr_5y": c5, "cagr_7y": c7, "cagr_10y": c10,
        "xirr_3y": xirr3, "xirr_5y": xirr5,
        "bm_3y_cagr": bm3, "bm_name": bm_name,
        "rolling_avg": r_avg, "rolling_median": r_med,
        "rolling_min": r_min, "rolling_max": r_max,
        "rolling_consistency": r_pos,
        "rolling_count": nroll, "rolling_neg": neg,
        "roll_ge8": roll_ge[8], "roll_ge10": roll_ge[10], "roll_ge12": roll_ge[12],
        "roll_ge15": roll_ge[15], "roll_ge20": roll_ge[20],
        "roll_beat_bm": beat_bm,
        "sharpe": sharpe, "sortino": sortino, "alpha": alpha,
        "beta": beta, "info_ratio": info_ratio,
        "volatility": round(vol, 2) if vol else None,
        "tracking_error": tracking_error,
        "max_dd": max_dd, "max_dd_recovery_days": recovery_days,
        "current_dd": current_dd,
        "down_capture": down_capture, "up_capture": up_capture,
        "underperf_months": underperf_months,
        # Valuation of the underlying portfolio — no free source publishes
        # scheme-level P/E / P/B, and NAV must not proxy for it: DATA GAP.
        "portfolio_pe": None, "portfolio_pb": None,
        "relative_pe": None, "valuation": None,
    }


# ── Weighted 0-100 composite score ──
# Framework weights; components whose inputs are unavailable become DATA GAPs
# and the score is renormalized over the remaining weight — never estimated.
def score_fund(m: Dict, category: str, is_index: bool = False) -> Dict:
    components = []

    def comp(name, weight, frac, detail):
        components.append({
            "name": name, "weight": weight,
            "score": round(frac * weight, 1) if frac is not None else None,
            "detail": detail,
        })

    ter = m.get("ter")
    aum = m.get("aum_cr")

    if is_index:
        # Index-fund scheme: tracking quality replaces active-management criteria
        comp("Tracking difference", 35, None,
             "DATA GAP — needs TRI benchmark; comparing vs a price-return index would mislabel dividend accrual as tracking gain")
        te = m.get("tracking_error")
        if te is not None:
            comp("Tracking error", 25, _clamp01((3 - te) / 2.5),
                 f"TE {te}% ann. (σ of daily active returns vs {m.get('bm_name') or 'benchmark'} PR)")
        else:
            comp("Tracking error", 25, None, "DATA GAP — benchmark overlap unavailable")
        if ter is not None:
            comp("Expense ratio", 15, _clamp01((0.5 - ter) / 0.4),
                 f"Direct TER {ter}% ({m.get('extras_source') or 'provider'})")
        else:
            comp("Expense ratio", 15, None, "DATA GAP — TER unavailable (check AMC factsheet)")
        if aum is not None:
            comp("AUM", 10, _clamp01(aum / 1000),
                 f"₹{aum:,.0f} Cr ({m.get('extras_source') or 'provider'}) — larger is better for index replication")
        else:
            comp("AUM", 10, None, "DATA GAP — check AMFI monthly data")
        beta = m.get("beta")
        if beta is not None:
            b_s = _clamp01(1 - abs(beta - 1) / 0.15)
            uc, dc = m.get("up_capture"), m.get("down_capture")
            if uc is not None and dc is not None:
                cap_s = _clamp01(1 - (abs(uc - 100) + abs(dc - 100)) / 2 / 25)
                frac = 0.5 * b_s + 0.5 * cap_s
                detail = f"β {beta} · capture up {uc}% / down {dc}% (100% = perfect replication)"
            else:
                frac, detail = b_s, f"β {beta} (1.00 = perfect replication)"
            comp("Replication quality & cash drag", 10, frac, detail)
        else:
            comp("Replication quality & cash drag", 10, None, "DATA GAP — regression vs benchmark unavailable")
        comp("Operational record", 5, None, "DATA GAP — not available from NAV feeds")
        avail_w = sum(c["weight"] for c in components if c["score"] is not None)
        earned = sum(c["score"] for c in components if c["score"] is not None)
        score = round(earned / avail_w * 100, 1) if avail_w >= 30 else None
        return {"components": components, "score": score, "scored_weight": avail_w}

    # 1. Rolling-return consistency (20)
    if m.get("rolling_count", 0) >= 30 and m.get("rolling_consistency") is not None:
        frac = (0.40 * _clamp01((m["rolling_consistency"] or 0) / 100)
                + 0.35 * _clamp01((m.get("roll_ge12") or 0) / 100)
                + 0.25 * _clamp01((m.get("roll_ge15") or 0) / 100))
        comp("Rolling-return consistency", 20, frac,
             f"{m['rolling_consistency']}% positive · {m.get('roll_ge12')}% ≥12% · {m.get('roll_ge15')}% ≥15% ({m['rolling_count']} windows since 2020)")
    else:
        comp("Rolling-return consistency", 20, None, "DATA GAP — fewer than 30 rolling 3Y windows since Jan 2020")

    # 2. Risk-adjusted returns (15)
    if m.get("sharpe") is not None and m.get("sortino") is not None:
        frac = 0.5 * _clamp01(m["sharpe"] / 1.2) + 0.5 * _clamp01(m["sortino"] / 1.6)
        comp("Risk-adjusted returns", 15, frac, f"Sharpe {m['sharpe']} · Sortino {m['sortino']}")
    else:
        comp("Risk-adjusted returns", 15, None, "DATA GAP — insufficient daily return history")

    # 3. Benchmark outperformance (15)
    if m.get("alpha") is not None and m.get("roll_beat_bm") is not None:
        ir = m.get("info_ratio")
        a_s = _clamp01((m["alpha"] + 2) / 8)      # -2% → 0, +6% → 1
        b_s = _clamp01(m["roll_beat_bm"] / 100)
        if ir is not None:
            frac = 0.45 * b_s + 0.35 * a_s + 0.20 * _clamp01((ir + 0.5) / 1.5)
        else:
            frac = 0.55 * b_s + 0.45 * a_s
        comp("Benchmark outperformance", 15, frac,
             f"{m['roll_beat_bm']}% windows beat {m.get('bm_name') or 'benchmark'} (PR) · alpha {m['alpha']}%")
    else:
        comp("Benchmark outperformance", 15, None, "DATA GAP — benchmark series or overlap unavailable")

    # 4. Valuation & entry attractiveness (15) — portfolio P/E vs category
    # average (same provider, same date); NAV level is never used as a proxy
    rel = m.get("relative_pe")
    if rel is not None:
        comp("Valuation & entry attractiveness", 15, _clamp01((1.25 - rel) / 0.45),
             f"Portfolio P/E {m.get('portfolio_pe')} vs category avg {m.get('category_pe')} → Relative P/E {rel} ({m.get('valuation')})")
    else:
        comp("Valuation & entry attractiveness", 15, None,
             "DATA GAP — portfolio P/E unavailable; NAV level is NOT used as a valuation proxy")

    # 5. Drawdown protection & recovery (10)
    if m.get("max_dd") is not None:
        dd_s = _clamp01((m["max_dd"] + 55) / 40)  # -15% → 1.0, -55% → 0
        dc = m.get("down_capture")
        frac = 0.6 * dd_s + 0.4 * _clamp01((130 - dc) / 60) if dc is not None else dd_s
        rec = m.get("max_dd_recovery_days")
        comp("Drawdown protection & recovery", 10, frac,
             f"Max DD {m['max_dd']}% · recovery {str(rec) + ' days' if rec else 'not yet recovered'}"
             + (f" · downside capture {dc}%" if dc is not None else ""))
    else:
        comp("Drawdown protection & recovery", 10, None, "DATA GAP")

    # 6. Portfolio quality & diversification (10) — holdings count + top-10
    hc = m.get("holdings_count")
    t10 = m.get("top10_weight")
    if hc is not None or t10 is not None:
        frac_sum, w_sum, bits = 0.0, 0.0, []
        if hc is not None:
            frac_sum += 0.5 * _clamp01((hc - 15) / 35); w_sum += 0.5
            bits.append(f"{hc} holdings")
        if t10 is not None:
            frac_sum += 0.5 * _clamp01((70 - t10) / 30); w_sum += 0.5
            bits.append(f"top-10 {t10}%")
        if m.get("top3_sector_weight") is not None:
            bits.append(f"top-3 sectors {m['top3_sector_weight']}%")
        comp("Portfolio quality & diversification", 10, frac_sum / w_sum, " · ".join(bits))
    else:
        comp("Portfolio quality & diversification", 10, None, "DATA GAP — holdings/concentration data unavailable")
    if ter is not None:
        comp("Expense ratio", 5, _clamp01((1.5 - ter) / 1.0),
             f"Direct TER {ter}% ({m.get('extras_source') or 'provider'})")
    else:
        comp("Expense ratio", 5, None, "DATA GAP — direct-plan TER unavailable (check AMC factsheet)")
    comp("Manager stability", 5, None,
         f"Managers: {m.get('managers')} — tenure DATA GAP" if m.get("managers")
         else "DATA GAP — manager names/tenure not available (check AMC factsheet)")
    if aum is not None:
        aum_s = 0.2 if aum < 100 else 0.6 if aum < 500 else 1.0 if aum <= 50000 else 0.7 if aum <= 100000 else 0.5
        comp("AUM, flows & operations", 5, aum_s,
             f"₹{aum:,.0f} Cr ({m.get('extras_source') or 'provider'}) — inflow trend DATA GAP; very large AUM can limit flexibility")
    else:
        comp("AUM, flows & operations", 5, None, "DATA GAP — AUM & net-inflow trend not available (check AMFI monthly data)")

    avail_w = sum(c["weight"] for c in components if c["score"] is not None)
    earned = sum(c["score"] for c in components if c["score"] is not None)
    score = round(earned / avail_w * 100, 1) if avail_w >= 40 else None
    return {"components": components, "score": score, "scored_weight": avail_w}


# ── Decision label: exactly one per fund ──
def decide(m: Dict, score) -> tuple:
    """Returns (decision, reason, entry_plan)."""
    years = m.get("years") or 0
    alpha = m.get("alpha")
    beat = m.get("roll_beat_bm")
    pos = m.get("rolling_consistency")
    cdd = m.get("current_dd") or 0
    vol = m.get("volatility")

    underp = m.get("underperf_months")

    if years < 3:
        return ("WAIT",
                f"Track record only {years} years — too short to judge rolling consistency; revisit after 3 full years.",
                "No fresh entry until a 3-year record exists.")
    if score is None:
        return ("WAIT", "Not enough computable data to score reliably.", "No entry until data coverage improves.")
    if underp is not None and underp >= 24 and (alpha or 0) < 0:
        return ("AVOID FRESH ENTRY",
                f"Trailing-1Y return has lagged the benchmark for {underp}+ consecutive months with negative alpha — persistent deterioration.",
                "Do not add fresh money. If held, review against category leaders.")
    if score < 45 or (alpha is not None and alpha <= -2 and beat is not None and beat < 35):
        return ("AVOID FRESH ENTRY",
                f"Score {score}/100 — persistent benchmark underperformance"
                + (f" (alpha {alpha}%, beats benchmark in only {beat}% of windows)" if alpha is not None and beat is not None else "")
                + "; better options exist in the same category.",
                "Do not add fresh money. If held, review against category leaders.")
    if score < 58:
        return ("WAIT",
                f"Score {score}/100 — middling consistency and risk-adjusted profile; no edge over category leaders at current levels.",
                "Keep on watchlist; re-score after next quarter's data.")
    if score < 70:
        return ("SIP ONLY",
                f"Score {score}/100 — decent but not elite consistency; rupee-cost averaging suits this profile better than lump sum.",
                "Monthly SIP only; avoid lump-sum deployment.")
    # score >= 70
    rel = m.get("relative_pe")
    val_note = f" Valuation: {m.get('valuation')} (Relative P/E {rel} vs category avg)." if rel is not None else ""
    if underp is not None and underp >= 15:
        return ("SIP ONLY",
                f"Score {score}/100 but trailing-1Y return has lagged the benchmark for {underp} straight months — average in via SIP rather than committing a lump sum.{val_note}",
                "Monthly SIP only until the fund re-establishes benchmark outperformance.")
    if rel is not None and rel > 1.25:
        return ("ENTER GRADUALLY",
                f"Score {score}/100 but the portfolio trades rich (Relative P/E {rel} vs category avg — {m.get('valuation')}) — do not commit a lump sum at this valuation.",
                "Phase entry over 6+ monthly tranches (or STP); prefer SIP until valuation normalizes.")
    if cdd <= -8 and (pos or 0) >= 85:
        return ("ENTER NOW",
                f"Score {score}/100 with {pos}% positive rolling windows, and NAV is {abs(cdd):.1f}% below its peak — a consistent fund at a dip entry.{val_note}",
                "Deploy lump sum in 1-2 tranches over ~4 weeks; continue via SIP for the remainder.")
    if vol is not None and vol > 22:
        return ("ENTER GRADUALLY",
                f"Score {score}/100 but volatility is high ({vol}%) and NAV is near its peak — phase the entry rather than committing at once.{val_note}",
                "Phase lump sum over 4-6 monthly tranches (or STP from a liquid fund); SIP for ongoing flows.")
    return ("ENTER GRADUALLY",
            f"Score {score}/100 — strong consistency and risk-adjusted profile; NAV near peak, so stagger the entry.{val_note}",
            "Phase lump sum over 3-6 monthly tranches (or STP); SIP for ongoing flows.")


# ── Scorecard checks (chips shown in the UI) ──
def build_checks(m: Dict, category: str) -> tuple:
    checks = []

    def add(name, val, target, red_test, green_test, note="", unit="%"):
        if val is None:
            checks.append({"p": name, "v": "DATA GAP", "t": target, "s": "gray", "n": "Not available — never estimated"})
            return
        vstr = f"{val}{unit}" if isinstance(val, (int, float)) else str(val)
        is_green = green_test(val) if callable(green_test) else False
        is_red = red_test(val) if callable(red_test) else False
        s = "green" if is_green else ("red" if is_red else "yellow")
        checks.append({"p": name, "v": vstr, "t": target, "s": s, "n": note})

    bm = m.get("bm_3y_cagr") or 0
    bm_name = m.get("bm_name") or "Benchmark"
    checks.append({"p": "Plan Type", "v": "Direct-Growth", "t": "Direct-Growth only", "s": "green", "n": "Regular & IDCW plans excluded at search"})
    checks.append({"p": f"BM 3Y CAGR ({bm_name})", "v": f"{bm}%" if bm else "DATA GAP", "t": "Price-return index, not TRI", "s": "gray" if not bm else "green", "n": "TRI unavailable — PR index flatters fund alpha ~1-1.5%/yr"})
    add("3Y CAGR", m.get("cagr_3y"), f"> BM ({bm:.1f}%)", lambda v: v < bm - 2, lambda v: v >= bm)
    add("5Y CAGR", m.get("cagr_5y"), "> 10%", lambda v: v < 8, lambda v: v >= 10)
    add("SIP XIRR 3Y", m.get("xirr_3y"), "> 10%", lambda v: v < 6, lambda v: v >= 10, "calculated, ₹10k/month simulated")
    add("Rolling 3Y Avg", m.get("rolling_avg"), "> 12%", lambda v: v < 8, lambda v: v >= 12, "windows since Jan 2020")
    add("% Windows Positive", m.get("rolling_consistency"), "> 95%", lambda v: v < 80, lambda v: v >= 95, f"{m.get('rolling_neg', 0)} negative windows")
    add("% Windows ≥ 12%", m.get("roll_ge12"), "> 60%", lambda v: v < 35, lambda v: v >= 60)
    add("% Windows ≥ 15%", m.get("roll_ge15"), "> 40%", lambda v: v < 20, lambda v: v >= 40)
    add("% Windows Beat BM", m.get("roll_beat_bm"), "> 55%", lambda v: v < 40, lambda v: v >= 55, f"vs {bm_name} (PR)")
    add("Sharpe Ratio", m.get("sharpe"), "> 0.75", lambda v: v < 0.5, lambda v: v >= 0.75, unit="")
    add("Sortino Ratio", m.get("sortino"), "> 1.0", lambda v: v < 0.7, lambda v: v >= 1.0, unit="")
    add("Alpha (Jensen)", m.get("alpha"), "≥ 0%", lambda v: v < -1.5, lambda v: v >= 0, f"β-adjusted vs {bm_name} PR")
    add("Information Ratio", m.get("info_ratio"), "> 0.3", lambda v: v < -0.2, lambda v: v >= 0.3, unit="")
    add("Beta", m.get("beta"), "0.8-1.05", lambda v: v > 1.15, lambda v: 0.8 <= v <= 1.05, unit="")
    add("Max Drawdown", m.get("max_dd"), "> -30%", lambda v: v < -45, lambda v: v > -30, "full NAV history")
    add("Downside Capture", m.get("down_capture"), "< 95%", lambda v: v > 110, lambda v: v < 95, "monthly, 3Y window")
    add("Volatility (ann.)", m.get("volatility"), "< 18%", lambda v: v > 25, lambda v: v <= 18)
    add("Fund Age", m.get("years"), "> 5 yrs", lambda v: v < 3, lambda v: v >= 5, f"Since {m.get('inception', '?')}", unit=" yrs")
    add("Underperf. Streak", m.get("underperf_months"), "< 6 months",
        lambda v: v >= 15, lambda v: v < 6, "consecutive months trailing-1Y < benchmark", unit="m")
    add("Direct TER", m.get("ter"), "< 1.0%",
        lambda v: v > 1.5, lambda v: v < 1.0, m.get("extras_source") or "")
    aum_v = round(m["aum_cr"]) if m.get("aum_cr") is not None else None
    add("AUM", aum_v, "₹500-50,000 Cr sweet spot",
        lambda v: v < 100, lambda v: 500 <= v <= 50000, "very large AUM can limit flexibility", unit=" Cr")
    add("Relative P/E (vs category)", m.get("relative_pe"), "< 1.10",
        lambda v: v > 1.25, lambda v: v <= 1.10,
        f"P/E {m.get('portfolio_pe')} vs cat {m.get('category_pe')} — {m.get('valuation') or ''}", unit="")
    add("Portfolio P/B (vs category)", m.get("portfolio_pb"), f"≤ cat ({m.get('category_pb') or '?'})",
        lambda v: m.get("category_pb") is not None and v > m["category_pb"] * 1.25,
        lambda v: m.get("category_pb") is not None and v <= m["category_pb"], unit="")
    add("Holdings Count", m.get("holdings_count"), "> 30",
        lambda v: v < 20, lambda v: v >= 30, "diversification", unit="")
    add("Top-10 Concentration", m.get("top10_weight"), "< 50%",
        lambda v: v > 65, lambda v: v < 50)
    if m.get("cat_rank_3y") is not None:
        checks.append({"p": "Category Rank (3Y)", "v": f"#{m['cat_rank_3y']}",
                       "t": f"Cat avg 3Y: {m.get('cat_avg_3y')}%", "s": "info", "n": m.get("extras_source") or ""})
    if m.get("managers"):
        n_mgrs = len([x for x in re.split(r"[;,]", str(m["managers"])) if x.strip()])
        checks.append({"p": "Fund Managers", "v": f"{n_mgrs} named", "t": "Tenure: DATA GAP",
                       "s": "yellow", "n": str(m["managers"])[:120]})
    else:
        checks.append({"p": "Fund Managers", "v": "DATA GAP", "t": "Check AMC factsheet", "s": "gray", "n": "Names/tenure unavailable"})
    # Remaining gaps no free source supplies — never estimated
    for gap in ("Net-Inflow Trend", "Manager Tenure"):
        checks.append({"p": gap, "v": "DATA GAP", "t": "Check AMFI / AMC factsheet", "s": "gray", "n": "Not published by free feeds — never estimated"})

    reds = sum(1 for c in checks if c["s"] == "red")
    greens = sum(1 for c in checks if c["s"] == "green")
    yellows = sum(1 for c in checks if c["s"] == "yellow")
    return checks, greens, reds, yellows


# ── Analyze selected funds ──
def analyze_funds(scheme_codes: List[int], category: str, progress_cb=None) -> Dict:
    if not scheme_codes:
        return {"error": "No funds selected", "results": []}

    total_steps = len(scheme_codes) + 1
    bm_cache: Dict[str, list] = {}

    def get_benchmark(symbol):
        if symbol not in bm_cache:
            bm_cache[symbol] = fetch_benchmark(symbol)
        return bm_cache[symbol]

    if progress_cb:
        progress_cb(0, total_steps, "Fetching fund data (FinAPI) & benchmarks…")
    finapi_map = fetch_finapi_batch(scheme_codes)
    get_benchmark("^NSEI")  # warm the universal fallback

    holdings_map: Dict[int, list] = {}
    results = []
    for i, code in enumerate(scheme_codes):
        if progress_cb:
            progress_cb(i + 1, total_steps, f"Analyzing fund {i + 1}/{len(scheme_codes)}…")
        try:
            raw = fetch_navs(code)  # mfapi.in primary, FinAPI fallback (internal)
            batch = finapi_map.get(code, {})
            if not raw:
                results.append({"scheme_code": code,
                                "scheme_name": batch.get("schemeName", f"Fund {code}"),
                                "fund_house": batch.get("fundHouse", ""),
                                "error": "NAV data unavailable from mfapi.in and FinAPI — re-run analysis"})
                continue
            navs = parse_navs(raw.get("data", []))
            if len(navs) < 50:
                results.append({"scheme_code": code,
                                "scheme_name": raw.get("meta", {}).get("scheme_name", f"Fund {code}"),
                                "fund_house": raw.get("meta", {}).get("fund_house", ""),
                                "error": "Insufficient NAV history (need 50+ points)"})
                continue
            meta = raw.get("meta", {})
            scheme_name = meta.get("scheme_name") or batch.get("schemeName") or f"Fund {code}"
            # Category: mfapi meta first; FinAPI compare batch fills it when the
            # NAV came from the FinAPI fallback (which omits category).
            scheme_category = meta.get("scheme_category") or batch.get("schemeCategoryLabel") or batch.get("schemeCategory") or ""
            fund_house = meta.get("fund_house") or batch.get("fundHouse") or ""

            # Per-fund benchmark from AMFI category + scheme name
            bm_sym, bm_label = pick_benchmark(f"{scheme_category} {scheme_name}")
            bm = get_benchmark(bm_sym)
            # Reject a benchmark that is too thin or has gone stale (dead feed):
            # comparing against it would silently corrupt alpha/beta/capture.
            if len(bm) < 500 or (navs[-1]["date"] - bm[-1]["date"]).days > 45:
                bm_sym, bm_label = "^NSEI", "Nifty 50 (fallback)"
                bm = get_benchmark(bm_sym)

            m = calc_metrics(navs, bm, bm_label)
            if "error" in m:
                results.append({
                    "scheme_code": code,
                    "scheme_name": scheme_name,
                    "fund_house": fund_house,
                    "error": m["error"],
                })
                continue
            # Provider-reported extras — FinAPI primary (joined by scheme
            # code), Kuvera fallback (conservative name match). Merged into
            # the metric set but clearly sourced.
            if code in finapi_map:
                extras = _finapi_extras(finapi_map[code])
                holdings_map[code] = extras.pop("_holdings", [])
                m.update(extras)
            else:
                m.update(fetch_fund_extras(scheme_name))
            is_index = bool(re.search(r"\bindex\b|\betf\b", f"{scheme_category} {scheme_name}", re.I))
            scored = score_fund(m, category, is_index=is_index)
            decision, reason, entry_plan = decide(m, scored["score"])
            checks, greens, reds, yellows = build_checks(m, category)
            nu = scheme_name.upper()
            results.append({
                "scheme_code": code,
                "scheme_name": scheme_name,
                "fund_house": fund_house,
                "scheme_category": scheme_category,
                "is_index": is_index,
                "plan_ok": "DIRECT" in nu and "IDCW" not in nu and "DIVIDEND" not in nu,
                "metrics": m,
                "score": scored["score"],
                "scored_weight": scored["scored_weight"],
                "components": scored["components"],
                "decision": decision,
                "reason": reason,
                "entry_plan": entry_plan,
                "checks": checks,
                "greens": greens,
                "reds": reds,
                "yellows": yellows,
            })
        except Exception as e:
            logger.error(f"Error analyzing fund {code}: {e}")

    # Pairwise portfolio overlap within the basket: Σ min(weight_A, weight_B)
    # over common holdings. Reported as the max overlap vs any other fund —
    # overlap vs the user's EXISTING portfolio is a DATA GAP.
    ok_for_overlap = [r for r in results if not r.get("error") and holdings_map.get(r["scheme_code"])]
    for r in ok_for_overlap:
        h1 = holdings_map[r["scheme_code"]]
        best_o, best_n = None, None
        for o in ok_for_overlap:
            if o is r:
                continue
            w2 = dict(holdings_map[o["scheme_code"]])
            ov = round(sum(min(w, w2[n]) for n, w in h1 if n in w2), 1)
            if best_o is None or ov > best_o:
                best_o, best_n = ov, o["scheme_name"]
        if best_o is not None:
            r["metrics"]["overlap_max"] = best_o
            r["metrics"]["overlap_with"] = best_n

    # Category-correct: flag funds whose AMFI category differs from the
    # basket's modal category (enforces single-category comparison discipline)
    cats = [r["scheme_category"] for r in results if not r.get("error") and r.get("scheme_category")]
    modal_cat = max(set(cats), key=cats.count) if cats else None
    for r in results:
        if not r.get("error"):
            r["category_ok"] = (r["scheme_category"] == modal_cat) if modal_cat else None

    # Rank: score desc, then rolling consistency, then 3Y CAGR; errors last
    def sort_key(x):
        if x.get("error"):
            return (1, 0, 0, 0)
        m = x.get("metrics", {})
        return (0, -(x.get("score") or 0), -(m.get("rolling_consistency") or 0), -(m.get("cagr_3y") or 0))
    results.sort(key=sort_key)

    ok = [r for r in results if not r.get("error")]
    decision_counts = {}
    for r in ok:
        decision_counts[r["decision"]] = decision_counts.get(r["decision"], 0) + 1

    # ── Best-in-class picks ──
    def best(key_fn, pool=None):
        pool = [r for r in (pool if pool is not None else ok) if key_fn(r) is not None]
        return max(pool, key=key_fn) if pool else None

    def brief(r):
        return {"scheme_code": r["scheme_code"], "scheme_name": r["scheme_name"], "score": r.get("score")} if r else None

    scored_pool = [r for r in ok if r.get("score") is not None]
    best_overall = scored_pool[0] if scored_pool else None
    best_consistency = best(lambda r: (r["metrics"].get("rolling_consistency") or 0) + (r["metrics"].get("roll_ge12") or 0) / 1000, scored_pool)
    best_downside = best(lambda r: r["metrics"].get("max_dd"), scored_pool)  # least-negative wins
    best_risk_adj = best(lambda r: r["metrics"].get("sortino"), scored_pool)
    avoid_list = [brief(r) for r in ok if r["decision"] == "AVOID FRESH ENTRY"]

    # Primary + one alternative (prefer a different AMC), only from entry-worthy
    # funds — and prefer funds matching the basket's category (single-category
    # discipline: an out-of-category outlier must not win the recommendation)
    entryworthy = [r for r in scored_pool if r["decision"] in ("ENTER NOW", "ENTER GRADUALLY", "SIP ONLY")]
    in_category = [r for r in entryworthy if r.get("category_ok") is not False]
    entryworthy = in_category or entryworthy
    primary = entryworthy[0] if entryworthy else None
    alternative = None
    if primary:
        for r in entryworthy[1:]:
            if r["fund_house"] != primary["fund_house"]:
                alternative = r
                break
        if alternative is None and len(entryworthy) > 1:
            alternative = entryworthy[1]

    def rec(r):
        if not r:
            return None
        return {**brief(r), "decision": r["decision"], "reason": r["reason"], "entry_plan": r["entry_plan"]}

    as_of = ok[0]["metrics"]["nav_date"] if ok else None
    if progress_cb:
        progress_cb(total_steps, total_steps, "Done!")

    return {
        "category": category,
        "modal_category": modal_cat,
        "total_analyzed": len(results),
        "as_of": as_of,
        "benchmark_note": "Per-fund benchmark from AMFI scheme category (Yahoo Finance price-return indices — TRI unavailable, so alpha/outperformance run ~1-1.5%/yr generous)",
        "decision_counts": decision_counts,
        "best_in_class": {
            "best_overall": brief(best_overall),
            "best_consistency": brief(best_consistency),
            "best_downside_protection": brief(best_downside),
            "best_risk_adjusted": brief(best_risk_adj),
            "avoid_fresh_entry": avoid_list,
        },
        "recommendation": {"primary": rec(primary), "alternative": rec(alternative)},
        "data_gaps": [
            "Manager tenure & net-inflow trend — only current names / AUM snapshot available",
            "Relative P/E uses the category average as denominator (same provider & date); benchmark-index P/E is not published",
            "Overlap is pairwise within this basket — overlap vs your existing portfolio is not computed",
            "Return statistics computed vs price-return index proxies (flatters alpha ~1-1.5%/yr); official TRI benchmark shown per factsheet",
        ],
        "disclaimer": "Educational research computed from public NAV data (mfapi.in), Yahoo Finance benchmark series and FinAPI/Kuvera-reported fund attributes (TER, AUM, portfolio P/E, holdings) — not advice from a SEBI-registered investment adviser. Scores are renormalized over data-available factors only; DATA GAP items are never estimated.",
        "results": results,
    }
