"""
Swing Trading Engine — 25-Year Veteran Swing Trader AI
=====================================================
Data Sources (priority order):
  1. Zerodha Kite MCP — Real-time LTP, quotes, historical OHLCV
  2. Yahoo Finance    — Fallback when Kite not connected

Modules:
  1. Stock Scanner:  Screens broad universe for swing setups
  2. Swing Analyzer: Deep swing analysis for individual stock
  3. Paper Trader:   Virtual portfolio with auto buy/sell
"""
import json, os, math, asyncio, time, logging, threading, shutil, bisect, copy
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import ai_models

logger = logging.getLogger("swing_trading")

PREDICTION_DISCLAIMER = (
    "Predictions are model estimates based on technical scoring, not "
    "guaranteed returns. Past performance does not guarantee future "
    "results. Paper trading only — nothing here is investment advice."
)

# ══════════════════════════════════════════════════════════════
#  SIGNAL VALIDATION / PAPER-FILL CONFIG
# ══════════════════════════════════════════════════════════════
# A recommendation is only "fresh" relative to the price that was actually
# available when it was published. These knobs control how a live/fresh price
# is reconciled against the (possibly older) technical setup — see
# validate_recommendation() and determine_fill() below.
SWING_CONFIG = {
    # % above buy_zone_high still shown as NEAR_BUY_ZONE (not yet MISSED).
    "near_zone_tolerance_pct": 2.0,
    # Minimum remaining % upside to a REAL (non-estimated) target for the
    # trade to still be worth taking.
    "min_remaining_upside_pct": 2.0,
    # Minimum reward-to-risk ((target-entry)/(entry-stop)) for a finite target
    # to make a recommendation actionable. v4's ATR-derived target sits at ~1.0
    # by construction; a small tolerance below avoids rejecting on rounding.
    "min_reward_risk_ratio": 1.0,
    # Slippage applied to a simulated paper fill (buys fill slightly worse
    # than the observed print, like a real market order would).
    "paper_slippage_pct": 0.05,
    # Trading days a PENDING_ENTRY watch item is kept alive waiting for price
    # to reach the buy zone before it's dropped as expired.
    "pending_entry_max_days": 5,
}

# Statuses that must NEVER be shown as a fresh/executable buy recommendation
# or drive a paper fill — the setup is stale, already played out, or broken.
NON_ACTIONABLE_STATUSES = frozenset({
    "MISSED_ENTRY", "TARGET_ALREADY_REACHED", "INVALID", "DATA_STALE",
    "TARGET_MISSING",
})


