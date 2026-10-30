"""Working client for NSE's technical-charting backend.

Why this exists instead of `pip install openchart`:

  openchart POSTs JSON to /v1/charts/symbolHistoricalData. The current server
  only honours GET with a query string (the charting SPA does
  `fetch('/v1' + path, {method:'GET'})`). The POST is answered with a canned
  `{"status":true,"data":[]}`, so openchart silently returns empty frames for
  every symbol. Verified 2026-07-27.

Timestamp handling -- the important part:

  The `time` field is epoch-milliseconds that already encodes IST wall clock.
  Decode it with `pd.to_datetime(ms, unit='ms')` and do NOT convert timezones.
  Proof: daily bars land on exact midnight (1784592000000 -> 2026-07-21
  00:00:00) and 1-minute sessions span 09:07..15:30, matching NSE's real
  trading day. Converting to IST would shift sessions to 14:37..21:00, which
  is not when NSE trades.

  Bar timestamps are bar-CLOSE times (the last trade in that minute), e.g.
  09:15:59 is the 09:15 bar. Use `.dt.floor("min")` to get the bar's minute.
"""
from __future__ import annotations

import random
import threading
import time as _time
from datetime import datetime

import pandas as pd
import requests

import config

_OHLC_COLS = ["open", "high", "low", "close", "volume"]


class NSEChartingError(RuntimeError):
    pass


class NSECharting:
    """Thread-safe-ish client. Each instance owns one requests.Session."""

    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or config.REQUEST_TIMEOUT
        self._lock = threading.Lock()
        self._session: requests.Session | None = None

    # -- plumbing ---------------------------------------------------------
    def _build_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": config.WARMUP_URL,
        })
        try:
            s.get(config.WARMUP_URL, timeout=self.timeout)
        except requests.RequestException:
            pass  # the cookie is a nicety, not a hard requirement
        return s

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            with self._lock:
                if self._session is None:
                    self._session = self._build_session()
        return self._session

    def reset_session(self) -> None:
        with self._lock:
            self._session = None

    def _get_json(self, path: str, params: dict) -> dict:
        url = f"{config.CHARTING_BASE}{path}"
        last_err = None
        for attempt in range(config.MAX_RETRIES):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code == 200:
                    return r.json()
                last_err = f"HTTP {r.status_code}"
                if r.status_code in (401, 403, 429) or r.status_code >= 500:
                    self.reset_session()
            except requests.RequestException as e:
                last_err = repr(e)
                self.reset_session()
            except ValueError as e:                      # bad JSON
                last_err = f"invalid JSON: {e}"
            if attempt < config.MAX_RETRIES - 1:
                _time.sleep(config.RETRY_BACKOFF ** attempt + random.uniform(0, 0.4))
        raise NSEChartingError(f"{path} failed after {config.MAX_RETRIES} tries: {last_err}")

    # -- symbol search ----------------------------------------------------
    def search(self, symbol: str, segment: str = "EQ") -> pd.DataFrame:
        """Resolve a symbol to its scripcode (token). segment: IDX | EQ | FO."""
        j = self._get_json("/exchanges/symbolsDynamic",
                           {"symbol": symbol, "segment": segment})
        rows = j.get("data") or []
        if not rows:
            return pd.DataFrame(columns=["symbol", "scripcode", "description",
                                         "type", "exchange"])
        df = pd.DataFrame(rows)
        keep = [c for c in ["symbol", "scripcode", "description", "type", "exchange"]
                if c in df.columns]
        return df[keep]

    def resolve(self, symbol: str, series: str = "EQ",
                segment: str = "EQ") -> dict | None:
        """Pick the right listing for a base symbol like 'RELIANCE'.

        The charting feed uses suffixed names ('RELIANCE-EQ', 'RCOM-BE'), and a
        search for 'RELIANCE' also returns RELCHEMQ, RELINFRA, RHFL etc. so we
        must match rather than take the first row.
        """
        df = self.search(symbol, segment)
        if df.empty:
            return None
        want = symbol.upper()
        names = df["symbol"].astype(str).str.upper()
        base = names.str.split("-").str[0]

        for candidate in (f"{want}-{series.upper()}", f"{want}-EQ", want):
            hit = df[names == candidate]
            if not hit.empty:
                return hit.iloc[0].to_dict()
        hit = df[base == want]                # any series for this exact base
        if not hit.empty:
            return hit.iloc[0].to_dict()
        return None

    # -- history ----------------------------------------------------------
    def history(self, token, symbol: str, symbol_type: str = "Equity",
                interval: str = "1d", start: datetime | None = None,
                end: datetime | None = None) -> pd.DataFrame:
        """Fetch OHLCV. Returns columns: ts, epoch_ms, open, high, low, close, volume.

        `start=None` sends fromDate=0, which is what the SPA does on first load
        and which yields the deepest history the server is willing to give.
        """
        if interval not in config.INTERVALS:
            raise ValueError(f"unsupported interval {interval!r}; "
                             f"expected one of {sorted(config.INTERVALS)}")
        chart_type, time_interval = config.INTERVALS[interval]

        params = {
            "token": str(token),
            "fromDate": int(start.timestamp()) if start else 0,
            "toDate": int(end.timestamp()) if end else int(_time.time()),
            "symbol": symbol,
            "symbolType": symbol_type,
            "chartType": chart_type,
            "timeInterval": time_interval,
        }
        j = self._get_json("/charts/symbolHistoricalData", params)
        return self._to_frame(j.get("data") or [], interval)

    @staticmethod
    def _to_frame(rows: list, interval: str) -> pd.DataFrame:
        cols = ["ts", "epoch_ms"] + _OHLC_COLS
        if not rows:
            return pd.DataFrame({c: pd.Series(dtype="float64") for c in cols}) \
                     .astype({"ts": "datetime64[ns]", "epoch_ms": "int64"})

        df = pd.DataFrame(rows)
        df = df.rename(columns={"time": "epoch_ms"})
        # Naive decode == IST wall clock. Do not tz_convert. See module docstring.
        df["ts"] = pd.to_datetime(df["epoch_ms"], unit="ms")
        if interval in config.INTRADAY_INTERVALS:
            # bar timestamps are close-of-bar; floor to the bar's own minute
            df["ts"] = df["ts"].dt.floor("min")
        else:
            df["ts"] = df["ts"].dt.normalize()

        for c in _OHLC_COLS:
            if c not in df.columns:
                df[c] = pd.NA
        df = df[cols]
        df = (df.sort_values(["ts", "epoch_ms"])
                .drop_duplicates(subset="ts", keep="last")
                .reset_index(drop=True))
        return df.astype({"epoch_ms": "int64", "open": "float64", "high": "float64",
                          "low": "float64", "close": "float64", "volume": "int64"})


def polite_sleep() -> None:
    _time.sleep(config.POLITE_DELAY + random.uniform(0, config.POLITE_DELAY))
