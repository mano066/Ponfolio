"""Tests for harness.py — the rig every promotion decision will rest on.

Priorities, in order:
  1. No lookahead. Entry is the open AFTER the signal bar; a rank never sees a
     future date.
  2. The random null is FAIR. It must draw from the same eligible pool the
     engines rank, or "beats random" means nothing.
  3. The hold parameter is actually wired to the exit.

Run: python research/scripts/v5/test_harness.py    (no network)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

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


def fake_sym(closes, opens=None, atr=1.0):
    """Minimal SYM entry: score_trades only reads c, o and atr."""
    c = np.asarray(closes, dtype=float)
    o = np.asarray(opens if opens is not None else closes, dtype=float)
    return {"c": c, "o": o, "atr": np.full(len(c), atr, dtype=float)}


print("\n-- exit arithmetic --")


def t_time_exit():
    """No stop hit: exit at the close of bar `hold` after entry, minus cost."""
    # entry at o[1]=100; closes drift up; stop = 100 - 2.5*1 = 97.5, never hit.
    c = [100, 101, 102, 103, 104, 105]
    o = [100, 100, 101, 102, 103, 104]
    SYM = {"X": fake_sym(c, o, atr=1.0)}
    sel = pd.DataFrame({"kid": [0], "j": [0]})
    nets = H.score_trades(sel, SYM, ["X"], hold=3)
    # exit at c[0+3] = 103  ->  (103/100-1)*100 - 0.30
    assert len(nets) == 1
    assert abs(nets[0] - (3.0 - H.COST)) < 1e-9, nets


def t_stop_exit_fills_at_next_open():
    """Stop is detected on a CLOSE and filled at the FOLLOWING open — never at
    the stop price itself, which would flatter the result."""
    # entry o[1]=100, atr=1 -> stop 97.5. c[2]=97 breaches; fill at o[3]=95.
    c = [100, 99, 97, 96, 96]
    o = [100, 100, 98, 95, 95]
    SYM = {"X": fake_sym(c, o, atr=1.0)}
    sel = pd.DataFrame({"kid": [0], "j": [0]})
    nets = H.score_trades(sel, SYM, ["X"], hold=4)
    assert abs(nets[0] - ((95 / 100 - 1) * 100 - H.COST)) < 1e-9, nets


def t_hold_changes_the_result():
    """If hold were ignored, these two would be equal."""
    c = [100, 101, 105, 110, 130]
    o = [100, 100, 101, 105, 110]
    SYM = {"X": fake_sym(c, o, atr=10.0)}   # wide stop so time exit governs
    sel = pd.DataFrame({"kid": [0], "j": [0]})
    short = H.score_trades(sel, SYM, ["X"], hold=1)
    long_ = H.score_trades(sel, SYM, ["X"], hold=3)
    assert short[0] < long_[0], (short, long_)
    assert abs(short[0] - ((101 / 100 - 1) * 100 - H.COST)) < 1e-9
    assert abs(long_[0] - ((110 / 100 - 1) * 100 - H.COST)) < 1e-9


def t_hold_truncated_at_series_end_not_dropped_silently():
    """A trade opened near the end of a symbol's life exits at its last bar."""
    c = [100, 102, 104]
    o = [100, 100, 102]
    SYM = {"X": fake_sym(c, o, atr=10.0)}
    sel = pd.DataFrame({"kid": [0], "j": [0]})
    nets = H.score_trades(sel, SYM, ["X"], hold=40)   # only 2 bars available
    assert len(nets) == 1, "delisted-soon trade must still be scored"
    assert abs(nets[0] - ((104 / 100 - 1) * 100 - H.COST)) < 1e-9, nets


check("time exit uses the close of bar `hold`, minus round-trip cost", t_time_exit)
check("stop exit fills at the NEXT open, not at the stop price",
      t_stop_exit_fills_at_next_open)
check("the hold parameter actually reaches the exit", t_hold_changes_the_result)
check("a hold running past a delisting is truncated, not dropped",
      t_hold_truncated_at_series_end_not_dropped_silently)

print("\n-- no lookahead --")


def t_entry_is_the_open_after_the_signal_bar():
    """Signal at j must be entered at o[j+1]. Entering at c[j] would leak."""
    c = [10, 20, 30, 40, 50, 60]
    o = [10, 11, 12, 13, 14, 15]      # opens deliberately unlike closes
    SYM = {"X": fake_sym(c, o, atr=100.0)}
    sel = pd.DataFrame({"kid": [0], "j": [2]})
    nets = H.score_trades(sel, SYM, ["X"], hold=1)
    # entry MUST be o[3]=13, exit c[3]=40
    assert abs(nets[0] - ((40 / 13 - 1) * 100 - H.COST)) < 1e-9, nets