def _finite_positive(value) -> bool:
    """True only for a real, finite, strictly-positive number (rejects None,
    NaN, inf, and non-numerics) — used to enforce the finite-target invariant."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f) and f > 0


def validate_recommendation(
    *, entry, buy_zone_low, buy_zone_high, stop_loss, target, current_price,
    max_entry_price=None,
    near_zone_tolerance_pct=None, min_remaining_upside_pct=None,
    min_reward_risk_ratio=None, require_target=False,
) -> tuple[str, str]:
    """Validate one recommendation's price levels against a fresh current
    price. Pure function — no I/O, no persistence — so it's independently
    testable and reusable by the scanner, the desk, and paper trading.

    Returns (actionable_status, status_reason). actionable_status is one of:
    READY_TO_BUY, WAIT_FOR_ENTRY, NEAR_BUY_ZONE, MISSED_ENTRY,
    TARGET_ALREADY_REACHED, INVALID, TARGET_MISSING.

    ``require_target``: when True (the production recommendation path), a
    recommendation cannot become actionable without a finite, positive target
    — a missing/NaN/≤0 target yields TARGET_MISSING. The caller is responsible
    for finalizing that target from the SAME completed-candle snapshot before
    calling (see _select_validated_picks). Left False for legacy/direct callers
    and unit tests that validate zone logic without a target.
    """
    tol = (SWING_CONFIG["near_zone_tolerance_pct"]
           if near_zone_tolerance_pct is None else near_zone_tolerance_pct)
    min_upside = (SWING_CONFIG["min_remaining_upside_pct"]
                  if min_remaining_upside_pct is None else min_remaining_upside_pct)
    min_rr = (SWING_CONFIG["min_reward_risk_ratio"]
              if min_reward_risk_ratio is None else min_reward_risk_ratio)

    # ── Internal consistency first — a broken setup is INVALID regardless
    #    of where the current price sits. ──
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and v > 0
               for v in (entry, buy_zone_low, buy_zone_high, stop_loss, current_price)):
        return "INVALID", "Entry, zone, stop and current price must be finite positive numbers."
    if max_entry_price is not None and not _finite_positive(max_entry_price):
        return "INVALID", "Maximum entry price must be finite and positive."
    if entry is None or entry <= 0:
        return "INVALID", "Missing or invalid suggested entry price."
    if (buy_zone_low is None or buy_zone_high is None
            or buy_zone_low <= 0 or buy_zone_high <= 0 or buy_zone_low > buy_zone_high):
        return "INVALID", "Buy zone bounds are missing or inverted."
    if not (buy_zone_low * 0.999 <= entry <= buy_zone_high * 1.001):
        return "INVALID", "Suggested entry falls outside its own buy zone."
    if stop_loss is None or stop_loss <= 0 or stop_loss >= entry:
        return "INVALID", "Stop-loss is missing or not below the entry price."
    if max_entry_price is not None and max_entry_price < buy_zone_low:
        return "INVALID", "Max entry price is inconsistent with the buy zone."
    if current_price is None or current_price <= 0:
        return "INVALID", "No current price available to validate the signal."

    # ── Finite-target invariant. A non-None target must be a real positive
    #    number; when require_target is set, the absence of one is a hard,
    #    non-actionable TARGET_MISSING (never silently actionable). ──
    has_target = target is not None
    if has_target and not _finite_positive(target):
        return ("TARGET_MISSING",
                "Target is present but not a finite positive number.")
    if require_target and not has_target:
        return ("TARGET_MISSING",
                "No finite target could be computed for this recommendation.")

    if has_target:
        if target <= entry:
            return "INVALID", "Target is not above the entry price."
        # Target must sit above the highest price we'd actually pay (the tighter
        # of the buy-zone top and max_entry_price) — otherwise a fill could open
        # already at/above target.
        fill_cap = (buy_zone_high if max_entry_price is None
                    else min(buy_zone_high, max_entry_price))
        if target <= fill_cap:
            return ("INVALID",
                    f"Target {target} is not above the max fill price {fill_cap}.")
        risk = entry - stop_loss
        reward = target - entry
        if risk > 0 and (reward / risk) + 1e-9 < min_rr:
            return ("INVALID",
                    f"Reward-to-risk {reward / risk:.2f} is below the "
                    f"{min_rr} minimum.")

    # ── A real (non-estimated) target that's already been reached, or has
    #    too little room left, makes the trade not worth taking — regardless
    #    of where price sits relative to the buy zone. ──
    if has_target:
        if current_price >= target:
            return ("TARGET_ALREADY_REACHED",
                    f"Current price {current_price} is at/above the target {target}; "
                    "the move is already done.")
        upside_pct = (target - current_price) / current_price * 100
        if upside_pct < min_upside:
            return ("TARGET_ALREADY_REACHED",
                    f"Only {upside_pct:.1f}% upside left to target {target} — "
                    f"below the {min_upside}% minimum.")

    # ── Zone position ──
    if current_price <= stop_loss:
        return "INVALID", "Price has breached the stop; the setup is invalidated."
    if max_entry_price is not None and current_price > max_entry_price:
        return "MISSED_ENTRY", "Price exceeds the maximum entry; do not chase."
    if has_target and buy_zone_low <= current_price <= buy_zone_high:
        live_risk = current_price - stop_loss
        live_reward = target - current_price
        if live_risk <= 0 or live_reward / live_risk + 1e-9 < min_rr:
            return "WAIT_FOR_ENTRY", "Reward-to-risk at the current price is below the minimum; wait for a better entry."
    if current_price < buy_zone_low:
        return ("WAIT_FOR_ENTRY",
                f"Current price {current_price} is below the buy zone "
                f"({buy_zone_low}-{buy_zone_high}).")
    if current_price <= buy_zone_high:
        return ("READY_TO_BUY",
                f"Current price {current_price} is inside the buy zone "
                f"({buy_zone_low}-{buy_zone_high}).")

    # Above the buy zone — either a chaseable near-miss or a missed setup.
    if max_entry_price is not None and current_price > max_entry_price:
        return ("MISSED_ENTRY",
                f"Current price {current_price} is above the max entry price "
                f"{max_entry_price}; do not chase.")
    tolerance_high = buy_zone_high * (1 + tol / 100)
    if current_price <= tolerance_high:
        return ("NEAR_BUY_ZONE",
                f"Current price {current_price} is just above the buy zone "
                f"(within {tol}% tolerance).")
    return ("MISSED_ENTRY",
            f"Current price {current_price} moved above the buy zone "
            f"({buy_zone_high}); do not chase.")


def determine_fill(*, buy_zone_low, buy_zone_high, max_entry_price, observed_price,
                    slippage_pct=None) -> dict:
    """Pure fill decision for ONE freshly observed price (the caller is
    responsible for only ever passing a price observed at/after the signal's
    timestamp — this function never looks backward in time).

    Returns {"filled": bool, "fill_price": float|None, "status": str, "reason": str}.
    Never fills above the buy zone (or max_entry_price, whichever is tighter)
    — a gap over the whole zone is MISSED_ENTRY, not a fill at the old
    suggested price.
    """
    slip = SWING_CONFIG["paper_slippage_pct"] if slippage_pct is None else slippage_pct
    if not _finite_positive(observed_price):
        return {"filled": False, "fill_price": None, "status": "DATA_STALE",
                "reason": "No fresh market price observation available."}
    if (not _finite_positive(buy_zone_low) or not _finite_positive(buy_zone_high)
            or buy_zone_low > buy_zone_high
            or (max_entry_price is not None and not _finite_positive(max_entry_price))
            or not isinstance(slip, (int, float)) or not math.isfinite(slip) or slip < 0):
        return {"filled": False, "fill_price": None, "status": "INVALID",
                "reason": "No buy zone available to validate a fill against."}

    cap = buy_zone_high if max_entry_price is None else min(buy_zone_high, max_entry_price)
    if observed_price < buy_zone_low:
        return {"filled": False, "fill_price": None, "status": "WAIT_FOR_ENTRY",
                "reason": f"Observed price {observed_price} is below the buy zone."}
    if observed_price <= cap:
        fill_price = round(observed_price * (1 + slip / 100), 2)
        if fill_price > cap:
            return {"filled": False, "fill_price": None, "status": "MISSED_ENTRY",
                    "reason": "Price including slippage exceeds the maximum entry; do not chase."}
        return {"filled": True, "fill_price": fill_price, "status": "FILLED",
                "reason": f"Filled at observed price {observed_price} "
                          f"(+{slip}% slippage)."}
    return {"filled": False, "fill_price": None, "status": "MISSED_ENTRY",
            "reason": f"Observed price {observed_price} jumped over the buy zone "
                      f"(cap {cap}); do not chase."}


def adjust_levels_for_fill(suggested_entry, stop_loss, target, fill_price):
    """Re-anchor stop/target to the ACTUAL fill price, preserving the original
    risk/reward *distance* (e.g. 2.5xATR) rather than leaving them pinned to
    the pre-fill suggested_entry.

    Without this, a fill that lands even slightly away from suggested_entry
    (which is expected — see determine_fill) silently changes how much rupee
    risk the position actually carries: the stop level itself doesn't move
    with the fill, so the trader ends up risking more (or less) than the
    strategy's own ATR-based sizing intended. Returns (stop, target) —
    unmodified if suggested_entry/fill_price aren't usable, or if the
    recomputed stop would be degenerate (<=0 or >= fill_price).
    """
    if suggested_entry is None or suggested_entry <= 0 or fill_price is None or fill_price <= 0:
        return stop_loss, target
    adj_stop = stop_loss
    if stop_loss is not None and stop_loss > 0:
        risk = suggested_entry - stop_loss
        candidate = round(fill_price - risk, 2)
        if 0 < candidate < fill_price:
            adj_stop = candidate
    adj_target = target
    if target is not None and target > 0:
        reward = target - suggested_entry
        adj_target = round(fill_price + reward, 2)
    return adj_stop, adj_target


def _json_safe(obj):
    """Recursively replace non-finite floats (NaN/Inf) with None.

    Indicator math on thin/degenerate price data can yield NaN/Inf. FastAPI's
    JSON encoder rejects those ("Out of range float values are not JSON
    compliant"), 500-ing any endpoint that returns them — so scrub at the
    boundary where scan output and API responses are built.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj

# ══════════════════════════════════════════════════════════════
#  KITE MCP DATA LAYER
# ══════════════════════════════════════════════════════════════
try:
    from kite_client import kite as _kite_client
except ImportError:
    _kite_client = None
    logger.warning("[Swing] kite_client not available, using Yahoo Finance only")

# Pre-seeded Nifty 50 instrument tokens (stable across sessions)
_NIFTY50_TOKENS = {
    "RELIANCE": 738561, "TCS": 2953217, "HDFCBANK": 341249, "INFY": 408065,
    "ICICIBANK": 1270529, "HINDUNILVR": 356865, "ITC": 424961, "SBIN": 779521,
    "BHARTIARTL": 2714625, "KOTAKBANK": 492033, "LT": 2939649, "HCLTECH": 1850625,
    "AXISBANK": 1510401, "ASIANPAINT": 60417, "MARUTI": 2815745, "SUNPHARMA": 857857,
    "TITAN": 897537, "BAJFINANCE": 81153, "WIPRO": 969473, "ULTRACEMCO": 2952193,
    "NESTLEIND": 4598529, "NTPC": 11536385, "TATAMOTORS": 884737, "POWERGRID": 3834113,
    "ONGC": 633601, "ADANIPORTS": 3861249, "JSWSTEEL": 3001089, "TATASTEEL": 895745,
    "COALINDIA": 5215745, "BAJAJFINSV": 4268801, "TECHM": 3465729, "HINDALCO": 348929,
    "INDUSINDBK": 1346049, "DRREDDY": 225537, "CIPLA": 177665, "EICHERMOT": 232961,
    "DIVISLAB": 2800641, "BRITANNIA": 140033, "BPCL": 134657, "GRASIM": 315393,
    "HEROMOTOCO": 345089, "APOLLOHOSP": 40193, "TRENT": 502785, "SHRIRAMFIN": 1102337,
    "HDFCLIFE": 119553, "SBILIFE": 5765889, "BEL": 98049, "HAL": 2738689,
    "TATACONSUM": 878593, "BAJAJ_AUTO": 4267265,
}

_instrument_tokens: dict[str, int] = dict(_NIFTY50_TOKENS)
_token_cache_loaded = False


def _is_kite_connected() -> bool:
    """Check if Kite MCP is available and connected."""
    if _kite_client is None:
        return False
    try:
        if _kite_client._mcp_available:
            return True
        # Try to reconnect if MCP dropped
        logger.info("[Swing] MCP not available, attempting reconnect...")
        _kite_client._ensure_session()
        return _kite_client._mcp_available
    except Exception:
        return False


def _ensure_kite_auth() -> bool:
    """Ensure Kite MCP is authenticated before scanning."""
    if _kite_client is None:
        return False
    try:
        if _kite_client.connected and _kite_client._mcp_available:
            return True
        # Try check_connection which calls get_profile
        if _kite_client.check_connection():
            logger.info("[Swing] Kite authenticated as %s", _kite_client._user_name)
            return True
        logger.warning("[Swing] Kite MCP auth failed: %s", _kite_client.last_error)
        return False
    except Exception as e:
        logger.warning("[Swing] Kite auth error: %s", e)
        return False

def _resolve_instrument_token(symbol: str) -> int | None:
    """Resolve a YF-style symbol (e.g. RELIANCE.NS) to a Kite instrument_token."""
    global _instrument_tokens
    clean = symbol.replace(".NS", "").replace(".BO", "")

    if clean in _instrument_tokens:
        return _instrument_tokens[clean]

    if not _is_kite_connected():
        return None

    try:
        results = _kite_client.search_instruments(clean, "NSE")
        if results and isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    ts = item.get("tradingsymbol", "")
                    if ts.upper() == clean.upper():
                        token = item.get("instrument_token")
                        if token:
                            _instrument_tokens[clean] = int(token)
                            return int(token)
            # Fallback: take first result
            if isinstance(results[0], dict) and results[0].get("instrument_token"):
                token = int(results[0]["instrument_token"])
                _instrument_tokens[clean] = token
                return token
        # If results is a string (MCP returned text), try parsing
        if isinstance(results, str):
            logger.debug("[Swing] search_instruments returned text: %s", results[:200])
    except Exception as e:
        logger.debug("[Swing] Token resolve error for %s: %s", clean, e)

    return None

def _warm_token_cache(symbols: list[str]):
    """Pre-warm instrument token cache for a batch of symbols."""
    global _token_cache_loaded
    if _token_cache_loaded or not _is_kite_connected():
        return

    logger.info("[Swing] Warming instrument token cache for %d symbols...", len(symbols))
    for sym in symbols:
        _resolve_instrument_token(sym)
    _token_cache_loaded = True
    logger.info("[Swing] Token cache: %d/%d resolved", len(_instrument_tokens), len(symbols))


def _fetch_ohlcv_kite(symbol: str, days: int = 90) -> dict | None:
    """Fetch OHLCV from Kite MCP historical data API."""
    token = _resolve_instrument_token(symbol)
    if token is None:
        print(f"[Swing] Error -- Could not resolve instrument token for {symbol}")
        return None

    to_date = datetime.now().strftime("%Y-%m-%d 23:59:59")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")

    for attempt in range(3):
        try:
            result = _kite_client.get_historical_data(
                instrument_token=token,
                from_date=from_date,
                to_date=to_date,
                interval="day",
            )

            if result is None:
                print(f"[Swing] {symbol} (token: {token}) get_historical_data returned None (attempt {attempt+1}/3)")
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    _kite_client._ensure_session()
                    continue
                return None

            if isinstance(result, str):
                print(f"[Swing] {symbol} get_historical_data returned string: {result[:200]} (attempt {attempt+1}/3)")
                if "login" in result.lower() or "auth" in result.lower():
                    _kite_client.check_connection()
                    time.sleep(2)
                    continue
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    _kite_client._ensure_session()
                    continue
                return None

            candles = None
            if isinstance(result, dict):
                candles = result.get("candles", result.get("data", {}).get("candles"))
            elif isinstance(result, list):
                candles = result

            if not candles:
                print(f"[Swing] {symbol} returned empty candles list/dict: {result} (attempt {attempt+1}/3)")
                return None
            
            if len(candles) < 20:
                print(f"[Swing] {symbol} returned too few candles: {len(candles)} (attempt {attempt+1}/3)")
                return None

            if isinstance(candles[0], dict):
                opens = np.array([c["open"] for c in candles], dtype=float)
                highs = np.array([c["high"] for c in candles], dtype=float)
                lows = np.array([c["low"] for c in candles], dtype=float)
                closes = np.array([c["close"] for c in candles], dtype=float)
                volumes = np.array([c["volume"] for c in candles], dtype=float)
            else:
                opens = np.array([c[1] for c in candles], dtype=float)
                highs = np.array([c[2] for c in candles], dtype=float)
                lows = np.array([c[3] for c in candles], dtype=float)
                closes = np.array([c[4] for c in candles], dtype=float)
                volumes = np.array([c[5] for c in candles], dtype=float)

            # print(f"[Swing] Kite OHLCV for {symbol} loaded successfully: {len(candles)} candles")
            return {"opens": opens, "highs": highs, "lows": lows, "closes": closes, "volumes": volumes}

        except Exception as e:
            print(f"[Swing] Exception fetching historical data for {symbol}: {e} (attempt {attempt+1}/3)")
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                try:
                    _kite_client._ensure_session()
                except Exception:
                    pass
    return None


def _fetch_ohlcv_yahoo(symbol: str, period: str = "3mo") -> dict | None:
    """Fetch OHLCV from Yahoo Finance (fallback) with rate-limit retry."""
    import time
    import yfinance as yf
    for attempt in range(3):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            if df is None or len(df) < 20:
                return None
            return {
                "opens": df["Open"].values.astype(float),
                "highs": df["High"].values.astype(float),
                "lows": df["Low"].values.astype(float),
                "closes": df["Close"].values.astype(float),
                "volumes": df["Volume"].values.astype(float),
            }
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str or "too many" in err_str:
                wait = 2 ** (attempt + 1)
                logger.warning("[Swing] YF rate limited for %s, retry in %ds (attempt %d/3)", symbol, wait, attempt+1)
                time.sleep(wait)
            else:
                logger.debug("[Swing] Yahoo error for %s: %s", symbol, e)
                return None
    return None


# Set True after the first Kite historical-data failure in a scan so we don't
# pay the retry cost on every one of ~500 symbols — we fall back to Yahoo for
# the remainder of the scan (Kite's historical API requires a paid subscription
# that may be absent even when the session/quotes work fine).
_kite_hist_broken = False


def _fetch_ohlcv(symbol: str, days: int = 365) -> dict | None:
    """Fetch OHLCV, preferring Kite MCP and falling back to Yahoo Finance.

    Default lookback ~365 calendar days (~250 trading days) so EMA-50 and MACD
    have enough history to be accurate. If Kite MCP historical data is
    unavailable (broken/unsubscribed), the first failure flips a flag and the
    rest of the scan uses Yahoo Finance so the desk still produces setups.
    """
    global _kite_hist_broken
    if _is_kite_connected() and not _kite_hist_broken:
        data = _fetch_ohlcv_kite(symbol, days)
        if data is not None:
            return data
        _kite_hist_broken = True
        logger.warning(
            "[Swing] Kite MCP historical data unavailable — falling back to "
            "Yahoo Finance for the rest of this scan")

    # Yahoo Finance fallback (no historical-data subscription required).
    period = "1y" if days > 250 else "6mo" if days > 120 else "3mo"
    return _fetch_ohlcv_yahoo(symbol, period)


def _fetch_ltp_kite(symbol: str) -> float | None:
    """Fetch last traded price from Kite MCP."""
    if not _is_kite_connected():
        return None
    try:
        clean = symbol.replace(".NS", "").replace(".BO", "")
        kite_sym = f"NSE:{clean}"
        result = _kite_client.get_ltp([kite_sym])
        if isinstance(result, dict):
            for key, val in result.items():
                if isinstance(val, dict) and "last_price" in val:
                    return float(val["last_price"])
                elif isinstance(val, (int, float)):
                    return float(val)
        return None
    except Exception as e:
        logger.debug("[Swing] Kite LTP error for %s: %s", symbol, e)
        return None


def _fetch_ltp_yahoo(symbol: str) -> float | None:
    """Fetch LTP from Yahoo Finance (fallback)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d")
        if len(hist) > 0:
            return float(hist["Close"].values[-1])
        return None
    except Exception:
        return None


def _fetch_ltp(symbol: str) -> float | None:
    """Fetch LTP from Kite MCP first, fallback to Yahoo."""
    ltp = _fetch_ltp_kite(symbol)
    if ltp is not None:
        return ltp
    return _fetch_ltp_yahoo(symbol)


def _batch_ltp_kite(symbols: list[str]) -> dict[str, float]:
    """Fetch LTP for multiple symbols in one Kite MCP call."""
    result_map = {}
    if not _is_kite_connected():
        return result_map

    try:
        kite_syms = [f"NSE:{s.replace('.NS', '').replace('.BO', '')}" for s in symbols]
        # Kite allows max ~200 symbols per call, batch in groups of 50
        for i in range(0, len(kite_syms), 50):
            batch = kite_syms[i:i+50]
            result = _kite_client.get_ltp(batch)
            if isinstance(result, dict):
                for key, val in result.items():
                    clean = key.replace("NSE:", "").replace("BSE:", "")
                    yf_sym = f"{clean}.NS"
                    if isinstance(val, dict) and "last_price" in val:
                        result_map[yf_sym] = float(val["last_price"])
                    elif isinstance(val, (int, float)):
                        result_map[yf_sym] = float(val)
    except Exception as e:
        logger.debug("[Swing] Batch LTP error: %s", e)

    return result_map


def _batch_ltp(symbols: list[str]) -> dict[str, float]:
    """Live LTP for many symbols: one Kite MCP batch, then one Yahoo batch for
    whatever Kite couldn't supply. Missing symbols are simply absent."""
    result = _batch_ltp_kite(symbols)
    missing = [s for s in symbols if s not in result]
    if missing:
        try:
            import yfinance as yf
            df = yf.download(missing, period="1d", interval="1d",
                             group_by="ticker", progress=False, threads=True)
            for s in missing:
                try:
                    closes = (df["Close"] if len(missing) == 1 else df[s]["Close"]).dropna()
                    if len(closes):
                        result[s] = float(closes.iloc[-1])
                except Exception:
                    continue
        except Exception as e:
            logger.debug("[Swing] Yahoo batch LTP error: %s", e)
    return result


# ══════════════════════════════════════════════════════════════
#  STOCK UNIVERSE -- Nifty Total Market
# ══════════════════════════════════════════════════════════════
SWING_UNIVERSE = [
    # Nifty Total Market (auto-pulled from NSE ind_niftytotalmarket_list.csv)
    "360ONE.NS", "3MINDIA.NS", "ABB.NS", "ACC.NS", "ACMESOLAR.NS", "AIAENG.NS", "APLAPOLLO.NS", "ASKAUTOLTD.NS",
    "AUBANK.NS", "AWL.NS", "AXISCADES.NS", "AADHARHFC.NS", "AARTIDRUGS.NS", "AARTIIND.NS", "AARTIPHARM.NS", "AAVAS.NS",
    "ABBOTINDIA.NS", "ACE.NS", "ACUTAAS.NS", "ADANIENSOL.NS", "ADANIENT.NS", "ADANIGREEN.NS", "ADANIPORTS.NS", "ADANIPOWER.NS",
    "ATGL.NS", "ABCAPITAL.NS", "ABFRL.NS", "ABLBL.NS", "ABREL.NS", "ABSLAMC.NS", "CPPLUS.NS", "AVL.NS",
    "ADVENZYMES.NS", "AEGISLOG.NS", "AEGISVOPAK.NS", "AEQUS.NS", "AETHER.NS", "AFCONS.NS", "AFFLE.NS", "AHLUCONT.NS",
    "AJANTPHARM.NS", "AKUMS.NS", "APLLTD.NS", "ALIVUS.NS", "ALKEM.NS", "ALKYLAMINE.NS", "AGL.NS", "ABDL.NS",
    "ALOKINDS.NS", "ARE&M.NS", "AMBER.NS", "AMBUJACEM.NS", "ANANDRATHI.NS", "ANANTRAJ.NS", "ANGELONE.NS", "ANTHEM.NS",
    "ANURAS.NS", "APARINDS.NS", "APOLLOHOSP.NS", "APOLLO.NS", "APOLLOTYRE.NS", "APTUS.NS", "ACI.NS", "ARVINDFASN.NS",
    "ARVIND.NS", "ASAHIINDIA.NS", "ASHAPURMIN.NS", "ASHOKLEY.NS", "ASHOKA.NS", "ASIANPAINT.NS", "ASTERDM.NS", "ASTRAMICRO.NS",
    "ASTRAL.NS", "ATHERENERG.NS", "ATLANTAELE.NS", "ATUL.NS", "AURIONPRO.NS", "AUROPHARMA.NS", "AIIL.NS", "AVALON.NS",
    "AVANTIFEED.NS", "DMART.NS", "CCAVENUE.NS", "AWFIS.NS", "AXISBANK.NS", "AZAD.NS", "BEML.NS", "BLS.NS",
    "BSE.NS", "BAJAJ-AUTO.NS", "BAJAJELEC.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BAJAJHLDNG.NS", "BAJAJHFL.NS", "BALAMINES.NS",
    "BALKRISIND.NS", "BALRAMCHIN.NS", "BALUFORGE.NS", "BANCOINDIA.NS", "BANDHANBNK.NS", "BANKBARODA.NS", "BANKINDIA.NS", "MAHABANK.NS",
    "BATAINDIA.NS", "BAYERCROP.NS", "BELRISE.NS", "BERGEPAINT.NS", "BDL.NS", "BEL.NS", "BHARATFORG.NS", "BHEL.NS",
    "BPCL.NS", "BHARTIARTL.NS", "BHARTIHEXA.NS", "BIKAJI.NS", "GROWW.NS", "BIOCON.NS", "BIRLACORPN.NS", "BSOFT.NS",
    "BBOX.NS", "BLACKBUCK.NS", "BLUEDART.NS", "BLUEJET.NS", "BLUESTARCO.NS", "BLUESTONE.NS", "BBTC.NS", "BORORENEW.NS",
    "BOSCHLTD.NS", "FIRSTCRY.NS", "BRIGADE.NS", "BRITANNIA.NS", "MAPMYINDIA.NS", "CCL.NS", "CESC.NS", "CGPOWER.NS",
    "CIEINDIA.NS", "CMSINFO.NS", "CORONA.NS", "CRISIL.NS", "CSBBANK.NS", "CAMPUS.NS", "CANFINHOME.NS", "CANBK.NS",
    "CANHLIFE.NS", "CRAMC.NS", "CAPILLARY.NS", "CAPLIPOINT.NS", "CGCL.NS", "CARBORUNIV.NS", "CARTRADE.NS", "CASTROLIND.NS",
    "CEATLTD.NS", "CELLO.NS", "CEMPRO.NS", "CENTRALBK.NS", "CDSL.NS", "CENTURYPLY.NS", "CERA.NS", "CHALET.NS",
    "CHAMBLFERT.NS", "CHENNPETRO.NS", "CHOICEIN.NS", "CHOLAHLDNG.NS", "CHOLAFIN.NS", "CIPLA.NS", "CUB.NS", "CLEAN.NS",
    "COALINDIA.NS", "COCHINSHIP.NS", "COFORGE.NS", "COHANCE.NS", "COLPAL.NS", "CAMS.NS", "CONCORDBIO.NS", "CONCOR.NS",
    "COROMANDEL.NS", "CRAFTSMAN.NS", "CREDITACC.NS", "CRIZAC.NS", "CROMPTON.NS", "CUMMINSIND.NS", "CUPID.NS", "CYIENT.NS",
    "DCBBANK.NS", "DCMSHRIRAM.NS", "DLF.NS", "DOMS.NS", "DABUR.NS", "DALBHARAT.NS", "DATAPATTNS.NS", "DATAMATICS.NS",
    "DEEPAKFERT.NS", "DEEPAKNTR.NS", "DELHIVERY.NS", "DEVYANI.NS", "DIACABS.NS", "DBL.NS", "DIVISLAB.NS", "DIXON.NS",
    "AGARWALEYE.NS", "LALPATHLAB.NS", "DRREDDY.NS", "DYNAMATECH.NS", "EIDPARRY.NS", "EIHOTEL.NS", "EPL.NS", "EDELWEISS.NS",
    "EICHERMOT.NS", "ELECON.NS", "EMIL.NS", "ELECTCAST.NS", "ELGIEQUIP.NS", "ELLEN.NS", "EMAMILTD.NS", "EMBDL.NS",
    "EMCURE.NS", "EMMVEE.NS", "ENDURANCE.NS", "ENGINERSIN.NS", "ENTERO.NS", "EIEL.NS", "EQUITASBNK.NS", "ERIS.NS",
    "ESCORTS.NS", "ETERNAL.NS", "ETHOSLTD.NS", "EUREKAFORB.NS", "EXIDEIND.NS", "NYKAA.NS", "FEDFINA.NS", "FEDERALBNK.NS",
    "FACT.NS", "FIEMIND.NS", "FINCABLES.NS", "FINPIPE.NS", "FSL.NS", "FIVESTAR.NS", "FORCEMOT.NS", "FORTIS.NS",
    "UTLSOLAR.NS", "GAIL.NS", "GVT&D.NS", "GHCL.NS", "GMMPFAUDLR.NS", "GMRAIRPORT.NS", "GMRP&UI.NS", "GABRIEL.NS",
    "GALLANTT.NS", "GRSE.NS", "GRWRHITECH.NS", "GICRE.NS", "GILLETTE.NS", "GLAND.NS", "GLAXO.NS", "GLENMARK.NS",
    "MEDANTA.NS", "GODIGIT.NS", "GPIL.NS", "GODFRYPHLP.NS", "GODREJAGRO.NS", "GODREJCP.NS", "GODREJIND.NS", "GODREJPROP.NS",
    "GOKEX.NS", "GOKULAGRO.NS", "GRANULES.NS", "GRAPHITE.NS", "GRASIM.NS", "GRAVITA.NS", "GESHIP.NS", "GREAVESCOT.NS",
    "GAEL.NS", "FLUOROCHEM.NS", "GMDCLTD.NS", "GNFC.NS", "GPPL.NS", "GSFC.NS", "HEG.NS", "HGINFRA.NS",
    "HBLENGINE.NS", "HCLTECH.NS", "HDBFS.NS", "HDFCAMC.NS", "HDFCBANK.NS", "HDFCLIFE.NS", "HFCL.NS", "HAPPSTMNDS.NS",
    "HAVELLS.NS", "HCG.NS", "HEMIPROP.NS", "HERITGFOOD.NS", "HEROMOTOCO.NS", "HEXT.NS", "HSCL.NS", "HINDALCO.NS",
    "HAL.NS", "HCC.NS", "HINDCOPPER.NS", "HINDPETRO.NS", "HINDUNILVR.NS", "HINDZINC.NS", "POWERINDIA.NS", "HOMEFIRST.NS",
    "HONASA.NS", "HONAUT.NS", "HUDCO.NS", "HYUNDAI.NS", "ICICIBANK.NS", "ICICIGI.NS", "ICICIAMC.NS", "ICICIPRULI.NS",
    "IDBI.NS", "IDFCFIRSTB.NS", "IFBIND.NS", "IFCI.NS", "IIFLCAPS.NS", "IIFL.NS", "INOXINDIA.NS", "IRB.NS",
    "IRCON.NS", "ITCHOTELS.NS", "ITC.NS", "ITI.NS", "INDGN.NS", "INDIACEM.NS", "INDIAGLYCO.NS", "INDIASHLTR.NS",
    "INDIAMART.NS", "INDIANB.NS", "IEX.NS", "INDHOTEL.NS", "IMFA.NS", "IOC.NS", "IOB.NS", "IRCTC.NS",
    "IRFC.NS", "IREDA.NS", "INDIGOPNTS.NS", "ICIL.NS", "IGL.NS", "INDUSTOWER.NS", "INDUSINDBK.NS", "NAUKRI.NS",
    "INFY.NS", "INOXGREEN.NS", "INOXWIND.NS", "INTELLECT.NS", "INDIGO.NS", "IGIL.NS", "IKS.NS", "IONEXCHANG.NS",
    "IPCALAB.NS", "JBCHEPHARM.NS", "JKCEMENT.NS", "JBMA.NS", "JKLAKSHMI.NS", "JKPAPER.NS", "JKTYRE.NS", "JMFINANCIL.NS",
    "JSWCEMENT.NS", "JSWDULUX.NS", "JSWENERGY.NS", "JSWINFRA.NS", "JSWSTEEL.NS", "JAIBALAJI.NS", "JAINREC.NS", "JPPOWER.NS",
    "J&KBANK.NS", "JAMNAAUTO.NS", "JSFB.NS", "JAYNECOIND.NS", "JSLL.NS", "JINDALSAW.NS", "JSL.NS", "JINDALSTEL.NS",
    "JIOFIN.NS", "JUBLFOOD.NS", "JUBLINGREA.NS", "JUBLPHARMA.NS", "JLHL.NS", "JWL.NS", "JUSTDIAL.NS", "JYOTHYLAB.NS",
    "JYOTICNC.NS", "KPRMILL.NS", "KEI.NS", "KNRCON.NS", "KPIGREEN.NS", "KPITTECH.NS", "KRBL.NS", "KRN.NS",
    "KSB.NS", "KAJARIACER.NS", "KPIL.NS", "KALYANKJIL.NS", "KANSAINER.NS", "KTKBANK.NS", "KARURVYSYA.NS", "KSCL.NS",
    "KAYNES.NS", "KEC.NS", "KFINTECH.NS", "KIRLOSBROS.NS", "KIRLOSENG.NS", "KIRLPNU.NS", "KITEX.NS", "KOTAKBANK.NS",
    "KIMS.NS", "LTF.NS", "LTTS.NS", "LGEINDIA.NS", "LICHSGFIN.NS", "LTFOODS.NS", "LTM.NS", "LT.NS",
    "LATENTVIEW.NS", "LAURUSLABS.NS", "LXCHEM.NS", "IXIGO.NS", "THELEELA.NS", "LEMONTREE.NS", "LENSKART.NS", "LICI.NS",
    "LINDEINDIA.NS", "LLOYDSENGG.NS", "LLOYDSENT.NS", "LLOYDSME.NS", "LODHA.NS", "LUMAXTECH.NS", "LUPIN.NS", "MMTC.NS",
    "MOIL.NS", "MRF.NS", "MSTCLTD.NS", "MTARTECH.NS", "MGL.NS", "MAHSCOOTER.NS", "MAHSEAMLES.NS", "M&MFIN.NS",
    "M&M.NS", "MANAPPURAM.NS", "MRPL.NS", "MANKIND.NS", "MANORAMA.NS", "MARICO.NS", "MARKSANS.NS", "MARUTI.NS",
    "MASTEK.NS", "MFSL.NS", "MAXHEALTH.NS", "MAZDOCK.NS", "MEDPLUS.NS", "MEESHO.NS", "METROPOLIS.NS", "MINDACORP.NS",
    "MIDHANI.NS", "MSUMI.NS", "MOTILALOFS.NS", "MPHASIS.NS", "BECTORFOOD.NS", "MCX.NS", "MUTHOOTFIN.NS", "NATCOPHARM.NS",
    "NBCC.NS", "NCC.NS", "NEOGEN.NS", "NESCO.NS", "NHPC.NS", "NLCINDIA.NS", "NMDC.NS", "NSLNISP.NS",
    "NTPCGREEN.NS", "NTPC.NS", "NH.NS", "NATIONALUM.NS", "NFL.NS", "NAVA.NS", "NAVINFLUOR.NS", "NAZARA.NS",
    "NESTLEIND.NS", "NETWEB.NS", "NETWORK18.NS", "NEULANDLAB.NS", "NEWGEN.NS", "NAM-INDIA.NS", "NIVABUPA.NS", "NUVAMA.NS",
    "NUVOCO.NS", "OBEROIRLTY.NS", "ONGC.NS", "OIL.NS", "OLAELEC.NS", "OLECTRA.NS", "PAYTM.NS", "ONESOURCE.NS",
    "OPTIEMUS.NS", "OFSS.NS", "ORIENTCEM.NS", "ORKLAINDIA.NS", "OSWALPUMPS.NS", "PNGJL.NS", "POLICYBZR.NS", "PCJEWELLER.NS",
    "PCBL.NS", "PGEL.NS", "PIIND.NS", "PNBHOUSING.NS", "PNCINFRA.NS", "PTC.NS", "PTCIL.NS", "PVRINOX.NS",
    "PAGEIND.NS", "PARADEEP.NS", "PARAS.NS", "PARKHOSPS.NS", "PATANJALI.NS", "PGIL.NS", "PERSISTENT.NS", "PETRONET.NS",
    "PFIZER.NS", "PHOENIXLTD.NS", "PWL.NS", "PICCADIL.NS", "PIDILITIND.NS", "PINELABS.NS", "PIRAMALFIN.NS", "PPLPHARMA.NS",
    "POLYMED.NS", "POLYCAB.NS", "POONAWALLA.NS", "PFC.NS", "POWERGRID.NS", "POWERMECH.NS", "PRAJIND.NS", "PREMIERENE.NS",
    "PRESTIGE.NS", "PRICOLLTD.NS", "PFOCUS.NS", "PRSMJOHNSN.NS", "PRIVISCL.NS", "PRUDENT.NS", "PNB.NS", "PURVA.NS",
    "QPOWER.NS", "QUESS.NS", "RRKABEL.NS", "RBLBANK.NS", "RECLTD.NS", "RHIM.NS", "RITES.NS", "RADICO.NS",
    "RVNL.NS", "RAILTEL.NS", "RAIN.NS", "RAINBOW.NS", "RALLIS.NS", "RKFORGE.NS", "RCF.NS", "RATEGAIN.NS",
    "RATNAMANI.NS", "RTNINDIA.NS", "RTNPOWER.NS", "RAYMONDLSL.NS", "REDINGTON.NS", "REDTAPE.NS", "REFEX.NS", "RELAXO.NS",
    "RELIANCE.NS", "RPOWER.NS", "RELIGARE.NS", "RBA.NS", "ROUTE.NS", "RUBICON.NS", "SBFC.NS", "SBICARD.NS",
    "SBILIFE.NS", "SJVN.NS", "SKFINDUS.NS", "SKFINDIA.NS", "SKYGOLD.NS", "SMLMAH.NS", "SHRIPISTON.NS", "SRF.NS",
    "SAATVIKGL.NS", "SAFARI.NS", "SAGILITY.NS", "SAILIFE.NS", "SAMHI.NS", "SAMMAANCAP.NS", "MOTHERSON.NS", "SANDUMA.NS",
    "SANOFICONR.NS", "SANSERA.NS", "SAPPHIRE.NS", "SARDAEN.NS", "SAREGAMA.NS", "SCHAEFFLER.NS", "SCHNEIDER.NS", "SENCO.NS",
    "STYL.NS", "SHAILY.NS", "SHAKTIPUMP.NS", "SHARDACROP.NS", "SHAREINDIA.NS", "SFL.NS", "SHILPAMED.NS", "SCI.NS",
    "SHREECEM.NS", "RENUKA.NS", "SHRIRAMFIN.NS", "SHYAMMETL.NS", "ENRIN.NS", "SIEMENS.NS", "SIGNATURE.NS", "SKIPPER.NS",
    "SMARTWORKS.NS", "SOBHA.NS", "SOLARINDS.NS", "SONACOMS.NS", "SONATSOFTW.NS", "SOUTHBANK.NS", "LOTUSDEV.NS", "STARCEMENT.NS",
    "STARHEALTH.NS", "SBIN.NS", "SAIL.NS", "SWSOLAR.NS", "STLTECH.NS", "STAR.NS", "STYRENIX.NS", "SUBROS.NS",
    "SUDARSCHEM.NS", "SUDEEPPHRM.NS", "SUMICHEM.NS", "SPARC.NS", "SUNPHARMA.NS", "SUNTV.NS", "SUNDARMFIN.NS", "SUNTECK.NS",
    "SUPREMEIND.NS", "SPLPETRO.NS", "SUPRIYA.NS", "SURYAROSNI.NS", "SUZLON.NS", "SWANCORP.NS", "SWIGGY.NS", "SYNGENE.NS",
    "SYRMA.NS", "TARC.NS", "TBOTEK.NS", "TDPOWERSYS.NS", "TSFINV.NS", "TVSMOTOR.NS", "TVSSCS.NS", "TMB.NS",
    "TANLA.NS", "TATACAP.NS", "TATACHEM.NS", "TATACOMM.NS", "TCS.NS", "TATACONSUM.NS", "TATAELXSI.NS", "TATAINVEST.NS",
    "TMCV.NS", "TMPV.NS", "TATAPOWER.NS", "TATASTEEL.NS", "TATATECH.NS", "TTML.NS", "TECHM.NS", "TECHNOE.NS",
    "TEGA.NS", "TEJASNET.NS", "TENNIND.NS", "TEXRAIL.NS", "THANGAMAYL.NS", "ANUP.NS", "NIACL.NS", "RAMCOCEM.NS",
    "THERMAX.NS", "THOMASCOOK.NS", "THYROCARE.NS", "TI.NS", "TIMETECHNO.NS", "TIMKEN.NS", "TIPSMUSIC.NS", "TITAGARH.NS",
    "TITAN.NS", "TORNTPHARM.NS", "TORNTPOWER.NS", "TARIL.NS", "TRANSRAILL.NS", "TRAVELFOOD.NS", "TRENT.NS", "TRIDENT.NS",
    "TRIVENI.NS", "TRITURBINE.NS", "TIINDIA.NS", "UCOBANK.NS", "UNOMINDA.NS", "UPL.NS", "UTIAMC.NS", "UJJIVANSFB.NS",
    "ULTRACEMCO.NS", "UNIONBANK.NS", "UBL.NS", "UNITDSPR.NS", "URBANCO.NS", "USHAMART.NS", "VGUARD.NS", "VMART.NS",
    "VIPIND.NS", "V2RETAIL.NS", "WABAG.NS", "VAIBHAVGBL.NS", "DBREALTY.NS", "VTL.NS", "VARROC.NS", "VBL.NS",
    "MANYAVAR.NS", "VEDL.NS", "VIJAYA.NS", "VIKRAMSOLR.NS", "VMM.NS", "VIYASH.NS", "IDEA.NS", "VOLTAMP.NS",
    "VOLTAS.NS", "WAAREEENER.NS", "WAAREERTL.NS", "WAKEFIT.NS", "WEWORK.NS", "WEBELSOLAR.NS", "WELCORP.NS", "WELENT.NS",
    "WELSPUNLIV.NS", "WESTLIFE.NS", "WHIRLPOOL.NS", "WIPRO.NS", "WOCKPHARMA.NS", "YATHARTH.NS", "YESBANK.NS", "ZFCVINDIA.NS",
    "ZAGGLE.NS", "ZEEL.NS", "ZENTEC.NS", "ZENSARTECH.NS", "ZYDUSLIFE.NS", "ZYDUSWELL.NS", "ECLERX.NS",
]


# ── Index subsets of the list above ──
# Hardcoded fallbacks only: get_swing_universe() prefers a weekly-refreshed
# pull from NSE so an index reshuffle is picked up without a release.
# Nifty 50 (auto-pulled from NSE ind_nifty50list.csv on 2026-07-30; 50 names)
NIFTY_50 = [
    "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "AXISBANK.NS", "BAJAJ-AUTO.NS",
    "BAJAJFINSV.NS", "BAJFINANCE.NS", "BEL.NS", "BHARTIARTL.NS", "CIPLA.NS", "COALINDIA.NS",
    "DRREDDY.NS", "EICHERMOT.NS", "ETERNAL.NS", "GRASIM.NS", "HCLTECH.NS", "HDFCBANK.NS", "HDFCLIFE.NS",
    "HINDALCO.NS", "HINDUNILVR.NS", "ICICIBANK.NS", "INDIGO.NS", "INFY.NS", "ITC.NS", "JIOFIN.NS",
    "JSWSTEEL.NS", "KOTAKBANK.NS", "LT.NS", "M&M.NS", "MARUTI.NS", "MAXHEALTH.NS", "NESTLEIND.NS",
    "NTPC.NS", "ONGC.NS", "POWERGRID.NS", "RELIANCE.NS", "SBILIFE.NS", "SBIN.NS", "SHRIRAMFIN.NS",
    "SUNPHARMA.NS", "TATACONSUM.NS", "TATASTEEL.NS", "TCS.NS", "TECHM.NS", "TITAN.NS", "TMPV.NS",
    "TRENT.NS", "ULTRACEMCO.NS", "WIPRO.NS",
]

# Nifty 500 (auto-pulled from NSE ind_nifty500list.csv on 2026-07-30; 500 names)
NIFTY_500 = [
    "360ONE.NS", "3MINDIA.NS", "AADHARHFC.NS", "AARTIIND.NS", "AAVAS.NS", "ABB.NS", "ABBOTINDIA.NS",
    "ABCAPITAL.NS", "ABDL.NS", "ABFRL.NS", "ABLBL.NS", "ABREL.NS", "ABSLAMC.NS", "ACC.NS", "ACE.NS",
    "ACMESOLAR.NS", "ACUTAAS.NS", "ADANIENSOL.NS", "ADANIENT.NS", "ADANIGREEN.NS", "ADANIPORTS.NS",
    "ADANIPOWER.NS", "AEGISLOG.NS", "AEGISVOPAK.NS", "AFCONS.NS", "AFFLE.NS", "AIAENG.NS", "AIIL.NS",
    "AJANTPHARM.NS", "ALKEM.NS", "AMBER.NS", "AMBUJACEM.NS", "ANANDRATHI.NS", "ANANTRAJ.NS",
    "ANGELONE.NS", "ANTHEM.NS", "ANURAS.NS", "APARINDS.NS", "APLAPOLLO.NS", "APOLLOHOSP.NS",
    "APOLLOTYRE.NS", "APTUS.NS", "ARE&M.NS", "ASAHIINDIA.NS", "ASHOKLEY.NS", "ASIANPAINT.NS",
    "ASTERDM.NS", "ASTRAL.NS", "ATGL.NS", "ATHERENERG.NS", "ATUL.NS", "AUBANK.NS", "AUROPHARMA.NS",
    "AWL.NS", "AXISBANK.NS", "BAJAJ-AUTO.NS", "BAJAJFINSV.NS", "BAJAJHFL.NS", "BAJAJHLDNG.NS",
    "BAJFINANCE.NS", "BALKRISIND.NS", "BALRAMCHIN.NS", "BANDHANBNK.NS", "BANKBARODA.NS", "BANKINDIA.NS",
    "BATAINDIA.NS", "BAYERCROP.NS", "BBTC.NS", "BDL.NS", "BEL.NS", "BELRISE.NS", "BEML.NS",
    "BERGEPAINT.NS", "BHARATFORG.NS", "BHARTIARTL.NS", "BHARTIHEXA.NS", "BHEL.NS", "BIKAJI.NS",
    "BIOCON.NS", "BLS.NS", "BLUEDART.NS", "BLUEJET.NS", "BLUESTARCO.NS", "BOSCHLTD.NS", "BPCL.NS",
    "BRIGADE.NS", "BRITANNIA.NS", "BSE.NS", "BSOFT.NS", "CAMS.NS", "CANBK.NS", "CANFINHOME.NS",
    "CANHLIFE.NS", "CAPLIPOINT.NS", "CARBORUNIV.NS", "CARTRADE.NS", "CASTROLIND.NS", "CCL.NS",
    "CDSL.NS", "CEATLTD.NS", "CEMPRO.NS", "CENTRALBK.NS", "CESC.NS", "CGCL.NS", "CGPOWER.NS",
    "CHALET.NS", "CHAMBLFERT.NS", "CHENNPETRO.NS", "CHOICEIN.NS", "CHOLAFIN.NS", "CHOLAHLDNG.NS",
    "CIEINDIA.NS", "CIPLA.NS", "CLEAN.NS", "COALINDIA.NS", "COCHINSHIP.NS", "COFORGE.NS", "COHANCE.NS",
    "COLPAL.NS", "CONCOR.NS", "CONCORDBIO.NS", "COROMANDEL.NS", "CPPLUS.NS", "CRAFTSMAN.NS",
    "CREDITACC.NS", "CRISIL.NS", "CROMPTON.NS", "CUB.NS", "CUMMINSIND.NS", "CYIENT.NS", "DABUR.NS",
    "DALBHARAT.NS", "DATAPATTNS.NS", "DCMSHRIRAM.NS", "DEEPAKFERT.NS", "DEEPAKNTR.NS", "DELHIVERY.NS",
    "DEVYANI.NS", "DIVISLAB.NS", "DIXON.NS", "DLF.NS", "DMART.NS", "DOMS.NS", "DRREDDY.NS", "ECLERX.NS",
    "EICHERMOT.NS", "EIDPARRY.NS", "EIHOTEL.NS", "ELECON.NS", "ELGIEQUIP.NS", "EMAMILTD.NS",
    "EMCURE.NS", "EMMVEE.NS", "ENDURANCE.NS", "ENGINERSIN.NS", "ENRIN.NS", "ERIS.NS", "ESCORTS.NS",
    "ETERNAL.NS", "EXIDEIND.NS", "FACT.NS", "FEDERALBNK.NS", "FINCABLES.NS", "FIRSTCRY.NS",
    "FIVESTAR.NS", "FLUOROCHEM.NS", "FORCEMOT.NS", "FORTIS.NS", "FSL.NS", "GABRIEL.NS", "GAIL.NS",
    "GALLANTT.NS", "GESHIP.NS", "GICRE.NS", "GILLETTE.NS", "GLAND.NS", "GLAXO.NS", "GLENMARK.NS",
    "GMDCLTD.NS", "GMRAIRPORT.NS", "GODFRYPHLP.NS", "GODIGIT.NS", "GODREJCP.NS", "GODREJIND.NS",
    "GODREJPROP.NS", "GPIL.NS", "GRANULES.NS", "GRAPHITE.NS", "GRASIM.NS", "GRAVITA.NS", "GROWW.NS",
    "GRSE.NS", "GVT&D.NS", "HAL.NS", "HAVELLS.NS", "HBLENGINE.NS", "HCLTECH.NS", "HDBFS.NS",
    "HDFCAMC.NS", "HDFCBANK.NS", "HDFCLIFE.NS", "HEG.NS", "HEROMOTOCO.NS", "HEXT.NS", "HFCL.NS",
    "HINDALCO.NS", "HINDCOPPER.NS", "HINDPETRO.NS", "HINDUNILVR.NS", "HINDZINC.NS", "HOMEFIRST.NS",
    "HONASA.NS", "HONAUT.NS", "HSCL.NS", "HUDCO.NS", "HYUNDAI.NS", "ICICIAMC.NS", "ICICIBANK.NS",
    "ICICIGI.NS", "ICICIPRULI.NS", "IDBI.NS", "IDEA.NS", "IDFCFIRSTB.NS", "IEX.NS", "IFCI.NS",
    "IGIL.NS", "IGL.NS", "IIFL.NS", "IKS.NS", "INDGN.NS", "INDHOTEL.NS", "INDIACEM.NS", "INDIAMART.NS",
    "INDIANB.NS", "INDIGO.NS", "INDUSINDBK.NS", "INDUSTOWER.NS", "INFY.NS", "INOXWIND.NS",
    "INTELLECT.NS", "IOB.NS", "IOC.NS", "IPCALAB.NS", "IRB.NS", "IRCON.NS", "IRCTC.NS", "IREDA.NS",
    "IRFC.NS", "ITC.NS", "ITCHOTELS.NS", "ITI.NS", "J&KBANK.NS", "JAINREC.NS", "JBMA.NS",
    "JINDALSAW.NS", "JINDALSTEL.NS", "JIOFIN.NS", "JKCEMENT.NS", "JKTYRE.NS", "JMFINANCIL.NS",
    "JPPOWER.NS", "JSL.NS", "JSWCEMENT.NS", "JSWDULUX.NS", "JSWENERGY.NS", "JSWINFRA.NS", "JSWSTEEL.NS",
    "JUBLFOOD.NS", "JUBLINGREA.NS", "JUBLPHARMA.NS", "JWL.NS", "JYOTICNC.NS", "KAJARIACER.NS",
    "KALYANKJIL.NS", "KARURVYSYA.NS", "KAYNES.NS", "KEC.NS", "KEI.NS", "KFINTECH.NS", "KIMS.NS",
    "KIRLOSENG.NS", "KOTAKBANK.NS", "KPIL.NS", "KPITTECH.NS", "KPRMILL.NS", "LALPATHLAB.NS",
    "LATENTVIEW.NS", "LAURUSLABS.NS", "LEMONTREE.NS", "LENSKART.NS", "LGEINDIA.NS", "LICHSGFIN.NS",
    "LICI.NS", "LINDEINDIA.NS", "LLOYDSME.NS", "LODHA.NS", "LT.NS", "LTF.NS", "LTFOODS.NS", "LTM.NS",
    "LTTS.NS", "LUPIN.NS", "M&M.NS", "M&MFIN.NS", "MAHABANK.NS", "MANAPPURAM.NS", "MANKIND.NS",
    "MAPMYINDIA.NS", "MARICO.NS", "MARUTI.NS", "MAXHEALTH.NS", "MAZDOCK.NS", "MCX.NS", "MEDANTA.NS",
    "MEESHO.NS", "MFSL.NS", "MGL.NS", "MINDACORP.NS", "MMTC.NS", "MOTHERSON.NS", "MOTILALOFS.NS",
    "MPHASIS.NS", "MRF.NS", "MRPL.NS", "MSUMI.NS", "MUTHOOTFIN.NS", "NAM-INDIA.NS", "NATCOPHARM.NS",
    "NATIONALUM.NS", "NAUKRI.NS", "NAVA.NS", "NAVINFLUOR.NS", "NBCC.NS", "NCC.NS", "NESTLEIND.NS",
    "NETWEB.NS", "NEULANDLAB.NS", "NEWGEN.NS", "NH.NS", "NHPC.NS", "NIACL.NS", "NIVABUPA.NS",
    "NLCINDIA.NS", "NMDC.NS", "NSLNISP.NS", "NTPC.NS", "NTPCGREEN.NS", "NUVAMA.NS", "NUVOCO.NS",
    "NYKAA.NS", "OBEROIRLTY.NS", "OFSS.NS", "OIL.NS", "OLAELEC.NS", "OLECTRA.NS", "ONESOURCE.NS",
    "ONGC.NS", "PAGEIND.NS", "PARADEEP.NS", "PATANJALI.NS", "PAYTM.NS", "PCBL.NS", "PERSISTENT.NS",
    "PETRONET.NS", "PFC.NS", "PFIZER.NS", "PFOCUS.NS", "PGEL.NS", "PHOENIXLTD.NS", "PIDILITIND.NS",
    "PIIND.NS", "PINELABS.NS", "PIRAMALFIN.NS", "PNB.NS", "PNBHOUSING.NS", "POLICYBZR.NS", "POLYCAB.NS",
    "POLYMED.NS", "POONAWALLA.NS", "POWERGRID.NS", "POWERINDIA.NS", "PPLPHARMA.NS", "PREMIERENE.NS",
    "PRESTIGE.NS", "PTCIL.NS", "PVRINOX.NS", "PWL.NS", "RADICO.NS", "RAILTEL.NS", "RAINBOW.NS",
    "RAMCOCEM.NS", "RBLBANK.NS", "RECLTD.NS", "REDINGTON.NS", "RELIANCE.NS", "RHIM.NS", "RITES.NS",
    "RKFORGE.NS", "RPOWER.NS", "RRKABEL.NS", "RVNL.NS", "SAGILITY.NS", "SAIL.NS", "SAILIFE.NS",
    "SAMMAANCAP.NS", "SAPPHIRE.NS", "SARDAEN.NS", "SAREGAMA.NS", "SBFC.NS", "SBICARD.NS", "SBILIFE.NS",
    "SBIN.NS", "SCHAEFFLER.NS", "SCHNEIDER.NS", "SCI.NS", "SHREECEM.NS", "SHRIRAMFIN.NS",
    "SHYAMMETL.NS", "SIEMENS.NS", "SIGNATURE.NS", "SJVN.NS", "SOBHA.NS", "SOLARINDS.NS", "SONACOMS.NS",
    "SONATSOFTW.NS", "SPLPETRO.NS", "SRF.NS", "STARHEALTH.NS", "SUMICHEM.NS", "SUNDARMFIN.NS",
    "SUNPHARMA.NS", "SUNTV.NS", "SUPREMEIND.NS", "SUZLON.NS", "SWANCORP.NS", "SWIGGY.NS", "SYNGENE.NS",
    "SYRMA.NS", "TARIL.NS", "TATACAP.NS", "TATACHEM.NS", "TATACOMM.NS", "TATACONSUM.NS", "TATAELXSI.NS",
    "TATAINVEST.NS", "TATAPOWER.NS", "TATASTEEL.NS", "TATATECH.NS", "TBOTEK.NS", "TCS.NS", "TECHM.NS",
    "TECHNOE.NS", "TEGA.NS", "TEJASNET.NS", "TENNIND.NS", "THELEELA.NS", "THERMAX.NS", "TIINDIA.NS",
    "TIMKEN.NS", "TITAGARH.NS", "TITAN.NS", "TMCV.NS", "TMPV.NS", "TORNTPHARM.NS", "TORNTPOWER.NS",
    "TRAVELFOOD.NS", "TRENT.NS", "TRIDENT.NS", "TRITURBINE.NS", "TTML.NS", "TVSMOTOR.NS", "UBL.NS",
    "UCOBANK.NS", "ULTRACEMCO.NS", "UNIONBANK.NS", "UNITDSPR.NS", "UNOMINDA.NS", "UPL.NS", "URBANCO.NS",
    "USHAMART.NS", "UTIAMC.NS", "VBL.NS", "VEDL.NS", "VIJAYA.NS", "VMM.NS", "VOLTAS.NS", "VTL.NS",
    "WAAREEENER.NS", "WELCORP.NS", "WELSPUNLIV.NS", "WHIRLPOOL.NS", "WIPRO.NS", "WOCKPHARMA.NS",
    "YESBANK.NS", "ZEEL.NS", "ZENSARTECH.NS", "ZENTEC.NS", "ZFCVINDIA.NS", "ZYDUSLIFE.NS",
    "ZYDUSWELL.NS",
]


# ── Full NSE universe (all listed EQ-series equities, ~2000) ──
# Downloaded from NSE archives and cached on disk for a week; the hardcoded
# Nifty Total Market list above is the fallback when NSE is unreachable.
_NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
_UNIVERSE_TTL = 7 * 24 * 3600
_UNIVERSE_CACHE = Path(__file__).parent / "nse_universe_cache.json"
# key -> (fetched_at, symbols). One entry per universe so switching back and
# forth in the UI doesn't re-download anything.
_universe_mem: dict[str, tuple[float, list]] = {}


def _fetch_nse_equity_list() -> list | None:
    """All EQ-series symbols from NSE's official listed-equities CSV."""
    import requests, csv, io
    try:
        r = requests.get(_NSE_EQUITY_URL, timeout=20,
                         headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok:
            return None
        rows = csv.DictReader(io.StringIO(r.text))
        syms = set()
        for row in rows:
            series = (row.get("SERIES") or row.get(" SERIES") or "").strip()
            sym = (row.get("SYMBOL") or "").strip()
            if series == "EQ" and sym:
                syms.add(sym + ".NS")
        # sanity: the real list is ~2000 names; anything tiny means a bad fetch
        return sorted(syms) if len(syms) > 1000 else None
    except Exception as e:
        logger.warning("[Swing] NSE equity list fetch failed: %s", e)
        return None


# ── Scan universe selector ──
# Three index universes, narrowest first. Nifty Total Market (751, ~98% of
# market cap) stays the default; Nifty 500 and Nifty 50 trade breadth for scan
# speed and liquidity. Each is refreshed weekly from its official NSE index CSV
# so a reshuffle lands without a release, with the hardcoded list as fallback.
_NSE_INDEX_URLS = {
    "nifty50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "nifty500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "total": "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
}

SWING_UNIVERSES: dict[str, dict] = {
    "nifty50": {
        "label": "Nifty 50",
        "description": "50 large caps — fastest scan, deepest liquidity",
        "fallback": NIFTY_50,
        "min_expected": 45,
    },
    "nifty500": {
        "label": "Nifty 500",
        "description": "~500 large, mid and small caps — balanced breadth",
        "fallback": NIFTY_500,
        "min_expected": 450,
    },
    "total": {
        "label": "Nifty Total Market",
        "description": "751 names, ~98% of market cap — widest index coverage",
        "fallback": SWING_UNIVERSE,
        "min_expected": 600,
    },
    # Not offered in the picker: kept so the pre-selector SCAN_ALL_NSE capability
    # (all ~2000 EQ-series names, mostly microcaps) is still reachable by setting
    # the universe to "all_nse" directly.
    "all_nse": {
        "label": "All NSE EQ",
        "description": "Every listed EQ-series equity (~2000) — includes microcaps",
        "fallback": SWING_UNIVERSE,
        "min_expected": 1000,
        "hidden": True,
    },
}

DEFAULT_SCAN_UNIVERSE = "total"
PICKABLE_UNIVERSES = [k for k, v in SWING_UNIVERSES.items() if not v.get("hidden")]
_scan_universe = DEFAULT_SCAN_UNIVERSE


def get_scan_universe() -> str:
    """Key of the universe the scanner is currently set to."""
    return _scan_universe


def set_scan_universe(key: str | None) -> str:
    """Point the scanner at a universe. Unknown/empty keys fall back to the
    default rather than raising, so a stale saved setting can't wedge scanning.
    Returns the key actually in effect."""
    global _scan_universe
    if key in SWING_UNIVERSES:
        _scan_universe = key
    else:
        if key:
            logger.warning("[Swing] Unknown scan universe %r — using %s",
                           key, DEFAULT_SCAN_UNIVERSE)
        _scan_universe = DEFAULT_SCAN_UNIVERSE
    return _scan_universe


def _load_universe_disk_cache() -> dict:
    """Per-universe disk cache: {key: {"ts": float, "symbols": [...]}}."""
    try:
        if not _UNIVERSE_CACHE.exists():
            return {}
        blob = json.loads(_UNIVERSE_CACHE.read_text())
        if not isinstance(blob, dict):
            return {}
        # Pre-selector format was a bare {"ts", "symbols"} all-NSE payload.
        if "symbols" in blob and "ts" in blob:
            return {"all_nse": {"ts": blob["ts"], "symbols": blob["symbols"]}}
        return {k: v for k, v in blob.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _store_universe_disk_cache(key: str, symbols: list, now: float):
    cache = _load_universe_disk_cache()
    cache[key] = {"ts": now, "symbols": symbols}
    try:
        _UNIVERSE_CACHE.write_text(json.dumps(cache))
    except Exception:
        pass


def _fetch_universe(key: str) -> list | None:
    """Fresh symbol list for a universe from its NSE source, or None."""
    if key == "all_nse":
        return _fetch_nse_equity_list()
    url = _NSE_INDEX_URLS.get(key)
    if not url:
        return None
    import requests, csv, io
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok:
            return None
        syms = {(row.get("Symbol") or row.get("SYMBOL") or "").strip() + ".NS"
                for row in csv.DictReader(io.StringIO(r.text))
                if (row.get("Symbol") or row.get("SYMBOL") or "").strip()}
        syms.discard(".NS")
        # Sanity gate: a truncated/error response must not shrink the universe.
        if len(syms) < SWING_UNIVERSES[key]["min_expected"]:
            logger.warning("[Swing] %s fetch returned only %d names — ignoring",
                           key, len(syms))
            return None
        return sorted(syms)
    except Exception as e:
        logger.warning("[Swing] %s index list fetch failed: %s", key, e)
        return None


def get_swing_universe(key: str | None = None) -> list:
    """Symbols the scanner covers for the selected (or given) universe.

    Order: in-memory cache → fresh disk cache → NSE download → stale disk
    cache → hardcoded fallback list. For all_nse the download is unioned with
    the hardcoded index list so index names survive series reclassifications.
    """
    key = key if key in SWING_UNIVERSES else _scan_universe
    spec = SWING_UNIVERSES[key]
    now = time.time()

    cached = _universe_mem.get(key)
    if cached and now - cached[0] < _UNIVERSE_TTL:
        return cached[1]

    disk = _load_universe_disk_cache()
    entry = disk.get(key) or {}
    symbols = entry.get("symbols") or []
    if (now - entry.get("ts", 0) < _UNIVERSE_TTL
            and len(symbols) >= spec["min_expected"]):
        _universe_mem[key] = (entry["ts"], symbols)
        return symbols

    fetched = _fetch_universe(key)
    if fetched:
        if key == "all_nse":
            fetched = sorted(set(fetched) | set(SWING_UNIVERSE))
        _universe_mem[key] = (now, fetched)
        _store_universe_disk_cache(key, fetched, now)
        logger.info("[Swing] %s universe refreshed from NSE: %d symbols",
                    key, len(fetched))
        return fetched

    if len(symbols) >= spec["min_expected"]:  # stale cache beats no refresh
        _universe_mem[key] = (now, symbols)
        return symbols
    return spec["fallback"]


def get_universe_size(key: str | None = None) -> int:
    """True number of symbols the scanner covers (single source of truth)."""
    return len(get_swing_universe(key))


def list_scan_universes() -> dict:
    """The picker payload: every selectable universe with its live size, plus
    the key currently in effect. Sizes come from cache/fallback — this never
    triggers a download for a universe the user hasn't selected."""
    options = []
    for key in PICKABLE_UNIVERSES:
        spec = SWING_UNIVERSES[key]
        cached = _universe_mem.get(key)
        if cached:
            size = len(cached[1])
        else:
            disk = (_load_universe_disk_cache().get(key) or {}).get("symbols") or []
            size = len(disk) if len(disk) >= spec["min_expected"] else len(spec["fallback"])
        options.append({
            "key": key,
            "label": spec["label"],
            "description": spec["description"],
            "size": size,
        })
    return {
        "selected": _scan_universe,
        "options": options,
        # Today's picks are frozen once saved, so a switch only takes effect on
        # the next scan — say so rather than letting the count look ignored.
        "note": ("Applies to the next scan. Today's saved picks stay as they "
                 "were — use Hard Refresh to re-scan with the new universe."),
    }


# ══════════════════════════════════════════════════════════════
#  TECHNICAL INDICATORS (pure math, no LLM)
# ══════════════════════════════════════════════════════════════
def _rsi(closes, period=14):
    """Relative Strength Index (Wilder-smoothed, matches TradingView/Zerodha)."""
    deltas = np.diff(np.asarray(closes, dtype=float))
    if len(deltas) < period:
        # Not enough data — fall back to simple average
        gain = np.where(deltas > 0, deltas, 0.0)
        loss = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = np.mean(gain) if len(gain) else 0.0
        avg_loss = np.mean(loss) if len(loss) else 0.0
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    gain = np.where(deltas > 0, deltas, 0.0)
    loss = np.where(deltas < 0, -deltas, 0.0)

    # Seed with simple mean of the first `period` gains/losses
    avg_gain = np.mean(gain[:period])
    avg_loss = np.mean(loss[:period])

    # Wilder smoothing across the rest of the series
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def _ema(data, period):
    """Exponential Moving Average, seeded with the SMA of the first `period` values."""
    arr = np.array(data, dtype=float)
    if len(arr) == 0:
        return arr
    multiplier = 2 / (period + 1)
    if len(arr) < period:
        # Not enough data to seed with a full SMA — fall back to simple recursion
        ema = [arr[0]]
        for i in range(1, len(arr)):
            ema.append((arr[i] - ema[-1]) * multiplier + ema[-1])
        return np.array(ema)

    # Seed the first `period-1` points with the running SMA so index alignment
    # with the input is preserved, then start the EMA at index period-1.
    ema = list(np.cumsum(arr[:period]) / np.arange(1, period + 1))
    for i in range(period, len(arr)):
        ema.append((arr[i] - ema[-1]) * multiplier + ema[-1])
    return np.array(ema)

def _macd(closes):
    """MACD line, signal line, histogram."""
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    signal = _ema(macd_line, 9)
    hist = macd_line - signal
    return macd_line, signal, hist

def _atr(highs, lows, closes, period=14):
    """Average True Range."""
    tr = []
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    return np.mean(tr[-period:]) if tr else 0

def _bollinger(closes, period=20):
    """Bollinger Bands."""
    sma = np.mean(closes[-period:])
    std = np.std(closes[-period:])
    return sma + 2*std, sma, sma - 2*std  # upper, middle, lower

def _adx(highs, lows, closes, period=14):
    """Average Directional Index — Wilder-smoothed trend strength.

    Smooths +DM, -DM and TR with Wilder's method, derives +DI/-DI, computes DX
    per bar, then returns the Wilder-smoothed average of DX (true ADX).
    """
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    closes = np.asarray(closes, dtype=float)

    # Need at least period bars to seed DI/TR and another period bars of DX to
    # seed the ADX smoothing.
    if len(closes) < 2 * period + 1:
        return 25.0  # neutral default

    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        tr_list.append(max(highs[i] - lows[i],
                           abs(highs[i] - closes[i-1]),
                           abs(lows[i] - closes[i-1])))

    plus_dm = np.array(plus_dm)
    minus_dm = np.array(minus_dm)
    tr_list = np.array(tr_list)

    # Wilder-smoothed running sums, seeded with the simple sum of the first period
    sm_plus = plus_dm[:period].sum()
    sm_minus = minus_dm[:period].sum()
    sm_tr = tr_list[:period].sum()

    dx_values = []
    for i in range(period, len(tr_list)):
        # Wilder smoothing of the accumulated DM/TR
        sm_plus = sm_plus - (sm_plus / period) + plus_dm[i]
        sm_minus = sm_minus - (sm_minus / period) + minus_dm[i]
        sm_tr = sm_tr - (sm_tr / period) + tr_list[i]

        if sm_tr == 0:
            dx_values.append(0.0)
            continue
        plus_di = 100 * sm_plus / sm_tr
        minus_di = 100 * sm_minus / sm_tr
        di_sum = plus_di + minus_di
        dx = abs(plus_di - minus_di) / di_sum * 100 if di_sum > 0 else 0.0
        dx_values.append(dx)

    if len(dx_values) < period:
        return 25.0

    # ADX = Wilder-smoothed average of DX
    adx = float(np.mean(dx_values[:period]))
    for i in range(period, len(dx_values)):
        adx = (adx * (period - 1) + dx_values[i]) / period
    return round(adx, 2)

def _stochastic_rsi(closes, rsi_period=14, stoch_period=14):
    """Stochastic RSI.

    Single-pass Wilder RSI series (O(n)) instead of recomputing the whole RSI
    from scratch at every bar (O(n^2)). Verified bit-identical to the previous
    implementation across the 10y universe; ~40x faster per call, which also
    cuts a full universe scan by ~30s.
    """
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    if n - 1 < rsi_period:
        return 50.0
    deltas = np.diff(closes)
    gain = np.where(deltas > 0, deltas, 0.0)
    loss = np.where(deltas < 0, -deltas, 0.0)
    m = len(deltas)
    ag = np.empty(m); al = np.empty(m)
    avg_gain = gain[:rsi_period].mean(); avg_loss = loss[:rsi_period].mean()
    ag[rsi_period - 1] = avg_gain; al[rsi_period - 1] = avg_loss
    for i in range(rsi_period, m):  # Wilder smoothing (causal recurrence)
        avg_gain = (avg_gain * (rsi_period - 1) + gain[i]) / rsi_period
        avg_loss = (avg_loss * (rsi_period - 1) + loss[i]) / rsi_period
        ag[i] = avg_gain; al[i] = avg_loss
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(al == 0, np.inf, ag / al)
    rsi_series = np.round(100 - 100 / (1 + rs), 2)  # al==0 -> 100.0
    # mirror original: rsi at prefix ending close-index i, for i in [rsi_period, n)
    rsi_vals = rsi_series[rsi_period - 1:n - 1]
    if len(rsi_vals) < stoch_period:
        return 50.0
    recent = rsi_vals[-stoch_period:]
    min_rsi = float(recent.min()); max_rsi = float(recent.max())
    if max_rsi == min_rsi:
        return 50.0
    return round((float(rsi_vals[-1]) - min_rsi) / (max_rsi - min_rsi) * 100, 2)

def _support_resistance(highs, lows, closes, n=40, window=5):
    """Find key support/resistance from recent swing pivots.

    A pivot low/high must be the min/max over `window` bars on each side (less
    noisy than a 3-bar pivot). Results are filtered against the current price so
    supports are strictly below and resistances strictly above, then de-duplicated
    and the nearest levels returned.
    """
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    closes = np.asarray(closes, dtype=float)

    if len(closes) < 2 * window + 1:
        return [], []

    price = float(closes[-1])
    supports, resistances = [], []

    # Scan the last `n` candles for pivots that clear a `window`-bar buffer on both sides
    start = max(window, len(closes) - n)
    for i in range(start, len(closes) - window):
        lo = lows[i]
        hi = highs[i]
        left_lo = lows[i-window:i]
        right_lo = lows[i+1:i+1+window]
        left_hi = highs[i-window:i]
        right_hi = highs[i+1:i+1+window]

        if lo <= left_lo.min() and lo <= right_lo.min():
            supports.append(round(float(lo), 2))
        if hi >= left_hi.max() and hi >= right_hi.max():
            resistances.append(round(float(hi), 2))

    # Supports strictly below price; resistances strictly above price
    supports = sorted({s for s in supports if s < price})
    resistances = sorted({r for r in resistances if r > price})

    # Nearest levels: highest supports (closest below), lowest resistances (closest above)
    nearest_supports = supports[-3:]
    nearest_resistances = resistances[:3]
    return nearest_supports, nearest_resistances

def _volume_spike(volumes, threshold=1.5):
    """Check if latest volume is a spike vs 20-day avg."""
    if len(volumes) < 21:
        return False, 0
    avg_vol = np.mean(volumes[-21:-1])
    if avg_vol == 0:
        return False, 0
    ratio = volumes[-1] / avg_vol
    return ratio >= threshold, round(ratio, 2)

def _candlestick_pattern(opens, highs, lows, closes):
    """Detect basic candlestick patterns on last 3 bars."""
    if len(closes) < 3:
        return "None"
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    o1, h1, l1, c1 = opens[-2], highs[-2], lows[-2], closes[-2]
    body = abs(c - o)
    total_range = h - l if h - l > 0 else 0.01
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)

    # Hammer (bullish reversal)
    if lower_wick > 2 * body and upper_wick < body * 0.3 and c > o:
        return "Hammer (Bullish)"
    # Bullish Engulfing
    if c1 < o1 and c > o and c > o1 and o < c1:
        return "Bullish Engulfing"
    # Morning Star
    if len(closes) >= 3:
        o2, c2 = opens[-3], closes[-3]
        if c2 < o2 and abs(c1 - o1) < body * 0.3 and c > o and c > (o2 + c2) / 2:
            return "Morning Star (Bullish)"
    # Bearish Engulfing
    if c1 > o1 and c < o and c < o1 and o > c1:
        return "Bearish Engulfing"
    # Doji
    if body < total_range * 0.1:
        return "Doji (Indecision)"
    return "None"

def _fibonacci_levels(high, low):
    """Fibonacci retracement levels."""
    diff = high - low
    return {
        "0%": round(high, 2),
        "23.6%": round(high - 0.236 * diff, 2),
        "38.2%": round(high - 0.382 * diff, 2),
        "50%": round(high - 0.5 * diff, 2),
        "61.8%": round(high - 0.618 * diff, 2),
        "78.6%": round(high - 0.786 * diff, 2),
        "100%": round(low, 2),
    }

def _pivot_points(high, low, close):
    """Standard pivot points."""
    pp = (high + low + close) / 3
    return {
        "R3": round(high + 2 * (pp - low), 2),
        "R2": round(pp + (high - low), 2),
        "R1": round(2 * pp - low, 2),
        "PP": round(pp, 2),
        "S1": round(2 * pp - high, 2),
        "S2": round(pp - (high - low), 2),
        "S3": round(low - 2 * (high - pp), 2),
    }


# ══════════════════════════════════════════════════════════════
#  SWING STOCK SCANNER — Score each stock for swing potential
# ══════════════════════════════════════════════════════════════
def _scan_stock(symbol: str, require_liquid: bool = False) -> dict | None:
    """Score a single stock for swing trading potential. Returns None on failure.

    require_liquid: used by the universe scan — skips penny/illiquid names
    (price < Rs.5 or 20-day avg turnover < Rs.1 crore) where a swing position
    has no realistic exit. Direct per-stock analysis keeps them visible.
    """
    try:
        # ~250 trading days of history so EMA-50 / MACD-26 seed correctly
        data = _fetch_ohlcv(symbol, days=365)
        if data is None:
            return None
        if require_liquid:
            closes = np.asarray(data["closes"], dtype=float)
            volumes = np.asarray(data["volumes"], dtype=float)
            n = min(len(closes), 20)
            turn20 = float(np.mean(closes[-n:] * volumes[-n:])) if n else 0.0
            if closes[-1] < 5 or turn20 < 1e7:
                return None
        # Report the source that actually supplied the candles for this scan.
        data_source = "Kite MCP" if (_is_kite_connected() and not _kite_hist_broken) else "Yahoo Finance"
        return _analyze_arrays(symbol, data["opens"], data["highs"], data["lows"],
                               data["closes"], data["volumes"], data_source)
    except Exception as e:
        logger.debug("[Swing] Scan error for %s: %s", symbol, e)
        return None


def _analyze_arrays(symbol: str, opens, highs, lows, closes, volumes,
                    data_source: str = "Yahoo Finance") -> dict | None:
    """Pure scoring core: score OHLCV arrays for swing potential.

    Split out of _scan_stock so the backtester can run the EXACT production
    logic on historical slices. No I/O here — arrays in, pick dict out.
    """
    try:
        price = float(closes[-1])
        rsi = _rsi(closes)
        macd_line, signal, hist = _macd(closes)
        atr = _atr(highs, lows, closes)
        bb_upper, bb_mid, bb_lower = _bollinger(closes)
        vol_spike, vol_ratio = _volume_spike(volumes)
        pattern = _candlestick_pattern(opens, highs, lows, closes)
        supports, resistances = _support_resistance(highs, lows, closes)
        ema20 = float(_ema(closes, 20)[-1])
        ema50 = float(_ema(closes, 50)[-1]) if len(closes) >= 50 else ema20
        adx = _adx(highs, lows, closes)
        stoch_rsi = _stochastic_rsi(closes)
        pivots = _pivot_points(float(highs[-1]), float(lows[-1]), price)

        # 52-week high/low from available data
        high_52w = float(np.max(highs))
        low_52w = float(np.min(lows))

        # ── Score calculation (0-100) ──
        score = 50  # base

        # RSI: Best swing zone 30-50 (oversold bounce)
        if 30 <= rsi <= 45:
            score += 15  # Sweet spot
        elif 25 <= rsi < 30:
            score += 10  # Very oversold, risky
        elif 45 < rsi <= 55:
            score += 5   # Neutral
        elif rsi > 70:
            score -= 10  # Overbought
        elif rsi < 25:
            score -= 5   # Too oversold, might be broken

        # MACD crossover
        if hist[-1] > 0 and hist[-2] <= 0:
            score += 15  # Fresh bullish crossover!
        elif hist[-1] > hist[-2] and hist[-1] > 0:
            score += 8   # Strengthening bullish
        elif hist[-1] < 0 and hist[-2] >= 0:
            score -= 10  # Bearish crossover

        # Price vs Bollinger
        if price <= bb_lower * 1.01:
            score += 12  # At/below lower band
        elif price >= bb_upper * 0.99:
            score -= 8   # At upper band

        # Volume spike
        if vol_spike:
            score += 10

        # Candlestick pattern
        if "Bullish" in pattern or "Hammer" in pattern or "Morning" in pattern:
            score += 12
        elif "Bearish" in pattern:
            score -= 8

        # Price near support
        if supports:
            nearest_support = min(supports, key=lambda s: abs(price - s))
            if abs(price - nearest_support) / price < 0.02:
                score += 10  # Within 2% of support

        # EMA alignment
        if price > ema20 > ema50:
            score += 8  # Uptrend
        elif price < ema20 < ema50:
            score -= 5  # Downtrend

        # ADX: Strong trend > 25
        if adx > 30:
            score += 5
        elif adx < 15:
            score -= 3  # No trend

        # Stochastic RSI: Oversold zone
        if stoch_rsi < 20:
            score += 5  # Oversold
        elif stoch_rsi > 80:
            score -= 3  # Overbought

        # Counter-trend demotion — backtested (45 scan days × 743 stocks with
        # this exact scoring): counter-trend picks (bearish MACD + price below
        # EMA20) won 36% at +0.04R avg, while trend-aligned picks won 71% at
        # +0.69R. Excluding counter-trend from the daily top-5 lifted total
        # return from +13.3R to +23.5R. Penalise and cap so these setups only
        # surface when nothing aligned is available.
        counter_trend = bool(hist[-1] <= 0 and price < ema20)
        if counter_trend:
            score = min(score - 20, 69)

        score = max(0, min(100, score))

        # ── Setup type ──
        if "Bullish" in pattern or "Hammer" in pattern:
            setup = pattern
        elif hist[-1] > 0 and hist[-2] <= 0:
            setup = "MACD Bullish Crossover"
        elif rsi < 35:
            setup = "RSI Oversold Bounce"
        elif price <= bb_lower * 1.02:
            setup = "Bollinger Band Squeeze"
        elif vol_spike and closes[-1] > closes[-2]:
            setup = "Volume Breakout"
        elif price > ema20 and closes[-1] > closes[-2]:
            setup = "EMA Bounce"
        else:
            setup = "Trend Continuation"

        # ── Entry / SL / Targets ──
        # Derive a real entry trigger from the detected setup rather than just
        # echoing the last close.
        nearest_support = min(supports, key=lambda s: abs(price - s)) if supports else None
        nearest_resistance = min(resistances, key=lambda r: abs(price - r)) if resistances else None

        setup_lower = setup.lower()
        entry = None
        if any(k in setup_lower for k in ("oversold", "bounce", "hammer", "bullish", "morning")):
            # Bounce/reversal setups: enter near support (or price if none below)
            entry = round(float(nearest_support), 2) if nearest_support is not None else round(float(price), 2)
        elif any(k in setup_lower for k in ("breakout", "squeeze", "crossover")):
            # Breakout/squeeze: enter just above nearest resistance
            if nearest_resistance is not None:
                entry = round(float(nearest_resistance) * 1.002, 2)
            else:
                entry = round(float(price), 2)
        else:
            # No meaningful trigger — leave null so the frontend shows "—"
            entry = None

        # ── Swing engine v4 exits (see research/V4_EXIT_STUDY.md) ──
        # No take-profit: winners exit at the 20-session time limit. Stop is
        # 2.5×ATR below entry, evaluated on the DAILY CLOSE only (exit next
        # open if breached) — tight intraday stops and fixed targets tested
        # worse on train/validation/test 2011-2026.
        ref = entry if entry is not None else price
        sl = round(ref - 2.5 * atr, 2)
        target1 = None
        target2 = None
        target3 = None
        rr = None
        # Gap guard: entries that open >4% above the signal close lose in every
        # tested period. The scan can't see tomorrow's open, so publish the
        # ceiling for the user (and paper trader) to enforce at entry time.
        max_entry_price = round(price * 1.04, 2)

        # Display-only "predicted gain" heuristic — NOT a v4 exit target (v4
        # deliberately has none, see above; fixed targets tested worse in
        # every period 2011-2026). This is an unvalidated technical estimate
        # (distance to nearest resistance, or a symmetric ATR-based move when
        # no resistance is available) used only for the Focus Dashboard's
        # "predicted gain" column and for ranking/filtering candidates in
        # scan_swing_picks. It never drives entries, stops, or exits.
        predicted_gain_pct = None
        gain_ref = entry if entry is not None else price
        if gain_ref and gain_ref > 0:
            gain_candidates = []
            if nearest_resistance is not None and nearest_resistance > gain_ref:
                gain_candidates.append((nearest_resistance - gain_ref) / gain_ref * 100)
            if atr and atr > 0:
                gain_candidates.append((2.5 * atr) / gain_ref * 100)
            if gain_candidates:
                predicted_gain_pct = round(max(gain_candidates), 1)

        # Display-only "estimated target price" — derived from the same
        # unvalidated predicted_gain_pct heuristic above, for the "Consider to
        # Buy" panel's Target column. Never used by the v4 exit engine.
        predicted_target_price = (
            round(gain_ref * (1 + predicted_gain_pct / 100), 2)
            if gain_ref and predicted_gain_pct is not None else None)

        # Entry range (±2%, matches the desk's buy-zone width) — a plain-
        # language band around the entry trigger for the "Consider to Buy"
        # panel, computed the same way regardless of whether this pick ever
        # reaches the 14-day desk.
        entry_range_low = round(gain_ref * 0.98, 2) if gain_ref else None
        entry_range_high = round(gain_ref * 1.02, 2) if gain_ref else None

        # Plain-language risk bucket from the stop distance (risk_pct below) —
        # a relabeling of an already-computed number, not a new risk model.
        risk_pct_val = (ref - sl) / ref * 100
        risk_level = ("Low" if risk_pct_val < 3 else
                      "Medium" if risk_pct_val < 6 else "High")

        name = symbol.replace(".NS", "").replace(".BO", "")

        return _json_safe({
            "symbol": symbol,
            "name": name,
            "price": float(price),
            "score": int(score),
            "setup": setup,
            "rsi": float(rsi),
            "macd_hist": round(float(hist[-1]), 2),
            "macd_signal": "Bullish" if float(hist[-1]) > 0 else "Bearish",
            "atr": round(float(atr), 2),
            "volume_ratio": float(vol_ratio),
            "volume_spike": bool(vol_spike),
            "pattern": pattern,
            "bb_position": "Lower" if price <= bb_lower * 1.02 else "Upper" if price >= bb_upper * 0.98 else "Middle",
            "ema20": round(float(ema20), 2),
            "ema50": round(float(ema50), 2),
            "adx": float(adx),
            "stoch_rsi": float(stoch_rsi),
            "pivots": pivots,
            "trend": "Up" if price > ema20 > ema50 else "Down" if price < ema20 < ema50 else "Sideways",
            "counter_trend": counter_trend,
            "supports": [round(float(s), 2) for s in supports],
            "resistances": [round(float(r), 2) for r in resistances],
            "high_52w": round(float(high_52w), 2),
            "low_52w": round(float(low_52w), 2),
            # ATR as a fraction of price, and how close price sits to its 52-week
            # high. Both are the raw inputs the v4.1 ranking turns into
            # cross-sectional percentile ranks — the two features that replicated
            # at 6/6 folds twice (research/FEATURE_IC_REPLICATION.md). Emitted
            # here so ranking never re-derives them from rupee `atr`.
            "atr_pct": (round(float(atr) / float(price) * 100, 3)
                        if atr and price else None),
            "dist_52w_pct": (round(float(price) / float(high_52w) * 100, 2)
                             if high_52w and high_52w > 0 else None),
            "ret_63d_pct": (round(float(closes[-1] / closes[-64] - 1) * 100, 2)
                            if len(closes) >= 64 and closes[-64] > 0 else None),
            "entry": (round(float(entry), 2) if entry is not None else None),
            "stop_loss": float(sl),
            "target1": target1,
            "target2": target2,
            "target3": target3,
            "risk_reward": (f"1:{rr}" if rr is not None else None),
            "risk_pct": round(float((ref - sl) / ref * 100), 1),
            "risk_level": risk_level,
            "reward_pct": None,
            # Confidence = the validated rule-based score, relabeled for the
            # Focus Dashboard. predicted_gain_pct/predicted_target_price are
            # the unvalidated heuristic above — see its own comment.
            "prediction_confidence": int(score),
            "confidence_grade": _desk_grade(score),
            "predicted_gain_pct": predicted_gain_pct,
            "predicted_target_price": predicted_target_price,
            "entry_range_low": entry_range_low,
            "entry_range_high": entry_range_high,
            "engine": "v4",
            "stop_check": "close",          # evaluate stop on daily close only
            "time_exit_sessions": 20,       # exit at close of the 20th session
            "max_entry_price": float(max_entry_price),  # skip if opens above this
            "data_source": data_source,
        })
    except Exception as e:
        logger.debug("[Swing] Analyze error for %s: %s", symbol, e)
        return None


COOLDOWN_LOOKBACK_DAYS = 3
COOLDOWN_TOP_RANK = 3


def _recently_topped_symbols(lookback_days: int = COOLDOWN_LOOKBACK_DAYS,
                              top_rank: int = COOLDOWN_TOP_RANK) -> set[str]:
    """Symbols that held a top-`top_rank` slot on any saved scan date in the
    last `lookback_days` (today excluded — that's the list being built now).

    Prevents an already-extended momentum leader from camping the #1 spot day
    after day: it still qualifies, but fresh setups get first refusal.
    """
    store = _load_picks_store()
    today = datetime.now().strftime("%Y-%m-%d")
    dates = sorted((d for d in store.get("dates", {}) if d != today), reverse=True)
    seen: set[str] = set()
    for d in dates[:lookback_days]:
        entry = store["dates"].get(d) or {}
        for p in (entry.get("picks") or [])[:top_rank]:
            sym = p.get("symbol")
            if sym:
                seen.add(sym)
    return seen


def _pct_ranks(values: list) -> list[float]:
    """Percentile rank in [0,1] of each value among its peers; 0.5 where the
    value is missing, so an unmeasurable candidate is neither rewarded nor
    punished. Ties share the average rank (pandas `rank(pct=True)` semantics),
    which is what the offline study measured."""
    present = sorted(v for v in values if v is not None)
    n = len(present)
    if n == 0:
        return [0.5] * len(values)
    if n == 1:
        return [0.5 if v is None else 1.0 for v in values]
    out = []
    for v in values:
        if v is None:
            out.append(0.5)
            continue
        lo = bisect.bisect_left(present, v)
        hi = bisect.bisect_right(present, v)
        out.append(((lo + hi) / 2 + 0.5) / n)  # average rank of the tie group
    return out


def _apply_v41_ranking(results: list[dict], recent: set, quality_fn, rs_fn) -> list[dict]:
    """v4.1 ordering: penalise cross-sectional ATR%, reward closeness to the
    52-week high — the two features that replicated at 6/6 folds on two
    different universes (research/FEATURE_IC_REPLICATION.md).

    REFUTED as a trading rule, 2026-07-30. Measured on the survivorship-free
    panel against 20 random pickers (research/HARNESS.md), this ranking sits at
    percentile 0 of the random distribution in both 2011-2019 and 2020-2022, at
    holds of 14, 20 and 40 sessions, with negative expectancy and profit factor
    under 1. The features' information coefficient was genuine; ranking on it
    was not profitable. Reachable via the engine toggle for inspection, never
    promoted, and never fed to the desk or paper trading.

    v4 ranks by score then a predicted-gain heuristic, and never looks at
    volatility at all. Measured IC on the day's cross-section: ATR% rank
    -0.047, distance-to-52w-high rank +0.057 — comparable magnitude, opposite
    sign. So the blend is a plain difference of the two percentile ranks with
    EQUAL, UNFITTED weights. Fitting weights here would fit them to a
    TRAIN-only IC with no VAL/TEST held back, which is the exact failure this
    engine exists to correct.

    v4's quality gate is left alone. Its momentum tier is split: the
    relative-strength half stays a tier, while the `price >= 0.85 * high_52w`
    half is what the continuous near-high rank replaces.
    """
    atr_ranks = _pct_ranks([r.get("atr_pct") for r in results])
    hi_ranks = _pct_ranks([r.get("dist_52w_pct") for r in results])

    for r, xr_atr, xr_hi in zip(results, atr_ranks, hi_ranks):
        r["engine"] = "v4.1"
        r["xr_atr_pct"] = round(xr_atr, 4)
        r["xr_near_high"] = round(xr_hi, 4)
        r["v41_rank_score"] = round(xr_hi - xr_atr, 4)   # in [-1, +1]
        r["quality_pick"] = quality_fn(r)
        r["v3_momentum"] = rs_fn(r)
        r["recently_topped"] = r["symbol"] in recent

    results.sort(key=lambda x: (not x["v3_momentum"], not x["quality_pick"],
                                x["recently_topped"], -x["v41_rank_score"],
                                -x["score"]))
    return results


def _v41_shadow_on() -> bool:
    """v4.1 forward-shadow logging: OFF unless SWING_V41_SHADOW is set.

    Read per scan (not cached at import) so the flag can be flipped without a
    restart, matching how an operator would actually run a validation window.
    """
    return os.getenv("SWING_V41_SHADOW", "").strip().lower() in ("1", "true", "yes", "on")


# Fields that make a shadow row evaluable later: enough to recompute realized
# return from the signal price, plus the two features v4.1 ranks on so the
# eventual study can check WHY a pick was chosen, not just that it was.
_SHADOW_PICK_FIELDS = (
    "symbol", "name", "score", "price", "current_price_at_signal",
    "predicted_gain_pct", "atr_pct", "dist_52w_pct", "high_52w", "ret_63d_pct",
    "adx", "trend", "setup", "risk_reward", "actionable_status",
    "signal_timestamp", "suggested_entry", "stop_loss",
    "xr_atr_pct", "xr_near_high", "v41_rank_score",
    "quality_pick", "v3_momentum", "recently_topped",
)


def _shadow_row(p: dict) -> dict:
    return {k: p.get(k) for k in _SHADOW_PICK_FIELDS if p.get(k) is not None}


def _shadow_log_v41(v4_picks: list[dict], candidates: list[dict], top_n: int,
                    quality_fn, rs_fn, recent: set, user_id: str = "default") -> dict | None:
    """Record today's v4 list next to what v4.1 WOULD have picked, for the
    forward comparison V6_TRAINING_PLAN §10 asks for and never got.

    Writes one row per scan to <user_dir>/v41_shadow_signals.json. Never traded,
    never fed to the desk or paper trading, and never allowed to raise into the
    scan — v4's published picks are byte-identical whether this runs or not.

    NOT validation on its own: at ~5 picks/day against ~20% per-trade
    dispersion, a real edge takes years to separate from noise here. This exists
    so the window has already started when the survivorship-free rig can
    finally judge it.
    """
    ranked = _apply_v41_ranking(candidates, recent, quality_fn, rs_fn)
    v41_picks = _select_validated_picks(ranked, top_n)

    v4_syms = [p.get("symbol") for p in (v4_picks or [])]
    v41_syms = [p.get("symbol") for p in v41_picks]
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "candidates_scanned": len(candidates),
        "v4_picks": [_shadow_row(p) for p in (v4_picks or [])],
        "v41_picks": [_shadow_row(p) for p in v41_picks],
        "overlap": sorted(set(v4_syms) & set(v41_syms)),
        "note": ("SHADOW — v4.1 is NOT traded and NOT fed to the desk. Forward "
                 "record only; promotion needs the rand:N bar on the "
                 "survivorship-free panel (research/FEATURE_IC_REPLICATION.md)."),
    }

    path = (Path(_active_user_dir) if _active_user_dir is not None
            else PAPER_DATA_DIR) / "v41_shadow_signals.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                log = loaded
        except Exception:
            log = []
    # One row per calendar day — a same-day re-scan replaces that day's row so a
    # hard refresh can't double-count a day in the forward sample.
    log = [r for r in log if r.get("date") != record["date"]]
    log.append(record)
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(_json_safe(log[-500:]), indent=2, default=str),
                   encoding="utf-8")
    tmp.replace(path)
    logger.info("[Swing] v4.1 shadow logged: v4=%s v41=%s overlap=%d",
                v4_syms, v41_syms, len(record["overlap"]))
    return record


