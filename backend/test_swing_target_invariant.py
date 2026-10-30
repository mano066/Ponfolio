"""G-HIGH — finite-target invariant for swing recommendations.

A recommendation must not become actionable (READY_TO_BUY / NEAR_BUY_ZONE, or
eligible for a paper order) unless it carries a finite, positive target from the
same completed-candle snapshot. These tests exercise validate_recommendation
with require_target=True (the production path) and the invalid-target cases the
audit called out.

Run: backend/.venv/Scripts/python.exe backend/test_swing_target_invariant.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swing_trading  # noqa: E402

_passed = 0
_failed = 0


def check(label, fn):
    global _passed, _failed
    try:
        fn()
        print(f"  PASS  {label}")
        _passed += 1
    except AssertionError as exc:
        print(f"  FAIL  {label}\n        {exc}")
        _failed += 1
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR {label}\n        {type(exc).__name__}: {exc}")
        _failed += 1


def V(**kw):
    """validate_recommendation with sensible in-zone defaults; override per test.
    require_target defaults to True (the production recommendation contract)."""
    params = dict(
        entry=100.0, buy_zone_low=98.0, buy_zone_high=102.0, stop_loss=95.0,
        target=130.0, current_price=100.0, max_entry_price=104.0,
        require_target=True,
    )
    params.update(kw)
    return swing_trading.validate_recommendation(**params)


def _assert(cond, ctx=None):
    assert cond, ctx


print("-- validate_recommendation finite-target invariant --")

# A valid, actionable baseline: in zone, finite target with room and R:R.
check("valid in-zone recommendation with a finite target -> READY_TO_BUY",
      lambda: _assert(V()[0] == "READY_TO_BUY", V()))

check("target=None with require_target -> TARGET_MISSING (not actionable)",
      lambda: _assert(V(target=None)[0] == "TARGET_MISSING", V(target=None)))

check("target=NaN -> TARGET_MISSING",
      lambda: _assert(V(target=float("nan"))[0] == "TARGET_MISSING", V(target=float("nan"))))

check("target=+inf -> TARGET_MISSING",
      lambda: _assert(V(target=float("inf"))[0] == "TARGET_MISSING", V(target=float("inf"))))

check("target=0 -> TARGET_MISSING",
      lambda: _assert(V(target=0)[0] == "TARGET_MISSING", V(target=0)))

check("target below entry -> INVALID",
      lambda: _assert(V(target=90)[0] == "INVALID", V(target=90)))

check("target at/below max fill price -> INVALID",
      lambda: _assert(V(target=103, max_entry_price=104)[0] == "INVALID",
                      V(target=103, max_entry_price=104)))

check("current price equal to target -> TARGET_ALREADY_REACHED",
      lambda: _assert(V(target=130, current_price=130)[0] == "TARGET_ALREADY_REACHED",
                      V(target=130, current_price=130)))

check("current price above target -> TARGET_ALREADY_REACHED",
      lambda: _assert(V(target=130, current_price=140)[0] == "TARGET_ALREADY_REACHED",
                      V(target=130, current_price=140)))

check("insufficient upside left (current just below target) -> TARGET_ALREADY_REACHED",
      lambda: _assert(V(target=130, current_price=129)[0] == "TARGET_ALREADY_REACHED",
                      V(target=130, current_price=129)))


def t_insufficient_reward_to_risk():
    # entry 100, stop 95 -> risk 5. target 104.2 -> reward 4.2 -> R:R 0.84 < 1.0.
    # (104.2 clears the 104 fill cap so this fails specifically on R:R.)
    status, reason = V(target=104.2, stop_loss=95.0, max_entry_price=104.0,
                       current_price=100.0)
    assert status == "INVALID", (status, reason)
    assert "reward-to-risk" in reason.lower(), reason


check("reward-to-risk below the minimum -> INVALID", t_insufficient_reward_to_risk)


def t_backward_compatible_without_require_target():
    # Legacy/direct callers (require_target=False) keep the old behavior:
    # a None target still validates on zone logic alone.
    status, _ = swing_trading.validate_recommendation(
        entry=100, buy_zone_low=98, buy_zone_high=102, stop_loss=95,
        target=None, current_price=100)
    assert status == "READY_TO_BUY", status


check("require_target=False stays backward compatible (None target -> zone logic)",
      t_backward_compatible_without_require_target)


print("\n-- paper eligibility gating --")


def t_target_missing_pick_never_creates_paper_order():
    with tempfile.TemporaryDirectory() as tmp:
        swing_trading.set_active_data_dir(Path(tmp))
        swing_trading.paper_reset(capital=1_000_000)
        pick = {
            "symbol": "NOTGT.NS", "name": "NOTGT", "price": 100.0,
            "entry": 100.0, "suggested_entry": 100.0,
            "buy_zone_low": 98.0, "buy_zone_high": 102.0,
            "entry_range_low": 98.0, "entry_range_high": 102.0,
            "stop_loss": 95.0, "target1": None, "max_entry_price": 104.0,
            "current_price_at_signal": 100.0,
            "actionable_status": "TARGET_MISSING",
            "status_reason": "No finite target.", "data_stale": False,
        }
        swing_trading.paper_auto_buy_picks([pick])
        data = swing_trading._load_paper()
        assert data["positions"] == [], "target-missing pick must not open a position"
        assert data["pending_entries"] == [], "target-missing pick must not be queued"


check("TARGET_MISSING pick creates no paper order/position",
      t_target_missing_pick_never_creates_paper_order)


print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