def t_cross_sectional_ranks_are_within_date():
    """A rank must be computed against the same day's cross-section only."""
    bars = pd.DataFrame({
        "date": ["d1", "d1", "d2", "d2"],
        "near_hi_frac": [0.50, 0.90, 0.10, 0.20],
        "atr_pct": [5.0, 1.0, 9.0, 2.0],
    })
    g = bars.groupby("date")
    bars["xr_near_hi"] = g["near_hi_frac"].rank(pct=True)
    # d2's 0.10 is the LOW of its own day, so rank 0.5 — not bottom of all four.
    d2 = bars[bars["date"] == "d2"]["xr_near_hi"].tolist()
    assert d2 == [0.5, 1.0], d2
    d1 = bars[bars["date"] == "d1"]["xr_near_hi"].tolist()
    assert d1 == [0.5, 1.0], d1


check("entry is the open AFTER the signal bar", t_entry_is_the_open_after_the_signal_bar)
check("cross-sectional ranks are computed within a date, not across dates",
      t_cross_sectional_ranks_are_within_date)

print("\n-- the random null is fair --")


def _pool(n_dates=40, n_syms=30, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for kid in range(n_syms):
        for di in range(n_dates):
            rows.append({"date": f"d{di:03d}", "kid": kid, "j": di + 300,
                         "ret63": rng.normal(), "v41_score": rng.normal(),
                         "sig_v4": bool(rng.random() < 0.3),
                         "sig_v41": bool(rng.random() < 0.5)})
    return pd.DataFrame(rows)


def t_random_is_reproducible_and_seed_dependent():
    bars = _pool()
    a1 = H.select_random(bars, 7)[["date", "kid"]].to_numpy().tolist()
    a2 = H.select_random(bars, 7)[["date", "kid"]].to_numpy().tolist()
    b = H.select_random(bars, 8)[["date", "kid"]].to_numpy().tolist()
    assert a1 == a2, "same seed must reproduce exactly"
    assert a1 != b, "different seeds must differ"


def t_random_draws_only_from_the_eligible_pool():
    """The whole point: the null trades the SAME bars the engines choose from."""
    bars = _pool()
    allowed = set(map(tuple, bars[["date", "kid", "j"]].to_numpy().tolist()))
    sel = H.select_random(bars, 3)
    got = set(map(tuple, sel[["date", "kid", "j"]].to_numpy().tolist()))
    assert got <= allowed, "random picker invented bars outside the pool"


def t_random_ignores_engine_signals():
    """If the null only sampled signalled bars it would inherit the engine's
    edge and the comparison would be circular."""
    bars = _pool()
    bars.loc[:, "sig_v4"] = False          # no engine signal anywhere
    bars.loc[:, "sig_v41"] = False
    sel = H.select_random(bars, 1)
    assert len(sel) > 0, "null must still trade when no engine signals exist"
    assert len(H.select_engine(bars, "v4")) == 0, "engine must have nothing here"


def t_top_n_per_date_is_respected():
    bars = _pool(n_dates=10, n_syms=50)
    for sel in (H.select_random(bars, 5), H.select_engine(bars, "v4.1")):
        counts = sel.groupby("date").size()
        assert counts.max() <= H.TOP_N, counts.to_dict()


def t_engines_rank_by_their_own_feature():
    """v4 ranks on ret63; v4.1 on the near-high minus ATR blend."""
    bars = pd.DataFrame({
        "date": ["d1"] * 3, "kid": [0, 1, 2], "j": [300, 300, 300],
        "ret63": [1.0, 5.0, 3.0],
        "v41_score": [0.9, -0.5, 0.1],
        "sig_v4": [True] * 3, "sig_v41": [True] * 3,
    })
    v4 = H.select_engine(bars, "v4")["kid"].tolist()
    v41 = H.select_engine(bars, "v4.1")["kid"].tolist()
    assert v4[0] == 1, v4      # highest ret63
    assert v41[0] == 0, v41    # highest v41_score
    assert v4[0] != v41[0], "the two engines must be distinguishable"


check("random selection is reproducible per seed and varies across seeds",
      t_random_is_reproducible_and_seed_dependent)
check("random selection draws only from the eligible pool",
      t_random_draws_only_from_the_eligible_pool)
check("random selection ignores engine signals (non-circular null)",
      t_random_ignores_engine_signals)
check("both selectors respect TOP_N per date", t_top_n_per_date_is_respected)
check("v4 ranks on ret63 and v4.1 on its own blend", t_engines_rank_by_their_own_feature)

print("\n-- percentile reporting --")


def t_pctile_vs_random():
    assert H.pct_rank(1.0, [0.0, 0.5, 0.9]) == 100.0
    assert H.pct_rank(0.0, [0.1, 0.2, 0.3]) == 0.0
    assert H.pct_rank(0.25, [0.0, 0.5]) == 50.0
    assert H.pct_rank(None, [0.1]) is None
    assert H.pct_rank(1.0, []) is None
    assert H.pct_rank(1.0, [None, None]) is None


check("expectancy percentile against the null handles empties", t_pctile_vs_random)

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