def scan_swing_picks(top_n: int = 5, on_progress=None, engine: str = "v4") -> list[dict]:
    """Scan the entire universe and return top N swing picks.

    `engine` selects the ranking policy only — the per-symbol scan is identical,
    so v4.1 reuses this one pass rather than re-fetching the whole universe:

      "v4"   — frozen incumbent. Ranked by score then the predicted-gain
               heuristic, gated at predicted_gain_pct >= 5%.
      "v4.1" — candidate. Same scan, same quality gate, but ranked on the two
               cross-sectional features that replicated (see
               _apply_v41_ranking) and WITHOUT the expected-gain floor, which
               reduces to an "atr_pct >= 2%" requirement (see below).

    No-lookahead guarantee: this is a live/online scan — _fetch_ohlcv pulls
    each symbol's history up to the moment of the call (Kite/yfinance both
    return data ending "now"), so there is no future bar for the score,
    momentum tier, or predicted_gain_pct heuristic to see. The offline
    research backtests that validated these rules use a separate pipeline
    with its own explicit leakage controls (shifted rolling windows,
    chronological train/validation/test splits) — see
    research/next_day_gainers_AUDIT_REPORT.md §2 and research/V4_EXIT_STUDY.md.
    """
    # Kite auth is optional — if the session or its historical-data API isn't
    # available we scan on Yahoo Finance instead (see _fetch_ohlcv). Probe, but
    # don't block the scan.
    if not _ensure_kite_auth():
        logger.warning("[Swing] Kite not authenticated — scanning with Yahoo Finance data")

    # Re-probe Kite historical data each scan; on the first failure we fall back
    # to Yahoo Finance (see _fetch_ohlcv). Skip the upfront token warm — with a
    # ~2000-name universe that would be ~2000 slow Kite lookups, and resolution
    # is lazy per symbol anyway.
    global _kite_hist_broken
    _kite_hist_broken = False

    universe = get_swing_universe()
    total = len(universe)
    results = []
    for i, sym in enumerate(universe):
        if on_progress:
            on_progress(i, total, sym)
        r = _scan_stock(sym, require_liquid=True)
        if r:
            print(f"[Swing] Scanned {sym} -- Score: {r['score']}, Setup: {r['setup']}")
            if r["score"] >= 55:  # Minimum threshold
                results.append(r)
        else:
            print(f"[Swing] Failed to scan {sym} -- Data fetch error")
    if on_progress:
        on_progress(total, total, "Done")

    # v3 momentum tier (research/V3_MOMENTUM_STUDY.md, 16y walk-forward):
    # candidates within 15% of their 52-week high whose 63-day return beats
    # BOTH Nifty's 63-day return and zero improved expectancy in train,
    # validation AND untouched 2023-26 test (-0.16 vs -0.26 %/trade on test).
    # Nifty benchmark return computed once per scan; if unavailable the
    # momentum tier degrades to absolute-strength only.
    nifty_r63 = None
    try:
        ndata = _fetch_ohlcv_yahoo("^NSEI", period="6mo")
        ncl = ndata["closes"] if ndata else []
        if len(ncl) >= 64 and float(ncl[-64]) > 0:
            nifty_r63 = (float(ncl[-1]) / float(ncl[-64]) - 1) * 100
    except Exception as e:
        logger.warning("[Swing] Nifty 63d benchmark unavailable: %s", e)

    def _quality(r) -> bool:
        # v2 gate (research/WIN_RATE_OPTIMIZATION.md): +8-12pp win rate in
        # every tested period including unseen data.
        return (not r.get("counter_trend")
                and r.get("trend") == "Up"
                and (r.get("adx") or 0) >= 25)

    def _momentum(r) -> bool:
        r63 = r.get("ret_63d_pct")
        hi = r.get("high_52w") or 0
        price = r.get("price") or 0
        if r63 is None or hi <= 0 or price <= 0:
            return False
        near_hi = price >= 0.85 * hi
        rs = r63 > nifty_r63 if nifty_r63 is not None else True
        return near_hi and rs and r63 > 0

    def _rs_only(r) -> bool:
        """_momentum's relative-strength half, without the 0.85*high_52w flag —
        v4.1 replaces that flag with a continuous near-high rank. Defined out
        here (not inside the v4.1 branch) so the shadow logger can reuse it."""
        r63 = r.get("ret_63d_pct")
        if r63 is None:
            return False
        rs = r63 > nifty_r63 if nifty_r63 is not None else True
        return rs and r63 > 0

    recent = _recently_topped_symbols()

    # v4.1 shadow: snapshot the FULL candidate list BEFORE v4's expected-gain
    # floor prunes it, so the shadow ranking sees the same candidates a real
    # v4.1 run would. Copied per row because _apply_v41_ranking and
    # _select_validated_picks both mutate each dict, and must not touch what v4
    # is about to publish. A shallow copy is enough: every key either writes is
    # top-level, so the shared nested values (indicator dicts) are never
    # mutated — and that avoids deep-copying hundreds of candidates per scan.
    v41_shadow_src = None
    if engine == "v4" and _v41_shadow_on():
        v41_shadow_src = [dict(r) for r in results]

    if engine == "v4.1":
        # v4's expected-gain floor is DROPPED here, not replaced. It reads as
        # "only candidates that could gain >=5%", but the value is
        # max(distance-to-resistance, 2.5*ATR/price*100) and for most names the
        # ATR term dominates — so the floor reduces to `atr_pct >= 2%`. That
        # makes v4 *require* high volatility, the one property measured
        # negative in 6 of 6 folds on two separate universes
        # (research/FEATURE_IC_REPLICATION.md). Since predicted_gain_pct's own
        # comment already calls it an unvalidated display heuristic, removing
        # it is a smaller claim than swapping in a different unvalidated
        # filter; score >= 55 and the quality gate still bound the candidates.
        results = _apply_v41_ranking(results, recent, _quality, _rs_only)
    else:
        # "Today's Focus List" gate: only candidates the heuristic estimates could
        # gain >=5% are eligible at all. Unlike the score/momentum/quality gates
        # above, this one is NOT backfilled — on a day where fewer than top_n
        # candidates clear it, the list is shorter rather than padding in a
        # sub-5% setup (see predicted_gain_pct's own comment: it's an unvalidated
        # display heuristic, used here only as a selection floor).
        MIN_PREDICTED_GAIN_PCT = 5.0
        results = [r for r in results
                   if (r.get("predicted_gain_pct") or 0) >= MIN_PREDICTED_GAIN_PCT]

        # Tier order = the exact configuration the study tested: momentum-passing
        # candidates first (quality-first within them), then the rest — so the
        # daily list never comes up empty on weak days *among candidates that
        # already cleared the 5% gate above*. Recently-topped names are demoted
        # within their tier (not excluded) so a repeat can still surface if
        # nothing fresh qualifies. Within a tier, rank by confidence (score) then
        # by the heuristic expected gain.
        results.sort(key=lambda x: (not _momentum(x), not _quality(x),
                                     x["symbol"] in recent, -x["score"],
                                     -(x.get("predicted_gain_pct") or 0)))
        for p in results:
            p["quality_pick"] = _quality(p)
            p["v3_momentum"] = _momentum(p)
            p["recently_topped"] = p["symbol"] in recent

    # Validate against a FRESH live price before publishing. A candidate whose
    # technical setup has already been overtaken by price (gap above the buy
    # zone, or a real target already reached) is rejected outright rather than
    # re-priced upward — see validate_recommendation(). We keep pulling from
    # the ranked candidate list until top_n pass, instead of padding the list
    # with stale setups.
    picks = _select_validated_picks(results, top_n)

    # v5 shadow mode (research/V5_ADVANCED_ENSEMBLE.md) — OFF unless SWING_V5_SHADOW
    # is set. When on, it logs the v5 ensemble's picks alongside these v4 picks for
    # forward comparison; it NEVER alters the v4 picks returned here. Best-effort:
    # any failure is swallowed so shadow logging can't break the production scan.
    try:
        import swing_v5
        if swing_v5.V5_SHADOW_ENABLED:
            swing_v5.run_shadow(picks, top_n=top_n)
    except Exception as e:
        logger.debug("[Swing] v5 shadow hook skipped: %s", e)

    # v4.1 shadow — OFF unless SWING_V41_SHADOW is set. Costs no extra universe
    # scan (it re-ranks the candidates already gathered above); only the fresh
    # validation prices are re-fetched. Same best-effort discipline as v5: any
    # failure is swallowed so shadow logging can never break the live scan.
    if v41_shadow_src is not None:
        try:
            _shadow_log_v41(picks, v41_shadow_src, top_n,
                            _quality, _rs_only, recent)
        except Exception as e:
            logger.debug("[Swing] v4.1 shadow hook skipped: %s", e)

    return picks


