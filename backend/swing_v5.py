"""v5 swing engine — SHADOW MODE (research/V5_ADVANCED_ENSEMBLE.md).

This module runs the researched v5 regime-adaptive ensemble ALONGSIDE the live
v4 engine, for forward paper-validation. It is OFF by default and never alters
v4's output: `scan_swing_picks` calls `run_shadow()` only when the feature flag
is set, wrapped so any failure is swallowed.

Enable for a validation run with the environment variable:
    SWING_V5_SHADOW=1            # turn shadow logging on
    SWING_V5_MAX_SYMBOLS=400     # optional cap to keep the extra scan cheap

What it logs (to <user_dir>/v5_shadow_signals.json): for each scan, the market
regime, the v4 picks, and the v5 ensemble picks (strategy tag, entry zone, stop,
target, volatility-target size hint) — so v4 vs v5 can be compared forward WITHOUT
touching production behavior or paper-trading history.

Promotion to a live default requires clearing the gates in
research/V5_V4_COMPARISON.md — this module does not do that; it only records.

Measured basis (daily, survivorship-biased) and all caveats: see
research/V5_ADVANCED_ENSEMBLE.md / research/V5_V4_COMPARISON.md.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import swing_trading  # reuse the live fetch layer, universe, and active user dir

logger = logging.getLogger("swing_v5")

# ── feature flag (OFF unless explicitly enabled) ────────────────────────────
def _flag_on() -> bool:
    return os.getenv("SWING_V5_SHADOW", "").strip().lower() in ("1", "true", "yes", "on")


V5_SHADOW_ENABLED = _flag_on()

# Researched config (frozen from V5_ADVANCED_ENSEMBLE.md / mtf_strategy_configs.json)
V5_CONFIG = {
    "risk_pct": 0.005,          # 0.5% equity risked per trade (volatility targeting)
    "max_pos_wt": 0.15,         # cap 15% equity per position
    "stop_atr": 2.5,            # v4 exit unit
    "target_atr": 3.0,          # research display/validation target
    "hold_sessions": 20,
    "min_turnover": 1e7,        # ₹1cr 20d avg traded value (liquidity)
    "min_price": 5.0,
    "s2_min_vol_ratio": 2.0,    # strong-volume breakout (volume study finding)
    "top_n_default": 5,
}


# ── indicators (daily, causal — computed on the fetched history) ────────────
def _indicators(d: dict) -> pd.DataFrame | None:
    try:
        c = pd.Series(d["closes"], dtype="float64")
        o = pd.Series(d["opens"], dtype="float64")
        h = pd.Series(d["highs"], dtype="float64")
        low = pd.Series(d["lows"], dtype="float64")
        v = pd.Series(d["volumes"], dtype="float64")
    except (KeyError, TypeError):
        return None
    if len(c) < 120:
        return None

    def ema(s, n):
        return s.ewm(span=n, adjust=False).mean()

    df = pd.DataFrame({"o": o, "h": h, "l": low, "c": c, "v": v})
    df["e20"], df["e50"], df["e200"] = ema(c, 20), ema(c, 50), ema(c, 200)
    diff = c.diff()
    g = diff.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    ll = (-diff.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + g / ll.replace(0, np.nan))
    pc = c.shift(1)
    tr = pd.concat([h - low, (h - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    df["e50rise"] = df["e50"] > df["e50"].shift(5)
    df["macdup"] = ema(c, 12) > ema(c, 26)
    df["hh20"] = h.rolling(20).max()
    ma20, sd20 = c.rolling(20).mean(), c.rolling(20).std()
    df["bbw"] = (4 * sd20) / ma20.replace(0, np.nan)
    df["bbwq"] = df["bbw"].rolling(100, min_periods=60).quantile(0.25)
    df["turn"] = (c * v).rolling(20).mean()
    df["vratio"] = v / v.rolling(20).mean().replace(0, np.nan)
    df["ret63"] = c / c.shift(63) - 1
    return df


def market_regime() -> tuple[str, float | None]:
    """(regime, nifty_63d_return) from ^NSEI daily. Regime = BULL / SIDEWAYS /
    BEAR / HIGHVOL / UNKNOWN, mirroring the research engine."""
    try:
        d = swing_trading._fetch_ohlcv_yahoo("^NSEI", period="2y")
    except Exception:
        d = None
    if not d or len(d.get("closes", [])) < 210:
        return "UNKNOWN", None
    c = pd.Series(d["closes"], dtype="float64")
    e50 = c.ewm(span=50, adjust=False).mean()
    e200 = c.ewm(span=200, adjust=False).mean()
    vol = c.pct_change().rolling(20).std() * np.sqrt(252)
    volhi = vol.rolling(252, min_periods=120).quantile(0.80)
    last = -1
    cc, a50, a200 = c.iloc[last], e50.iloc[last], e200.iloc[last]
    vv, vh = vol.iloc[last], volhi.iloc[last]
    r63 = float(c.iloc[-1] / c.iloc[-64] - 1) if len(c) >= 64 else None
    if pd.isna(a200):
        return "UNKNOWN", r63
    if pd.notna(vh) and vv > vh and cc < a50:
        return "HIGHVOL", r63
    if cc > a200 and a50 > a200:
        return "BULL", r63
    if cc < a200 and a50 < a200:
        return "BEAR", r63
    return "SIDEWAYS", r63


# ── ensemble signal (last completed bar) ────────────────────────────────────
def _eval_signal(df: pd.DataFrame, regime: str, nifty_r63: float | None):
    """Return (strategy_tag, features) if the regime-appropriate v5 signal fires
    on the latest bar, else None. Long-only, regime-gated."""
    j = len(df) - 1
    r = df.iloc[j]
    if not (r["turn"] >= V5_CONFIG["min_turnover"] and r["c"] >= V5_CONFIG["min_price"]):
        return None
    c, e20, e50, e200 = r["c"], r["e20"], r["e50"], r["e200"]
    if regime == "BULL":
        if (c > e50 > e200 and bool(r["e50rise"]) and (r["l"] <= e20 * 1.02 or abs(c / e20 - 1) <= 0.02)
                and c > e20 and 40 <= r["rsi"] <= 62 and c > r["o"]):
            return "S1_trend_pullback", r
        prev_hh = df["hh20"].iloc[j - 1] if j >= 1 else np.nan
        rs_ok = (nifty_r63 is None) or (pd.notna(r["ret63"]) and r["ret63"] > nifty_r63)
        if (c > e50 > e200 and rs_ok and pd.notna(prev_hh) and c >= prev_hh * 0.92
                and c > df["c"].iloc[j - 1] and c > e20):
            return "S3_rs_continuation", r
        if c > e50 > e200 and bool(r["macdup"]) and 45 <= r["rsi"] < 70:
            return "S6_momentum", r
    elif regime == "SIDEWAYS":
        prev_hh = df["hh20"].iloc[j - 1] if j >= 1 else np.nan
        if (c > e50 > e200 and pd.notna(r["bbwq"]) and r["bbw"] <= r["bbwq"]
                and pd.notna(prev_hh) and c > prev_hh and c <= e20 * 1.15
                and pd.notna(r["vratio"]) and r["vratio"] >= V5_CONFIG["s2_min_vol_ratio"]):
            return "S2_vol_breakout", r
    return None


def _build_pick(symbol: str, tag: str, r) -> dict | None:
    entry = float(r["c"])
    atr = float(r["atr"])
    if not (entry > 0 and atr > 0):
        return None
    stop = round(entry - V5_CONFIG["stop_atr"] * atr, 2)
    target = round(entry + V5_CONFIG["target_atr"] * atr, 2)
    risk_per_share = entry - stop
    size_hint = None
    if risk_per_share > 0:
        raw = V5_CONFIG["risk_pct"] / (risk_per_share / entry)   # fraction of equity
        size_hint = round(min(raw, V5_CONFIG["max_pos_wt"]) * 100, 2)
    return {
        "symbol": symbol,
        "strategy": tag,
        "ref_close": round(entry, 2),
        "buy_zone_low": round(entry * 0.99, 2),
        "buy_zone_high": round(entry * 1.01, 2),
        "max_entry_price": round(entry * 1.04, 2),
        "stop_loss": stop,
        "target": target,
        "atr": round(atr, 2),
        "ret63_pct": round(float(r["ret63"]) * 100, 2) if pd.notna(r["ret63"]) else None,
        "size_hint_pct_equity": size_hint,
        "rank": float(r["ret63"]) if pd.notna(r["ret63"]) else -9.0,
        "engine": "v5",
    }


# ── shadow scan + logging ───────────────────────────────────────────────────
def shadow_scan(top_n: int = 5, max_symbols: int | None = None) -> dict:
    """Run the v5 ensemble over the universe and return its top-N picks + regime.
    Independent of v4; long-only; no orders, no persistence side effects here."""
    regime, nifty_r63 = market_regime()
    picks: list[dict] = []
    if regime in ("BULL", "SIDEWAYS"):
        universe = swing_trading.get_swing_universe()
        if max_symbols:
            universe = universe[:max_symbols]
        for sym in universe:
            try:
                d = swing_trading._fetch_ohlcv(sym, days=365)
                if not d:
                    continue
                df = _indicators(d)
                if df is None:
                    continue
                sig = _eval_signal(df, regime, nifty_r63)
                if sig:
                    p = _build_pick(sym, sig[0], sig[1])
                    if p:
                        picks.append(p)
            except Exception as e:
                logger.debug("[SwingV5] scan error %s: %s", sym, e)
        picks.sort(key=lambda x: x["rank"], reverse=True)
        picks = picks[:top_n]
    return {"regime": regime, "nifty_r63_pct":
            round(nifty_r63 * 100, 2) if nifty_r63 is not None else None,
            "picks": picks}


def scan_v5_production(top_n: int = 5, on_progress=None) -> list[dict]:
    """Production v5 scan: regime-adaptive ensemble → candidates shaped like the
    v4 scanner's, then run through swing_trading._select_validated_picks so the
    SAME safety layer applies (fresh-price validation, finite-target invariant,
    no retrospective/gap fills). Returns production-shaped picks tagged engine=v5.

    Long-only and regime-gated: in BEAR/HIGH-VOL it returns an empty list (v5's
    defensive stance) rather than forcing longs.
    """
    regime, nifty_r63 = market_regime()
    candidates: list[dict] = []
    if regime in ("BULL", "SIDEWAYS"):
        universe = swing_trading.get_swing_universe()
        total = len(universe)
        for i, sym in enumerate(universe):
            if on_progress:
                on_progress(i, total, sym)
            try:
                d = swing_trading._fetch_ohlcv(sym, days=365)
                if not d:
                    continue
                df = _indicators(d)
                if df is None:
                    continue
                sig = _eval_signal(df, regime, nifty_r63)
                if not sig:
                    continue
                tag, r = sig
                entry = float(r["c"])
                atr = float(r["atr"])
                if not (entry > 0 and atr > 0):
                    continue
                target = round(entry + V5_CONFIG["target_atr"] * atr, 2)
                stop = round(entry - V5_CONFIG["stop_atr"] * atr, 2)
                rps = entry - stop
                size_hint = (round(min(V5_CONFIG["risk_pct"] / (rps / entry),
                                       V5_CONFIG["max_pos_wt"]) * 100, 2)
                             if rps > 0 else None)
                gain_pct = round((target / entry - 1) * 100, 1)
                name = sym.replace(".NS", "").replace(".BO", "")
                candidates.append({
                    "symbol": sym, "name": name, "price": round(entry, 2),
                    "entry": round(entry, 2),
                    "entry_range_low": round(entry * 0.99, 2),
                    "entry_range_high": round(entry * 1.01, 2),
                    "stop_loss": stop,
                    "target1": None,                       # no fixed TP exit (v4-style)
                    "predicted_target_price": target,      # → recommendation_target
                    "predicted_gain_pct": gain_pct,
                    "max_entry_price": round(entry * 1.04, 2),
                    "atr": round(atr, 2),
                    "rsi": round(float(r["rsi"]), 1) if pd.notna(r["rsi"]) else None,
                    "score": 75, "prediction_confidence": 75,
                    "setup": tag, "strategy": tag,
                    "trend": "Up",
                    "ret_63d_pct": round(float(r["ret63"]) * 100, 2) if pd.notna(r["ret63"]) else None,
                    "engine": "v5", "stop_check": "close", "time_exit_sessions": 20,
                    "size_hint_pct_equity": size_hint,
                    "regime": regime,
                    "data_source": "v5 ensemble (regime-adaptive)",
                    "_rank": float(r["ret63"]) if pd.notna(r["ret63"]) else -9.0,
                })
            except Exception as e:
                logger.debug("[SwingV5] prod scan error %s: %s", sym, e)
        candidates.sort(key=lambda x: x["_rank"], reverse=True)
    if on_progress:
        on_progress(len(candidates) or 1, len(candidates) or 1, "Done")
    # Same validation/fresh-price/finite-target path as v4.
    return swing_trading._select_validated_picks(candidates, top_n)


def _shadow_path() -> Path:
    base = getattr(swing_trading, "_active_user_dir", None)
    base = Path(base) if base else Path(__file__).resolve().parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base / "v5_shadow_signals.json"


def run_shadow(v4_picks: list[dict], top_n: int = 5) -> dict | None:
    """Called from scan_swing_picks ONLY when the flag is on. Logs the v4 vs v5
    side-by-side snapshot for forward comparison. Best-effort and side-effect
    free w.r.t. v4 — never raises into the caller."""
    if not _flag_on():
        return None
    cap = os.getenv("SWING_V5_MAX_SYMBOLS")
    max_symbols = int(cap) if cap and cap.isdigit() else None
    v5 = shadow_scan(top_n=top_n, max_symbols=max_symbols)
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "regime": v5["regime"],
        "nifty_r63_pct": v5["nifty_r63_pct"],
        "v4_symbols": [p.get("symbol") for p in (v4_picks or [])],
        "v5_picks": v5["picks"],
        "note": "SHADOW — not traded; forward comparison only (see V5_V4_COMPARISON.md)",
    }
    try:
        path = _shadow_path()
        log = []
        if path.exists():
            try:
                log = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                log = []
        log.append(record)
        tmp = path.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(log[-500:], indent=2), encoding="utf-8")
        tmp.replace(path)
        logger.info("[SwingV5] shadow logged: regime=%s v5_picks=%d",
                    v5["regime"], len(v5["picks"]))
    except Exception as e:
        logger.debug("[SwingV5] shadow write skipped: %s", e)
    return record
