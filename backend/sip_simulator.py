"""
SIP Investment Simulator — Backend Engine.
Uses Zerodha Kite MCP as primary data source, with Yahoo Finance + mfapi.in fallback.
"""
import logging, requests
from datetime import datetime, timedelta
from typing import List, Dict
import yfinance as yf


# ── XIRR calculation ─────────────────────────────────────────

def _xirr(cashflows: List[tuple], guess: float = 0.1, max_iter: int = 200, tol: float = 1e-6) -> float:
    """Calculate XIRR (Extended Internal Rate of Return) for irregular cashflows.

    Args:
        cashflows: list of (datetime, amount) tuples.
                   Negative = investment, positive = redemption/final value.
        guess: initial rate guess (0.1 = 10%)
    Returns:
        Annualised rate as a decimal (0.25 = 25%). Returns 0 on failure.
    """
    if not cashflows or len(cashflows) < 2:
        return 0.0
    t0 = cashflows[0][0]

    def npv_at(candidate: float) -> float:
        total = 0.0
        for dt, amt in cashflows:
            years = (dt - t0).days / 365.25
            total += amt / ((1 + candidate) ** years)
        return total

    # Newton-Raphson is fast near ordinary returns, but can jump below -100%
    # for recent positions with a sharp loss. Keep it in the valid domain and
    # fall back to a bracketed solve below instead of reporting no XIRR.
    rate = guess
    for _ in range(max_iter):
        npv = 0.0
        dnpv = 0.0
        for dt, amt in cashflows:
            years = (dt - t0).days / 365.25
            denom = (1 + rate) ** years
            if denom == 0:
                return 0.0
            npv += amt / denom
            if years != 0:
                dnpv -= years * amt / ((1 + rate) ** (years + 1))
        if abs(dnpv) < 1e-12:
            break
        new_rate = rate - npv / dnpv
        if new_rate <= -1 or new_rate > 1_000_000:
            break
        if abs(new_rate - rate) < tol:
            return round(new_rate * 100, 2)
        rate = new_rate

    # Robust fallback. XIRR is only defined for r > -1; scan that domain for
    # a sign change, then bisect. This resolves real cases such as a 61% loss
    # over six months, where Newton commonly overshoots the lower bound.
    candidates = [
        -0.999999, -0.9999, -0.999, -0.99, -0.95, -0.9, -0.75, -0.5,
        -0.25, 0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0,
        1_000.0, 1_000_000.0,
    ]
    previous_rate = candidates[0]
    try:
        previous_npv = npv_at(previous_rate)
    except (OverflowError, ZeroDivisionError, ValueError):
        previous_npv = None
    for candidate in candidates[1:]:
        try:
            candidate_npv = npv_at(candidate)
        except (OverflowError, ZeroDivisionError, ValueError):
            previous_rate, previous_npv = candidate, None
            continue
        if abs(candidate_npv) < tol:
            return round(candidate * 100, 2)
        if previous_npv is not None and previous_npv * candidate_npv < 0:
            low, high = previous_rate, candidate
            low_npv = previous_npv
            for _ in range(max_iter):
                mid = (low + high) / 2
                mid_npv = npv_at(mid)
                if abs(mid_npv) < tol or high - low < tol:
                    return round(mid * 100, 2)
                if low_npv * mid_npv <= 0:
                    high = mid
                else:
                    low, low_npv = mid, mid_npv
            return round(((low + high) / 2) * 100, 2)
        previous_rate, previous_npv = candidate, candidate_npv
    return 0.0

logger = logging.getLogger("sip_simulator")

# Lazy import kite client to avoid circular imports
def _get_kite():
    try:
        from kite_client import kite
        return kite
    except:
        return None