def _select_validated_picks(ranked_candidates: list[dict], top_n: int) -> list[dict]:
    """Stamp signal timestamps + a fresh price onto ranked candidates and keep
    only the first `top_n` whose actionable_status is still tradeable today.
    Rejected candidates (stale/broken) are simply skipped — no re-pricing.
    """
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    signal_ts = now.isoformat(timespec="seconds")
    chosen: list[dict] = []
    idx = 0
    batch_size = max(top_n * 4, 20)
    # Safety cap so a day with almost nothing "fresh" can't turn into an
    # unbounded LTP-fetching loop over the whole candidate list.
    max_checked = min(len(ranked_candidates), max(batch_size * 5, 200))

    while len(chosen) < top_n and idx < max_checked:
        batch = ranked_candidates[idx:min(idx + batch_size, max_checked)]
        if not batch:
            break
        ltp_map = _batch_ltp([c["symbol"] for c in batch])
        for c in batch:
            entry = c.get("entry") if c.get("entry") is not None else c.get("price")
            buy_zone_low = c.get("entry_range_low")
            buy_zone_high = c.get("entry_range_high")
            fresh = ltp_map.get(c["symbol"])
            stale = fresh is None
            current_price = fresh if fresh is not None else c.get("price")

            # Finalize the recommendation target from the SAME completed-candle
            # snapshot the pick was built from, BEFORE validation. v4 has no
            # take-profit (target1 is None), so the authoritative finite target
            # is the production-computed predicted_target_price. This is used to
            # validate/display the recommendation and gate paper eligibility — it
            # does NOT become an auto-sell take-profit (v4 rides to the stop/time
            # exit by design; see _pending_entry_from_pick).
            rec_target = c.get("target1")
            if rec_target is None:
                rec_target = c.get("predicted_target_price")
            c["recommendation_target"] = rec_target

            c["suggested_entry"] = round(float(entry), 2) if entry is not None else None
            c["buy_zone_low"] = buy_zone_low
            c["buy_zone_high"] = buy_zone_high
            c["signal_date"] = today
            c["signal_timestamp"] = signal_ts
            c["market_data_timestamp"] = signal_ts
            c["current_price_at_signal"] = (
                round(float(current_price), 2) if current_price is not None else None)
            c["data_stale"] = stale

            if stale or current_price is None:
                c["actionable_status"] = "DATA_STALE"
                c["status_reason"] = "No fresh market price available to validate this signal."
            else:
                status, reason = validate_recommendation(
                    entry=entry, buy_zone_low=buy_zone_low, buy_zone_high=buy_zone_high,
                    stop_loss=c.get("stop_loss"), target=rec_target,
                    current_price=current_price, max_entry_price=c.get("max_entry_price"),
                    require_target=True)
                c["actionable_status"] = status
                c["status_reason"] = reason

            if c["actionable_status"] not in NON_ACTIONABLE_STATUSES:
                chosen.append(c)
            if len(chosen) >= top_n:
                break
        idx += batch_size
        batch_size = min(batch_size * 2, 200)  # widen the search if too many were rejected

    return chosen[:top_n]

