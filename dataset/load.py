"""Read API for the store -- use this from research code and backtests.

    from load import daily, intraday, universe, panel

    df  = daily("RELIANCE", start="2010-01-01")
    m1  = intraday("RELIANCE", "1m")
    px  = panel(["RELIANCE", "TCS", "INFY"], field="close", start="2015-01-01")
    uni = universe()                      # symbol, series, token, industry...

All frames are indexed/ordered by `ts`, which is naive IST wall clock.
"""
from __future__ import annotations

import pandas as pd

import config
import store


def universe() -> pd.DataFrame:
    cons = pd.read_csv(config.UNIVERSE_DIR / f"{config.UNIVERSE_NAME}.csv")
    cons.columns = [c.strip() for c in cons.columns]
    tok_path = config.UNIVERSE_DIR / "tokens.csv"
    if not tok_path.exists():
        return cons
    tok = pd.read_csv(tok_path, dtype={"token": str})
    return tok.merge(cons.rename(columns={"Symbol": "symbol",
                                          "Company Name": "company",
                                          "Industry": "industry",
                                          "ISIN Code": "isin"}),
                     on="symbol", how="left")


def symbols(interval: str = "1d") -> list[str]:
    if interval in config.INTRADAY_INTERVALS:
        d = config.INTRADAY_DIR / interval
        return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []
    d = config.STORE / ("daily" if interval == "1d" else f"eod_{interval}")
    return sorted(p.stem for p in d.glob("*.parquet")) if d.exists() else []


def _slice(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if df.empty:
        return df
    if start is not None:
        df = df[df["ts"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["ts"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


def daily(symbol: str, start=None, end=None, interval: str = "1d") -> pd.DataFrame:
    """Full EOD history for one symbol."""
    return _slice(store.read(store.eod_path(symbol, interval)), start, end)


def intraday(symbol: str, interval: str = "1m", start=None, end=None,
             session_only: bool = False) -> pd.DataFrame:
    """Accumulated intraday bars for one symbol, all months concatenated."""
    d = config.INTRADAY_DIR / interval / symbol
    if not d.exists():
        return pd.DataFrame(columns=["ts", "epoch_ms", "open", "high", "low",
                                     "close", "volume"])
    parts = sorted(d.glob("*.parquet"))
    if start is not None:
        lo = pd.Timestamp(start).strftime("%Y-%m")
        parts = [p for p in parts if p.stem >= lo]
    if end is not None:
        hi = pd.Timestamp(end).strftime("%Y-%m")
        parts = [p for p in parts if p.stem <= hi]
    if not parts:
        return pd.DataFrame(columns=["ts", "epoch_ms", "open", "high", "low",
                                     "close", "volume"])
    df = pd.concat([store.read(p) for p in parts], ignore_index=True)
    df = df.sort_values("ts").reset_index(drop=True)
    if session_only:
        tod = df["ts"].dt.time
        lo_t = pd.to_datetime(config.SESSION_OPEN).time()
        hi_t = pd.to_datetime(config.SESSION_CLOSE).time()
        df = df[(tod >= lo_t) & (tod <= hi_t)].reset_index(drop=True)
    return _slice(df, start, end)


def panel(syms: list[str] | None = None, field: str = "close",
          start=None, end=None, interval: str = "1d") -> pd.DataFrame:
    """Wide frame: index=ts, one column per symbol. The backtest workhorse."""
    syms = syms or symbols(interval)
    series = {}
    for s in syms:
        df = (intraday(s, interval, start, end) if interval in config.INTRADAY_INTERVALS
              else daily(s, start, end, interval))
        if not df.empty:
            series[s] = df.set_index("ts")[field]
    if not series:
        return pd.DataFrame()
    return pd.DataFrame(series).sort_index()


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate 1m bars to any coarser bar ('5min', '15min', '1h', '1D')."""
    if df.empty:
        return df
    out = (df.set_index("ts")
             .resample(rule, label="left", closed="left")
             .agg(open=("open", "first"), high=("high", "max"),
                  low=("low", "min"), close=("close", "last"),
                  volume=("volume", "sum"))
             .dropna(subset=["open"]))
    return out.reset_index()