# ── Popular instruments for instant matching ──────────────────
POPULAR_INDIAN = [
    {"symbol": "^NSEI", "name": "Nifty 50 Index", "type": "Index", "exchange": "NSE"},
    {"symbol": "^NSEBANK", "name": "Bank Nifty Index", "type": "Index", "exchange": "NSE"},
    {"symbol": "NIFTYBEES.NS", "name": "Nippon Nifty 50 BeES ETF", "type": "ETF", "exchange": "NSE"},
    {"symbol": "BANKBEES.NS", "name": "Nippon Bank BeES ETF", "type": "ETF", "exchange": "NSE"},
    {"symbol": "GOLDBEES.NS", "name": "Nippon Gold BeES ETF", "type": "ETF", "exchange": "NSE"},
    {"symbol": "SILVERBEES.NS", "name": "Nippon Silver BeES ETF", "type": "ETF", "exchange": "NSE"},
    {"symbol": "JUNIORBEES.NS", "name": "Nippon Nifty Next 50 BeES ETF", "type": "ETF", "exchange": "NSE"},
    {"symbol": "MON100.NS", "name": "Motilal NASDAQ 100 ETF", "type": "ETF", "exchange": "NSE"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "type": "Stock", "exchange": "NSE"},
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "type": "Stock", "exchange": "NSE"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "type": "Stock", "exchange": "NSE"},
    {"symbol": "INFY.NS", "name": "Infosys", "type": "Stock", "exchange": "NSE"},
    {"symbol": "ITC.NS", "name": "ITC Limited", "type": "Stock", "exchange": "NSE"},
    {"symbol": "LT.NS", "name": "Larsen & Toubro", "type": "Stock", "exchange": "NSE"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank", "type": "Stock", "exchange": "NSE"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "type": "Stock", "exchange": "NSE"},
    {"symbol": "SBIN.NS", "name": "State Bank of India", "type": "Stock", "exchange": "NSE"},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel", "type": "Stock", "exchange": "NSE"},
    {"symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank", "type": "Stock", "exchange": "NSE"},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever", "type": "Stock", "exchange": "NSE"},
    {"symbol": "HCLTECH.NS", "name": "HCL Technologies", "type": "Stock", "exchange": "NSE"},
    {"symbol": "NTPC.NS", "name": "NTPC", "type": "Stock", "exchange": "NSE"},
    {"symbol": "ASIANPAINT.NS", "name": "Asian Paints", "type": "Stock", "exchange": "NSE"},
    {"symbol": "MARUTI.NS", "name": "Maruti Suzuki", "type": "Stock", "exchange": "NSE"},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance", "type": "Stock", "exchange": "NSE"},
    {"symbol": "SUNPHARMA.NS", "name": "Sun Pharma", "type": "Stock", "exchange": "NSE"},
    {"symbol": "TITAN.NS", "name": "Titan Company", "type": "Stock", "exchange": "NSE"},
    {"symbol": "ULTRACEMCO.NS", "name": "UltraTech Cement", "type": "Stock", "exchange": "NSE"},
    {"symbol": "POWERGRID.NS", "name": "Power Grid Corporation", "type": "Stock", "exchange": "NSE"},
]