# ══════════════════════════════════════════════════════════════
#  SWING ANALYZER — Deep analysis for one stock
# ══════════════════════════════════════════════════════════════
async def analyze_swing(symbol: str) -> dict:
    """Deep swing analysis using math + LLM interpretation."""
    scan = _scan_stock(symbol)
    if not scan:
        return {"error": f"Could not analyze {symbol}"}

    # Get extra data for deep analysis — 6 months
    fib = {}
    weekly_trend = "Unknown"
    try:
        data_6m = _fetch_ohlcv(symbol, days=180)
        if data_6m:
            high_6m = float(np.max(data_6m["highs"]))
            low_6m = float(np.min(data_6m["lows"]))
            fib = _fibonacci_levels(high_6m, low_6m)

            # Weekly trend from 6-month data
            weekly_trend = "Up" if data_6m["closes"][-1] > data_6m["closes"][0] else "Down"
    except Exception:
        pass

    # LLM interprets the computed data
    prompt = f"""
    ROLE: You are a 25-year veteran swing trader. You trade Indian stocks on NSE.
    TASK: Provide a swing trading analysis for {scan['name']} (Current: Rs.{scan['price']}).

    COMPUTED TECHNICAL DATA (trust these numbers — they are calculated from real market data):
    RSI: {scan['rsi']}
    Stochastic RSI: {scan['stoch_rsi']}
    MACD: {scan['macd_signal']} (histogram: {scan['macd_hist']})
    ADX: {scan['adx']} ({'Strong Trend' if scan['adx'] > 25 else 'Weak/No Trend'})
    Pattern: {scan['pattern']}
    Volume: {scan['volume_ratio']}x avg {'(SPIKE!)' if scan['volume_spike'] else ''}
    Bollinger: Price at {scan['bb_position']} band
    EMA 20: Rs.{scan['ema20']} | EMA 50: Rs.{scan['ema50']}
    Trend: {scan['trend']} | Weekly: {weekly_trend}
    ATR: Rs.{scan['atr']}
    Supports: {scan['supports']}
    Resistances: {scan['resistances']}
    Pivot Points: {json.dumps(scan['pivots'])}
    52W High: Rs.{scan['high_52w']} | 52W Low: Rs.{scan['low_52w']}
    Fibonacci: {json.dumps(fib)}
    Setup: {scan['setup']}
    Entry: Rs.{scan['entry']} | SL: Rs.{scan['stop_loss']} (2.5xATR, checked on daily CLOSE only)
    Exit engine v4: NO price target — hold up to 20 sessions, exit at time limit or stop.
    Max entry price: Rs.{scan.get('max_entry_price')} (skip the trade if it opens above this — >4% gap-ups lose)
    Data Source: {scan['data_source']}

    Provide your expert swing trade plan. Output JSON only:
    {{
        "trade_plan": "1-2 sentence trade plan in plain English",
        "entry_trigger": "What exact condition to enter (e.g. 'Buy above Rs.X with volume confirmation')",
        "exit_plan": "When to exit — both profit and loss scenarios",
        "hold_duration": "Expected hold: up to 20 sessions (v4 time exit)",
        "confidence": "High / Medium / Low",
        "key_levels": "Key price levels to watch",
        "risk_warning": "1 sentence: biggest risk",
        "edge": "What gives this trade an edge"
    }}
    """
    llm_analysis = await ai_models.async_llm_call(prompt)

    return {**scan, "fibonacci": fib, "weekly_trend": weekly_trend, "llm_analysis": llm_analysis}

# ══════════════════════════════════════════════════════════════
#  PAPER TRADING ENGINE — Virtual portfolio with auto-execution
# ══════════════════════════════════════════════════════════════
# Anchored to this file (not the CWD) so paper/desk data survives the backend
# being launched from a different working directory.
PAPER_DATA_DIR = Path(__file__).parent / "data" / "paper_trading"
PAPER_DATA_DIR.mkdir(parents=True, exist_ok=True)
INITIAL_CAPITAL = 1_000_000  # Rs. 10 Lakh

# Per-user synced data directory (backend/data/users/<hash>), set by
# main._switch_user_data on login/logout. When set, all swing state (paper,
# desk, daily picks) lives there under fixed filenames so Google Drive sync
# picks it up; when None (logged out) the legacy paper_trading paths are used.
_active_user_dir: Path | None = None

# Fixed per-user filenames (must match google_auth.SYNC_FILES)
PAPER_SYNC_NAME = "swing_paper.json"
DESK_SYNC_NAME = "swing_desk.json"
PICKS_SYNC_NAME = "swing_daily_picks.json"


def set_active_data_dir(user_dir: Path | None):
    """Point swing storage at the logged-in user's synced folder (or back to legacy)."""
    global _active_user_dir
    _active_user_dir = Path(user_dir) if user_dir else None
    if _active_user_dir is not None:
        _migrate_legacy_swing_files(_active_user_dir)


def _migrate_legacy_swing_files(user_dir: Path):
    """Copy legacy data/paper_trading files into the per-user folder (never delete)."""
    legacy_dirs = [PAPER_DATA_DIR, Path("data/paper_trading").resolve()]
    for legacy in legacy_dirs:
        for src_name, dst_name in (("default.json", PAPER_SYNC_NAME),
                                   ("desk_default.json", DESK_SYNC_NAME),
                                   (PICKS_SYNC_NAME, PICKS_SYNC_NAME)):
            src = legacy / src_name
            dst = user_dir / dst_name
            try:
                if src.exists() and not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    logger.info("[Swing] Migrated %s -> %s", src, dst)
            except Exception as e:
                logger.warning("[Swing] Migration failed for %s: %s", src, e)


def _drive_upload_async(path: Path):
    """Background-upload a saved swing file to Drive when a user is logged in."""
    if _active_user_dir is None or path.parent != _active_user_dir:
        return

    def _bg():
        try:
            import google_auth
            google_auth.drive_upload_file(path.name, data_dir=path.parent)
        except Exception as e:
            logger.debug("[Swing] Drive upload failed for %s: %s", path.name, e)

    threading.Thread(target=_bg, daemon=True).start()


def _paper_file(user_id: str = "default") -> Path:
    if _active_user_dir is not None:
        return _active_user_dir / PAPER_SYNC_NAME
    return PAPER_DATA_DIR / f"{user_id}.json"

def _load_paper(user_id: str = "default") -> dict:
    f = _paper_file(user_id)
    if f.exists():
        with open(f, "r") as fh:
            data = json.load(fh)
        data.setdefault("pending_entries", [])
        data.setdefault("missed_entries", [])
        return data
    return {
        "capital": INITIAL_CAPITAL,
        "cash": INITIAL_CAPITAL,
        "pending_entries": [],   # PENDING_ENTRY watch items — not yet filled
        "missed_entries": [],    # transparency log: setups rejected/expired unfilled
        "positions": [],
        "closed_trades": [],
        "start_date": datetime.now().strftime("%Y-%m-%d"),
        "day_count": 0,
        "daily_equity": [],
    }

def _save_paper(data: dict, user_id: str = "default"):
    f = _paper_file(user_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w") as fh:
        json.dump(data, fh, indent=2, default=str)
    _drive_upload_async(f)

def paper_status(user_id: str = "default") -> dict:
    """Get paper trading portfolio status with live P&L."""
    data = _load_paper(user_id)
    total_invested = 0
    total_current = 0
    positions = []

    # Batch fetch LTP for all positions via Kite MCP
    pos_symbols = [p["symbol"] for p in data.get("positions", [])]
    ltp_map = _batch_ltp_kite(pos_symbols) if pos_symbols else {}

    for pos in data.get("positions", []):
        # Use batch LTP from Kite, fallback to Yahoo
        ltp = ltp_map.get(pos["symbol"])
        if ltp is None:
            ltp = _fetch_ltp(pos["symbol"])
        if ltp is None:
            ltp = pos["entry_price"]

        invested = pos["entry_price"] * pos["quantity"]
        current = ltp * pos["quantity"]
        pnl = current - invested
        pnl_pct = round(pnl / invested * 100, 2) if invested > 0 else 0
        total_invested += invested
        total_current += current

        # Check SL/Target hit (v4 positions carry no target)
        sl_hit = ltp <= (pos.get("stop_loss") or 0)
        tgt_hit = ltp >= (pos.get("target") or 999999)

        positions.append({
            **pos, "ltp": round(ltp, 2),
            "current_value": round(current, 2),
            "pnl": round(pnl, 2), "pnl_pct": pnl_pct,
            "sl_hit": sl_hit, "tgt_hit": tgt_hit,
            "status": "SL HIT!" if sl_hit else "TARGET!" if tgt_hit else "Active",
        })

    # Stats from closed trades
    closed = data.get("closed_trades", [])
    wins = [t for t in closed if t.get("pnl", 0) > 0]
    losses = [t for t in closed if t.get("pnl", 0) <= 0]
    total_pnl_closed = sum(t.get("pnl", 0) for t in closed)
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0
    initial_capital = data.get("capital") or INITIAL_CAPITAL

    return {
        "cash": round(data["cash"], 2),
        "initial_capital": initial_capital,
        "positions": positions,
        "pending_entries": data.get("pending_entries", []),
        "missed_entries": data.get("missed_entries", [])[-20:],
        "closed_trades": closed[-20:],  # Last 20
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "unrealized_pnl": round(total_current - total_invested, 2),
        "realized_pnl": round(total_pnl_closed, 2),
        "total_equity": round(data["cash"] + total_current, 2),
        "total_pnl": round(data["cash"] + total_current - initial_capital, 2),
        "total_pnl_pct": round((data["cash"] + total_current - initial_capital) / initial_capital * 100, 2),
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "start_date": data.get("start_date", ""),
        "day_count": data.get("day_count", 0),
        "daily_equity": data.get("daily_equity", []),
    }

def paper_buy(symbol: str, quantity: int, entry_price: float,
              stop_loss: float, target: float, setup: str = "",
              user_id: str = "default", suggested_entry: float = None,
              signal_timestamp: str = None, fill_source: str = "manual",
              fill_reason: str = "") -> dict:
    """Execute a paper buy trade at `entry_price` — this MUST already be a
    real, freshly-observed executable price (see determine_fill /
    _desk_execute_buy / paper_try_fill_pending); this function does not
    itself validate against a buy zone. Records both the originally
    suggested entry and the actual fill so the two are never confused."""
    data = _load_paper(user_id)
    cost = entry_price * quantity
    if cost > data["cash"]:
        return {"error": "Insufficient paper capital", "cash": data["cash"], "cost": cost}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    data["cash"] -= cost
    data["positions"].append({
        "symbol": symbol,
        "name": symbol.replace(".NS", "").replace(".BO", ""),
        "quantity": quantity,
        "entry_price": round(entry_price, 2),          # = actual_fill_price (kept for back-compat)
        "actual_fill_price": round(entry_price, 2),
        "suggested_entry": (round(suggested_entry, 2)
                             if suggested_entry is not None else round(entry_price, 2)),
        "stop_loss": round(stop_loss, 2),
        # v4: no take-profit — winners exit at the 20-session time limit
        "target": (round(target, 2) if target else None),
        "setup": setup,
        "entry_date": now_str,
        "filled_at": now_str,
        "signal_timestamp": signal_timestamp or now_str,
        "fill_source": fill_source,
        "fill_reason": fill_reason or "Filled at observed market price.",
    })
    _save_paper(data, user_id)
    return {"status": "bought", "symbol": symbol, "quantity": quantity,
            "entry_price": entry_price, "actual_fill_price": entry_price,
            "filled_at": now_str, "cash_remaining": round(data["cash"], 2)}

def paper_sell(symbol: str, exit_price: float = None,
              reason: str = "manual", user_id: str = "default") -> dict:
    """Sell a paper position."""
    data = _load_paper(user_id)
    pos = None
    pos_idx = None
    for i, p in enumerate(data["positions"]):
        if p["symbol"] == symbol:
            pos = p
            pos_idx = i
            break
    if pos is None:
        return {"error": f"No position found for {symbol}"}

    if exit_price is None:
        exit_price = _fetch_ltp(symbol) or pos["entry_price"]

    proceeds = exit_price * pos["quantity"]
    pnl = proceeds - (pos["entry_price"] * pos["quantity"])
    pnl_pct = round(pnl / (pos["entry_price"] * pos["quantity"]) * 100, 2)

    data["cash"] += proceeds
    data["positions"].pop(pos_idx)
    data["closed_trades"].append({
        **pos,
        "exit_price": round(exit_price, 2),
        "exit_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pnl": round(pnl, 2),
        "pnl_pct": pnl_pct,
        "reason": reason,
    })
    _save_paper(data, user_id)
    return {"status": "sold", "symbol": symbol, "exit_price": exit_price,
            "pnl": round(pnl, 2), "pnl_pct": pnl_pct, "cash": round(data["cash"], 2)}

def paper_auto_check(user_id: str = "default") -> list[dict]:
    """Auto-check all positions for v4 exits and execute sells.

    v4 exit engine (research/V4_EXIT_STUDY.md):
    - Stop 2.5×ATR, evaluated on the daily CLOSE — so the stop only fires when
      checked after 15:00 IST (the close read), except a deep emergency breach
      (>5% through the stop) which exits immediately.
    - Time exit after 20 trading sessions (~28 calendar days).
    - Take-profit fires only for legacy positions that still carry a target.
    """
    data = _load_paper(user_id)
    actions = []
    to_sell = []

    # Batch fetch LTP for all positions
    pos_symbols = [p["symbol"] for p in data["positions"]]
    ltp_map = _batch_ltp_kite(pos_symbols) if pos_symbols else {}

    now = datetime.now()
    close_read = now.hour >= 15  # after 3 pm IST ≈ the daily close check
    for pos in data["positions"]:
        ltp = ltp_map.get(pos["symbol"])
        if ltp is None:
            ltp = _fetch_ltp(pos["symbol"])
        if ltp is None:
            continue

        stop = pos.get("stop_loss") or 0
        target = pos.get("target") or None
        held_days = None
        try:
            entered = datetime.strptime(pos.get("entry_date", "")[:10], "%Y-%m-%d")
            held_days = (now - entered).days
        except Exception:
            pass

        if ltp <= stop and (close_read or ltp <= stop * 0.95):
            to_sell.append((pos["symbol"], ltp, "Stop Loss Hit (close check)"))
        elif target is not None and ltp >= target:
            to_sell.append((pos["symbol"], ltp, "Target Reached"))
        elif held_days is not None and held_days >= 28:
            to_sell.append((pos["symbol"], ltp, "Time Exit (20 sessions)"))

    for sym, price, reason in to_sell:
        result = paper_sell(sym, exit_price=price, reason=reason, user_id=user_id)
        actions.append(result)

    actions += paper_try_fill_pending(user_id)
    return actions


def _pending_entry_from_pick(pick: dict, quantity: int, source: str = "auto_scan") -> dict:
    """A PENDING_ENTRY watch item — a recommendation that exists but has NOT
    been bought. Carries the signal-time snapshot so a later fill can never
    be confused with a backdated/earlier price."""
    now_iso = datetime.now().isoformat(timespec="seconds")
    return {
        "symbol": pick["symbol"],
        "name": pick.get("name", str(pick["symbol"]).replace(".NS", "")),
        "quantity": quantity,
        "suggested_entry": pick.get("suggested_entry", pick.get("entry")),
        "buy_zone_low": pick.get("buy_zone_low", pick.get("entry_range_low")),
        "buy_zone_high": pick.get("buy_zone_high", pick.get("entry_range_high")),
        "max_entry_price": pick.get("max_entry_price"),
        "stop_loss": pick.get("stop_loss"),
        "target": pick.get("target1"),  # None under v4 — no take-profit exit
        # The finite target used to VALIDATE/display this recommendation (from
        # the same snapshot). Recorded for provenance; not an auto-sell trigger.
        "recommendation_target": pick.get("recommendation_target"),
        "setup": pick.get("setup", ""),
        "signal_date": pick.get("signal_date", datetime.now().strftime("%Y-%m-%d")),
        "signal_timestamp": pick.get("signal_timestamp", now_iso),
        "current_price_at_signal": pick.get("current_price_at_signal"),
        "actionable_status": pick.get("actionable_status", "WAIT_FOR_ENTRY"),
        "status_reason": pick.get("status_reason", ""),
        "source": source,
        "status": "PENDING_ENTRY",
    }


def paper_try_fill_pending(user_id: str = "default") -> list[dict]:
    """Attempt to fill every PENDING_ENTRY watch item at a FRESHLY observed
    price. Never backdates: the only price ever considered is one fetched
    right now (i.e. at/after the signal's own timestamp) — see determine_fill.
    A gap straight over the buy zone marks the item MISSED_ENTRY instead of
    filling at the old suggested_entry. Pending items unresolved for longer
    than SWING_CONFIG['pending_entry_max_days'] trading days expire.
    """
    data = _load_paper(user_id)
    pending = list(data.get("pending_entries", []))
    if not pending:
        return []

    ltp_map = _batch_ltp([p["symbol"] for p in pending])
    now = datetime.now()
    still_pending, newly_missed, actions = [], [], []

    for p in pending:
        observed = ltp_map.get(p["symbol"])
        age_days = _trading_days_between(p.get("signal_date", now.strftime("%Y-%m-%d")), now)
        expired = age_days > SWING_CONFIG["pending_entry_max_days"]

        if observed is None:
            if expired:
                newly_missed.append({**p, "removal_reason":
                                     "Expired — no fresh price before the watch window closed"})
                actions.append({"status": "expired", "symbol": p["symbol"]})
            else:
                p["actionable_status"] = "DATA_STALE"
                p["status_reason"] = "No fresh market price available."
                still_pending.append(p)
            continue

        result = determine_fill(
            buy_zone_low=p.get("buy_zone_low"), buy_zone_high=p.get("buy_zone_high"),
            max_entry_price=p.get("max_entry_price"), observed_price=observed)

        if result["filled"]:
            fill_price = result["fill_price"]
            adj_stop, adj_target = adjust_levels_for_fill(
                p.get("suggested_entry"), p.get("stop_loss"), p.get("target"), fill_price)
            buy_result = paper_buy(
                symbol=p["symbol"], quantity=p["quantity"], entry_price=fill_price,
                stop_loss=adj_stop, target=adj_target, setup=p.get("setup", ""),
                user_id=user_id, suggested_entry=p.get("suggested_entry"),
                signal_timestamp=p.get("signal_timestamp"),
                fill_source=p.get("source", "auto_scan"), fill_reason=result["reason"])
            actions.append({"status": "filled", "symbol": p["symbol"], **buy_result})
        elif result["status"] == "MISSED_ENTRY":
            newly_missed.append({**p, "removal_reason": result["reason"], "observed_price": observed})
            actions.append({"status": "missed", "symbol": p["symbol"], "reason": result["reason"]})
        elif expired:
            newly_missed.append({**p, "removal_reason":
                                 "Expired — signal window elapsed without an entry"})
            actions.append({"status": "expired", "symbol": p["symbol"]})
        else:
            p["last_observed_price"] = round(observed, 2)
            p["actionable_status"] = result["status"]  # typically WAIT_FOR_ENTRY
            p["status_reason"] = result["reason"]
            still_pending.append(p)

    # Reload — paper_buy() above already persisted any cash/position changes.
    data = _load_paper(user_id)
    data["pending_entries"] = still_pending
    data["missed_entries"] = (data.get("missed_entries", []) + newly_missed)[-50:]
    _save_paper(data, user_id)
    return actions


def paper_auto_buy_picks(picks: list[dict], user_id: str = "default") -> list[dict]:
    """Queue today's validated swing picks as PENDING_ENTRY watch items, then
    attempt an immediate fill at a freshly observed price.

    Never buys directly at pick['entry'] / pick['price'] — that was the bug:
    'entry' can be a historical support/resistance trigger that's already far
    from the current live price. A position only opens once
    paper_try_fill_pending confirms a fresh price is actually inside the buy
    zone. Picks whose actionable_status is already stale/broken (MISSED_ENTRY,
    TARGET_ALREADY_REACHED, INVALID, DATA_STALE) are never queued at all.
    """
    data = _load_paper(user_id)
    held = {p["symbol"] for p in data["positions"]}
    already_pending = {p["symbol"] for p in data.get("pending_entries", [])}
    live_picks = [p for p in picks
                  if p.get("actionable_status") not in NON_ACTIONABLE_STATUSES]
    available = data["cash"]
    per_pick = available / max(len(live_picks), 1) * 0.9  # Use 90% of available cash

    for pick in live_picks:
        sym = pick["symbol"]
        if sym in held or sym in already_pending:
            continue
        ref_price = pick.get("current_price_at_signal") or pick.get("price")
        if not ref_price or per_pick < ref_price:
            continue  # can't afford even 1 share
        qty = max(1, int(per_pick / ref_price))
        data.setdefault("pending_entries", []).append(
            _pending_entry_from_pick(pick, qty, source="auto_scan"))

    _save_paper(data, user_id)
    results = paper_try_fill_pending(user_id)  # attempt an immediate fill

    # Record daily equity — mark-to-market (cash + Σ ltp·qty) so the curve
    # reflects unrealized P&L, consistent with paper_status.total_equity.
    data = _load_paper(user_id)
    equity = data["cash"]
    pos_symbols = [p["symbol"] for p in data["positions"]]
    ltp_map = _batch_ltp_kite(pos_symbols) if pos_symbols else {}
    for pos in data["positions"]:
        ltp = ltp_map.get(pos["symbol"])
        if ltp is None:
            ltp = _fetch_ltp(pos["symbol"])
        if ltp is None:
            ltp = pos["entry_price"]  # last resort: cost basis
        equity += ltp * pos["quantity"]
    data["daily_equity"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "equity": round(equity, 2),
    })
    data["day_count"] = len(data["daily_equity"])
    _save_paper(data, user_id)

    return results

