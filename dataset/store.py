"""Parquet store with merge-append semantics.

Layout:
    store/daily/<SYMBOL>.parquet                     full EOD history per symbol
    store/intraday/<interval>/<SYMBOL>/<YYYY-MM>.parquet
    store/universe/nifty_total_market.csv            constituents as published
    store/universe/tokens.csv                        symbol -> scripcode map
    store/state/<job>.json                           resume state

Appending is idempotent: rows are merged on `ts` and the newest copy of a bar
wins, so re-running a harvest over an overlapping window is always safe and
self-healing (a missed day is recovered by the next run while it is still
inside the server's rolling window).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

import config

_SCHEMA = ["ts", "epoch_ms", "open", "high", "low", "close", "volume"]


# --- paths ----------------------------------------------------------------
def daily_path(symbol: str) -> Path:
    return config.DAILY_DIR / f"{symbol}.parquet"


def eod_path(symbol: str, interval: str) -> Path:
    d = config.STORE / ("daily" if interval == "1d" else f"eod_{interval}")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{symbol}.parquet"


def intraday_path(symbol: str, interval: str, period: str) -> Path:
    d = config.INTRADAY_DIR / interval / symbol
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{period}.parquet"


# --- io -------------------------------------------------------------------
def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp = Path(tmp)
    try:
        import os
        os.close(fd)
        df.to_parquet(tmp, index=False, compression="zstd")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=_SCHEMA)
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame(columns=_SCHEMA)


def merge_write(new: pd.DataFrame, path: Path) -> tuple[int, int]:
    """Merge `new` into the parquet at `path`. Returns (rows_added, total_rows)."""
    if new is None or new.empty:
        existing = read(path)
        return 0, len(existing)

    new = new[[c for c in _SCHEMA if c in new.columns]].copy()
    existing = read(path)
    before = len(existing)

    if existing.empty:
        merged = new
    else:
        merged = pd.concat([existing, new], ignore_index=True)

    merged = (merged.sort_values(["ts", "epoch_ms"])
                    .drop_duplicates(subset="ts", keep="last")
                    .sort_values("ts")
                    .reset_index(drop=True))
    _atomic_write(merged, path)
    return len(merged) - before, len(merged)


def write_intraday(symbol: str, interval: str, df: pd.DataFrame) -> dict:
    """Split an intraday frame by calendar month and merge each partition."""
    if df is None or df.empty:
        return {"added": 0, "months": 0}
    df = df.copy()
    periods = df["ts"].dt.strftime("%Y-%m")
    added = 0
    months = 0
    for period, chunk in df.groupby(periods, sort=True):
        a, _ = merge_write(chunk.drop(columns=[], errors="ignore"),
                           intraday_path(symbol, interval, str(period)))
        added += a
        months += 1
    return {"added": added, "months": months}


# --- state ----------------------------------------------------------------
def state_path(job: str) -> Path:
    return config.STATE_DIR / f"{job}.json"


def load_state(job: str) -> dict:
    p = state_path(job)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(job: str, state: dict) -> None:
    p = state_path(job)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    import os
    os.close(fd)
    Path(tmp).write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    Path(tmp).replace(p)