def search_instruments(query: str) -> List[Dict]:
    """Search instruments: Kite MCP → Popular list → Yahoo → mfapi.in."""
    if not query or len(query) < 2:
        return []
    q = query.upper().strip()
    results = []
    seen = set()

    # 1) Zerodha Kite MCP search (primary)
    kite = _get_kite()
    if kite and kite.connected:
        try:
            kite_results = kite.search_instruments(query, exchange="NSE")
            if kite_results and isinstance(kite_results, list):
                for item in kite_results[:15]:
                    sym_raw = item.get("tradingsymbol", "")
                    exchange = item.get("exchange", "NSE")
                    itype = item.get("instrument_type", "EQ")
                    name = item.get("name", sym_raw)
                    token = item.get("instrument_token")
                    yf_sym = f"{sym_raw}.NS" if exchange == "NSE" else f"{sym_raw}.BO"

                    type_label = "ETF" if itype == "ETF" else ("Index" if "INDEX" in itype or "NIFTY" in sym_raw.upper() else "Stock")
                    key = yf_sym
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append({
                        "symbol": yf_sym,
                        "name": name or sym_raw,
                        "type": type_label,
                        "exchange": exchange,
                        "instrument_token": token,
                        "source": "Zerodha",
                    })
                logger.info(f"[SIP] Kite search '{query}' → {len(results)} results")
        except Exception as e:
            logger.warning(f"[SIP] Kite search error: {e}")

    # 2) Match popular instruments
    for item in POPULAR_INDIAN:
        if q in item["symbol"].upper() or q in item["name"].upper():
            if item["symbol"] not in seen:
                results.append({**item, "source": "Popular"})
                seen.add(item["symbol"])

    # 3) Yahoo Finance search (fallback)
    try:
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
        r = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=2)
        if r.status_code == 200:
            for q_item in r.json().get("quotes", []):
                sym = q_item.get("symbol", "")
                if sym in seen:
                    continue
                qtype = q_item.get("quoteType", "")
                name = q_item.get("shortname") or q_item.get("longname") or sym
                type_label = {"ETF": "ETF", "INDEX": "Index", "MUTUALFUND": "MF"}.get(qtype, "Stock")
                results.append({"symbol": sym, "name": name, "type": type_label, "exchange": q_item.get("exchange", ""), "source": "Yahoo"})
                seen.add(sym)
    except Exception as e:
        logger.warning(f"Yahoo search error: {e}")

    # 4) mfapi.in search (Indian mutual funds)
    try:
        r = requests.get("https://api.mfapi.in/mf/search", params={"q": query}, timeout=2)
        if r.status_code == 200:
            for mf in r.json()[:8]:
                code = mf.get("schemeCode")
                key = f"MF:{code}"
                if key in seen:
                    continue
                seen.add(key)
                results.append({"symbol": key, "name": mf.get("schemeName", ""), "type": "Mutual Fund", "exchange": "AMFI", "source": "mfapi"})
    except Exception as e:
        logger.warning(f"mfapi search error: {e}")

    return results[:25]


# ── Historical Data Fetching ──────────────────────────────────

def _fetch_kite_historical(sym: str, start_dt: datetime, instrument_token: int = None) -> list:
    """Fetch monthly historical data from Zerodha Kite MCP."""
    kite = _get_kite()
    if not kite or not kite.connected:
        return []

    # If we don't have instrument_token, search for it
    if not instrument_token:
        trading_sym = sym.replace(".NS", "").replace(".BO", "")
        try:
            instruments = kite.search_instruments(trading_sym, exchange="NSE")
            if instruments and isinstance(instruments, list) and len(instruments) > 0:
                instrument_token = instruments[0].get("instrument_token")
        except:
            pass

    if not instrument_token:
        return []

    try:
        from_date = start_dt.strftime("%Y-%m-%d")
        to_date = datetime.now().strftime("%Y-%m-%d")
        data = kite.get_historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval="month"
        )
        if data and isinstance(data, list):
            monthly = []
            for candle in data:
                if isinstance(candle, dict):
                    dt_str = candle.get("date", "")[:10]
                    close = candle.get("close", 0)
                elif isinstance(candle, list) and len(candle) >= 5:
                    dt_str = str(candle[0])[:10]
                    close = candle[4]
                else:
                    continue
                if close > 0:
                    monthly.append({"date": dt_str, "price": round(float(close), 2)})
            logger.info(f"[SIP] Kite historical {sym} → {len(monthly)} months")
            return monthly
    except Exception as e:
        logger.warning(f"[SIP] Kite historical error for {sym}: {e}")
    return []


def _fetch_yf_monthly(sym: str, start_dt: datetime) -> list:
    """Fetch monthly history from Yahoo Finance using unadjusted prices.
    TradingView uses unadjusted prices by default, so we match that.
    Includes retry logic for rate limiting.
    """
    import time
    for attempt in range(3):
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(start=start_dt, end=datetime.now(), interval="1mo", auto_adjust=False)
            if hist.empty and not sym.endswith(".NS") and not sym.endswith(".BO"):
                hist = yf.Ticker(f"{sym}.NS").history(start=start_dt, end=datetime.now(), interval="1mo", auto_adjust=False)
            if not hist.empty:
                monthly = []
                for date, row in hist.iterrows():
                    dt = date.to_pydatetime().replace(tzinfo=None)
                    close = float(row["Close"]) if row["Close"] > 0 else 0
                    if close > 0:
                        monthly.append({"date": dt.strftime("%Y-%m-%d"), "price": round(close, 2)})
                return monthly
            return []
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str or "too many" in err_str:
                wait = 2 ** (attempt + 1)  # 2, 4, 8 seconds
                logger.warning(f"[SIP] YF rate limited for {sym}, retry in {wait}s (attempt {attempt+1}/3)")
                time.sleep(wait)
            else:
                logger.warning(f"[SIP] yfinance error for {sym}: {e}")
                break
    return []