def paper_reset(user_id: str = "default", capital: float = None) -> dict:
    """Reset paper trading account, initializing a clean account at `capital`
    (falls back to the default INITIAL_CAPITAL when not supplied)."""
    cap = capital if capital and capital > 0 else INITIAL_CAPITAL
    data = {
        "capital": cap,
        "cash": cap,
        "pending_entries": [],
        "missed_entries": [],
        "positions": [],
        "closed_trades": [],
        "start_date": datetime.now().strftime("%Y-%m-%d"),
        "day_count": 0,
        "daily_equity": [{"date": datetime.now().strftime("%Y-%m-%d"), "equity": cap}],
    }
    _save_paper(data, user_id)
    return {"status": "reset", "capital": cap}

# ══════════════════════════════════════════════════════════════
#  PERSISTED DAILY PICKS — first successful scan of a date is canonical
# ══════════════════════════════════════════════════════════════
#  Shape: {"dates": {"YYYY-MM-DD": {"created_at": "...", "picks": [...]}}}

def _picks_file(user_id: str = "default") -> Path:
    base = _active_user_dir if _active_user_dir is not None else PAPER_DATA_DIR
    return base / PICKS_SYNC_NAME


def _load_picks_store(user_id: str = "default") -> dict:
    f = _picks_file(user_id)
    if f.exists():
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("dates"), dict):
                return data
        except Exception as e:
            logger.warning("[Swing] Could not read %s: %s", f, e)
    return {"dates": {}}


def _pick_key(date: str, variant: str = "") -> str:
    """Storage key for a date's picks. variant namespaces alternate engines
    (e.g. 'v5') so they never collide with the v4 canonical list; the default
    empty variant keeps the v4 key exactly as before."""
    return f"{date}::{variant}" if variant else date


def load_saved_picks(date: str, user_id: str = "default", variant: str = "") -> list | None:
    """Saved canonical picks for a date (optionally an engine variant), or None
    if that date/variant has no publishable list yet.

    An EMPTY stored list reads as None here, deliberately. A scan that returned
    nothing is a failed scan, not a published "no setups today" verdict: the
    universe is thousands of names wide and the gates leave dozens of
    candidates on an ordinary day, so zero picks means the scan itself broke
    (Kite/Yahoo unavailable mid-pass, rate limiting, a cold start racing the
    first poll). Returning [] here used to be indistinguishable from a real
    list, which froze the day's Focus List at empty until midnight and made
    `force` a no-op at every call site. The empty entry is still kept on disk
    for the audit trail — it just never shadows a rescan.
    """
    entry = _load_picks_store(user_id)["dates"].get(_pick_key(date, variant))
    if isinstance(entry, dict) and isinstance(entry.get("picks"), list):
        return entry["picks"] or None
    return None


