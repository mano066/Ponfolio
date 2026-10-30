"""Central configuration for the NSE dataset store.

Everything here was verified empirically against charting.nseindia.com on
2026-07-27; see README.md for the probe results that justify these values.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "store"

UNIVERSE_DIR = STORE / "universe"
DAILY_DIR = STORE / "daily"
INTRADAY_DIR = STORE / "intraday"
LOG_DIR = STORE / "logs"
STATE_DIR = STORE / "state"

for _d in (UNIVERSE_DIR, DAILY_DIR, INTRADAY_DIR, LOG_DIR, STATE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Universe -------------------------------------------------------------
# NSE publishes index constituents as plain CSV, no auth required.
UNIVERSE_CSV_URLS = [
    "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
    "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
]
UNIVERSE_NAME = "nifty_total_market"

# --- API behaviour --------------------------------------------------------
# The charting API is GET-with-query-params. (The `openchart` PyPI package
# POSTs JSON, which the server answers with a canned empty stub -- do not
# use it.)
CHARTING_BASE = "https://charting.nseindia.com/v1"
WARMUP_URL = "https://charting.nseindia.com/"

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

REQUEST_TIMEOUT = 45
MAX_RETRIES = 4
RETRY_BACKOFF = 2.0          # seconds, exponential
POLITE_DELAY = 0.30          # per-request sleep inside each worker
MAX_WORKERS = 3              # keep low; NSE throttles aggressively

# --- Intervals ------------------------------------------------------------
# chartType / timeInterval pairs the server accepts.
INTERVALS = {
    "1m":  ("I", 1),
    "5m":  ("I", 5),
    "10m": ("I", 10),
    "15m": ("I", 15),
    "30m": ("I", 30),
    "1h":  ("I", 60),
    "1d":  ("D", 1),
    "1w":  ("W", 1),
    "1M":  ("M", 1),
}
INTRADAY_INTERVALS = {"1m", "5m", "10m", "15m", "30m", "1h"}

# Verified server-side limits (RELIANCE, 2026-07-27):
#   intraday : rolling window only, ~7.5k most recent bars (~20 trading days).
#              Older explicit windows return []. Backward paging does not work.
#   1d / 1w  : full history from 1995-01-05 in a single request.
INTRADAY_WINDOW_DAYS = 28
EOD_HISTORY_START = "1995-01-01"

# --- Session envelope (IST) ----------------------------------------------
# A full session yields 377 one-minute bars: one pre-open block near 09:07
# plus 09:15..15:30 inclusive.
SESSION_OPEN = "09:15"
SESSION_CLOSE = "15:30"
PREOPEN_CUTOFF = "09:08"     # bars at/below this are the pre-open block
EXPECTED_1M_BARS_PER_DAY = 377
