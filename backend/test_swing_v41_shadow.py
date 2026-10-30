"""Tests for v4.1 forward-shadow logging (SWING_V41_SHADOW).

The one property that matters most: turning shadow logging ON must not change a
single byte of what v4 publishes. v4.1 re-ranks the SAME candidate dicts v4 is
about to return, so a missing copy would silently corrupt production picks.

Run: python test_swing_v41_shadow.py   (no network, no Drive uploads)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import swing_trading

swing_trading._drive_upload_async = lambda path: None

_p, _f = 0, 0


def check(name, fn):
    global _p, _f
    try:
        fn()
        _p += 1
        print(f"  PASS  {name}")
    except Exception as e:
        _f += 1
        print(f"  FAIL  {name}: {e!r}")


def candidate(symbol, score, price, atr_pct, dist_52w_pct):
    """A candidate shaped like one _scan_stock emits, past v4's score gate."""
    return {
        "symbol": symbol, "name": symbol.replace(".NS", ""),
        "score": score, "price": price, "entry": price,
        "atr_pct": atr_pct, "dist_52w_pct": dist_52w_pct,
        "high_52w": price / (dist_52w_pct / 100.0),
        "ret_63d_pct": 12.0, "adx": 30.0, "trend": "Up",
        "counter_trend": False, "setup": "Breakout",
        "risk_reward": "1:2.0", "stop_loss": price * 0.95,
        "predicted_target_price": price * 1.08,
        "predicted_gain_pct": max(5.5, 2.5 * atr_pct),
        # _select_validated_picks rejects a candidate outright without these
        # ("Buy zone bounds are missing or inverted") — real _scan_stock output
        # always carries them.
        "entry_range_low": price * 0.98,
        "entry_range_high": price * 1.02,
    }


# Two candidates that v4.1 must order OPPOSITE to raw score: the lower-scored
# name is calmer and nearer its 52-week high, which is what v4.1 rewards.
CANDIDATES = [
    candidate("HOTVOL.NS", 80, 100.0, atr_pct=6.0, dist_52w_pct=60.0),
    candidate("CALMHI.NS", 70, 200.0, atr_pct=1.5, dist_52w_pct=96.0),
]


def _stub_ltp(monkey_prices):
    orig = swing_trading._batch_ltp
    swing_trading._batch_ltp = lambda syms: {s: monkey_prices[s] for s in syms
                                             if s in monkey_prices}
    return orig


def _quality(r):
    return (not r.get("counter_trend") and r.get("trend") == "Up"
            and (r.get("adx") or 0) >= 25)


def _rs_only(r):
    r63 = r.get("ret_63d_pct")
    return r63 is not None and r63 > 0


print("\n-- flag gating --")


def t_flag_off_by_default():
    os.environ.pop("SWING_V41_SHADOW", None)
    assert swing_trading._v41_shadow_on() is False


def t_flag_reads_live_not_at_import():
    os.environ["SWING_V41_SHADOW"] = "1"
    try:
        assert swing_trading._v41_shadow_on() is True
    finally:
        os.environ.pop("SWING_V41_SHADOW", None)
    assert swing_trading._v41_shadow_on() is False, "flag must not stick"


check("shadow logging is OFF unless SWING_V41_SHADOW is set", t_flag_off_by_default)
check("the flag is read per scan, so it can be flipped without a restart",
      t_flag_reads_live_not_at_import)

print("\n-- v4's published picks are never touched --")


def t_shadow_does_not_mutate_v4_picks():
    """_apply_v41_ranking stamps engine/rank fields onto every dict it sees. If
    the scan handed it v4's own candidate objects, v4's published picks would
    come out labelled v4.1. The per-row copy in scan_swing_picks prevents that;
    this asserts the copy is what makes it safe."""
    v4_published = [candidate("HOTVOL.NS", 80, 100.0, 6.0, 60.0)]
    before = json.dumps(v4_published, sort_keys=True, default=str)

    # Exactly what the scan does: copy per row, then rank the copies.
    shadow_src = [dict(r) for r in v4_published]
    swing_trading._apply_v41_ranking(shadow_src, set(), _quality, _rs_only)

    after = json.dumps(v4_published, sort_keys=True, default=str)
    assert before == after, "v4's candidate dicts were mutated by the shadow rank"
    assert shadow_src[0]["engine"] == "v4.1", "the copy SHOULD be stamped"
    assert "engine" not in v4_published[0], "the original must stay unlabelled"


check("ranking the shadow copy leaves v4's own dicts byte-identical",
      t_shadow_does_not_mutate_v4_picks)