def _fetch_mf_monthly(code: str, start_dt: datetime) -> list:
    """Fetch mutual fund NAV from mfapi.in and resample to monthly."""
    try:
        r = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        if data.get("status") != "SUCCESS":
            return []
        parsed = []
        for item in data.get("data", []):
            try:
                dt = datetime.strptime(item["date"], "%d-%m-%Y")
                if dt >= start_dt:
                    parsed.append({"date": dt, "nav": float(item["nav"])})
            except:
                pass
        if not parsed:
            return []
        parsed.sort(key=lambda x: x["date"])
        monthly, seen_months = [], set()
        for p in parsed:
            key = (p["date"].year, p["date"].month)
            if key not in seen_months:
                seen_months.add(key)
                monthly.append({"date": p["date"].strftime("%Y-%m-%d"), "price": round(p["nav"], 4)})
        return monthly
    except Exception as e:
        logger.error(f"[SIP] MF NAV error for {code}: {e}")
        return []


# ── SIP Simulation ────────────────────────────────────────────

def simulate_sip(symbols: List[Dict], start_date: str, sip_day: int = 1, step_up_pct: float = 0, custom_entries: list = None) -> Dict:
    """Run SIP simulation. Uses Kite → yfinance → mfapi.in for data."""
    if not symbols:
        return {"error": "No symbols provided"}

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    kite = _get_kite()
    kite_connected = kite and kite.connected
    data_source = "Zerodha Kite" if kite_connected else "Yahoo Finance"

    # Parse custom entries into lookup maps
    ce_overrides = {}   # month_key -> amount (replaces regular SIP)
    ce_skips = set()    # month_keys to skip
    ce_extras = []      # [{date, amount}] extra investments
    if custom_entries:
        for ce in custom_entries:
            ce_date = ce.get("date", "")
            ce_month = ce_date[:7]  # "2022-03"
            ce_type = ce.get("type", "extra")
            ce_amt = ce.get("amount", 0)
            if ce_type == "override":
                ce_overrides[ce_month] = ce_amt
            elif ce_type == "skip":
                ce_skips.add(ce_month)
            elif ce_type == "extra":
                ce_extras.append({"date": ce_date, "amount": ce_amt})

    # Fetch monthly history for each symbol
    price_data = {}
    symbol_info = {}
    for s in symbols:
        sym = s["symbol"]
        token = s.get("instrument_token")
        prices = []

        if sym.startswith("MF:"):
            # Mutual fund — mfapi.in only
            prices = _fetch_mf_monthly(sym.replace("MF:", ""), start_dt)
            symbol_info[sym] = {"type": "Mutual Fund", "source": "mfapi.in"}
        else:
            # Try Kite first, then Yahoo
            if kite_connected:
                prices = _fetch_kite_historical(sym, start_dt, token)
                if prices:
                    symbol_info[sym] = {"type": "Stock/ETF", "source": "Zerodha Kite"}

            if not prices:
                prices = _fetch_yf_monthly(sym, start_dt)
                symbol_info[sym] = {"type": "Stock/ETF", "source": "Yahoo Finance"}

        if prices:
            price_data[sym] = prices
            logger.info(f"[SIP] {sym} → {len(prices)} months via {symbol_info.get(sym, {}).get('source', '?')}")

    if not price_data:
        return {"error": "Could not fetch price data for any symbol"}

    # Normalize every date to YYYY-MM-{sip_day} so each calendar month
    # produces exactly ONE SIP installment on the user's chosen day
    sip_day_str = str(max(1, min(28, sip_day))).zfill(2)  # clamp 1-28
    for sym in price_data:
        normalised = {}
        for entry in price_data[sym]:
            month_key = entry["date"][:7] + f"-{sip_day_str}"  # e.g. "2025-01-05"
            normalised[month_key] = entry["price"]     # last-write wins (same month)
        price_data[sym] = [{"date": d, "price": p} for d, p in sorted(normalised.items())]

    # Build unified timeline (now guaranteed one entry per calendar month)
    # Filter to only include months >= user's chosen start date
    start_month = start_date[:7] + f"-{sip_day_str}"   # normalize start date to sip day
    all_dates = sorted({d["date"] for sym in price_data for d in price_data[sym] if d["date"] >= start_month})

    # Add extra entry dates to the timeline (find closest available price)
    for extra in ce_extras:
        extra_month = extra["date"][:7] + f"-{sip_day_str}"
        if extra_month not in all_dates:
            all_dates.append(extra_month)
    all_dates = sorted(set(all_dates))

    price_map = {s["symbol"]: {d["date"]: d["price"] for d in price_data.get(s["symbol"], [])} for s in symbols}

    # Simulate SIP
    units = {s["symbol"]: 0.0 for s in symbols}
    invested_per_sym = {s["symbol"]: 0.0 for s in symbols}
    label_map = {s["symbol"]: s.get("label", s["symbol"]) for s in symbols}

    timeline = []
    total_invested = 0.0
    sip_count = 0
    cashflows_all = []         # for portfolio-level XIRR
    cashflows_per = {s["symbol"]: [] for s in symbols}  # per-symbol XIRR
    monthly_detail = {s["symbol"]: [] for s in symbols}  # per-symbol monthly breakdown

    for date_str in all_dates:
        month_invested = 0.0
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        month_key = date_str[:7]  # "2022-03"

        # Check if this month is skipped
        if month_key in ce_skips:
            # Still record timeline point but with 0 investment
            port_val = sum(units[s["symbol"]] * price_map.get(s["symbol"], {}).get(date_str, _last_price(price_data.get(s["symbol"], []), date_str)) for s in symbols)
            pnl = port_val - total_invested
            pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0
            timeline.append({"date": date_str, "invested": round(total_invested, 2), "value": round(port_val, 2), "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2)})
            continue

        # Calculate step-up: increase SIP amount after each full year from start
        # e.g. start=Oct-2021 → step-up at Oct-2022, Oct-2023, etc.
        months_from_start = (dt.year - start_dt.year) * 12 + (dt.month - start_dt.month)
        years_elapsed = max(0, months_from_start // 12)
        step_multiplier = (1 + step_up_pct / 100) ** years_elapsed if step_up_pct > 0 else 1.0

        # Check for extra entries this month — add extra investment
        extra_amt_this_month = sum(e["amount"] for e in ce_extras if e["date"][:7] == month_key)

        for s in symbols:
            sym = s["symbol"]
            base_amt = s["amount"]

            # Determine this month's SIP amount
            if month_key in ce_overrides:
                amt = ce_overrides[month_key]  # override replaces regular SIP
            else:
                amt = round(base_amt * step_multiplier, 2)  # normal + step-up

            # Add extra lump-sum (split equally across symbols)
            if extra_amt_this_month > 0:
                amt += round(extra_amt_this_month / len(symbols), 2)

            if sym in price_map and date_str in price_map[sym] and amt > 0:
                price = price_map[sym][date_str]
                if price > 0:
                    units_bought = amt / price
                    units[sym] += units_bought
                    invested_per_sym[sym] += amt
                    month_invested += amt
                    cashflows_per[sym].append((dt, -amt))  # outflow
                    cur_val_at = units[sym] * price
                    monthly_detail[sym].append({
                        "date": date_str,
                        "invested": round(amt, 2),
                        "nav": round(price, 4),
                        "units_bought": round(units_bought, 4),
                        "cumulative_units": round(units[sym], 4),
                        "cumulative_invested": round(invested_per_sym[sym], 2),
                        "current_value": round(cur_val_at, 2),
                        "pnl": round(cur_val_at - invested_per_sym[sym], 2),
                    })

        if month_invested > 0:
            total_invested += month_invested
            sip_count += 1
            cashflows_all.append((dt, -month_invested))  # outflow

        port_val = sum(units[s["symbol"]] * price_map.get(s["symbol"], {}).get(date_str, _last_price(price_data.get(s["symbol"], []), date_str)) for s in symbols)
        pnl = port_val - total_invested
        pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0
        timeline.append({"date": date_str, "invested": round(total_invested, 2), "value": round(port_val, 2), "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2)})

    # Per-symbol results
    today = datetime.now()
    per_symbol = []
    for s in symbols:
        sym = s["symbol"]
        last_p = _last_price(price_data.get(sym, []), all_dates[-1] if all_dates else "")
        cur_val = round(units[sym] * last_p, 2) if last_p > 0 else 0
        inv = round(invested_per_sym.get(sym, 0), 2)
        pnl = round(cur_val - inv, 2)
        pct = round(pnl / inv * 100, 2) if inv > 0 else 0
        # XIRR for this symbol
        sym_cf = cashflows_per.get(sym, [])
        sym_cf_final = sym_cf + [(today, cur_val)]  # final redemption
        xirr_val = _xirr(sym_cf_final) if len(sym_cf) >= 1 else 0

        # Build yearly aggregation for bar chart
        yearly = {}
        details = monthly_detail.get(sym, [])
        for md in details:
            year = md["date"][:4]
            if year not in yearly:
                yearly[year] = {"year": year, "invested": 0, "months": 0}
            yearly[year]["invested"] += md["invested"]
            yearly[year]["months"] += 1
        # Calculate year-end values using the last NAV of each year
        for year in yearly:
            year_entries = [md for md in details if md["date"][:4] == year]
            if year_entries:
                last_entry = year_entries[-1]
                yearly[year]["cumulative_units"] = last_entry["cumulative_units"]
                yearly[year]["cumulative_invested"] = last_entry["cumulative_invested"]
                yearly[year]["nav"] = last_entry["nav"]
                yearly[year]["value"] = round(last_entry["cumulative_units"] * last_entry["nav"], 2)
                yearly[year]["pnl"] = round(yearly[year]["value"] - last_entry["cumulative_invested"], 2)
                pnl_y = yearly[year]["pnl"]
                inv_y = last_entry["cumulative_invested"]
                yearly[year]["return_pct"] = round(pnl_y / inv_y * 100, 2) if inv_y > 0 else 0
        yearly_list = sorted(yearly.values(), key=lambda x: x["year"])

        per_symbol.append({
            "symbol": sym, "label": label_map[sym],
            "type": symbol_info.get(sym, {}).get("type", "Unknown"),
            "source": symbol_info.get(sym, {}).get("source", "Unknown"),
            "amount_per_month": s["amount"], "units": round(units[sym], 4),
            "invested": inv, "current_value": cur_val,
            "pnl": pnl, "return_pct": pct, "cagr": xirr_val, "last_price": last_p,
            "monthly": details, "yearly": yearly_list,
        })
    per_symbol.sort(key=lambda x: x["return_pct"], reverse=True)

    final_value = timeline[-1]["value"] if timeline else 0
    final_invested = timeline[-1]["invested"] if timeline else 0
    abs_ret = round(final_value - final_invested, 2)
    pct_ret = round(abs_ret / final_invested * 100, 2) if final_invested > 0 else 0
    # Portfolio-level XIRR
    cashflows_all.append((today, final_value))  # final redemption
    portfolio_xirr = _xirr(cashflows_all) if len(cashflows_all) >= 2 else 0

    return {
        "start_date": start_date, "sip_day": sip_day, "step_up_pct": step_up_pct,
        "sip_count": sip_count,
        "data_source": data_source,
        "total_invested": round(final_invested, 2), "portfolio_value": round(final_value, 2),
        "absolute_return": abs_ret, "return_pct": pct_ret, "cagr": portfolio_xirr,
        "monthly_total": sum(s["amount"] for s in symbols),
        "num_symbols": len(symbols), "per_symbol": per_symbol, "timeline": timeline,
    }


def _last_price(data: list, before_date: str) -> float:
    last = 0.0
    for d in data:
        if d["date"] <= before_date:
            last = d["price"]
    return last

