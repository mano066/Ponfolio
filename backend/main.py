import json
import os
import asyncio
import threading
from datetime import datetime, date, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Query, Body, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel, Field
import yfinance as yf
import ai_models
from kite_client import kite as kite_client, KITE_MCP_URL
import mf_analysis
import sip_simulator
import google_auth
import swing_trading
import strategies
import dividend_analysis
import market_indices
import deploy_engine
import backtest_engine
import stock_dip
import mf_dip
import conviction
import opportunities
import rebalance_engine
import rebalance_history
import equity_txns
import equity_closed
import kite_pnl_import
import kite_ledger_import
import xlsx_reader
import tradebook_import
import sys
import re
import base64
import uuid
from typing import List, Dict, Optional


def _safe_print(*args, **kwargs):
    """Print wrapper that handles OSError [Errno 22] on Windows.

    Background threads on Windows can lose their stdout handle, causing
    print(..., flush=True) to raise OSError: [Errno 22] Invalid argument.
    """
    kwargs.setdefault("flush", True)
    try:
        print(*args, **kwargs)
    except OSError:
        try:
            sys.stderr.write(str(args[0]) + "\n") if args else None
        except Exception:
            pass

app = FastAPI(title="Ponfolio — Indian Stock & MF Recommender API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class AddStockRequest(BaseModel):
    symbol: str
    shares: int
    avg_cost: float = 0

class WatchlistRequest(BaseModel):
    symbol: str

class PlaceOrderRequest(BaseModel):
    tradingsymbol: str
    exchange: str = "NSE"
    transaction_type: str = "BUY"
    quantity: int = 1
    order_type: str = "MARKET"
    product: str = "CNC"
    price: float = None
    trigger_price: float = None

class PlaceGTTRequest(BaseModel):
    tradingsymbol: str
    exchange: str = "NSE"
    trigger_type: str = "single"  # single or two-leg (OCO)
    last_price: float
    trigger_values: list
    orders: list

POPULAR_INDIAN_STOCKS = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "sector": "Technology"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "sector": "Finance"},
    {"symbol": "INFY.NS", "name": "Infosys", "sector": "Technology"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "sector": "Finance"},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever", "sector": "Consumer"},
    {"symbol": "ITC.NS", "name": "ITC Limited", "sector": "Consumer"},
    {"symbol": "SBIN.NS", "name": "State Bank of India", "sector": "Finance"},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel", "sector": "Telecom"},
    {"symbol": "LT.NS", "name": "Larsen & Toubro", "sector": "Infrastructure"},
    {"symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank", "sector": "Finance"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank", "sector": "Finance"},
    {"symbol": "NTPC.NS", "name": "NTPC", "sector": "Energy"},
    {"symbol": "ULTRACEMCO.NS", "name": "UltraTech Cement", "sector": "Infrastructure"},
    {"symbol": "ASIANPAINT.NS", "name": "Asian Paints", "sector": "Consumer"},
]

# Nifty 50 constituents (NSE symbols with .NS suffix + readable names)
NIFTY50_CONSTITUENTS = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank"},
    {"symbol": "INFY.NS", "name": "Infosys"},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever"},
    {"symbol": "ITC.NS", "name": "ITC Limited"},
    {"symbol": "SBIN.NS", "name": "State Bank of India"},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel"},
    {"symbol": "LT.NS", "name": "Larsen & Toubro"},
    {"symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank"},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance"},
    {"symbol": "BAJAJFINSV.NS", "name": "Bajaj Finserv"},
    {"symbol": "HCLTECH.NS", "name": "HCL Technologies"},
    {"symbol": "WIPRO.NS", "name": "Wipro"},
    {"symbol": "TECHM.NS", "name": "Tech Mahindra"},
    {"symbol": "LTIM.NS", "name": "LTIMindtree"},
    {"symbol": "MARUTI.NS", "name": "Maruti Suzuki"},
    {"symbol": "TATAMOTORS.NS", "name": "Tata Motors"},
    {"symbol": "M&M.NS", "name": "Mahindra & Mahindra"},
    {"symbol": "BAJAJ-AUTO.NS", "name": "Bajaj Auto"},
    {"symbol": "EICHERMOT.NS", "name": "Eicher Motors"},
    {"symbol": "HEROMOTOCO.NS", "name": "Hero MotoCorp"},
    {"symbol": "SUNPHARMA.NS", "name": "Sun Pharmaceutical"},
    {"symbol": "DRREDDY.NS", "name": "Dr. Reddy's Laboratories"},
    {"symbol": "CIPLA.NS", "name": "Cipla"},
    {"symbol": "DIVISLAB.NS", "name": "Divi's Laboratories"},
    {"symbol": "APOLLOHOSP.NS", "name": "Apollo Hospitals"},
    {"symbol": "NESTLEIND.NS", "name": "Nestle India"},
    {"symbol": "BRITANNIA.NS", "name": "Britannia Industries"},
    {"symbol": "TATACONSUM.NS", "name": "Tata Consumer Products"},
    {"symbol": "ASIANPAINT.NS", "name": "Asian Paints"},
    {"symbol": "TITAN.NS", "name": "Titan Company"},
    {"symbol": "ULTRACEMCO.NS", "name": "UltraTech Cement"},
    {"symbol": "GRASIM.NS", "name": "Grasim Industries"},
    {"symbol": "SHREECEM.NS", "name": "Shree Cement"},
    {"symbol": "JSWSTEEL.NS", "name": "JSW Steel"},
    {"symbol": "TATASTEEL.NS", "name": "Tata Steel"},
    {"symbol": "HINDALCO.NS", "name": "Hindalco Industries"},
    {"symbol": "ONGC.NS", "name": "Oil & Natural Gas Corporation"},
    {"symbol": "COALINDIA.NS", "name": "Coal India"},
    {"symbol": "BPCL.NS", "name": "Bharat Petroleum"},
    {"symbol": "NTPC.NS", "name": "NTPC"},
    {"symbol": "POWERGRID.NS", "name": "Power Grid Corporation"},
    {"symbol": "ADANIENT.NS", "name": "Adani Enterprises"},
    {"symbol": "ADANIPORTS.NS", "name": "Adani Ports & SEZ"},
    {"symbol": "HDFCLIFE.NS", "name": "HDFC Life Insurance"},
    {"symbol": "SBILIFE.NS", "name": "SBI Life Insurance"},
    {"symbol": "INDUSINDBK.NS", "name": "IndusInd Bank"},
]

# Module-level cache for Nifty50 constituent quotes: {"ts": float, "data": [...]}
_nifty50_constituents_cache: dict = {"ts": 0.0, "data": []}
_NIFTY50_CACHE_TTL = 300  # 5 minutes

# ══════════════════════════════════════════════════════════════
#  REFRESH CADENCE
# ══════════════════════════════════════════════════════════════
# One hour, round the clock, for everything the dashboard shows.
#
# The caches below split into two groups, and the split is not arbitrary:
#
#   * Anything that CAN change within an hour — index levels, share prices,
#     52-week highs, headlines, fund NAV — refreshes hourly.
#   * Anything whose source is a DAILY bar — the ten-year history, the dip
#     backtest built from it, the split detector — stays at a day. Refetching
#     a decade of daily closes every hour costs ~18 seconds to return numbers
#     that are identical by construction, because no new bar exists until the
#     market closes.
#
# Fund NAV deserves a note. AMFI publishes it once per trading day, after
# close, so an hourly check finds the same number all day. That is not waste:
# it is what makes the evening NAV appear within an hour of publication rather
# than up to twelve hours later, which is what the old 12-hour TTL did.
REFRESH_SECONDS = 3600
DAILY_SECONDS = 24 * 3600

# Module-level cache for the market index tape: {"ts": float, "data": {...}}
# One batched yf.download covers all ~31 indices, so the TTL is what keeps the
# dashboard's poll from turning into 31 Yahoo requests per refresh.
_index_tape_cache: dict = {"ts": 0.0, "data": None}
# Five minutes, matching the client's tape poll. An hour was right when the
# tape was built purely from batched Yahoo history, but the live level and day
# change now come from ONE Kite quotes call covering all 28 instruments, and
# holding those for an hour meant the screen showed an hour-old market. The
# expensive parts are cached separately and independently: Yahoo history for a
# day, Kite candles for a day, instrument tokens for the life of the process.
_INDEX_TAPE_TTL = 300

# Deep daily history, keyed {symbol: (dates, closes)}. Kept separate from the
# tape cache because the two have opposite refresh economics: ten years of
# closes barely change, today's close changes constantly. See
# market_indices.merge_series for why they are spliced rather than one fetch.
_index_history_cache: dict = {"ts": 0.0, "data": None}
_INDEX_HISTORY_TTL = DAILY_SECONDS     # a decade of DAILY bars
_INDEX_HISTORY_PERIOD = "10y"          # powers 200 DMA, full-history high, backtest
_INDEX_RECENT_PERIOD = "5d"            # powers last / prev_close / day change

# Dip-threshold backtest, keyed by symbol. Derived purely from the cached
# history above, so its TTL only needs to outlast a history refresh.
_backtest_cache: dict = {"ts": 0.0, "data": None}
_BACKTEST_TTL = DAILY_SECONDS          # derived from the daily history

# ══════════════════════════════════════════════════════════════
#  Yahoo Finance rate-limit resilient wrapper
# ══════════════════════════════════════════════════════════════
import time as _time
import pandas as _pd
_yf_history_cache: dict = {}  # key -> (timestamp, dataframe)
_YF_CACHE_TTL = {"5d": 600, "1y": 1800, "3mo": 1800}

# yfinance keeps its timezone/cookie caches in SQLite files (via peewee). When
# one of those files breaks ("database disk image is malformed"), waiting and
# retrying never helps — and the sleeps hold server worker threads until even
# /api/status can't be answered, which froze the login screen on 28 Oct 2026.
import sqlite3 as _sqlite3
import tempfile as _tempfile
_yf_cache_lock = threading.Lock()
_yf_cache_dir_fresh: Optional[str] = None

def _is_yf_cache_db_error(e: Exception) -> bool:
    if isinstance(e, _sqlite3.DatabaseError):
        return True
    # peewee's errors don't subclass sqlite3's, so match by name / message.
    return (type(e).__name__ in ("DatabaseError", "OperationalError", "InterfaceError")
            or "database disk image is malformed" in str(e))

def _heal_yf_cache() -> None:
    """Point yfinance at a fresh, empty cache folder for the rest of this run.

    The broken files can't be deleted while this process holds them open on
    Windows, so switch folders instead. Only the first caller switches.
    """
    global _yf_cache_dir_fresh
    with _yf_cache_lock:
        if _yf_cache_dir_fresh:
            return
        try:
            fresh = _tempfile.mkdtemp(prefix="aiei-yf-cache-")
            yf.set_tz_cache_location(fresh)
            # The cache objects are bound to the old DB on first use; drop them
            # so the next lookup builds new ones on the fresh folder.
            from yfinance import cache as _yfc
            for mgr, attr in (("_TzCacheManager", "_tz_cache"),
                              ("_CookieCacheManager", "_Cookie_cache"),
                              ("_ISINCacheManager", "_isin_cache")):
                if hasattr(getattr(_yfc, mgr, None), attr):
                    setattr(getattr(_yfc, mgr), attr, None)
            _yf_cache_dir_fresh = fresh
            print(f"[YF] Cache DB broken — switched yfinance cache to {fresh}")
        except Exception as e:
            print(f"[YF] Could not switch yfinance cache: {e}")

def _safe_yf_history(symbol: str, period: str = "1y", max_retries: int = 3):
    """Fetch ticker history with retry on rate-limit, session reset, and caching."""
    cache_key = f"{symbol}:{period}"
    now = _time.time()
    # Check cache
    if cache_key in _yf_history_cache:
        ts, df = _yf_history_cache[cache_key]
        ttl = _YF_CACHE_TTL.get(period, 1800)
        if now - ts < ttl and not df.empty:
            print(f"[YF Cache] Hit for {symbol} ({period})")
            return df
    last_err = None
    db_retried = False
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            if attempt > 0:
                try:
                    if hasattr(yf, 'shared') and hasattr(yf.shared, '_CACHE'):
                        yf.shared._CACHE = {}
                except: pass
                ticker = yf.Ticker(symbol)
            history = ticker.history(period=period)
            if not history.empty:
                _yf_history_cache[cache_key] = (now, history)
                print(f"[YF] OK {symbol} ({period}) — {len(history)} rows (attempt {attempt+1})")
                return history
            else:
                print(f"[YF] Empty result for {symbol} ({period}) attempt {attempt+1}")
        except Exception as e:
            last_err = e
            err_name = type(e).__name__
            if _is_yf_cache_db_error(e):
                # Retry once, immediately, on a fresh cache; never sleep on these.
                if not db_retried:
                    db_retried = True
                    _heal_yf_cache()
                    continue
                print(f"[YF] {err_name} for {symbol} ({period}) persists on fresh cache — giving up without waiting")
                break
            wait = [5, 15, 30][min(attempt, 2)]
            print(f"[YF] {err_name} for {symbol} ({period}) attempt {attempt+1}/{max_retries} — waiting {wait}s")
            _time.sleep(wait)
    print(f"[YF] FAILED all {max_retries} retries for {symbol}: {last_err}")
    return _pd.DataFrame()

# ─── Persistent Storage ────
import hashlib
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
USERS_DIR = DATA_DIR / "users"
USERS_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

# Per-user data paths (set by _switch_user_data)
_current_user_email = None
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"      # legacy fallback
MF_PORTFOLIO_FILE = DATA_DIR / "mf_portfolio.json" # legacy fallback
MF_HOLDINGS_FILE = DATA_DIR / "mf_holdings.json"   # per-fund stock look-through
WATCHLIST_FILE = DATA_DIR / "watchlist.json"        # legacy fallback
EQUITY_TXNS_FILE = DATA_DIR / "equity_txns.json"    # dated buy/sell ledger for XIRR
# Imported Kite Console P&L statements, keyed by the period each one covers,
# so monthly exports accumulate instead of overwriting or double-counting.
EQUITY_PNL_FILE = DATA_DIR / "equity_pnl.json"
# Imported Console funds ledgers, also keyed by period. The only export that
# carries TDS.
EQUITY_LEDGER_FILE = DATA_DIR / "equity_ledger.json"
# Audit trail of recorded deployments. Read ONLY to answer "have I already
# processed this request_id?" and to serve deploy-history — never to compute SIP
# status, which is derived from real transactions. See deploy_engine's docstring.
DEPLOY_LOG_FILE = DATA_DIR / "deploy_log.json"
# The user's written reasoning per holding — thesis, sell triggers, manual
# quarter verdicts — plus quarterly fundamentals snapshots and the
# discipline settings. See conviction.py.
CONVICTION_FILE = DATA_DIR / "conviction.json"
user_conviction: dict = {}

# scheme_name -> [{stock, pct}] user-supplied fund look-through holdings
user_mf_holdings: dict = {}

# symbol -> [{date, type, qty, price, amount, trade_id}] dated equity ledger.
# Kite hands us holdings without dates, so this is the only source of the
# cashflows an equity XIRR needs. It accumulates across syncs; see equity_txns.
user_equity_txns: dict = {}
# {"2026-08-01..2026-08-31": <statement>} — see kite_pnl_import for why the
# period is the key rather than the import time.
user_equity_pnl: dict = {}
# Console funds ledgers by period. Holds TDS, which no other export carries.
user_equity_ledger: dict = {}

def _user_data_dir(email: str) -> Path:
    """Get per-user data directory based on email."""
    safe_name = hashlib.md5(email.lower().strip().encode()).hexdigest()[:12]
    d = USERS_DIR / safe_name
    d.mkdir(exist_ok=True)
    return d

def _migrate_legacy_data(user_dir: Path):
    """One-time migration: move legacy root data files into the FIRST user's directory, then rename originals."""
    migrated_any = False
    for fname in ["portfolio.json", "mf_portfolio.json", "watchlist.json"]:
        legacy = DATA_DIR / fname
        target = user_dir / fname
        if legacy.exists() and not target.exists():
            import shutil
            shutil.copy2(legacy, target)
            print(f"[Migration] Copied {fname} to user dir {user_dir.name}")
            migrated_any = True
    # After migration, rename legacy files so they won't be copied to future new users
    if migrated_any:
        for fname in ["portfolio.json", "mf_portfolio.json", "watchlist.json"]:
            legacy = DATA_DIR / fname
            if legacy.exists():
                legacy.rename(DATA_DIR / f"{fname}.bak")
                print(f"[Migration] Renamed {fname} -> {fname}.bak")

def _switch_user_data(email: str = None):
    """Switch global data paths and reload data for the given user.
    Pulls newer data from Google Drive so every device stays in sync."""
    global PORTFOLIO_FILE, MF_PORTFOLIO_FILE, WATCHLIST_FILE, SETTINGS_FILE
    global user_portfolio, user_mf_portfolio, user_watchlist, _current_user_email
    global app_settings, MF_HOLDINGS_FILE, user_mf_holdings
    global EQUITY_TXNS_FILE, user_equity_txns
    global EQUITY_PNL_FILE, user_equity_pnl
    global EQUITY_LEDGER_FILE, user_equity_ledger
    global DEPLOY_LOG_FILE, user_deploy_log
    global CONVICTION_FILE, user_conviction

    if email:
        user_dir = _user_data_dir(email)
        # Migrate legacy data for the first authenticated user
        _migrate_legacy_data(user_dir)
        PORTFOLIO_FILE = user_dir / "portfolio.json"
        MF_PORTFOLIO_FILE = user_dir / "mf_portfolio.json"
        MF_HOLDINGS_FILE = user_dir / "mf_holdings.json"
        WATCHLIST_FILE = user_dir / "watchlist.json"
        SETTINGS_FILE = user_dir / "settings.json"
        EQUITY_TXNS_FILE = user_dir / "equity_txns.json"
        EQUITY_PNL_FILE = user_dir / "equity_pnl.json"
        EQUITY_LEDGER_FILE = user_dir / "equity_ledger.json"
        DEPLOY_LOG_FILE = user_dir / "deploy_log.json"
        CONVICTION_FILE = user_dir / "conviction.json"
        _current_user_email = email
        # Migrate a pre-existing global settings.json into the per-user folder
        legacy_settings = DATA_DIR / "settings.json"
        if not SETTINGS_FILE.exists() and legacy_settings.exists():
            try:
                import shutil
                shutil.copy2(legacy_settings, SETTINGS_FILE)
            except Exception as e:
                print(f"[Storage] Settings migration failed: {e}")
        # Swing state (paper, desk, daily picks) follows the user too
        swing_trading.set_active_data_dir(user_dir)
        print("[Storage] Switched to authenticated user storage")

        # Two-way sync: on a fresh machine pull everything; otherwise pull only
        # the files Drive has a NEWER copy of (modified-time check) so we never
        # clobber unsynced local edits.
        has_data = PORTFOLIO_FILE.exists() or MF_PORTFOLIO_FILE.exists()
        try:
            if not has_data:
                print("[Drive] New machine detected — downloading all data from Google Drive...")
                results = google_auth.drive_sync_all("download", data_dir=user_dir)
            else:
                results = google_auth.drive_pull_newer(data_dir=user_dir)
            downloaded = [f for f, ok in results.items() if ok]
            if downloaded:
                print(f"[Drive] Pulled from Drive: {', '.join(downloaded)}")
            elif not has_data:
                print("[Drive] No data found on Drive (first time user)")
        except Exception as e:
            print(f"[Drive] Auto-pull failed: {e}")

        # One-time: backfill the 14-Day Desk from prior days' saved picks so it
        # shows the full rolling window, not just today (guarded — runs once,
        # after the Drive pull so it operates on the freshest desk).
        try:
            bf = swing_trading.desk_backfill_from_history()
            if bf.get("records_added"):
                print(f"[Swing] Desk backfilled {bf['records_added']} picks across {bf['days_added']} day(s)")
        except Exception as e:
            print(f"[Swing] Desk backfill failed: {e}")
    else:
        PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
        MF_PORTFOLIO_FILE = DATA_DIR / "mf_portfolio.json"
        MF_HOLDINGS_FILE = DATA_DIR / "mf_holdings.json"
        WATCHLIST_FILE = DATA_DIR / "watchlist.json"
        SETTINGS_FILE = DATA_DIR / "settings.json"
        EQUITY_TXNS_FILE = DATA_DIR / "equity_txns.json"
        EQUITY_PNL_FILE = DATA_DIR / "equity_pnl.json"
        EQUITY_LEDGER_FILE = DATA_DIR / "equity_ledger.json"
        DEPLOY_LOG_FILE = DATA_DIR / "deploy_log.json"
        CONVICTION_FILE = DATA_DIR / "conviction.json"
        _current_user_email = None
        swing_trading.set_active_data_dir(None)

    user_portfolio = _load_json(PORTFOLIO_FILE, [])
    user_mf_portfolio = _load_json(MF_PORTFOLIO_FILE, [])
    user_mf_holdings = _load_json(MF_HOLDINGS_FILE, {})
    user_equity_txns = _load_json(EQUITY_TXNS_FILE, {})
    user_equity_pnl = _load_json(EQUITY_PNL_FILE, {})
    user_equity_ledger = _load_json(EQUITY_LEDGER_FILE, {})
    user_deploy_log = _load_json(DEPLOY_LOG_FILE, [])
    user_watchlist = _load_json(WATCHLIST_FILE, [])
    user_conviction = _load_json(CONVICTION_FILE, {})
    # Reload settings from the (possibly just-pulled) per-user file
    app_settings = _load_settings()
    ai_models.OLLAMA_API_URL = app_settings["ollama_url"].rstrip("/") + "/api/generate"
    ai_models.MODEL_NAME = app_settings["model_name"]
    # The scan universe is a per-user setting, so it follows the user switch.
    swing_trading.set_scan_universe(app_settings.get("swing_universe"))

DEFAULT_SETTINGS = {
    "ollama_url": "http://localhost:11434",
    "model_name": "qwen3.6:35b",
    "theme": "dark",
    "auto_refresh_nav": True,
    "nav_refresh_interval": 300,
    # Which index the swing scanner sweeps: nifty50 | nifty500 | total
    "swing_universe": swing_trading.DEFAULT_SCAN_UNIVERSE,
    # ── Dividend income goal ──
    "dividend_goal_annual": dividend_analysis.DEFAULT_GOAL_ANNUAL,
    "dividend_tax_slab_pct": dividend_analysis.DEFAULT_TAX_SLAB_PCT,
    "dividend_monthly_investment": 0.0,
    # Manual annual DPS overrides for symbols the provider has no data for:
    # {"SOMECO": 12.5}.  Keyed by bare symbol, no .NS/.BO suffix.
    "dividend_overrides": {},
    # Declared annual payout for IDCW funds: {"<scheme name>": 7500}.
    "dividend_fund_overrides": {},
    # ── Capital deployment plan ──
    # One leg per fund/stock, each with its OWN monthly amount and due day:
    # [{"id","kind","key","amount","due_day","active","note"}].
    "deploy_sip_legs": [],
    # Target allocation %, per individual fund/stock, as a share of the whole
    # deployable book. Keyed by scheme_name (funds) or yf symbol (stocks).
    "deploy_targets": {},
    # Factor weights; invalid/missing keys fall back to DEFAULT_WEIGHTS.
    "deploy_weights": {},
    # Allocation knobs, exposed so the user can tune how aggressive the split is.
    "deploy_score_floor": deploy_engine.SCORE_FLOOR,
    "deploy_max_concentration_pct": deploy_engine.MAX_CONCENTRATION_PCT,
    "deploy_max_candidates": deploy_engine.MAX_CANDIDATES_PER_DEPLOY,
    "deploy_min_ticket_mf": deploy_engine.MIN_TICKET_MF,
    # Suggested monthly budget used to seed a first-run plan.
    "deploy_monthly_budget": 30000.0,
    # When the book was last actually rebalanced. None means never, which the
    # engine reports as a first run rather than as an overdue one.
    "last_rebalanced_at": None,
    # s.112A allowance still unspent this financial year. Carried in settings
    # because it is consumed by disposals this app never sees.
    "ltcg_exemption_left": rebalance_engine.EQUITY_LTCG_EXEMPT,

    # ── Rebalance policy ──
    # The per-asset band, as a share of the holding's own category. Both
    # sliders run 0–100 and the engine swaps them if they cross.
    "rebalance_min_weight_pct": rebalance_engine.MIN_WEIGHT_PCT,
    # Matches the default preset's ceiling (S10 trims above 20%). The two
    # must agree or the screen opens showing a band the plan is not using.
    "rebalance_max_weight_pct": rebalance_engine.STRATEGY_BY_ID[
        rebalance_engine.DEFAULT_STRATEGY]["trim_pct"],
    # How far a whole category may drift from its target, in percentage points
    # of the book, before the drift is worth a trade.
    "rebalance_deviation_pct": rebalance_engine.DEFAULT_DEVIATION_PCT,
    "rebalance_cadence": "semiannual",
    "rebalance_triggers": list(rebalance_engine.DEFAULT_TRIGGERS),
    "rebalance_boom_gain_pct": rebalance_engine.BOOM_YEAR_GAIN_PCT,
    "rebalance_crash_drop_pct": rebalance_engine.CRASH_DRAWDOWN_PCT,
    # None means "no threshold set", which is why the matching trigger is off
    # by default — firing it against a guessed percentage would be worse than
    # not offering it.
    "rebalance_gain_trigger_pct": None,
    "rebalance_loss_trigger_pct": None,
    "rebalance_vol_trigger_pct": rebalance_engine.DEFAULT_VOL_TRIGGER_PCT,
    # Unset until the user states an intention. While it is None the engine
    # uses today's split as the target, so drift is zero rather than the
    # 50 points a brand-new all-equity book would show against a gold
    # target nobody chose.
    "rebalance_category_targets": None,
    "rebalance_mode": rebalance_engine.MODE_AUTO,
    # Which backtested preset drives the plan. S10 was the best of the ten
    # on the measured schedule; M1 beat it there but lost on an annual one,
    # so it is offered rather than defaulted to.
    "rebalance_strategy": rebalance_engine.DEFAULT_STRATEGY,
    # None means every category / every asset. An explicit list narrows what
    # the plan will propose a trade for, without changing any weight.
    "rebalance_selected_categories": None,
    "rebalance_selected_assets": None,
}

def _load_settings():
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
            # Merge with defaults to pick up new keys
            merged = {**DEFAULT_SETTINGS, **saved}
            return merged
    return dict(DEFAULT_SETTINGS)

def _save_settings(settings):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
    # Auto-sync to Google Drive (per-user; no-op when signed out)
    threading.Thread(target=_drive_upload_bg, args=("settings.json",), daemon=True).start()

app_settings = _load_settings()
# Apply settings to ai_models module
ai_models.OLLAMA_API_URL = app_settings["ollama_url"] + "/api/generate"
ai_models.MODEL_NAME = app_settings["model_name"]
swing_trading.set_scan_universe(app_settings.get("swing_universe"))

DEFAULT_PORTFOLIO = []

def _load_json(path, default):
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)
            print(f"[Storage] Loaded {len(data)} items from {path}")
            return data
    return list(default) if isinstance(default, list) else default

def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _drive_upload_bg(filename: str):
    """Background upload a single file to Google Drive."""
    try:
        if not _current_user_email:
            return
        user_dir = _user_data_dir(_current_user_email)
        status = google_auth.drive_sync_file(filename, data_dir=user_dir)
        if status in (google_auth.SYNC_CREATED, google_auth.SYNC_UPDATED):
            print(f"[Drive] Auto-uploaded {filename}")
    except Exception as e:
        print(f"[Drive] Auto-upload failed ({filename}): {e}")

def _save_portfolio():
    _save_json(PORTFOLIO_FILE, user_portfolio)
    threading.Thread(target=_drive_upload_bg, args=("portfolio.json",), daemon=True).start()

def _save_mf_portfolio():
    _save_json(MF_PORTFOLIO_FILE, user_mf_portfolio)
    threading.Thread(target=_drive_upload_bg, args=("mf_portfolio.json",), daemon=True).start()

def _save_mf_holdings():
    _save_json(MF_HOLDINGS_FILE, user_mf_holdings)
    threading.Thread(target=_drive_upload_bg, args=("mf_holdings.json",), daemon=True).start()

def _save_equity_ledger():
    _save_json(EQUITY_LEDGER_FILE, user_equity_ledger)
    threading.Thread(target=_drive_upload_bg, args=("equity_ledger.json",), daemon=True).start()

def _save_equity_pnl():
    _save_json(EQUITY_PNL_FILE, user_equity_pnl)
    threading.Thread(target=_drive_upload_bg, args=("equity_pnl.json",), daemon=True).start()

def _save_equity_txns():
    _save_json(EQUITY_TXNS_FILE, user_equity_txns)
    threading.Thread(target=_drive_upload_bg, args=("equity_txns.json",), daemon=True).start()

def _save_deploy_log():
    _save_json(DEPLOY_LOG_FILE, user_deploy_log)
    threading.Thread(target=_drive_upload_bg, args=("deploy_log.json",), daemon=True).start()

def _save_watchlist():
    _save_json(WATCHLIST_FILE, user_watchlist)
    threading.Thread(target=_drive_upload_bg, args=("watchlist.json",), daemon=True).start()

DEFAULT_MF_PORTFOLIO = []

# Load data for the currently authenticated user (if any)
_auth_profile = google_auth.get_profile()
if _auth_profile and _auth_profile.get("email"):
    _switch_user_data(_auth_profile["email"])
else:
    # No authenticated user — start with empty data (not legacy files)
    user_portfolio = []
    user_mf_portfolio = []
    user_mf_holdings = {}
    user_equity_txns = {}
    user_deploy_log = []
    user_watchlist = []
    user_conviction = {}

# ─── Deep Signal Cache ────
deep_signal_cache: dict = {}
deep_signal_running = False

# ─── Live Price Cache ────
import dashboard_metadata

live_price_cache: dict = {}
_price_thread_started = False

# ─── Data Source Mode ────
# When Kite is connected, use it as primary. Otherwise fallback to yfinance.
def _is_kite_connected() -> bool:
    return kite_client.connected

def _yf_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if not s.endswith(".NS") and not s.endswith(".BO"):
        s += ".NS"
    return s

KITE_PRICE_DEBUG = os.getenv("KITE_PRICE_DEBUG", "").lower() in ("1", "true", "yes")


def _kite_syms_for(yf_sym: str) -> list:
    """Candidate Kite instrument keys for a portfolio symbol.

    The holdings round-trip (tradingsymbol -> .NS suffix -> NSE:) is not an identity
    for BSE-only scrips, so try the other exchange as well rather than giving up.
    """
    primary = kite_client.symbol_to_kite_format(yf_sym)
    base = primary.split(":", 1)[1]
    alt = f"BSE:{base}" if primary.startswith("NSE:") else f"NSE:{base}"
    return [primary, alt]


def _price_from_ohlc(d: dict):
    """Pull (last, prev_close) out of one get_ohlc entry, or (None, None)."""
    if not isinstance(d, dict):
        return None, None
    try:
        cur = float(d.get("last_price") or 0)
    except (TypeError, ValueError):
        return None, None
    if cur <= 0:
        return None, None
    ohlc = d.get("ohlc") or {}
    try:
        prev = float(ohlc.get("close") or 0) or cur
    except (TypeError, ValueError):
        prev = cur
    return cur, prev


# Provider names used everywhere a price is attributed. Kept as constants
# because the dashboard's "Live from Zerodha" badge is derived from them, and a
# typo would silently turn a truthful badge back into a decorative one.
PRICE_SRC_KITE = "kite"
PRICE_SRC_YF = "yfinance"
PRICE_SRC_KITE_SNAPSHOT = "kite_holdings"
PRICE_SRC_NONE = "none"


def _derive_data_source(from_kite: int, from_yf: int) -> str:
    """Name the provider that actually priced the book.

    Extracted so it can be tested without standing up a portfolio. "mixed" is
    a real and common answer — Kite prices the NSE names and Yahoo covers the
    BSE-only ones — and collapsing it into "kite" is exactly the
    over-claim this function exists to prevent.
    """
    if from_kite and not from_yf:
        return "kite"
    if from_yf and not from_kite:
        return "yfinance"
    if from_kite and from_yf:
        return "mixed"
    return "none"


def _fetch_price(yf_sym: str):
    """Fetch price: try Kite (OHLC then LTP), fallback to yfinance.

    Two-value wrapper kept for the several callers that only want numbers.
    Anything that needs to say WHERE the price came from must use
    :func:`_fetch_price_with_source`.
    """
    cur, prev, _src = _fetch_price_with_source(yf_sym)
    return cur, prev


def _fetch_price_with_source(yf_sym: str):
    """As :func:`_fetch_price`, but also returns the provider that answered.

    This exists because the app was claiming "Live from Zerodha" while every
    single price came from Yahoo. The Kite session reports connected — its
    get_profile call genuinely succeeds and returns the real user — but
    get_ohlc and get_ltp were both failing, so the badge described the
    CONNECTION rather than the DATA. Attribution has to travel with the number
    for the badge to be able to tell the truth.
    """
    # Try Kite Connect first
    if _is_kite_connected():
        candidates = _kite_syms_for(yf_sym)
        try:
            ohlc = kite_client.get_ohlc(candidates)
            if KITE_PRICE_DEBUG:
                print(f"[Kite:debug] get_ohlc({candidates}) -> {ohlc!r}")
            for kite_sym in candidates:
                if ohlc and kite_sym in ohlc:
                    cur, prev = _price_from_ohlc(ohlc[kite_sym])
                    if cur:
                        return cur, prev, PRICE_SRC_KITE
            print(f"[Kite] OHLC gave no usable price for {yf_sym} "
                  f"(tried {candidates}, got keys {list(ohlc) if ohlc else None}); trying LTP")
        except Exception as e:
            print(f"[Kite] OHLC fetch failed for {yf_sym}: {e}")

        # Second Kite attempt: LTP is a lighter endpoint and sometimes populated
        # when OHLC is not (e.g. pre-open, or instruments without a day candle yet).
        try:
            ltp = kite_client.get_ltp(candidates)
            if KITE_PRICE_DEBUG:
                print(f"[Kite:debug] get_ltp({candidates}) -> {ltp!r}")
            for kite_sym in candidates:
                if ltp and kite_sym in ltp:
                    try:
                        cur = float((ltp[kite_sym] or {}).get("last_price") or 0)
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if cur > 0:
                        # No prev close available from LTP.
                        return cur, cur, PRICE_SRC_KITE
        except Exception as e:
            print(f"[Kite] LTP fetch failed for {yf_sym}: {e}")

        print(f"[Kite] No Kite price for {yf_sym}, falling back to yfinance")

    # Fallback to yfinance
    try:
        h = _safe_yf_history(yf_sym, period="5d")
        if h.empty:
            return None, None, PRICE_SRC_NONE
        import math
        cur = float(h["Close"].iloc[-1])
        prev = float(h["Close"].iloc[-2]) if len(h) >= 2 else cur
        # Sanitize NaN — thinly traded stocks can have NaN closes
        if math.isnan(cur):
            return None, None, PRICE_SRC_NONE
        if math.isnan(prev):
            prev = cur
        return cur, prev, PRICE_SRC_YF
    except Exception:
        return None, None, PRICE_SRC_NONE

def _bg_price_refresh():
    import time
    while True:
        resolved = set()

        # Batch fetch from Kite if connected
        if _is_kite_connected() and user_portfolio:
            try:
                kite_syms = []
                for item in user_portfolio:
                    kite_syms.extend(_kite_syms_for(_yf_symbol(item["symbol"])))
                ohlc = kite_client.get_ohlc(kite_syms)
                if ohlc:
                    for item in user_portfolio:
                        for kite_sym in _kite_syms_for(_yf_symbol(item["symbol"])):
                            if kite_sym not in ohlc:
                                continue
                            cur, prev = _price_from_ohlc(ohlc[kite_sym])
                            if cur:
                                live_price_cache[item["symbol"]] = {
                                    "current": cur, "prev": prev,
                                    "source": PRICE_SRC_KITE,
                                    "observed_at": dashboard_metadata.utc_now()}
                                resolved.add(item["symbol"])
                                break
            except Exception as e:
                print(f"[Kite] Batch price refresh failed: {e}")

            if len(resolved) == len(user_portfolio):
                time.sleep(_price_poll_seconds(kite=True))
                continue

        # Fallback: yfinance one-by-one, but only for what Kite could not price.
        # Previously a partial Kite batch skipped this entirely, so the misses
        # stayed permanently absent from the cache.
        for item in user_portfolio:
            if item["symbol"] in resolved:
                continue
            sym = _yf_symbol(item["symbol"])
            cur, prev, provider = _fetch_price_with_source(sym)
            if cur is not None:
                live_price_cache[item["symbol"]] = {
                    "current": cur, "prev": prev, "source": provider,
                    "observed_at": dashboard_metadata.utc_now()}
        time.sleep(_price_poll_seconds(kite=False))


def _price_poll_seconds(kite: bool) -> float:
    """How long the background price loop waits between passes.

    In session: 3s from Kite (one batched call), 10s from Yahoo (one request
    per holding, so it has to be gentler). Out of session the prices cannot
    move, and hammering either source only spends rate limit — the thing that
    cost the Kite login — so it drops to once a minute.
    """
    if not market_indices.is_market_open():
        return 60.0
    return 3.0 if kite else 10.0

def _start_price_thread():
    global _price_thread_started
    if not _price_thread_started:
        _price_thread_started = True
        t = threading.Thread(target=_bg_price_refresh, daemon=True)
        t.start()
        src = "Kite Connect" if _is_kite_connected() else "Yahoo Finance"
        print(f"[LiveFeed] Background price thread started (source: {src})")

def _run_deep_signal_bg():
    global deep_signal_running, deep_signal_cache
    deep_signal_running = True
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for item in user_portfolio:
        sym = item["symbol"]
        deep_signal_cache[sym] = {"status": "running"}
        try:
            yf_s = _yf_symbol(sym)
            ticker = yf.Ticker(yf_s)
            hist = _safe_yf_history(yf_s, period="1y")
            if hist.empty:
                deep_signal_cache[sym] = {"status": "done", "verdict_owned": "NO DATA", "analysis_ok": False}
                continue
            sector = "Other"
            for s in POPULAR_INDIAN_STOCKS:
                if s["symbol"] == sym: sector = s["sector"]; break
            result = loop.run_until_complete(ai_models.run_full_analysis_async(ticker, sym, hist, [], sector))
            cio = result.get("cio_report", {})
            # Coerce conviction score to int clamped 0-100, else null
            conviction = None
            try:
                conviction = max(0, min(100, int(float(str(cio.get("conviction_score"))))))
            except (ValueError, TypeError):
                conviction = None
            deep_signal_cache[sym] = {
                "status": "done",
                "verdict_owned": cio.get("final_decision", "HOLD"),
                "conviction_score": conviction,
                "executive_summary": cio.get("executive_summary"),
                "target_price": cio.get("target_price"),
                "current_price": cio.get("current_price"),
                "stop_loss": cio.get("stop_loss"),
                "action_type": cio.get("action_type"),
                "analysis_ok": True,
            }
        except Exception as e:
            print(f"[DeepSignal] Error for {sym}: {e}")
            deep_signal_cache[sym] = {"status": "done", "verdict_owned": "ERROR", "analysis_ok": False}
        # Throttle: wait 2s between stocks to avoid Yahoo rate-limit
        _time.sleep(2)
    deep_signal_running = False
    loop.close()


@app.get("/api/status")
async def read_root():
    # Reports whether Kite is actually SERVING data, not merely whether a
    # session exists — see the note in get_portfolio.
    # async on purpose: it does no blocking work, so it runs on the event loop
    # and still answers (the login screen's readiness check) when every
    # threadpool worker is busy with slow price fetches.
    serving = any((v or {}).get("source") == PRICE_SRC_KITE
                  for v in list(live_price_cache.values()))
    src = "Zerodha Kite Connect" if serving else "Yahoo Finance"
    return {"message": "Ponfolio API", "data_source": src,
            "kite_connected": _is_kite_connected(),
            "kite_serving_prices": serving}

@app.get("/api/search")
def search_stock(q: str):
    q = q.upper()
    matches = [s for s in POPULAR_INDIAN_STOCKS if q in s["symbol"] or q in s["name"].upper()]
    if not matches:
        yf_sym = _yf_symbol(q)
        try:
            t = yf.Ticker(yf_sym)
            info = t.fast_info
            if info and info.last_price:
                matches.append({"symbol": yf_sym, "name": q, "sector": "Unknown", "live_price": round(info.last_price, 2)})
        except: pass
    return {"results": matches[:20]}

def _sector_for(symbol: str) -> str:
    base_sym = symbol.replace(".BO", "").replace(".NS", "")
    for s in POPULAR_INDIAN_STOCKS:
        if s["symbol"].replace(".BO", "").replace(".NS", "") == base_sym:
            return s["sector"]
    ns_key = base_sym + ".NS"
    if ns_key in _SECTOR_MAP:
        return _SECTOR_MAP[ns_key]["sector"]
    return "Other"


def _resolve_price(item: dict, use_cache: bool = True):
    """Resolve (current, prev, source) for a holding.

    Order: live cache -> live fetch -> the price Kite sent with the holding itself.
    That last leg is what stops a holding rendering as a blank value: Kite already
    gave us a price at sync time, so a failed get_ohlc/yfinance round-trip is no
    longer the difference between showing a value and showing nothing.
    """
    import math

    def _ok(v):
        return v is not None and isinstance(v, (int, float)) and not math.isnan(v) and v > 0

    if use_cache:
        cached = live_price_cache.get(item["symbol"])
        if cached and _ok(cached.get("current")):
            prev = cached.get("prev")
            # A cache entry written before providers were tracked has no
            # source. Reporting it as Kite would be a guess in the flattering
            # direction, so it degrades to unknown instead.
            return (cached["current"],
                    (prev if _ok(prev) else cached["current"]),
                    cached.get("source") or "unknown")

    current, prev, provider = _fetch_price_with_source(_yf_symbol(item["symbol"]))
    if _ok(current):
        live_price_cache[item["symbol"]] = {
            "current": current, "prev": prev, "source": provider,
            "observed_at": dashboard_metadata.utc_now(),
        }
        return current, (prev if _ok(prev) else current), provider

    # Last resort: the snapshot carried over from get_holdings.
    snap = item.get("kite_last_price")
    if _ok(snap):
        close = item.get("kite_close_price")
        return snap, (close if _ok(close) else snap), PRICE_SRC_KITE_SNAPSHOT

    return None, None, PRICE_SRC_NONE


def _holding_row(item: dict, current, prev, source: str) -> dict:
    """Build one holding row. Always emits the value keys, even with no price."""
    qty = item["shares"]
    avg_cost = item.get("avg_cost") or 0
    invested = qty * avg_cost
    row = {
        "symbol": item["symbol"], "name": item["name"], "sector": _sector_for(item["symbol"]),
        "shares": qty, "avg_cost": avg_cost,
        "invested": round(invested, 2), "currency": "INR",
        "price_source": source,
        "last_updated": (live_price_cache.get(item["symbol"]) or {}).get("observed_at"),
    }
    if current is None:
        # No price anywhere. Emit explicit nulls plus an error rather than omitting
        # the keys — a missing key silently renders as 0 on the client.
        row.update({
            "current_price": None, "total_value": None, "pnl": None,
            "net_chg": None, "day_chg": None, "day_change_value": None, "error": "No price data",
        })
        return row
    cur_val = qty * current
    row.update({
        "current_price": round(current, 2),
        "total_value": round(cur_val, 2),
        "pnl": round(cur_val - invested, 2),
        "net_chg": round(((current - avg_cost) / avg_cost) * 100, 2) if avg_cost else 0,
        "day_chg": round(((current - prev) / prev) * 100, 2) if prev else 0,
        "day_change_value": round(qty * (current - prev), 2) if prev else None,
    })
    return row


# ──────────────────────────────────────
# Equity XIRR — dated ledger from the Kite tradebook
# ──────────────────────────────────────

def _sync_equity_trades_from_kite() -> dict:
    """Pull the Kite MCP tradebook into the local dated ledger.

    Kite's holdings carry no dates, so this is the only way an equity XIRR gets
    its cashflows. Merging is idempotent (deduped on trade_id), so this is safe
    to run on every portfolio sync — and because the ledger persists, a
    day-scoped tradebook still accumulates real history one session at a time.
    """
    global user_equity_txns
    if not _is_kite_connected():
        return {"status": "not_connected", "added": 0}
    try:
        raw = kite_client.fetch_all_trades()
    except Exception as e:
        print(f"[Kite] Tradebook fetch failed: {e}")
        return {"status": "error", "detail": str(e), "added": 0}
    if raw is None:
        return {"status": "unavailable", "added": 0}

    rows = []
    skipped = 0
    for t in raw:
        row = equity_txns.normalize_kite_trade(t, kite_client.kite_to_yf_symbol)
        if row:
            rows.append(row)
        else:
            skipped += 1

    added = equity_txns.merge_trades(user_equity_txns, rows)
    if added:
        _save_equity_txns()
    dates = sorted(r["date"] for r in rows) if rows else []
    span = f", {dates[0]}..{dates[-1]}" if dates else ""
    print(f"[Kite] Tradebook: {len(raw)} fetched, {len(rows)} usable, {added} new{span}")
    return {
        "status": "ok", "fetched": len(raw), "usable": len(rows),
        "added": added, "skipped": skipped,
        "date_range": [dates[0], dates[-1]] if dates else None,
        "symbols": len(user_equity_txns),
    }


def _annotate_xirr(rows: list) -> dict:
    """Attach per-holding XIRR to portfolio rows (mutated) and return the book total.

    Each row gains ``xirr`` (None when no honest number exists), ``xirr_basis``
    ('exact' | 'partial' | 'unsolved' | 'none') and ``xirr_exact``. The
    book-level figure counts only exactly-covered holdings — see equity_txns.
    """
    for row in rows:
        res = equity_txns.xirr_for(
            # Resolved by underlying, not by exact key: the ledger and the
            # portfolio routinely disagree on the .NS/.BO suffix for the same
            # company, and an exact lookup silently reported "no history".
            equity_txns.txns_for(
                user_equity_txns, row.get("symbol"), row.get("isin") or ""),
            current_value=row.get("total_value") or 0,
            held_qty=row.get("shares") or 0,
            avg_cost=row.get("avg_cost") or 0,
        )
        row["xirr"] = res["xirr"]
        row["xirr_basis"] = res["basis"]
        row["xirr_exact"] = res["exact"]
    return equity_txns.portfolio_xirr(user_equity_txns, rows)


def _solve_xirr(flows: list, terminal_value: float):
    """Solve XIRR over dated flows plus a terminal value. None when unsolvable."""
    if not flows or terminal_value <= 0:
        return None
    try:
        rate = sip_simulator._xirr(sorted(flows, key=lambda f: f[0])
                                   + [(datetime.now(), terminal_value)])
    except Exception:
        return None
    return round(rate, 2) if rate else None


def _mf_cashflows(funds: list = None):
    """Dated MF cashflows and the value they cover.

    Only funds that actually carry a transaction history contribute — a fund
    synced from Kite as a bare snapshot has no dates, so folding its current
    value into the terminal amount without its cashflows would inflate the rate.
    """
    flows, covered = [], 0.0
    for fund in (funds if funds is not None else user_mf_portfolio):
        txns = fund.get("transactions") or []
        value = fund.get("current_value", 0) or 0
        if not txns or value <= 0:
            continue
        fund_flows = []
        for txn in txns:
            when = equity_txns.parse_date(txn.get("date"))
            if not when:
                continue
            invested = txn.get("invested", 0) or 0
            redeemed = txn.get("redeemed", 0) or 0
            if invested > 0:
                fund_flows.append((when, -invested))
            if redeemed > 0:
                fund_flows.append((when, redeemed))
        if not fund_flows:
            continue
        flows.extend(fund_flows)
        covered += value
    return flows, covered


@app.get("/api/portfolio/transactions")
def get_equity_transactions(symbol: str = Query(None)):
    """The dated equity ledger — everything, or one symbol's trades."""
    if symbol:
        sym = _yf_symbol(symbol)
        rows = user_equity_txns.get(sym, [])
        holding = next((h for h in user_portfolio
                        if h.get("symbol") == sym), None)
        return {
            "symbol": sym,
            "count": len(rows),
            "buys": sum(1 for row in rows if row.get("type") == "BUY"),
            "sells": sum(1 for row in rows if row.get("type") == "SELL"),
            "net_qty": round(equity_txns.net_qty(rows), 4),
            "held_qty": (holding or {}).get("shares"),
            "transactions": rows,
        }
    return {
        "symbols": len(user_equity_txns),
        "total_trades": sum(len(v) for v in user_equity_txns.values()),
        "transactions": user_equity_txns,
    }


def _tradebook_resolver():
    """Symbol resolver bound to the CURRENT portfolio and Kite holdings.

    Rebuilt per import rather than cached: the portfolio changes, and a stale
    map would file a newly added holding under an exchange-suffixed symbol that
    nothing reconciles against.
    """
    try:
        kite_holdings = kite_client.get_holdings() or []
    except Exception:
        kite_holdings = []
    return tradebook_import.build_symbol_resolver(user_portfolio, kite_holdings)


@app.post("/api/portfolio/import-tradebook")
async def import_tradebook(file: UploadFile = File(...)):
    """Import a Zerodha Console tradebook (CSV or XLSX) into the equity ledger.

    Console is the only source of a full dated trade history — the Kite MCP
    `get_trades` tool is day-scoped and reports `{"total": 0}` on any day with
    no fills, which is why this ledger was empty while the mutual-fund side had
    24 dated transactions.

    Safe to re-run every month. Rows carry Console's `trade_id` and
    `equity_txns.merge_trades` de-duplicates on it, so an export that overlaps
    the previous one contributes only what is new. `added` reports the
    difference; a second upload of the same file adds 0.

    The response also reconciles the resulting ledger against the broker's own
    quantities, because an import that cannot be checked against the account is
    not worth trusting.
    """
    global user_equity_txns

    try:
        blob = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read upload: {e}")
    if not blob:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    resolver = _tradebook_resolver()
    # Dispatch on the bytes, not on the filename: Console's download button
    # gives .xlsx by default and a renamed file must not be parsed as CSV.
    # "PK" is the zip magic every xlsx starts with.
    if blob[:2] == b"PK":
        rows, report = tradebook_import.parse_tradebook_xlsx(blob, resolver)
    else:
        # Console CSVs are utf-8, sometimes with a BOM. Fall back rather than
        # 500 on an unexpected encoding.
        try:
            text = blob.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = blob.decode("latin-1", errors="replace")
        rows, report = tradebook_import.parse_tradebook_csv(text, resolver)
    if report.get("error"):
        raise HTTPException(status_code=400, detail=report["error"])

    canonicalized = tradebook_import.canonicalize_store(
        user_equity_txns, resolver)
    added = equity_txns.merge_trades(user_equity_txns, rows)
    if added or canonicalized:
        _save_equity_txns()

    return {
        "status": "ok",
        "filename": file.filename,
        "added": added,
        "canonicalized": canonicalized,
        "already_present": report["parsed"] - added,
        "report": report,
        "reconciliation": tradebook_import.reconcile(
            user_equity_txns, user_portfolio),
        "ledger_symbols": len(user_equity_txns),
    }


@app.get("/api/portfolio/tradebook-status")
def tradebook_status():
    """What the equity ledger currently covers, per holding.

    Answers "which of my stocks have real buy dates and which do not" without
    uploading anything — the four holdings absent from the first export show as
    `no_history` rather than as zero-cost positions.
    """
    recon = tradebook_import.reconcile(user_equity_txns, user_portfolio)
    trades = sum(len(v) for v in user_equity_txns.values())
    return {
        "ledger_symbols": len(user_equity_txns),
        "ledger_trades": trades,
        "covered": sum(1 for r in recon if r["status"] == "exact"),
        "partial": sum(1 for r in recon if r["status"] == "partial"),
        "missing": sum(1 for r in recon if r["status"] == "no_history"),
        "reconciliation": recon,
    }


@app.post("/api/portfolio/import-kite-pnl")
async def import_kite_pnl(file: UploadFile = File(...)):
    """Import a Kite Console P&L statement (.xlsx) for one period.

    This is the measured half of the closed book. A tradebook supports a FIFO
    reconstruction of realised P&L but knows nothing about what the trades
    cost; this statement carries the broker's own realised figure AND the
    charges actually levied — brokerage, STT, GST, stamp duty, DP — which can
    be far above what a statutory rate card estimates.

    Statements are filed by the period printed in their title, so exporting
    one month at a time accumulates correctly: re-uploading a month replaces
    it rather than doubling it. An upload whose range overlaps a period
    already held is still stored, but the overlap is reported, because a book
    total that sums overlapping statements counts those days twice.
    """
    global user_equity_pnl

    try:
        blob = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read upload: {e}")
    if not blob:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if blob[:2] != b"PK":
        raise HTTPException(
            status_code=400,
            detail="The P&L statement must be the .xlsx export. Console -> "
                   "Reports -> P&L -> download as XLSX.")

    try:
        statement = kite_pnl_import.parse_pnl_workbook(blob)
    except xlsx_reader.XlsxError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if statement.get("error"):
        raise HTTPException(status_code=400, detail=statement["error"])

    result = kite_pnl_import.merge_statement(user_equity_pnl, statement)
    if not result.get("stored"):
        raise HTTPException(status_code=400,
                            detail=result.get("error", "Could not store the statement."))
    _save_equity_pnl()

    return {
        "status": "ok",
        "filename": file.filename,
        "period": statement["period"],
        "replaced": result["replaced"],
        "conflicts": result["conflicts"],
        "periods_held": result["periods_held"],
        "realized_pnl": statement["summary"].get("realized_pnl"),
        "charges_actual": statement["summary"].get("charges"),
        "symbols_closed": len(statement["closed"]),
        "symbols_open": len(statement["open"]),
        "checks": statement["checks"],
    }


@app.post("/api/portfolio/import-kite-ledger")
async def import_kite_ledger(file: UploadFile = File(...)):
    """Import a Kite Console funds ledger (.xlsx) for one period.

    The ledger is the only export that carries TDS. The tradebook is fills and
    the P&L charge block covers brokerage, STT, GST, stamp duty, SEBI and
    IPFT — TDS appears in none of them, so a cost figure built from those two
    alone is short by whatever was withheld.

    Provisional TDS is kept apart from deducted TDS on purpose: Console blocks
    an amount against a pending liability and usually reverses it days later,
    and a blocked-then-reversed pair can be many times the TDS genuinely
    deducted. Adding the two would overstate the tax by that multiple.
    """
    global user_equity_ledger

    try:
        blob = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read upload: {e}")
    if not blob:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if blob[:2] != b"PK":
        raise HTTPException(
            status_code=400,
            detail="The ledger must be the .xlsx export. Console -> Reports -> "
                   "Ledger -> download as XLSX.")

    try:
        statement = kite_ledger_import.parse_ledger_workbook(blob)
    except xlsx_reader.XlsxError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if statement.get("error"):
        raise HTTPException(status_code=400, detail=statement["error"])

    result = kite_ledger_import.merge_ledger(user_equity_ledger, statement)
    if not result.get("stored"):
        raise HTTPException(status_code=400,
                            detail=result.get("error", "Could not store the ledger."))
    _save_equity_ledger()

    tds = statement["tds"]
    return {
        "status": "ok",
        "filename": file.filename,
        "period": statement["period"],
        "replaced": result["replaced"],
        "conflicts": result["conflicts"],
        "periods_held": result["periods_held"],
        "entries": len(statement["entries"]),
        "tds_deducted": tds["deducted"],
        "tds_provisional_outstanding": tds["provisional_outstanding"],
        "funds": statement["funds"],
        "opening_balance": statement["opening_balance"],
        "closing_balance": statement["closing_balance"],
    }


@app.get("/api/portfolio/ledger-entries")
def ledger_entries():
    """TDS and fund movements across every imported ledger period."""
    return kite_ledger_import.book(user_equity_ledger)


@app.delete("/api/portfolio/ledger-entries/{period}")
def delete_ledger_period(period: str):
    """Drop one imported ledger period."""
    global user_equity_ledger
    if period not in user_equity_ledger:
        raise HTTPException(status_code=404, detail=f"No ledger for {period}.")
    user_equity_ledger.pop(period, None)
    _save_equity_ledger()
    return {"status": "ok", "removed": period,
            "periods_held": sorted(user_equity_ledger.keys())}


@app.get("/api/portfolio/pnl-statements")
def pnl_statements():
    """Which P&L periods are held, so the user can see the gaps."""
    return kite_pnl_import.book(user_equity_pnl)


@app.delete("/api/portfolio/pnl-statements/{period}")
def delete_pnl_statement(period: str):
    """Drop one imported period — the way out of an overlapping import."""
    global user_equity_pnl
    if period not in user_equity_pnl:
        raise HTTPException(status_code=404, detail=f"No statement for {period}.")
    user_equity_pnl.pop(period, None)
    _save_equity_pnl()
    return {"status": "ok", "removed": period,
            "periods_held": sorted(user_equity_pnl.keys())}


@app.get("/api/portfolio/closed-positions")
def closed_positions():
    """Realised P&L on shares already sold, FIFO-matched from the ledger.

    Holdings answer "what is my open position worth"; this answers "what did I
    actually make on what I sold", which nothing in the app reported before —
    the dashboard's Realised profit tile simply read "Unavailable".

    Charges are ESTIMATED from the statutory delivery rate card and the tax
    figure is INDICATIVE: a tradebook carries no contract-note charges, so
    they are computed rather than billed. Both bases ship in the response so
    the UI can label them, and :mod:`equity_closed` documents why they are
    kept apart from the measured buy/sell numbers.
    """
    return equity_closed.closed_positions(user_equity_txns,
                                          statements=user_equity_pnl,
                                          ledgers=user_equity_ledger)


@app.post("/api/kite/sync-trades")
def kite_sync_trades():
    """Force a tradebook pull from Kite MCP into the equity ledger."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    return _sync_equity_trades_from_kite()


@app.get("/api/portfolio/xirr")
def get_portfolio_xirr():
    """Annualised return for equity, mutual funds, and the two combined.

    The combined figure pools both sets of cashflows into a single solve rather
    than blending two rates, so it is a real rate on the real timeline. Each
    block reports ``covered_pct`` — the share of that book's value that has
    dated cashflows behind it. A null ``xirr`` means nothing does.
    """
    rows = []
    for item in user_portfolio:
        current, prev, source = _resolve_price(item)
        rows.append(_holding_row(item, current, prev, source))
    eq = _annotate_xirr(rows)

    eq_flows = []
    for sym in eq["covered_symbols"]:
        eq_flows.extend(equity_txns.cashflows(user_equity_txns.get(sym) or []))
    mf_flows, mf_covered = _mf_cashflows()

    mf_value = sum(f.get("current_value", 0) or 0 for f in user_mf_portfolio)
    total_value = eq["total_value"] + mf_value
    combined_covered = eq["covered_value"] + mf_covered

    return {
        "equity": {
            "xirr": eq["xirr"],
            "covered_value": eq["covered_value"],
            "total_value": eq["total_value"],
            "covered_pct": eq["covered_pct"],
        },
        "mutual_funds": {
            "xirr": _solve_xirr(mf_flows, mf_covered),
            "covered_value": round(mf_covered, 2),
            "total_value": round(mf_value, 2),
            "covered_pct": round(mf_covered / mf_value * 100, 2) if mf_value > 0 else 0.0,
        },
        "combined": {
            "xirr": _solve_xirr(eq_flows + mf_flows, combined_covered),
            "covered_value": round(combined_covered, 2),
            "total_value": round(total_value, 2),
            "covered_pct": round(combined_covered / total_value * 100, 2) if total_value > 0 else 0.0,
        },
    }


@app.get("/api/portfolio/xirr-coverage")
def get_xirr_coverage():
    """Per-holding diagnosis of why an XIRR is exact, approximate, or missing.

    The dashboard shows '—' for anything the ledger can't back; this is where
    to look to find out which holdings still need trade history and why.
    """
    rows = []
    for item in user_portfolio:
        current, prev, source = _resolve_price(item)
        row = _holding_row(item, current, prev, source)
        rows.append(row)
    book = _annotate_xirr(rows)
    detail = []
    for row in rows:
        txns = user_equity_txns.get(row["symbol"]) or []
        detail.append({
            "symbol": row["symbol"],
            "shares": row["shares"],
            "trades": len(txns),
            "ledger_qty": round(equity_txns.net_qty(txns), 4),
            "xirr": row["xirr"],
            "basis": row["xirr_basis"],
            "first_trade": txns[0]["date"] if txns else None,
        })
    return {
        "kite_connected": _is_kite_connected(),
        "portfolio_xirr": book["xirr"],
        "covered_pct": book["covered_pct"],
        "exact": sum(1 for d in detail if d["basis"] == "exact"),
        "partial": sum(1 for d in detail if d["basis"] == "partial"),
        "missing": sum(1 for d in detail if d["basis"] == "none"),
        "holdings": detail,
    }


@app.get("/api/portfolio/default")
def get_portfolio(sync_kite: bool = False):
    # Sync portfolio from Kite if connected and requested (or first load)
    if _is_kite_connected() and sync_kite:
        _sync_portfolio_from_kite()

    _start_price_thread()
    results, total_value, total_invested = [], 0, 0
    stale, unpriced = 0, 0
    from_kite, from_yf = 0, 0
    for item in user_portfolio:
        try:
            current, prev, source = _resolve_price(item)
            row = _holding_row(item, current, prev, source)
            results.append(row)
            total_invested += row["invested"]
            if row["total_value"] is not None:
                total_value += row["total_value"]
            if source == PRICE_SRC_KITE:
                from_kite += 1
            elif source == PRICE_SRC_YF:
                from_yf += 1
            if source == PRICE_SRC_KITE_SNAPSHOT:
                stale += 1
            elif source == PRICE_SRC_NONE:
                unpriced += 1
        except Exception as e:
            results.append({"symbol": item["symbol"], "name": item["name"], "error": str(e)})
    if stale or unpriced:
        print(f"[Portfolio] {stale} holding(s) priced from the Kite holdings snapshot, "
              f"{unpriced} with no price at all")

    # data_source describes where the PRICES came from, not whether a session
    # exists. It used to be `"kite" if _is_kite_connected()`, which made the
    # dashboard read "Live from Zerodha" while every single price had fallen
    # back to Yahoo — the Kite session reports connected because get_profile
    # genuinely succeeds, but get_ohlc and get_ltp were both failing. A badge
    # describing the connection instead of the data is worse than no badge: it
    # tells the user their numbers are live when they are not.
    data_source = _derive_data_source(from_kite, from_yf)

    tp = round(total_value - total_invested, 2)
    book = _annotate_xirr(results)
    return {
        "status": "success", "currency": "INR",
        "data_source": data_source,
        **dashboard_metadata.freshness(r.get("last_updated") for r in results),
        "timestamp_basis": "price retrieved; exchange timestamp unavailable",
        "valuation_complete": len(results) == len(user_portfolio) and all(r.get("total_value") is not None for r in results),
        "month_investment": dashboard_metadata.monthly_buys(
            t for rows in user_equity_txns.values() for t in rows),
        "month_investment_basis": "recorded purchases only; ledger may be incomplete",
        "kite_connected": _is_kite_connected(),
        "stale_priced_count": stale, "unpriced_count": unpriced,
        "kite_priced_count": from_kite, "fallback_priced_count": from_yf,
        "total_portfolio_value": round(total_value, 2), "total_invested": round(total_invested, 2),
        "total_pnl": tp, "total_pnl_pct": round((tp / total_invested) * 100, 2) if total_invested > 0 else 0,
        "total_xirr": book["xirr"],
        "xirr_covered_pct": book["covered_pct"],
        "holdings": results,
    }

@app.get("/api/portfolio/live-prices")
def get_live_prices():
    """The dashboard's live poll: the same payload as /default, from cache.

    It used to return a reduced shape (no data_source, freshness or Kite
    counts), so the client could not lay it over the dashboard without losing
    the badges — and nothing used it, which is why the dashboard never moved
    between manual refreshes. Same shape, no Kite sync: the background thread
    keeps `live_price_cache` current, so this is a cheap read.
    """
    payload = get_portfolio(sync_kite=False)
    payload["market_open"] = market_indices.is_market_open()
    return payload

def _bare_symbol(sym: str) -> str:
    """'ITC.NS' -> 'ITC' — the tradingsymbol form the Kite ledger rows use."""
    return re.sub(r"\.(NS|BO)$", "", sym or "", flags=re.I)


def _upsert_holding(sym: str, shares: int, price: float, *,
                    date: str = None, trade_id: str = None,
                    source: str = "manual") -> dict:
    """Add shares to a holding AND record the buy in the dated ledger.

    The ledger write is the whole point. ``portfolio.json`` stores only a net
    position and a blended average cost, which cannot answer "when did this
    money go in?". :func:`equity_txns.xirr_for` needs dated cashflows, and the
    deployment SIP checklist needs to know whether this month's buy actually
    happened. Until this helper existed, ``/api/portfolio/add`` wrote only
    ``portfolio.json``, so every manually added holding was permanently
    invisible to both — its XIRR stayed ``basis: "none"`` forever.

    ``merge_trades`` dedupes on ``trade_id``, so a caller that supplies a stable
    id makes this idempotent. Callers without a natural id get one derived from
    the current bucket length rather than from qty/price, so two genuinely
    separate same-day buys of the same size are not swallowed as a duplicate.
    """
    when = date or datetime.now().strftime("%Y-%m-%d")

    existing = next((h for h in user_portfolio if h["symbol"] == sym), None)
    if existing:
        old_total = existing["shares"] * existing.get("avg_cost", 0)
        new_total = shares * price
        existing["shares"] += shares
        if existing["shares"] > 0:
            existing["avg_cost"] = round((old_total + new_total) / existing["shares"], 2)
        status, new_shares = "updated", existing["shares"]
    else:
        name = sym
        for s in POPULAR_INDIAN_STOCKS:
            if s["symbol"] == sym:
                name = s["name"]
                break
        user_portfolio.append({"symbol": sym, "name": name, "shares": shares,
                               "avg_cost": round(price, 2)})
        status, new_shares = "added", shares
    _save_portfolio()

    # Only a real price makes a meaningful ledger row — a zero-price row would
    # poison the XIRR solve it exists to feed.
    ledger_added = 0
    if price and price > 0 and shares:
        if not trade_id:
            bucket_len = len(user_equity_txns.get(sym, []))
            trade_id = f"{source}:{sym}:{when}:{bucket_len}"
        ledger_added = equity_txns.merge_trades(user_equity_txns, [{
            "symbol": sym,
            "tradingsymbol": _bare_symbol(sym),
            "exchange": "NSE",
            "date": when,
            "type": "BUY",
            "qty": shares,
            "price": round(float(price), 4),
            "amount": round(shares * float(price), 2),
            "trade_id": trade_id,
            "source": source,
        }])
        if ledger_added:
            _save_equity_txns()

    return {"status": status, "symbol": sym, "new_shares": new_shares,
            "ledger_rows_added": ledger_added, "trade_id": trade_id,
            "price": round(float(price), 2) if price else 0}


@app.post("/api/portfolio/add")
def add_to_portfolio(req: AddStockRequest):
    symbol = _yf_symbol(req.symbol)
    avg_cost = req.avg_cost
    if avg_cost <= 0:
        cur, _ = _fetch_price(symbol)
        avg_cost = cur if cur else 0
    result = _upsert_holding(symbol, req.shares, avg_cost)
    return {"status": result["status"], "symbol": symbol,
            "new_shares": result["new_shares"]}

@app.delete("/api/portfolio/{symbol}")
def remove_from_portfolio(symbol: str):
    global user_portfolio
    sym = _yf_symbol(symbol)
    user_portfolio = [p for p in user_portfolio if p["symbol"] != sym]
    _save_portfolio()
    return {"status": "removed", "symbol": sym}

@app.get("/api/portfolio/watchlist")
def get_watchlist():
    return {"status": "success", "watchlist": user_watchlist}

@app.post("/api/portfolio/watchlist")
def add_to_watchlist(req: WatchlistRequest):
    sym = _yf_symbol(req.symbol)
    for item in user_watchlist:
        if item["symbol"] == sym:
            return {"status": "exists", "symbol": sym}
    name = sym
    for s in POPULAR_INDIAN_STOCKS:
        if s["symbol"] == sym: name = s["name"]; break
    # The date starts the waiting period: a name heard today is not bought
    # today (see conviction.watch_stage).
    user_watchlist.append({"symbol": sym, "name": name,
                           "added_at": date.today().isoformat()})
    _save_watchlist()
    return {"status": "added", "symbol": sym}

@app.delete("/api/portfolio/watchlist/{symbol}")
def remove_from_watchlist(symbol: str):
    global user_watchlist
    sym = _yf_symbol(symbol)
    user_watchlist = [p for p in user_watchlist if p["symbol"] != sym]
    _save_watchlist()
    return {"status": "removed", "symbol": sym}



# ══════════════════════════════════════════════════════════════
#  CONVICTION & POSITION SIZE
# ══════════════════════════════════════════════════════════════
#  The questions to answer BEFORE "has it fallen?": is it a good business,
#  why do I own it, what would make me sell, is it sized sensibly, and did the
#  last quarterly result meet what I expected? See conviction.py.

def _save_conviction():
    _save_json(CONVICTION_FILE, user_conviction)
    threading.Thread(target=_drive_upload_bg, args=("conviction.json",),
                     daemon=True).start()


def _conviction_settings() -> dict:
    return conviction.merge_settings(user_conviction.get("settings"))


def _conviction_inputs(symbols) -> dict:
    """{symbol: (fundamentals, financial?)}, fetched in parallel (cached daily)."""
    def one(sym):
        yf_sym = _history_symbol(_yf_symbol(sym) if not sym.upper().endswith((".NS", ".BO")) else sym)
        try:
            fund = _stock_fundamentals(yf_sym)
        except Exception as e:
            print(f"[Conviction] fundamentals failed for {sym}: {e}")
            fund = {}
        info = _get_stock_info(sym) or {}
        return sym, (fund, conviction.is_financial(
            info.get("sector") or "", info.get("industry") or "", sym))

    out = {}
    unique = list(dict.fromkeys(s for s in symbols if s))
    if not unique:
        return out
    with ThreadPoolExecutor(max_workers=6) as pool:
        for sym, value in pool.map(one, unique):
            out[sym] = value
    return out


def _etf_health() -> dict:
    """Index funds have no business of their own to score."""
    return {"score": None, "grade": "not_applicable",
            "grade_label": "Index fund — no business score", "coverage": 0.0,
            "low_coverage": False, "financial": False, "groups": {},
            "group_labels": conviction.GROUP_LABELS, "checks": []}


@app.get("/api/conviction/board")
def get_conviction_board():
    """Every holding and watchlist name, judged on the business, the thesis
    and the position size — never on the price or the user's average cost."""
    settings = _conviction_settings()
    today = date.today()
    book = get_portfolio(sync_kite=False)
    holdings = [h for h in book.get("holdings", []) if "error" not in h]
    weights, total_value = conviction.weights_by_symbol(holdings)

    theses = user_conviction.setdefault("theses", {})
    snapshots = user_conviction.setdefault("snapshots", {})
    manual = user_conviction.setdefault("manual_results", {})

    held_keys = {conviction.bare_symbol(h.get("symbol")) for h in holdings}
    watch_entries = [w for w in user_watchlist
                     if conviction.bare_symbol(w.get("symbol")) not in held_keys]
    inputs = _conviction_inputs([h.get("symbol") for h in holdings]
                                + [w.get("symbol") for w in watch_entries])

    changed = False
    rows = []
    for h in holdings:
        sym = h.get("symbol")
        key = conviction.bare_symbol(sym)
        fund, financial = inputs.get(sym, ({}, False))
        etf = market_indices.etf_benchmark(sym) is not None
        if not etf:
            snapshots[key], did = conviction.record_snapshot(
                snapshots.get(key), fund, today)
            changed = changed or did
        row = conviction.analyse_holding(
            h, weight_pct=weights.get(key),
            fundamentals=None if etf else fund, financial=financial,
            thesis=theses.get(key), snapshots=snapshots.get(key),
            manual_results=manual.get(key), settings=settings, today=today)
        if etf:
            row["health"] = _etf_health()
            gate = row["add_gate"]
            gate["blockers"] = [
                b for b in gate["blockers"]
                if b not in conviction.DATA_ONLY_BLOCKERS
                and not b.startswith("Business health")]
            gate["allowed"] = not gate["blockers"]
            # The action was chosen before the ETF exemption; choose again.
            row["action"] = conviction.choose_action(
                thesis_state=row["thesis_state"], band=row["size_band"],
                fired=row["fired_triggers"], streak=row["missed_streak"],
                gate=gate, due=row["review_due"], settings=settings)
            row["action_label"] = conviction.ACTION_LABELS[row["action"]]
        row["instrument"] = "etf" if etf else "stock"
        row["value"] = h.get("total_value")
        rows.append(row)
    rows.sort(key=conviction.board_sort_key)

    watch_changed = False
    watch = []
    for entry in watch_entries:
        if not entry.get("added_at"):
            # A name added before dates were recorded starts its wait today
            # rather than being treated as already watched for years.
            entry["added_at"] = today.isoformat()
            watch_changed = True
        sym = entry.get("symbol")
        fund, financial = inputs.get(sym, ({}, False))
        key = conviction.bare_symbol(sym)
        watch.append(conviction.watch_stage(
            entry, thesis=theses.get(key),
            health=conviction.business_health(fund, financial=financial),
            settings=settings, today=today))

    if changed:
        _save_conviction()
    if watch_changed:
        _save_watchlist()

    return {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "settings": settings,
        "results_season": conviction.results_season(today),
        "equity_value": round(total_value, 2),
        "summary": conviction.summarise(rows, watch),
        "holdings": rows,
        "watchlist": watch,
        "trigger_metrics": conviction.TRIGGER_METRICS,
        "trigger_ops": list(conviction.TRIGGER_OPS),
    }


@app.put("/api/conviction/thesis/{symbol}")
def put_conviction_thesis(symbol: str, payload: dict = Body(...)):
    """Save the three answers, expected growth and sell triggers."""
    key = conviction.bare_symbol(symbol)
    if not key:
        raise HTTPException(400, "A symbol is required")
    theses = user_conviction.setdefault("theses", {})
    previous = theses.get(key) or {}
    try:
        thesis = conviction.clean_thesis(
            {**payload, "written_at": previous.get("written_at")})
    except ValueError as e:
        raise HTTPException(400, str(e))
    theses[key] = thesis
    _save_conviction()
    return {"status": "saved", "symbol": key, "thesis": thesis,
            "thesis_state": conviction.thesis_status(thesis, _conviction_settings())}


@app.delete("/api/conviction/thesis/{symbol}")
def delete_conviction_thesis(symbol: str):
    key = conviction.bare_symbol(symbol)
    removed = user_conviction.setdefault("theses", {}).pop(key, None)
    if removed is not None:
        _save_conviction()
    return {"status": "removed" if removed is not None else "absent", "symbol": key}


@app.put("/api/conviction/result/{symbol}")
def put_conviction_result(symbol: str, payload: dict = Body(...)):
    """Record your own verdict on a quarter, or clear it ("result": "clear").

    The automatic verdict compares the feed's growth figure with the thesis;
    this is for when you read the results yourself and judged otherwise.
    """
    key = conviction.bare_symbol(symbol)
    quarter = str(payload.get("quarter") or "").strip()
    result = payload.get("result")
    if not re.fullmatch(r"\d{4}Q[1-4]", quarter):
        raise HTTPException(400, "quarter must look like 2026Q3")
    manual = user_conviction.setdefault("manual_results", {}).setdefault(key, {})
    if result == "clear":
        manual.pop(quarter, None)
    elif result in (conviction.RESULT_MET, conviction.RESULT_MISSED):
        manual[quarter] = {"result": result,
                           "note": str(payload.get("note") or "")[:300],
                           "at": date.today().isoformat()}
    else:
        raise HTTPException(400, "result must be met, missed or clear")
    _save_conviction()
    return {"status": "saved", "symbol": key, "quarter": quarter,
            "manual": manual.get(quarter)}


@app.put("/api/conviction/settings")
def put_conviction_settings(payload: dict = Body(...)):
    merged = conviction.merge_settings(payload)
    user_conviction["settings"] = merged
    _save_conviction()
    return {"status": "saved", "settings": merged}

def _nifty_1y_return():
    """Trailing ~1Y % return of ^NSEI. None on failure."""
    try:
        h = _safe_yf_history("^NSEI", period="1y")
        if h.empty or "Close" not in h or len(h) < 2:
            return None
        closes = h["Close"].dropna()
        if len(closes) < 2:
            return None
        first, last = float(closes.iloc[0]), float(closes.iloc[-1])
        if first <= 0:
            return None
        return round((last / first - 1.0) * 100, 2)
    except Exception:
        return None


@app.get("/api/analytics/portfolio")
def get_portfolio_analytics():
    _empty = {
        "portfolio_beta": None, "sharpe_ratio": None,
        "projected_1y_return": 0, "proj_1y_return": None, "one_year_return": None,
        "nifty_1y_return": _nifty_1y_return(),
        "volatility_index": 0, "volatility": None,
        "diversification_score": 0, "num_sectors": 0, "hhi": None,
        "top_performer": "N/A", "top_performer_pct": None,
        "worst_performer": None, "worst_performer_pct": None,
        "metrics_real": True,
    }
    if not user_portfolio:
        return _empty

    import math as _math

    # ── Per-holding value + net return (since avg cost) + daily close series ──
    holdings = []          # {symbol, shares, value, return_pct}
    close_series = {}      # symbol -> pandas Series (daily close, DatetimeIndex)
    total_value = 0.0
    for item in user_portfolio:
        sym = item["symbol"]
        yf_sym = _yf_symbol(sym)
        cur, _prev = _fetch_price(yf_sym)
        if cur is None or (isinstance(cur, float) and _math.isnan(cur)):
            continue
        shares = item.get("shares", 0)
        avg_cost = item.get("avg_cost", cur) or cur
        value = shares * cur
        total_value += value
        ret_pct = ((cur - avg_cost) / avg_cost * 100) if avg_cost else 0.0
        holdings.append({"symbol": sym, "shares": shares, "value": value, "return_pct": ret_pct})
        # Daily history for the portfolio return series (skip on failure)
        try:
            h = _safe_yf_history(yf_sym, period="1y")
            if not h.empty and "Close" in h:
                s = h["Close"].dropna()
                if len(s) >= 2:
                    close_series[sym] = s
        except Exception:
            pass

    if not holdings:
        return _empty

    # ── Top / worst performer (net return since avg cost) ──
    best = max(holdings, key=lambda x: x["return_pct"])
    worst = min(holdings, key=lambda x: x["return_pct"])
    top_performer = best["symbol"].replace(".NS", "").replace(".BO", "")
    top_performer_pct = round(best["return_pct"], 2)
    if len(holdings) >= 2:
        worst_performer = worst["symbol"].replace(".NS", "").replace(".BO", "")
        worst_performer_pct = round(worst["return_pct"], 2)
    else:
        worst_performer = None
        worst_performer_pct = None

    # ── Diversification via value-weighted HHI + sector count ──
    hhi = None
    div_score = 0
    sectors = set()
    if total_value > 0:
        hhi_sum = 0.0
        for hd in holdings:
            w = hd["value"] / total_value
            hhi_sum += w * w
            try:
                sectors.add(_get_stock_info(hd["symbol"]).get("sector", "Other"))
            except Exception:
                sectors.add("Other")
        hhi = round(hhi_sum, 4)
        div_score = round((1 - hhi_sum) * 100)
    num_sectors = len(sectors)

    # ── Value-weighted daily portfolio return series ──
    portfolio_beta = None
    sharpe_ratio = None
    volatility = None
    one_year_return = None
    try:
        if close_series:
            import pandas as pd
            # Align all holding close series on common dates
            df = pd.DataFrame({sym: s for sym, s in close_series.items()}).dropna()
            if len(df) >= 3:
                # Weight by current value of the holdings that have history
                weights = {}
                wsum = 0.0
                for hd in holdings:
                    if hd["symbol"] in df.columns:
                        weights[hd["symbol"]] = hd["value"]
                        wsum += hd["value"]
                if wsum > 0:
                    port_val = sum(df[sym] * (weights[sym] / df[sym].iloc[0]) for sym in weights)
                    # Trailing 1Y portfolio return %
                    if float(port_val.iloc[0]) > 0:
                        one_year_return = round((float(port_val.iloc[-1]) / float(port_val.iloc[0]) - 1.0) * 100, 2)
                    daily = port_val.pct_change().dropna()
                    if len(daily) >= 2:
                        mean_d = float(daily.mean())
                        std_d = float(daily.std())
                        ann_ret = mean_d * 252
                        ann_vol = std_d * (252 ** 0.5)
                        if ann_vol and not _math.isnan(ann_vol):
                            volatility = round(ann_vol * 100, 2)
                            sharpe_ratio = round((ann_ret - 0.07) / ann_vol, 2)
                        # Beta vs ^NSEI aligned by date
                        try:
                            nh = _safe_yf_history("^NSEI", period="1y")
                            if not nh.empty and "Close" in nh:
                                nser = nh["Close"].dropna()
                                nret = nser.pct_change().dropna()
                                aligned = pd.DataFrame({"p": daily, "n": nret}).dropna()
                                if len(aligned) >= 3:
                                    var_n = float(aligned["n"].var())
                                    if var_n and var_n > 0:
                                        cov = float(aligned["p"].cov(aligned["n"]))
                                        portfolio_beta = round(cov / var_n, 2)
                        except Exception:
                            pass
    except Exception as e:
        print(f"[Analytics] Return-series metrics failed: {e}")

    return {
        "portfolio_beta": portfolio_beta,
        "sharpe_ratio": sharpe_ratio,
        # Backward-compat keys
        "projected_1y_return": one_year_return if one_year_return is not None else 0,
        "proj_1y_return": one_year_return,
        "one_year_return": one_year_return,
        "nifty_1y_return": _nifty_1y_return(),
        "volatility_index": volatility if volatility is not None else 0,
        "volatility": volatility,
        "diversification_score": div_score,
        "num_sectors": num_sectors,
        "hhi": hhi,
        "top_performer": top_performer,
        "top_performer_pct": top_performer_pct,
        "worst_performer": worst_performer,
        "worst_performer_pct": worst_performer_pct,
        "metrics_real": True,
    }

# ──────────────────────────────────────
# EXPOSURE ANALYSIS — Look-through Portfolio Analytics
# ──────────────────────────────────────

# Extended sector mapping for Indian stocks (SEBI classification)
_SECTOR_MAP = {
    # Finance & Banking
    "HDFCBANK.NS": {"sector": "Banking", "industry": "Private Bank", "mcap_class": "Large Cap"},
    "ICICIBANK.NS": {"sector": "Banking", "industry": "Private Bank", "mcap_class": "Large Cap"},
    "SBIN.NS": {"sector": "Banking", "industry": "Public Sector Bank", "mcap_class": "Large Cap"},
    "KOTAKBANK.NS": {"sector": "Banking", "industry": "Private Bank", "mcap_class": "Large Cap"},
    "AXISBANK.NS": {"sector": "Banking", "industry": "Private Bank", "mcap_class": "Large Cap"},
    "INDUSINDBK.NS": {"sector": "Banking", "industry": "Private Bank", "mcap_class": "Large Cap"},
    "BANKBARODA.NS": {"sector": "Banking", "industry": "Public Sector Bank", "mcap_class": "Large Cap"},
    "PNB.NS": {"sector": "Banking", "industry": "Public Sector Bank", "mcap_class": "Mid Cap"},
    # IT
    "TCS.NS": {"sector": "IT", "industry": "IT Services", "mcap_class": "Large Cap"},
    "INFY.NS": {"sector": "IT", "industry": "IT Services", "mcap_class": "Large Cap"},
    "WIPRO.NS": {"sector": "IT", "industry": "IT Services", "mcap_class": "Large Cap"},
    "HCLTECH.NS": {"sector": "IT", "industry": "IT Services", "mcap_class": "Large Cap"},
    "TECHM.NS": {"sector": "IT", "industry": "IT Services", "mcap_class": "Large Cap"},
    "LTIM.NS": {"sector": "IT", "industry": "IT Services", "mcap_class": "Large Cap"},
    # Energy
    "RELIANCE.NS": {"sector": "Energy", "industry": "Oil & Gas", "mcap_class": "Large Cap"},
    "ONGC.NS": {"sector": "Energy", "industry": "Oil & Gas", "mcap_class": "Large Cap"},
    "IOC.NS": {"sector": "Energy", "industry": "Oil & Gas", "mcap_class": "Large Cap"},
    "BPCL.NS": {"sector": "Energy", "industry": "Oil & Gas", "mcap_class": "Large Cap"},
    "VEDL.NS": {"sector": "Mining", "industry": "Mining & Metals", "mcap_class": "Mid Cap"},
    "COALINDIA.NS": {"sector": "Energy", "industry": "Mining", "mcap_class": "Large Cap"},
    "NTPC.NS": {"sector": "Power", "industry": "Power Generation", "mcap_class": "Large Cap"},
    "POWERGRID.NS": {"sector": "Power", "industry": "Power Transmission", "mcap_class": "Large Cap"},
    "ADANIGREEN.NS": {"sector": "Power", "industry": "Renewable Energy", "mcap_class": "Large Cap"},
    # Consumer
    "HINDUNILVR.NS": {"sector": "FMCG", "industry": "FMCG", "mcap_class": "Large Cap"},
    "ITC.NS": {"sector": "FMCG", "industry": "Tobacco & FMCG", "mcap_class": "Large Cap"},
    "NESTLEIND.NS": {"sector": "FMCG", "industry": "Food Products", "mcap_class": "Large Cap"},
    "BRITANNIA.NS": {"sector": "FMCG", "industry": "Food Products", "mcap_class": "Large Cap"},
    "TATACONSUM.NS": {"sector": "FMCG", "industry": "Food & Beverages", "mcap_class": "Large Cap"},
    # Infra & Auto
    "LT.NS": {"sector": "Infrastructure", "industry": "Engineering", "mcap_class": "Large Cap"},
    "TATASTEEL.NS": {"sector": "Metals", "industry": "Steel", "mcap_class": "Large Cap"},
    "JSWSTEEL.NS": {"sector": "Metals", "industry": "Steel", "mcap_class": "Large Cap"},
    "HINDALCO.NS": {"sector": "Metals", "industry": "Aluminium", "mcap_class": "Large Cap"},
    "MARUTI.NS": {"sector": "Auto", "industry": "Passenger Vehicles", "mcap_class": "Large Cap"},
    "TATAMOTORS.NS": {"sector": "Auto", "industry": "Vehicles", "mcap_class": "Large Cap"},
    "M&M.NS": {"sector": "Auto", "industry": "Vehicles", "mcap_class": "Large Cap"},
    "BAJAJ-AUTO.NS": {"sector": "Auto", "industry": "Two-Wheelers", "mcap_class": "Large Cap"},
    # Pharma
    "SUNPHARMA.NS": {"sector": "Pharma", "industry": "Pharmaceuticals", "mcap_class": "Large Cap"},
    "DRREDDY.NS": {"sector": "Pharma", "industry": "Pharmaceuticals", "mcap_class": "Large Cap"},
    "CIPLA.NS": {"sector": "Pharma", "industry": "Pharmaceuticals", "mcap_class": "Large Cap"},
    "DIVISLAB.NS": {"sector": "Pharma", "industry": "Pharmaceuticals", "mcap_class": "Large Cap"},
    # Financials (non-bank)
    "BAJFINANCE.NS": {"sector": "Financial Services", "industry": "NBFC", "mcap_class": "Large Cap"},
    "BAJAJFINSV.NS": {"sector": "Financial Services", "industry": "Holding", "mcap_class": "Large Cap"},
    "HDFCLIFE.NS": {"sector": "Financial Services", "industry": "Insurance", "mcap_class": "Large Cap"},
    "SBILIFE.NS": {"sector": "Financial Services", "industry": "Insurance", "mcap_class": "Large Cap"},
    # Telecom
    "BHARTIARTL.NS": {"sector": "Telecom", "industry": "Telecom Services", "mcap_class": "Large Cap"},
    # Others
    "ASIANPAINT.NS": {"sector": "Consumer Durables", "industry": "Paints", "mcap_class": "Large Cap"},
    "TITAN.NS": {"sector": "Consumer Durables", "industry": "Jewellery", "mcap_class": "Large Cap"},
    "ULTRACEMCO.NS": {"sector": "Cement", "industry": "Cement", "mcap_class": "Large Cap"},
    "GRASIM.NS": {"sector": "Cement", "industry": "Diversified", "mcap_class": "Large Cap"},
    "ADANIENT.NS": {"sector": "Infrastructure", "industry": "Diversified", "mcap_class": "Large Cap"},
    "ADANIPORTS.NS": {"sector": "Infrastructure", "industry": "Ports", "mcap_class": "Large Cap"},
    "EICHERMOT.NS": {"sector": "Auto", "industry": "Motorcycles", "mcap_class": "Large Cap"},
    "HEROMOTOCO.NS": {"sector": "Auto", "industry": "Two-Wheelers", "mcap_class": "Large Cap"},
}

def _load_local_seed(filename: str) -> dict:
    """Read an optional, git-ignored seed file from DATA_DIR ({} if absent)."""
    path = DATA_DIR / filename
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# Seed MF look-through holdings (static factsheet data, refreshed by hand).
# Maps a lowercase scheme_name keyword -> list of {stock, pct}: equity lines
# disclosed at >=1% in the AMC factsheet; sub-1% tail, debt/TREPS/T-bill and
# international lines are omitted from look-through. Nothing is built in:
# look-through normally comes from the per-user store filled by the
# holdings-import endpoint. A local data/mf_known_holdings.json in the same
# shape (git-ignored, like the rest of data/) is used as a fallback seed.
_MF_KNOWN_HOLDINGS: dict = _load_local_seed("mf_known_holdings.json")


def _get_stock_info(symbol: str) -> dict:
    """Get enriched stock info from _SECTOR_MAP or yfinance fallback."""
    # Placeholder symbols (unresolved MF holdings) never hit the network.
    if "_" in symbol:
        return {"sector": "Other", "industry": "Other", "mcap_class": "Small Cap"}
    yf_sym = _yf_symbol(symbol) if not symbol.endswith(".NS") and not symbol.endswith(".BO") else symbol
    # Normalize: try both .NS and .BO variants for lookup
    ns_sym = yf_sym.replace(".BO", ".NS") if yf_sym.endswith(".BO") else yf_sym
    bo_sym = yf_sym.replace(".NS", ".BO") if yf_sym.endswith(".NS") else yf_sym
    # Check _SECTOR_MAP (keys are .NS)
    if ns_sym in _SECTOR_MAP:
        return _SECTOR_MAP[ns_sym]
    if bo_sym in _SECTOR_MAP:
        return _SECTOR_MAP[bo_sym]
    # Fallback to POPULAR_INDIAN_STOCKS (also .NS keys)
    base = yf_sym.replace(".BO", "").replace(".NS", "")
    for s in POPULAR_INDIAN_STOCKS:
        s_base = s["symbol"].replace(".BO", "").replace(".NS", "")
        if s_base == base:
            return {"sector": s["sector"], "industry": s["sector"], "mcap_class": "Mid Cap"}
    # Try yfinance (cached)
    try:
        t = yf.Ticker(yf_sym)
        info = t.info
        return {
            "sector": info.get("sector", "Other"),
            "industry": info.get("industry", "Other"),
            "mcap_class": _classify_mcap(info.get("marketCap", 0)),
        }
    except Exception:
        return {"sector": "Other", "industry": "Other", "mcap_class": "Mid Cap"}


def _classify_mcap(mcap_value: float) -> str:
    """Classify market cap using SEBI-like thresholds (INR)."""
    if mcap_value <= 0:
        return "Unknown"
    # Convert USD to INR approximate
    mcap_inr = mcap_value * 83
    if mcap_inr >= 20000_00_00_000:  # 20,000 Cr+
        return "Large Cap"
    elif mcap_inr >= 5000_00_00_000:  # 5,000 Cr+
        return "Mid Cap"
    elif mcap_inr >= 500_00_00_000:  # 500 Cr+
        return "Small Cap"
    else:
        return "Micro Cap"


def _get_mf_top_holdings(fund: dict) -> list:
    """Get stock holdings for a mutual fund.

    Prefers the user-supplied look-through store (works for ANY fund, refreshed
    via the holdings-import endpoint), then falls back to the built-in seed data.
    """
    scheme_name = fund.get("scheme_name", "")
    stored = _lookup_stored_holdings(scheme_name)
    if stored:
        return stored
    key = scheme_name.lower()
    for k, holdings in _MF_KNOWN_HOLDINGS.items():
        if k in key:
            return holdings
    return []


def _lookup_stored_holdings(scheme_name: str) -> list:
    """Return user-stored look-through holdings for a scheme (exact/CI match)."""
    if not scheme_name or not user_mf_holdings:
        return []
    if scheme_name in user_mf_holdings:
        return user_mf_holdings[scheme_name]
    low = scheme_name.lower().strip()
    for k, v in user_mf_holdings.items():
        if k.lower().strip() == low:
            return v
    return []


# ── Company-name → NSE symbol resolution (for factsheet holdings import) ──
# Seed with fund constituents whose tickers aren't in the Nifty50/popular lists.
_MANUAL_NAME_SYMBOLS = {
    "Power Grid Corporation of India": "POWERGRID.NS",
    "Bajaj Holdings & Investment": "BAJAJHLDNG.NS",
    "Embassy Office Parks REIT": "EMBASSY.NS",
    "Brookfield India Real Estate Trust": "BIRET.NS",
    "Zydus Lifesciences": "ZYDUSLIFE.NS",
    "Indraprastha Gas": "IGL.NS",
    "InterGlobe Aviation": "INDIGO.NS",
    "Eternal": "ETERNAL.NS", "Zomato": "ETERNAL.NS",
    "Federal Bank": "FEDERALBNK.NS",
    "BSE": "BSE.NS",
    "Fortis Healthcare": "FORTIS.NS",
    "Marico": "MARICO.NS",
    "Solar Industries India": "SOLARINDS.NS",
    "Multi Commodity Exchange Of India": "MCX.NS", "MCX": "MCX.NS",
    "Bharat Heavy Electricals": "BHEL.NS",
    "IDFC First Bank": "IDFCFIRSTB.NS",
    "City Union Bank": "CUB.NS",
    "IPCA Laboratories": "IPCALAB.NS",
    "Creditaccess Grameen": "CREDITACC.NS",
    "Radico Khaitan": "RADICO.NS",
    "L&T Finance": "LTF.NS",
    "Bharat Forge": "BHARATFORG.NS",
    "AU Small Finance Bank": "AUBANK.NS",
    "Coforge": "COFORGE.NS",
    "Indian Bank": "INDIANB.NS",
    "JSW Energy": "JSWENERGY.NS",
    "Max Healthcare Institute": "MAXHEALTH.NS",
    "NMDC": "NMDC.NS",
    "Cummins India": "CUMMINSIND.NS",
    "GE Vernova T&D India": "GVT&D.NS",
    "KEI Industries": "KEI.NS",
    "UNO Minda": "UNOMINDA.NS",
    "HDFC Asset Management Company": "HDFCAMC.NS",
    "Indus Towers": "INDUSTOWER.NS",
    "APL Apollo Tubes": "APLAPOLLO.NS",
    "Max Financial Services": "MFSL.NS",
    "Karur Vysya Bank": "KARURVYSYA.NS",
    "Torrent Power": "TORNTPOWER.NS",
    "Ashok Leyland": "ASHOKLEY.NS",
    "Hindustan Petroleum Corporation": "HINDPETRO.NS",
    "Persistent Systems": "PERSISTENT.NS",
    "PB Fintech": "POLICYBZR.NS",
    "Phoenix Mills": "PHOENIXLTD.NS",
    "Polycab India": "POLYCAB.NS",
    "JK Cement": "JKCEMENT.NS",
    "Jindal Stainless": "JSL.NS",
    "Page Industries": "PAGEIND.NS",
    "Ajanta Pharma": "AJANTPHARM.NS",
    "Sundaram Finance": "SUNDARMFIN.NS",
    "Indian Hotels Company": "INDHOTEL.NS", "Indian Hotels": "INDHOTEL.NS",
    "Vishal Mega Mart": "VMM.NS",
    "SRF": "SRF.NS",
    "Bharat Electronics": "BEL.NS",
    "REC": "REC.NS",
    "Sobha": "SOBHA.NS",
    "Arvind": "ARVIND.NS",
    "LT Foods": "LTFOODS.NS",
    "South Indian Bank": "SOUTHBANK.NS",
    "PNB Housing Finance": "PNBHOUSING.NS",
    "Cholamandalam Financial Holdings": "CHOLAHLDNG.NS",
    "Paradeep Phosphates": "PARADEEP.NS",
    "Jubilant Pharmova": "JUBLPHARMA.NS",
    "Yatharth Hospital And Trauma Care Services": "YATHARTH.NS",
    "Rashi Peripherals": "RPTECH.NS",
    "Shaily Engineering Plastics": "SHAILY.NS",
    "Cyient": "CYIENT.NS",
    "One 97 Communications": "PAYTM.NS", "Paytm": "PAYTM.NS",
    "Sky Gold And Diamonds": "SKYGOLD.NS", "Sky Gold": "SKYGOLD.NS",
    "Aditya Birla Real Estate": "ABREL.NS",
    "Great Eastern Shipping Company": "GESHIP.NS",
    "Sun Pharmaceutical Industries": "SUNPHARMA.NS",
    "Lupin": "LUPIN.NS", "NTPC": "NTPC.NS", "Cipla": "CIPLA.NS",
}

_NON_EQUITY_MARKERS = (
    "TREPS", "TBILL", "T-BILL", "TREASURY BILL", "GOI ", " GOI", "SDL",
    "STATE DEVELOPMENT", "NET RECEIVABLE", "NET CURRENT ASSET", "NET ASSET",
    "ACCRUED", "REPO", "CERTIFICATE OF DEPOSIT", "COMMERCIAL PAPER",
    "CLEARING CORP", "364 DAYS", "182 DAYS", "91 DAYS", "TIER 2", "TIER-2",
    "BASEL", "LIQUID FUND", "CASH ", "MARGIN",
)
_FOREIGN_MARKERS = (
    "ALPHABET", "META PLATFORMS", "AMAZON", "MICROSOFT", "APPLE INC",
    "NVIDIA", "TESLA", "NETFLIX", "BROADCOM", "COSTCO",
)


def _norm_company(name: str) -> str:
    """Normalize a company name to a comparable key."""
    n = f" {name.upper()} "
    for w in (" LIMITED ", " LTD. ", " LTD ", " (INDIA) ", " INDIA ",
              " CORPORATION ", " CORP. ", " CORP ", " COMPANY ", " CO. ",
              " & CO ", " PLC ", " INC. ", " INC ", " THE ",
              " REGISTERED SHARES A ", " REIT ", " TRUST "):
        n = n.replace(w, " ")
    n = re.sub(r"[^A-Z0-9& ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _build_name_index() -> dict:
    idx = {}
    for row in NIFTY50_CONSTITUENTS + POPULAR_INDIAN_STOCKS:
        idx[_norm_company(row["name"])] = row["symbol"]
    for name, sym in _MANUAL_NAME_SYMBOLS.items():
        idx[_norm_company(name)] = sym
    return idx


_NAME_INDEX = _build_name_index()


def _resolve_stock_symbol(name: str):
    """Resolve a company name to an NSE symbol.

    Returns (symbol, resolved). When unresolved, symbol is a placeholder key
    (normalized name + '.NS' with underscores) so the same holding still
    overlaps across funds; resolved is False so the caller can surface it.
    """
    norm = _norm_company(name)
    if not norm:
        return None, False
    if norm in _NAME_INDEX:
        return _NAME_INDEX[norm], True
    return norm.replace(" ", "_") + ".NS", False


def _is_non_equity_line(name: str) -> bool:
    """True for debt/cash/bond/derivative lines that aren't equity holdings."""
    u = name.upper()
    if any(m in u for m in _NON_EQUITY_MARKERS):
        return True
    if re.match(r"^\s*\d+(\.\d+)?%?\s", name):   # coupon-prefixed bonds
        return True
    if re.search(r"\(\d{2}/\d{2}/\d{4}\)", name) or " MAT " in u:
        return True
    return False


def _parse_holdings_text(text: str):
    """Parse pasted 'Company<TAB>X.XX%' factsheet rows into look-through holdings.

    Returns (holdings, unresolved). Sub-1% weights (not precisely disclosed),
    debt/cash lines and foreign stocks are skipped.
    """
    holdings, unresolved, seen = [], [], set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("company"):
            continue
        m = re.search(r"(<?\s*\d+(?:\.\d+)?)\s*%", line)
        if not m:
            continue
        name = line[:m.start()].replace("#", "").strip().rstrip("\t ").strip()
        raw_pct = m.group(1)
        try:
            pct = float(raw_pct.replace("<", "").strip())
        except ValueError:
            continue
        if "<" in raw_pct or pct < 1.0 or not name:
            continue
        if _is_non_equity_line(name):
            continue
        if any(f in name.upper() for f in _FOREIGN_MARKERS):
            continue
        sym, resolved = _resolve_stock_symbol(name)
        if not sym or sym in seen:
            continue
        seen.add(sym)
        holdings.append({"stock": sym, "pct": pct, "name": name, "resolved": resolved})
        if not resolved:
            unresolved.append(name)
    holdings.sort(key=lambda h: h["pct"], reverse=True)
    return holdings, unresolved


def _get_stock_fundamentals(symbol: str) -> dict:
    """Get PE, PB, ROE, D/E ratios for a stock."""
    yf_sym = _yf_symbol(symbol) if not symbol.endswith(".NS") and not symbol.endswith(".BO") else symbol
    try:
        t = yf.Ticker(yf_sym)
        info = t.info
        pe = info.get("trailingPE") or info.get("forwardPE") or 0
        pb = info.get("priceToBook") or 0
        roe = info.get("returnOnEquity") or 0
        de = info.get("debtToEquity") or 0
        return {
            "pe": round(pe, 1) if pe else 0,
            "pb": round(pb, 1) if pb else 0,
            "roe": round(roe * 100, 1) if roe and roe < 1 else round(roe, 1) if roe else 0,
            "debt_equity": round(de, 1) if de else 0,
            "market_cap": info.get("marketCap", 0),
            "analyst_rating": info.get("recommendationKey", "hold"),
        }
    except Exception:
        return {"pe": 0, "pb": 0, "roe": 0, "debt_equity": 0, "market_cap": 0, "analyst_rating": "hold"}


@app.get("/api/portfolio/exposure-analysis")
def get_exposure_analysis():
    """
    Comprehensive look-through portfolio exposure analysis.
    Computes: sector exposure, market-cap exposure, overlap analysis,
    concentration risk, and enriched stock/fund data.
    """
    # ── Collect all direct stock holdings ──
    all_holdings = {}  # stock_symbol -> {total_value, sources: [{source_name, weight}]}
    enriched_stocks = []
    total_stock_value = 0
    total_mf_value = 0

    for item in user_portfolio:
        symbol = item["symbol"]
        yf_sym = _yf_symbol(symbol)
        cached = live_price_cache.get(symbol)
        if cached:
            current = cached["current"]
        else:
            current, _ = _fetch_price(yf_sym)
        if current is None:
            continue

        qty = item["shares"]
        avg_cost = item.get("avg_cost", current)
        cur_val = qty * current
        invested = qty * avg_cost
        pnl = cur_val - invested
        net_chg = ((current - avg_cost) / avg_cost * 100) if avg_cost else 0
        total_stock_value += cur_val

        stock_info = _get_stock_info(symbol)

        # Collect for overlap analysis
        if yf_sym not in all_holdings:
            all_holdings[yf_sym] = {"total_value": 0, "sources": [], "name": symbol.replace(".NS", "").replace(".BO", "")}
        all_holdings[yf_sym]["total_value"] += cur_val
        all_holdings[yf_sym]["sources"].append({"source": "Direct Stock", "value": cur_val})

        # Risk score: 1-5 based on volatility proxy
        risk = 3  # default moderate
        if stock_info["mcap_class"] == "Small Cap":
            risk = 4
        elif stock_info["mcap_class"] == "Micro Cap":
            risk = 5
        elif stock_info["mcap_class"] == "Large Cap":
            risk = 2

        enriched_stocks.append({
            "symbol": symbol.replace(".NS", "").replace(".BO", ""),
            "sector": stock_info["sector"],
            "industry": stock_info["industry"],
            "mcap_class": stock_info["mcap_class"],
            "current_price": round(current, 2),
            "shares": qty,
            "avg_cost": round(avg_cost, 2),
            "invested": round(invested, 2),
            "current_value": round(cur_val, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(net_chg, 2),
            "risk_score": risk,
        })

    # ── Process MF holdings with look-through ──
    enriched_funds = []
    for fund in user_mf_portfolio:
        cur_val = fund.get("current_value", 0)
        invested = fund.get("invested", 0)
        total_mf_value += cur_val

        top_holdings = _get_mf_top_holdings(fund)
        # Look-through: add MF's stock holdings to all_holdings
        lc_pct = 0
        mc_pct = 0
        sc_pct = 0
        top_sector = "N/A"
        sector_counts = {}

        for h in top_holdings:
            stock_sym = h["stock"]
            if not stock_sym.endswith(".NS") and not stock_sym.endswith(".BO"):
                continue  # skip international
            weight = h["pct"] / 100
            h_value = cur_val * weight

            if stock_sym not in all_holdings:
                all_holdings[stock_sym] = {"total_value": 0, "sources": [], "name": stock_sym.replace(".NS", "")}
            all_holdings[stock_sym]["total_value"] += h_value
            all_holdings[stock_sym]["sources"].append({
                "source": fund.get("scheme_name", "Unknown MF"),
                "value": round(h_value, 2),
            })

            # Classify
            info = _get_stock_info(stock_sym)
            if info["mcap_class"] == "Large Cap":
                lc_pct += h["pct"]
            elif info["mcap_class"] == "Mid Cap":
                mc_pct += h["pct"]
            else:
                sc_pct += h["pct"]

            sec = info["sector"]
            sector_counts[sec] = sector_counts.get(sec, 0) + h["pct"]

        if sector_counts:
            top_sector = max(sector_counts, key=sector_counts.get)

        # Determine fund style
        cat = fund.get("category", "").lower()
        if "growth" in cat or "flexi" in cat or "small" in cat:
            style = "Growth"
        elif "value" in cat or "dividend" in cat:
            style = "Value"
        else:
            style = "Blend"

        # Overlap score: how many of its top holdings also appear in other funds/direct
        overlap_count = 0
        for h in top_holdings:
            sym = h["stock"]
            if sym in all_holdings and len(all_holdings[sym]["sources"]) > 1:
                overlap_count += 1
        overlap_score = round(overlap_count / max(len(top_holdings), 1) * 100, 0)

        enriched_funds.append({
            "scheme_name": fund.get("scheme_name", ""),
            "category": fund.get("category", "Unknown"),
            "invested": round(invested, 2),
            "current_value": round(cur_val, 2),
            "pnl": round(cur_val - invested, 2),
            "return_pct": round(fund.get("return_pct", 0), 2),
            "xirr": round(fund.get("xirr", 0), 2),
            "lc_pct": round(lc_pct, 1),
            "mc_pct": round(mc_pct, 1),
            "sc_pct": round(sc_pct, 1),
            "top_sector": top_sector,
            "style": style,
            "overlap_score": overlap_score,
            "top_holdings_count": len(top_holdings),
            "risk_score": 3 if "flexi" in cat or "large" in cat else 4 if "mid" in cat else 5 if "small" in cat else 3,
        })

    # ── Compute true sector exposure ──
    total_value = total_stock_value + total_mf_value
    sector_exposure = {}
    mcap_exposure = {"Large Cap": 0, "Mid Cap": 0, "Small Cap": 0, "Micro Cap": 0, "Unknown": 0}

    for sym, data in all_holdings.items():
        info = _get_stock_info(sym)
        sector = info["sector"]
        mcap = info["mcap_class"]
        val = data["total_value"]

        sector_exposure[sector] = sector_exposure.get(sector, 0) + val
        mcap_exposure[mcap] = mcap_exposure.get(mcap, 0) + val

    # Convert to percentages
    sector_pct = {}
    if total_value > 0:
        for sec, val in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True):
            sector_pct[sec] = round(val / total_value * 100, 1)

    mcap_pct = {}
    if total_value > 0:
        for mc, val in mcap_exposure.items():
            mcap_pct[mc] = round(val / total_value * 100, 1)

    # ── Overlap analysis ──
    overlap_holdings = []
    for sym, data in sorted(all_holdings.items(), key=lambda x: x[1]["total_value"], reverse=True):
        if len(data["sources"]) >= 2:
            pct = round(data["total_value"] / total_value * 100, 2) if total_value > 0 else 0
            overlap_holdings.append({
                "stock": data["name"],
                "total_value": round(data["total_value"], 2),
                "exposure_pct": pct,
                "source_count": len(data["sources"]),
                "sources": data["sources"],
            })

    total_overlap_value = sum(h["total_value"] for h in overlap_holdings)
    overlap_pct = round(total_overlap_value / total_value * 100, 1) if total_value > 0 else 0
    duplicate_pct = round(len(overlap_holdings) / max(len(all_holdings), 1) * 100, 1)

    # ── Concentration risk ──
    sorted_holdings = sorted(all_holdings.items(), key=lambda x: x[1]["total_value"], reverse=True)
    top5_val = sum(h[1]["total_value"] for h in sorted_holdings[:5])
    top10_val = sum(h[1]["total_value"] for h in sorted_holdings[:10])
    top5_pct = round(top5_val / total_value * 100, 1) if total_value > 0 else 0
    top10_pct = round(top10_val / total_value * 100, 1) if total_value > 0 else 0
    top_sector_pct = max(sector_pct.values()) if sector_pct else 0
    top_sector_name = max(sector_pct, key=sector_pct.get) if sector_pct else "N/A"
    single_stock_pct = round(sorted_holdings[0][1]["total_value"] / total_value * 100, 1) if sorted_holdings and total_value > 0 else 0

    # Generate alerts
    alerts = []
    if top5_pct > 40:
        alerts.append({"level": "warning", "msg": f"Top 5 holdings concentration is high at {top5_pct}%"})
    if top10_pct > 60:
        alerts.append({"level": "warning", "msg": f"Top 10 holdings account for {top10_pct}% of portfolio"})
    if top_sector_pct > 25:
        alerts.append({"level": "warning", "msg": f"High {top_sector_name} sector exposure at {top_sector_pct}%"})
    if single_stock_pct > 8:
        alerts.append({"level": "critical", "msg": f"Single stock risk: {sorted_holdings[0][0].replace('.NS','').replace('.BO','')} at {single_stock_pct}%"})
    if overlap_pct > 30:
        alerts.append({"level": "warning", "msg": f"Portfolio overlap is {overlap_pct}% — consider reducing duplicate exposure"})
    banking_pct = sector_pct.get("Banking", 0) + sector_pct.get("Financial Services", 0)
    if banking_pct > 30:
        alerts.append({"level": "warning", "msg": f"Excess banking/financial exposure at {round(banking_pct, 1)}%"})

    # Sector risk ratings
    sector_details = []
    sector_targets = {
        "Banking": 20, "IT": 15, "Financial Services": 10, "Energy": 10,
        "FMCG": 10, "Pharma": 8, "Auto": 8, "Infrastructure": 5,
        "Metals": 5, "Telecom": 5, "Power": 5, "Consumer Durables": 4,
    }
    for sec, pct in sorted(sector_pct.items(), key=lambda x: x[1], reverse=True):
        target = sector_targets.get(sec, 5)
        delta = pct - target
        if delta > 5:
            status = "Overweight"
            risk_rating = "High"
        elif delta < -5:
            status = "Underweight"
            risk_rating = "Low"
        else:
            status = "Neutral"
            risk_rating = "Medium"
        sector_details.append({
            "sector": sec,
            "current_pct": pct,
            "target_pct": target,
            "delta": round(delta, 1),
            "status": status,
            "risk_rating": risk_rating,
            "value": round(sector_exposure.get(sec, 0), 2),
        })

    return {
        "total_value": round(total_value, 2),
        "total_stock_value": round(total_stock_value, 2),
        "total_mf_value": round(total_mf_value, 2),
        "unique_holdings": len(all_holdings),

        # True market-cap exposure
        "mcap_exposure": mcap_pct,
        "mcap_values": {k: round(v, 2) for k, v in mcap_exposure.items()},

        # True sector exposure
        "sector_exposure": sector_pct,
        "sector_details": sector_details,

        # Overlap analysis
        "overlap": {
            "overlap_pct": overlap_pct,
            "duplicate_pct": duplicate_pct,
            "hidden_concentration_pct": round(sum(h["exposure_pct"] for h in overlap_holdings[:5]), 1),
            "holdings": overlap_holdings[:20],
        },

        # Concentration risk
        "concentration": {
            "top5_pct": top5_pct,
            "top10_pct": top10_pct,
            "top_sector_pct": top_sector_pct,
            "top_sector_name": top_sector_name,
            "single_stock_pct": single_stock_pct,
            "single_stock_name": sorted_holdings[0][0].replace(".NS", "").replace(".BO", "") if sorted_holdings else "N/A",
            "alerts": alerts,
        },

        # Enriched data
        "enriched_stocks": enriched_stocks,
        "enriched_funds": enriched_funds,

        # Top holdings across everything
        "top_holdings": [
            {
                "stock": h[1]["name"],
                "value": round(h[1]["total_value"], 2),
                "pct": round(h[1]["total_value"] / total_value * 100, 2) if total_value > 0 else 0,
                "source_count": len(h[1]["sources"]),
            }
            for h in sorted_holdings[:20]
        ],

        # Sector holdings for treemap drill-down
        "sector_holdings": _build_sector_holdings(all_holdings, total_value),

        # Source names for overlap grid columns
        "overlap_source_names": _get_overlap_source_names(all_holdings),
    }


def _build_sector_holdings(all_holdings: dict, total_value: float) -> dict:
    """Build sector -> holdings mapping for treemap drill-down."""
    sector_map = {}  # sector -> [{stock, value, pct}]
    for sym, data in all_holdings.items():
        info = _get_stock_info(sym)
        sector = info["sector"]
        name = data["name"]
        val = data["total_value"]
        pct = round(val / total_value * 100, 2) if total_value > 0 else 0
        if sector not in sector_map:
            sector_map[sector] = []
        sector_map[sector].append({
            "stock": name,
            "value": round(val, 2),
            "pct": pct,
        })
    # Sort each sector's holdings by value
    for sec in sector_map:
        sector_map[sec].sort(key=lambda x: x["value"], reverse=True)
    return sector_map


def _get_overlap_source_names(all_holdings: dict) -> list:
    """Get unique source names across all holdings for overlap grid columns."""
    sources = set()
    for _, data in all_holdings.items():
        for s in data["sources"]:
            sources.add(s["source"])
    # Put "Direct Stock" first, then sort alphabetically
    result = sorted(sources)
    if "Direct Stock" in result:
        result.remove("Direct Stock")
        result.insert(0, "Direct Stock")
    return result


# ══════════════════════════════════════════════════════════════════════════
#  DIVIDEND INCOME ANALYSIS
# ══════════════════════════════════════════════════════════════════════════

# symbol -> {"facts": {...}, "fetched_at": ts}.  Dividends change a handful of
# times a year, so a long TTL keeps the section instant after the first load.
_dividend_facts_cache: dict = {}
DIVIDEND_CACHE_TTL = 12 * 60 * 60      # 12 hours


def _fetch_dividend_facts(yf_sym: str) -> dict:
    """
    Pull raw dividend facts for one symbol from yfinance.

    Returns whatever it can — every field is optional downstream, so a symbol
    with no coverage degrades to a zero-payer rather than breaking the book.
    """
    facts: dict = {"history": [], "dividend_rate": 0.0,
                   "trailing_dividend_rate": 0.0, "payout_ratio": 0.0}
    try:
        t = yf.Ticker(yf_sym)
        try:
            series = t.dividends
            if series is not None and len(series) > 0:
                # Only the last ~8 years matter for run-rate and CAGR.
                for ts, amt in series.items():
                    try:
                        facts["history"].append((ts.date().isoformat(), float(amt)))
                    except Exception:
                        continue
                facts["history"] = facts["history"][-40:]
        except Exception as e:
            _safe_print(f"[Dividend] history unavailable for {yf_sym}: {e}")
        try:
            info = t.info or {}
            facts["dividend_rate"] = info.get("dividendRate") or 0.0
            facts["trailing_dividend_rate"] = info.get("trailingAnnualDividendRate") or 0.0
            facts["payout_ratio"] = info.get("payoutRatio") or 0.0
        except Exception as e:
            _safe_print(f"[Dividend] info unavailable for {yf_sym}: {e}")
    except Exception as e:
        _safe_print(f"[Dividend] fetch failed for {yf_sym}: {e}")
    return facts


def _get_dividend_facts(symbol: str, force: bool = False) -> dict:
    """Cached :func:`_fetch_dividend_facts`."""
    yf_sym = _yf_symbol(symbol) if not symbol.endswith((".NS", ".BO")) else symbol
    now = _time.time()
    cached = _dividend_facts_cache.get(yf_sym)
    if cached and not force and (now - cached["fetched_at"]) < DIVIDEND_CACHE_TTL:
        return cached["facts"]
    facts = _fetch_dividend_facts(yf_sym)
    _dividend_facts_cache[yf_sym] = {"facts": facts, "fetched_at": now}
    return facts


def _bare_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "").strip()


# ══════════════════════════════════════════════════════════════
#  REBALANCING
# ══════════════════════════════════════════════════════════════

class RebalanceMarkRequest(BaseModel):
    date: Optional[str] = None


class RebalanceSettingsRequest(BaseModel):
    tax_rates: Optional[Dict[str, float]] = None
    asset_limits: Optional[Dict[str, float]] = None
    long_term_only: Optional[bool] = None
    """A partial update to the rebalance policy.

    Every field is optional and only what is sent is written, so the settings
    screen can save one slider without having to round-trip the rest and risk
    clobbering a change made elsewhere.
    """
    min_weight_pct: Optional[float] = Field(None, ge=0, le=100)
    max_weight_pct: Optional[float] = Field(None, ge=0, le=100)
    deviation_pct: Optional[float] = Field(None, ge=0, le=100)
    cadence: Optional[str] = Field(None, pattern="^(semiannual|annual)$")
    triggers: Optional[List[str]] = None
    boom_gain_pct: Optional[float] = Field(None, ge=0, le=200)
    crash_drop_pct: Optional[float] = Field(None, ge=0, le=100)
    # Explicitly nullable: clearing a custom threshold is a real action, and
    # the trigger has nothing to fire against once it is gone.
    gain_trigger_pct: Optional[float] = Field(None, ge=0, le=1000)
    loss_trigger_pct: Optional[float] = Field(None, ge=0, le=100)
    vol_trigger_pct: Optional[float] = Field(None, ge=0, le=200)
    category_targets: Optional[Dict[str, float]] = None
    mode: Optional[str] = Field(None, pattern="^(auto|manual)$")
    strategy: Optional[str] = None
    selected_categories: Optional[List[str]] = None
    selected_assets: Optional[List[str]] = None
    # Sentinels, because None already means "leave this alone" above. Sending
    # these clears a narrowing back to "everything".
    clear_selected_categories: bool = False
    clear_selected_assets: bool = False
    clear_gain_trigger: bool = False
    clear_loss_trigger: bool = False


def _rebalance_settings() -> dict:
    """The saved policy, as the shape the UI reads and writes."""
    saved_targets = app_settings.get("rebalance_category_targets")
    targets = (rebalance_engine.normalise_targets(saved_targets)[0]
               if saved_targets else None)
    low, high = rebalance_engine.clamp_band(
        app_settings.get("rebalance_min_weight_pct"),
        app_settings.get("rebalance_max_weight_pct"))
    saved = app_settings.get("rebalance_triggers")
    return {
        "asset_limits": app_settings.get("rebalance_asset_limits", {}),
        "long_term_only": app_settings.get("rebalance_long_term_only", True),
        "tax_rates": {"equity_short_term": rebalance_engine.EQUITY_STCG_PCT, "equity_long_term": rebalance_engine.EQUITY_LTCG_PCT, "non_equity_short_term": rebalance_engine.NON_EQUITY_STCG_PCT, "non_equity_long_term": rebalance_engine.NON_EQUITY_LTCG_PCT, **app_settings.get("rebalance_tax_rates", {})},
        "min_weight_pct": low,
        "max_weight_pct": high,
        "deviation_pct": float(app_settings.get(
            "rebalance_deviation_pct", rebalance_engine.DEFAULT_DEVIATION_PCT)),
        "cadence": app_settings.get("rebalance_cadence", "semiannual"),
        "triggers": [t for t in (saved if isinstance(saved, list)
                                 else rebalance_engine.DEFAULT_TRIGGERS)
                     if t in rebalance_engine.ALL_TRIGGERS],
        "boom_gain_pct": float(app_settings.get(
            "rebalance_boom_gain_pct", rebalance_engine.BOOM_YEAR_GAIN_PCT)),
        "crash_drop_pct": float(app_settings.get(
            "rebalance_crash_drop_pct", rebalance_engine.CRASH_DRAWDOWN_PCT)),
        "gain_trigger_pct": app_settings.get("rebalance_gain_trigger_pct"),
        "loss_trigger_pct": app_settings.get("rebalance_loss_trigger_pct"),
        "vol_trigger_pct": float(app_settings.get(
            "rebalance_vol_trigger_pct",
            rebalance_engine.DEFAULT_VOL_TRIGGER_PCT)),
        "category_targets": targets,
        "category_targets_set": bool(saved_targets),
        "default_category_targets": dict(
            rebalance_engine.DEFAULT_CATEGORY_TARGETS),
        "mode": app_settings.get("rebalance_mode", rebalance_engine.MODE_AUTO),
        "strategy": app_settings.get("rebalance_strategy",
                                     rebalance_engine.DEFAULT_STRATEGY),
        "all_strategies": rebalance_engine.STRATEGIES,
        "default_strategy": rebalance_engine.DEFAULT_STRATEGY,
        "selected_categories": app_settings.get("rebalance_selected_categories"),
        "selected_assets": app_settings.get("rebalance_selected_assets"),
        # Reference data, so the UI never has to hard-code the vocabulary.
        "all_triggers": [
            {"name": t, "label": rebalance_engine.TRIGGER_LABELS.get(t, t)}
            for t in rebalance_engine.ALL_TRIGGERS],
        "all_categories": [
            {"name": c, "label": rebalance_engine.CATEGORY_LABELS[c]}
            for c in rebalance_engine.CATEGORIES],
    }


def _cached_peak_ratios(stocks) -> dict:
    """Each holding's last close over its highest close of the past year.

    Read from the price cache ONLY, never fetched. This sits on the critical
    path of opening the Rebalance tab, and nineteen fresh year-long downloads
    would turn that into a two-minute wait — the same mistake the login poller
    was making. A symbol that is not cached simply gets no ratio, and the
    engine falls back to its cost-basis rule for that row.

    The cache is warmed by anything that already pulls a year of history: the
    exposure analysis on the Allocation screen, and the trade-history replay.
    """
    out = {}
    for h in stocks or []:
        symbol = str(h.get("symbol") or "")
        if not symbol:
            continue
        # Try the sibling exchange too. Yahoo carries one bar for many `.BO`
        # tickers while the `.NS` listing of the same company has years, and
        # the history replay caches whichever one it found — so a holding
        # filed as ITC.BO would otherwise never find the ITC.NS series that
        # was already downloaded for it.
        stem, _, suffix = symbol.rpartition(".")
        tickers = [symbol]
        if stem and suffix.upper() in ("NS", "BO"):
            tickers.append(f"{stem}.{'NS' if suffix.upper() == 'BO' else 'BO'}")
        for ticker, period in ((t, p) for p in ("1y", "2y", "5y")
                               for t in tickers):
            entry = _yf_history_cache.get(f"{ticker}:{period}")
            if not entry:
                continue
            frame = entry[1]
            try:
                if frame is None or frame.empty or "Close" not in frame:
                    continue
                closes = [float(v) for v in frame["Close"].tail(260) if v == v]
            except Exception:
                continue
            if len(closes) < 30:
                continue
            high = max(closes)
            if high > 0:
                out[symbol] = round(closes[-1] / high, 4)
                break
    return out


@app.get("/api/portfolio/rebalance/history")
def get_rebalance_history(limit_symbols: int = 60):
    """The tradebook replayed as one ledger page per date you traded.

    Prices are daily closes from the same cached Yahoo path the rest of the
    app uses. A symbol whose history will not download is carried at its held
    quantity with an empty weight rather than dropped, because dropping it
    would change the denominator every other weight is measured against — the
    response says how many rows that affected on each page.
    """
    live = get_live_prices()
    holdings = [h for h in live["holdings"] if h.get("shares")]
    trades = rebalance_history.flatten(user_equity_txns)
    if not trades:
        return {"pages": [], "count": 0, "reconciles": True,
                "note": "No equity transactions on file to replay."}

    # One series per BASE symbol, requested under whichever ticker the app
    # already knows works for it.
    wanted: dict = {}
    for h in holdings:
        wanted.setdefault(rebalance_history.base_symbol(h.get("symbol")),
                          h.get("symbol"))
    for t in trades:
        wanted.setdefault(rebalance_history.base_symbol(t["symbol"]),
                          t["symbol"])

    span = (date.today() - trades[0]["date"]).days
    period = "1y" if span <= 330 else ("2y" if span <= 690 else "5y")
    def _closes(ticker: str) -> list:
        """Daily closes, falling back to the other exchange.

        Yahoo carries almost no history for many `.BO` tickers — ITC.BO
        returns a single row — while the `.NS` listing of the same company has
        years of it. A holding priced from one row is not just thin, it drops
        out of the weight denominator on every page and inflates every other
        holding's percentage, so it is worth a second request to avoid.
        """
        stem, _, suffix = str(ticker).rpartition(".")
        pair = [str(ticker)]
        if stem and suffix.upper() in ("NS", "BO"):
            pair.append(f"{stem}.{'NS' if suffix.upper() == 'BO' else 'BO'}")
        best: list = []
        for candidate in pair:
            try:
                frame = _safe_yf_history(candidate, period=period)
            except Exception as e:
                print(f"[Rebalance history] {candidate}: {e}")
                continue
            if frame is None or frame.empty or "Close" not in frame:
                continue
            rows = [(i.date() if hasattr(i, "date") else i, float(v))
                    for i, v in frame["Close"].items() if v == v]
            if len(rows) > len(best):
                best = rows
            # Enough to cover the replay: no reason to ask twice.
            if best and best[0][0] <= trades[0]["date"]:
                break
        return best

    series: dict = {}
    for key, ticker in list(wanted.items())[:limit_symbols]:
        rows = _closes(str(ticker))
        if rows:
            series[key] = rows

    out = rebalance_history.build_pages(
        holdings, user_equity_txns, rebalance_history.Closes(series))
    out["priced_symbols"] = len(series)
    out["symbols"] = len(wanted)
    return out


@app.get("/api/portfolio/rebalance/strategies")
def get_rebalance_strategies():
    """The selectable presets, with what each one measured in the backtest."""
    return {"strategies": rebalance_engine.STRATEGIES,
            "default": rebalance_engine.DEFAULT_STRATEGY,
            "selected": app_settings.get("rebalance_strategy",
                                         rebalance_engine.DEFAULT_STRATEGY),
            "measured_basis": "Monthly Rs 10,000 into a ten-stock NSE basket, "
                              "2011-2026, after NRI tax. The record of that "
                              "basket on that path, not a forecast."}


@app.get("/api/portfolio/rebalance/settings")
def get_rebalance_settings():
    """The saved rebalance policy, plus the vocabulary the UI renders it with."""
    return _rebalance_settings()


@app.put("/api/portfolio/rebalance/settings")
def save_rebalance_settings(req: RebalanceSettingsRequest):
    """Persist a partial change to the rebalance policy."""
    if req.tax_rates is not None:
        import math
        allowed = {'equity_short_term', 'equity_long_term', 'non_equity_short_term', 'non_equity_long_term'}
        if any(k not in allowed or not math.isfinite(v) or not 0 <= v <= 100 for k, v in req.tax_rates.items()):
            raise HTTPException(status_code=422, detail='Tax rates must be finite percentages between 0 and 100.')
        app_settings['rebalance_tax_rates'] = req.tax_rates
    if req.asset_limits is not None:
        import math
        if any(not math.isfinite(v) or not 0 <= v <= 100 for v in req.asset_limits.values()):
            raise HTTPException(status_code=422, detail='Asset limits must be between 0 and 100.')
        app_settings['rebalance_asset_limits'] = req.asset_limits
    if req.long_term_only is not None:
        app_settings['rebalance_long_term_only'] = req.long_term_only
    if req.min_weight_pct is not None:
        app_settings["rebalance_min_weight_pct"] = req.min_weight_pct
    if req.max_weight_pct is not None:
        app_settings["rebalance_max_weight_pct"] = req.max_weight_pct
        # Setting the ceiling by hand is what "Custom" means. Leaving a preset
        # selected here would claim a rule the plan is no longer following —
        # including for a never-sells preset, where ANY ceiling contradicts the
        # rule rather than merely differing from it.
        if req.strategy is None:
            preset = rebalance_engine.get_strategy(
                app_settings.get("rebalance_strategy"))
            if (preset["id"] != rebalance_engine.STRATEGY_CUSTOM
                    and preset["trim_pct"] != req.max_weight_pct):
                app_settings["rebalance_strategy"] =                     rebalance_engine.STRATEGY_CUSTOM
    if req.deviation_pct is not None:
        app_settings["rebalance_deviation_pct"] = req.deviation_pct
    if req.cadence is not None:
        app_settings["rebalance_cadence"] = req.cadence
    if req.triggers is not None:
        unknown = [t for t in req.triggers
                   if t not in rebalance_engine.ALL_TRIGGERS]
        if unknown:
            # Silently dropping these would leave the user looking at a
            # trigger they believe is armed and is not.
            raise HTTPException(status_code=400,
                                detail=f"Unknown trigger(s): {', '.join(unknown)}")
        app_settings["rebalance_triggers"] = list(dict.fromkeys(req.triggers))
    if req.boom_gain_pct is not None:
        app_settings["rebalance_boom_gain_pct"] = req.boom_gain_pct
    if req.crash_drop_pct is not None:
        app_settings["rebalance_crash_drop_pct"] = req.crash_drop_pct
    if req.vol_trigger_pct is not None:
        app_settings["rebalance_vol_trigger_pct"] = req.vol_trigger_pct
    if req.gain_trigger_pct is not None:
        app_settings["rebalance_gain_trigger_pct"] = req.gain_trigger_pct
    if req.clear_gain_trigger:
        app_settings["rebalance_gain_trigger_pct"] = None
    if req.loss_trigger_pct is not None:
        app_settings["rebalance_loss_trigger_pct"] = req.loss_trigger_pct
    if req.clear_loss_trigger:
        app_settings["rebalance_loss_trigger_pct"] = None
    if req.category_targets is not None:
        unknown = [c for c in req.category_targets
                   if c not in rebalance_engine.CATEGORIES]
        if unknown:
            raise HTTPException(status_code=400,
                                detail=f"Unknown categor(y/ies): {', '.join(unknown)}")
        app_settings["rebalance_category_targets"] = {
            c: float(v) for c, v in req.category_targets.items()}
    if req.mode is not None:
        app_settings["rebalance_mode"] = req.mode
    if req.strategy is not None:
        if req.strategy not in rebalance_engine.STRATEGY_BY_ID:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy: {req.strategy}")
        app_settings["rebalance_strategy"] = req.strategy
        # A preset carries a ceiling, so adopting one MOVES the slider. Keeping
        # two sources of truth for the same number is how a screen ends up
        # showing 10% while the plan trims at 20%.
        ceiling = rebalance_engine.STRATEGY_BY_ID[req.strategy]["trim_pct"]
        if ceiling is not None:
            app_settings["rebalance_max_weight_pct"] = ceiling
    if req.selected_categories is not None:
        app_settings["rebalance_selected_categories"] = [
            c for c in req.selected_categories
            if c in rebalance_engine.CATEGORIES]
    if req.clear_selected_categories:
        app_settings["rebalance_selected_categories"] = None
    if req.selected_assets is not None:
        app_settings["rebalance_selected_assets"] = list(req.selected_assets)
    if req.clear_selected_assets:
        app_settings["rebalance_selected_assets"] = None

    _save_settings(app_settings)
    return _rebalance_settings()


@app.get("/api/portfolio/rebalance")
def get_rebalance_plan(
    cadence: Optional[str] = None,
    residency: str = rebalance_engine.RESIDENT,
    as_of: Optional[str] = None,
    exemption_left: Optional[float] = None,
    min_weight_pct: Optional[float] = None,
    max_weight_pct: Optional[float] = None,
    deviation_pct: Optional[float] = None,
    mode: Optional[str] = None,
    strategy: Optional[str] = None,
    # Gold and debt the user tracks by hand on the allocation screen. They live
    # in the client's local store, so they have to travel with the request:
    # leaving them out would make every other category look heavier than it is.
    manual_gold: float = 0.0,
    manual_debt: float = 0.0,
    # New money to place with this plan. Zero means "just show me the bands",
    # which is what every caller before contributions existed asks for.
    new_money: float = 0.0,
    force: bool = False,
):
    """What to trim, what to top up, and what the tax on doing it would be.

    Reads the saved policy and lets the query override any of it, so the
    screen can preview a slider position without saving it first.

    Every parameter is a plain default rather than a `Query(...)`, and the
    enums are checked in the body. The tests — and `_sync_portfolio_from_kite`
    — call this as an ordinary function, and a `Query` default reaches such a
    caller as a FastAPI object rather than as the value it stands for, which
    then fails the moment anything does arithmetic on it.

    The market tape is fetched but never allowed to fail the request: without
    it the boom, crash and volatility triggers report "unknown" and the band,
    drift and calendar triggers still stand on their own. A rebalance plan that
    disappeared because an index feed timed out would be the worse failure.
    """
    if cadence is not None and cadence not in rebalance_engine.CADENCES:
        raise HTTPException(status_code=422, detail="cadence must be "
                            "'semiannual' or 'annual'")
    if residency not in (rebalance_engine.NRI, rebalance_engine.RESIDENT):
        raise HTTPException(status_code=422,
                            detail="residency must be 'nri' or 'resident'")
    if mode is not None and mode not in (rebalance_engine.MODE_AUTO,
                                         rebalance_engine.MODE_MANUAL):
        raise HTTPException(status_code=422,
                            detail="mode must be 'auto' or 'manual'")
    if strategy is not None and strategy not in rebalance_engine.STRATEGY_BY_ID:
        raise HTTPException(status_code=422,
                            detail=f"Unknown strategy: {strategy}")
    import math as _math
    if not _math.isfinite(new_money) or new_money < 0:
        raise HTTPException(status_code=422,
                            detail="new_money must be zero or a positive "
                                   "amount")
    live = get_live_prices()
    stocks = [h for h in live["holdings"] if h.get("total_value") is not None]

    try:
        tape = _get_index_tape(force=force)
    except Exception as e:
        print(f"[Rebalance] Index tape unavailable: {e}")
        tape = None

    remaining = (exemption_left if exemption_left is not None
                 else app_settings.get("ltcg_exemption_left",
                                       rebalance_engine.EQUITY_LTCG_EXEMPT))
    saved = _rebalance_settings()

    plan = rebalance_engine.build_plan(
        peak_ratios=_cached_peak_ratios(stocks),
        stocks=stocks,
        funds=user_mf_portfolio,
        txns_by_symbol=user_equity_txns,
        manual_assets={rebalance_engine.CAT_GOLD: manual_gold,
                       rebalance_engine.CAT_DEBT: manual_debt},
        as_of=as_of,
        last_rebalanced=app_settings.get("last_rebalanced_at"),
        cadence=cadence or saved["cadence"],
        tape=tape,
        residency=residency,
        exemption_left=float(remaining),
        min_weight_pct=(min_weight_pct if min_weight_pct is not None
                        else saved["min_weight_pct"]),
        max_weight_pct=(max_weight_pct if max_weight_pct is not None
                        else saved["max_weight_pct"]),
        deviation_pct=(deviation_pct if deviation_pct is not None
                       else saved["deviation_pct"]),
        category_targets=saved["category_targets"],
        triggers_enabled=saved["triggers"],
        boom_gain_pct=saved["boom_gain_pct"],
        crash_drop_pct=saved["crash_drop_pct"],
        gain_trigger_pct=saved["gain_trigger_pct"],
        loss_trigger_pct=saved["loss_trigger_pct"],
        vol_trigger_pct=saved["vol_trigger_pct"],
        mode=mode or saved["mode"],
        selected_categories=saved["selected_categories"],
        selected_assets=saved["selected_assets"],
        asset_limits=saved["asset_limits"],
        long_term_only=saved["long_term_only"],
        tax_rates=saved["tax_rates"],
        strategy=strategy or saved["strategy"],
        new_money=float(new_money),
    )
    plan["settings"] = saved
    return plan


@app.post("/api/portfolio/rebalance/mark-done")
def mark_rebalance_done(req: RebalanceMarkRequest = Body(default=None)):
    """Record that a rebalance was carried out, which restarts the clock."""
    stamp = (req.date if req and req.date else datetime.now().date().isoformat())
    app_settings["last_rebalanced_at"] = stamp
    _save_settings(app_settings)
    return {"last_rebalanced_at": stamp}


@app.get("/api/portfolio/dividend-analysis")
def get_dividend_analysis(
    force: bool = False,
    goal_annual: float | None = None,
    monthly_investment: float | None = None,
    other_assets_value: float = 0.0,
):
    """
    Dividend income ledger and goal tracker across direct equity + funds.

    Reads live from ``user_portfolio`` / ``user_mf_portfolio``, so any stock or
    fund added later is picked up with no extra configuration.  ``goal_annual``
    and ``monthly_investment`` default to the saved settings; passing them lets
    the UI preview a what-if without persisting it.
    """
    overrides = {str(k).upper(): v
                 for k, v in (app_settings.get("dividend_overrides") or {}).items()}
    fund_overrides = app_settings.get("dividend_fund_overrides") or {}

    goal = float(goal_annual if goal_annual is not None
                 else app_settings.get("dividend_goal_annual",
                                       dividend_analysis.DEFAULT_GOAL_ANNUAL))
    sip = float(monthly_investment if monthly_investment is not None
                else app_settings.get("dividend_monthly_investment", 0.0))
    slab = float(app_settings.get("dividend_tax_slab_pct",
                                  dividend_analysis.DEFAULT_TAX_SLAB_PCT))

    # ── Direct equity rows ──
    stock_rows = []
    stock_yields: dict = {}          # for mutual-fund look-through
    for item in user_portfolio:
        symbol = item["symbol"]
        yf_sym = _yf_symbol(symbol)
        cached = live_price_cache.get(symbol)
        price = cached["current"] if cached else (_fetch_price(yf_sym)[0] or 0)
        if not price:
            continue

        facts = dict(_get_dividend_facts(yf_sym, force=force))
        bare = _bare_symbol(symbol)
        if bare in overrides:
            facts["manual_dps"] = overrides[bare]

        info = _get_stock_info(symbol)
        row = dividend_analysis.build_stock_row(
            {
                "symbol": symbol,
                "shares": item.get("shares", 0),
                "price": price,
                "avg_cost": item.get("avg_cost", price),
                "sector": info.get("sector", "Other"),
            },
            facts,
        )
        row["mcap_class"] = info.get("mcap_class", "Unknown")
        stock_rows.append(row)
        stock_yields[yf_sym] = row["yield_pct"]
        stock_yields[bare] = row["yield_pct"]

    # ── Mutual fund rows (look-through yield from disclosed top holdings) ──
    fund_rows = []
    for fund in user_mf_portfolio:
        top_holdings = _get_mf_top_holdings(fund)
        # Fill in yields for underlying names we have not priced directly.
        for h in top_holdings:
            sym = h.get("stock", "")
            if not sym.endswith((".NS", ".BO")) or sym in stock_yields:
                continue
            sub_facts = _get_dividend_facts(sym, force=force)
            sub_cached = live_price_cache.get(_bare_symbol(sym))
            if sub_cached:
                sub_price = sub_cached.get("current") or 0
            else:
                sub_price = _fetch_price(sym)[0] or 0
            dps, _src = dividend_analysis.resolve_dps(
                history=sub_facts.get("history"),
                info_rate=sub_facts.get("dividend_rate"),
                trailing_rate=sub_facts.get("trailing_dividend_rate"),
            )
            stock_yields[sym] = round(dps / sub_price * 100, 2) if sub_price else 0.0

        lt_yield = dividend_analysis.lookthrough_yield(top_holdings, stock_yields)
        fund_payload = dict(fund)
        scheme = fund.get("scheme_name", "")
        if scheme in fund_overrides:
            fund_payload["declared_annual_income"] = fund_overrides[scheme]
        fund_rows.append(dividend_analysis.build_fund_row(fund_payload, lt_yield))

    book = dividend_analysis.build_dividend_book(
        stock_rows, fund_rows,
        goal_annual=goal,
        tax_slab_pct=slab,
        monthly_investment=sip,
        other_assets_value=other_assets_value,
    )
    book["disclosure"] = {
        "dps_basis": "Higher of trailing 12 months and last completed fiscal year",
        "fund_income_basis": "IDCW plans only; growth-plan dividends are reinvested",
        "lookthrough_basis": "Weighted by disclosed top holdings",
        "override_count": len(overrides) + len(fund_overrides),
    }
    return book


@app.put("/api/portfolio/dividend-goal")
def set_dividend_goal(payload: dict = Body(...)):
    """
    Persist the dividend goal and its assumptions.

    Accepts any of ``goal_annual``, ``tax_slab_pct``, ``monthly_investment``,
    ``overrides`` (symbol -> annual DPS) and ``fund_overrides``
    (scheme name -> declared annual payout).
    """
    global app_settings
    updates = {}
    if "goal_annual" in payload:
        updates["dividend_goal_annual"] = max(float(payload["goal_annual"] or 0), 0.0)
    if "tax_slab_pct" in payload:
        updates["dividend_tax_slab_pct"] = min(
            max(float(payload["tax_slab_pct"] or 0), 0.0), 100.0)
    if "monthly_investment" in payload:
        updates["dividend_monthly_investment"] = max(
            float(payload["monthly_investment"] or 0), 0.0)
    if "overrides" in payload and isinstance(payload["overrides"], dict):
        updates["dividend_overrides"] = {
            str(k).upper().replace(".NS", "").replace(".BO", ""): float(v or 0)
            for k, v in payload["overrides"].items() if float(v or 0) > 0
        }
    if "fund_overrides" in payload and isinstance(payload["fund_overrides"], dict):
        updates["dividend_fund_overrides"] = {
            str(k): float(v or 0)
            for k, v in payload["fund_overrides"].items() if float(v or 0) > 0
        }
    if not updates:
        raise HTTPException(status_code=400, detail="No recognised dividend settings")
    app_settings.update(updates)
    _save_settings(app_settings)
    return {"status": "saved", "settings": {k: app_settings[k] for k in updates}}


# ══════════════════════════════════════════════════════════════
#  CAPITAL DEPLOYMENT  —  "where does my money go today?"
# ══════════════════════════════════════════════════════════════

# A 52-week high does not move intraday and a fund's NAV peak moves once a day,
# so both are cached hard. Refetching them per board request would mean one
# yfinance/mfapi round trip per holding on every dashboard poll.
_stock_52w_cache: dict = {}          # symbol -> (ts, high)
_STOCK_52W_TTL = REFRESH_SECONDS
_fund_peak_cache: dict = {}          # scheme_name -> (ts, peak_nav)
_FUND_PEAK_TTL = REFRESH_SECONDS       # catches the evening NAV promptly


def _stock_52w_high(sym: str):
    """52-week high for a stock, or None when history is unavailable."""
    now = _time.time()
    hit = _stock_52w_cache.get(sym)
    if hit and (now - hit[0]) < _STOCK_52W_TTL:
        return hit[1]
    high = None
    try:
        hist = _safe_yf_history(sym, period="1y")
        if not hist.empty and "High" in hist:
            value = float(hist["High"].max())
            if value > 0:
                high = round(value, 4)
    except Exception as e:
        print(f"[Deploy] 52w high failed for {sym}: {e}")
    _stock_52w_cache[sym] = (now, high)
    return high


def _fund_nav_peak(fund: dict):
    """All-time NAV peak for a fund from its mfapi history, or None.

    Degrading to None is correct and safe: deploy_engine drops the own-drawdown
    factor to "unknown" rather than scoring the fund as if it were at its peak.
    """
    name = fund.get("scheme_name") or ""
    now = _time.time()
    hit = _fund_peak_cache.get(name)
    if hit and (now - hit[0]) < _FUND_PEAK_TTL:
        return hit[1]
    peak = None
    try:
        code = fund.get("scheme_code")
        if code:
            navs = mf_analysis.parse_navs(mf_analysis.fetch_navs(int(code)))
            values = [n["nav"] for n in navs if n.get("nav")]
            if values:
                peak = round(max(values), 4)
    except Exception as e:
        print(f"[Deploy] NAV peak failed for {name}: {e}")
    _fund_peak_cache[name] = (now, peak)
    return peak


def _deploy_candidates(index_dips: dict) -> tuple:
    """Build the engine's candidate list. All I/O happens here, none in it."""
    targets = app_settings.get("deploy_targets") or {}
    candidates = []

    for fund in user_mf_portfolio:
        name = fund.get("scheme_name")
        if not name:
            continue
        nav = float(fund.get("nav") or 0)
        units = float(fund.get("units") or 0)
        bench, bench_label = mf_analysis.pick_benchmark(
            f"{name} {fund.get('category', '')}")
        candidates.append({
            "kind": deploy_engine.KIND_FUND,
            "key": name,
            "name": name,
            "price": nav or None,
            "units": units,
            "value": float(fund.get("current_value") or 0),
            "avg_cost": float(fund.get("avg_nav") or 0) or None,
            "peak": _fund_nav_peak(fund),
            "peak_basis": "all_time",
            "benchmark": bench,
            "benchmark_label": bench_label,
            "target_pct": targets.get(name),
            "sector": fund.get("category", ""),
        })

    for holding in user_portfolio:
        sym = holding.get("symbol")
        if not sym:
            continue
        price, _src = _fetch_price(sym)
        info = _get_stock_info(sym) or {}
        sector = info.get("sector") or ""
        bench, bench_label = market_indices.benchmark_for_stock(
            sym, sector, info.get("mcap_class", ""))
        shares = float(holding.get("shares") or 0)
        candidates.append({
            "kind": deploy_engine.KIND_STOCK,
            "key": sym,
            "name": holding.get("name") or sym,
            "price": price or None,
            "units": shares,
            "value": (price or 0) * shares,
            "avg_cost": float(holding.get("avg_cost") or 0) or None,
            "peak": _stock_52w_high(sym),
            "peak_basis": "52w",
            "benchmark": bench,
            "benchmark_label": bench_label,
            "target_pct": targets.get(sym),
            "sector": sector,
        })

    return candidates


_headlines_cache: dict = {}
_HEADLINES_TTL = REFRESH_SECONDS


def _headlines_for(yf_sym: str) -> list:
    """Recent headlines for one symbol, cached.

    Uncached, this is the slowest thing on the dashboard by a wide margin: two
    network round trips per holding (yfinance plus a Google News RSS query with
    a 5s timeout), nineteen holdings, and BOTH /portfolio/opportunities and
    /portfolio/stock-dips run the whole sweep independently — so the master
    bar, which is meant to be readable in about five seconds, sat on "Reading
    the market..." for the better part of a minute while the work was done
    twice.

    A six-hour TTL matches the fundamentals cache and suits the data: headlines
    move on the scale of hours, not seconds. Caching also keeps the bar and the
    cards CONSISTENT — both now read the same headline set, so a score cannot
    differ between the two views because one of them refetched and got a
    slightly different feed.
    """
    now = _time.time()
    hit = _headlines_cache.get(yf_sym)
    if hit and (now - hit[0]) < _HEADLINES_TTL:
        return hit[1]
    try:
        titles = [n.get("title", "") for n in (_fetch_news_for_symbol(yf_sym) or [])]
    except Exception:
        # One dead feed degrades that holding's news factor to unknown; it must
        # not take down the sweep, and it must not be cached as "no news".
        return []
    _headlines_cache[yf_sym] = (now, titles)
    return titles


_price_integrity_cache: dict = {}
_PRICE_INTEGRITY_TTL = DAILY_SECONDS   # split detection reads daily bars

# A genuine one-day fall of this size is close to unheard of for a listed
# Indian company; a demerger, split or bonus produces one routinely. Recent
# demergers in large caps showed one-day "falls" of roughly 40-65%, while
# genuine bad days for large caps are typically single digits. The gap between
# the two populations is wide enough that 25% separates them without argument.
CORPORATE_ACTION_1D_MOVE_PCT = 25.0


def _price_integrity(yf_sym: str) -> dict:
    """Flag price history that a corporate action has made uncomparable.

    A demerger drops the quote by half in one session AND removes the spun-off
    entity from the year-on-year revenue line. Both the drawdown and the
    "revenue shrinking" flag then describe an accounting event rather than a
    business in trouble, so stock_dip declines to judge such a holding at all
    rather than confidently reaching the wrong verdict about it.
    """
    now = _time.time()
    hit = _price_integrity_cache.get(yf_sym)
    if hit and (now - hit[0]) < _PRICE_INTEGRITY_TTL:
        return hit[1]

    out = {"corporate_action_suspected": False, "max_1d_move_pct": None,
           "points": 0, "checked": False}
    try:
        hist = _safe_yf_history(yf_sym, period="1y")
        if hist is not None and not hist.empty and "Close" in hist:
            closes = [float(v) for v in hist["Close"].dropna().tolist()]
            out["points"] = len(closes)
            if len(closes) >= 2:
                worst = 0.0
                for prev, cur in zip(closes, closes[1:]):
                    if prev > 0:
                        move = (cur - prev) / prev * 100.0
                        if abs(move) > abs(worst):
                            worst = move
                out["max_1d_move_pct"] = round(worst, 2)
                out["checked"] = True
                out["corporate_action_suspected"] = (
                    abs(worst) >= CORPORATE_ACTION_1D_MOVE_PCT)
    except Exception as e:
        print(f"[StockDip] price integrity check failed for {yf_sym}: {e}")

    _price_integrity_cache[yf_sym] = (now, out)
    return out


_stock_fundamentals_cache: dict = {}
_FUNDAMENTALS_TTL = DAILY_SECONDS      # revenue and debt move quarterly


def _stock_fundamentals(sym: str) -> dict:
    """Map yfinance's info blob onto the fields stock_dip scores.

    A field absent from yfinance is ABSENT from the result, never zero — a
    company whose debt figure did not download must not be scored as debt-free.
    Percentages are normalised here so the pure layer never has to guess
    whether it is holding 0.18 or 18.0; debtToEquity is the exception yfinance
    already reports as a percentage, and is passed through as one.
    """
    now = _time.time()
    hit = _stock_fundamentals_cache.get(sym)
    if hit and (now - hit[0]) < _FUNDAMENTALS_TTL:
        return hit[1]

    out: dict = {}
    try:
        info = yf.Ticker(sym).info or {}

        def put(key, source, scale=1.0):
            v = info.get(source)
            if v is None:
                return
            try:
                out[key] = float(v) * scale
            except (TypeError, ValueError):
                return

        put("pe", "trailingPE")
        put("forward_pe", "forwardPE")
        put("pb", "priceToBook")
        put("roe_pct", "returnOnEquity", 100.0)
        put("debt_to_equity", "debtToEquity")      # already a percentage
        put("profit_margin_pct", "profitMargins", 100.0)
        put("operating_margin_pct", "operatingMargins", 100.0)
        put("free_cashflow", "freeCashflow")
        put("operating_cashflow", "operatingCashflow")
        put("revenue_growth_pct", "revenueGrowth", 100.0)
        put("ev_ebitda", "enterpriseToEbitda")
        put("market_cap", "marketCap")
        put("current_ratio", "currentRatio")
        if "earningsGrowth" in info and info.get("earningsGrowth") is not None:
            put("earnings_growth_pct", "earningsGrowth", 100.0)
        else:
            put("earnings_growth_pct", "earningsQuarterlyGrowth", 100.0)
    except Exception as e:
        print(f"[StockDip] fundamentals failed for {sym}: {e}")

    _stock_fundamentals_cache[sym] = (now, out)
    return out


# Below this many daily bars a 1-year series is not a 52-week record.
_MIN_HISTORY_POINTS = 200
_history_symbol_cache: dict = {}


def _history_symbol(yf_sym: str) -> str:
    """The listing whose price HISTORY should be read for a holding.

    Holdings synced from a BSE demat line arrive as `.BO`, and Yahoo's BSE
    series is often a stub — an ETF's .BO series can serve one bar, so its drawdown, price
    integrity check and fundamentals were all measured on nothing. When the
    `.BO` series is thin and the NSE listing has a real one, the NSE series is
    used; the two exchanges trade the same shares within a paisa or two.
    """
    if not yf_sym.upper().endswith(".BO"):
        return yf_sym
    if yf_sym in _history_symbol_cache:
        return _history_symbol_cache[yf_sym]

    def points(sym):
        try:
            h = _safe_yf_history(sym, period="1y")
            return 0 if h is None or h.empty else int(h["Close"].dropna().shape[0])
        except Exception:
            return 0

    chosen = yf_sym
    if points(yf_sym) < _MIN_HISTORY_POINTS:
        alt = yf_sym[:-3] + ".NS"
        if points(alt) > points(yf_sym):
            chosen = alt
            print(f"[StockDip] {yf_sym} history is thin — reading {alt} instead")
    _history_symbol_cache[yf_sym] = chosen
    return chosen


def _stock_dip_rows(force: bool = False, with_news: bool = True) -> list:
    """Run the stock dip analysis across every equity holding."""
    index_dips = market_indices.dip_map(_get_index_tape(force=force))

    holdings = []
    for h in user_portfolio:
        sym = h.get("symbol")
        if not sym:
            continue
        yf_sym = _yf_symbol(sym) if not (sym.endswith(".NS") or sym.endswith(".BO")) else sym
        holdings.append((h, sym, _history_symbol(yf_sym)))

    # Headlines are the slowest input and the least important, so they are
    # fetched in parallel and a failure degrades one row rather than the board.
    news_by_sym: dict = {}
    if with_news and holdings:
        def grab(item):
            _h, _sym, yf_sym = item
            return yf_sym, _headlines_for(yf_sym)
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for key, titles in pool.map(grab, holdings):
                    news_by_sym[key] = titles
        except Exception as e:
            print(f"[StockDip] news fetch failed: {e}")

    rows = []
    for h, sym, yf_sym in holdings:
        price, _src = _fetch_price(sym)

        etf = market_indices.etf_benchmark(sym)
        if etf:
            bench, bench_label = etf
            high = _stock_52w_high(yf_sym)
            drawdown = (round((high - price) / high * 100.0, 2)
                        if high and price and high > 0 else None)
            rows.append(stock_dip.analyse_etf(
                {"symbol": sym, "name": h.get("name") or sym,
                 "price": price or None,
                 "avg_cost": float(h.get("avg_cost") or 0) or None,
                 "drawdown_pct": drawdown,
                 "benchmark": bench, "benchmark_label": bench_label},
                benchmark_drawdown_pct=index_dips.get(bench),
                study=_study_for(bench, force=force),
                price_integrity=_price_integrity(yf_sym)))
            continue

        info = _get_stock_info(sym) or {}
        sector = info.get("sector") or ""
        bench, bench_label = market_indices.benchmark_for_stock(
            sym, sector, info.get("mcap_class", ""))

        high = _stock_52w_high(yf_sym)
        drawdown = None
        if high and price and high > 0:
            drawdown = round((high - price) / high * 100.0, 2)

        rows.append(stock_dip.analyse_stock(
            {
                "symbol": sym,
                "name": h.get("name") or sym,
                "price": price or None,
                "avg_cost": float(h.get("avg_cost") or 0) or None,
                "drawdown_pct": drawdown,
                "benchmark": bench,
                "benchmark_label": bench_label,
            },
            benchmark_drawdown_pct=index_dips.get(bench),
            fundamentals=_stock_fundamentals(yf_sym),
            headlines=news_by_sym.get(yf_sym),
            price_integrity=_price_integrity(yf_sym),
            # Sector P/E is not available from any feed in use — NSE's index
            # endpoint is unreachable from a script and yfinance carries no
            # sector aggregate. Passing None drops the sector comparison and
            # falls back to price-to-book rather than inventing a peer level.
            sector_pe=None,
        ))

    rows.sort(key=stock_dip.board_sort_key)
    return rows


def _study_for(symbol: str, force: bool = False):
    """The backtest study for one benchmark symbol, or None."""
    if not symbol:
        return None
    payload = _get_dip_backtest(force=force)
    return next((s for s in payload.get("studies", [])
                 if s.get("symbol") == symbol), None)


@app.get("/api/portfolio/fund-dips")
def get_fund_dips(force: bool = False):
    """Per-fund dip context: purchase range, benchmark drawdown and buy zones.

    Deliberately carries no ranking score — /api/portfolio/deploy-board already
    ranks and allocates, and a second score built from overlapping inputs would
    give the dashboard two different answers to the same question. This supplies
    the evidence behind a decision instead.

    Every buy zone carries what ten years of history actually measured at that
    depth for that benchmark, including when the answer is that the depth did
    NOT beat simply buying on a random day.
    """
    index_dips = market_indices.dip_map(_get_index_tape(force=force))
    rows = []
    for fund in user_mf_portfolio:
        name = fund.get("scheme_name")
        if not name:
            continue
        bench, bench_label = mf_analysis.pick_benchmark(
            f"{name} {fund.get('category', '')}")
        rows.append(mf_dip.analyse_fund(
            fund,
            peak_nav=_fund_nav_peak(fund),
            benchmark=bench,
            benchmark_label=bench_label,
            benchmark_drawdown_pct=index_dips.get(bench),
            study=_study_for(bench, force=force),
        ))

    rows.sort(key=mf_dip.board_sort_key)
    return {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "count": len(rows),
        "zone_depths": {k: v for k, v in mf_dip.ZONE_DEPTHS},
        "funds": rows,
    }


@app.get("/api/portfolio/stock-dips")
def get_stock_dips(force: bool = False, with_news: bool = True):
    """Per-stock dip analysis with an explicit reason for every fall.

    The verdict that matters is `reason_for_fall`: a stock down 20% while its
    sector is down 18% is a market move, and one down 20% while its sector is
    flat is not. `averaging_blocked` is a hard gate — when the fundamentals
    show real deterioration it overrides the numeric score, which a collapsing
    price would otherwise push upward.

    Always HTTP 200. Missing inputs lower `confidence` rather than being
    scored as bad news.
    """
    rows = _stock_dip_rows(force=force, with_news=with_news)
    blocked = [r for r in rows if r["averaging_blocked"]]
    corp = [r for r in rows if r.get("corporate_action_suspected")]
    return {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "count": len(rows),
        "blocked_count": len(blocked),
        "corporate_action_count": len(corp),
        "with_news": with_news,
        "factor_weights": stock_dip.DEFAULT_WEIGHTS,
        "min_confidence": stock_dip.MIN_CONFIDENCE,
        "valuation_note": stock_dip.VALUATION_HISTORY_UNAVAILABLE,
        "sector_pe_available": False,
        "stocks": rows,
    }


@app.get("/api/portfolio/opportunities")
def get_opportunities(force: bool = False, with_news: bool = True):
    """The dashboard's master decision bar: what deserves attention today.

    Reuses the fund and stock analyses rather than recomputing them, so the bar
    can never disagree with the cards beneath it.

    A quiet day is a normal answer, not an error: `status="quiet"` means
    nothing met the threshold, and the measured backtest in this app says that
    is the common case. The bar says so plainly instead of surfacing the
    least-bad row as though it were advice.
    """
    tape = _get_index_tape(force=force)
    funds = get_fund_dips(force=force).get("funds", [])
    stocks = _stock_dip_rows(force=force, with_news=with_news)

    board = opportunities.build_board(funds=funds, stocks=stocks, tape=tape)
    board["as_of"] = datetime.now().isoformat(timespec="seconds")
    return board


@app.get("/api/portfolio/deploy-board")
def get_deploy_board(amount: float = 0.0, force: bool = False,
                     score_floor: Optional[float] = None,
                     max_candidates: Optional[int] = None):
    """Rank every holding by how much it deserves new money, and split `amount`.

    `amount=0` is a valid call — the ranking is useful on its own. The
    `score_floor` / `max_candidates` overrides preview a what-if without
    persisting, exactly as dividend-analysis does with goal_annual.
    """
    index_dips = market_indices.dip_map(_get_index_tape(force=force))
    candidates = _deploy_candidates(index_dips)

    opts = {
        "score_floor": score_floor if score_floor is not None
                       else app_settings.get("deploy_score_floor",
                                             deploy_engine.SCORE_FLOOR),
        "max_candidates": max_candidates if max_candidates is not None
                          else app_settings.get("deploy_max_candidates",
                                                deploy_engine.MAX_CANDIDATES_PER_DEPLOY),
        "max_concentration_pct": app_settings.get(
            "deploy_max_concentration_pct", deploy_engine.MAX_CONCENTRATION_PCT),
        "min_ticket_mf": app_settings.get("deploy_min_ticket_mf",
                                          deploy_engine.MIN_TICKET_MF),
    }

    board = deploy_engine.build_deploy_board(
        candidates,
        index_dips=index_dips,
        amount=amount,
        weights=app_settings.get("deploy_weights"),
        legs=app_settings.get("deploy_sip_legs") or [],
        mf_portfolio=user_mf_portfolio,
        equity_ledger=user_equity_txns,
        **opts)
    board["market_mood"] = _get_index_tape().get("market_mood", "unknown")
    board["indices_summary"] = _get_index_tape().get("summary", "")
    return board


class DeployLegModel(BaseModel):
    id: Optional[str] = None
    kind: str
    key: str
    amount: float = 0
    due_day: int = 1
    active: bool = True
    note: str = ""


class DeployPlanRequest(BaseModel):
    sip_legs: Optional[List[DeployLegModel]] = None
    targets: Optional[Dict[str, float]] = None
    weights: Optional[Dict[str, float]] = None
    score_floor: Optional[float] = None
    max_concentration_pct: Optional[float] = None
    max_candidates: Optional[int] = None
    min_ticket_mf: Optional[float] = None


def _deploy_holding_keys() -> tuple:
    """(fund scheme names, equity symbols) — the only valid plan/target keys."""
    funds = [f["scheme_name"] for f in user_mf_portfolio if f.get("scheme_name")]
    stocks = [h["symbol"] for h in user_portfolio if h.get("symbol")]
    return funds, stocks


@app.get("/api/portfolio/deploy-plan")
def get_deploy_plan():
    """The saved plan, plus first-run suggestions and the valid key list."""
    funds, stocks = _deploy_holding_keys()
    prices = {s: (live_price_cache.get(s) or {}).get("current") for s in stocks}
    return {
        "sip_legs": app_settings.get("deploy_sip_legs") or [],
        "targets": app_settings.get("deploy_targets") or {},
        "weights": deploy_engine.normalize_weights(app_settings.get("deploy_weights")),
        "score_floor": app_settings.get("deploy_score_floor",
                                        deploy_engine.SCORE_FLOOR),
        "max_concentration_pct": app_settings.get(
            "deploy_max_concentration_pct", deploy_engine.MAX_CONCENTRATION_PCT),
        "max_candidates": app_settings.get("deploy_max_candidates",
                                           deploy_engine.MAX_CANDIDATES_PER_DEPLOY),
        "min_ticket_mf": app_settings.get("deploy_min_ticket_mf",
                                          deploy_engine.MIN_TICKET_MF),
        "monthly_budget": app_settings.get("deploy_monthly_budget", 30000.0),
        "suggested_legs": deploy_engine.default_legs_from_portfolio(
            user_mf_portfolio, user_portfolio,
            monthly_budget=app_settings.get("deploy_monthly_budget", 30000.0)),
        "suggested_targets": deploy_engine.default_targets_from_portfolio(
            user_mf_portfolio, user_portfolio, prices=prices),
        "holdings": {"funds": funds, "stocks": stocks},
        "defaults": {
            "score_floor": deploy_engine.SCORE_FLOOR,
            "max_concentration_pct": deploy_engine.MAX_CONCENTRATION_PCT,
            "max_candidates": deploy_engine.MAX_CANDIDATES_PER_DEPLOY,
            "min_ticket_mf": deploy_engine.MIN_TICKET_MF,
            "weights": deploy_engine.DEFAULT_WEIGHTS,
        },
    }


@app.put("/api/portfolio/deploy-plan")
def set_deploy_plan(req: DeployPlanRequest):
    """Partial update of the deployment plan — only supplied fields are touched.

    Keys are validated against live holdings: a leg or target pointing at
    something the user no longer owns is a silent dead entry that would confuse
    every downstream reading, so it is rejected loudly instead.
    """
    global app_settings
    funds, stocks = _deploy_holding_keys()
    updates = {}

    if req.sip_legs is not None:
        legs = []
        for leg in req.sip_legs:
            kind = (leg.kind or "").strip().lower()
            if kind not in (deploy_engine.KIND_FUND, deploy_engine.KIND_STOCK):
                raise HTTPException(status_code=400,
                                    detail=f"Unknown kind '{leg.kind}' for '{leg.key}'")
            key = _yf_symbol(leg.key) if kind == deploy_engine.KIND_STOCK else leg.key
            valid = stocks if kind == deploy_engine.KIND_STOCK else funds
            if key not in valid:
                raise HTTPException(status_code=400,
                                    detail=f"'{leg.key}' is not in your portfolio")
            legs.append({
                "id": leg.id or f"leg_{uuid.uuid4().hex[:8]}",
                "kind": kind,
                "key": key,
                "label": key,
                "amount": max(float(leg.amount or 0), 0.0),
                "due_day": min(max(int(leg.due_day or 1), 1), 31),
                "active": bool(leg.active),
                "note": leg.note or "",
            })
        updates["deploy_sip_legs"] = legs

    if req.targets is not None:
        clean = {}
        for raw_key, raw_pct in req.targets.items():
            pct = min(max(float(raw_pct or 0), 0.0), 100.0)
            if pct <= 0:
                continue
            key = raw_key if raw_key in funds else _yf_symbol(raw_key)
            if key not in funds and key not in stocks:
                raise HTTPException(status_code=400,
                                    detail=f"'{raw_key}' is not in your portfolio")
            clean[key] = round(pct, 2)
        updates["deploy_targets"] = clean

    if req.weights is not None:
        updates["deploy_weights"] = deploy_engine.normalize_weights(req.weights)
    if req.score_floor is not None:
        updates["deploy_score_floor"] = min(max(float(req.score_floor), 0.0), 100.0)
    if req.max_concentration_pct is not None:
        updates["deploy_max_concentration_pct"] = min(
            max(float(req.max_concentration_pct), 1.0), 100.0)
    if req.max_candidates is not None:
        updates["deploy_max_candidates"] = max(int(req.max_candidates), 1)
    if req.min_ticket_mf is not None:
        updates["deploy_min_ticket_mf"] = max(float(req.min_ticket_mf), 0.0)

    if not updates:
        raise HTTPException(status_code=400, detail="No recognised deployment settings")
    app_settings.update(updates)
    _save_settings(app_settings)
    return {"status": "saved", "settings": {k: app_settings[k] for k in updates}}


class DeployItem(BaseModel):
    kind: str                       # "fund" | "stock"
    key: str
    amount: float = 0               # funds: rupees
    shares: int = 0                 # stocks: whole shares
    price: float = 0                # NAV / share price; 0 -> resolve live
    date: Optional[str] = None      # YYYY-MM-DD, defaults to today
    tag: str = "opportunistic"      # "sip" | "opportunistic"
    leg_id: Optional[str] = None


class DeployExecuteRequest(BaseModel):
    request_id: str                 # REQUIRED, client-generated
    items: List[DeployItem]
    note: str = ""


@app.post("/api/portfolio/deploy-execute")
def deploy_execute(req: DeployExecuteRequest):
    """Record a batch of buys against the portfolio. Places NO broker order.

    Batch rather than one-at-a-time because the proposal *is* a split: per-item
    requests would leave a partial failure half-recorded with no single id to
    retry against.

    Idempotency has three layers — this endpoint's request_id check, the
    deterministic trade_id that equity_txns.merge_trades dedupes on, and the
    `ref` stamped on MF transactions. The request_id is deliberately
    client-generated; a server-side fallback would defeat the whole purpose.
    """
    global user_deploy_log

    if not req.request_id:
        raise HTTPException(status_code=400, detail="request_id is required")

    for entry in user_deploy_log:
        if entry.get("request_id") == req.request_id:
            return {**entry.get("result", {}), "status": "duplicate"}

    if not req.items:
        raise HTTPException(status_code=422, detail="No items to record")

    today = datetime.now().strftime("%Y-%m-%d")

    # ── Validate the WHOLE batch before applying any of it ──
    planned = []
    for i, item in enumerate(req.items):
        kind = (item.kind or "").strip().lower()
        when = item.date or today
        if kind == deploy_engine.KIND_FUND:
            fund = next((f for f in user_mf_portfolio
                         if f.get("scheme_name") == item.key), None)
            if not fund:
                raise HTTPException(status_code=422,
                                    detail=f"Fund not found: {item.key}")
            if item.amount <= 0:
                raise HTTPException(status_code=422,
                                    detail=f"Amount must be positive for {item.key}")
            nav = float(item.price or 0) or float(fund.get("nav") or 0)
            if nav <= 0:
                raise HTTPException(status_code=422,
                                    detail=f"No NAV available for {item.key}")
            planned.append({"kind": kind, "fund": fund, "key": item.key,
                            "amount": round(float(item.amount), 2), "price": nav,
                            "date": when, "index": i, "tag": item.tag,
                            "leg_id": item.leg_id})
        elif kind == deploy_engine.KIND_STOCK:
            sym = _yf_symbol(item.key)
            if item.shares < 1:
                raise HTTPException(status_code=422,
                                    detail=f"Shares must be at least 1 for {item.key}")
            price = float(item.price or 0)
            if price <= 0:
                price, _src = _fetch_price(sym)
            if not price or price <= 0:
                raise HTTPException(status_code=422,
                                    detail=f"No price available for {item.key}")
            planned.append({"kind": kind, "key": sym, "shares": int(item.shares),
                            "price": float(price), "date": when, "index": i,
                            "tag": item.tag, "leg_id": item.leg_id})
        else:
            raise HTTPException(status_code=422, detail=f"Unknown kind: {item.kind}")

    # ── Apply. The two JSON stores are not transactional, so a mid-apply
    #    failure is reported honestly as "partial" rather than pretending
    #    an atomicity we do not have. ──
    recorded, failed = [], []
    for plan in planned:
        trade_id = f"deploy:{req.request_id}:{plan['index']}"
        try:
            if plan["kind"] == deploy_engine.KIND_FUND:
                fund = plan["fund"]
                if any(t.get("ref") == trade_id
                       for t in fund.get("transactions", []) or []):
                    continue
                units = round(plan["amount"] / plan["price"], 3)
                _append_mf_txn(fund, {
                    "date": plan["date"], "invested": plan["amount"],
                    "redeemed": 0, "units": units, "nav": plan["price"],
                    "ref": trade_id, "tag": plan["tag"],
                })
                recorded.append({"kind": "fund", "key": plan["key"],
                                 "amount": plan["amount"], "units": units,
                                 "nav": plan["price"], "date": plan["date"]})
            else:
                res = _upsert_holding(plan["key"], plan["shares"], plan["price"],
                                      date=plan["date"], trade_id=trade_id,
                                      source="deploy")
                recorded.append({"kind": "stock", "key": plan["key"],
                                 "shares": plan["shares"], "price": plan["price"],
                                 "amount": round(plan["shares"] * plan["price"], 2),
                                 "date": plan["date"],
                                 "ledger_rows_added": res["ledger_rows_added"]})
        except Exception as e:
            print(f"[Deploy] Failed to record {plan['key']}: {e}")
            failed.append({"key": plan["key"], "error": str(e)})

    result = {
        "status": "partial" if failed else "recorded",
        "request_id": req.request_id,
        "recorded": recorded,
        "failed": failed,
        "totals": {"amount": round(sum(r["amount"] for r in recorded), 2),
                   "count": len(recorded)},
        "note": req.note,
    }
    user_deploy_log.append({
        "request_id": req.request_id,
        "at": datetime.now().isoformat(timespec="seconds"),
        "result": result,
    })
    _save_deploy_log()
    return result


@app.get("/api/portfolio/deploy-history")
def get_deploy_history(limit: int = 50):
    """Newest-first audit trail of recorded deployments. Read-only."""
    entries = list(reversed(user_deploy_log))[:max(int(limit), 1)]
    return {"entries": entries, "total": len(user_deploy_log)}


@app.post("/api/deep-signals/start")
def start_deep_signals():
    global deep_signal_running
    if deep_signal_running:
        return {"status": "already_running"}
    for item in user_portfolio:
        deep_signal_cache[item["symbol"]] = {"status": "pending"}
    t = threading.Thread(target=_run_deep_signal_bg, daemon=True)
    t.start()
    return {"status": "started", "count": len(user_portfolio)}

@app.get("/api/deep-signals")
def get_deep_signals():
    return {"signals": deep_signal_cache, "running": deep_signal_running}

@app.get("/api/test")
def test_endpoint():
    return {"hello": "world"}

# ══════════════════════════════════════════════════════════════
#  DEEP ANALYSIS — Async Job System (no timeout issues)
# ══════════════════════════════════════════════════════════════
_deep_jobs: dict = {}  # job_id -> {status, current_agent, agents_done, result, error, started_at}

def _run_deep_analysis_bg(job_id: str, symbol: str):
    """Background thread: runs 9-agent pipeline and updates job status."""
    import time
    job = _deep_jobs[job_id]
    yf_sym = _yf_symbol(symbol)
    try:
        ticker = yf.Ticker(yf_sym)
        history = _safe_yf_history(yf_sym, period="1y")
        if history.empty:
            job["status"] = "error"
            job["error"] = f"No data for {symbol}"
            return
        sector = "Other"
        for s in POPULAR_INDIAN_STOCKS:
            if s["symbol"] == yf_sym: sector = s["sector"]; break

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # ── Phase 1: Data extraction ──
        job["current_agent"] = "Data Collection"
        job["current_agent_idx"] = 0
        info = {}
        if hasattr(ticker, 'fast_info'):
            try:
                fi = ticker.fast_info
                for attr in ['last_price', 'open', 'previous_close', 'day_high', 'day_low',
                             'year_high', 'year_low', 'market_cap', 'shares', 'currency',
                             'fifty_day_average', 'two_hundred_day_average']:
                    try:
                        val = getattr(fi, attr, None)
                        if val is not None: info[attr] = val
                    except: pass
            except: pass
        if hasattr(ticker, 'info'):
            try:
                raw_info = ticker.info
                if isinstance(raw_info, dict):
                    info.update(raw_info)
            except: pass
        # ── Build portfolio context: does user hold this stock? ──
        portfolio_ctx = {"is_held": False}
        base_sym = symbol.replace(".BO", "").replace(".NS", "")
        for item in user_portfolio:
            item_base = item["symbol"].replace(".BO", "").replace(".NS", "")
            if item_base == base_sym:
                qty = item.get("shares", 0)
                avg_cost = item.get("avg_cost", 0)
                invested = qty * avg_cost
                current_price = info.get("last_price") or info.get("currentPrice") or info.get("previousClose", 0)
                current_value = qty * current_price if current_price else invested
                pnl = current_value - invested
                pnl_pct = (pnl / invested * 100) if invested > 0 else 0
                # Portfolio weight
                total_portfolio = sum(
                    p.get("shares", 0) * (live_price_cache.get(p["symbol"], {}).get("current") or p.get("avg_cost", 0))
                    for p in user_portfolio
                )
                weight_pct = (current_value / total_portfolio * 100) if total_portfolio > 0 else 0
                portfolio_ctx = {
                    "is_held": True,
                    "shares": qty,
                    "avg_cost": round(avg_cost, 2),
                    "invested": round(invested, 2),
                    "current_value": round(current_value, 2),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "portfolio_weight_pct": round(weight_pct, 1),
                }
                _safe_print(f"[DEEP] Portfolio context: {qty} shares @ Rs.{avg_cost:.0f}, "
                      f"P&L: Rs.{pnl:.0f} ({pnl_pct:.1f}%), Weight: {weight_pct:.1f}%")
                break

        data_ctx = loop.run_until_complete(ai_models.run_data_agent(symbol, info, history, [], sector, ticker_obj=ticker, portfolio_ctx=portfolio_ctx))
        job["agents_done"].append("data")

        # ── Phase 2: Independent agents (concurrent) ──
        agent_names = ["Fundamental", "Technical", "Sentiment", "Macro", "Quant", "Risk"]
        agent_keys = ["fundamental", "technical", "news", "macro", "quant", "risk"]
        tasks_fns = [
            ai_models.run_fundamental_agent,
            ai_models.run_technical_agent,
            ai_models.run_news_agent,
            ai_models.run_macro_agent,
            ai_models.run_quant_agent,
            ai_models.run_risk_agent,
        ]

        agents_output = {}
        for i, (name, key, fn) in enumerate(zip(agent_names, agent_keys, tasks_fns)):
            job["current_agent"] = name
            job["current_agent_idx"] = i + 1  # 0 was data
            try:
                result = loop.run_until_complete(fn(data_ctx))
                agents_output[key] = result
            except Exception as e:
                agents_output[key] = {"error": str(e), "verdict": "ERROR"}
            job["agents_done"].append(key)

        # ── Phase 3: Execution Agent ──
        job["current_agent"] = "Execution"
        job["current_agent_idx"] = 7
        try:
            execution = loop.run_until_complete(ai_models.run_trade_structuring_agent(data_ctx))
            agents_output["execution"] = execution
        except Exception as e:
            agents_output["execution"] = {"error": str(e)}
        job["agents_done"].append("execution")

        # ── Phase 4: Master CIO ──
        job["current_agent"] = "Master CIO"
        job["current_agent_idx"] = 8
        try:
            cio_report = loop.run_until_complete(ai_models.run_master_cio_agent(symbol, agents_output, portfolio_ctx=portfolio_ctx))
        except Exception as e:
            cio_report = {"error": str(e), "final_decision": "HOLD"}
        job["agents_done"].append("cio")

        loop.close()

        job["result"] = {
            "symbol": symbol,
            "agents": agents_output,
            "cio_report": cio_report,
        }
        job["status"] = "done"
        _safe_print(f"[DEEP] Analysis complete for {symbol} in {time.time() - job['started_at']:.1f}s")

    except Exception as e:
        import traceback
        job["status"] = "error"
        job["error"] = traceback.format_exc()
        _safe_print(f"[ERROR] Deep analysis failed for {symbol}:\n{job['error']}")


@app.post("/api/stock/{symbol}/deep-analysis/start")
def start_deep_analysis(symbol: str):
    """Start deep analysis in background, return job ID immediately."""
    import time, uuid
    job_id = f"{symbol}_{uuid.uuid4().hex[:8]}"
    _deep_jobs[job_id] = {
        "status": "running",
        "symbol": symbol,
        "current_agent": "Initializing",
        "current_agent_idx": 0,
        "agents_done": [],
        "result": None,
        "error": None,
        "started_at": time.time(),
    }
    t = threading.Thread(target=_run_deep_analysis_bg, args=(job_id, symbol), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "running"}


@app.get("/api/deep-analysis/status/{job_id}")
def get_deep_analysis_status(job_id: str):
    """Poll for analysis progress and results."""
    import time
    if job_id not in _deep_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _deep_jobs[job_id]
    elapsed = time.time() - job["started_at"]
    resp = {
        "job_id": job_id,
        "status": job["status"],
        "symbol": job["symbol"],
        "current_agent": job["current_agent"],
        "current_agent_idx": job["current_agent_idx"],
        "agents_done": job["agents_done"],
        "total_agents": 9,
        "elapsed_seconds": round(elapsed, 1),
    }
    if job["status"] == "done":
        resp["result"] = job["result"]
        # Cleanup old jobs (keep for 5 min after completion)
    elif job["status"] == "error":
        resp["error"] = job["error"]
    return resp


# Legacy synchronous endpoint (kept for backward compat)
@app.get("/api/stock/{symbol}/deep-analysis")
async def get_deep_analysis(symbol: str):
    yf_sym = _yf_symbol(symbol)
    try:
        ticker = yf.Ticker(yf_sym)
        history = _safe_yf_history(yf_sym, period="1y")
        if history.empty: raise HTTPException(status_code=400, detail=f"No data for {symbol}")
        sector = "Other"
        for s in POPULAR_INDIAN_STOCKS:
            if s["symbol"] == yf_sym: sector = s["sector"]; break
        result = await ai_models.run_full_analysis_async(ticker, yf_sym, history, [], sector)
        return result
    except HTTPException: raise
    except Exception as e: 
        import traceback
        tb = traceback.format_exc()
        _safe_print(f"[ERROR] Deep analysis failed:\n{tb}")
        raise HTTPException(status_code=500, detail=tb)

@app.get("/api/stock/{symbol}/quote")
def get_live_quote(symbol: str):
    yf_sym = _yf_symbol(symbol)
    try:
        ticker = yf.Ticker(yf_sym)
        hist = _safe_yf_history(yf_sym, period="5d")
        if hist.empty: raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        current = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2] if len(hist) >= 2 else current
        return {"symbol": symbol, "current_price": round(current, 2), "previous_close": round(prev, 2),
                "change_pct": round(((current - prev) / prev) * 100, 2)}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/nifty50")
def get_nifty50():
    try:
        h = _safe_yf_history("^NSEI", period="5d")
        if h.empty: return {"error": "No data"}
        cur = h["Close"].iloc[-1]; prev = h["Close"].iloc[-2] if len(h) >= 2 else cur
        return {"symbol": "NIFTY 50", "current": round(cur, 2), "change_pct": round(((cur - prev) / prev) * 100, 2)}
    except Exception as e: return {"error": str(e)}

def _download_index_frames(symbols: List[str], period: str) -> Dict[str, tuple]:
    """Batched daily closes AND dates for the index universe.

    One yf.download for all ~34 symbols rather than 34 sequential
    _safe_yf_history calls — same idiom as get_nifty50_constituents. A symbol
    Yahoo cannot resolve comes back as empty lists, which
    market_indices.summarize_index turns into an `unavailable` row.

    Dates come back alongside closes because the year-to-date column has no
    correct trading-day offset — it has to know where the year actually broke.
    """
    out: Dict[str, tuple] = {s: ([], []) for s in symbols}
    data = yf.download(symbols, period=period, group_by="ticker",
                       progress=False, threads=True)
    for sym in symbols:
        try:
            if sym not in data:
                continue
            closes = data[sym]["Close"].dropna()
            dates = [d.date() if hasattr(d, "date") else d for d in closes.index]
            out[sym] = (dates, [float(v) for v in closes.tolist()])
        except Exception:
            # One bad frame must not cost us the other thirty-three.
            continue
    return out


def _get_index_history(force: bool = False) -> Dict[str, tuple]:
    """Ten years of daily closes per index, cached for hours.

    Also the source the dip backtest reads, so the decade is downloaded once
    and serves both the tape's long-window statistics and the threshold study.
    On failure the previous history is reused; an empty dict is the last
    resort and degrades every long-window field to unknown rather than wrong.
    """
    now = _time.time()
    cached = _index_history_cache["data"]
    if not force and cached and (now - _index_history_cache["ts"]) < _INDEX_HISTORY_TTL:
        return cached
    try:
        frames = _download_index_frames(list(market_indices.UNIVERSE_SYMBOLS),
                                        _INDEX_HISTORY_PERIOD)
        if not any(closes for _, closes in frames.values()):
            raise RuntimeError("history download returned nothing")

        # Truncate split-like discontinuities once, here, so the tape and the
        # backtest both see the same clean series. GOLDBEES.NS steps +9,900% on
        # 2019-12-23 (a unit split); untrimmed it produced a 6,463% "mean
        # forward return" in the dip study and a nonsensical full-series low.
        for sym, (dts, closes) in list(frames.items()):
            clean_closes, clean_dates, info = market_indices.trim_corporate_actions(
                closes, dts)
            if info["trimmed"]:
                print(f"[IndexTape] {sym}: dropped {info['dropped']} bars before "
                      f"a corporate action ({info['events'][-1]['move_pct']:+.0f}% "
                      f"on {info['events'][-1]['date']})")
            frames[sym] = (clean_dates, clean_closes)
        _index_history_cache["ts"] = now
        _index_history_cache["data"] = frames
        return frames
    except Exception as e:
        print(f"[IndexTape] History fetch failed: {e}")
        return cached if cached else {}


# Instrument tokens are stable, so they are looked up once per process rather
# than on every fifteen-second tape refresh.
_kite_token_cache: dict = {}
# Daily candles fetched from Kite, kept a whole day. Re-fetching a DAILY series
# on every tape refresh is what tripped Kite's rate limit: fifteen token
# lookups plus fifteen history calls in one burst returned 429, the stream
# died, the resume was refused and the user's Zerodha login went with it. The
# data changes once a day; so does the fetch.
_kite_history_cache: dict = {"day": None, "series": {}}
# How many NEW indices may be fetched in one tape build. The rest fill in on
# later refreshes, so the gap closes over a few minutes instead of arriving as
# a burst that costs a login.
KITE_HISTORY_PER_PASS = 4
# A breath between calls, for the same reason.
KITE_CALL_SPACING_SECONDS = 0.4


def _kite_index_history(symbols) -> dict:
    """Daily closes from Kite for indices whose Yahoo series is unusable.

    Returns {yahoo symbol: (dates, closes)} for the ones that answered. A
    symbol that cannot be resolved, refuses, or comes back too short is simply
    absent — the caller then keeps whatever it already had, which is the right
    outcome when the alternative is replacing a thin series with an empty one.
    """
    today = date.today()
    # Serve the day's cache first; only genuinely new symbols cost a call.
    if _kite_history_cache["day"] != today.isoformat():
        _kite_history_cache["day"] = today.isoformat()
        _kite_history_cache["series"] = {}
    cached = _kite_history_cache["series"]
    out = {sym: cached[sym] for sym in symbols if sym in cached}
    todo = [s for s in symbols if s not in cached][:KITE_HISTORY_PER_PASS]
    if not todo:
        return out
    symbols = todo
    to_date = f"{today.isoformat()} 23:59:59"
    # A little over a year, so a 52-week window is actually covered once
    # non-trading days are removed.
    from_date = f"{(today - timedelta(days=400)).isoformat()} 00:00:00"
    for sym in symbols:
        instrument = market_indices.KITE_INDEX.get(sym)
        if not instrument:
            continue
        token = _kite_token_cache.get(instrument)
        if token is None:
            token = kite_client.resolve_instrument_token(instrument)
            _time.sleep(KITE_CALL_SPACING_SECONDS)
            if token:
                _kite_token_cache[instrument] = token
        if not token:
            continue
        candles = kite_client.get_index_history(token, from_date, to_date)
        _time.sleep(KITE_CALL_SPACING_SECONDS)
        if not candles:
            continue
        dates, closes = market_indices.parse_candles(candles)
        if len(closes) >= market_indices.MIN_POINTS_FOR_RANGE:
            out[sym] = (dates, closes)
            cached[sym] = (dates, closes)
    return out


def _get_index_tape(force: bool = False) -> dict:
    """Cached index tape. Never raises — falls back to stale, then to empty."""
    now = _time.time()
    cached = _index_tape_cache["data"]
    if not force and cached and (now - _index_tape_cache["ts"]) < _INDEX_TAPE_TTL:
        return cached

    try:
        history = _get_index_history(force=force)
        try:
            recent = _download_index_frames(
                list(market_indices.UNIVERSE_SYMBOLS), _INDEX_RECENT_PERIOD)
        except Exception as e:
            # The cached decade alone still builds a valid tape, only a little
            # staler at the last bar. Dropping the whole tape because the fresh
            # window failed would be the worse trade.
            print(f"[IndexTape] Recent window failed, using history only: {e}")
            recent = {}

        series = {}
        for meta in market_indices.INDEX_UNIVERSE:
            sym = meta["symbol"]
            h_dates, h_closes = history.get(sym, ([], []))
            r_dates, r_closes = recent.get(sym, ([], []))
            series[sym] = market_indices.merge_series(
                h_dates, h_closes, r_dates, r_closes)

        # ORDER MATTERS. The quotes call is ONE request covering all 28
        # instruments; the history loop is up to thirty. Fetching the cheap one
        # first means a rate limit in the expensive one cannot take the live
        # day change down with it — which is exactly what happened: the history
        # burst returned 429, the stream died, the resume was refused and the
        # Zerodha login went with it. It is fetched here and applied after the
        # rows exist, because the overlay needs somewhere to land.
        quotes = None
        wanted = [market_indices.KITE_INDEX[m["symbol"]]
                  for m in market_indices.INDEX_UNIVERSE
                  if m["symbol"] in market_indices.KITE_INDEX]
        try:
            quotes = kite_client.get_index_quotes(wanted)
        except Exception as e:
            print(f"[IndexTape] Kite quotes skipped: {e}")

        # Yahoo serves ONE bar for most NSE sector indices, which is why AUTO,
        # FMCG, ENERGY and the rest had no 52-week range at all. Kite is the
        # only source left that will hand over their history, so ask it for
        # exactly the ones Yahoo left empty — and no others, since a working
        # Yahoo series is already the cheaper answer.
        short = [m["symbol"] for m in market_indices.INDEX_UNIVERSE
                 if len(series.get(m["symbol"], ([], []))[1])
                 < market_indices.MIN_POINTS_FOR_RANGE]
        if short:
            try:
                filled = _kite_index_history(short)
            except Exception as e:
                print(f"[IndexTape] Kite history skipped: {e}")
                filled = {}
            for sym, (dts, closes) in filled.items():
                series[sym] = (dts, closes)
            print(f"[IndexTape] Kite supplied history for {len(filled)} of "
                  f"{len(short)} indices Yahoo left empty")

        rows = []
        for meta in market_indices.INDEX_UNIVERSE:
            dates, closes = series.get(meta["symbol"], ([], []))
            rows.append(market_indices.summarize_index(meta, closes, dates=dates))

        # Yahoo supplies the long series behind the 52-week range; Kite the
        # live level and — the part that matters — the PREVIOUS close. Half the
        # sector tape had a live level and nothing to measure it against.
        #
        # Never allowed to fail the tape: a refused or unauthenticated Kite
        # session leaves every Yahoo figure exactly as it was.
        if quotes:
            n = market_indices.apply_live_quotes(rows, quotes)
            print(f"[IndexTape] Kite refreshed {n} of {len(wanted)} indices")
        else:
            # Say WHY, or a tape full of blank day changes looks like a bug in
            # the tape rather than a Kite session that needs a login.
            print(f"[IndexTape] Kite quotes unavailable "
                  f"({kite_client.connection_state}) — the {len(wanted)} "
                  f"NSE indices keep whatever Yahoo gave them")

        tape = market_indices.build_tape(rows)
        _index_tape_cache["ts"] = now
        _index_tape_cache["data"] = tape
        return tape
    except Exception as e:
        print(f"[IndexTape] Fetch failed: {e}")
        # A stale tape is still a real reading; an empty one is honest about
        # having none. Never fabricate a flat market.
        return cached if cached else market_indices.empty_tape()


# Between full tape rebuilds, the live level and day change are refreshed from
# ONE batched Kite quotes call at most this often, and only while NSE is in
# session. This is what makes the tape move with the market instead of in
# five-minute steps; the history behind the 52-week figures is not touched.
_INDEX_LIVE_TTL = 15
_index_live_state: dict = {"ts": 0.0}


def _refresh_index_tape_live(tape: dict) -> dict:
    """Overlay fresh Kite quotes on the cached tape. Never raises."""
    now = _time.time()
    if (not tape or not tape.get("indices") or not _is_kite_connected()
            or not market_indices.is_market_open()
            or now - _index_live_state["ts"] < _INDEX_LIVE_TTL):
        return tape
    # Stamp before the call so a slow or failing Kite cannot be retried by
    # every concurrent poll at once.
    _index_live_state["ts"] = now
    wanted = [market_indices.KITE_INDEX[m["symbol"]]
              for m in market_indices.INDEX_UNIVERSE
              if m["symbol"] in market_indices.KITE_INDEX]
    try:
        quotes = kite_client.get_index_quotes(wanted)
        if not quotes:
            return tape
        rows, touched = market_indices.refresh_live_rows(tape["indices"], quotes)
        if not touched:
            return tape
        live = market_indices.build_tape(rows)
        live["live_at"] = datetime.now().isoformat(timespec="seconds")
        # Same timestamp as the rebuild it overlays: the TTL still governs the
        # next full rebuild, the overlay only keeps the numbers current.
        _index_tape_cache["data"] = live
        return live
    except Exception as e:
        print(f"[IndexTape] Live overlay skipped: {e}")
        return tape


@app.get("/api/market/indices")
def get_market_indices(force: bool = False, group: Optional[str] = None):
    """Live tape across broad-market, bank, sector and commodity indices.

    Always HTTP 200: cache -> batched fetch -> stale cache -> empty tape.
    Each row carries today's move and how far the index sits below its 1-year
    high; an index whose data did not arrive reports status "unavailable" with
    null numbers rather than a fabricated zero.
    """
    tape = _refresh_index_tape_live(_get_index_tape(force=force))
    now = _time.time()
    payload = dict(tape)
    payload["cached_at"] = _index_tape_cache["ts"] or None
    payload["stale"] = bool(
        _index_tape_cache["ts"] and (now - _index_tape_cache["ts"]) >= _INDEX_TAPE_TTL
    )
    if group:
        key = group.strip().lower()
        payload["indices"] = [r for r in payload.get("indices", [])
                              if r.get("group") == key]
    return payload


def _get_dip_backtest(force: bool = False) -> dict:
    """Ten-year dip study for every index in the universe, cached.

    Reads the same cached history the tape uses, so this costs one pass of
    arithmetic rather than a second decade-long download.
    """
    now = _time.time()
    cached = _backtest_cache["data"]
    if not force and cached and (now - _backtest_cache["ts"]) < _BACKTEST_TTL:
        return cached

    history = _get_index_history(force=force)
    studies = []
    for meta in market_indices.INDEX_UNIVERSE:
        _dates, closes = history.get(meta["symbol"], ([], []))
        studies.append(backtest_engine.backtest_benchmark(
            meta["symbol"], meta["label"], closes))

    payload = {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "horizons": list(backtest_engine.HORIZONS),
        "horizon_labels": backtest_engine.HORIZON_LABELS,
        "thresholds": list(backtest_engine.DEFAULT_THRESHOLDS),
        "min_signals_for_reliable": backtest_engine.MIN_SIGNALS_FOR_RELIABLE,
        "studies": studies,
    }
    _backtest_cache["ts"] = now
    _backtest_cache["data"] = payload
    return payload


@app.get("/api/market/dip-backtest")
def get_dip_backtest(force: bool = False, symbol: Optional[str] = None):
    """What ten years of history say about buying each drawdown threshold.

    Every threshold row is quoted against a baseline of buying on a random day,
    because a forward return with no null to compare it against says nothing
    about whether the signal added anything. Rows resting on fewer than
    `min_signals_for_reliable` separate episodes are flagged reliable=false and
    must not be presented as evidence.

    Always HTTP 200: an index without enough history reports
    status "insufficient_history" with null statistics, never zeros.
    """
    payload = dict(_get_dip_backtest(force=force))
    payload["cached_at"] = _backtest_cache["ts"] or None
    if symbol:
        key = symbol.strip()
        payload["studies"] = [s for s in payload.get("studies", [])
                              if s.get("symbol") == key]
    return payload


@app.get("/api/strategies")
def get_strategies():
    """Rules-based backtested strategies over the Nifty50 universe.
    Returns a list of strategy result dicts (see strategies.run_strategies)."""
    try:
        universe = [c["symbol"] for c in NIFTY50_CONSTITUENTS]
        name_by_sym = {c["symbol"]: c["name"] for c in NIFTY50_CONSTITUENTS}
        strat_list = strategies.run_strategies(universe, name_by_symbol=name_by_sym, years=3)
        return {"strategies": strat_list}
    except Exception as e:
        print(f"[Strategies] Endpoint failed: {e}")
        return {"strategies": []}


@app.get("/api/market/nifty50/constituents")
def get_nifty50_constituents():
    """Return the ~50 Nifty50 members with price + daily change_pct.
    Batched yf.download, cached ~5 min. Never raises; empty list on failure."""
    now = _time.time()
    if _nifty50_constituents_cache["data"] and (now - _nifty50_constituents_cache["ts"]) < _NIFTY50_CACHE_TTL:
        return {"constituents": _nifty50_constituents_cache["data"]}

    symbols = [c["symbol"] for c in NIFTY50_CONSTITUENTS]
    name_by_sym = {c["symbol"]: c["name"] for c in NIFTY50_CONSTITUENTS}
    out = []
    try:
        import math as _math
        data = yf.download(symbols, period="2d", group_by="ticker", progress=False, threads=True)
        for sym in symbols:
            price = None
            change_pct = None
            try:
                # Multi-ticker frame: columns are (symbol, field)
                closes = data[sym]["Close"].dropna() if sym in data else _pd.Series(dtype=float)
                if len(closes) >= 1:
                    last = float(closes.iloc[-1])
                    if not _math.isnan(last):
                        price = round(last, 2)
                    if len(closes) >= 2:
                        prev = float(closes.iloc[-2])
                        if prev and not _math.isnan(prev) and price is not None:
                            change_pct = round((last - prev) / prev * 100, 2)
            except Exception:
                pass
            out.append({
                "symbol": sym.replace(".NS", ""),
                "name": name_by_sym.get(sym, sym),
                "price": price,
                "change_pct": change_pct,
            })
        _nifty50_constituents_cache["ts"] = now
        _nifty50_constituents_cache["data"] = out
        return {"constituents": out}
    except Exception as e:
        print(f"[Nifty50Constituents] Fetch failed: {e}")
        # Return stale cache if we have it, else empty list
        if _nifty50_constituents_cache["data"]:
            return {"constituents": _nifty50_constituents_cache["data"]}
        return {"constituents": []}


@app.get("/api/stock/{symbol}/news")
def get_stock_news(symbol: str):
    """Fetch real news for a stock from yfinance + Google News RSS."""
    from datetime import datetime, timedelta
    import urllib.request, urllib.parse, re, html
    import xml.etree.ElementTree as ET

    all_news = []
    clean_name = symbol.replace(".NS", "").replace(".BO", "")

    # 1) yfinance news (fast, usually cached)
    try:
        ticker = yf.Ticker(symbol)
        yf_news = getattr(ticker, "news", None) or []
        for item in yf_news[:10]:
            if isinstance(item, dict):
                # yfinance v2 format
                content = item.get("content", item)
                if isinstance(content, dict):
                    title = content.get("title", "")
                    summary = content.get("summary", "")
                    pub_date = content.get("pubDate", "")
                    # Get provider
                    prov = content.get("provider", {})
                    provider = prov.get("displayName", "") if isinstance(prov, dict) else str(prov)
                    # Get URL
                    cu = content.get("canonicalUrl", {})
                    link = cu.get("url", "") if isinstance(cu, dict) else ""
                else:
                    title = item.get("title", "")
                    summary = item.get("summary", "")
                    pub_date = item.get("pubDate", "")
                    provider = item.get("publisher", "Yahoo Finance")
                    link = item.get("link", "")

                if title:
                    all_news.append({
                        "title": title[:150],
                        "source": provider or "Yahoo Finance",
                        "date": pub_date or "",
                        "link": link or "",
                        "snippet": (summary[:180] + "...") if len(str(summary)) > 180 else str(summary),
                    })
    except Exception as e:
        print(f"yfinance news error: {e}")

    # 2) Google News RSS (with strict timeout)
    try:
        query = urllib.parse.quote(f"{clean_name} stock India news")
        url = f"https://news.google.com/rss/search?q={query}+when:7d&hl=en-IN&gl=IN&ceid=IN:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            xml_data = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml_data)
        for item in root.findall(".//item")[:10]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source = (item.findtext("source") or "News").strip()
            desc = re.sub(r'<[^>]+>', '', html.unescape(item.findtext("description") or ""))[:180]

            if title and not any(n["title"] == title for n in all_news):
                all_news.append({"title": title[:150], "source": source, "date": pub_date, "link": link, "snippet": desc})
    except Exception as e:
        print(f"Google News RSS error: {e}")

    # Format dates
    def parse_dt(d):
        for fmt in ["%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%SZ"]:
            try: return datetime.strptime(d.strip(), fmt)
            except: pass
        return datetime.min

    for n in all_news:
        dt = parse_dt(n.get("date", ""))
        n["_dt"] = dt
        if dt != datetime.min:
            n["date"] = dt.strftime("%d %b %Y")

    all_news.sort(key=lambda x: x.pop("_dt", datetime.min), reverse=True)
    return {"symbol": symbol, "name": clean_name, "news": all_news[:15], "total": len(all_news)}


# ──────────────────────────────────────
# Shared: News fetcher for a single symbol
# ──────────────────────────────────────
def _fetch_news_for_symbol(symbol: str) -> list:
    """Fetch news headlines for a single stock."""
    import urllib.request, urllib.parse
    import xml.etree.ElementTree as ET
    
    articles = []
    clean_name = symbol.replace(".NS", "").replace(".BO", "")
    
    # yfinance
    try:
        ticker = yf.Ticker(symbol)
        yf_news = getattr(ticker, "news", None) or []
        for item in yf_news[:8]:
            if isinstance(item, dict):
                content = item.get("content", item)
                if isinstance(content, dict):
                    title = content.get("title", "")
                else:
                    title = item.get("title", "")
                if title:
                    articles.append(title[:150])
    except:
        pass
    
    # Google News RSS
    try:
        query = urllib.parse.quote(f"{clean_name} stock India news")
        url = f"https://news.google.com/rss/search?q={query}+when:7d&hl=en-IN&gl=IN&ceid=IN:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            xml_data = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml_data)
        for item in root.findall(".//item")[:8]:
            title = (item.findtext("title") or "").strip()
            if title and title not in articles:
                articles.append(title[:150])
    except:
        pass
    
    return articles[:12]


# ──────────────────────────────────────
# AI Smart Advisor — Full Portfolio Analysis
# ──────────────────────────────────────

advisor_state = {
    "running": False,
    "results": {},
    "last_run": None,
}

def _get_stock_context(symbol: str, holding: dict) -> dict:
    """Gather all relevant data for a stock: price, technicals, fundamentals, news."""
    import urllib.request, urllib.parse, re, html
    import xml.etree.ElementTree as ET
    
    ctx = {"symbol": symbol, "name": holding.get("name", symbol.replace(".NS", ""))}
    clean = symbol.replace(".NS", "")
    
    # Current price & technicals from yfinance
    try:
        ticker = yf.Ticker(symbol)
        hist = _safe_yf_history(symbol, period="3mo")
        if not hist.empty:
            close = hist["Close"]
            ctx["current_price"] = round(float(close.iloc[-1]), 2)
            ctx["price_1w_ago"] = round(float(close.iloc[-5]), 2) if len(close) >= 5 else ctx["current_price"]
            ctx["price_1m_ago"] = round(float(close.iloc[-22]), 2) if len(close) >= 22 else ctx["current_price"]
            ctx["52w_high"] = round(float(close.max()), 2)
            ctx["52w_low"] = round(float(close.min()), 2)
            
            # SMA
            if len(close) >= 50:
                ctx["sma_20"] = round(float(close.rolling(20).mean().iloc[-1]), 2)
                ctx["sma_50"] = round(float(close.rolling(50).mean().iloc[-1]), 2)
            
            # RSI 14
            if len(close) >= 15:
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                ctx["rsi_14"] = round(float(rsi.iloc[-1]), 1)
            
            # Support/Resistance (simple: recent lows/highs)
            recent = close.tail(20)
            ctx["support"] = round(float(recent.min()), 2)
            ctx["resistance"] = round(float(recent.max()), 2)
            
            # Volume trend
            vol = hist["Volume"].tail(5).mean()
            vol_20 = hist["Volume"].tail(20).mean()
            ctx["volume_trend"] = "HIGH" if vol > vol_20 * 1.3 else "LOW" if vol < vol_20 * 0.7 else "NORMAL"
        
        # Fundamentals
        info = ticker.info or {}
        ctx["pe_ratio"] = info.get("trailingPE") or info.get("forwardPE")
        ctx["market_cap"] = info.get("marketCap")
        ctx["dividend_yield"] = info.get("dividendYield")
        ctx["sector"] = info.get("sector", "")
        ctx["industry"] = info.get("industry", "")
    except Exception as e:
        print(f"[Advisor] Data error for {symbol}: {e}")
    
    # Portfolio position
    ctx["avg_cost"] = holding.get("avg_cost", 0)
    ctx["shares"] = holding.get("shares", 0)
    ctx["invested"] = round(ctx["avg_cost"] * ctx["shares"], 2)
    if ctx.get("current_price"):
        ctx["current_value"] = round(ctx["current_price"] * ctx["shares"], 2)
        ctx["pnl"] = round(ctx["current_value"] - ctx["invested"], 2)
        ctx["pnl_pct"] = round((ctx["pnl"] / ctx["invested"]) * 100, 2) if ctx["invested"] > 0 else 0
    
    # News headlines
    headlines = _fetch_news_for_symbol(symbol)
    ctx["news_headlines"] = headlines[:8]
    ctx["news_count"] = len(headlines)
    
    return ctx


def _build_advisor_prompt(ctx: dict) -> str:
    """Build a comprehensive prompt for the AI advisor."""
    clean = ctx["symbol"].replace(".NS", "")
    
    lines = [f"You are a senior portfolio advisor managing Indian equity investments."]
    lines.append(f"\n=== STOCK: {clean} ({ctx.get('name', '')}) ===")
    lines.append(f"Sector: {ctx.get('sector', 'N/A')} | Industry: {ctx.get('industry', 'N/A')}")
    
    # Price data
    lines.append(f"\n--- PRICE DATA ---")
    lines.append(f"Current Price: Rs.{ctx.get('current_price', '?')}")
    lines.append(f"1 Week Ago: Rs.{ctx.get('price_1w_ago', '?')}")
    lines.append(f"1 Month Ago: Rs.{ctx.get('price_1m_ago', '?')}")
    lines.append(f"52W High: Rs.{ctx.get('52w_high', '?')} | 52W Low: Rs.{ctx.get('52w_low', '?')}")
    
    # Technicals
    lines.append(f"\n--- TECHNICALS ---")
    if ctx.get("sma_20"): lines.append(f"SMA 20: Rs.{ctx['sma_20']} | SMA 50: Rs.{ctx.get('sma_50', '?')}")
    if ctx.get("rsi_14"): lines.append(f"RSI (14): {ctx['rsi_14']}")
    lines.append(f"Support: Rs.{ctx.get('support', '?')} | Resistance: Rs.{ctx.get('resistance', '?')}")
    lines.append(f"Volume Trend: {ctx.get('volume_trend', 'N/A')}")
    
    # Fundamentals
    lines.append(f"\n--- FUNDAMENTALS ---")
    if ctx.get("pe_ratio"): lines.append(f"P/E Ratio: {round(ctx['pe_ratio'], 2)}")
    if ctx.get("market_cap"): lines.append(f"Market Cap: Rs.{ctx['market_cap']:,.0f}")
    if ctx.get("dividend_yield"): lines.append(f"Dividend Yield: {round(ctx['dividend_yield']*100, 2)}%")
    
    # Portfolio position
    lines.append(f"\n--- YOUR POSITION ---")
    lines.append(f"Shares Held: {ctx.get('shares', 0)} | Avg Cost: Rs.{ctx.get('avg_cost', 0)}")
    lines.append(f"Invested: Rs.{ctx.get('invested', 0):,.0f} | Current Value: Rs.{ctx.get('current_value', 0):,.0f}")
    lines.append(f"P&L: Rs.{ctx.get('pnl', 0):,.0f} ({ctx.get('pnl_pct', 0)}%)")
    
    # News
    if ctx.get("news_headlines"):
        lines.append(f"\n--- RECENT NEWS ({ctx['news_count']} articles, last 7 days) ---")
        for h in ctx["news_headlines"][:6]:
            lines.append(f"• {h}")
    
    lines.append(f"""
\n--- YOUR TASK ---
Based on ALL the above data, provide a COMPLETE actionable recommendation.

Your verdict MUST be exactly one of:
- BUY: New buying opportunity. Specify entry price range.
- BUY MORE: Already holding, add more shares. Specify entry price.
- HOLD: Keep current position. No action needed.
- SELL PARTIAL: Reduce position. Specify how much % to sell and at what price.
- SELL FULL: Exit entire position. Specify exit price.
- NO BUY: Avoid buying. Explain why.
- ACCUMULATE: Buy in small quantities on dips. Specify accumulation range.

Respond in this EXACT JSON format:
{{
  "verdict": "BUY|BUY MORE|HOLD|SELL PARTIAL|SELL FULL|NO BUY|ACCUMULATE",
  "action_summary": "One line action, e.g. 'Buy below Rs.780, Target Rs.850'",
  "entry_range": "Rs.XXX - Rs.YYY or null",
  "target_price": "Rs.XXX or null",
  "stop_loss": "Rs.XXX or null",
  "sell_pct": "50% or null (only for SELL PARTIAL)",
  "time_horizon": "Short (1-2 weeks) | Medium (1-3 months) | Long (6-12 months)",
  "risk_level": "Low | Medium | High",
  "confidence": 75,
  "reasoning": "2-3 sentence explanation covering technicals, news, and fundamentals"
}}""")
    
    return "\n".join(lines)


def _call_ollama_sync(prompt: str, retries: int = 2) -> dict:
    """Call Ollama synchronously with robust JSON parsing and retries."""
    import requests as req_lib
    import re
    
    for attempt in range(retries):
        try:
            resp = req_lib.post("http://localhost:11434/api/generate", json={
                "model": "gemma4:31b", "prompt": prompt, "stream": False, "format": "json"
            }, timeout=180)
            if resp.status_code != 200:
                print(f"[Ollama] HTTP {resp.status_code} on attempt {attempt+1}")
                continue
            data = resp.json()
            text = data.get("response", "").strip()
            
            if not text:
                print(f"[Ollama] Empty response on attempt {attempt+1}")
                continue
            
            # Try direct parse first
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
            
            # Strip <think>...</think> blocks (some models do this)
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            
            # Remove control characters
            text = re.sub(r'[\x00-\x1f\x7f]', ' ', text)
            
            # Try to find JSON object
            try:
                s = text.find('{')
                e = text.rfind('}')
                if s != -1 and e > s:
                    candidate = text[s:e+1]
                    return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            
            # Try regex to extract key fields manually
            verdict_m = re.search(r'"verdict"\s*:\s*"([^"]+)"', text)
            summary_m = re.search(r'"action_summary"\s*:\s*"([^"]+)"', text)
            target_m = re.search(r'"target_price"\s*:\s*"([^"]*)"', text)
            stop_m = re.search(r'"stop_loss"\s*:\s*"([^"]*)"', text)
            reason_m = re.search(r'"reasoning"\s*:\s*"([^"]+)"', text)
            conf_m = re.search(r'"confidence"\s*:\s*(\d+)', text)
            
            if verdict_m:
                return {
                    "verdict": verdict_m.group(1),
                    "action_summary": summary_m.group(1) if summary_m else "",
                    "target_price": target_m.group(1) if target_m and target_m.group(1) != "null" else None,
                    "stop_loss": stop_m.group(1) if stop_m and stop_m.group(1) != "null" else None,
                    "reasoning": reason_m.group(1) if reason_m else "",
                    "confidence": int(conf_m.group(1)) if conf_m else 50,
                    "time_horizon": "Medium",
                    "risk_level": "Medium",
                }
            
            print(f"[Ollama] Parse failed on attempt {attempt+1}, raw: {text[:200]}")
            
        except Exception as e:
            print(f"[Ollama] Exception on attempt {attempt+1}: {e}")
    
    return {"error": "Parse failed after retries"}


def _run_advisor_thread():
    """Run the full AI advisor for all portfolio stocks."""
    from datetime import datetime
    
    advisor_state["running"] = True
    advisor_state["results"] = {}
    
    symbols_data = [(h["symbol"], h) for h in user_portfolio]
    
    if not symbols_data:
        advisor_state["running"] = False
        return
    
    print(f"[AI Advisor] Starting for {len(symbols_data)} stocks...")
    
    # Initialize all as ANALYZING
    for sym, _ in symbols_data:
        clean = sym.replace(".NS", "")
        advisor_state["results"][sym] = {
            "verdict": "ANALYZING",
            "action_summary": f"Gathering data for {clean}...",
            "confidence": 0,
        }
    
    for sym, holding in symbols_data:
        clean = sym.replace(".NS", "")
        
        # Phase 1: Gather all data
        advisor_state["results"][sym]["action_summary"] = f"Fetching market data for {clean}..."
        print(f"[AI Advisor] Fetching data for {clean}...")
        
        try:
            ctx = _get_stock_context(sym, holding)
        except Exception as e:
            print(f"[AI Advisor] Data error for {clean}: {e}")
            advisor_state["results"][sym] = {
                "verdict": "ERROR", "action_summary": f"Data fetch failed: {str(e)[:60]}",
                "confidence": 0, "reasoning": str(e),
            }
            continue
        
        # Phase 2: AI Analysis
        advisor_state["results"][sym]["action_summary"] = f"AI analyzing {clean}..."
        print(f"[AI Advisor] AI analyzing {clean} (price: Rs.{ctx.get('current_price', '?')}, P&L: {ctx.get('pnl_pct', '?')}%)...")
        
        prompt = _build_advisor_prompt(ctx)
        result = _call_ollama_sync(prompt)
        
        if "error" in result:
            advisor_state["results"][sym] = {
                "verdict": "ERROR", "action_summary": f"AI error: {result['error'][:60]}",
                "confidence": 0, "reasoning": result["error"],
            }
            print(f"[AI Advisor] ERROR for {clean}: {result['error'][:60]}")
            continue
        
        # Normalize verdict
        verdict = (result.get("verdict", "HOLD")).upper().strip()
        valid = ["BUY", "BUY MORE", "HOLD", "SELL PARTIAL", "SELL FULL", "NO BUY", "ACCUMULATE"]
        if verdict not in valid:
            for v in valid:
                if v in verdict:
                    verdict = v
                    break
            else:
                verdict = "HOLD"
        
        final = {
            "verdict": verdict,
            "action_summary": result.get("action_summary", ""),
            "entry_range": result.get("entry_range"),
            "target_price": result.get("target_price"),
            "stop_loss": result.get("stop_loss"),
            "sell_pct": result.get("sell_pct"),
            "time_horizon": result.get("time_horizon", "Medium"),
            "risk_level": result.get("risk_level", "Medium"),
            "confidence": result.get("confidence", 50),
            "reasoning": result.get("reasoning", ""),
            "current_price": ctx.get("current_price"),
            "pnl_pct": ctx.get("pnl_pct"),
            "rsi": ctx.get("rsi_14"),
            "news_count": ctx.get("news_count", 0),
        }
        
        advisor_state["results"][sym] = final
        print(f"[AI Advisor] {clean}: {verdict} — {final.get('action_summary', '')[:80]}")
    
    advisor_state["running"] = False
    advisor_state["last_run"] = datetime.now().strftime("%I:%M %p")
    print(f"[AI Advisor] Complete for {len(symbols_data)} stocks.")


@app.post("/api/advisor/start")
def start_advisor():
    """Start the AI Smart Advisor for all portfolio stocks."""
    import threading
    
    if advisor_state["running"]:
        return {"status": "already_running", "results": advisor_state["results"]}
    
    t = threading.Thread(target=_run_advisor_thread, daemon=True)
    t.start()
    return {"status": "started", "message": "AI Smart Advisor started."}


@app.get("/api/advisor")
def get_advisor():
    """Get AI advisor results."""
    return {
        "running": advisor_state["running"],
        "results": advisor_state["results"],
        "last_run": advisor_state.get("last_run"),
        "total": len(advisor_state["results"]),
        "completed": sum(1 for r in advisor_state["results"].values() if r.get("verdict") not in ["ANALYZING"]),
    }


# Keep old news analysis endpoints for backward compat
@app.post("/api/news-analysis/start")
def start_news_analysis():
    return start_advisor()

@app.get("/api/news-analysis")
def get_news_analysis():
    d = get_advisor()
    d["results"] = {k: {"verdict": v.get("verdict","--"), "comment": v.get("action_summary",""), "sentiment": "neutral", "news_count": v.get("news_count",0)} for k,v in d["results"].items()}
    return d


# ──────────────────────────────────────
# AI Chat Bot — Conversational Stock Q&A
# ──────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    symbol: str | None = None
    history: list = []   # list of {"role":"user"|"assistant", "content":"..."}

@app.post("/api/chat")
def chat_with_ai(req: ChatRequest):
    """Conversational AI chatbot that answers questions about stocks using live data."""
    import requests as req_lib
    import re

    user_msg = req.message.strip()
    if not user_msg:
        return {"reply": "Please ask me a question about stocks or your portfolio."}

    # ── Build context from portfolio & stock data ──
    context_parts = []

    # Always include portfolio summary
    try:
        pf_summary = []
        total_val, total_inv = 0, 0
        for item in user_portfolio:
            cached = live_price_cache.get(item["symbol"])
            if cached:
                cur = cached["current"]
                qty = item["shares"]
                avg = item.get("avg_cost", cur)
                val = qty * cur
                inv = qty * avg
                total_val += val
                total_inv += inv
                pnl_pct = round(((cur - avg) / avg) * 100, 2) if avg else 0
                pf_summary.append(f"  {item['symbol'].replace('.NS','')}: {qty} shares @ Rs.{avg:.0f}, LTP Rs.{cur:.2f}, P&L {pnl_pct:+.1f}%")
        if pf_summary:
            context_parts.append("=== USER'S STOCK PORTFOLIO ===")
            context_parts.append(f"Total Invested: Rs.{total_inv:,.0f} | Current Value: Rs.{total_val:,.0f} | P&L: Rs.{total_val-total_inv:,.0f} ({((total_val-total_inv)/total_inv*100) if total_inv else 0:+.1f}%)")
            context_parts.extend(pf_summary)
    except Exception as e:
        print(f"[Chat] Portfolio context error: {e}")

    # Include MF portfolio
    try:
        if user_mf_portfolio:
            mf_summary = []
            mf_total_inv = sum(f.get("invested", 0) for f in user_mf_portfolio)
            mf_total_cur = sum(f.get("current_value", 0) for f in user_mf_portfolio)
            mf_pnl = mf_total_cur - mf_total_inv
            mf_pnl_pct = (mf_pnl / mf_total_inv * 100) if mf_total_inv > 0 else 0
            for mf in user_mf_portfolio:
                inv = mf.get("invested", 0)
                cur = mf.get("current_value", 0)
                ret = mf.get("return_pct", 0)
                xirr = mf.get("xirr", 0)
                mf_summary.append(f"  {mf['scheme_name']} ({mf.get('category','MF')}): Invested Rs.{inv:,.0f}, Current Rs.{cur:,.0f}, Return {ret:+.2f}%, XIRR {xirr:+.1f}%, Units {mf.get('units',0):.3f}, NAV Rs.{mf.get('nav',0):.2f}")
            context_parts.append(f"\n=== USER'S MUTUAL FUND PORTFOLIO ===")
            context_parts.append(f"Total MF Invested: Rs.{mf_total_inv:,.0f} | Current Value: Rs.{mf_total_cur:,.0f} | P&L: Rs.{mf_pnl:,.0f} ({mf_pnl_pct:+.1f}%)")
            context_parts.extend(mf_summary)
    except Exception as e:
        print(f"[Chat] MF context error: {e}")

    # ── Detect stock symbol from message ──
    target_symbol = req.symbol
    if not target_symbol:
        # Try to detect a stock name in the message
        msg_upper = user_msg.upper()
        for s in POPULAR_INDIAN_STOCKS:
            clean = s["symbol"].replace(".NS", "")
            if clean in msg_upper or s["name"].upper() in msg_upper:
                target_symbol = s["symbol"]
                break
        # Also check portfolio symbols
        if not target_symbol:
            for item in user_portfolio:
                clean = item["symbol"].replace(".NS", "")
                if clean in msg_upper:
                    target_symbol = item["symbol"]
                    break

    # ── Gather detailed data for the target stock ──
    if target_symbol:
        yf_sym = _yf_symbol(target_symbol)
        context_parts.append(f"\n=== DETAILED DATA FOR {yf_sym.replace('.NS','')} ===")
        try:
            ticker = yf.Ticker(yf_sym)
            hist = _safe_yf_history(yf_sym, period="3mo")
            if not hist.empty:
                close = hist["Close"]
                cur_price = float(close.iloc[-1])
                context_parts.append(f"Current Price: Rs.{cur_price:.2f}")
                if len(close) >= 5:
                    context_parts.append(f"1-Week Ago: Rs.{float(close.iloc[-5]):.2f}")
                if len(close) >= 22:
                    context_parts.append(f"1-Month Ago: Rs.{float(close.iloc[-22]):.2f}")
                context_parts.append(f"3M High: Rs.{float(close.max()):.2f} | 3M Low: Rs.{float(close.min()):.2f}")

                # RSI
                if len(close) >= 15:
                    delta = close.diff()
                    gain = delta.where(delta > 0, 0).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    context_parts.append(f"RSI (14): {float(rsi.iloc[-1]):.1f}")

                # SMA
                if len(close) >= 50:
                    context_parts.append(f"SMA 20: Rs.{float(close.rolling(20).mean().iloc[-1]):.2f}")
                    context_parts.append(f"SMA 50: Rs.{float(close.rolling(50).mean().iloc[-1]):.2f}")

            # Fundamentals
            info = ticker.info or {}
            if info.get("trailingPE"):
                context_parts.append(f"P/E Ratio: {info['trailingPE']:.2f}")
            if info.get("marketCap"):
                context_parts.append(f"Market Cap: Rs.{info['marketCap']:,.0f}")
            if info.get("dividendYield"):
                context_parts.append(f"Dividend Yield: {info['dividendYield']*100:.2f}%")
            if info.get("sector"):
                context_parts.append(f"Sector: {info['sector']}")

            # News
            headlines = _fetch_news_for_symbol(yf_sym)
            if headlines:
                context_parts.append(f"\nRecent News ({len(headlines)} articles):")
                for h in headlines[:5]:
                    context_parts.append(f"  • {h}")
        except Exception as e:
            context_parts.append(f"(Could not fetch data: {e})")

    # ── Build conversation history ──
    history_text = ""
    if req.history:
        for msg in req.history[-6:]:  # Keep last 6 messages for context
            role = "User" if msg.get("role") == "user" else "Assistant"
            history_text += f"\n{role}: {msg.get('content', '')}"

    # ── Build the final prompt ──
    context_block = "\n".join(context_parts) if context_parts else "No specific data available."

    prompt = f"""You are "AIEI Advisor", a friendly, expert AI financial advisor for Indian markets (NSE/BSE & Mutual Funds).
You help users understand their COMPLETE portfolio (both direct equity/stocks AND mutual funds), analyze investments, and make informed decisions.

RULES:
- Be concise but insightful. Use bullet points where helpful.
- Always mention specific numbers (prices, P/E, RSI, NAV, XIRR, etc.) when available.
- Give actionable advice when asked, with entry/exit levels for stocks and SIP/lumpsum suggestions for MFs.
- The user has BOTH stocks and mutual funds. Always reference both when discussing overall portfolio.
- If you don't know something, say so honestly.
- Use Indian Rupee (Rs. or ₹) for all prices.
- Be conversational and personable, but professional.
- Keep responses under 250 words unless the user asks for detail.
- For mutual funds, discuss NAV trends, XIRR, category allocation, and fund performance.

LIVE MARKET DATA:
{context_block}

{f"CONVERSATION HISTORY:{history_text}" if history_text else ""}

User: {user_msg}

Respond naturally and helpfully. Do NOT output JSON. Use plain text with markdown-like formatting (bold with **, bullet points with •)."""

    # ── Call Ollama ──
    try:
        resp = req_lib.post("http://localhost:11434/api/generate", json={
            "model": "gemma4:31b", "prompt": prompt, "stream": False,
        }, timeout=120)
        if resp.status_code != 200:
            return {"reply": "I'm having trouble connecting to the AI engine right now. Please try again in a moment."}
        data = resp.json()
        text = data.get("response", "").strip()

        # Strip <think>...</think> blocks
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        if not text:
            return {"reply": "I didn't get a response. Could you rephrase your question?"}

        return {"reply": text, "symbol_detected": target_symbol}

    except req_lib.exceptions.Timeout:
        return {"reply": "The AI is taking too long to respond. Try asking a simpler question or try again shortly."}
    except Exception as e:
        print(f"[Chat] Error: {e}")
        return {"reply": f"Something went wrong: {str(e)[:100]}. Please try again."}


# ──────────────────────────────────────
# Zerodha Kite Connect — Auth & Data Endpoints
# ──────────────────────────────────────

def _sync_portfolio_from_kite():
    """Sync portfolio from Kite holdings to local portfolio."""
    global user_portfolio, user_mf_portfolio
    result = {
        "stocks_synced": False,
        "holdings_received": None,
        "stock_error": None,
    }
    # Sync stock holdings
    holdings = kite_client.get_holdings()
    if isinstance(holdings, list):
        result["holdings_received"] = len(holdings)
        new_portfolio = kite_client.transform_holdings_to_portfolio(holdings)
        if new_portfolio:
            for item in new_portfolio:
                for s in POPULAR_INDIAN_STOCKS:
                    if s["symbol"] == item["symbol"]:
                        item["name"] = s["name"]
                        break
            user_portfolio = new_portfolio
            _save_portfolio()
            # Prime the live cache from the holdings payload. These prices are live
            # as of this sync, so the very first /portfolio/default after a sync
            # shows real values instead of waiting a poll cycle for the bg thread.
            primed = 0
            for item in new_portfolio:
                last = item.get("kite_last_price") or 0
                if last > 0:
                    close = item.get("kite_close_price") or 0
                    live_price_cache[item["symbol"]] = {
                        "current": last, "prev": close if close > 0 else last,
                        "source": PRICE_SRC_KITE_SNAPSHOT,
                    }
                    primed += 1
            print(f"[Kite] Stock portfolio synced: {len(new_portfolio)} holdings "
                  f"({primed} priced from the holdings payload)")
            result["stocks_synced"] = True
        else:
            # Never replace a real local portfolio with an unauthenticated or
            # unexpectedly empty response.
            result["stock_error"] = "Kite returned no holdings"
    else:
        result["stock_error"] = (
            kite_client.last_error or "Kite holdings were unavailable")
    # Pull the tradebook too — holdings carry no dates, so this is what makes
    # equity XIRR possible. Merging is idempotent, so a per-sync call is safe.
    try:
        _sync_equity_trades_from_kite()
    except Exception as e:
        print(f"[Kite] Tradebook sync error: {e}")
    # Sync MF holdings
    _sync_mf_from_kite()
    return result


def _sync_mf_from_kite():
    """Sync mutual fund holdings from Kite MCP."""
    global user_mf_portfolio
    try:
        mf_data = kite_client.get_mf_holdings()
        if mf_data and isinstance(mf_data, list) and len(mf_data) > 0:
            new_mf = []
            # Kite's MF holdings are a snapshot with no transaction history. Any
            # dated transactions already stored for a scheme are the only thing
            # its XIRR can be computed from, so carry them across the sync
            # instead of letting the snapshot overwrite them away.
            existing_txns = {
                f.get("scheme_name", ""): f.get("transactions", [])
                for f in user_mf_portfolio if f.get("transactions")
            }
            for mf in mf_data:
                if isinstance(mf, dict):
                    invested = mf.get("invested", 0) or mf.get("amount", 0) or 0
                    current = mf.get("current_value", 0) or mf.get("market_value", 0) or 0
                    units = mf.get("units", 0) or mf.get("quantity", 0) or 0
                    nav = mf.get("nav", 0) or mf.get("last_price", 0) or 0
                    avg_nav = mf.get("average_price", 0) or mf.get("avg_nav", 0) or 0
                    return_pct = ((current - invested) / invested * 100) if invested > 0 else 0
                    new_mf.append({
                        "scheme_name": mf.get("tradingsymbol", "") or mf.get("scheme_name", "") or mf.get("fund", ""),
                        "category": mf.get("category", "Mutual Fund"),
                        "folio": mf.get("folio", ""),
                        "invested": round(invested, 2),
                        "current_value": round(current, 2),
                        "units": round(units, 3),
                        "nav": round(nav, 4),
                        "avg_nav": round(avg_nav, 4),
                        "return_pct": round(return_pct, 2),
                        "xirr": mf.get("xirr", 0) or 0,
                    })
                    kept = existing_txns.get(new_mf[-1]["scheme_name"])
                    if kept:
                        new_mf[-1]["transactions"] = kept
            if new_mf:
                user_mf_portfolio = new_mf
                _save_mf_portfolio()
                print(f"[Kite] MF portfolio synced: {len(new_mf)} funds")
    except Exception as e:
        print(f"[Kite] MF sync error: {e}")


@app.get("/api/kite/status")
def kite_status():
    """Get status proven against the current MCP session, not stale memory."""
    kite_client.check_connection()
    return kite_client.get_status()


@app.get("/api/kite/login")
def kite_login():
    """Get Zerodha login URL via Kite MCP."""
    kite_client._manual_disconnect = False
    kite_client._last_profile_check = 0.0
    url = kite_client.get_login_url()
    if url:
        return {"login_url": url}
    # If no URL, check if already connected
    if kite_client.connected or kite_client.check_connection():
        return {"already_connected": True, "user_name": kite_client._user_name}
    raise HTTPException(status_code=400, detail="Kite MCP server not reachable")


@app.get("/api/kite/callback")
def kite_callback(request_token: str = Query(None), status: str = Query(None)):
    """Handle Zerodha OAuth callback after user login."""
    if status == "error":
        return RedirectResponse(url="http://localhost:3000?kite_error=login_failed")
    
    # After MCP login, check if we're now authenticated
    if kite_client.check_connection():
        _sync_portfolio_from_kite()
        return RedirectResponse(url=f"http://localhost:3000?kite_connected=true&user={kite_client._user_name or ''}")
    else:
        return RedirectResponse(url=f"http://localhost:3000?kite_error=auth_pending")


@app.post("/api/kite/check")
def kite_check_connection(sync_holdings: bool = True):
    """Check authentication and sync holdings before login is called done.

    `sync_holdings=False` answers the cheap half of the question. The login
    screen polls this every two seconds while it waits for the browser, and a
    full holdings sync on every tick meant a two-minute login fired sixty
    portfolio pulls over MCP — enough to saturate the backend, time out the
    status poll, and leave the sidebar claiming Kite was reconnecting when it
    was not. Callers that poll should ask for the sync only once, on the tick
    that first comes back connected.
    """
    if kite_client.check_connection():
        sync = ({"stocks_synced": False, "holdings_received": None,
                 "stock_error": None, "skipped": True}
                if not sync_holdings else _sync_portfolio_from_kite())
        # get_holdings can reveal that a session which passed get_profile is
        # no longer authenticated. Respect that newer evidence.
        if not kite_client.connected:
            return {"connected": False, "error": kite_client.last_error,
                    "portfolio_synced": False, "sync": sync}
        return {
            "connected": True,
            "user_name": kite_client._user_name,
            "user_id": kite_client._user_id,
            "portfolio_synced": sync["stocks_synced"],
            "sync": sync,
        }
    return {"connected": False, "error": kite_client.last_error}


@app.post("/api/kite/logout")
def kite_logout():
    """Logout from Kite Connect."""
    kite_client.logout()
    return {"status": "logged_out"}


@app.post("/api/kite/reconnect")
def kite_reconnect():
    """Force a clean MCP session when automatic recovery cannot get one.

    Distinct from logout: this keeps the intent to be connected and only
    discards the transport and the remembered session id. Needed because a
    server-side session that is gone for good makes every resume attempt fail
    the same way, and the user has no other way to say "stop trying to restore
    that one".
    """
    out = kite_client.reconnect()
    return {**out, "status": "reconnecting"}


@app.get("/api/kite/test")
def kite_test_mcp():
    """Test Kite MCP data fetch — for debugging only."""
    results = {}

    # 1. Status
    results["connected"] = kite_client.connected
    results["mcp_available"] = kite_client._mcp_available
    results["user"] = kite_client._user_name

    # 2. Search
    try:
        sr = kite_client.search_instruments("RELIANCE", "NSE")
        if sr and isinstance(sr, list):
            eq = [r for r in sr if r.get("instrument_type") == "EQ"]
            results["search"] = f"{len(sr)} total, {len(eq)} EQ"
            token = eq[0]["instrument_token"] if eq else 738561
        else:
            results["search"] = f"Failed: {str(sr)[:100]}"
            token = 738561
    except Exception as e:
        results["search"] = f"Error: {e}"
        token = 738561
    results["token"] = token

    # 3. Historical
    from datetime import datetime, timedelta
    to_d = datetime.now().strftime("%Y-%m-%d 23:59:59")
    from_d = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d 00:00:00")
    try:
        r = kite_client.get_historical_data(
            instrument_token=token, from_date=from_d, to_date=to_d, interval="day"
        )
        if isinstance(r, list) and len(r) > 0:
            results["historical"] = f"SUCCESS: {len(r)} candles"
            results["last_candle"] = str(r[-1])
        elif isinstance(r, str):
            results["historical"] = f"STRING ERROR: {r}"
        elif isinstance(r, dict):
            candles = r.get("candles", [])
            results["historical"] = f"Dict: {len(candles)} candles"
        else:
            results["historical"] = f"type={type(r).__name__}"
    except Exception as e:
        results["historical"] = f"Error: {e}"

    # 4. LTP
    try:
        ltp = kite_client.get_ltp(["NSE:RELIANCE"])
        results["ltp"] = str(ltp)[:200]
    except Exception as e:
        results["ltp"] = f"Error: {e}"

    return results

@app.post("/api/kite/sync")
def kite_sync_portfolio():
    """Force sync portfolio from Kite holdings."""
    if not kite_client.check_connection():
        raise HTTPException(status_code=400, detail="Kite not connected")
    sync = _sync_portfolio_from_kite()
    if not sync["stocks_synced"]:
        raise HTTPException(
            status_code=502,
            detail=sync["stock_error"] or "Kite holdings sync failed")
    return {
        "status": "synced",
        "holdings_count": len(user_portfolio),
        "mf_count": len(user_mf_portfolio),
        "sync": sync,
    }


# Only tools whose name begins with one of these may be invoked through the
# diagnostic endpoint. The Kite MCP server also exposes order placement,
# modification and cancellation; a debug route that could reach those would be
# a way to lose real money by typo. Read-only verbs only, enforced by prefix
# rather than by a blocklist, so a tool added upstream tomorrow is denied by
# default instead of allowed by omission.
KITE_DEBUG_ALLOWED_PREFIXES = ("get_", "list_", "search", "fetch_")


def _kite_debug_allowed(tool: str) -> bool:
    return bool(tool) and tool.startswith(KITE_DEBUG_ALLOWED_PREFIXES)


@app.get("/api/kite/debug/tools")
def kite_debug_tools():
    """What the Kite MCP server advertises it can do."""
    tools = kite_client.list_tools()
    if tools is None:
        return {"status": "unavailable", "tools": [],
                "detail": "No MCP session, or list_tools failed."}
    return {
        "status": "ok",
        "count": len(tools),
        "tools": sorted(tools, key=lambda x: x["name"]),
        "callable_here": sorted(x["name"] for x in tools
                                if _kite_debug_allowed(x["name"])),
    }


@app.get("/api/kite/debug/call")
def kite_debug_call(tool: str, args: Optional[str] = None):
    """Call one READ-ONLY MCP tool and return the raw payload.

    Exists because every account-scoped call was coming back empty while the
    session reported connected, and the normal accessors cannot tell "the
    portfolio is empty" apart from "the server sent prose instead of JSON".
    """
    if not _kite_debug_allowed(tool):
        raise HTTPException(
            status_code=400,
            detail=(f"'{tool}' is not read-only. Allowed prefixes: "
                    f"{', '.join(KITE_DEBUG_ALLOWED_PREFIXES)}"))
    parsed_args = {}
    if args:
        try:
            parsed_args = json.loads(args)
        except Exception as e:
            raise HTTPException(status_code=400,
                                detail=f"args must be JSON: {e}")
    return {"tool": tool, "args": parsed_args,
            "result": kite_client.call_tool_raw(tool, parsed_args)}


@app.get("/api/kite/holdings")
def kite_holdings():
    """Get raw Kite holdings data."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    holdings = kite_client.get_holdings()
    return {"holdings": holdings or []}


@app.get("/api/kite/positions")
def kite_positions():
    """Get current day positions from Kite."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    positions = kite_client.get_positions()
    return {"positions": positions or {}}


@app.get("/api/kite/margins")
def kite_margins():
    """Get account margins from Kite."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    margins = kite_client.get_margins()
    return {"margins": margins or {}}


@app.get("/api/kite/orders")
def kite_orders():
    """Get today's orders from Kite."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    orders = kite_client.get_orders()
    return {"orders": orders or []}


@app.post("/api/kite/order")
def kite_place_order(req: PlaceOrderRequest):
    """Place an order via Kite Connect."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    order_id = kite_client.place_order(
        tradingsymbol=req.tradingsymbol,
        exchange=req.exchange,
        transaction_type=req.transaction_type,
        quantity=req.quantity,
        order_type=req.order_type,
        product=req.product,
        price=req.price,
        trigger_price=req.trigger_price,
    )
    if order_id:
        return {"status": "success", "order_id": order_id}
    raise HTTPException(status_code=500, detail="Order placement failed")


@app.get("/api/kite/gtt")
def kite_gtt_orders():
    """Get GTT orders from Kite."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    gtts = kite_client.get_gtt_orders()
    return {"gtt_orders": gtts or []}


@app.post("/api/kite/gtt")
def kite_place_gtt(req: PlaceGTTRequest):
    """Place a GTT order via Kite Connect."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    gtt_id = kite_client.place_gtt_order(
        tradingsymbol=req.tradingsymbol,
        exchange=req.exchange,
        trigger_type=req.trigger_type,
        last_price=req.last_price,
        trigger_values=req.trigger_values,
        orders=req.orders,
    )
    if gtt_id:
        return {"status": "success", "gtt_id": gtt_id}
    raise HTTPException(status_code=500, detail="GTT order placement failed")


@app.get("/api/kite/mf-holdings")
def kite_mf_holdings():
    """Get mutual fund holdings from Kite MCP (raw)."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    mf = kite_client.get_mf_holdings()
    return {"mf_holdings": mf or []}


@app.get("/api/mf-portfolio")
def get_mf_portfolio():
    """Get local mutual fund portfolio (auto-refreshes NAV)."""
    _refresh_mf_nav()  # update NAVs before returning
    mf_total_invested = sum(f.get("invested", 0) for f in user_mf_portfolio)
    mf_total_current = sum(f.get("current_value", 0) for f in user_mf_portfolio)
    mf_pnl = mf_total_current - mf_total_invested
    mf_pnl_pct = (mf_pnl / mf_total_invested * 100) if mf_total_invested > 0 else 0

    # Book XIRR, pooled over every fund that carries a transaction history.
    # Funds synced from Kite as a bare snapshot have no dates and so cannot
    # contribute — covered_pct reports how much of the book is really behind
    # the number.
    mf_flows, mf_covered = _mf_cashflows()
    portfolio_xirr = _solve_xirr(mf_flows, mf_covered)

    # Per-fund XIRR. A fund Kite already gave us an XIRR for keeps it; the rest
    # are solved from their own transactions, or left at 0 when there are none.
    for fund in user_mf_portfolio:
        flows, covered = _mf_cashflows([fund])
        solved = _solve_xirr(flows, covered)
        fund["xirr"] = solved

    return {
        "funds": user_mf_portfolio,
        **dashboard_metadata.freshness(f.get("nav_retrieved_at") for f in user_mf_portfolio),
        "data_source": "NAV providers / saved holdings",
        "timestamp_basis": "NAV retrieved; see each fund's nav_date",
        "month_investment": dashboard_metadata.monthly_buys(
            t for f in user_mf_portfolio for t in f.get("transactions", [])),
        "total_invested": round(mf_total_invested, 2),
        "total_current": round(mf_total_current, 2),
        "total_pnl": round(mf_pnl, 2),
        "total_pnl_pct": round(mf_pnl_pct, 2),
        "total_xirr": portfolio_xirr,
        "xirr_covered_pct": round(mf_covered / mf_total_current * 100, 2) if mf_total_current > 0 else 0.0,
    }


# ──────────────────────────────────────
# MF Live NAV Refresh
# ──────────────────────────────────────

# Map scheme names to mfapi.in scheme codes (auto-populated on first search)
_mf_scheme_codes: dict = {}
_mf_nav_cache: dict = {}  # scheme_name -> {nav, updated_at}
_mf_nav_last_refresh = 0.0  # timestamp of last NAV refresh
MF_NAV_REFRESH_INTERVAL = 300  # refresh at most every 5 minutes

# Pinned mfapi.in scheme codes (scheme_name -> code), checked before a search.
# Filled at runtime when a fund is added with an explicit scheme code; a local
# data/known_scheme_codes.json (git-ignored) can pin codes that the name search
# resolves poorly. Anything not pinned is resolved via the mfapi.in search below.
KNOWN_SCHEME_CODES: dict = _load_local_seed("known_scheme_codes.json")


def _resolve_scheme_code(scheme_name: str) -> str:
    """Find mfapi.in scheme code for a fund name."""
    import requests as req_lib

    # Check known codes first
    if scheme_name in KNOWN_SCHEME_CODES:
        return KNOWN_SCHEME_CODES[scheme_name]
    if scheme_name in _mf_scheme_codes:
        return _mf_scheme_codes[scheme_name]

    # Search mfapi.in
    try:
        # Build search query from scheme name
        q = scheme_name.replace("Growth Direct Plan", "Direct Growth").replace("  ", " ").strip()
        r = req_lib.get("https://api.mfapi.in/mf/search", params={"q": q}, timeout=5)
        if r.ok:
            results = r.json()
            if results and len(results) > 0:
                # Score results by token overlap with the target name so that
                # e.g. "Mid Cap" never resolves to "Large & Mid Cap" (extra
                # tokens lower the score). Exact token match wins outright.
                import re as _re

                def _tokens(s: str) -> set:
                    return set(_re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())

                target = _tokens(scheme_name)
                want_direct = "direct" in target
                best_code, best_score = "", -1.0
                for item in results:
                    sn_tokens = _tokens(item.get("schemeName") or "")
                    code = str(item.get("schemeCode", ""))
                    if not code or not sn_tokens:
                        continue
                    if want_direct and "direct" not in sn_tokens:
                        continue
                    if sn_tokens == target:
                        _mf_scheme_codes[scheme_name] = code
                        return code
                    score = len(target & sn_tokens) / len(target | sn_tokens)
                    if score > best_score:
                        best_code, best_score = code, score
                if best_code:
                    _mf_scheme_codes[scheme_name] = best_code
                    return best_code
    except Exception as e:
        print(f"[MF NAV] Scheme code search error for '{scheme_name}': {e}")
    return ""


def _fetch_nav_from_mfapi(scheme_code: str) -> float:
    """Fetch latest NAV from mfapi.in."""
    import requests as req_lib
    try:
        r = req_lib.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=8)
        if r.ok:
            data = r.json()
            nav_data = data.get("data", [])
            if nav_data and len(nav_data) > 0:
                _mf_nav_cache[scheme_code] = {
                    "nav_date": nav_data[0].get("date"),
                    "retrieved_at": dashboard_metadata.utc_now(),
                }
                return float(nav_data[0].get("nav", 0))
    except Exception as e:
        print(f"[MF NAV] mfapi fetch error for {scheme_code}: {e}")
    return 0.0


def _refresh_mf_nav():
    """Refresh live NAV for all MF holdings.

    Priority: Kite MCP (if connected) → mfapi.in fallback.
    Rate-limited to avoid hammering APIs.
    """
    import time
    global _mf_nav_last_refresh

    now = _time.time()
    if now - _mf_nav_last_refresh < MF_NAV_REFRESH_INTERVAL:
        return  # too soon

    _mf_nav_last_refresh = now
    updated_count = 0

    # 1) Try Kite MCP first
    if _is_kite_connected():
        try:
            mf_data = kite_client.get_mf_holdings()
            if mf_data and isinstance(mf_data, list):
                kite_map = {}
                for mf in mf_data:
                    if isinstance(mf, dict):
                        key = (mf.get("tradingsymbol", "") or mf.get("fund", "") or "").strip()
                        nav = mf.get("nav", 0) or mf.get("last_price", 0) or 0
                        if key and nav > 0:
                            kite_map[key.lower()] = nav
                            # Also try folio matching
                            folio = mf.get("folio", "")
                            if folio:
                                kite_map[f"folio:{folio}"] = nav

                for fund in user_mf_portfolio:
                    name = fund.get("scheme_name", "").lower()
                    folio = fund.get("folio", "")
                    matched_nav = None

                    # Try name match
                    for kk, kv in kite_map.items():
                        if kk in name or name in kk:
                            matched_nav = kv
                            break
                    # Try folio match
                    if not matched_nav and folio:
                        matched_nav = kite_map.get(f"folio:{folio}")

                    if matched_nav and matched_nav > 0:
                        fund["nav"] = round(matched_nav, 4)
                        fund["nav_retrieved_at"] = dashboard_metadata.utc_now()
                        fund["nav_source"] = "Kite"
                        fund["nav_date"] = None
                        fund["current_value"] = round(fund.get("units", 0) * matched_nav, 2)
                        inv = fund.get("invested", 0)
                        fund["return_pct"] = round((fund["current_value"] - inv) / inv * 100, 2) if inv > 0 else 0
                        updated_count += 1

                if updated_count > 0:
                    _save_mf_portfolio()
                    print(f"[MF NAV] Updated {updated_count}/{len(user_mf_portfolio)} funds via Kite")
                    return
        except Exception as e:
            print(f"[MF NAV] Kite refresh error: {e}")

    # 2) Fallback: mfapi.in
    for fund in user_mf_portfolio:
        scheme_name = fund.get("scheme_name", "")
        code = _resolve_scheme_code(scheme_name)
        if not code:
            continue
        nav = _fetch_nav_from_mfapi(code)
        if nav > 0:
            fund["scheme_code"] = code
            fund["nav"] = round(nav, 4)
            fund["nav_retrieved_at"] = (_mf_nav_cache.get(code) or {}).get("retrieved_at")
            fund["nav_date"] = (_mf_nav_cache.get(code) or {}).get("nav_date")
            fund["nav_source"] = "mfapi.in"
            fund["current_value"] = round(fund.get("units", 0) * nav, 2)
            inv = fund.get("invested", 0)
            fund["return_pct"] = round((fund["current_value"] - inv) / inv * 100, 2) if inv > 0 else 0
            updated_count += 1

    if updated_count > 0:
        _save_mf_portfolio()
        print(f"[MF NAV] Updated {updated_count}/{len(user_mf_portfolio)} funds via mfapi.in")


@app.post("/api/mf-portfolio/refresh-nav")
def refresh_mf_nav():
    """Force refresh NAV for all MF holdings."""
    import time
    global _mf_nav_last_refresh
    _mf_nav_last_refresh = 0  # force refresh
    _refresh_mf_nav()
    return {
        "status": "refreshed",
        "funds": len(user_mf_portfolio),
        "source": "Kite" if _is_kite_connected() else "mfapi.in",
        "navs": {f["scheme_name"]: f.get("nav", 0) for f in user_mf_portfolio},
    }


@app.post("/api/kite/sync-mf")
def kite_sync_mf():
    """Force sync MF holdings from Kite."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    _sync_mf_from_kite()
    return {"status": "synced", "mf_count": len(user_mf_portfolio)}


# ──────────────────────────────────────
# MF Transaction Management
# ──────────────────────────────────────

class MFTransactionRequest(BaseModel):
    scheme_name: str
    date: str
    invested: float = 0
    redeemed: float = 0
    units: float = 0
    nav: float = 0

class MFTransactionEditRequest(BaseModel):
    scheme_name: str
    index: int
    date: str
    invested: float = 0
    redeemed: float = 0
    units: float = 0
    nav: float = 0

class MFTransactionDeleteRequest(BaseModel):
    scheme_name: str
    index: int

def _recalc_mf_fund(fund: dict):
    """Recalculate fund summary from its transactions."""
    txns = fund.get("transactions", [])
    if not txns:
        return
    total_invested = sum(t.get("invested", 0) for t in txns)
    total_redeemed = sum(t.get("redeemed", 0) for t in txns)
    total_units = sum(
        t.get("units", 0) * (1 if t.get("invested", 0) > 0 else -1)
        for t in txns
    )
    if total_units > 0 and total_invested > 0:
        fund["invested"] = round(total_invested - total_redeemed, 2)
        fund["units"] = round(total_units, 3)
        fund["avg_nav"] = round(total_invested / total_units, 4) if total_units > 0 else 0
        if fund.get("nav", 0) > 0:
            fund["current_value"] = round(total_units * fund["nav"], 2)
        pnl = fund["current_value"] - fund["invested"]
        fund["return_pct"] = round((pnl / fund["invested"]) * 100, 2) if fund["invested"] > 0 else 0


def _seed_opening_balance(fund: dict) -> bool:
    """Preserve an existing cost basis before the fund's first transaction.

    :func:`_recalc_mf_fund` recomputes ``invested`` and ``units`` from the
    transaction list ALONE. A Kite-synced fund arrives with a real
    ``invested``/``units`` but an empty ``transactions`` list, so appending a
    single ₹10,000 top-up would recompute the whole position from that one row
    and silently replace a ₹3,00,000 cost basis with ₹10,000.

    Seeding an explicit opening row first makes the recalculation correct: the
    existing position becomes transaction zero, and the top-up adds to it. The
    row is marked ``seeded`` so the UI can show it as an opening balance rather
    than a real dated purchase — its date is a placeholder, not a fact.

    Returns True when a row was seeded.
    """
    if fund.get("transactions"):
        return False
    invested = float(fund.get("invested") or 0)
    units = float(fund.get("units") or 0)
    if invested <= 0 or units <= 0:
        return False

    nav = fund.get("avg_nav") or fund.get("nav") or 0
    if not nav:
        nav = round(invested / units, 4) if units else 0
    fund["transactions"] = [{
        # No purchase date exists for a synced opening position. Backdate it so
        # it always sorts before any real transaction the user adds.
        "date": fund.get("first_purchase_date") or "2000-01-01",
        "invested": round(invested, 2),
        "redeemed": 0,
        "units": round(units, 3),
        "nav": round(float(nav), 4),
        "ref": "opening-balance",
        "seeded": True,
    }]
    return True


def _append_mf_txn(fund: dict, txn: dict) -> dict:
    """Append one transaction to a fund and recompute its summary.

    The single write path for MF transactions, so the opening-balance guard
    above can never be bypassed.
    """
    if "transactions" not in fund:
        fund["transactions"] = []
    seeded = _seed_opening_balance(fund)
    fund["transactions"].append(txn)
    fund["transactions"].sort(key=lambda t: t.get("date", ""))
    _recalc_mf_fund(fund)
    _save_mf_portfolio()
    return {"seeded_opening_balance": seeded}


@app.post("/api/mf-portfolio/transaction")
def add_mf_transaction(req: MFTransactionRequest):
    """Add a new transaction to a mutual fund."""
    for fund in user_mf_portfolio:
        if fund["scheme_name"] == req.scheme_name:
            _append_mf_txn(fund, {
                "date": req.date,
                "invested": req.invested,
                "redeemed": req.redeemed,
                "units": req.units,
                "nav": req.nav,
            })
            return {"status": "added", "fund": fund}
    raise HTTPException(status_code=404, detail=f"Fund not found: {req.scheme_name}")


@app.put("/api/mf-portfolio/transaction")
def edit_mf_transaction(req: MFTransactionEditRequest):
    """Edit an existing transaction."""
    for fund in user_mf_portfolio:
        if fund["scheme_name"] == req.scheme_name:
            txns = fund.get("transactions", [])
            if req.index < 0 or req.index >= len(txns):
                raise HTTPException(400, "Invalid transaction index")
            txns[req.index] = {
                "date": req.date,
                "invested": req.invested,
                "redeemed": req.redeemed,
                "units": req.units,
                "nav": req.nav,
            }
            fund["transactions"].sort(key=lambda t: t["date"])
            _recalc_mf_fund(fund)
            _save_mf_portfolio()
            return {"status": "updated", "fund": fund}
    raise HTTPException(404, "Fund not found")


@app.delete("/api/mf-portfolio/transaction")
def delete_mf_transaction(req: MFTransactionDeleteRequest):
    """Delete a transaction."""
    for fund in user_mf_portfolio:
        if fund["scheme_name"] == req.scheme_name:
            txns = fund.get("transactions", [])
            if req.index < 0 or req.index >= len(txns):
                raise HTTPException(400, "Invalid transaction index")
            txns.pop(req.index)
            _recalc_mf_fund(fund)
            _save_mf_portfolio()
            return {"status": "deleted", "fund": fund}
    raise HTTPException(404, "Fund not found")


# ──────────────────────────────────────
# MF Fund Management (Add / Remove)
# ──────────────────────────────────────

@app.get("/api/mf-portfolio/search-fund")
def search_mf_fund(q: str = Query(..., min_length=2)):
    """Search mutual funds on mfapi.in for adding to portfolio."""
    import requests as req_lib
    try:
        r = req_lib.get("https://api.mfapi.in/mf/search", params={"q": q}, timeout=5)
        if r.ok:
            results = r.json()
            # Filter: prefer direct growth plans, limit to 15
            out = []
            for item in results[:50]:
                name = item.get("schemeName", "")
                code = str(item.get("schemeCode", ""))
                out.append({"scheme_name": name, "scheme_code": code})
            return {"results": out[:15]}
        return {"results": []}
    except Exception as e:
        return {"results": [], "error": str(e)}


class AddFundRequest(BaseModel):
    scheme_name: str
    category: str = "Mutual Fund"
    scheme_code: str = ""


class DeleteFundRequest(BaseModel):
    scheme_name: str


@app.post("/api/mf-portfolio/fund")
def add_mf_fund(req: AddFundRequest):
    """Add a new mutual fund to the portfolio."""
    # Check if fund already exists
    for fund in user_mf_portfolio:
        if fund["scheme_name"].lower() == req.scheme_name.lower():
            raise HTTPException(400, f"Fund already exists: {req.scheme_name}")

    # Fetch latest NAV via mfapi.in if scheme_code provided
    nav = 0.0
    if req.scheme_code:
        nav = _fetch_nav_from_mfapi(req.scheme_code)
        # Cache the scheme code for future NAV refreshes
        KNOWN_SCHEME_CODES[req.scheme_name] = req.scheme_code

    new_fund = {
        "scheme_name": req.scheme_name,
        "category": req.category,
        "folio": "",
        "invested": 0,
        "current_value": 0,
        "units": 0,
        "nav": round(nav, 4),
        "avg_nav": 0,
        "return_pct": 0,
        "xirr": 0,
        "transactions": [],
    }
    user_mf_portfolio.append(new_fund)
    _save_mf_portfolio()
    return {"status": "added", "fund": new_fund, "total_funds": len(user_mf_portfolio)}


@app.delete("/api/mf-portfolio/fund")
def delete_mf_fund(req: DeleteFundRequest):
    """Remove a mutual fund from the portfolio."""
    global user_mf_portfolio
    initial_count = len(user_mf_portfolio)
    user_mf_portfolio = [f for f in user_mf_portfolio if f["scheme_name"] != req.scheme_name]
    if len(user_mf_portfolio) == initial_count:
        raise HTTPException(404, f"Fund not found: {req.scheme_name}")
    _save_mf_portfolio()
    return {"status": "deleted", "remaining_funds": len(user_mf_portfolio)}


# ──────────────────────────────────────
# MF Look-through Holdings (per-fund stock composition for overlap analysis)
# ──────────────────────────────────────

class ImportHoldingsRequest(BaseModel):
    scheme_name: str
    holdings_text: str = ""                       # pasted factsheet rows
    holdings: Optional[List[Dict]] = None         # or structured [{stock, pct}]


@app.post("/api/mf-portfolio/holdings")
def import_mf_holdings(req: ImportHoldingsRequest):
    """Store a fund's stock-level holdings so overlap analysis works for it.

    Accepts pasted factsheet text ('Company<TAB>X.XX%') which is parsed and
    name-resolved to NSE tickers, or a pre-structured holdings list.
    """
    if req.holdings:
        parsed = [
            {"stock": h["stock"], "pct": float(h.get("pct", 0) or 0),
             "name": h.get("name", h["stock"]), "resolved": True}
            for h in req.holdings if h.get("stock")
        ]
        unresolved = []
    else:
        parsed, unresolved = _parse_holdings_text(req.holdings_text or "")
    if not parsed:
        raise HTTPException(400, "No equity holdings (>=1%) could be parsed from the input")
    user_mf_holdings[req.scheme_name] = [{"stock": h["stock"], "pct": h["pct"]} for h in parsed]
    _save_mf_holdings()
    return {
        "status": "saved",
        "scheme_name": req.scheme_name,
        "count": len(parsed),
        "resolved": sum(1 for h in parsed if h.get("resolved", True)),
        "unresolved": unresolved,
        "holdings": parsed,
    }


@app.get("/api/mf-portfolio/holdings")
def get_stored_mf_holdings(scheme_name: str = Query(None)):
    """Return stored look-through holdings for one fund, or all funds."""
    if scheme_name:
        return {"scheme_name": scheme_name, "holdings": _lookup_stored_holdings(scheme_name)}
    return {"funds": list(user_mf_holdings.keys()), "holdings": user_mf_holdings}


@app.delete("/api/mf-portfolio/holdings")
def delete_stored_mf_holdings(req: DeleteFundRequest):
    """Remove stored look-through holdings for a fund."""
    if req.scheme_name in user_mf_holdings:
        del user_mf_holdings[req.scheme_name]
        _save_mf_holdings()
        return {"status": "deleted", "scheme_name": req.scheme_name}
    raise HTTPException(404, f"No stored holdings for: {req.scheme_name}")


@app.get("/api/mf-portfolio/analyze")
def analyze_mf_portfolio():
    """Analyze actual MF portfolio like SIP simulator — uses real transaction data."""
    from datetime import datetime as dt

    results = []
    portfolio_cashflows = []  # for overall XIRR
    total_invested = 0
    total_current = 0
    today = dt.now()

    for fund in user_mf_portfolio:
        txns = fund.get("transactions", [])
        if not txns:
            continue

        scheme = fund["scheme_name"]
        current_nav = fund.get("nav", 0)
        total_units = 0.0
        fund_invested = 0.0
        fund_cashflows = []
        monthly_detail = []

        for txn in sorted(txns, key=lambda t: t["date"]):
            txn_date = dt.strptime(txn["date"], "%Y-%m-%d")
            inv = txn.get("invested", 0)
            red = txn.get("redeemed", 0)
            u = txn.get("units", 0)
            nav = txn.get("nav", 0)

            if inv > 0:
                total_units += u
                fund_invested += inv
                fund_cashflows.append((txn_date, -inv))
                portfolio_cashflows.append((txn_date, -inv))
            elif red > 0:
                total_units -= u
                fund_invested -= red
                fund_cashflows.append((txn_date, red))
                portfolio_cashflows.append((txn_date, red))

            cur_val_at = total_units * nav
            monthly_detail.append({
                "date": txn["date"],
                "invested": round(inv, 2),
                "redeemed": round(red, 2),
                "nav": round(nav, 4),
                "units_bought": round(u, 4),
                "cumulative_units": round(total_units, 4),
                "cumulative_invested": round(fund_invested, 2),
                "current_value": round(cur_val_at, 2),
                "pnl": round(cur_val_at - fund_invested, 2),
            })

        cur_val = round(total_units * current_nav, 2) if current_nav > 0 else fund.get("current_value", 0)
        pnl = round(cur_val - fund_invested, 2)
        pct = round(pnl / fund_invested * 100, 2) if fund_invested > 0 else 0

        # XIRR
        sym_cf = fund_cashflows + [(today, cur_val)]
        xirr_val = sip_simulator._xirr(sym_cf) if len(fund_cashflows) >= 1 else 0

        # Yearly aggregation
        yearly = {}
        for md in monthly_detail:
            year = md["date"][:4]
            if year not in yearly:
                yearly[year] = {"year": year, "invested": 0, "months": 0}
            yearly[year]["invested"] += md["invested"]
            yearly[year]["months"] += 1
        for year in yearly:
            year_entries = [md for md in monthly_detail if md["date"][:4] == year]
            if year_entries:
                last = year_entries[-1]
                yearly[year]["cumulative_units"] = last["cumulative_units"]
                yearly[year]["cumulative_invested"] = last["cumulative_invested"]
                yearly[year]["nav"] = last["nav"]
                yearly[year]["value"] = round(last["cumulative_units"] * last["nav"], 2)
                yearly[year]["pnl"] = round(yearly[year]["value"] - last["cumulative_invested"], 2)
                inv_y = last["cumulative_invested"]
                yearly[year]["return_pct"] = round(yearly[year]["pnl"] / inv_y * 100, 2) if inv_y > 0 else 0
        yearly_list = sorted(yearly.values(), key=lambda x: x["year"])

        # Timeline for chart
        timeline = []
        cum_inv = 0.0
        cum_units = 0.0
        for txn in sorted(txns, key=lambda t: t["date"]):
            inv = txn.get("invested", 0)
            u = txn.get("units", 0)
            nav = txn.get("nav", 0)
            cum_inv += inv
            cum_units += u
            val = cum_units * nav
            p = val - cum_inv
            pp = (p / cum_inv * 100) if cum_inv > 0 else 0
            timeline.append({"date": txn["date"], "invested": round(cum_inv, 2), "value": round(val, 2), "pnl": round(p, 2), "pnl_pct": round(pp, 2)})
        # Add current value as last point
        if current_nav > 0 and timeline:
            today_str = today.strftime("%Y-%m-%d")
            val = total_units * current_nav
            p = val - fund_invested
            pp = (p / fund_invested * 100) if fund_invested > 0 else 0
            timeline.append({"date": today_str, "invested": round(fund_invested, 2), "value": round(val, 2), "pnl": round(p, 2), "pnl_pct": round(pp, 2)})

        total_invested += fund_invested
        total_current += cur_val

        results.append({
            "symbol": scheme,
            "label": scheme,
            "type": fund.get("category", "Mutual Fund"),
            "source": "Portfolio",
            "amount_per_month": 0,
            "units": round(total_units, 4),
            "invested": round(fund_invested, 2),
            "current_value": cur_val,
            "pnl": pnl,
            "return_pct": pct,
            "cagr": xirr_val,
            "last_price": current_nav,
            "monthly": monthly_detail,
            "yearly": yearly_list,
            "timeline": timeline,
        })

    results.sort(key=lambda x: x["return_pct"], reverse=True)

    # Portfolio-level XIRR
    portfolio_cashflows.append((today, total_current))
    portfolio_xirr = sip_simulator._xirr(portfolio_cashflows) if len(portfolio_cashflows) >= 2 else 0

    abs_ret = round(total_current - total_invested, 2)
    pct_ret = round(abs_ret / total_invested * 100, 2) if total_invested > 0 else 0

    # Build combined timeline — carry forward each fund's last known values
    combined_tl = []
    all_dates = sorted({d for r in results for t in r.get("timeline", []) for d in [t["date"]]})
    # For each fund, build a sorted list of (date, invested, value) for carry-forward
    fund_timelines = []
    for r in results:
        tl = sorted(r.get("timeline", []), key=lambda t: t["date"])
        fund_timelines.append(tl)

    for date_str in all_dates:
        ci = 0.0
        cv = 0.0
        for ftl in fund_timelines:
            # Find the last entry at or before this date (carry-forward)
            last_inv = 0.0
            last_val = 0.0
            for pt in ftl:
                if pt["date"] <= date_str:
                    last_inv = pt["invested"]
                    last_val = pt["value"]
                else:
                    break
            ci += last_inv
            cv += last_val
        if ci > 0 or cv > 0:
            p = cv - ci
            pp = (p / ci * 100) if ci > 0 else 0
            combined_tl.append({"date": date_str, "invested": round(ci, 2), "value": round(cv, 2), "pnl": round(p, 2), "pnl_pct": round(pp, 2)})

    # Calculate actual investment period in months from earliest txn to today
    all_txn_dates = [
        dt.strptime(md["date"], "%Y-%m-%d")
        for r in results for md in r.get("monthly", [])
    ]
    if all_txn_dates:
        earliest = min(all_txn_dates)
        period_months = (today.year - earliest.year) * 12 + (today.month - earliest.month)
        first_date = earliest.strftime("%Y-%m-%d")
    else:
        period_months = 0
        first_date = ""
    total_transactions = sum(len(r["monthly"]) for r in results)

    return {
        "start_date": first_date,
        "sip_count": period_months,
        "total_transactions": total_transactions,
        "data_source": "Portfolio",
        "total_invested": round(total_invested, 2),
        "portfolio_value": round(total_current, 2),
        "absolute_return": abs_ret,
        "return_pct": pct_ret,
        "cagr": portfolio_xirr,
        "monthly_total": 0,
        "num_symbols": len(results),
        "per_symbol": results,
        "timeline": combined_tl,
    }


@app.get("/api/kite/quote/{symbol}")
def kite_quote(symbol: str):
    """Get full quote for a symbol via Kite."""
    if not _is_kite_connected():
        raise HTTPException(status_code=400, detail="Kite not connected")
    kite_sym = kite_client.symbol_to_kite_format(_yf_symbol(symbol))
    quotes = kite_client.get_quotes([kite_sym])
    if quotes and kite_sym in quotes:
        return {"symbol": symbol, "quote": quotes[kite_sym]}
    raise HTTPException(status_code=404, detail=f"No quote data for {symbol}")


# ──────────────────────────────────────
# MF Category Analysis
# ──────────────────────────────────────
mf_analysis_state = {"running": False, "category": "", "progress": 0, "total": 0, "msg": "", "results": None, "error": None}

class MFAnalyzeRequest(BaseModel):
    category: str
    scheme_codes: list  # List of scheme codes to analyze

def _run_mf_analysis(category: str, scheme_codes: list):
    def progress_cb(i, total, msg):
        mf_analysis_state["progress"] = i
        mf_analysis_state["total"] = total
        mf_analysis_state["msg"] = msg
    try:
        mf_analysis_state["running"] = True
        mf_analysis_state["error"] = None
        mf_analysis_state["category"] = category
        result = mf_analysis.analyze_funds(scheme_codes, category, progress_cb)
        mf_analysis_state["results"] = result
    except Exception as e:
        mf_analysis_state["error"] = str(e)
        import traceback; traceback.print_exc()
    finally:
        mf_analysis_state["running"] = False

@app.get("/api/mf-analysis/search")
def mf_search(q: str = Query(...)):
    """Search for MF funds — returns list for user to pick from."""
    funds = mf_analysis.search_funds(q, kite_client=kite_client if _is_kite_connected() else None)
    return {"query": q, "funds": funds, "total": len(funds), "kite_connected": _is_kite_connected()}

@app.post("/api/mf-analysis/start")
def start_mf_analysis_selected(req: MFAnalyzeRequest):
    """Analyze user-selected funds."""
    if mf_analysis_state["running"]:
        return {"status": "already_running"}
    mf_analysis_state["results"] = None
    t = threading.Thread(target=_run_mf_analysis, args=(req.category, req.scheme_codes), daemon=True)
    t.start()
    return {"status": "started", "category": req.category, "count": len(req.scheme_codes)}

@app.get("/api/mf-analysis/status")
def mf_analysis_status():
    return {**mf_analysis_state}


# ──────────────────────────────────────
# Comprehensive Wealth Report
# ──────────────────────────────────────

@app.get("/api/report/wealth")
def get_wealth_report():
    """Generate a comprehensive wealth report aggregating all portfolio data."""
    from datetime import datetime

    report_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
    data_source = "Zerodha Kite MCP" if _is_kite_connected() else "Yahoo Finance"

    # ── Stock Holdings ──
    stock_holdings = []
    total_stock_invested = 0
    total_stock_value = 0
    sector_map = {}  # sector -> {invested, value, count}
    top_gainer = None
    top_loser = None

    for item in user_portfolio:
        cached = live_price_cache.get(item["symbol"])
        if cached:
            current, prev = cached["current"], cached["prev"]
        else:
            current, prev = _fetch_price(_yf_symbol(item["symbol"]))
        if current is None:
            continue

        qty = item["shares"]
        avg_cost = item.get("avg_cost", current)
        invested = qty * avg_cost
        cur_val = qty * current
        pnl = cur_val - invested
        net_chg = ((current - avg_cost) / avg_cost * 100) if avg_cost else 0
        day_chg = ((current - prev) / prev * 100) if prev else 0
        total_stock_invested += invested
        total_stock_value += cur_val

        sector = "Other"
        for s in POPULAR_INDIAN_STOCKS:
            if s["symbol"] == item["symbol"]:
                sector = s["sector"]
                break

        holding = {
            "symbol": item["symbol"],
            "name": item.get("name", item["symbol"].replace(".NS", "")),
            "sector": sector,
            "shares": qty,
            "avg_cost": round(avg_cost, 2),
            "current_price": round(current, 2),
            "invested": round(invested, 2),
            "current_value": round(cur_val, 2),
            "pnl": round(pnl, 2),
            "net_chg": round(net_chg, 2),
            "day_chg": round(day_chg, 2),
            "weight_pct": 0,  # will calculate after
        }
        stock_holdings.append(holding)

        # Sector aggregation
        if sector not in sector_map:
            sector_map[sector] = {"invested": 0, "value": 0, "count": 0, "pnl": 0}
        sector_map[sector]["invested"] += invested
        sector_map[sector]["value"] += cur_val
        sector_map[sector]["count"] += 1
        sector_map[sector]["pnl"] += pnl

        # Track top gainer/loser
        if top_gainer is None or net_chg > top_gainer["net_chg"]:
            top_gainer = holding
        if top_loser is None or net_chg < top_loser["net_chg"]:
            top_loser = holding

    # Calculate weights
    for h in stock_holdings:
        h["weight_pct"] = round((h["current_value"] / total_stock_value * 100) if total_stock_value > 0 else 0, 2)

    # Per-holding + book XIRR from the dated ledger. This endpoint names the
    # value key "current_value" where the ledger helpers expect "total_value",
    # so hand them a shim rather than compute the annualised return twice.
    _xirr_rows = [{"symbol": h["symbol"], "shares": h["shares"],
                   "total_value": h["current_value"], "avg_cost": h["avg_cost"]}
                  for h in stock_holdings]
    stock_xirr_book = _annotate_xirr(_xirr_rows)
    for h, r in zip(stock_holdings, _xirr_rows):
        h["xirr"] = r["xirr"]
        h["xirr_basis"] = r["xirr_basis"]
        h["xirr_exact"] = r["xirr_exact"]

    stock_pnl = total_stock_value - total_stock_invested
    stock_pnl_pct = (stock_pnl / total_stock_invested * 100) if total_stock_invested > 0 else 0

    # Sector breakdown
    sector_breakdown = []
    for sec, data in sorted(sector_map.items(), key=lambda x: x[1]["value"], reverse=True):
        sector_breakdown.append({
            "sector": sec,
            "invested": round(data["invested"], 2),
            "value": round(data["value"], 2),
            "pnl": round(data["pnl"], 2),
            "pnl_pct": round((data["pnl"] / data["invested"] * 100) if data["invested"] > 0 else 0, 2),
            "weight_pct": round((data["value"] / total_stock_value * 100) if total_stock_value > 0 else 0, 2),
            "count": data["count"],
        })

    # ── Mutual Fund Holdings ──
    mf_holdings = []
    total_mf_invested = 0
    total_mf_value = 0
    mf_category_map = {}

    for mf in user_mf_portfolio:
        invested = mf.get("invested", 0)
        current = mf.get("current_value", 0)
        pnl = current - invested
        total_mf_invested += invested
        total_mf_value += current

        cat = mf.get("category", "Unknown")
        if cat not in mf_category_map:
            mf_category_map[cat] = {"invested": 0, "value": 0, "count": 0, "pnl": 0}
        mf_category_map[cat]["invested"] += invested
        mf_category_map[cat]["value"] += current
        mf_category_map[cat]["count"] += 1
        mf_category_map[cat]["pnl"] += pnl

        mf_holdings.append({
            "scheme_name": mf.get("scheme_name", ""),
            "category": cat,
            "folio": mf.get("folio", ""),
            "units": round(mf.get("units", 0), 3),
            "avg_nav": round(mf.get("avg_nav", 0), 4),
            "nav": round(mf.get("nav", 0), 4),
            "invested": round(invested, 2),
            "current_value": round(current, 2),
            "pnl": round(pnl, 2),
            "return_pct": round(mf.get("return_pct", 0), 2),
            "xirr": round(mf.get("xirr", 0), 2),
            "weight_pct": 0,
        })

    for mf in mf_holdings:
        mf["weight_pct"] = round((mf["current_value"] / total_mf_value * 100) if total_mf_value > 0 else 0, 2)

    mf_pnl = total_mf_value - total_mf_invested
    mf_pnl_pct = (mf_pnl / total_mf_invested * 100) if total_mf_invested > 0 else 0

    mf_category_breakdown = []
    for cat, data in sorted(mf_category_map.items(), key=lambda x: x[1]["value"], reverse=True):
        mf_category_breakdown.append({
            "category": cat,
            "invested": round(data["invested"], 2),
            "value": round(data["value"], 2),
            "pnl": round(data["pnl"], 2),
            "pnl_pct": round((data["pnl"] / data["invested"] * 100) if data["invested"] > 0 else 0, 2),
            "weight_pct": round((data["value"] / total_mf_value * 100) if total_mf_value > 0 else 0, 2),
            "count": data["count"],
        })

    # ── Combined Totals ──
    total_invested = total_stock_invested + total_mf_invested
    total_value = total_stock_value + total_mf_value
    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    # ── XIRR ──
    # Equity and MF cashflows are pooled into one solve rather than averaged,
    # so the combined figure is a real rate on the real timeline. Only the part
    # of the book with dated cashflows behind it is included, and covered_pct
    # says how much of the book that is.
    mf_flows, mf_covered_value = _mf_cashflows()
    stock_flows = []
    for sym in stock_xirr_book["covered_symbols"]:
        stock_flows.extend(equity_txns.cashflows(user_equity_txns.get(sym) or []))
    mf_xirr = _solve_xirr(mf_flows, mf_covered_value)
    combined_covered = stock_xirr_book["covered_value"] + mf_covered_value
    combined_xirr = _solve_xirr(stock_flows + mf_flows, combined_covered)
    combined_covered_pct = round(combined_covered / total_value * 100, 2) if total_value > 0 else 0.0

    # Asset allocation
    asset_allocation = {
        "stocks": {
            "invested": round(total_stock_invested, 2),
            "value": round(total_stock_value, 2),
            "weight_pct": round((total_stock_value / total_value * 100) if total_value > 0 else 0, 2),
            "count": len(stock_holdings),
        },
        "mutual_funds": {
            "invested": round(total_mf_invested, 2),
            "value": round(total_mf_value, 2),
            "weight_pct": round((total_mf_value / total_value * 100) if total_value > 0 else 0, 2),
            "count": len(mf_holdings),
        },
    }

    # ── Kite-specific data (margins, positions, orders) ──
    margins_data = None
    positions_data = None
    orders_data = None
    trades_data = None

    if _is_kite_connected():
        try:
            margins_data = kite_client.get_margins()
        except:
            pass
        try:
            positions_data = kite_client.get_positions()
        except:
            pass
        try:
            orders_data = kite_client.get_orders()
        except:
            pass
        try:
            trades_data = kite_client.get_trades()
        except:
            pass

    # ── Kite Profile ──
    kite_profile = None
    if _is_kite_connected() and kite_client.profile:
        kite_profile = {
            "user_name": kite_client._user_name,
            "user_id": kite_client._user_id,
            "email": kite_client._email,
            "broker": "Zerodha",
        }

    return {
        "report_time": report_time,
        "data_source": data_source,
        "kite_connected": _is_kite_connected(),
        "kite_profile": kite_profile,

        # Combined summary
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "total_xirr": combined_xirr,
            "xirr_covered_pct": combined_covered_pct,
            "total_instruments": len(stock_holdings) + len(mf_holdings),
        },

        # Asset allocation
        "asset_allocation": asset_allocation,

        # Stocks
        "stocks": {
            "holdings": stock_holdings,
            "total_invested": round(total_stock_invested, 2),
            "total_value": round(total_stock_value, 2),
            "total_pnl": round(stock_pnl, 2),
            "total_pnl_pct": round(stock_pnl_pct, 2),
            "total_xirr": stock_xirr_book["xirr"],
            "xirr_covered_pct": stock_xirr_book["covered_pct"],
            "count": len(stock_holdings),
            "sector_breakdown": sector_breakdown,
            "top_gainer": top_gainer,
            "top_loser": top_loser,
        },

        # Mutual Funds
        "mutual_funds": {
            "holdings": mf_holdings,
            "total_invested": round(total_mf_invested, 2),
            "total_value": round(total_mf_value, 2),
            "total_pnl": round(mf_pnl, 2),
            "total_pnl_pct": round(mf_pnl_pct, 2),
            "total_xirr": mf_xirr,
            "xirr_covered_pct": round(mf_covered_value / total_mf_value * 100, 2) if total_mf_value > 0 else 0.0,
            "count": len(mf_holdings),
            "category_breakdown": mf_category_breakdown,
        },

        # Kite-specific
        "margins": margins_data,
        "positions": positions_data,
        "orders": orders_data,
        "trades": trades_data,
    }


# ── SIP Simulator ──────────────────────────────────────────────
class SIPRequest(BaseModel):
    symbols: list
    start_date: str
    sip_day: int = 1       # Day of month for SIP (1-28)
    step_up_pct: float = 0 # Annual step-up percentage
    custom_entries: list = None  # [{date, amount, type}] for extra/override/skip

@app.get("/api/sip/search")
def sip_search(q: str = Query("", min_length=2)):
    """Universal search: stocks, ETFs, mutual funds."""
    return {"results": sip_simulator.search_instruments(q)}

@app.post("/api/sip/simulate")
def run_sip_simulation(req: SIPRequest):
    """Run SIP simulation for given symbols and start date."""
    if not req.symbols or len(req.symbols) > 10:
        raise HTTPException(400, "Provide 1-10 symbols")
    try:
        result = sip_simulator.simulate_sip(req.symbols, req.start_date, sip_day=req.sip_day, step_up_pct=req.step_up_pct, custom_entries=req.custom_entries)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ──────────────────────────────────────
# Settings API
# ──────────────────────────────────────

class UpdateSettingsRequest(BaseModel):
    ollama_url: str = None
    model_name: str = None
    theme: str = None
    auto_refresh_nav: bool = None
    nav_refresh_interval: int = None

@app.get("/api/settings")
def get_settings():
    """Get current app settings."""
    return app_settings

@app.put("/api/settings")
def update_settings(req: UpdateSettingsRequest):
    """Update app settings."""
    global app_settings
    updates = {k: v for k, v in req.dict().items() if v is not None}
    app_settings.update(updates)
    _save_settings(app_settings)
    # Apply to ai_models dynamically
    if "ollama_url" in updates or "model_name" in updates:
        ai_models.OLLAMA_API_URL = app_settings["ollama_url"].rstrip("/") + "/api/generate"
        ai_models.MODEL_NAME = app_settings["model_name"]
    return {"status": "saved", "settings": app_settings}

@app.get("/api/settings/ollama-models")
def list_ollama_models():
    """Fetch available models from Ollama."""
    import requests as req_lib
    try:
        url = app_settings["ollama_url"].rstrip("/") + "/api/tags"
        r = req_lib.get(url, timeout=5)
        if r.ok:
            data = r.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return {"connected": True, "models": models}
        return {"connected": False, "models": [], "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"connected": False, "models": [], "error": str(e)}

@app.post("/api/settings/test-ollama")
def test_ollama_connection():
    """Test Ollama connection and model availability."""
    import requests as req_lib
    url = app_settings["ollama_url"].rstrip("/")
    try:
        # Check server
        r = req_lib.get(url + "/api/tags", timeout=5)
        if not r.ok:
            return {"status": "error", "message": f"Ollama server returned HTTP {r.status_code}"}
        models = [m.get("name", "") for m in r.json().get("models", [])]
        model_found = app_settings["model_name"] in models
        # Quick test generate
        test_ok = False
        if model_found:
            try:
                tr = req_lib.post(url + "/api/generate", json={"model": app_settings["model_name"], "prompt": "Say OK", "stream": False}, timeout=15)
                test_ok = tr.ok
            except Exception:
                pass
        return {
            "status": "ok" if model_found else "model_missing",
            "server_connected": True,
            "models_available": models,
            "current_model": app_settings["model_name"],
            "model_found": model_found,
            "test_response": test_ok,
        }
    except Exception as e:
        return {"status": "error", "server_connected": False, "message": str(e)}


# ═══════════════════════════════════════════════════════════
# ██  GOOGLE AUTH + DRIVE SYNC
# ═══════════════════════════════════════════════════════════

@app.get("/api/auth/profile")
async def auth_profile():
    """Get current user profile (or null if not logged in)."""
    profile = google_auth.get_profile()
    if profile and profile.get("email") and profile["email"] != _current_user_email:
        _switch_user_data(profile["email"])
    return profile or {"logged_in": False}

@app.get("/api/auth/google/url")
async def auth_google_url():
    """Get Google OAuth login URL and start callback server."""
    google_auth.start_callback_server()
    url = google_auth.get_auth_url()
    return {"url": url}

@app.post("/api/auth/google/callback")
async def auth_google_callback(code: str = Query(...)):
    """Exchange OAuth code for tokens."""
    result = google_auth.exchange_code(code)
    if result:
        # Switch to per-user data directory
        email = result.get("email")
        if email:
            _switch_user_data(email)
        return {"success": True, "name": result.get("name"), "email": email, "picture": result.get("picture")}
    raise HTTPException(400, "Authentication failed")

@app.post("/api/auth/logout")
async def auth_logout():
    """Clear auth session."""
    google_auth.clear_auth()
    _switch_user_data(None)  # Reset to empty state
    return {"success": True}

@app.post("/api/drive/sync")
async def drive_sync(direction: str = Query("upload")):
    """Sync data to/from Google Drive. direction: 'upload' or 'download'"""
    profile = google_auth.get_profile()
    if not profile:
        raise HTTPException(401, "Not logged in")
    email = profile.get("email")
    user_dir = _user_data_dir(email) if email else None
    results = google_auth.drive_sync_all(direction, data_dir=user_dir)
    # After download, reload data into memory
    if direction == "download" and email:
        _switch_user_data(email)
    return {"success": True, "direction": direction, "files": results}

@app.get("/api/drive/status")
async def drive_status():
    """Check Drive sync status."""
    profile = google_auth.get_profile()
    return {"synced": profile is not None, "logged_in": profile is not None}


# ══════════════════════════════════════════════════════════════
#  EXPENSE RAW-DATASET BACKUP / SYNC (Google Drive)
# ══════════════════════════════════════════════════════════════
#  The Flutter app keeps the live dataset in Hive; these endpoints persist a
#  copy to the per-user data dir and back it up to Google Drive (appDataFolder):
#    - a stable master file (overwritten each save)
#    - a timestamped backup (never overwritten → full version history)
#    - the dashboard history log
#  Restore reads any backup/master back from Drive.

def _expense_dir() -> Path:
    """The dir where expense master/backups live (per-user when signed in)."""
    if _current_user_email:
        return _user_data_dir(_current_user_email)
    return DATA_DIR

# Daily backups kept on Drive (and locally) before the oldest are pruned. Every
# save used to leave a new per-minute backup behind, forever.
EXPENSE_BACKUPS_KEPT = 30

# File names on disk and Drive are "<prefix>_master.json" and
# "<prefix>_backup_<date>.json". The prefix defaults to "expense"; an optional,
# git-ignored data/expense_config.json ({"file_prefix": "..."}) overrides it so
# an existing install keeps finding the files it already has.
EXPENSE_FILE_PREFIX_DEFAULT = "expense"


def _expense_config() -> dict:
    """The optional local expense config; missing or unreadable -> {}."""
    try:
        cfg = json.loads((DATA_DIR / "expense_config.json").read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def _expense_file_prefix() -> str:
    prefix = _expense_config().get("file_prefix")
    return prefix.strip() if isinstance(prefix, str) and prefix.strip() else EXPENSE_FILE_PREFIX_DEFAULT


def _expense_backup_prefix() -> str:
    return _expense_file_prefix() + "_backup_"


def _expense_master_name() -> str:
    return _expense_file_prefix() + "_master.json"


def _prune_expense_backups(d: Path, keep: int = EXPENSE_BACKUPS_KEPT,
                           remote: bool = True) -> int:
    """Delete all but the newest `keep` backups. Returns how many went."""
    removed = 0
    prefix = _expense_backup_prefix()
    local = sorted((p for p in d.glob(prefix + "*.json")),
                   key=lambda p: p.name, reverse=True)
    for old in local[keep:]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    if remote:
        # Names embed the date, so name order is age order; drive_list_files
        # is newest-modified first, which a restored old backup would upset.
        files = sorted(google_auth.drive_list_files(prefix=prefix),
                       key=lambda f: f.get("name", ""), reverse=True)
        for f in files[keep:]:
            if google_auth.drive_delete_file(f.get("id")):
                removed += 1
    return removed


@app.post("/api/expense/backup")
async def expense_backup(payload: dict = Body(...)):
    """Save the dataset locally and (if signed in) upload master + dated
    backup + history log to Google Drive.

    Body: {master, master_name, backup_name?, history?, history_name?}

    Only what CHANGED travels: a file whose bytes Drive already holds is not
    re-uploaded (no new Drive revision), and a backup is written only when the
    master itself changed — a save with no edits used to leave one more
    "version" behind every time.
    """
    d = _expense_dir()
    d.mkdir(parents=True, exist_ok=True)
    master_name = payload.get("master_name") or _expense_master_name()
    backup_name = payload.get("backup_name")
    history_name = payload.get("history_name") or "dashboard_history_log.json"

    written = []
    master_changed = False
    try:
        master = payload.get("master")
        if master is not None:
            text = json.dumps(master, indent=2, ensure_ascii=False)
            path = d / master_name
            try:
                master_changed = path.read_text(encoding="utf-8") != text
            except OSError:
                master_changed = True
            if master_changed:
                path.write_text(text, encoding="utf-8")
            written.append(master_name)
        history = payload.get("history")
        if history is not None:
            (d / history_name).write_text(
                json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
            written.append(history_name)
    except Exception as e:
        raise HTTPException(500, f"Local save failed: {e}")

    profile = google_auth.get_profile()
    authenticated = profile is not None
    uploads = {}
    statuses = {}
    if authenticated:
        for name in written:
            try:
                statuses[name] = google_auth.drive_sync_file(name, data_dir=d)
            except Exception as e:
                print(f"[Expense] Drive upload failed for {name}: {e}")
                statuses[name] = google_auth.SYNC_FAILED
            uploads[name] = statuses[name] != google_auth.SYNC_FAILED

    # A backup marks a new state of the master. "Changed" is judged against
    # Drive when signed in (another device may hold these same bytes already)
    # and against the local copy otherwise.
    if master is not None and backup_name:
        new_state = (statuses.get(master_name) in (
            google_auth.SYNC_CREATED, google_auth.SYNC_UPDATED)
            if authenticated else master_changed)
        if new_state:
            try:
                (d / backup_name).write_text(text, encoding="utf-8")
                written.append(backup_name)
                if authenticated:
                    statuses[backup_name] = google_auth.drive_sync_file(
                        backup_name, data_dir=d)
                    uploads[backup_name] = (statuses[backup_name]
                                            != google_auth.SYNC_FAILED)
                _prune_expense_backups(d, remote=authenticated)
            except Exception as e:
                print(f"[Expense] Backup failed for {backup_name}: {e}")

    all_ok = authenticated and all(uploads.values()) and bool(uploads)
    return {
        "saved": True,
        "authenticated": authenticated,
        "written": written,
        "uploads": uploads,
        "sync": statuses,
        "unchanged": authenticated and bool(statuses) and all(
            v == google_auth.SYNC_UNCHANGED for v in statuses.values()),
        "driveStatus": "success" if all_ok else ("pending" if not authenticated else "failed"),
    }

@app.get("/api/expense/versions")
async def expense_versions():
    """List saved dataset versions on Google Drive (master + backups)."""
    profile = google_auth.get_profile()
    if not profile:
        return {"authenticated": False, "versions": []}
    files = google_auth.drive_list_files(prefix=_expense_file_prefix() + "_")
    return {
        "authenticated": True,
        "versions": [
            {"name": f.get("name"), "modifiedTime": f.get("modifiedTime"),
             "size": f.get("size")}
            for f in files
        ],
    }

@app.get("/api/expense/version")
async def expense_version(name: str = Query(...)):
    """Fetch a specific dataset version's JSON content from Drive."""
    profile = google_auth.get_profile()
    if not profile:
        raise HTTPException(401, "Not logged in")
    content = google_auth.drive_get_content(name)
    if content is None:
        raise HTTPException(404, f"Version '{name}' not found on Drive")
    try:
        return {"name": name, "master": json.loads(content.decode("utf-8"))}
    except Exception as e:
        raise HTTPException(500, f"Could not parse '{name}': {e}")

@app.get("/api/expense/drive-meta")
async def expense_drive_meta(name: str = Query(None)):
    """Return Drive modifiedTime for conflict detection, or null."""
    name = name or _expense_master_name()
    profile = google_auth.get_profile()
    if not profile:
        return {"authenticated": False, "meta": None}
    return {"authenticated": True, "meta": google_auth.drive_folder_meta(name)}


# ══════════════════════════════════════════════════════════════
#  RESEARCH LIBRARY SYNC (Google Drive)
# ══════════════════════════════════════════════════════════════
#  The app's research library keeps user-added reports locally; these endpoints
#  mirror them in the same Drive appDataFolder as the expense backups:
#    - research_library.json          {docs: [...], removed: [ids]}
#    - research_file_<id>.<ext>       one per report added from a file
#  The app does the merge (union of docs, union of removals); the backend only
#  moves bytes, so it never has to decide which device is right.

_RESEARCH_INDEX = "research_library.json"
_RESEARCH_FILE_RE = re.compile(r"^research_file_user-\d+\.(html|htm|pdf)$")


@app.get("/api/research/drive")
async def research_drive_pull():
    """The research index on Drive plus the report files already there."""
    if not google_auth.get_profile():
        return {"authenticated": False}
    raw = google_auth.drive_get_content(_RESEARCH_INDEX)
    library = {"docs": [], "removed": []}
    if raw:
        try:
            library = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise HTTPException(500, f"Drive research index is unreadable: {e}")
    files = [f.get("name") for f in google_auth.drive_list_files(prefix="research_file_")]
    return {"authenticated": True, "library": library, "files": sorted(set(files))}


@app.get("/api/research/drive/file")
async def research_drive_file(name: str = Query(...)):
    """One report file from Drive, base64-encoded."""
    if not _RESEARCH_FILE_RE.match(name):
        raise HTTPException(400, "Not a research file name")
    if not google_auth.get_profile():
        raise HTTPException(401, "Not logged in")
    content = google_auth.drive_get_content(name)
    if content is None:
        raise HTTPException(404, f"'{name}' is not on Drive")
    return {"name": name, "data": base64.b64encode(content).decode("ascii")}


@app.post("/api/research/drive")
async def research_drive_push(payload: dict = Body(...)):
    """Upload the merged index and any report files Drive is missing, and delete
    Drive copies of reports that were removed.

    Body: {library: {docs, removed}, files: {name: base64}}
    """
    if not google_auth.get_profile():
        raise HTTPException(401, "Not logged in")
    library = payload.get("library") or {}
    files = payload.get("files") or {}
    d = _expense_dir() / "research_sync"
    d.mkdir(parents=True, exist_ok=True)

    uploads = {}
    for name, b64 in files.items():
        if not _RESEARCH_FILE_RE.match(name):
            raise HTTPException(400, f"Not a research file name: {name}")
        try:
            (d / name).write_bytes(base64.b64decode(b64))
        except Exception as e:
            raise HTTPException(400, f"Could not decode {name}: {e}")
        uploads[name] = google_auth.drive_upload_file(name, data_dir=d)

    (d / _RESEARCH_INDEX).write_text(json.dumps(library, indent=2, ensure_ascii=False), encoding="utf-8")
    uploads[_RESEARCH_INDEX] = google_auth.drive_upload_file(_RESEARCH_INDEX, data_dir=d)

    # Drop Drive copies of removed reports so they stop costing space.
    removed = {str(i) for i in library.get("removed", [])}
    deleted = []
    if removed:
        for f in google_auth.drive_list_files(prefix="research_file_"):
            stem = f.get("name", "")[len("research_file_"):].rsplit(".", 1)[0]
            if stem in removed and google_auth.drive_delete_file(f.get("id")):
                deleted.append(f.get("name"))

    return {"ok": all(uploads.values()), "uploads": uploads, "deleted": deleted}


# ══════════════════════════════════════════════════════════════
#  SWING TRADING API
# ══════════════════════════════════════════════════════════════

_swing_scan_lock = threading.Lock()
_swing_scan_cache = {"date": None, "picks": [], "scanning": False, "progress": 0, "total": 0, "current_stock": ""}
_last_scan_time = 0  # epoch timestamp of last scan start

# Candidate (non-default) engines. Each gets its OWN in-flight cache and its own
# per-date storage variant, so a selectable engine can never touch the v4
# canonical list, the 14-day desk, or the paper flow. v4 stays the default.
_CANDIDATE_ENGINES = {
    "v5": {
        "note": ("v5 regime-adaptive ensemble — research/experimental; "
                 "v4 remains the default."),
        "scan": lambda on_progress: __import__("swing_v5").scan_v5_production(
            5, on_progress=on_progress),
    },
    "v4.1": {
        # Same scan and same quality gate as v4; only the ranking differs. See
        # swing_trading._apply_v41_ranking and research/FEATURE_IC_REPLICATION.md.
        #
        # MEASURED AND REFUTED 2026-07-30 (research/HARNESS.md). On the
        # survivorship-free panel against 20 random pickers, v4.1 ranks at
        # percentile 0 in BOTH train (2011-19) and val (2020-22) at every hold
        # tested (14/20/40) — worse than all 20 random pickers, with negative
        # expectancy and profit factor below 1. It is positive only in test
        # (2023-26). The feature-IC edge was real and replicated, but it did not
        # convert into a profitable selection rule. Kept selectable for
        # inspection only; do NOT promote on the strength of the IC study.
        "note": ("v4.1 — REFUTED. Re-ranks v4's scan on cross-sectional ATR% and "
                 "closeness to the 52-week high. Measured against a random-pick "
                 "benchmark on survivorship-free data it is worse than random in "
                 "2011-2019 and 2020-2022 at every hold tested. Retained for "
                 "inspection; v4 remains the default. See research/HARNESS.md."),
        "scan": lambda on_progress: swing_trading.scan_swing_picks(
            5, on_progress=on_progress, engine="v4.1"),
    },
}
_candidate_state = {
    e: {"date": None, "picks": [], "scanning": False, "progress": 0,
        "total": 0, "current_stock": "", "last_scan": 0.0}
    for e in _CANDIDATE_ENGINES
}

# Kept for back-compat with any caller that reached for these directly.
_swing_scan_cache_v5 = _candidate_state["v5"]


def _candidate_daily_picks(engine: str, force: bool, hard_reset: bool) -> dict:
    """Selectable candidate engine. Mirrors the v4 handler's
    scan/cooldown/canonical-save behavior but stores under the engine's own
    variant and does NOT auto-feed the 14-day desk or paper trading."""
    import datetime as dt
    import time as _time
    spec = _CANDIDATE_ENGINES[engine]
    st = _candidate_state[engine]
    today = dt.datetime.now().strftime("%Y-%m-%d")
    universe_size = swing_trading.get_universe_size()
    meta = {"universe_size": universe_size, "engine": engine,
            "disclaimer": swing_trading.PREDICTION_DISCLAIMER,
            "engine_note": spec["note"]}

    if st["scanning"]:
        return {"picks": st["picks"], "cached": True, "scanning": True,
                "progress": st["progress"], "total": st["total"],
                "current_stock": st["current_stock"], **meta}

    if not hard_reset:
        saved = swing_trading.load_saved_picks(today, variant=engine)
        if saved:
            st.update({"date": today, "picks": saved})
            return {"picks": swing_trading.with_live_price_overlay(saved),
                    "cached": True, "scanning": False, **meta}
        if st["date"] == today and not force:
            return {"picks": st["picks"], "cached": True, "scanning": False, **meta}

    elapsed = _time.time() - st["last_scan"]
    if elapsed < 60:
        return {"picks": st["picks"], "cached": True, "scanning": False,
                "cooldown": int(60 - elapsed), **meta}

    st.update({"last_scan": _time.time(), "scanning": True, "progress": 0,
               "total": universe_size, "current_stock": "", "picks": []})

    def _on_progress(cur, total, name):
        st.update({"progress": cur, "total": total, "current_stock": name})

    def _bg():
        try:
            picks = spec["scan"](_on_progress)
            picks = swing_trading.save_daily_picks(today, picks,
                                                   overwrite=hard_reset, variant=engine)
            st.update({"date": today, "picks": picks, "scanning": False,
                       "progress": st["total"], "current_stock": "Done"})
            print(f"[Swing:{engine}] SCAN COMPLETE -- {len(picks)} picks")
        except Exception as e:
            print(f"[Swing:{engine}] Scan error: {e}")
            st.update({"scanning": False, "date": today})
    threading.Thread(target=_bg, daemon=True).start()
    return {"picks": [], "cached": False, "scanning": True,
            "progress": 0, "total": st["total"], "current_stock": "", **meta}


@app.get("/api/swing/daily-picks")
async def swing_daily_picks(force: bool = False, hard_reset: bool = False, engine: str = "v4"):
    # Selectable engines (v5, v4.1) are handled by an isolated path — their own
    # cache and their own storage variant; everything below is the UNCHANGED v4
    # default.
    if engine in _CANDIDATE_ENGINES:
        return _candidate_daily_picks(engine, force, hard_reset)
    """Get Today's Focus List: the top 5 swing picks whose heuristic predicted
    gain clears 5% (see scan_swing_picks), ranked by confidence then expected
    gain. These same picks are what desk_auto_select tracks for 14 trading
    days on the Focus Dashboard.

    The first successful scan of a calendar date is saved as the canonical
    list for that date and returned on every later call. `force` only retries
    when today has no saved picks (e.g. an errored scan); `hard_reset` is the
    deliberate path that discards today's saved list and re-scans.
    """
    global _last_scan_time
    import datetime as dt
    today = dt.datetime.now().strftime("%Y-%m-%d")
    universe_size = swing_trading.get_universe_size()
    disclaimer = swing_trading.PREDICTION_DISCLAIMER

    # If scan is already running, ALWAYS return current progress (never restart)
    if _swing_scan_cache["scanning"]:
        return {"picks": _swing_scan_cache["picks"], "cached": True, "scanning": True,
                "progress": _swing_scan_cache["progress"], "total": _swing_scan_cache["total"],
                "current_stock": _swing_scan_cache["current_stock"], "universe_size": universe_size,
                "disclaimer": disclaimer}

    if not hard_reset:
        # Saved picks for today are canonical — refresh/research/restart all
        # land here and get the same list.
        saved = swing_trading.load_saved_picks(today)
        if saved:  # empty == the scan failed; fall through so `force` can retry
            _swing_scan_cache["date"] = today
            _swing_scan_cache["picks"] = saved
            # Live price overlay is display-only — it never rewrites the
            # canonical signal-time fields (current_price_at_signal,
            # actionable_status) saved at publish time.
            enriched = swing_trading.with_live_price_overlay(saved)
            return {"picks": enriched, "cached": True, "scanning": False,
                    "universe_size": universe_size, "disclaimer": disclaimer}

        # Nothing saved (scan errored or never ran): keep the old behavior of
        # not retrying on poll ticks until the user forces a scan.
        if _swing_scan_cache["date"] == today and not force:
            return {"picks": _swing_scan_cache["picks"], "cached": True, "scanning": False,
                    "universe_size": universe_size, "disclaimer": disclaimer}

    # Cooldown: don't allow re-scan within 60 seconds
    import time as _time
    elapsed = _time.time() - _last_scan_time
    if elapsed < 60:
        return {"picks": _swing_scan_cache["picks"], "cached": True, "scanning": False,
                "cooldown": int(60 - elapsed), "universe_size": universe_size,
                "disclaimer": disclaimer}

    # Start new scan in background
    _last_scan_time = _time.time()
    _swing_scan_cache["scanning"] = True
    _swing_scan_cache["progress"] = 0
    _swing_scan_cache["total"] = swing_trading.get_universe_size()
    _swing_scan_cache["current_stock"] = ""
    _swing_scan_cache["picks"] = []
    def _on_progress(current, total, stock_name):
        _swing_scan_cache["progress"] = current
        _swing_scan_cache["total"] = total
        _swing_scan_cache["current_stock"] = stock_name
    def _bg_scan():
        try:
            # Prefer Kite for real-time context, but scanning no longer requires
            # it — swing data falls back to Yahoo Finance when Kite (or its
            # historical-data API) is unavailable.
            if not kite_client.connected:
                print("[Swing] Kite not connected, attempting auth...")
                kite_client.check_connection()
            if not kite_client.connected:
                print("[Swing] Kite not connected -- scanning with Yahoo Finance data")

            picks = swing_trading.scan_swing_picks(5, on_progress=_on_progress)
            # Persist immediately — first save of the day is canonical; only a
            # deliberate hard reset overwrites it. Use whatever ends up saved.
            picks = swing_trading.save_daily_picks(today, picks, overwrite=hard_reset)
            # Auto-admit the best of today's picks into the 14-Day Desk
            # (keeps the max-5/day cap + score/R:R quality gate inside desk_auto_select).
            try:
                sel = swing_trading.desk_auto_select(picks)
                print(f"[Swing] Desk auto-select: {sel.get('selected_count', 0)} added {sel.get('selected', [])}")
            except Exception as e:
                print(f"[Swing] Desk auto-select failed: {e}")
            _swing_scan_cache["date"] = today
            _swing_scan_cache["picks"] = picks
            _swing_scan_cache["scanning"] = False
            _swing_scan_cache["progress"] = _swing_scan_cache["total"]
            _swing_scan_cache["current_stock"] = "Done"
            # Auto-buy in paper trading
            if picks:
                swing_trading.paper_auto_check()
                swing_trading.paper_auto_buy_picks(picks)
            print(f"[Swing] SCAN COMPLETE -- {swing_trading.get_universe_size()} stocks, {len(picks)} picks found")
        except Exception as e:
            print(f"[Swing] Scan error: {e}")
            _swing_scan_cache["scanning"] = False
            _swing_scan_cache["date"] = today  # Prevent immediate retry on error
    threading.Thread(target=_bg_scan, daemon=True).start()
    return {"picks": [], "cached": False, "scanning": True,
            "progress": 0, "total": _swing_scan_cache["total"], "current_stock": "",
            "universe_size": universe_size, "disclaimer": disclaimer}


class SwingUniverseRequest(BaseModel):
    universe: str


@app.get("/api/swing/universe")
async def swing_universe_options():
    """Selectable scan universes (Nifty 50 / 500 / Total Market) + the current one."""
    return swing_trading.list_scan_universes()


@app.put("/api/swing/universe")
async def swing_set_universe(req: SwingUniverseRequest):
    """Point the scanner at a different index. Persisted per user (settings.json,
    Drive-synced) and applied on the next scan — today's saved picks are frozen,
    so a hard refresh is what re-scans with the new universe."""
    global app_settings
    if req.universe not in swing_trading.PICKABLE_UNIVERSES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown universe {req.universe!r}. "
                   f"Expected one of {swing_trading.PICKABLE_UNIVERSES}.")
    selected = swing_trading.set_scan_universe(req.universe)
    app_settings["swing_universe"] = selected
    _save_settings(app_settings)
    return {"status": "saved", **swing_trading.list_scan_universes()}


@app.get("/api/swing/daily-pick-history")
async def swing_daily_pick_history():
    """Daily Pick History: every saved date's picks joined with what actually
    happened to each (still tracking / expired / never tracked)."""
    return {
        "dates": swing_trading.get_daily_pick_history(),
        "disclaimer": swing_trading.PREDICTION_DISCLAIMER,
    }


@app.get("/api/swing/test-stock")
async def swing_test_stock(symbol: str = "RELIANCE.NS"):
    """Fetch all indicators and raw details for a single stock for debugging."""
    try:
        # Ensure Kite is authenticated before scanning
        if not kite_client.connected:
            kite_client.check_connection()
        if not kite_client.connected:
            return {"error": "Kite MCP not authenticated"}

        token = swing_trading._resolve_instrument_token(symbol)
        if token is None:
            return {"error": f"Could not resolve instrument token for {symbol}"}

        import datetime as dt
        to_date = dt.datetime.now().strftime("%Y-%m-%d 23:59:59")
        from_date = (dt.datetime.now() - dt.timedelta(days=90)).strftime("%Y-%m-%d 00:00:00")

        # Call get_historical_data
        result = kite_client.get_historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval="day",
        )

        if result is None:
            return {"error": "get_historical_data returned None", "token": token}
        
        if isinstance(result, str):
            return {"error": f"get_historical_data returned string error: {result}", "token": token}

        candles = None
        if isinstance(result, dict):
            candles = result.get("candles", result.get("data", {}).get("candles"))
        elif isinstance(result, list):
            candles = result

        if not candles:
            return {"error": "No candles returned", "token": token, "raw_result": str(result)[:500]}

        # Perform calculations
        import numpy as np
        opens = np.array([c[1] for c in candles], dtype=float)
        highs = np.array([c[2] for c in candles], dtype=float)
        lows = np.array([c[3] for c in candles], dtype=float)
        closes = np.array([c[4] for c in candles], dtype=float)
        volumes = np.array([c[5] for c in candles], dtype=float)

        rsi = swing_trading._rsi(closes)
        macd_line, signal, hist = swing_trading._macd(closes)
        atr = swing_trading._atr(highs, lows, closes)
        bb_upper, bb_mid, bb_lower = swing_trading._bollinger(closes)
        vol_spike, vol_ratio = swing_trading._volume_spike(volumes)
        pattern = swing_trading._candlestick_pattern(opens, highs, lows, closes)
        supports, resistances = swing_trading._support_resistance(highs, lows, closes)
        ema20 = float(swing_trading._ema(closes, 20)[-1])
        ema50 = float(swing_trading._ema(closes, 50)[-1]) if len(closes) >= 50 else ema20
        adx = swing_trading._adx(highs, lows, closes)
        stoch_rsi = swing_trading._stochastic_rsi(closes)

        # Scan calculation details
        full_analysis = swing_trading._scan_stock(symbol)

        return {
            "symbol": symbol,
            "token": token,
            "candles_count": len(candles),
            "last_price": float(closes[-1]),
            "rsi": float(rsi),
            "macd": {"line": float(macd_line[-1]), "signal": float(signal[-1]), "hist": float(hist[-1])},
            "atr": float(atr),
            "bollinger": {"upper": float(bb_upper), "mid": float(bb_mid), "lower": float(bb_lower)},
            "volume": {"last": float(volumes[-1]), "ratio": float(vol_ratio), "spike": bool(vol_spike)},
            "pattern": pattern,
            "supports": [float(x) for x in supports],
            "resistances": [float(x) for x in resistances],
            "ema20": float(ema20),
            "ema50": float(ema50),
            "adx": float(adx),
            "stoch_rsi": float(stoch_rsi),
            "full_analysis": full_analysis
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()}




@app.get("/api/swing/analyze/{symbol}")
async def swing_analyze(symbol: str):
    """Deep swing analysis for a specific stock."""
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol += ".NS"
    result = await swing_trading.analyze_swing(symbol)
    return result

@app.get("/api/swing/paper/status")
async def swing_paper_status():
    """Get paper trading portfolio status."""
    return swing_trading.paper_status()

class SwingPaperTradeRequest(BaseModel):
    symbol: str
    action: str = "buy"  # buy or sell
    quantity: int = 0
    price: float = 0
    stop_loss: float = 0
    target: float = 0
    setup: str = ""

@app.post("/api/swing/paper/trade")
async def swing_paper_trade(req: SwingPaperTradeRequest):
    """Execute a paper trade.

    Buys never trust the client-submitted `price` as the fill — it may be
    stale by the time the request lands. A fresh price is fetched server-side
    and used as the actual fill; the submitted price (if any) is kept only as
    the "suggested" reference. Rejects when no fresh price is available.
    """
    symbol = req.symbol
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol += ".NS"
    if req.action == "buy":
        fresh = swing_trading._fetch_ltp(symbol)
        if fresh is None or fresh <= 0:
            return {"error": f"No fresh price available for {symbol} — try again.",
                    "status": "DATA_STALE"}
        return swing_trading.paper_buy(
            symbol, req.quantity, fresh, req.stop_loss, req.target, req.setup,
            suggested_entry=req.price if req.price > 0 else None,
            fill_source="manual", fill_reason="Manual paper buy at freshly fetched price.")
    else:
        return swing_trading.paper_sell(symbol, req.price if req.price > 0 else None, reason="manual")

class SwingPaperResetRequest(BaseModel):
    capital: float = 0

@app.post("/api/swing/paper/reset")
async def swing_paper_reset(req: SwingPaperResetRequest = SwingPaperResetRequest()):
    """Reset paper trading account, optionally at a user-supplied starting capital."""
    return swing_trading.paper_reset(capital=req.capital if req.capital > 0 else None)

@app.get("/api/swing/paper/auto-check")
async def swing_paper_auto_check():
    """Auto-check positions for SL/target hits."""
    actions = swing_trading.paper_auto_check()
    return {"actions": actions, "count": len(actions)}

@app.get("/api/swing/test-kite")
async def swing_test_kite():
    """Test if Kite MCP can provide data for swing trading."""
    results = {"kite_connected": False, "tests": {}}
    try:
        results["kite_connected"] = kite_client.connected and kite_client._mcp_available
    except Exception as e:
        results["connection_error"] = str(e)
    if not results["kite_connected"]:
        results["message"] = "Kite MCP not connected. Login to Zerodha first."
        return results
    # Test 1: Search instruments
    instruments = None
    try:
        instruments = kite_client.search_instruments("RELIANCE", "NSE")
        results["tests"]["search_instruments"] = {"status": "OK" if instruments else "FAIL", "result": instruments[:3] if isinstance(instruments, list) else str(instruments)[:500]}
    except Exception as e:
        results["tests"]["search_instruments"] = {"status": "ERROR", "error": str(e)}
    # Test 2: Get LTP
    try:
        ltp = kite_client.get_ltp(["NSE:RELIANCE"])
        results["tests"]["get_ltp"] = {"status": "OK" if ltp else "FAIL", "result": ltp if isinstance(ltp, dict) else str(ltp)[:500]}
    except Exception as e:
        results["tests"]["get_ltp"] = {"status": "ERROR", "error": str(e)}
    # Test 3: Historical Data
    try:
        token = None
        if isinstance(instruments, list):
            for item in instruments:
                if isinstance(item, dict) and item.get("instrument_token"):
                    token = item["instrument_token"]
                    break
        if token:
            from datetime import datetime as dt2, timedelta as td2
            to_d = dt2.now().strftime("%Y-%m-%d")
            from_d = (dt2.now() - td2(days=90)).strftime("%Y-%m-%d")
            hist = kite_client.get_historical_data(int(token), from_d, to_d, "day")
            results["tests"]["get_historical_data"] = {"status": "OK" if hist else "FAIL", "instrument_token": token, "candles_count": len(hist) if isinstance(hist, list) else "N/A", "sample": hist[:2] if isinstance(hist, list) and hist else str(hist)[:300]}
        else:
            results["tests"]["get_historical_data"] = {"status": "SKIP", "reason": "No token found"}
    except Exception as e:
        results["tests"]["get_historical_data"] = {"status": "ERROR", "error": str(e)}
    # Test 4: Get Quotes
    try:
        quotes = kite_client.get_quotes(["NSE:RELIANCE"])
        results["tests"]["get_quotes"] = {"status": "OK" if quotes else "FAIL", "has_data": bool(quotes)}
    except Exception as e:
        results["tests"]["get_quotes"] = {"status": "ERROR", "error": str(e)}
    ok_count = sum(1 for t in results["tests"].values() if t.get("status") == "OK")
    total = len(results["tests"])
    results["summary"] = f"{ok_count}/{total} tests passed"
    return results


# ──────────────────────────────────────
# 14-Day Swing Desk — AI-selected, user-executed watchlist
# ──────────────────────────────────────

class SwingDeskSymbolRequest(BaseModel):
    symbol: str

class SwingDeskPaperBuyRequest(BaseModel):
    symbol: str
    quantity: int = 0

def _desk_norm_symbol(symbol: str) -> str:
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol += ".NS"
    return symbol

@app.get("/api/swing/desk/list")
async def swing_desk_list(reanalyze: bool = False):
    """Return the 14-day desk (batches, history, summary)."""
    return swing_trading.desk_list(reanalyze=reanalyze)

@app.post("/api/swing/desk/auto-select-from-today")
async def swing_desk_auto_select():
    """Select the best of today's saved canonical picks into the desk (max 5/day)."""
    import datetime as dt
    today = dt.datetime.now().strftime("%Y-%m-%d")
    picks = swing_trading.load_saved_picks(today)
    if picks is None:
        picks = _swing_scan_cache.get("picks") or []
    return swing_trading.desk_auto_select(picks)

@app.post("/api/swing/desk/reanalyze")
async def swing_desk_reanalyze():
    """Re-scan tracked stocks and run the 14-day lifecycle."""
    swing_trading.desk_reanalyze()
    return swing_trading.desk_list(reanalyze=False)

@app.get("/api/swing/desk/focus")
def swing_desk_focus():
    """Priority view: the single #1 action + urgency buckets with live prices."""
    return swing_trading.desk_focus()

@app.post("/api/swing/desk/backfill")
async def swing_desk_backfill(force: bool = False):
    """Backfill the desk from prior days' saved picks (rolling 14-day window).

    Runs once by default; pass force=true to re-run (still dedups + respects removals).
    """
    result = swing_trading.desk_backfill_from_history(force=force)
    result["desk"] = swing_trading.desk_list(reanalyze=False)
    return result

@app.post("/api/swing/desk/remove")
async def swing_desk_remove(req: SwingDeskSymbolRequest):
    return swing_trading.desk_remove(_desk_norm_symbol(req.symbol))

@app.post("/api/swing/desk/archive")
async def swing_desk_archive(req: SwingDeskSymbolRequest):
    """User-chosen archive (e.g. after a paper trade closes)."""
    return swing_trading.desk_archive(_desk_norm_symbol(req.symbol))

@app.post("/api/swing/desk/paper-buy")
async def swing_desk_paper_buy(req: SwingDeskPaperBuyRequest):
    return swing_trading.desk_paper_buy(_desk_norm_symbol(req.symbol), req.quantity)

@app.post("/api/swing/desk/arm-auto-buy")
async def swing_desk_arm(req: SwingDeskSymbolRequest):
    return swing_trading.desk_arm(_desk_norm_symbol(req.symbol))

@app.post("/api/swing/desk/disarm-auto-buy")
async def swing_desk_disarm(req: SwingDeskSymbolRequest):
    return swing_trading.desk_disarm(_desk_norm_symbol(req.symbol))


class SwingResetAllRequest(BaseModel):
    capital: float = 0

@app.post("/api/swing/reset-all")
async def swing_reset_all(req: SwingResetAllRequest = SwingResetAllRequest()):
    """Reset ALL Swing Trading data for the current user: saved daily picks +
    history, the 14-Day Desk (active + history), pending paper entries, open
    paper positions, closed paper trades, paper equity history, and the
    in-memory scan cache — then initialize a clean paper account.

    Only touches the current user's swing_*.json files (never portfolio,
    mutual funds, watchlist, or login data, and never another user's files —
    see swing_trading.reset_all_swing_data). The confirmation dialog lives
    client-side; this endpoint executes unconditionally once called.
    """
    summary = swing_trading.reset_all_swing_data(
        capital=req.capital if req.capital > 0 else None)

    global _swing_scan_cache, _last_scan_time
    _swing_scan_cache = {"date": None, "picks": [], "scanning": False,
                          "progress": 0, "total": 0, "current_stock": ""}
    _last_scan_time = 0
    summary["scan_cache_cleared"] = True

    # Best-effort: push the freshly-reset swing files to Drive right away
    # (the existing per-user sync path — same files _save_paper/_save_desk
    # already upload individually, just forced immediately instead of async).
    try:
        if _current_user_email:
            user_dir = _user_data_dir(_current_user_email)
            swing_files = ["swing_daily_picks.json", "swing_desk.json", "swing_paper.json"]
            results = {f: google_auth.drive_upload_file(f, data_dir=user_dir) for f in swing_files}
            summary["drive_synced"] = any(results.values())
        else:
            summary["drive_synced"] = False
    except Exception as e:
        summary["drive_synced"] = False
        summary["drive_sync_error"] = str(e)
    return summary


if __name__ == "__main__":
    import uvicorn
    kite_status_msg = "CONNECTED" if _is_kite_connected() else "MCP Ready (login via dashboard)"
    print(f"[Kite MCP] Status: {kite_status_msg}")
    print(f"[Kite MCP] Server: {KITE_MCP_URL}")
    print(f"[AI] Ollama: {app_settings['ollama_url']} | Model: {app_settings['model_name']}")
    print(f"[Test] Swing Trading test page: http://localhost:8182/swing-test")
    uvicorn.run("main:app", host="0.0.0.0", port=8182, reload=False)


# ══════════════════════════════════════════════════════════════
#  SWING TRADING TEST PAGE
# ══════════════════════════════════════════════════════════════
@app.get("/swing-test", response_class=HTMLResponse)
async def swing_test_page():
    """Serve standalone swing trading test page."""
    html_path = Path(__file__).parent / "swing_test.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>swing_test.html not found</h1>", status_code=404)
