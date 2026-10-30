"""Provider adapters for free/research-accessible NSE intraday sources."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import io
import json
import os

import pandas as pd
import requests

from .schema import normalize_candles


def fetch_yahoo(
    symbol: str,
    *,
    period: str = "7d",
    interval: str = "1m",
) -> pd.DataFrame:
    """Fetch Yahoo's recent window. This adapter never claims old coverage."""
    import yfinance as yf

    raw = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=False,
        prepost=False,
        progress=False,
        threads=False,
    )
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()
    timestamp = next(c for c in raw.columns if str(c).lower() in {"datetime", "date"})
    raw = raw.rename(columns={timestamp: "timestamp"})
    return normalize_candles(
        raw,
        symbol=symbol,
        source="yahoo_recent",
        timestamp_col="timestamp",
        interval=interval,
        adjusted=False,
    )


def fetch_upstox(
    instrument_key: str,
    symbol: str,
    start: date,
    end: date,
    *,
    interval_minutes: int = 1,
    access_token: str | None = None,
) -> pd.DataFrame:
    token = access_token or os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("UPSTOX_ACCESS_TOKEN is required")
    url = (
        "https://api.upstox.com/v3/historical-candle/"
        f"{instrument_key}/minutes/{interval_minutes}/{end.isoformat()}/{start.isoformat()}"
    )
    response = requests.get(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    candles = response.json().get("data", {}).get("candles", [])
    raw = pd.DataFrame(
        candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"]
    )
    return normalize_candles(
        raw,
        symbol=symbol,
        source="upstox_v3",
        instrument_id=instrument_key,
        interval=f"{interval_minutes}m",
    )


def fetch_dhan(
    security_id: str,
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    interval_minutes: int = 1,
    access_token: str | None = None,
) -> pd.DataFrame:
    token = access_token or os.getenv("DHAN_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("DHAN_ACCESS_TOKEN is required")
    payload = {
        "securityId": str(security_id),
        "exchangeSegment": "NSE_EQ",
        "instrument": "EQUITY",
        "interval": str(interval_minutes),
        "oi": False,
        "fromDate": start.strftime("%Y-%m-%d %H:%M:%S"),
        "toDate": end.strftime("%Y-%m-%d %H:%M:%S"),
    }
    response = requests.post(
        "https://api.dhan.co/v2/charts/intraday",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": token,
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    raw = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(body.get("timestamp", []), unit="s", utc=True),
            "open": body.get("open", []),
            "high": body.get("high", []),
            "low": body.get("low", []),
            "close": body.get("close", []),
            "volume": body.get("volume", []),
        }
    )
    return normalize_candles(
        raw,
        symbol=symbol,
        source="dhan_v2",
        instrument_id=str(security_id),
        interval=f"{interval_minutes}m",
    )


def fetch_alpha_vantage_month(
    symbol: str,
    month: str,
    *,
    interval: str = "1min",
    api_key: str | None = None,
) -> pd.DataFrame:
    key = api_key or os.getenv("ALPHAVANTAGE_API_KEY")
    if not key:
        raise RuntimeError("ALPHAVANTAGE_API_KEY is required")
    response = requests.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": interval,
            "month": month,
            "outputsize": "full",
            "datatype": "csv",
            "adjusted": "false",
            "apikey": key,
        },
        timeout=120,
    )
    response.raise_for_status()
    if response.text.lstrip().startswith("{"):
        raise RuntimeError(f"Alpha Vantage returned an API message: {response.text[:500]}")
    raw = pd.read_csv(io.StringIO(response.text))
    return normalize_candles(
        raw,
        symbol=symbol,
        source="alpha_vantage_intraday",
        interval=interval.replace("min", "m"),
        adjusted=False,
    )


def download_kaggle_dataset(dataset: str) -> Path:
    try:
        import kagglehub
    except ImportError as exc:
        raise RuntimeError(
            "Install kagglehub first: python -m pip install kagglehub"
        ) from exc
    return Path(kagglehub.dataset_download(dataset))


def import_kaggle_nifty_bank_file(
    path: Path,
    *,
    symbol: str,
    source: str = "kaggle_nifty_bank_2008_2020",
) -> pd.DataFrame:
    """Import the seven-column NIFTY/BANKNIFTY community CSV format."""
    raw = pd.read_csv(path)
    columns = {str(c).strip().lower(): c for c in raw.columns}
    required = {"date", "time", "open", "high", "low", "close"}
    missing = sorted(required - set(columns))
    if missing:
        raise ValueError(f"Unsupported Kaggle index schema; missing {missing}")
    raw["timestamp"] = pd.to_datetime(
        raw[columns["date"]].astype(str).str.replace(r"\.0$", "", regex=True)
        + " "
        + raw[columns["time"]].astype(str).str.strip(),
        format="%Y%m%d %H:%M",
        errors="coerce",
    )
    renamed = raw.rename(
        columns={
            columns["open"]: "open",
            columns["high"]: "high",
            columns["low"]: "low",
            columns["close"]: "close",
        }
    )
    return normalize_candles(
        renamed,
        symbol=symbol,
        source=source,
        timestamp_col="timestamp",
        interval="1m",
        source_file=str(path),
    )


def import_generic_csv(
    path: Path,
    *,
    symbol: str,
    source: str,
    timestamp_col: str = "timestamp",
    interval: str = "1m",
) -> pd.DataFrame:
    raw = pd.read_csv(path)
    return normalize_candles(
        raw,
        symbol=symbol,
        source=source,
        timestamp_col=timestamp_col,
        interval=interval,
        source_file=str(path),
    )
