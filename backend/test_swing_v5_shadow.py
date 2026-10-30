"""Tests for the v5 shadow module — proves it is INERT by default and only
logs (never trades / never alters v4) when explicitly enabled.

Run: backend/.venv/Scripts/python.exe backend/test_swing_v5_shadow.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import swing_trading  # noqa: E402
import swing_v5  # noqa: E402

_p = _f = 0


def check(label, fn):
    global _p, _f
    try:
        fn(); print(f"  PASS  {label}"); _p += 1
    except AssertionError as e:
        print(f"  FAIL  {label}\n        {e}"); _f += 1
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR {label}\n        {type(e).__name__}: {e}"); _f += 1


def _uptrend(n=260):
    """Synthetic bullish OHLCV with a final pullback+reclaim (fires S1)."""
    base = np.linspace(100, 200, n)
    noise = np.sin(np.arange(n) / 7) * 2
    c = base + noise
    c[-2] = c[-3] * 0.985          # pullback toward EMA20
    c[-1] = c[-2] * 1.012          # up-close reclaim
    o = c * 0.998
    h = np.maximum(o, c) * 1.004
    low = np.minimum(o, c) * 0.994
    v = np.full(n, 1_000_000.0)
    return {"opens": o, "highs": h, "lows": low, "closes": c, "volumes": v}


def _assert(c, m="assertion failed"):
    assert c, m


print("-- flag is OFF by default --")
check("_flag_on() is False when SWING_V5_SHADOW is unset",
      lambda: _assert(not os.getenv("SWING_V5_SHADOW") and not swing_v5._flag_on()))

check("run_shadow is a no-op (returns None) while flag is off",
      lambda: _assert(swing_v5.run_shadow([{"symbol": "X.NS"}]) is None))


print("\n-- indicators + signal logic --")


def t_indicators_smoke():
    df = swing_v5._indicators(_uptrend())
    assert df is not None
    for col in ("e20", "e50", "e200", "rsi", "atr", "hh20", "vratio", "ret63"):
        assert col in df.columns, col


check("_indicators returns a full frame on synthetic data", t_indicators_smoke)


def t_signal_fires_in_bull():
    df = swing_v5._indicators(_uptrend())
    sig = swing_v5._eval_signal(df, "BULL", nifty_r63=0.0)
    assert sig is not None, "a bullish pullback/momentum setup should fire in BULL"
    assert sig[0] in ("S1_trend_pullback", "S3_rs_continuation", "S6_momentum"), sig[0]


check("a bullish synthetic stock fires an ensemble signal in BULL regime", t_signal_fires_in_bull)


def t_regime_gate_blocks_bear():
    df = swing_v5._indicators(_uptrend())
    assert swing_v5._eval_signal(df, "BEAR", nifty_r63=0.0) is None, "no longs in BEAR"
    assert swing_v5._eval_signal(df, "HIGHVOL", nifty_r63=0.0) is None, "no longs in HIGHVOL"


check("regime gate blocks all longs in BEAR / HIGHVOL", t_regime_gate_blocks_bear)


def t_build_pick_safety():
    df = swing_v5._indicators(_uptrend())
    p = swing_v5._build_pick("AAA.NS", "S1_trend_pullback", df.iloc[-1])
    assert p is not None
    assert p["target"] > p["ref_close"] > p["stop_loss"], p
    assert 0 < p["size_hint_pct_equity"] <= swing_v5.V5_CONFIG["max_pos_wt"] * 100, p
    assert p["engine"] == "v5"


check("built pick has finite target>entry>stop and a capped size hint", t_build_pick_safety)


print("\n-- shadow logging writes only when enabled (still no v4 impact) --")


def t_shadow_writes_when_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        swing_trading.set_active_data_dir(Path(tmp))
        os.environ["SWING_V5_SHADOW"] = "1"
        orig_regime = swing_v5.market_regime
        orig_uni = swing_trading.get_swing_universe
        orig_fetch = swing_trading._fetch_ohlcv
        swing_v5.market_regime = lambda: ("BULL", 0.0)
        swing_trading.get_swing_universe = lambda: ["AAA.NS", "BBB.NS"]
        swing_trading._fetch_ohlcv = lambda sym, days=365: _uptrend()
        try:
            rec = swing_v5.run_shadow([{"symbol": "V4STOCK.NS"}], top_n=5)
        finally:
            swing_v5.market_regime = orig_regime
            swing_trading.get_swing_universe = orig_uni
            swing_trading._fetch_ohlcv = orig_fetch
            os.environ.pop("SWING_V5_SHADOW", None)
        assert rec is not None and rec["regime"] == "BULL", rec
        assert rec["v4_symbols"] == ["V4STOCK.NS"], "v4 picks logged verbatim, not modified"
        assert len(rec["v5_picks"]) >= 1, "v5 ensemble produced picks"
        log = Path(tmp) / "v5_shadow_signals.json"
        assert log.exists(), "shadow log file written"
        import json
        data = json.loads(log.read_text())
        assert isinstance(data, list) and data[-1]["regime"] == "BULL"


check("run_shadow logs v4+v5 side-by-side to v5_shadow_signals.json when enabled",
      t_shadow_writes_when_enabled)


def t_flag_off_again_after_test():
    # env popped -> flag must read off again (no leakage across runs)
    assert swing_v5.run_shadow([{"symbol": "X.NS"}]) is None


check("flag reads OFF again after the enabled test (no leakage)", t_flag_off_again_after_test)

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