def save_daily_picks(date: str, picks: list[dict], user_id: str = "default",
                     overwrite: bool = False, variant: str = "") -> list[dict]:
    """Persist a date's picks and return the canonical list for that date.

    The first NON-EMPTY save for a date (per variant) wins; later saves are
    ignored unless overwrite (a deliberate hard reset) is set. `variant`
    namespaces alternate engines (default '' = the v4 canonical list,
    unchanged).

    An empty `picks` never becomes canonical and never replaces a list that
    already has rows — not even under `overwrite`. A hard rescan that comes
    back empty is a failed rescan; letting it win destroyed the morning's
    published list on 2026-07-30 and 2026-08-03 (5 and 3 picks respectively,
    each already admitted to the 14-day desk). The empty attempt is still
    recorded so the day is visibly "scanned, found nothing" rather than
    silently absent, but load_saved_picks treats it as unsaved.
    """
    store = _load_picks_store(user_id)
    key = _pick_key(date, variant)
    existing = store["dates"].get(key)
    existing_picks = existing.get("picks") if isinstance(existing, dict) else None
    if not isinstance(existing_picks, list):
        existing_picks = None

    # An empty result yields to whatever is already published, overwrite or not.
    if not picks and existing_picks:
        logger.warning("[Swing] Empty scan for %s ignored — keeping the %d "
                       "already-published pick(s)", key, len(existing_picks))
        return existing_picks
    # A non-empty canonical list is what "first save wins" protects.
    if not overwrite and existing_picks:
        return existing_picks
    picks = _json_safe(picks)  # keep NaN/Inf out of stored + returned picks
    # A hard refresh used to silently destroy the list that was already
    # published (and already admitted to the desk) for that date, which left
    # Daily Pick History unable to join any of it back to real tracking. Keep
    # the superseded lists so the audit trail survives an overwrite.
    superseded = []
    if isinstance(existing, dict):
        superseded = list(existing.get("superseded") or [])
        if existing_picks:
            superseded.append({
                "created_at": existing.get("created_at"),
                "picks": existing["picks"],
            })
            superseded = superseded[-5:]
    store["dates"][key] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "picks": picks,
    }
    if superseded:
        store["dates"][key]["superseded"] = superseded
    f = _picks_file(user_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w") as fh:
        json.dump(store, fh, indent=2, default=str)
    _drive_upload_async(f)
    return picks


def get_daily_picks(force: bool = False) -> list[dict]:
    """Canonical picks for today: saved list first; scan only when absent or forced."""
    today = datetime.now().strftime("%Y-%m-%d")
    if not force:
        saved = load_saved_picks(today)
        if saved:  # an empty/absent day re-scans rather than serving nothing
            return saved
    picks = scan_swing_picks(5)
    return save_daily_picks(today, picks, overwrite=force)


def hard_refresh_daily_picks() -> list[dict]:
    """Explicit hard reset: discard today's saved picks and re-scan."""
    return get_daily_picks(force=True)


def get_daily_picks_response(force: bool = False) -> dict:
    """Daily-picks response with the true universe size for the frontend.

    Wraps get_daily_picks; use this when the frontend needs an accurate
    universe count (avoids the false "80+ & BSE" copy).
    """
    picks = get_daily_picks(force=force)
    return {
        "picks": picks,
        "universe_size": get_universe_size(),
    }


def with_live_price_overlay(picks: list[dict]) -> list[dict]:
    """Attach a fresh `live_price` to each pick for display purposes only.

    Does NOT touch the persisted signal-time fields (current_price_at_signal,
    actionable_status, buy zone, etc.) — those are frozen at publish time so
    "today's canonical recommendation" never silently changes underfoot. This
    is purely so the UI can show "signal price" next to "live price now".
    """
    if not picks:
        return picks
    symbols = [p.get("symbol") for p in picks if p.get("symbol")]
    ltp_map = _batch_ltp(symbols) if symbols else {}
    out = []
    for p in picks:
        p = dict(p)
        p["live_price"] = ltp_map.get(p.get("symbol"))
        out.append(p)
    return out


_hist_ltp_cache: tuple[float, tuple, dict] | None = None
_HIST_LTP_TTL = 60  # the history panel reloads often; one LTP batch per minute


def _history_ltp(symbols: list[str]) -> dict:
    """Live LTP for the history overlay, cached ~1 min so repeated panel loads
    don't re-run a 24-symbol Yahoo batch on every refresh."""
    global _hist_ltp_cache
    key = tuple(symbols)
    if not key:
        return {}
    if (_hist_ltp_cache and _hist_ltp_cache[1] == key
            and time.time() - _hist_ltp_cache[0] < _HIST_LTP_TTL):
        return _hist_ltp_cache[2]
    try:
        result = _batch_ltp(symbols) or {}
    except Exception as e:
        logger.debug("[Swing] Pick-history LTP overlay failed: %s", e)
        result = {}
    _hist_ltp_cache = (time.time(), key, result)
    return result


def _history_untracked_row(row: dict, elsewhere: str | None) -> dict:
    """Fill in a pick that the desk never tracked under its own date."""
    row.update({
        "tracked": False,
        "status": "NOT_TRACKED",
        "current_price": None,
        "live_price": None,
        "actual_profit_pct": None,
        "tracking_day": None,
        "day_snapshots": {},
        "final_result_pct": None,
        # The most common reason a pick is untracked is that the same symbol
        # was already on the desk from an earlier day — say so instead of a
        # bare "Not tracked".
        "tracked_elsewhere_date": elsewhere,
    })
    return row


def _history_tracked_row(row: dict, kind: str, tracked: dict, now: datetime,
                         ltp_map: dict) -> dict:
    """Fill in a pick the desk is (or was) tracking, with a live price overlay.

    The overlay matters because a same-day pick and its first re-scan both read
    the same (unfinished) daily candle, so the stored prices are identical and
    the pick reads as an exactly-flat +0.0%. Live LTP is what the user means by
    "profit so far".
    """
    if kind == "history":
        row.update({
            "tracked": True,
            "status": "EXPIRED" if "actual_profit_pct" in tracked else "REMOVED",
            "current_price": tracked.get("final_price"),
            "live_price": None,
            "actual_profit_pct": tracked.get("actual_profit_pct"),
            "tracking_day": DESK_THRESHOLDS["max_tracking_days"],
            "day_snapshots": tracked.get("day_snapshots", {}),
            "final_result_pct": tracked.get("actual_profit_pct"),
        })
        return row

    view = _desk_stock_view(tracked, now)
    orig_price = row.get("original_price") or view["original_price"]
    live_price = ltp_map.get(tracked.get("symbol"))
    profit_pct = view["price_change_pct"]
    if live_price and orig_price:
        profit_pct = round((live_price - orig_price) / orig_price * 100, 2)
    row.update({
        "tracked": True,
        "status": view["tracking_status"],
        "current_price": live_price or view["current_price"],
        "live_price": live_price,
        "actual_profit_pct": profit_pct,
        "tracking_day": view["tracking_day"],
        "day_snapshots": view["day_snapshots"],
        "final_result_pct": None,  # still tracking — no final result yet
    })
    return row


def get_daily_pick_history(user_id: str = "default", live: bool = True) -> list[dict]:
    """Every pick date joined with each pick's tracked outcome, for the
    "Daily Pick History" view — a read-only join of two already-persisted
    stores (swing_daily_picks.json + swing_desk.json) plus a live LTP overlay.
    No new prediction logic; only presents what's already been collected.

    The desk is treated as authoritative for what was actually tracked: any
    desk record whose date/symbol is missing from the picks store is still
    listed under its own selected_date. Without that, a hard refresh that
    replaced a date's saved picks after the desk had already admitted the
    morning list made every one of that day's rows read "Not tracked" with no
    P&L at all, even though the desk was tracking five stocks with real gains.
    """
    picks_store = _load_picks_store(user_id)
    desk_data = _load_desk(user_id)
    now = datetime.now()

    by_symbol_date: dict[tuple, tuple] = {}
    tracked_dates_by_symbol: dict[str, str] = {}
    for r in desk_data.get("records", []):
        by_symbol_date[(r.get("symbol"), r.get("selected_date"))] = ("active", r)
        tracked_dates_by_symbol.setdefault(r.get("symbol"), r.get("selected_date"))
    for h in desk_data.get("history", []):
        key = (h.get("symbol"), h.get("selected_date"))
        by_symbol_date.setdefault(key, ("history", h))
        tracked_dates_by_symbol.setdefault(h.get("symbol"), h.get("selected_date"))

    ltp_map: dict[str, float] = {}
    if live:
        symbols = sorted({r.get("symbol") for r in desk_data.get("records", [])
                          if r.get("symbol")})
        ltp_map = _history_ltp(symbols)

    def base_row(p: dict, source: str) -> dict:
        return {
            "symbol": p.get("symbol"),
            "name": p.get("name"),
            "predicted_gain_pct": p.get("predicted_gain_pct"),
            "prediction_confidence": p.get("prediction_confidence", p.get("score")),
            "original_price": p.get("price"),
            "source": source,
        }

    # date -> {symbol: row}, so a tracked row always wins over an untracked
    # duplicate of the same symbol (a re-scan can re-publish a symbol the desk
    # already holds for that day).
    grouped: dict[str, dict[str, dict]] = {}

    def add(date: str, row: dict):
        slot = grouped.setdefault(date, {})
        prev = slot.get(row["symbol"])
        if prev is None or (row.get("tracked") and not prev.get("tracked")):
            slot[row["symbol"]] = row

    seen_desk_keys = set()
    for key in picks_store.get("dates", {}):
        entry = picks_store["dates"][key] or {}
        date, _, variant = str(key).partition("::")
        lists = [(entry.get("picks") or [], "picks")]
        # Superseded lists (a hard refresh replaced them) still belong to the
        # day they were published on.
        for s in entry.get("superseded") or []:
            lists.append((s.get("picks") or [], "superseded"))
        if variant and not any(items for items, _ in lists):
            # An empty shadow-engine variant (e.g. "2026-07-30::v5") was
            # rendering as its own date group showing "0 picks · 0 tracked".
            continue
        # A non-empty variant keeps its own group so a shadow engine's list is
        # never confused with the canonical one for that day.
        group = str(key)
        for items, source in lists:
            for p in items:
                sym = p.get("symbol")
                row = base_row(p, source)
                if variant:
                    row["variant"] = variant
                kind, tracked = by_symbol_date.get((sym, date), (None, None))
                if kind:
                    seen_desk_keys.add((sym, date))
                    add(group, _history_tracked_row(row, kind, tracked, now, ltp_map))
                else:
                    elsewhere = tracked_dates_by_symbol.get(sym)
                    add(group, _history_untracked_row(
                        row, elsewhere if elsewhere != date else None))

    # Desk records with no surviving saved pick for their date — the desk is
    # the record of what was really tracked, so surface them regardless.
    for (sym, date), (kind, tracked) in by_symbol_date.items():
        if (sym, date) in seen_desk_keys or not date:
            continue
        row = base_row({
            "symbol": sym,
            "name": tracked.get("name"),
            "predicted_gain_pct": (tracked.get("predicted_gain_pct")
                                   or tracked.get("original_predicted_gain_pct")),
            "prediction_confidence": (tracked.get("prediction_confidence")
                                      or tracked.get("original_score")),
            "price": tracked.get("original_price"),
        }, "desk")
        add(date, _history_tracked_row(row, kind, tracked, now, ltp_map))

    def row_order(r: dict):
        # Rows that actually have an outcome first, best performer at the top —
        # otherwise a day whose saved list was replaced leads with five rows
        # that have no numbers at all and the day reads as broken.
        pct = r.get("actual_profit_pct")
        return (0 if r.get("tracked") else 1, -(pct if pct is not None else -1e9))

    return [{"date": date,
             "picks": sorted(grouped[date].values(), key=row_order)}
            for date in sorted(grouped, reverse=True)]


# ══════════════════════════════════════════════════════════════
#  14-DAY SWING DESK — AI-selected, user-executed watchlist
# ══════════════════════════════════════════════════════════════
#  Today's Picks are ideas; the desk is the system-selected watchlist. The best
#  few picks per scan day (max 5/day) are tracked for 14 trading days. Nothing
#  auto-buys unless the user arms a stock and it then turns READY. All lifecycle
#  thresholds mirror the frontend DeskThresholds (swing_signals.dart) so the
#  server-computed badges match what the UI expects.

DESK_DATA_DIR = PAPER_DATA_DIR
DESK_MAX_PER_DAY = 5

DESK_THRESHOLDS = {
    "max_tracking_days": 14,
    "entry_wait_days": 3,
    "strong_confirm_day": 11,
    "min_score_keep": 45,
    "score_drop_remove": 20,
    "weakened_score_drop": 8,
    "improved_score_gain": 5,
    "min_rr_keep": 1.2,
    "ready_min_volume_ratio": 0.8,
    "ready_min_data_quality": 40,
    "strong_min_rr": 2.0,
    "strong_min_volume_ratio": 1.0,
}


def _desk_file(user_id: str = "default") -> Path:
    if _active_user_dir is not None:
        return _active_user_dir / DESK_SYNC_NAME
    return DESK_DATA_DIR / f"desk_{user_id}.json"


def _load_desk(user_id: str = "default") -> dict:
    f = _desk_file(user_id)
    if f.exists():
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
                data.setdefault("records", [])
                data.setdefault("history", [])
                data.setdefault("last_reanalyze_date", None)
                for r in data["records"]:
                    _desk_migrate_record(r)
                return data
        except Exception:
            pass
    return {"records": [], "history": [], "last_reanalyze_date": None}


def _desk_migrate_record(r: dict):
    """Backfill fields added after a record was first written (older desks)."""
    r.setdefault("reanalysis_history", [])
    if "initial_snapshot" not in r:
        r["initial_snapshot"] = {
            "analyzed_at": r.get("selected_date"),
            "price": r.get("original_price"),
            "score": r.get("original_score"),
            "grade": r.get("original_grade"),
            "recommendation": "WAIT",
            "risk_reward": r.get("risk_reward"),
            "indicators": r.get("original_indicators", {}),
            "levels": {
                "entry": r.get("original_entry"),
                "stop_loss": r.get("original_stop_loss"),
                "target1": r.get("original_target1"),
                "target2": r.get("original_target2"),
            },
        }
    r.setdefault("original_indicators", r.get("initial_snapshot", {}).get("indicators", {}))
    r.setdefault("current_indicators", {})
    r.setdefault("current_entry", r.get("original_entry"))
    r.setdefault("current_stop_loss", r.get("original_stop_loss"))
    r.setdefault("current_target1", r.get("original_target1"))
    r.setdefault("current_target2", r.get("original_target2"))
    r.setdefault("what_changed", "")
    # Signal-integrity fields (added after older desks were first written).
    r.setdefault("suggested_entry", r.get("original_entry"))
    r.setdefault("max_entry_price", None)
    r.setdefault("signal_date", r.get("selected_date"))
    r.setdefault("signal_timestamp", r.get("selected_at"))
    r.setdefault("current_price_at_signal", r.get("original_price"))
    r.setdefault("market_data_timestamp", r.get("selected_at"))
    r.setdefault("original_actionable_status", None)
    r.setdefault("original_status_reason", "")


def _save_desk(data: dict, user_id: str = "default"):
    f = _desk_file(user_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w") as fh:
        json.dump(data, fh, indent=2, default=str)
    _drive_upload_async(f)


def _desk_grade(score) -> str:
    s = score or 0
    if s >= 85:
        return "A+"
    if s >= 75:
        return "A"
    if s >= 65:
        return "B"
    if s >= 55:
        return "C"
    return "Avoid"


def _desk_parse_rr(rr) -> float:
    """Parse a '1:2.0' style ratio (or a raw number) into a float reward:risk."""
    if isinstance(rr, (int, float)):
        return float(rr)
    if isinstance(rr, str) and ":" in rr:
        try:
            return float(rr.split(":")[1])
        except Exception:
            return 0.0
    return 0.0


def _trading_days_between(from_date: str, to_date: datetime) -> int:
    """Weekdays strictly after from_date, up to and including to_date."""
    try:
        d = datetime.strptime(from_date[:10], "%Y-%m-%d")
    except Exception:
        return 0
    d = datetime(d.year, d.month, d.day)
    end = datetime(to_date.year, to_date.month, to_date.day)
    if end <= d:
        return 0
    days = 0
    while d < end:
        d += timedelta(days=1)
        if d.weekday() <= 4:  # Mon-Fri
            days += 1
    return days


def _desk_ready_conditions_met(record: dict, snapshot: dict, days: int) -> bool:
    """Every READY condition must hold today (mirrors readyConditionsMet)."""
    th = DESK_THRESHOLDS
    price = snapshot.get("price")
    entry = record.get("original_entry")
    stop = record.get("original_stop_loss")
    if price is None or entry is None:
        return False
    low = record.get("buy_zone_low") or entry * 0.98
    high = record.get("buy_zone_high") or entry * 1.02
    in_zone = low <= price <= high
    # "Triggered" (price at/above entry — a breakout confirmation) must still
    # be capped at the max entry price / buy zone high. Without a ceiling, a
    # stock that gapped far past its entry (e.g. entry 100, price now 200)
    # would stay "triggered" forever and keep showing BUY long after the
    # setup is no longer chaseable — see validate_recommendation/determine_fill.
    ceiling = record.get("max_entry_price") or high
    triggered = entry <= price <= ceiling
    if not (in_zone or triggered):
        return False
    ema20 = snapshot.get("ema20") or 0
    ema50 = snapshot.get("ema50") or 0
    trend_valid = (ema20 > 0 and price > ema20) or (
        ema50 > 0 and price > ema50 and snapshot.get("trend") == "Up")
    if not trend_valid:
        return False
    rr = _desk_parse_rr(snapshot.get("risk_reward"))
    vol = snapshot.get("volume_ratio") or 0
    if vol < th["ready_min_volume_ratio"]:
        return False
    # v4 picks carry no take-profit, so risk_reward is None (rr == 0):
    # the RR gates only apply to legacy snapshots that still have one.
    if rr > 0 and rr < th["min_rr_keep"]:
        return False
    if not stop or stop <= 0:
        return False
    if days >= th["strong_confirm_day"]:
        grade = snapshot.get("grade", "")
        strong = ((rr == 0 or rr >= th["strong_min_rr"])
                  and vol >= th["strong_min_volume_ratio"]
                  and grade in ("A+", "A"))
        if not strong:
            return False
    return True


def _desk_classify(record: dict, snapshot: dict | None, days: int) -> str:
    """Re-classify a tracked stock into a desk action (mirrors classifyTracked)."""
    th = DESK_THRESHOLDS
    entered = record.get("entered") is True
    if snapshot is None:
        if not entered and days >= th["max_tracking_days"]:
            return "EXPIRED"
        return record.get("tracking_status", "WAIT")

    price = snapshot.get("price")
    score = snapshot.get("score", 0)
    grade = snapshot.get("grade", "")
    ema20 = snapshot.get("ema20") or 0
    ema50 = snapshot.get("ema50") or 0
    rr = _desk_parse_rr(snapshot.get("risk_reward"))
    orig_score = record.get("original_score", 0)
    orig_stop = record.get("original_stop_loss") or 0
    trend_broke = (price is not None and ema20 > 0 and ema50 > 0
                   and price < ema20 and price < ema50)

    if entered:
        if price is not None and orig_stop > 0 and price <= orig_stop:
            return "EXIT"
        if trend_broke:
            return "EXIT"
        # The v4 exit is a hard price stop, but a live position shouldn't sit on
        # HOLD once the system's own re-scan says the thesis is gone: a sharp
        # score collapse or a flip to grade "Avoid" both mean the setup that
        # justified the entry no longer exists, even if price hasn't tripped
        # the ATR stop yet.
        if orig_score - score >= th["score_drop_remove"]:
            return "EXIT"
        if grade == "Avoid":
            return "EXIT"
        return "HOLD"

    if days >= th["max_tracking_days"]:
        return "EXPIRED"
    # A weakened/invalidated non-entered setup is KEPT on the desk and marked
    # AVOID (avoid a new entry) rather than removed — it only leaves on expiry,
    # manual removal, or user archive.
    if price is not None and orig_stop > 0 and price <= orig_stop:
        return "AVOID"
    if trend_broke:
        return "AVOID"
    if rr > 0 and rr < th["min_rr_keep"]:
        return "AVOID"
    if score < th["min_score_keep"]:
        return "AVOID"
    if days > th["entry_wait_days"] and orig_score - score >= th["score_drop_remove"]:
        return "AVOID"
    if grade == "Avoid":
        return "AVOID"
    if _desk_ready_conditions_met(record, snapshot, days):
        return "BUY"
    return "WAIT"


def _desk_setup_status(orig_score: int, cur_score: int, invalid: bool = False) -> str:
    th = DESK_THRESHOLDS
    if invalid:
        return "invalid"
    if cur_score - orig_score >= th["improved_score_gain"]:
        return "improved"
    if orig_score - cur_score >= th["weakened_score_drop"]:
        return "weakened"
    return "same"


def _desk_signals(snapshot: dict) -> tuple[list[str], list[str]]:
    """Human-readable confirmation / failure tags for the details drawer."""
    confirms, fails = [], []
    if snapshot.get("macd_signal") == "Bullish":
        confirms.append("MACD bullish")
    else:
        fails.append("MACD bearish")
    rsi = snapshot.get("rsi", 50) or 50
    if 30 <= rsi <= 55:
        confirms.append(f"RSI {rsi:.0f}")
    elif rsi > 70:
        fails.append(f"RSI overbought {rsi:.0f}")
    elif rsi < 25:
        fails.append(f"RSI broken {rsi:.0f}")
    if snapshot.get("volume_spike"):
        confirms.append("Volume spike")
    trend = snapshot.get("trend")
    if trend == "Up":
        confirms.append("Uptrend (EMA aligned)")
    elif trend == "Down":
        fails.append("Downtrend")
    if (snapshot.get("adx") or 0) > 25:
        confirms.append("Strong ADX")
    bb = snapshot.get("bb_position")
    if bb == "Lower":
        confirms.append("At lower Bollinger")
    elif bb == "Upper":
        fails.append("At upper Bollinger")
    return confirms, fails


def _desk_reason_for_action(status: str) -> str:
    return {
        "BUY": "Setup triggered — in the buy zone with trend and volume confirmation.",
        "READY": "Setup triggered — in the buy zone with trend and volume confirmation.",
        "WAIT": "Waiting for price to reach the buy zone / trigger.",
        "HOLD": "Position open — hold while the thesis stays intact.",
        "EXIT": "Stop, trend, or score/grade broke down — exit the position.",
        "AVOID": "Setup weakened/invalidated — still tracked, but avoid a new entry.",
        "REMOVE": "Setup invalidated — leaving the desk.",
        "EXPIRED": "14-day tracking window elapsed without a trigger.",
    }.get(status, "")


def _desk_final_instruction(status: str, entered: bool) -> str:
    """One short instruction the UI shows at the bottom of each stock."""
    if entered:
        return "Exit the position" if status == "EXIT" else "Hold the position"
    return {
        "BUY": "Enter now — conditions align in the buy zone",
        "WAIT": "Keep watching — wait for the trigger",
        "AVOID": "Avoid new entry — setup weakened",
        "EXIT": "Exit — thesis broken",
        "EXPIRED": "Tracking window over",
    }.get(status, "Keep watching")


def _desk_indicators_from(snapshot: dict) -> dict:
    """Compact indicator block stored on the record / in each history snapshot."""
    return {
        "rsi": snapshot.get("rsi"),
        "macd_signal": snapshot.get("macd_signal"),
        "macd_hist": snapshot.get("macd_hist"),
        "adx": snapshot.get("adx"),
        "volume_ratio": snapshot.get("volume_ratio"),
        "trend": snapshot.get("trend"),
        "ema20": snapshot.get("ema20"),
        "ema50": snapshot.get("ema50"),
        "supports": snapshot.get("supports", []),
        "resistances": snapshot.get("resistances", []),
    }


def _desk_levels_from(snapshot: dict) -> dict:
    return {
        "entry": snapshot.get("entry"),
        "stop_loss": snapshot.get("stop_loss"),
        "target1": snapshot.get("target1"),
        "target2": snapshot.get("target2"),
        "target3": snapshot.get("target3"),
    }


def _desk_what_changed(record: dict, snapshot: dict) -> str:
    """Plain-English summary of what moved since the initial pick."""
    parts = []
    orig_score = int(record.get("original_score", 0))
    cur_score = int(snapshot.get("score", orig_score))
    if cur_score != orig_score:
        parts.append(f"score {orig_score}→{cur_score} ({'+' if cur_score >= orig_score else ''}{cur_score - orig_score})")
    orig_price = record.get("original_price")
    cur_price = snapshot.get("price")
    if orig_price and cur_price:
        pct = (cur_price - orig_price) / orig_price * 100
        parts.append(f"price {'+' if pct >= 0 else ''}{pct:.1f}%")
    orig_ind = record.get("original_indicators", {})
    if orig_ind.get("trend") and snapshot.get("trend") and orig_ind["trend"] != snapshot["trend"]:
        parts.append(f"trend {orig_ind['trend']}→{snapshot['trend']}")
    if orig_ind.get("macd_signal") and snapshot.get("macd_signal") \
            and orig_ind["macd_signal"] != snapshot["macd_signal"]:
        parts.append(f"MACD {orig_ind['macd_signal']}→{snapshot['macd_signal']}")
    return "No material change since the initial pick." if not parts \
        else "Since pick: " + ", ".join(parts) + "."


def _desk_record_from_pick(pick: dict, today: str) -> dict:
    """Build a fresh desk record from a scan pick."""
    score = int(pick.get("score", 0))
    entry = pick.get("entry")
    price = pick.get("price")
    ref = entry if entry is not None else price
    grade = _desk_grade(score)
    rr = pick.get("risk_reward")
    zone_low = round(entry * 0.98, 2) if entry is not None else None
    zone_high = round(entry * 1.02, 2) if entry is not None else None
    setup = pick.get("setup", "")
    reason = f"{setup} · score {score} · R:R {rr or '—'}"
    stop = pick.get("stop_loss")
    invalidation = (f"Close below SL ₹{stop} or trend break (price < EMA20 & EMA50)"
                    if stop else "Trend break (price < EMA20 & EMA50)")
    indicators = _desk_indicators_from(pick)
    now_iso = datetime.now().isoformat(timespec="seconds")
    initial_snapshot = {
        "analyzed_at": now_iso,
        "price": price,
        "score": score,
        "grade": grade,
        "recommendation": "WAIT",
        "setup_status": "same",
        "score_delta": 0,
        "reason": "Initial system selection.",
        "risk_reward": rr,
        "indicators": indicators,
        "levels": _desk_levels_from(pick),
    }
    return {
        "symbol": pick.get("symbol", ""),
        "name": pick.get("name", str(pick.get("symbol", "")).replace(".NS", "")),
        "selected_date": today,
        "selected_at": now_iso,
        "day_batch_label": f"{today} Picks",
        "entered": False,
        "armed": False,
        "tracking_status": "WAIT",
        "setup": setup,
        "reason_selected": reason,
        "invalidation_condition": invalidation,
        # Original (frozen at selection)
        "original_score": score,
        "original_grade": grade,
        "original_price": price,
        "original_entry": ref,
        "suggested_entry": pick.get("suggested_entry", ref),
        "max_entry_price": pick.get("max_entry_price"),
        "signal_date": pick.get("signal_date", today),
        "signal_timestamp": pick.get("signal_timestamp", now_iso),
        "current_price_at_signal": pick.get("current_price_at_signal", price),
        "market_data_timestamp": pick.get("market_data_timestamp", now_iso),
        "original_actionable_status": pick.get("actionable_status"),
        "original_status_reason": pick.get("status_reason", ""),
        "original_stop_loss": stop,
        "original_target1": pick.get("target1"),
        "original_target2": pick.get("target2"),
        "original_target3": pick.get("target3"),
        "original_predicted_gain_pct": pick.get("predicted_gain_pct"),
        "original_indicators": indicators,
        "buy_zone_low": zone_low,
        "buy_zone_high": zone_high,
        "risk_reward": rr,
        # Current (refreshed each reanalyze; seeded from original)
        "current_score": score,
        "current_grade": grade,
        "current_price": price,
        "current_risk_reward": rr,
        "current_entry": ref,
        "current_stop_loss": stop,
        "current_target1": pick.get("target1"),
        "current_target2": pick.get("target2"),
        "current_target3": pick.get("target3"),
        "current_indicators": indicators,
        "setup_status": "same",
        "what_changed": "",
        "confirmation_signals": [],
        "failure_signals": [],
        # Frozen initial snapshot + append-only re-analysis timeline
        "initial_snapshot": initial_snapshot,
        "reanalysis_history": [],
    }


def _desk_apply_snapshot(record: dict, snapshot: dict, days: int) -> str:
    """Refresh a record's current_* fields from a fresh scan snapshot.

    Original selection data is never overwritten. Current fields are refreshed,
    a re-analysis snapshot is appended to the timeline (one per calendar day —
    a same-day re-run replaces that day's entry), and the status is returned.
    """
    snapshot = dict(snapshot)
    snapshot["grade"] = _desk_grade(snapshot.get("score", 0))
    status = _desk_classify(record, snapshot, days)
    confirms, fails = _desk_signals(snapshot)
    orig_stop = record.get("original_stop_loss") or 0
    price = snapshot.get("price")
    # "Invalid" once the setup breaks: stop taken out or trend fully rolled over.
    ema20 = snapshot.get("ema20") or 0
    ema50 = snapshot.get("ema50") or 0
    trend_broke = bool(price is not None and ema20 > 0 and ema50 > 0
                       and price < ema20 and price < ema50)
    invalid = bool(price is not None and orig_stop > 0 and price <= orig_stop) or trend_broke
    cur_score = int(snapshot.get("score", record.get("current_score", 0)))
    record["current_score"] = cur_score
    record["current_grade"] = snapshot["grade"]
    record["current_price"] = price
    record["current_risk_reward"] = snapshot.get("risk_reward")
    record["risk_reward"] = record.get("risk_reward") or snapshot.get("risk_reward")
    record["current_entry"] = snapshot.get("entry", record.get("current_entry"))
    record["current_stop_loss"] = snapshot.get("stop_loss", record.get("current_stop_loss"))
    record["current_target1"] = snapshot.get("target1", record.get("current_target1"))
    record["current_target2"] = snapshot.get("target2", record.get("current_target2"))
    record["current_target3"] = snapshot.get("target3", record.get("current_target3"))
    record["current_indicators"] = _desk_indicators_from(snapshot)
    record["confirmation_signals"] = confirms
    record["failure_signals"] = fails
    setup_status = _desk_setup_status(
        record.get("original_score", 0), cur_score, invalid=invalid)
    record["setup_status"] = setup_status
    record["tracking_status"] = status
    record["what_changed"] = _desk_what_changed(record, snapshot)

    # Append (or replace today's) re-analysis snapshot — append-only timeline.
    entry = {
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "price": price,
        "score": cur_score,
        "grade": snapshot["grade"],
        "recommendation": status,
        "action": status,
        "setup_status": setup_status,
        "score_delta": cur_score - int(record.get("original_score", 0)),
        "reason": _desk_reason_for_action(status),
        "risk_reward": snapshot.get("risk_reward"),
        "indicators": record["current_indicators"],
        "levels": _desk_levels_from(snapshot),
    }
    hist = record.setdefault("reanalysis_history", [])
    today = datetime.now().strftime("%Y-%m-%d")
    if hist and str(hist[-1].get("analyzed_at", ""))[:10] == today:
        hist[-1] = entry  # collapse repeated same-day re-runs to the latest
    else:
        hist.append(entry)
    # Keep at most ~one entry per tracking day plus headroom.
    record["reanalysis_history"] = hist[-20:]
    return status


def desk_reanalyze(user_id: str = "default") -> dict:
    """Re-scan every tracked stock, refresh setups, and run the 14-day lifecycle.

    Weakened/invalidated stocks are KEPT on the desk (marked AVOID/EXIT) so the
    full batch stays visible under its selected date. The only automatic exit is
    14-trading-day expiry; manual removal and user archive are the other two.
    Armed stocks that turn BUY-ready are auto paper-bought.
    """
    data = _load_desk(user_id)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    kept = []
    for record in data.get("records", []):
        days = _trading_days_between(record.get("selected_date", today), now)
        snapshot = None
        try:
            snapshot = _scan_stock(record.get("symbol", ""))
        except Exception as e:
            logger.debug("[Desk] Re-scan failed for %s: %s", record.get("symbol"), e)

        if snapshot:
            status = _desk_apply_snapshot(record, snapshot, days)
        else:
            status = _desk_classify(record, None, days)
            record["tracking_status"] = status

        # Auto-buy an armed stock the moment it becomes BUY-ready. _desk_execute_buy
        # re-fetches a fresh price and validates it itself — only mark entered
        # when it actually filled, not merely attempted (see its own docstring).
        if status == "BUY" and record.get("armed") and not record.get("entered"):
            try:
                buy_result = _desk_execute_buy(record, 0, user_id)
                if buy_result.get("status") == "bought":
                    record["entered"] = True
                    record["tracking_status"] = "HOLD"
                    status = "HOLD"
                else:
                    logger.debug("[Desk] Armed auto-buy deferred for %s: %s",
                                 record.get("symbol"), buy_result.get("error"))
            except Exception as e:
                logger.debug("[Desk] Auto-buy failed for %s: %s", record.get("symbol"), e)

        # Lifecycle: ONLY 14-day expiry auto-archives a non-entered stock.
        # Weakened/invalid stocks stay visible (AVOID/EXIT) under their date.
        if not record.get("entered") and status == "EXPIRED":
            # Retain the full performance snapshot (not just symbol/date) so
            # expired picks remain usable for model evaluation — did
            # prediction_confidence / predicted_gain_pct actually track
            # realized profit over the 14-day window?
            orig_price = record.get("original_price")
            final_price = record.get("current_price")
            actual_profit_pct = None
            if orig_price and final_price:
                actual_profit_pct = round((final_price - orig_price) / orig_price * 100, 2)
            data.setdefault("history", []).append({
                "symbol": record.get("symbol"),
                "name": record.get("name"),
                "selected_date": record.get("selected_date"),
                "removed_date": today,
                "removal_reason": "Expired — 14 trading days elapsed",
                "setup": record.get("setup"),
                "original_price": orig_price,
                "final_price": final_price,
                "prediction_confidence": record.get("original_score"),
                "final_score": record.get("current_score"),
                "predicted_gain_pct": record.get("original_predicted_gain_pct"),
                "actual_profit_pct": actual_profit_pct,
                "day_snapshots": _day_snapshots_from_history(record, now),
                "entered": False,
            })
        else:
            kept.append(record)

    data["records"] = kept
    data["last_reanalyze_date"] = today
    # Cap history length so the file stays small.
    data["history"] = data.get("history", [])[-50:]
    _save_desk(data, user_id)
    return data


DAY_SNAPSHOT_TARGETS = (1, 3, 7, 14)


def _day_snapshots_from_history(record: dict, now: datetime | None = None) -> dict:
    """Day 1/3/7/14 performance ladder derived from the record's own
    reanalysis_history (already-collected re-scan snapshots) — no new market
    fetch, just a plain-language read of data already gathered daily.

    Two rules keep the ladder honest:

    * A target is reported ONLY once tracking has actually reached that trading
      day. A day-4 pick fills Day 1/3 and leaves Day 7/14 empty, instead of
      repeating today's number under every future column (which made every
      column look "already measured" and a same-day pick read as a flat
      +0.0% across all four).
    * Within a reached target, the latest snapshot at-or-before that day that
      carries a usable price wins. One failed re-scan (price=None) therefore
      no longer blanks a column that earlier days can answer.
    """
    sel_date = record.get("selected_date")
    orig_price = record.get("original_price")
    hist = record.get("reanalysis_history") or []
    days_in = _trading_days_between(sel_date or "", now or datetime.now())
    dated = []
    for h in hist:
        analyzed_at = h.get("analyzed_at")
        if not analyzed_at or not sel_date:
            continue
        try:
            d = datetime.fromisoformat(analyzed_at)
        except Exception:
            continue
        dated.append((_trading_days_between(sel_date, d), h))
    dated.sort(key=lambda x: x[0])

    out = {}
    for target in DAY_SNAPSHOT_TARGETS:
        if days_in < target:
            break  # not reached yet — leave it blank rather than echoing today
        candidates = [h for (d, h) in dated if d <= target]
        if not candidates:
            continue
        priced = [h for h in candidates if h.get("price") is not None]
        h = priced[-1] if priced else candidates[-1]
        h_price = h.get("price")
        pct = None
        if orig_price and h_price:
            pct = round((h_price - orig_price) / orig_price * 100, 2)
        out[str(target)] = {"score": h.get("score"), "price": h_price, "profit_pct": pct}
    return out


def _desk_stock_view(record: dict, now: datetime) -> dict:
    """Assemble the per-stock dict the desk UI renders."""
    th = DESK_THRESHOLDS
    days_in = _trading_days_between(record.get("selected_date", ""), now)
    days_left = max(0, th["max_tracking_days"] - days_in)
    orig_score = int(record.get("original_score", 0))
    cur_score = int(record.get("current_score", orig_score))
    orig_price = record.get("original_price") or record.get("original_entry")
    cur_price = record.get("current_price")
    price_change_pct = None
    if orig_price and cur_price:
        price_change_pct = round((cur_price - orig_price) / orig_price * 100, 2)
    status = record.get("tracking_status", "WAIT")
    entered = record.get("entered", False)
    orig_ind = record.get("original_indicators", {})
    cur_ind = record.get("current_indicators", {}) or orig_ind
    return {
        "symbol": record.get("symbol"),
        "name": record.get("name"),
        "tracking_status": status,
        "current_recommendation": status,
        "original_recommendation": record.get("initial_snapshot", {}).get("recommendation", "WAIT"),
        "setup_status": record.get("setup_status", "same"),
        "entered": entered,
        "armed": record.get("armed", False),
        "days_in_tracking": days_in,
        "tracking_day": days_in,  # 1-14, alias for the Focus Dashboard column
        "days_remaining": days_left,
        "selected_at": record.get("selected_at"),
        "original_score": orig_score,
        "current_score": cur_score,
        "score_change": cur_score - orig_score,
        "prediction_confidence": orig_score,  # confidence at selection time
        "predicted_gain_pct": record.get("original_predicted_gain_pct"),
        "day_snapshots": _day_snapshots_from_history(record, now),
        "original_grade": record.get("original_grade"),
        "current_grade": record.get("current_grade", record.get("original_grade")),
        "original_price": orig_price,
        "current_price": cur_price,
        "price_change_pct": price_change_pct,
        "original_entry": record.get("original_entry"),
        "current_entry": record.get("current_entry", record.get("original_entry")),
        "suggested_entry": record.get("suggested_entry", record.get("original_entry")),
        "max_entry_price": record.get("max_entry_price"),
        "buy_zone_low": record.get("buy_zone_low"),
        "buy_zone_high": record.get("buy_zone_high"),
        "signal_date": record.get("signal_date", record.get("selected_date")),
        "signal_timestamp": record.get("signal_timestamp", record.get("selected_at")),
        "current_price_at_signal": record.get("current_price_at_signal", orig_price),
        "market_data_timestamp": record.get("market_data_timestamp"),
        "original_actionable_status": record.get("original_actionable_status"),
        "original_status_reason": record.get("original_status_reason", ""),
        "original_stop_loss": record.get("original_stop_loss"),
        "current_stop_loss": record.get("current_stop_loss", record.get("original_stop_loss")),
        "original_target1": record.get("original_target1"),
        "original_target2": record.get("original_target2"),
        "current_target1": record.get("current_target1", record.get("original_target1")),
        "current_target2": record.get("current_target2", record.get("original_target2")),
        "risk_reward": record.get("current_risk_reward") or record.get("risk_reward"),
        "original_risk_reward": record.get("risk_reward"),
        # Live indicators (current) + what they were at the pick
        "rsi": cur_ind.get("rsi"),
        "macd_signal": cur_ind.get("macd_signal"),
        "macd_hist": cur_ind.get("macd_hist"),
        "adx": cur_ind.get("adx"),
        "volume_ratio": cur_ind.get("volume_ratio"),
        "trend": cur_ind.get("trend"),
        "ema20": cur_ind.get("ema20"),
        "ema50": cur_ind.get("ema50"),
        "supports": cur_ind.get("supports", []),
        "resistances": cur_ind.get("resistances", []),
        "original_indicators": orig_ind,
        "current_indicators": cur_ind,
        "confirmation_signals": record.get("confirmation_signals", []),
        "failure_signals": record.get("failure_signals", []),
        "reason_for_action": _desk_reason_for_action(status),
        "reason_selected": record.get("reason_selected", ""),
        "what_changed": record.get("what_changed", ""),
        "final_instruction": _desk_final_instruction(status, entered),
        "invalidation_condition": record.get("invalidation_condition"),
        "selected_date": record.get("selected_date"),
        "day_batch_label": record.get("day_batch_label"),
        # Timeline for the details drawer
        "initial_snapshot": record.get("initial_snapshot"),
        "reanalysis_history": record.get("reanalysis_history", []),
        "latest_reanalysis": (record.get("reanalysis_history") or [None])[-1],
    }


def desk_list(reanalyze: bool = False, user_id: str = "default") -> dict:
    """Return the full desk (batches + history + summary).

    Auto-reanalyzes on a new day, or on demand when reanalyze=True.
    """
    data = _load_desk(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    if reanalyze or data.get("last_reanalyze_date") != today:
        if data.get("records"):
            data = desk_reanalyze(user_id)
        else:
            data["last_reanalyze_date"] = today
            _save_desk(data, user_id)

    now = datetime.now()
    records = data.get("records", [])
    stocks = [_desk_stock_view(r, now) for r in records]

    # Group into "YYYY-MM-DD Picks" batches, newest selected date first.
    groups: dict[str, dict] = {}
    for s in stocks:
        label = s.get("day_batch_label") or f"{s.get('selected_date')} Picks"
        g = groups.setdefault(label, {
            "batch_label": label,
            "selected_date": s.get("selected_date"),
            "stocks": [],
        })
        g["stocks"].append(s)
    batches = sorted(groups.values(),
                     key=lambda b: str(b.get("selected_date") or ""), reverse=True)

    ready = [s for s in stocks if s["tracking_status"] == "BUY"]
    ready_count = len(ready)
    active_count = len(stocks)

    if ready_count > 0:
        names = ", ".join(s["symbol"].replace(".NS", "") for s in ready[:3])
        best_action = f"{ready_count} stock(s) ready to BUY: {names}"
    elif active_count > 0:
        best_action = "Nothing ready to buy yet — wait for a tracked setup to trigger."
    else:
        best_action = ("Run Today's Picks, then Auto-select to start a 14-day "
                       "tracked watchlist.")

    summary = {
        "best_action_today": best_action,
        "how_it_works": ("AI auto-selects the best few picks each day (max 5) and "
                         "tracks them for 14 trading days. Stocks stay under their "
                         "date even when a setup weakens — you choose what to paper "
                         "trade; nothing buys unless you arm a stock and it turns BUY."),
        "risk_warning": ("Paper trading only. BUY means the conditions align today "
                         "— always confirm volume and your own risk limits before entering."),
        "disclaimer": PREDICTION_DISCLAIMER,
    }

    # Scrub NaN/Inf so the response is strict-JSON serializable — also cleans
    # any non-finite values that a pre-fix scan may have persisted in the file.
    return _json_safe({
        "desk_date": today,
        "ready_count": ready_count,
        "active_count": active_count,
        "batches": batches,
        "history": list(reversed(data.get("history", []))),
        "summary": summary,
        "thresholds": DESK_THRESHOLDS,
    })


def desk_auto_select(picks: list[dict], user_id: str = "default") -> dict:
    """Select the best of today's picks into the desk (max 5/day, deduped)."""
    th = DESK_THRESHOLDS
    data = _load_desk(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    tracked = {r.get("symbol") for r in data.get("records", [])}
    already_today = sum(1 for r in data.get("records", [])
                        if r.get("selected_date") == today)

    # Quality gate: keep the setup only if score and R:R clear the keep bar.
    eligible = []
    for p in picks or []:
        if p.get("symbol") in tracked:
            continue
        if int(p.get("score", 0)) < th["min_score_keep"]:
            continue
        rr = _desk_parse_rr(p.get("risk_reward"))
        if rr and rr < th["min_rr_keep"]:
            continue
        # Never track a setup price has already overtaken (gapped past the
        # buy zone, target already reached, broken/stale signal) — reject it
        # rather than tracking it at a re-priced level. See validate_recommendation.
        if p.get("actionable_status") in NON_ACTIONABLE_STATUSES:
            continue
        eligible.append(p)

    eligible.sort(key=lambda p: int(p.get("score", 0)), reverse=True)
    slots = max(0, DESK_MAX_PER_DAY - already_today)
    chosen = eligible[:slots]

    for p in chosen:
        data["records"].append(_desk_record_from_pick(p, today))
    if chosen:
        _save_desk(data, user_id)

    return {
        "status": "ok",
        "selected_count": len(chosen),
        "selected": [p.get("symbol") for p in chosen],
        "active_count": len(data.get("records", [])),
    }


def desk_backfill_from_history(user_id: str = "default", max_days: int = None,
                               force: bool = False) -> dict:
    """Admit prior days' saved picks into the desk under their ORIGINAL date so the
    desk shows the full rolling window, not just today.

    Runs once per desk (guarded by a persisted ``backfill_done`` flag) unless
    ``force`` is set. Dedups by symbol against both the current desk and the
    removed-history so an explicitly removed/expired stock is never re-added.
    Skips dates outside the 14-trading-day window and processes oldest→newest,
    so a recurring stock is attributed to the earliest day it was picked. Applies
    the same score/R:R gate and max-5/day cap as the daily auto-select.
    """
    th = DESK_THRESHOLDS
    max_days = max_days or th["max_tracking_days"]
    data = _load_desk(user_id)

    if data.get("backfill_done") and not force:
        return {"status": "skipped", "reason": "already backfilled",
                "active_count": len(data.get("records", []))}

    store = _load_picks_store(user_id)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    # Never re-add a stock the user removed or that expired out of the desk.
    removed = {h.get("symbol") for h in data.get("history", [])}

    added = {}
    for date in sorted(store.get("dates", {}).keys()):
        if date > today:
            continue
        # Skip dates that fall outside the rolling window (would be pruned anyway).
        if _trading_days_between(date, now) > max_days:
            continue
        entry = store["dates"][date]
        picks = entry.get("picks") if isinstance(entry, dict) else None
        if not isinstance(picks, list):
            continue

        tracked = {r.get("symbol") for r in data.get("records", [])}
        already = sum(1 for r in data.get("records", []) if r.get("selected_date") == date)
        slots = max(0, DESK_MAX_PER_DAY - already)
        if slots <= 0:
            continue

        eligible = []
        for p in picks:
            if p.get("symbol") in tracked or p.get("symbol") in removed:
                continue
            if int(p.get("score", 0)) < th["min_score_keep"]:
                continue
            rr = _desk_parse_rr(p.get("risk_reward"))
            if rr and rr < th["min_rr_keep"]:
                continue
            if p.get("actionable_status") in NON_ACTIONABLE_STATUSES:
                continue
            eligible.append(p)
        eligible.sort(key=lambda p: int(p.get("score", 0)), reverse=True)
        chosen = eligible[:slots]

        created_at = (entry.get("created_at") if isinstance(entry, dict) else None) or f"{date}T00:00:00"
        for p in chosen:
            rec = _desk_record_from_pick(p, date)
            # Stamp with the historical date rather than "now".
            rec["selected_at"] = created_at
            rec["initial_snapshot"]["analyzed_at"] = created_at
            data["records"].append(rec)
        if chosen:
            added[date] = [p.get("symbol") for p in chosen]

    data["backfill_done"] = True
    _save_desk(data, user_id)  # persist the flag even when nothing was added

    return {
        "status": "ok",
        "backfilled": added,
        "days_added": len(added),
        "records_added": sum(len(v) for v in added.values()),
        "active_count": len(data.get("records", [])),
    }


# ── Focus ladder: 3 entry positions per stock + level-hit tracking ──
# P1 = the scanner's own trigger (breakout/bounce), P2 = pullback to EMA20,
# P3 = deep pullback to the nearest support below. Each gets its own ATR-based
# SL and T1/T2/T3 (+2/+3/+4 ATR from its trigger) so a user who misses P1 knows
# exactly where the second and third chances are.

_focus_ohlc_cache: dict[str, tuple[float, tuple]] = {}
_FOCUS_OHLC_TTL = 300  # hit-tracking candles refresh every 5 min; LTP every call


def _focus_window(symbol: str, k: int) -> tuple[list, list]:
    """Highs/lows of the last k trading days (cached ~5 min). Empty when k=0."""
    if k <= 0:
        return [], []
    now_ts = time.time()
    cached = _focus_ohlc_cache.get(symbol)
    if cached is None or now_ts - cached[0] > _FOCUS_OHLC_TTL:
        # Yahoo directly (not Kite) — thread-safe for the parallel prefetch,
        # and daily candles are all that hit-tracking needs.
        data = _fetch_ohlcv_yahoo(symbol, "3mo")
        if data is None:
            _focus_ohlc_cache[symbol] = (now_ts, ([], []))
        else:
            _focus_ohlc_cache[symbol] = (
                now_ts, (list(data["highs"]), list(data["lows"])))
    highs, lows = _focus_ohlc_cache[symbol][1]
    return highs[-k:], lows[-k:]


def _focus_position(label: str, trigger: float, atr: float, ltp: float | None,
                    highs: list, lows: list, breakout: bool, condition: str,
                    sl: float = None, t1: float = None, t2: float = None,
                    t3: float = None, filled_price: float = None) -> dict:
    """One entry position: levels, trigger/hit state, live P/L from trigger."""
    trigger = round(float(trigger), 2)
    # v4: stop is 2.5×ATR (close-checked). T1/T2/T3 here are informational
    # milestones for hit-tracking, NOT exit targets — v4 has no take-profit.
    sl = round(sl if sl is not None else trigger - 2.5 * atr, 2)
    t1 = round(t1 if t1 is not None else trigger + 2 * atr, 2)
    t2 = round(t2 if t2 is not None else trigger + 3 * atr, 2)
    t3 = round(t3 if t3 is not None else trigger + 4 * atr, 2)
    zone_lo, zone_hi = round(trigger * 0.99, 2), round(trigger * 1.01, 2)

    # Find the bar where the trigger was first touched — level hits only count
    # FROM that bar onward (a low before the trigger fired is not a stop-out).
    ti = None
    if filled_price is not None:
        ti = 0  # entered on selection day; whole window counts
    else:
        for i in range(len(highs)):
            if (breakout and highs[i] >= trigger) or (not breakout and lows[i] <= trigger):
                ti = i
                break
    live_trig = ltp is not None and (ltp >= trigger if breakout else ltp <= trigger)
    triggered = ti is not None or live_trig
    # Targets may count from the trigger bar itself; the SL only counts from the
    # NEXT bar (or the live tick). A same-bar low usually happened before the
    # upward trigger cross — daily candles can't order intraday moves, and an
    # entry taken NOW at the trigger has a fresh, untouched stop either way.
    post_h = highs[ti:] if ti is not None else []
    post_l = lows[ti + 1:] if ti is not None else []
    hi = max(post_h) if post_h else None
    lo = min(post_l) if post_l else None

    sl_hit = triggered and ((lo is not None and lo <= sl) or (ltp is not None and ltp <= sl))
    t1_hit = triggered and not sl_hit and ((hi is not None and hi >= t1) or (ltp is not None and ltp >= t1))
    t2_hit = t1_hit and ((hi is not None and hi >= t2) or (ltp is not None and ltp >= t2))
    t3_hit = t2_hit and ((hi is not None and hi >= t3) or (ltp is not None and ltp >= t3))

    fill = filled_price if filled_price is not None else trigger
    pl_abs = round(ltp - fill, 2) if (triggered and ltp is not None) else None
    pl_pct = round((ltp - fill) / fill * 100, 2) if (triggered and ltp is not None and fill) else None

    in_zone = ltp is not None and zone_lo <= ltp <= zone_hi
    if filled_price is not None:
        state = "FILLED"
    elif sl_hit:
        state = "SL_HIT"
    elif t3_hit:
        state = "T3_DONE"
    elif t2_hit:
        state = "T2_DONE"
    elif t1_hit:
        state = "T1_DONE"
    elif triggered and in_zone:
        state = "BUYABLE"       # triggered and price is still in the zone
    elif triggered:
        state = "MISSED"        # triggered but price ran out of the zone
    elif in_zone:
        state = "IN_ZONE"       # at the trigger right now
    else:
        state = "WAITING"

    dist_pct = round((trigger - ltp) / ltp * 100, 2) if ltp else None
    return {
        "position": label,
        "trigger": trigger,
        "buy_zone_low": zone_lo,
        "buy_zone_high": zone_hi,
        "stop_loss": sl,
        "target1": t1,
        "target2": t2,
        "target3": t3,
        "condition": condition,
        "state": state,
        "triggered": bool(triggered),
        "in_zone": bool(in_zone),
        "distance_to_trigger_pct": dist_pct,
        "hits": {"sl": bool(sl_hit), "t1": bool(t1_hit),
                 "t2": bool(t2_hit), "t3": bool(t3_hit)},
        "fill_price": round(float(fill), 2) if triggered else None,
        "pl_abs": pl_abs,
        "pl_pct": pl_pct,
    }


def _build_positions(r: dict, ltp: float | None, highs: list, lows: list) -> list[dict]:
    """Build the 3-position entry ladder for one desk record."""
    entry = r.get("current_entry") or r.get("original_entry")
    sl = r.get("current_stop_loss") or r.get("original_stop_loss")
    t1 = r.get("current_target1") or r.get("original_target1")
    t2 = r.get("current_target2") or r.get("original_target2")
    t3 = r.get("current_target3") or r.get("original_target3")
    if entry is None:
        return []
    # ATR back-derived from the plan (T1 = entry + 2·ATR); T3 fallback +4·ATR.
    atr = (t1 - entry) / 2 if (t1 and t1 > entry) else (ltp or entry) * 0.02
    if t3 is None and t2:
        t3 = round(t2 + atr, 2)

    ind = r.get("current_indicators") or r.get("original_indicators") or {}
    ema20 = ind.get("ema20") or 0
    ema50 = ind.get("ema50") or 0
    supports = [s for s in (ind.get("supports") or []) if isinstance(s, (int, float))]

    sel_price = r.get("original_price") or entry
    breakout = entry > sel_price * 1.001
    filled = (r.get("original_entry") if r.get("entered") is True else None)

    positions = [_focus_position(
        "P1", entry, atr, ltp, highs, lows, breakout,
        (f"Price crosses ₹{entry} → buy immediately" if breakout
         else f"Dip to ₹{entry} (setup trigger) and it holds → buy"),
        sl=sl, t1=t1, t2=t2, t3=t3, filled_price=filled)]

    # P2 — pullback to EMA20, only if meaningfully below P1's trigger.
    if ema20 > 0 and ema20 < entry * 0.995:
        positions.append(_focus_position(
            "P2", ema20, atr, ltp, highs, lows, False,
            f"Missed P1? Wait for a pullback to EMA20 ₹{round(ema20, 2)} that holds"))

    # P3 — deep pullback: nearest support (else EMA50) below P2/P1.
    p2_trigger = positions[-1]["trigger"]
    deep_candidates = [s for s in supports if s < p2_trigger * 0.995]
    deep = max(deep_candidates) if deep_candidates else (
        ema50 if 0 < ema50 < p2_trigger * 0.995 else None)
    if deep:
        positions.append(_focus_position(
            "P3", deep, atr, ltp, highs, lows, False,
            f"Deep pullback to support ₹{round(deep, 2)} — enter only if it closes above"))

    return positions


# ── Focus view: "what do I act on right now?" ──
# Priority order answers the user's question directly: protect capital first
# (exits), then triggered entries, then near-trigger watches, then open
# positions to monitor, then tomorrow's checks. AVOID/EXPIRED are ignored.
FOCUS_BUCKET_ORDER = ["EXIT_NOW", "BUY_NOW", "WATCH_TODAY", "HOLD", "CHECK_TOMORROW"]

FOCUS_ACTION_TEXT = {
    "EXIT_NOW": "Exit this position now — stop or trend is broken.",
    "BUY_NOW": "Price is at the trigger — enter now with the stop in place.",
    "WATCH_TODAY": "Within striking distance — watch for the trigger today.",
    "HOLD": "Position open and healthy — monitor the stop, do nothing.",
    "CHECK_TOMORROW": "Valid setup, still far from trigger — re-check tomorrow.",
}

FOCUS_VERDICT_TEXT = {
    "SELL_EXIT": "SELL / EXIT — stop or trend broken",
    "HOLD": "HOLD — position open, monitor the stop",
    "ENTER_NOW": "ENTER NOW — price is at a position trigger",
    "MISSED_P1": "MISSED P1 — wait for the Position 2 pullback",
    "WAIT": "WAIT — no trigger touched yet",
    "NO_ENTRY": "NO ENTRY — setup invalid or stop already hit",
}


def desk_focus(user_id: str = "default") -> dict:
    """Rank the desk into action buckets with LIVE prices (Kite → Yahoo batch).

    Returns one #1 `focus` item plus every active record bucketed by urgency,
    so the user always knows the single next action instead of scanning 5+/day.
    """
    data = _load_desk(user_id)
    records = data.get("records", [])
    now = datetime.now()
    syms = [r.get("symbol") for r in records if r.get("symbol")]
    ltp_map = _batch_ltp(syms) if syms else {}
    live_count = sum(1 for s in syms if s in ltp_map)

    # Warm the hit-tracking candle cache in parallel (Yahoo, thread-safe) so a
    # cold call doesn't pay ~16 sequential fetches; cached calls skip this.
    stale = [s for s in dict.fromkeys(syms)
             if (c := _focus_ohlc_cache.get(s)) is None
             or time.time() - c[0] > _FOCUS_OHLC_TTL]
    if stale:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(lambda s: _focus_window(s, 1), stale))

    buckets = {k: [] for k in FOCUS_BUCKET_ORDER}
    ignored = []
    for r in records:
        sym = r.get("symbol", "")
        status = r.get("tracking_status", "WAIT")
        entered = r.get("entered") is True
        ltp = ltp_map.get(sym) or r.get("current_price") or r.get("original_price")
        entry = r.get("current_entry") or r.get("original_entry")
        sl = r.get("current_stop_loss") or r.get("original_stop_loss")
        t1 = r.get("current_target1") or r.get("original_target1")
        score = r.get("current_score", r.get("original_score", 0)) or 0
        rr = _desk_parse_rr(r.get("current_risk_reward") or r.get("risk_reward"))
        days_in = _trading_days_between(r.get("selected_date", ""), now)

        # % move still needed to reach the entry trigger (+ = above, − = below)
        dist_pct = (round((entry - ltp) / ltp * 100, 2)
                    if (entry and ltp) else None)
        in_zone = bool(r.get("buy_zone_low") and r.get("buy_zone_high") and ltp
                       and r["buy_zone_low"] <= ltp <= r["buy_zone_high"])
        sl_dist_pct = (round((ltp - sl) / ltp * 100, 2) if (sl and ltp) else None)
        invalid = r.get("setup_status") == "invalid" or status in ("AVOID", "EXPIRED", "REMOVE")

        if entered and status == "EXIT":
            bucket = "EXIT_NOW"
        elif entered:
            bucket = "HOLD"
        elif invalid:
            bucket = None  # tracked but not actionable
        elif status in ("BUY", "READY", "BUY_NOW") or in_zone:
            bucket = "BUY_NOW"
        elif dist_pct is not None and abs(dist_pct) <= 2.0:
            bucket = "WATCH_TODAY"
        else:
            bucket = "CHECK_TOMORROW"

        # 3-position entry ladder + level-hit tracking since selection.
        w_highs, w_lows = _focus_window(sym, min(days_in, 20))
        positions = _build_positions(r, ltp, w_highs, w_lows)
        p1 = positions[0] if positions else {}
        if entered and status == "EXIT":
            verdict = "SELL_EXIT"
        elif entered:
            verdict = "HOLD"
        elif invalid or (p1.get("hits") or {}).get("sl"):
            verdict = "NO_ENTRY"
        elif any(p["state"] in ("IN_ZONE", "BUYABLE") for p in positions):
            verdict = "ENTER_NOW"
        elif p1.get("state") in ("MISSED", "T1_DONE", "T2_DONE", "T3_DONE"):
            verdict = "MISSED_P1"
        else:
            verdict = "WAIT"

        item = {
            "symbol": sym,
            "name": r.get("name", sym.replace(".NS", "")),
            "bucket": bucket or "AVOID",
            "action": FOCUS_ACTION_TEXT.get(bucket, "Setup invalid — no action."),
            "tracking_status": status,
            "entered": entered,
            "ltp": round(float(ltp), 2) if ltp else None,
            "live": sym in ltp_map,
            "entry": entry,
            "stop_loss": sl,
            "target1": t1,
            "target2": r.get("current_target2") or r.get("original_target2"),
            "target3": (p1.get("target3")
                        or r.get("current_target3") or r.get("original_target3")),
            "positions": positions,
            "verdict": verdict,
            "verdict_text": FOCUS_VERDICT_TEXT.get(verdict, ""),
            "distance_to_entry_pct": dist_pct,
            "sl_distance_pct": sl_dist_pct,
            "in_buy_zone": in_zone,
            "score": score,
            "risk_reward": r.get("current_risk_reward") or r.get("risk_reward"),
            "setup": r.get("setup") or r.get("original_setup_type", ""),
            "selected_date": r.get("selected_date"),
            "days_in": days_in,
            "why": r.get("what_changed") or r.get("reason_selected", ""),
        }
        if bucket is None:
            ignored.append(item)
        else:
            buckets[bucket].append(item)

    # Rank inside each bucket: urgency proxy — score first, then tighter R:R.
    for k in buckets:
        if k == "WATCH_TODAY":
            # closest to trigger first
            buckets[k].sort(key=lambda x: (abs(x["distance_to_entry_pct"] or 99), -x["score"]))
        else:
            buckets[k].sort(key=lambda x: (-x["score"],
                                           -(_desk_parse_rr(x.get("risk_reward")) or 0)))

    focus = next((buckets[k][0] for k in FOCUS_BUCKET_ORDER if buckets[k]), None)

    # Flat ranked list (position #1 = most urgent) — actionable stocks first,
    # then the not-actionable (NO_ENTRY) ones so the table still shows them.
    stocks = [it for k in FOCUS_BUCKET_ORDER for it in buckets[k]] + ignored
    for i, it in enumerate(stocks, 1):
        it["rank"] = i

    return _json_safe({
        "focus": focus,
        "stocks": stocks,
        "buckets": buckets,
        "ignored": ignored,
        "counts": {k: len(v) for k, v in buckets.items()},
        "live_prices": live_count,
        "total_symbols": len(syms),
        "price_source": ("Kite MCP" if _is_kite_connected() and live_count else
                         "Yahoo Finance" if live_count else "cached"),
        "updated_at": now.isoformat(timespec="seconds"),
    })


def _desk_find(data: dict, symbol: str) -> dict | None:
    for r in data.get("records", []):
        if r.get("symbol") == symbol:
            return r
    return None


def desk_remove(symbol: str, user_id: str = "default") -> dict:
    data = _load_desk(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    rec = _desk_find(data, symbol)
    if rec is None:
        return {"error": f"{symbol} is not on the desk"}
    data["records"] = [r for r in data["records"] if r.get("symbol") != symbol]
    data.setdefault("history", []).append({
        "symbol": symbol,
        "removed_date": today,
        "removal_reason": "Manually removed",
    })
    _save_desk(data, user_id)
    return {"status": "removed", "symbol": symbol}


def desk_archive(symbol: str, user_id: str = "default") -> dict:
    """User-chosen archive: move a stock (e.g. one whose paper trade is closed)
    off the active desk into history. Distinct from lifecycle expiry."""
    data = _load_desk(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    rec = _desk_find(data, symbol)
    if rec is None:
        return {"error": f"{symbol} is not on the desk"}
    data["records"] = [r for r in data["records"] if r.get("symbol") != symbol]
    data.setdefault("history", []).append({
        "symbol": symbol,
        "removed_date": today,
        "removal_reason": "Archived by user",
    })
    _save_desk(data, user_id)
    return {"status": "archived", "symbol": symbol}


def _desk_execute_buy(record: dict, quantity: int, user_id: str) -> dict:
    """Size and place a paper buy for a desk record.

    ALWAYS re-fetches a fresh live price and validates it against the record's
    buy zone / max entry price before filling — never trusts a cached
    current_price or original_entry as the fill (that was the bug: a stale
    desk snapshot could be hours old by the time the user clicks Paper Buy).
    Rejects with an error (no position opened) when the fresh price is
    outside the executable range. Never manufactures a take-profit target —
    only a REAL current/original target is ever passed to paper_buy.
    """
    symbol = record.get("symbol")
    fresh = _fetch_ltp(symbol)
    if fresh is None or fresh <= 0:
        return {"error": f"No fresh price available for {symbol} right now — try again.",
                "status": "DATA_STALE"}

    result = determine_fill(
        buy_zone_low=record.get("buy_zone_low"),
        buy_zone_high=record.get("buy_zone_high"),
        max_entry_price=record.get("max_entry_price"),
        observed_price=fresh,
    )
    if not result["filled"]:
        return {"error": f"{symbol} is not executable at the current price "
                          f"₹{fresh} — {result['reason']}",
                "status": result["status"], "observed_price": fresh}

    fill_price = result["fill_price"]
    qty = quantity
    if qty <= 0:
        paper = _load_paper(user_id)
        alloc = paper.get("cash", 0) * 0.10  # 10% of paper cash per position
        qty = max(1, int(alloc / fill_price))

    suggested = record.get("suggested_entry") or record.get("original_entry")
    stop = (record.get("current_stop_loss") or record.get("original_stop_loss")
            or round(fill_price * 0.97, 2))
    target = record.get("current_target1") or record.get("original_target1")
    # Re-anchor stop/target to the price actually paid — see adjust_levels_for_fill.
    stop, target = adjust_levels_for_fill(suggested, stop, target, fill_price)

    return paper_buy(
        symbol=symbol,
        quantity=qty,
        entry_price=fill_price,
        stop_loss=stop,
        target=target,
        setup=record.get("setup", ""),
        user_id=user_id,
        suggested_entry=suggested,
        signal_timestamp=record.get("signal_timestamp"),
        fill_source="desk_manual",
        fill_reason=result["reason"],
    )


def desk_paper_buy(symbol: str, quantity: int = 0, user_id: str = "default") -> dict:
    """Manual "Paper Buy" from the desk. Rejects (no position opened) when the
    freshly-fetched price is outside the allowed entry range; the caller sees
    the observed price and the reason in the returned error."""
    data = _load_desk(user_id)
    rec = _desk_find(data, symbol)
    if rec is None:
        return {"error": f"{symbol} is not on the desk"}
    if rec.get("entered"):
        return {"error": f"{symbol} already has an open paper position"}
    result = _desk_execute_buy(rec, quantity, user_id)
    if result.get("status") != "bought":
        return result
    rec["entered"] = True
    rec["tracking_status"] = "HOLD"
    _save_desk(data, user_id)
    return {"status": "bought", "symbol": symbol, **result}


def desk_arm(symbol: str, user_id: str = "default") -> dict:
    data = _load_desk(user_id)
    rec = _desk_find(data, symbol)
    if rec is None:
        return {"error": f"{symbol} is not on the desk"}
    rec["armed"] = True
    _save_desk(data, user_id)
    return {"status": "armed", "symbol": symbol}


def desk_disarm(symbol: str, user_id: str = "default") -> dict:
    data = _load_desk(user_id)
    rec = _desk_find(data, symbol)
    if rec is None:
        return {"error": f"{symbol} is not on the desk"}
    rec["armed"] = False
    _save_desk(data, user_id)
    return {"status": "disarmed", "symbol": symbol}


# ══════════════════════════════════════════════════════════════
#  RESET ALL SWING DATA
# ══════════════════════════════════════════════════════════════
def reset_all_swing_data(user_id: str = "default", capital: float = None) -> dict:
    """Clear ALL Swing Trading data for the CURRENT user only, and initialize a
    clean paper account at `capital`.

    Clears: saved daily picks + daily-pick history, the 14-Day Desk (active
    records + history), pending paper entries, open paper positions, closed
    paper trades, the paper equity history, and the missed-entry log. Does
    NOT touch portfolio/mutual-fund/watchlist/login data — those live in
    separate files this function never opens — and (via set_active_data_dir /
    _active_user_dir) only ever touches the currently active user's directory,
    never another user's.

    Returns a summary with a removed-record count per category. Does not
    itself talk to Google Drive — the caller (the API endpoint) triggers the
    existing Drive-sync path after this returns, same as any other save.
    """
    picks_store = _load_picks_store(user_id)
    picks_dates_removed = len(picks_store.get("dates", {}))
    f = _picks_file(user_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w") as fh:
        json.dump({"dates": {}}, fh, indent=2)
    _drive_upload_async(f)

    desk_data = _load_desk(user_id)
    desk_active_removed = len(desk_data.get("records", []))
    desk_history_removed = len(desk_data.get("history", []))
    _save_desk({"records": [], "history": [], "last_reanalyze_date": None,
                "backfill_done": False}, user_id)

    paper_data = _load_paper(user_id)
    pending_removed = len(paper_data.get("pending_entries", []))
    missed_removed = len(paper_data.get("missed_entries", []))
    open_positions_removed = len(paper_data.get("positions", []))
    closed_trades_removed = len(paper_data.get("closed_trades", []))
    equity_points_removed = len(paper_data.get("daily_equity", []))
    reset_result = paper_reset(user_id, capital=capital)

    return {
        "status": "reset",
        "daily_pick_dates_removed": picks_dates_removed,
        "desk_active_records_removed": desk_active_removed,
        "desk_history_records_removed": desk_history_removed,
        "pending_entries_removed": pending_removed,
        "missed_entries_removed": missed_removed,
        "open_positions_removed": open_positions_removed,
        "closed_trades_removed": closed_trades_removed,
        "equity_points_removed": equity_points_removed,
        "capital": reset_result["capital"],
    }
    return {"status": "disarmed", "symbol": symbol}