def t_shadow_writes_both_lists():
    with tempfile.TemporaryDirectory() as tmp:
        swing_trading.set_active_data_dir(Path(tmp))
        orig = _stub_ltp({"HOTVOL.NS": 100.0, "CALMHI.NS": 200.0})
        try:
            v4_picks = [dict(CANDIDATES[0])]     # v4 ranks by score -> HOTVOL
            rec = swing_trading._shadow_log_v41(
                v4_picks, [dict(c) for c in CANDIDATES], 5,
                _quality, _rs_only, set())
        finally:
            swing_trading._batch_ltp = orig

        assert rec is not None
        assert [p["symbol"] for p in rec["v4_picks"]] == ["HOTVOL.NS"], rec["v4_picks"]
        v41 = [p["symbol"] for p in rec["v41_picks"]]
        # v4.1 must prefer the calm, near-high name despite its LOWER score.
        assert v41[0] == "CALMHI.NS", f"v4.1 ranking not applied: {v41}"
        assert rec["candidates_scanned"] == 2, rec
        assert rec["overlap"] == ["HOTVOL.NS"], rec["overlap"]

        log = Path(tmp) / "v41_shadow_signals.json"
        assert log.exists(), "shadow log written"
        data = json.loads(log.read_text(encoding="utf-8"))
        assert isinstance(data, list) and len(data) == 1, data
        assert data[-1]["date"] == datetime.now().strftime("%Y-%m-%d")


def t_shadow_row_carries_evaluable_fields():
    """A row is worthless later unless realized return is recomputable from it."""
    with tempfile.TemporaryDirectory() as tmp:
        swing_trading.set_active_data_dir(Path(tmp))
        orig = _stub_ltp({"CALMHI.NS": 200.0})
        try:
            rec = swing_trading._shadow_log_v41(
                [], [dict(CANDIDATES[1])], 5, _quality, _rs_only, set())
        finally:
            swing_trading._batch_ltp = orig
    row = rec["v41_picks"][0]
    for field in ("symbol", "score", "price", "current_price_at_signal",
                  "signal_timestamp", "atr_pct", "dist_52w_pct",
                  "xr_atr_pct", "xr_near_high", "v41_rank_score"):
        assert field in row, f"{field} missing — row not evaluable: {sorted(row)}"


def t_same_day_rescan_replaces_the_row():
    """A hard refresh must not double-count a day in the forward sample."""
    with tempfile.TemporaryDirectory() as tmp:
        swing_trading.set_active_data_dir(Path(tmp))
        orig = _stub_ltp({"HOTVOL.NS": 100.0, "CALMHI.NS": 200.0})
        try:
            for _ in range(3):
                swing_trading._shadow_log_v41(
                    [dict(CANDIDATES[0])], [dict(c) for c in CANDIDATES], 5,
                    _quality, _rs_only, set())
        finally:
            swing_trading._batch_ltp = orig
        data = json.loads((Path(tmp) / "v41_shadow_signals.json")
                          .read_text(encoding="utf-8"))
        today = datetime.now().strftime("%Y-%m-%d")
        assert len(data) == 1, f"3 same-day scans produced {len(data)} rows"
        assert data[0]["date"] == today


def t_prior_days_are_kept():
    with tempfile.TemporaryDirectory() as tmp:
        swing_trading.set_active_data_dir(Path(tmp))
        path = Path(tmp) / "v41_shadow_signals.json"
        path.write_text(json.dumps([{"date": "2020-01-01", "v4_picks": [],
                                     "v41_picks": []}]), encoding="utf-8")
        orig = _stub_ltp({"CALMHI.NS": 200.0})
        try:
            swing_trading._shadow_log_v41([], [dict(CANDIDATES[1])], 5,
                                          _quality, _rs_only, set())
        finally:
            swing_trading._batch_ltp = orig
        data = json.loads(path.read_text(encoding="utf-8"))
        assert [r["date"] for r in data][0] == "2020-01-01", data
        assert len(data) == 2, data


print("\n-- scan_swing_picks integration --")


def _run_scan(flag_on: bool, tmp: str):
    """Drive the real scan_swing_picks over a stubbed 2-name universe."""
    swing_trading.set_active_data_dir(Path(tmp))
    orig_uni = swing_trading.get_swing_universe
    orig_scan = swing_trading._scan_stock
    orig_recent = swing_trading._recently_topped_symbols
    orig_auth = swing_trading._ensure_kite_auth
    orig_yf = swing_trading._fetch_ohlcv_yahoo
    orig_ltp = swing_trading._batch_ltp
    by_sym = {c["symbol"]: c for c in CANDIDATES}

    swing_trading.get_swing_universe = lambda key=None: list(by_sym)
    swing_trading._scan_stock = lambda sym, require_liquid=False: dict(by_sym[sym])
    swing_trading._recently_topped_symbols = lambda *a, **k: set()
    swing_trading._ensure_kite_auth = lambda: False
    # No Nifty benchmark -> the momentum tier degrades to absolute strength,
    # which both engines handle; keeps the test off the network.
    swing_trading._fetch_ohlcv_yahoo = lambda *a, **k: None
    swing_trading._batch_ltp = lambda syms: {s: by_sym[s]["price"] for s in syms
                                             if s in by_sym}
    if flag_on:
        os.environ["SWING_V41_SHADOW"] = "1"
    else:
        os.environ.pop("SWING_V41_SHADOW", None)
    try:
        return swing_trading.scan_swing_picks(top_n=5, engine="v4")
    finally:
        swing_trading.get_swing_universe = orig_uni
        swing_trading._scan_stock = orig_scan
        swing_trading._recently_topped_symbols = orig_recent
        swing_trading._ensure_kite_auth = orig_auth
        swing_trading._fetch_ohlcv_yahoo = orig_yf
        swing_trading._batch_ltp = orig_ltp
        os.environ.pop("SWING_V41_SHADOW", None)


