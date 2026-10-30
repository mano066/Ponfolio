"""V5 multi-timeframe swing analyzer (1m → 1d), leakage-safe.

Top-down role assignment (a swing trade is a DAILY thesis executed with an
intraday trigger). Each timeframe answers exactly one question:

  1d / weekly  -> WHAT to buy   : trend regime, relative strength, 52w context,
                                   volatility contraction. (backtestable on the
                                   2010 daily lake)
  2h / 60m     -> IS IT INTACT  : intermediate trend + higher-low structure,
                                   swing support/resistance zones.
  30m / 15m    -> WHEN today    : the actionable trigger — pullback-to-VWAP
                                   reclaim, opening-range breakout, breakout
                                   retest.
  5m / 1m      -> EXACT fill    : execution timing, VWAP side, momentum turn,
                                   spread/liquidity sanity, stop placement.

DATA HONESTY: intraday history is not available per-stock across 2010-present
or the 2023-2026 test window (see research/V5_DATA_FEASIBILITY.md and
research/intraday/VERIFIED_COVERAGE.md). This analyzer is therefore the LIVE /
forward-paper execution layer: the daily thesis is backtested elsewhere; the
1m-60m layers refine entry timing on live data going forward. It never claims a
historical intraday backtest.

LEAKAGE CONTROL: every read is as-of `as_of_ist`. For an intraday bar to be
visible its CLOSE time (bar_open + interval) must be <= as_of; a lower timeframe
can never see an unfinished higher-timeframe bar. Daily uses only completed
sessions (date strictly before as_of's session, or an earlier session).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

NSE_TZ = "Asia/Kolkata"
SESSION_OPEN = "09:15"

# interval label -> minutes (daily handled separately)
TF_MINUTES = {"1m": 1, "5m": 5, "10m": 10, "15m": 15, "30m": 30,
              "60m": 60, "2h": 120, "5h": 300}
OHLCV_AGG = {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}


# ───────────────────────── resampling (session-anchored) ─────────────────────
def resample_session_anchored(df1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample 1-minute IST bars to `rule` minutes, anchored to the 09:15 NSE
    open, never crossing a trading session. `df1m` must be tz-aware IST, indexed
    by bar-open time. The final bar of a session may be partial (fewer source
    minutes) — that is expected for 5h (a 6h15m session yields one 5h bar plus a
    1h15m remainder bar) and is flagged via `source_minutes`."""
    if df1m.empty:
        return df1m.copy()
    pieces = []
    for _, session in df1m.groupby(df1m.index.date):
        bars = session.resample(
            rule, origin="start_day", offset="9h15min",
            label="left", closed="left",
        ).agg(OHLCV_AGG)
        bars["source_minutes"] = session["close"].resample(
            rule, origin="start_day", offset="9h15min",
            label="left", closed="left",
        ).count()
        pieces.append(bars.dropna(subset=["open", "high", "low", "close"]))
    return pd.concat(pieces).sort_index() if pieces else df1m.iloc[0:0].copy()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """EMA/RSI/ATR + session-reset VWAP. All causal (no future data)."""
    out = df.copy()
    c = out["close"]
    out["ema20"] = c.ewm(span=20, adjust=False).mean()
    out["ema50"] = c.ewm(span=50, adjust=False).mean()
    out["ema200"] = c.ewm(span=200, adjust=False).mean()
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    out["rsi14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    pc = c.shift(1)
    tr = pd.concat([out["high"] - out["low"],
                    (out["high"] - pc).abs(), (out["low"] - pc).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    out["vol_ma20"] = out["volume"].rolling(20).mean()
    out["vol_ratio"] = out["volume"] / out["vol_ma20"].replace(0, np.nan)
    if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        typ = (out["high"] + out["low"] + out["close"]) / 3
        skey = pd.Series(out.index.date, index=out.index)
        out["vwap"] = ((typ * out["volume"]).groupby(skey).cumsum()
                       / out["volume"].groupby(skey).cumsum().replace(0, np.nan))
    return out


# ───────────────────────── as-of (leakage-safe) views ────────────────────────
def completed_intraday(frame: pd.DataFrame, interval: str,
                       as_of: pd.Timestamp) -> pd.DataFrame:
    """Bars whose CLOSE (open + interval) is at or before `as_of`."""
    if frame.empty:
        return frame
    mins = TF_MINUTES[interval]
    close_time = frame.index + pd.Timedelta(minutes=mins)
    return frame[close_time <= as_of]


def completed_daily(daily: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Only fully-completed sessions: date strictly before as_of's date, or the
    as_of date itself only if as_of is at/after the 15:30 close."""
    if daily.empty:
        return daily
    idx = pd.to_datetime(daily.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(NSE_TZ).tz_localize(None)
    # Compare naive-date to naive-date (daily bars are dateless of tz).
    as_of_naive = as_of.tz_localize(None) if as_of.tzinfo is not None else as_of
    cutoff = as_of_naive.normalize()
    after_close = as_of_naive.time() >= datetime.strptime("15:30", "%H:%M").time()
    mask = (idx <= cutoff) if after_close else (idx < cutoff)
    return daily[mask]


# ───────────────────────── per-timeframe state ───────────────────────────────
@dataclass
class TFState:
    interval: str
    ok: bool
    trend_up: bool = False
    above_vwap: bool | None = None
    rsi: float | None = None
    note: str = ""


def _tf_state(frame: pd.DataFrame, interval: str) -> TFState:
    if frame is None or frame.empty:
        return TFState(interval, ok=False, note="no data")
    last = frame.iloc[-1]
    trend_up = bool(last["close"] > last["ema20"] > last["ema50"])
    above_vwap = (bool(last["close"] >= last["vwap"])
                  if "vwap" in frame.columns and pd.notna(last.get("vwap")) else None)
    return TFState(interval, ok=True, trend_up=trend_up, above_vwap=above_vwap,
                   rsi=float(last["rsi14"]) if pd.notna(last.get("rsi14")) else None,
                   note="")


# ───────────────────────── setup categories ──────────────────────────────────
CATEGORIES = (
    "TREND_PULLBACK_CONTINUATION",
    "VOLATILITY_CONTRACTION_BREAKOUT",
    "RELATIVE_STRENGTH_MOMENTUM",
    "SUPPORT_RECLAIM_REVERSAL",
    "NO_SETUP",
)


@dataclass
class MTFResult:
    as_of_ist: str
    category: str
    alignment_score: int                 # 0..100
    actionable: bool
    daily: dict = field(default_factory=dict)
    timeframes: dict = field(default_factory=dict)
    entry_zone: tuple | None = None
    stop: float | None = None
    invalidation: str = ""
    reasons: list = field(default_factory=list)


def _daily_context(daily_c: pd.DataFrame) -> dict:
    """Backtestable daily thesis fields (WHAT to buy)."""
    last = daily_c.iloc[-1]
    c = daily_c["close"]
    hi_252 = c.rolling(252, min_periods=60).max().iloc[-1]
    ret_63 = float(c.iloc[-1] / c.iloc[-64] - 1) if len(c) >= 64 else np.nan
    vol20 = c.pct_change().rolling(20, min_periods=20).std()
    vol_pctl = (vol20.rolling(250, min_periods=120)
                .apply(lambda w: (w[-1] >= w).mean(), raw=True).iloc[-1])
    return {
        "trend_up": bool(last["close"] > last["ema20"] > last["ema50"]),
        "above_ema200": bool(last["close"] > last["ema200"]) if pd.notna(last["ema200"]) else False,
        "dist_52w_high_pct": round(float(last["close"] / hi_252 - 1) * 100, 2)
        if pd.notna(hi_252) else None,
        "ret_63d_pct": round(ret_63 * 100, 2) if pd.notna(ret_63) else None,
        "vol_contraction_pctl": round(float(vol_pctl), 2) if pd.notna(vol_pctl) else None,
        "atr14": round(float(last["atr14"]), 2) if pd.notna(last["atr14"]) else None,
        "close": round(float(last["close"]), 2),
    }


def analyze_multiframe(daily: pd.DataFrame, intraday: dict[str, pd.DataFrame],
                       as_of_ist, *, nifty_ret_63d: float | None = None) -> MTFResult:
    """Produce a leakage-safe multi-timeframe swing read as of `as_of_ist`.

    `daily`   : daily OHLCV+indicators, indexed by date.
    `intraday`: {interval: frame} with indicators, tz-aware IST, indexed by
                bar-open. Any subset of TF_MINUTES keys.
    Returns an MTFResult; `actionable` is True only when the daily thesis holds
    AND the higher-intraday structure confirms AND an entry trigger is present.
    """
    as_of = pd.Timestamp(as_of_ist)
    if as_of.tzinfo is None:
        as_of = as_of.tz_localize(NSE_TZ)

    daily_c = completed_daily(daily, as_of)
    if daily_c.empty or len(daily_c) < 60:
        return MTFResult(str(as_of), "NO_SETUP", 0, False,
                         reasons=["insufficient completed daily history"])

    dctx = _daily_context(daily_c)
    tf_states = {tf: _tf_state(completed_intraday(frame, tf, as_of), tf)
                 for tf, frame in intraday.items()}

    # Relative strength vs Nifty (if benchmark supplied).
    rs_ok = (nifty_ret_63d is None or
             (dctx["ret_63d_pct"] is not None and dctx["ret_63d_pct"] / 100 > nifty_ret_63d))

    # ── alignment scoring (each layer contributes; higher TF weighted more) ──
    score, reasons = 0, []
    if dctx["trend_up"]:
        score += 30; reasons.append("daily trend up (close>EMA20>EMA50)")
    if dctx["above_ema200"]:
        score += 10; reasons.append("above daily EMA200")
    h60 = tf_states.get("60m") or tf_states.get("2h")
    if h60 and h60.ok and h60.trend_up:
        score += 20; reasons.append("60m/2h trend intact")
    m15 = tf_states.get("15m") or tf_states.get("30m")
    if m15 and m15.ok and m15.above_vwap:
        score += 20; reasons.append("15m/30m holding above VWAP")
    m5 = tf_states.get("5m") or tf_states.get("1m")
    if m5 and m5.ok and m5.above_vwap:
        score += 20; reasons.append("5m/1m momentum above VWAP")
    score = min(score, 100)

    # ── category classification (top-down; first match wins) ──
    near_high = (dctx["dist_52w_high_pct"] is not None
                 and dctx["dist_52w_high_pct"] >= -15)
    coiled = (dctx["vol_contraction_pctl"] is not None
              and dctx["vol_contraction_pctl"] <= 0.35)
    daily_up = dctx["trend_up"]
    h60_up = bool(h60 and h60.ok and h60.trend_up)
    trigger = bool(m15 and m15.ok and m15.above_vwap)

    category = "NO_SETUP"
    if daily_up and near_high and rs_ok and h60_up and trigger:
        category = "RELATIVE_STRENGTH_MOMENTUM"
    elif daily_up and coiled and trigger:
        category = "VOLATILITY_CONTRACTION_BREAKOUT"
    elif daily_up and h60_up and trigger:
        category = "TREND_PULLBACK_CONTINUATION"
    elif (not daily_up) and dctx["above_ema200"] and trigger and h60_up:
        category = "SUPPORT_RECLAIM_REVERSAL"

    # Entry zone / stop from the daily thesis (the swing risk unit), refined by
    # the intraday trigger. Stop = 2.5xATR below entry (production v4 unit).
    entry = dctx["close"]
    atr = dctx["atr14"]
    entry_zone = (round(entry * 0.99, 2), round(entry * 1.01, 2)) if entry else None
    stop = round(entry - 2.5 * atr, 2) if (entry and atr) else None

    actionable = category != "NO_SETUP" and score >= 70
    if not actionable and category != "NO_SETUP":
        reasons.append(f"alignment {score} < 70 — wait for intraday confirmation")

    return MTFResult(
        as_of_ist=str(as_of), category=category, alignment_score=score,
        actionable=actionable, daily=dctx,
        timeframes={tf: asdict(s) for tf, s in tf_states.items()},
        entry_zone=entry_zone, stop=stop,
        invalidation=(f"daily close below {stop}" if stop else "daily trend loss"),
        reasons=reasons,
    )