_VOLATILE = ("engine", "signal_timestamp", "market_data_timestamp")


def _stable(picks):
    return [{k: v for k, v in p.items() if k not in _VOLATILE} for p in picks]


def t_flag_off_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        picks = _run_scan(False, tmp)
        assert len(picks) >= 1, "scan produced no picks — fixture broken"
        assert not (Path(tmp) / "v41_shadow_signals.json").exists(), \
            "shadow file written while the flag was OFF"


def t_flag_on_does_not_change_v4_output():
    """The guarantee that makes this safe to leave enabled in production."""
    with tempfile.TemporaryDirectory() as t_off:
        off = _run_scan(False, t_off)
    with tempfile.TemporaryDirectory() as t_on:
        on = _run_scan(True, t_on)
        shadow = Path(t_on) / "v41_shadow_signals.json"
        assert shadow.exists(), "shadow file missing while the flag was ON"
        rec = json.loads(shadow.read_text(encoding="utf-8"))[-1]

    assert [p["symbol"] for p in off] == [p["symbol"] for p in on], \
        "shadow logging changed which symbols v4 published"
    assert _stable(off) == _stable(on), \
        "shadow logging changed v4's pick payload"
    for p in on:
        assert p.get("engine") != "v4.1", \
            f"v4 published a pick labelled v4.1: {p['symbol']}"
    assert rec["v41_picks"], "shadow ran but recorded no v4.1 picks"


def t_shadow_sees_candidates_v4s_floor_would_drop():
    """The snapshot is taken BEFORE v4's expected-gain floor, so v4.1 can rank a
    calm name v4 structurally cannot pick."""
    low_gain = candidate("CALMLOW.NS", 72, 300.0, atr_pct=0.8, dist_52w_pct=98.0)
    low_gain["predicted_gain_pct"] = 2.0        # below v4's 5% floor
    with tempfile.TemporaryDirectory() as tmp:
        swing_trading.set_active_data_dir(Path(tmp))
        by_sym = {c["symbol"]: c for c in CANDIDATES + [low_gain]}
        orig = (swing_trading.get_swing_universe, swing_trading._scan_stock,
                swing_trading._recently_topped_symbols,
                swing_trading._ensure_kite_auth,
                swing_trading._fetch_ohlcv_yahoo, swing_trading._batch_ltp)
        swing_trading.get_swing_universe = lambda key=None: list(by_sym)
        swing_trading._scan_stock = lambda sym, require_liquid=False: dict(by_sym[sym])
        swing_trading._recently_topped_symbols = lambda *a, **k: set()
        swing_trading._ensure_kite_auth = lambda: False
        swing_trading._fetch_ohlcv_yahoo = lambda *a, **k: None
        swing_trading._batch_ltp = lambda syms: {s: by_sym[s]["price"] for s in syms
                                                 if s in by_sym}
        os.environ["SWING_V41_SHADOW"] = "1"
        try:
            picks = swing_trading.scan_swing_picks(top_n=5, engine="v4")
        finally:
            (swing_trading.get_swing_universe, swing_trading._scan_stock,
             swing_trading._recently_topped_symbols,
             swing_trading._ensure_kite_auth,
             swing_trading._fetch_ohlcv_yahoo, swing_trading._batch_ltp) = orig
            os.environ.pop("SWING_V41_SHADOW", None)

        assert "CALMLOW.NS" not in [p["symbol"] for p in picks], \
            "v4's 5% floor should have excluded it"
        rec = json.loads((Path(tmp) / "v41_shadow_signals.json")
                         .read_text(encoding="utf-8"))[-1]
        assert rec["candidates_scanned"] == 3, rec["candidates_scanned"]
        assert "CALMLOW.NS" in [p["symbol"] for p in rec["v41_picks"]], \
            "v4.1 shadow never saw the candidate v4's floor dropped"


check("flag OFF writes no shadow file", t_flag_off_writes_nothing)
check("flag ON leaves v4's published picks byte-identical",
      t_flag_on_does_not_change_v4_output)
check("the shadow snapshot precedes v4's expected-gain floor",
      t_shadow_sees_candidates_v4s_floor_would_drop)

print("\n-- the shadow record --")


check("record holds v4 + v4.1 lists, their overlap, and the candidate count",
      t_shadow_writes_both_lists)
check("each shadow row carries the fields a later study needs",
      t_shadow_row_carries_evaluable_fields)
check("a same-day re-scan replaces that day's row (no double-count)",
      t_same_day_rescan_replaces_the_row)
check("earlier days in the forward sample are preserved", t_prior_days_are_kept)

swing_trading.set_active_data_dir(None)
print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
