"""Tests for swing persistence: canonical daily picks, desk idempotency,
14-day lifecycle, per-user storage migration, and Drive sync wiring.

Run: python test_swing_persistence.py  (no network, no Drive uploads)
"""
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

# Windows consoles default to cp1252, which can't encode ₹/→ etc. that show up
# in error messages/assertion reprs — reconfigure so a real failure's message
# always prints instead of masking itself with a UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import swing_trading
import google_auth

# Never touch the real Drive from tests
swing_trading._drive_upload_async = lambda path: None

# Part 2 (API endpoint tests) stubs these to no-ops for isolation from real
# market calls, and never restores them — Part 3 needs the real
# implementations (it mocks _batch_ltp/_fetch_ltp per-test instead), so keep
# a reference here to restore right before Part 3 runs.
_real_paper_auto_check = swing_trading.paper_auto_check
_real_paper_auto_buy_picks = swing_trading.paper_auto_buy_picks

TODAY = datetime.now().strftime("%Y-%m-%d")
_passed, _failed = [], []


def check(name, fn):
    try:
        fn()
        _passed.append(name)
        print(f"  PASS  {name}")
    except Exception as e:
        _failed.append((name, e))
        print(f"  FAIL  {name}: {e!r}")


def fake_pick(symbol, score=80, price=100.0):
    return {
        "symbol": symbol, "name": symbol.replace(".NS", ""), "price": price,
        "score": score, "setup": "RSI Oversold Bounce", "rsi": 40.0,
        "volume_ratio": 1.3, "volume_spike": False, "trend": "Up",
        "ema20": price * 0.99, "ema50": price * 0.97, "macd_signal": "Bullish",
        "entry": price, "stop_loss": price * 0.95, "target1": price * 1.06,
        "target2": price * 1.10, "risk_reward": "1:2.0",
        "predicted_gain_pct": 7.5, "prediction_confidence": score,
    }


PICKS_A = [fake_pick("AAA.NS", 82), fake_pick("BBB.NS", 71)]
PICKS_B = [fake_pick("CCC.NS", 90), fake_pick("DDD.NS", 66)]

# ══════════════════════════════════════════════════════════════
# Part 1 — swing_trading storage unit tests (temp dirs, logged out)
# ══════════════════════════════════════════════════════════════
tmp_root = Path(tempfile.mkdtemp(prefix="swing_test_"))
legacy_dir = tmp_root / "paper_trading"
legacy_dir.mkdir(parents=True)
swing_trading.PAPER_DATA_DIR = legacy_dir
swing_trading.DESK_DATA_DIR = legacy_dir
swing_trading.set_active_data_dir(None)

print("\n-- Daily picks persistence --")


def t_first_save_is_canonical():
    saved = swing_trading.save_daily_picks(TODAY, PICKS_A)
    assert saved == PICKS_A
    # Second save without overwrite must NOT change the canonical list
    saved2 = swing_trading.save_daily_picks(TODAY, PICKS_B)
    assert saved2 == PICKS_A
    assert swing_trading.load_saved_picks(TODAY) == PICKS_A


def t_file_shape():
    store = json.loads(swing_trading._picks_file().read_text())
    assert "dates" in store and TODAY in store["dates"]
    entry = store["dates"][TODAY]
    assert "created_at" in entry and entry["picks"] == PICKS_A


def t_get_daily_picks_stable_never_rescans():
    calls = {"n": 0}

    def fake_scan(top_n, on_progress=None):
        calls["n"] += 1
        return PICKS_B

    orig = swing_trading.scan_swing_picks
    swing_trading.scan_swing_picks = fake_scan
    try:
        for _ in range(3):
            assert swing_trading.get_daily_picks(force=False) == PICKS_A
        assert calls["n"] == 0, "saved picks must not trigger a scan"
    finally:
        swing_trading.scan_swing_picks = orig


def t_hard_refresh_overwrites():
    orig = swing_trading.scan_swing_picks
    swing_trading.scan_swing_picks = lambda top_n, on_progress=None: PICKS_B
    try:
        assert swing_trading.get_daily_picks(force=True) == PICKS_B
        assert swing_trading.load_saved_picks(TODAY) == PICKS_B
    finally:
        swing_trading.scan_swing_picks = orig
    # restore canonical PICKS_A for later tests
    swing_trading.save_daily_picks(TODAY, PICKS_A, overwrite=True)


check("first save for a date is canonical; later saves ignored", t_first_save_is_canonical)
check("picks file has {dates: {date: {created_at, picks}}} shape", t_file_shape)
check("get_daily_picks(force=False) is stable and never re-scans", t_get_daily_picks_stable_never_rescans)
check("hard refresh (force=True) overwrites saved picks", t_hard_refresh_overwrites)

# ── Empty scans are failures, never canonical ──────────────────
# Regression: a scan that returned [] used to be saved as the day's canonical
# list. Because [] is a list, load_saved_picks returned it instead of None,
# which froze the Focus List at empty until midnight, made `force` a no-op at
# every call site, and let a failed hard rescan destroy an already-published
# list (2026-07-30 lost 5 picks, 2026-08-03 lost 3).
EMPTY_DAY = "2026-01-02"


def t_empty_save_never_reads_back_as_canonical():
    swing_trading.save_daily_picks(EMPTY_DAY, [])
    assert swing_trading.load_saved_picks(EMPTY_DAY) is None, \
        "an empty scan must read back as 'not saved', not as an empty list"


def t_empty_day_is_still_recorded_on_disk():
    store = json.loads(swing_trading._picks_file().read_text())
    assert EMPTY_DAY in store["dates"], "the failed attempt must stay auditable"
    assert store["dates"][EMPTY_DAY]["picks"] == []


def t_good_scan_can_follow_an_empty_one():
    out = swing_trading.save_daily_picks(EMPTY_DAY, PICKS_A)
    assert out == PICKS_A, "an empty day must not block a later good save"
    assert swing_trading.load_saved_picks(EMPTY_DAY) == PICKS_A


def t_empty_never_overwrites_a_published_list():
    # Even a deliberate hard reset must not trade real picks for nothing.
    out = swing_trading.save_daily_picks(EMPTY_DAY, [], overwrite=True)
    assert out == PICKS_A, "empty rescan must yield to the published list"
    assert swing_trading.load_saved_picks(EMPTY_DAY) == PICKS_A


def t_empty_day_rescans_instead_of_serving_nothing():
    day = "2026-01-05"
    swing_trading.save_daily_picks(day, [])
    calls = {"n": 0}

    def fake_scan(top_n, on_progress=None):
        calls["n"] += 1
        return PICKS_B

    orig_scan = swing_trading.scan_swing_picks
    orig_now = swing_trading.datetime
    swing_trading.scan_swing_picks = fake_scan

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 5, 10, 0, 0)

    swing_trading.datetime = _FrozenNow
    try:
        got = swing_trading.get_daily_picks(force=False)
        assert calls["n"] == 1, "an empty day must trigger a re-scan, not serve []"
        assert got == PICKS_B
    finally:
        swing_trading.scan_swing_picks = orig_scan
        swing_trading.datetime = orig_now


check("empty scan does not read back as a canonical list", t_empty_save_never_reads_back_as_canonical)
check("empty day is still recorded on disk for the audit trail", t_empty_day_is_still_recorded_on_disk)
check("a good scan can still publish after an empty one", t_good_scan_can_follow_an_empty_one)
check("empty rescan never overwrites a published list (even hard reset)", t_empty_never_overwrites_a_published_list)
check("get_daily_picks re-scans an empty day instead of serving []", t_empty_day_rescans_instead_of_serving_nothing)

print("\n-- Momentum-tier repeat cooldown --")
COOL_D1 = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
COOL_D2 = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
COOL_D3 = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
COOL_D4 = (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d")


def t_recently_topped_is_top_k_union_over_lookback():
    swing_trading.save_daily_picks(COOL_D1, [
        fake_pick("REPEAT1.NS", 90), fake_pick("REPEAT2.NS", 85),
        fake_pick("REPEAT3.NS", 80), fake_pick("RANK4.NS", 75),
    ])
    swing_trading.save_daily_picks(COOL_D2, [fake_pick("REPEAT4.NS", 88)])
    swing_trading.save_daily_picks(COOL_D3, [fake_pick("REPEAT5.NS", 77)])
    swing_trading.save_daily_picks(COOL_D4, [fake_pick("TOO_OLD.NS", 99)])

    recent = swing_trading._recently_topped_symbols(lookback_days=3, top_rank=3)
    assert recent == {"REPEAT1.NS", "REPEAT2.NS", "REPEAT3.NS", "REPEAT4.NS", "REPEAT5.NS"}
    assert "RANK4.NS" not in recent, "rank 4 on D-1 should not count as top-3"
    assert "TOO_OLD.NS" not in recent, "D-4 is outside the 3-day lookback"


def t_recently_topped_excludes_todays_own_picks():
    # A same-day re-scan must not see today's own (about-to-be-replaced)
    # picks as "recent" — otherwise a hard-reset re-scan would demote itself.
    swing_trading.save_daily_picks(TODAY, [fake_pick("SELFMATCH.NS", 99)], overwrite=True)
    recent = swing_trading._recently_topped_symbols(lookback_days=3, top_rank=3)
    assert "SELFMATCH.NS" not in recent
    swing_trading.save_daily_picks(TODAY, PICKS_A, overwrite=True)  # restore for later tests


check("recently-topped symbols = top-K union over the last N saved days",
      t_recently_topped_is_top_k_union_over_lookback)
check("today's own saved picks never count against itself",
      t_recently_topped_excludes_todays_own_picks)

print("\n-- Desk auto-select --")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def t_auto_select_idempotent():
    r1 = swing_trading.desk_auto_select(PICKS_A)
    assert r1["selected_count"] == 2, r1
    r2 = swing_trading.desk_auto_select(PICKS_A)
    assert r2["selected_count"] == 0, "second run must select nothing"
    data = swing_trading._load_desk()
    symbols = [r["symbol"] for r in data["records"]]
    assert symbols == ["AAA.NS", "BBB.NS"], symbols


def t_new_day_appends_batch():
    # Rewrite existing records as if selected yesterday, then auto-select
    # today's new picks — old batch must survive untouched.
    data = swing_trading._load_desk()
    for r in data["records"]:
        r["selected_date"] = YESTERDAY
        r["day_batch_label"] = f"{YESTERDAY} Picks"
    swing_trading._save_desk(data)
    frozen_before = {r["symbol"]: dict(r) for r in data["records"]}

    r = swing_trading.desk_auto_select(PICKS_B)
    assert r["selected_count"] == 2, r
    data = swing_trading._load_desk()
    by_date = {}
    for rec in data["records"]:
        by_date.setdefault(rec["selected_date"], []).append(rec["symbol"])
    assert by_date[YESTERDAY] == ["AAA.NS", "BBB.NS"]
    assert by_date[TODAY] == ["CCC.NS", "DDD.NS"]
    for rec in data["records"]:
        if rec["selected_date"] == YESTERDAY:
            assert rec == frozen_before[rec["symbol"]], "old batch was modified"


def t_auto_select_never_removes():
    before = swing_trading._load_desk()["records"]
    swing_trading.desk_auto_select(PICKS_A + PICKS_B)
    after = swing_trading._load_desk()["records"]
    assert after == before, "auto-select must never remove or replace records"


check("auto-select is idempotent (re-run selects 0, no dupes)", t_auto_select_idempotent)
check("next day's picks append a new dated batch, old batch frozen", t_new_day_appends_batch)
check("auto-select never removes existing records", t_auto_select_never_removes)

print("\n-- Desk lifecycle & frozen originals --")


def t_originals_frozen_on_reanalyze():
    data = swing_trading._load_desk()
    rec = data["records"][0]
    originals = {k: v for k, v in rec.items() if k.startswith("original_")} | {
        "selected_date": rec["selected_date"],
        "reason_selected": rec["reason_selected"],
        "buy_zone_low": rec["buy_zone_low"],
        "buy_zone_high": rec["buy_zone_high"],
    }
    snapshot = fake_pick(rec["symbol"], score=55, price=120.0)
    swing_trading._desk_apply_snapshot(rec, snapshot, days=2)
    assert rec["current_score"] == 55 and rec["current_price"] == 120.0
    for k, v in originals.items():
        assert rec[k] == v, f"{k} changed by re-analysis"


def t_lifecycle_expiry_and_persistence():
    orig_scan = swing_trading._scan_stock
    swing_trading._scan_stock = lambda sym: None  # offline re-scan
    try:
        data = swing_trading._load_desk()
        old_date = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
        expired_sym = data["records"][0]["symbol"]
        data["records"][0]["selected_date"] = old_date  # 20 trading days ago
        swing_trading._save_desk(data)

        swing_trading.desk_reanalyze()
        data = swing_trading._load_desk()
        symbols = [r["symbol"] for r in data["records"]]
        assert expired_sym not in symbols, "14-day-old record should expire"
        assert len(symbols) == 3, f"young records must survive: {symbols}"
        hist = [h["symbol"] for h in data["history"]]
        assert expired_sym in hist, "expired record must be retained in history"

        # A refresh/re-scan (even offline) must not clear active records
        swing_trading.desk_reanalyze()
        assert len(swing_trading._load_desk()["records"]) == 3
    finally:
        swing_trading._scan_stock = orig_scan


def t_records_survive_reload():
    # Simulated restart: read the file fresh from disk
    data = swing_trading._load_desk()
    assert len(data["records"]) == 3 and len(data["history"]) >= 1


check("re-analysis updates current_* but never originals", t_originals_frozen_on_reanalyze)
check("expiry after 14 trading days; survivors + history kept", t_lifecycle_expiry_and_persistence)
check("desk records survive reload from disk", t_records_survive_reload)

print("\n-- Desk keeps weakened/invalid; re-analysis history --")


def t_reanalyze_keeps_weakened_and_records_history():
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    swing_trading.desk_auto_select(
        [fake_pick("KEEP1.NS", 80, 100.0), fake_pick("KEEP2.NS", 78, 200.0)])

    def broken(sym):
        px = 50.0 if sym == "KEEP1.NS" else 100.0  # both below their stop
        return {**fake_pick(sym, 30, px), "trend": "Down",
                "ema20": px * 1.1, "ema50": px * 1.2, "risk_reward": "1:0.5"}

    orig = swing_trading._scan_stock
    swing_trading._scan_stock = broken
    try:
        swing_trading.desk_reanalyze()
    finally:
        swing_trading._scan_stock = orig

    data = swing_trading._load_desk()
    syms = [r["symbol"] for r in data["records"]]
    assert "KEEP1.NS" in syms and "KEEP2.NS" in syms, \
        f"weakened stocks must NOT be auto-removed: {syms}"
    assert all(h["symbol"] not in ("KEEP1.NS", "KEEP2.NS") for h in data["history"])
    rec = swing_trading._desk_find(data, "KEEP1.NS")
    assert rec["tracking_status"] == "AVOID", rec["tracking_status"]
    assert rec["setup_status"] == "invalid", rec["setup_status"]
    assert rec["original_score"] == 80, "original score must stay frozen"
    assert len(rec["reanalysis_history"]) >= 1, "a snapshot must be recorded"
    snap = rec["reanalysis_history"][-1]
    assert snap["recommendation"] == "AVOID"
    assert "indicators" in snap and "levels" in snap and "analyzed_at" in snap
    assert rec["what_changed"]


def t_reanalysis_history_collapses_same_day():
    rec = swing_trading._desk_find(swing_trading._load_desk(), "KEEP1.NS")
    before = len(rec["reanalysis_history"])
    orig = swing_trading._scan_stock
    swing_trading._scan_stock = lambda sym: fake_pick(sym, 60, 105.0)
    try:
        swing_trading.desk_reanalyze()
    finally:
        swing_trading._scan_stock = orig
    rec = swing_trading._desk_find(swing_trading._load_desk(), "KEEP1.NS")
    assert len(rec["reanalysis_history"]) == before, "same-day re-run must not grow history"
    assert rec["reanalysis_history"][-1]["score"] == 60, "latest snapshot must win"


def t_archive_moves_to_history():
    r = swing_trading.desk_archive("KEEP2.NS")
    assert r["status"] == "archived", r
    data = swing_trading._load_desk()
    assert swing_trading._desk_find(data, "KEEP2.NS") is None
    assert any(h["symbol"] == "KEEP2.NS" and h["removal_reason"] == "Archived by user"
               for h in data["history"])


def t_desk_list_is_strict_json_safe_with_nan():
    # A degenerate scan can yield NaN/Inf indicators; the desk response must
    # still serialize to strict JSON (what FastAPI does) instead of 500-ing.
    import json as _json
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    swing_trading.desk_auto_select([fake_pick("NANY.NS", 80, 100.0)])
    orig = swing_trading._scan_stock
    swing_trading._scan_stock = lambda sym: {
        "symbol": sym, "name": "NANY", "price": float("nan"), "score": 70,
        "setup": "s", "rsi": float("nan"), "macd_signal": "Bullish",
        "macd_hist": float("inf"), "adx": float("nan"), "volume_ratio": 1.1,
        "trend": "Up", "ema20": float("nan"), "ema50": 95.0,
        "supports": [float("nan")], "resistances": [110.0], "entry": None,
        "stop_loss": 95.0, "target1": 106.0, "target2": 110.0, "risk_reward": "1:2.0",
    }
    try:
        r = swing_trading.desk_list(reanalyze=True)
    finally:
        swing_trading._scan_stock = orig
    _json.dumps(r, allow_nan=False)  # raises if any NaN/Inf leaked through


check("re-analyze keeps weakened/invalid stocks (AVOID, not removed)", t_reanalyze_keeps_weakened_and_records_history)
check("re-analysis history appends and collapses per day", t_reanalysis_history_collapses_same_day)
check("user archive moves a stock to history", t_archive_moves_to_history)
check("desk list serializes to strict JSON even with NaN indicators", t_desk_list_is_strict_json_safe_with_nan)

print("\n-- Focus Dashboard fields (confidence, predicted gain, tracking day) --")


def t_focus_dashboard_fields_flow_through():
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    swing_trading.desk_auto_select([fake_pick("FOCUS1.NS", 82, 100.0)])
    data = swing_trading._load_desk()
    rec = data["records"][0]
    assert rec["original_predicted_gain_pct"] == 7.5

    view = swing_trading._desk_stock_view(rec, datetime.now())
    assert view["predicted_gain_pct"] == 7.5
    assert view["prediction_confidence"] == 82
    assert view["tracking_day"] == view["days_in_tracking"]


def t_expiry_history_retains_full_performance_snapshot():
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    swing_trading.desk_auto_select([fake_pick("EXPIRE1.NS", 85, 100.0)])
    data = swing_trading._load_desk()
    old_date = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
    data["records"][0]["selected_date"] = old_date
    data["records"][0]["current_price"] = 108.0  # simulate drift before expiry
    swing_trading._save_desk(data)

    orig_scan = swing_trading._scan_stock
    swing_trading._scan_stock = lambda sym: None  # offline re-scan
    try:
        swing_trading.desk_reanalyze()
    finally:
        swing_trading._scan_stock = orig_scan

    data = swing_trading._load_desk()
    hist = next(h for h in data["history"] if h["symbol"] == "EXPIRE1.NS")
    assert hist["original_price"] == 100.0
    assert hist["final_price"] == 108.0
    assert hist["actual_profit_pct"] == 8.0, hist["actual_profit_pct"]
    assert hist["prediction_confidence"] == 85
    assert hist["predicted_gain_pct"] == 7.5
    assert hist["entered"] is False


check("Focus Dashboard fields (confidence/predicted gain/tracking day) flow "
      "from pick to desk view", t_focus_dashboard_fields_flow_through)
check("expired picks retain a full performance snapshot in history, not just symbol/date",
      t_expiry_history_retains_full_performance_snapshot)


def t_day_snapshots_ladder():
    now = datetime.now()
    sel_date = (now - timedelta(days=20)).strftime("%Y-%m-%d")
    hist = []
    for offset in range(20, -1, -1):
        dt = now - timedelta(days=offset)
        day_num = swing_trading._trading_days_between(sel_date, dt)
        hist.append({
            "analyzed_at": dt.isoformat(timespec="seconds"),
            "price": 100.0 + day_num,
            "score": 80,
        })
    record = {"selected_date": sel_date, "original_price": 100.0,
              "reanalysis_history": hist}
    snaps = swing_trading._day_snapshots_from_history(record)
    for target in (1, 3, 7, 14):
        assert str(target) in snaps, f"day {target} missing: {snaps}"
        snap = snaps[str(target)]
        expected_pct = round((snap["price"] - 100.0) / 100.0 * 100, 2)
        assert snap["profit_pct"] == expected_pct, (target, snap)


def t_daily_pick_history_joins_picks_with_outcomes():
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    hist_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tracked_pick = fake_pick("TRACKED1.NS", 90, 100.0)
    skipped_pick = fake_pick("SKIPPED1.NS", 60, 50.0)
    swing_trading.save_daily_picks(hist_date, [tracked_pick, skipped_pick], overwrite=True)
    swing_trading.desk_auto_select([tracked_pick])
    data = swing_trading._load_desk()
    data["records"][0]["selected_date"] = hist_date
    swing_trading._save_desk(data)

    history = swing_trading.get_daily_pick_history(live=False)
    day_entry = next(d for d in history if d["date"] == hist_date)
    rows = {r["symbol"]: r for r in day_entry["picks"]}
    assert rows["TRACKED1.NS"]["tracked"] is True
    assert rows["TRACKED1.NS"]["predicted_gain_pct"] == 7.5
    assert rows["TRACKED1.NS"]["status"] in ("WAIT", "HOLD", "BUY", "AVOID")
    assert rows["SKIPPED1.NS"]["tracked"] is False
    assert rows["SKIPPED1.NS"]["status"] == "NOT_TRACKED"
    assert rows["SKIPPED1.NS"]["actual_profit_pct"] is None


def t_day_snapshots_stop_at_days_reached():
    """A pick 4 trading days old fills Day 1/3 and leaves Day 7/14 blank —
    it must not echo today's number under columns that haven't happened."""
    now = datetime.now()
    sel_date = swing_trading._nth_prior_trading_day(now, 4) \
        if hasattr(swing_trading, "_nth_prior_trading_day") else None
    if sel_date is None:
        # Walk back until exactly 4 trading days separate sel_date from now.
        d = now
        while True:
            d -= timedelta(days=1)
            if swing_trading._trading_days_between(d.strftime("%Y-%m-%d"), now) >= 4:
                break
        sel_date = d.strftime("%Y-%m-%d")
    days_in = swing_trading._trading_days_between(sel_date, now)
    hist = []
    d = datetime.strptime(sel_date, "%Y-%m-%d")
    while d < now:
        d += timedelta(days=1)
        if d.weekday() > 4:
            continue
        day_num = swing_trading._trading_days_between(sel_date, d)
        hist.append({"analyzed_at": d.isoformat(timespec="seconds"),
                     "price": 100.0 + day_num, "score": 70})
    record = {"selected_date": sel_date, "original_price": 100.0,
              "reanalysis_history": hist}
    snaps = swing_trading._day_snapshots_from_history(record, now)
    for target in (1, 3, 7, 14):
        if target <= days_in:
            assert str(target) in snaps, f"day {target} should be filled: {snaps}"
        else:
            assert str(target) not in snaps, \
                f"day {target} not reached yet (days_in={days_in}) but got {snaps}"


def t_day_snapshots_skip_failed_rescan_price():
    """A re-scan that returned no price must not blank the whole column — the
    latest priced snapshot at or before that day wins instead."""
    now = datetime.now()
    d = now
    while swing_trading._trading_days_between(d.strftime("%Y-%m-%d"), now) < 3:
        d -= timedelta(days=1)
    sel_date = d.strftime("%Y-%m-%d")
    hist, day = [], datetime.strptime(sel_date, "%Y-%m-%d")
    while day < now:
        day += timedelta(days=1)
        if day.weekday() > 4:
            continue
        n = swing_trading._trading_days_between(sel_date, day)
        # Day 3's re-scan failed (no price) — day 2 had 110.0.
        price = None if n == 3 else 100.0 + 5.0 * n
        hist.append({"analyzed_at": day.isoformat(timespec="seconds"),
                     "price": price, "score": 70})
    record = {"selected_date": sel_date, "original_price": 100.0,
              "reanalysis_history": hist}
    snaps = swing_trading._day_snapshots_from_history(record, now)
    assert snaps["3"]["price"] == 110.0, snaps["3"]
    assert snaps["3"]["profit_pct"] == 10.0, snaps["3"]


def t_history_surfaces_desk_records_after_picks_overwritten():
    """A hard refresh replacing a date's saved picks must not erase that day's
    real tracking from history — the desk is authoritative for what was tracked,
    and the superseded list is kept too."""
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    # A date no other test writes to, so `superseded` reflects only this test.
    date = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    morning = fake_pick("MORNING1.NS", 88, 100.0)
    swing_trading.save_daily_picks(date, [morning], overwrite=True)
    swing_trading.desk_auto_select([morning])
    data = swing_trading._load_desk()
    data["records"][0]["selected_date"] = date
    swing_trading._save_desk(data)

    # Hard refresh publishes a completely different list for the same date.
    evening = fake_pick("EVENING1.NS", 84, 200.0)
    swing_trading.save_daily_picks(date, [evening], overwrite=True)

    store = swing_trading._load_picks_store()
    assert store["dates"][date]["superseded"][0]["picks"][0]["symbol"] == "MORNING1.NS"

    history = swing_trading.get_daily_pick_history(live=False)
    rows = {r["symbol"]: r
            for r in next(d for d in history if d["date"] == date)["picks"]}
    assert rows["MORNING1.NS"]["tracked"] is True, rows["MORNING1.NS"]
    assert rows["EVENING1.NS"]["tracked"] is False, rows["EVENING1.NS"]


def t_history_skips_empty_engine_variants():
    """An empty shadow-engine variant key must not render as its own date group
    reading '0 picks · 0 tracked'."""
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    swing_trading.save_daily_picks(date, [fake_pick("CANON1.NS", 80)], overwrite=True)
    swing_trading.save_daily_picks(date, [], overwrite=True, variant="v5")
    dates = [d["date"] for d in swing_trading.get_daily_pick_history(live=False)]
    assert f"{date}::v5" not in dates, dates
    assert date in dates, dates


def t_history_flags_symbol_tracked_under_earlier_date():
    """A pick left untracked because the same symbol is already on the desk from
    an earlier day should say so rather than a bare 'not tracked'."""
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    earlier = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    later = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    pick = fake_pick("REPEAT1.NS", 85, 100.0)
    swing_trading.save_daily_picks(earlier, [pick], overwrite=True)
    swing_trading.desk_auto_select([pick])
    data = swing_trading._load_desk()
    data["records"][0]["selected_date"] = earlier
    swing_trading._save_desk(data)
    swing_trading.save_daily_picks(later, [pick], overwrite=True)

    history = swing_trading.get_daily_pick_history(live=False)
    row = next(r for r in next(d for d in history if d["date"] == later)["picks"]
               if r["symbol"] == "REPEAT1.NS")
    assert row["tracked"] is False, row
    assert row["tracked_elsewhere_date"] == earlier, row


def t_history_live_overlay_beats_stale_same_candle_price():
    """A same-day pick reads +0.0% because the pick and its first re-scan share
    one unfinished daily candle. The live LTP overlay is what makes 'profit so
    far' real."""
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    pick = fake_pick("LIVE1.NS", 86, 100.0)
    swing_trading.save_daily_picks(TODAY, [pick], overwrite=True)
    swing_trading.desk_auto_select([pick])

    swing_trading._hist_ltp_cache = None
    real_batch = swing_trading._batch_ltp
    swing_trading._batch_ltp = lambda syms: {"LIVE1.NS": 104.0}
    try:
        history = swing_trading.get_daily_pick_history(live=True)
    finally:
        swing_trading._batch_ltp = real_batch
        swing_trading._hist_ltp_cache = None
    row = next(r for r in next(d for d in history if d["date"] == TODAY)["picks"]
               if r["symbol"] == "LIVE1.NS")
    assert row["live_price"] == 104.0, row
    assert row["actual_profit_pct"] == 4.0, row
    # Day 0 of tracking: no ladder column has happened yet.
    assert row["day_snapshots"] == {}, row


check("day 1/3/7/14 ladder derives from already-collected reanalysis_history",
      t_day_snapshots_ladder)
check("ladder stops at the trading day actually reached (no future columns)",
      t_day_snapshots_stop_at_days_reached)
check("ladder falls back past a failed re-scan with no price",
      t_day_snapshots_skip_failed_rescan_price)
check("Daily Pick History joins saved picks with desk outcomes (tracked vs not)",
      t_daily_pick_history_joins_picks_with_outcomes)
check("history keeps desk tracking + superseded picks after a hard refresh",
      t_history_surfaces_desk_records_after_picks_overwritten)
check("history skips empty shadow-engine variant date groups",
      t_history_skips_empty_engine_variants)
check("history explains a pick already tracked from an earlier date",
      t_history_flags_symbol_tracked_under_earlier_date)
check("history overlays live LTP so same-day picks aren't a flat +0.0%",
      t_history_live_overlay_beats_stale_same_candle_price)

print("\n-- v4.1 ranking (cross-sectional ATR penalty + near-high reward) --")


def v41_cand(symbol, atr_pct, dist_52w_pct, score=70, predicted_gain=9.0,
             ret63=12.0):
    """A scan result carrying just the fields v4/v4.1 ranking reads."""
    price = 100.0
    return {
        "symbol": symbol, "name": symbol.replace(".NS", ""), "price": price,
        "score": score, "setup": "Breakout", "adx": 30.0, "trend": "Up",
        "counter_trend": False, "atr_pct": atr_pct,
        "dist_52w_pct": dist_52w_pct,
        "high_52w": price / (dist_52w_pct / 100) if dist_52w_pct else None,
        "ret_63d_pct": ret63, "predicted_gain_pct": predicted_gain,
        "atr": price * atr_pct / 100 if atr_pct is not None else None,
        "risk_reward": "1:2.0", "prediction_confidence": score,
        # _scan_stock stamps this; v4 must leave it alone, v4.1 overwrites it.
        "engine": "v4",
    }


def _rank_v41(cands):
    """Run just the v4.1 ordering over `cands` (no scan, no network)."""
    def quality(r):
        return (not r.get("counter_trend") and r.get("trend") == "Up"
                and (r.get("adx") or 0) >= 25)

    def rs(r):
        r63 = r.get("ret_63d_pct")
        return r63 is not None and r63 > 0

    return swing_trading._apply_v41_ranking(list(cands), set(), quality, rs)


def t_pct_ranks_ties_and_missing():
    pr = swing_trading._pct_ranks
    assert pr([]) == []
    assert pr([None, None]) == [0.5, 0.5]
    # Ties share the average rank (pandas rank(pct=True) semantics).
    a = pr([1.0, 1.0, 2.0, 2.0])
    assert a[0] == a[1] and a[2] == a[3] and a[2] > a[0], a
    # A missing value lands mid-pack rather than at either extreme.
    b = pr([1.0, 5.0, 10.0, None])
    assert b[3] == 0.5, b
    assert b[0] < b[1] < b[2], b
    # Monotone and inside (0, 1].
    c = pr([3.0, 1.0, 2.0])
    assert c[1] < c[2] < c[0], c
    assert all(0 < v <= 1 for v in c), c


def t_v41_penalises_high_atr():
    """Two candidates alike but for volatility: the calmer one must rank first.
    v4 has no ATR term at all, so this is the change with the most evidence
    behind it (IC -0.047, negative in 6 of 6 folds)."""
    out = _rank_v41([v41_cand("WILD.NS", atr_pct=8.0, dist_52w_pct=95.0),
                     v41_cand("CALM.NS", atr_pct=1.5, dist_52w_pct=95.0)])
    assert [r["symbol"] for r in out] == ["CALM.NS", "WILD.NS"], out
    assert out[0]["v41_rank_score"] > out[1]["v41_rank_score"]


def t_v41_rewards_closeness_to_52w_high():
    out = _rank_v41([v41_cand("FAR.NS", atr_pct=3.0, dist_52w_pct=70.0),
                     v41_cand("NEAR.NS", atr_pct=3.0, dist_52w_pct=98.0)])
    assert [r["symbol"] for r in out] == ["NEAR.NS", "FAR.NS"], out


def t_v41_near_high_is_continuous_not_an_85pct_cliff():
    """v4 treats near-high as a binary `price >= 0.85 * high_52w` tier, so 84%
    and 5% are the same to it. v4.1 must separate them by degree."""
    out = _rank_v41([v41_cand("A.NS", atr_pct=3.0, dist_52w_pct=60.0),
                     v41_cand("B.NS", atr_pct=3.0, dist_52w_pct=80.0),
                     v41_cand("C.NS", atr_pct=3.0, dist_52w_pct=84.0)])
    assert [r["symbol"] for r in out] == ["C.NS", "B.NS", "A.NS"], out
    scores = [r["v41_rank_score"] for r in out]
    assert scores[0] > scores[1] > scores[2], scores


def t_v41_score_only_breaks_ties():
    """Rank score dominates; the raw score is the tiebreak, not the driver.
    A high-scoring volatile name must NOT outrank a calm one."""
    out = _rank_v41([v41_cand("WILD.NS", atr_pct=9.0, dist_52w_pct=95.0, score=95),
                     v41_cand("CALM.NS", atr_pct=1.2, dist_52w_pct=95.0, score=56)])
    assert out[0]["symbol"] == "CALM.NS", out
    # Equal features -> score decides.
    tie = _rank_v41([v41_cand("LO.NS", atr_pct=3.0, dist_52w_pct=90.0, score=60),
                     v41_cand("HI.NS", atr_pct=3.0, dist_52w_pct=90.0, score=88)])
    assert [r["symbol"] for r in tie] == ["HI.NS", "LO.NS"], tie


def t_v41_stamps_engine_and_rank_fields():
    out = _rank_v41([v41_cand("X.NS", atr_pct=2.0, dist_52w_pct=90.0),
                     v41_cand("Y.NS", atr_pct=4.0, dist_52w_pct=80.0)])
    for r in out:
        assert r["engine"] == "v4.1", r
        for f in ("xr_atr_pct", "xr_near_high", "v41_rank_score",
                  "quality_pick", "v3_momentum", "recently_topped"):
            assert f in r, (f, r)


def _scan_with_stubs(cands, engine):
    """Drive scan_swing_picks over `cands` with no network and no live-price
    validation, so only the floor + ranking are under test."""
    orig = (swing_trading.get_swing_universe, swing_trading._scan_stock,
            swing_trading._ensure_kite_auth, swing_trading._fetch_ohlcv_yahoo,
            swing_trading._select_validated_picks,
            swing_trading._recently_topped_symbols)
    by_sym = {c["symbol"]: c for c in cands}
    swing_trading.get_swing_universe = lambda key=None: list(by_sym)
    swing_trading._scan_stock = lambda sym, require_liquid=True: dict(by_sym[sym])
    swing_trading._ensure_kite_auth = lambda: False
    swing_trading._fetch_ohlcv_yahoo = lambda *a, **k: None   # no Nifty benchmark
    swing_trading._select_validated_picks = lambda ranked, top_n: ranked[:top_n]
    swing_trading._recently_topped_symbols = lambda *a, **k: set()
    try:
        return swing_trading.scan_swing_picks(5, engine=engine)
    finally:
        (swing_trading.get_swing_universe, swing_trading._scan_stock,
         swing_trading._ensure_kite_auth, swing_trading._fetch_ohlcv_yahoo,
         swing_trading._select_validated_picks,
         swing_trading._recently_topped_symbols) = orig


def t_v41_selection_floor_no_longer_requires_high_atr():
    """THE defect this engine exists to fix.

    v4 gates on predicted_gain_pct >= 5, and that value is
    max(resistance_distance, 2.5*ATR/price*100). With no resistance overhead a
    calm name scores 2.5 * 1.5 = 3.75 and is thrown out, so v4 structurally
    cannot pick low-volatility stocks — the one property measured negative in
    6 of 6 folds, twice, on two different universes.
    """
    calm = v41_cand("CALM.NS", atr_pct=1.5, dist_52w_pct=96.0, predicted_gain=3.75)
    wild = v41_cand("WILD.NS", atr_pct=8.0, dist_52w_pct=96.0, predicted_gain=20.0)

    v4 = [p["symbol"] for p in _scan_with_stubs([calm, wild], "v4")]
    assert v4 == ["WILD.NS"], f"v4 should filter the calm name out: {v4}"

    v41 = [p["symbol"] for p in _scan_with_stubs([calm, wild], "v4.1")]
    assert set(v41) == {"CALM.NS", "WILD.NS"}, v41
    assert v41[0] == "CALM.NS", f"v4.1 should rank the calm name first: {v41}"


def t_v4_ranking_unchanged_by_the_v41_addition():
    """Regression: v4 is the frozen incumbent and the default. Adding v4.1 must
    not move a single v4 pick."""
    cands = [v41_cand("A.NS", 3.0, 95.0, score=80, predicted_gain=9.0),
             v41_cand("B.NS", 6.0, 92.0, score=90, predicted_gain=12.0),
             v41_cand("C.NS", 2.0, 88.0, score=70, predicted_gain=7.0)]
    # v4 ranks by score inside the momentum/quality tier; all three pass both.
    got = [p["symbol"] for p in _scan_with_stubs(cands, "v4")]
    assert got == ["B.NS", "A.NS", "C.NS"], got
    assert all(p.get("engine") == "v4" for p in _scan_with_stubs(cands, "v4"))


check("_pct_ranks handles ties, missing values and edge cases",
      t_pct_ranks_ties_and_missing)
check("v4.1 ranks the lower-ATR candidate first (the 6/6-fold effect)",
      t_v41_penalises_high_atr)
check("v4.1 rewards closeness to the 52-week high",
      t_v41_rewards_closeness_to_52w_high)
check("v4.1 treats near-high as continuous, not an 85% cliff",
      t_v41_near_high_is_continuous_not_an_85pct_cliff)
check("v4.1 uses raw score only as a tiebreak, not as the driver",
      t_v41_score_only_breaks_ties)
check("v4.1 stamps engine + cross-sectional rank fields on every pick",
      t_v41_stamps_engine_and_rank_fields)
check("v4.1 selection floor no longer implies atr_pct >= 2% (the defect)",
      t_v41_selection_floor_no_longer_requires_high_atr)
check("regression: v4's own ranking is untouched by the v4.1 addition",
      t_v4_ranking_unchanged_by_the_v41_addition)

print("\n-- Scan universe selector (Nifty 50 / 500 / Total Market) --")


def _no_network_universe():
    """Force the offline path so these tests exercise the fallback lists only."""
    orig_fetch = swing_trading._fetch_universe
    orig_mem = dict(swing_trading._universe_mem)
    orig_cache = swing_trading._UNIVERSE_CACHE
    swing_trading._fetch_universe = lambda key: None
    swing_trading._universe_mem = {}
    swing_trading._UNIVERSE_CACHE = tmp_root / "no_such_universe_cache.json"

    def restore():
        swing_trading._fetch_universe = orig_fetch
        swing_trading._universe_mem = orig_mem
        swing_trading._UNIVERSE_CACHE = orig_cache
    return restore


def t_universe_picker_offers_three_sizes():
    restore = _no_network_universe()
    try:
        assert swing_trading.PICKABLE_UNIVERSES == ["nifty50", "nifty500", "total"], \
            swing_trading.PICKABLE_UNIVERSES
        payload = swing_trading.list_scan_universes()
        sizes = {o["key"]: o["size"] for o in payload["options"]}
        assert sizes["nifty50"] == 50, sizes
        assert sizes["nifty500"] == 500, sizes
        assert sizes["total"] == len(swing_trading.SWING_UNIVERSE), sizes
        # Narrowest first, so the list reads fastest -> broadest.
        assert [o["key"] for o in payload["options"]] == ["nifty50", "nifty500", "total"]
        assert payload["selected"] == swing_trading.get_scan_universe()
    finally:
        restore()


def t_universe_selection_switches_the_scan_list():
    restore = _no_network_universe()
    original = swing_trading.get_scan_universe()
    try:
        for key, expected in (("nifty50", 50), ("nifty500", 500),
                              ("total", len(swing_trading.SWING_UNIVERSE))):
            assert swing_trading.set_scan_universe(key) == key
            assert swing_trading.get_universe_size() == expected, key
        # Nifty 50 must be a strict subset of the wider lists, or the picker is
        # offering inconsistent universes.
        n50 = set(swing_trading.get_swing_universe("nifty50"))
        n500 = set(swing_trading.get_swing_universe("nifty500"))
        assert n50 <= n500, sorted(n50 - n500)
    finally:
        swing_trading.set_scan_universe(original)
        restore()


def t_unknown_universe_falls_back_to_default():
    """A stale/renamed saved setting must not wedge scanning."""
    original = swing_trading.get_scan_universe()
    try:
        assert swing_trading.set_scan_universe("nifty4000") == \
            swing_trading.DEFAULT_SCAN_UNIVERSE
        assert swing_trading.set_scan_universe(None) == \
            swing_trading.DEFAULT_SCAN_UNIVERSE
    finally:
        swing_trading.set_scan_universe(original)


def t_universe_fetch_rejects_truncated_response():
    """A short/error CSV must be ignored rather than shrinking the universe."""
    import requests
    orig_get = requests.get
    orig_cache = swing_trading._UNIVERSE_CACHE
    orig_mem = dict(swing_trading._universe_mem)
    requests.get = lambda *a, **k: SimpleNamespace(
        ok=True, text="Company Name,Industry,Symbol\nX Ltd,IT,XONLY\n")
    swing_trading._UNIVERSE_CACHE = tmp_root / "trunc_universe_cache.json"
    swing_trading._universe_mem = {}
    try:
        assert swing_trading._fetch_universe("nifty500") is None
        # Falling back keeps the full hardcoded list, not the 1-name response.
        assert len(swing_trading.get_swing_universe("nifty500")) == 500
    finally:
        requests.get = orig_get
        swing_trading._UNIVERSE_CACHE = orig_cache
        swing_trading._universe_mem = orig_mem


def t_legacy_universe_cache_format_still_reads():
    """The pre-selector cache was a bare {"ts","symbols"} all-NSE payload."""
    orig_cache = swing_trading._UNIVERSE_CACHE
    try:
        legacy = tmp_root / "legacy_universe_cache.json"
        legacy.write_text(json.dumps({"ts": time.time(),
                                      "symbols": [f"S{i}.NS" for i in range(1500)]}))
        swing_trading._UNIVERSE_CACHE = legacy
        cache = swing_trading._load_universe_disk_cache()
        assert set(cache) == {"all_nse"}, list(cache)
        assert len(cache["all_nse"]["symbols"]) == 1500
    finally:
        swing_trading._UNIVERSE_CACHE = orig_cache


check("picker offers Nifty 50 / 500 / Total Market with real sizes",
      t_universe_picker_offers_three_sizes)
check("selecting a universe switches the list the scanner sweeps",
      t_universe_selection_switches_the_scan_list)
check("an unknown saved universe falls back to the default",
      t_unknown_universe_falls_back_to_default)
check("a truncated NSE index response is rejected, not adopted",
      t_universe_fetch_rejects_truncated_response)
check("the pre-selector universe cache format still loads",
      t_legacy_universe_cache_format_still_reads)

print("\n-- Per-user storage, migration, Drive sync list --")


def t_migration_copies_without_deleting():
    user_dir = tmp_root / "users" / "abc123def456"
    user_dir.mkdir(parents=True)
    legacy_paper = legacy_dir / "default.json"
    legacy_paper.write_text(json.dumps({"cash": 999, "positions": []}))
    legacy_desk_bytes = (legacy_dir / "desk_default.json").read_bytes()
    legacy_picks_bytes = (legacy_dir / "swing_daily_picks.json").read_bytes()

    swing_trading.set_active_data_dir(user_dir)
    try:
        assert (user_dir / "swing_paper.json").exists()
        assert (user_dir / "swing_desk.json").exists()
        assert (user_dir / "swing_daily_picks.json").exists()
        # Copies match, originals untouched
        assert (user_dir / "swing_desk.json").read_bytes() == legacy_desk_bytes
        assert (user_dir / "swing_daily_picks.json").read_bytes() == legacy_picks_bytes
        assert legacy_paper.exists()
        assert (legacy_dir / "desk_default.json").exists()
        assert (legacy_dir / "swing_daily_picks.json").exists()
        # Active paths now point into the user dir
        assert swing_trading._paper_file() == user_dir / "swing_paper.json"
        assert swing_trading._desk_file() == user_dir / "swing_desk.json"
        assert swing_trading._picks_file() == user_dir / "swing_daily_picks.json"
        # Migration must not overwrite existing user data
        marker = json.dumps({"cash": 111})
        (user_dir / "swing_paper.json").write_text(marker)
        swing_trading.set_active_data_dir(user_dir)
        assert (user_dir / "swing_paper.json").read_text() == marker
    finally:
        swing_trading.set_active_data_dir(None)


def t_sync_files_include_swing():
    for name in ("swing_daily_picks.json", "swing_desk.json", "swing_paper.json"):
        assert name in google_auth.SYNC_FILES, f"{name} missing from SYNC_FILES"


check("legacy files migrate by copy (nothing deleted/overwritten)", t_migration_copies_without_deleting)
check("google_auth.SYNC_FILES includes the swing files", t_sync_files_include_swing)

# ══════════════════════════════════════════════════════════════
# Part 2 — API endpoint tests (FastAPI TestClient, scans stubbed)
# ══════════════════════════════════════════════════════════════
print("\n-- API endpoints --")
# Importing main switches swing storage to the REAL logged-in user's dir and
# runs migration from PAPER_DATA_DIR — point it at an empty dir first so
# part-1 test data can never leak into real user data.
_empty_legacy = tmp_root / "empty_legacy"
_empty_legacy.mkdir()
swing_trading.PAPER_DATA_DIR = _empty_legacy
swing_trading.DESK_DATA_DIR = _empty_legacy
import main  # noqa: E402  (heavy import: registers routes, may switch user dir)
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)

api_dir = tmp_root / "api_user"
api_dir.mkdir()
swing_trading.set_active_data_dir(api_dir)
swing_trading._drive_upload_async = lambda path: None  # re-arm after main import
# Migration may have copied part-1 / real legacy files in — start clean.
for _name in ("swing_desk.json", "swing_daily_picks.json", "swing_paper.json"):
    (api_dir / _name).unlink(missing_ok=True)
main.kite_client = SimpleNamespace(connected=True, check_connection=lambda: True)
swing_trading.paper_auto_check = lambda user_id="default": []
swing_trading.paper_auto_buy_picks = lambda picks, user_id="default": []

_scan_calls = {"n": 0}
_scan_result = {"picks": PICKS_A}


def _fake_scan(top_n, on_progress=None):
    _scan_calls["n"] += 1
    return _scan_result["picks"]


swing_trading.scan_swing_picks = _fake_scan


def _reset_scan_state():
    main._swing_scan_cache.update(
        {"date": None, "picks": [], "scanning": False, "progress": 0,
         "total": 0, "current_stock": ""})
    main._last_scan_time = 0


def _strip_live(picks):
    """The daily-picks API attaches a display-only `live_price` overlay (see
    with_live_price_overlay) on top of the canonical saved picks — strip it
    before comparing against the raw fixture so these tests still assert the
    real invariant (saved picks are stable / never re-scanned) rather than
    the overlay's presence."""
    return [{k: v for k, v in p.items() if k != "live_price"} for p in picks]


def _wait_scan_done(timeout=10):
    deadline = time.time() + timeout
    while main._swing_scan_cache["scanning"] and time.time() < deadline:
        time.sleep(0.05)
    assert not main._swing_scan_cache["scanning"], "scan did not finish"


def t_api_first_scan_saves():
    _reset_scan_state()
    r = client.get("/api/swing/daily-picks", params={"force": True}).json()
    assert r["scanning"] is True
    _wait_scan_done()
    assert _scan_calls["n"] == 1
    assert swing_trading.load_saved_picks(TODAY) == PICKS_A
    assert (api_dir / "swing_daily_picks.json").exists()


def t_api_stable_across_calls():
    for force in (False, False, True, False):
        r = client.get("/api/swing/daily-picks", params={"force": force}).json()
        assert _strip_live(r["picks"]) == PICKS_A and r["cached"] is True and r["scanning"] is False
    assert _scan_calls["n"] == 1, "no call may re-scan while today's picks are saved"


def t_api_restart_serves_saved():
    _reset_scan_state()  # simulate process restart (memory cache gone)
    r = client.get("/api/swing/daily-picks", params={"force": False}).json()
    assert _strip_live(r["picks"]) == PICKS_A and r["cached"] is True
    assert _scan_calls["n"] == 1


def t_api_auto_select_uses_saved_and_idempotent():
    # The daily scan auto-admits its picks into the desk, so the canonical
    # picks are already tracked by the time auto-select is pressed — the manual
    # endpoint must stay a safe, idempotent no-op that never duplicates.
    desk = json.loads((api_dir / "swing_desk.json").read_text())
    assert [x["symbol"] for x in desk["records"]] == ["AAA.NS", "BBB.NS"], (
        "scan should have auto-admitted the canonical picks into the desk")
    main._swing_scan_cache["picks"] = PICKS_B  # RAM differs from canonical file
    r1 = client.post("/api/swing/desk/auto-select-from-today").json()
    assert r1["selected_count"] == 0, r1
    r2 = client.post("/api/swing/desk/auto-select-from-today").json()
    assert r2["selected_count"] == 0, r2
    desk = json.loads((api_dir / "swing_desk.json").read_text())
    assert [x["symbol"] for x in desk["records"]] == ["AAA.NS", "BBB.NS"]


def t_api_hard_reset_rescans():
    _reset_scan_state()
    _scan_result["picks"] = PICKS_B
    r = client.get("/api/swing/daily-picks",
                   params={"force": True, "hard_reset": True}).json()
    assert r["scanning"] is True
    _wait_scan_done()
    assert _scan_calls["n"] == 2
    assert swing_trading.load_saved_picks(TODAY) == PICKS_B
    # ...and the new canonical list is what later calls return
    r = client.get("/api/swing/daily-picks").json()
    assert _strip_live(r["picks"]) == PICKS_B


def t_api_desk_list_keeps_records():
    # 4 records: AAA/BBB auto-admitted by the first scan, CCC/DDD by the
    # hard-reset re-scan (the daily scan feeds the desk automatically).
    orig_scan = swing_trading._scan_stock
    swing_trading._scan_stock = lambda sym: None
    try:
        r = client.get("/api/swing/desk/list", params={"reanalyze": True}).json()
        assert r["active_count"] == 4, r
        labels = [b["batch_label"] for b in r["batches"]]
        assert labels == [f"{TODAY} Picks"], labels
        symbols = {st["symbol"] for b in r["batches"] for st in b["stocks"]}
        assert symbols == {"AAA.NS", "BBB.NS", "CCC.NS", "DDD.NS"}, symbols
    finally:
        swing_trading._scan_stock = orig_scan


def t_api_reanalyze_enriched_view_and_history():
    orig_scan = swing_trading._scan_stock
    swing_trading._scan_stock = lambda sym: fake_pick(sym, 70, 101.0)
    try:
        r = client.post("/api/swing/desk/reanalyze").json()
    finally:
        swing_trading._scan_stock = orig_scan
    stocks = [st for b in r["batches"] for st in b["stocks"]]
    assert stocks, r
    st = stocks[0]
    # Enriched fields the UI needs
    for k in ("current_recommendation", "original_recommendation", "what_changed",
              "final_instruction", "current_entry", "current_indicators",
              "initial_snapshot", "reanalysis_history"):
        assert k in st, f"desk view missing {k}"
    assert st["current_indicators"].get("rsi") is not None
    assert len(st["reanalysis_history"]) >= 1
    assert st["reanalysis_history"][-1]["recommendation"] in (
        "BUY", "WAIT", "HOLD", "AVOID", "EXIT")


check("first scan of the day persists picks to the user dir", t_api_first_scan_saves)
check("repeated calls (force true/false) return the saved list, no re-scan", t_api_stable_across_calls)
check("restart (cleared RAM cache) still serves saved picks", t_api_restart_serves_saved)
check("auto-select reads canonical saved picks and is idempotent", t_api_auto_select_uses_saved_and_idempotent)
check("hard_reset=true is the only path that re-scans and overwrites", t_api_hard_reset_rescans)
check("desk list + reanalyze keeps active records grouped by batch", t_api_desk_list_keeps_records)
check("reanalyze exposes enriched view + appends history", t_api_reanalyze_enriched_view_and_history)

# ══════════════════════════════════════════════════════════════
# Part 3 — Signal validation, paper-fill integrity, reset (acceptance criteria)
# ══════════════════════════════════════════════════════════════
print("\n-- Signal validation (validate_recommendation) --")

part3_dir = tmp_root / "part3_user"
part3_dir.mkdir(parents=True, exist_ok=True)
swing_trading.set_active_data_dir(part3_dir)
# Undo Part 2's permanent no-op stubs — Part 3 exercises the real functions.
swing_trading.paper_auto_check = _real_paper_auto_check
swing_trading.paper_auto_buy_picks = _real_paper_auto_buy_picks


def _fresh_pick(symbol, *, entry=100.0, buy_low=98.0, buy_high=102.0, stop=95.0,
                target=None, max_entry=None, current_price=100.0, status_override=None):
    """A minimal validated pick — the shape scan_swing_picks/_select_validated_picks
    produces, with full control over the fields the acceptance criteria specify."""
    status, reason = swing_trading.validate_recommendation(
        entry=entry, buy_zone_low=buy_low, buy_zone_high=buy_high, stop_loss=stop,
        target=target, current_price=current_price, max_entry_price=max_entry)
    if status_override:
        status = status_override
    return {
        "symbol": symbol, "name": symbol.replace(".NS", ""), "price": current_price,
        "score": 80, "setup": "RSI Oversold Bounce",
        "entry": entry, "suggested_entry": entry,
        "buy_zone_low": buy_low, "buy_zone_high": buy_high,
        "entry_range_low": buy_low, "entry_range_high": buy_high,
        "stop_loss": stop, "target1": target, "max_entry_price": max_entry,
        "current_price_at_signal": current_price, "signal_date": TODAY,
        "signal_timestamp": datetime.now().isoformat(timespec="seconds"),
        "actionable_status": status, "status_reason": reason,
        "data_stale": False,
    }


def t_A_stale_target_excluded():
    # Suggested entry ₹100, buy zone ₹90-110, target ₹130, current price ₹130.
    status, _ = swing_trading.validate_recommendation(
        entry=100, buy_zone_low=90, buy_zone_high=110, stop_loss=95,
        target=130, current_price=130)
    assert status in ("TARGET_ALREADY_REACHED", "MISSED_ENTRY"), status
    # Must never be selectable as a fresh recommendation or tracked by the desk.
    pick = _fresh_pick("STALE1.NS", entry=100, buy_low=90, buy_high=110, stop=95,
                       target=130, current_price=130)
    assert pick["actionable_status"] in ("TARGET_ALREADY_REACHED", "MISSED_ENTRY")
    r = swing_trading.desk_auto_select([pick])
    assert r["selected_count"] == 0, "stale/target-reached pick must never be tracked"
    swing_trading.paper_auto_buy_picks([pick])
    assert swing_trading._load_paper()["positions"] == [], "no paper position for a stale setup"
    assert swing_trading._load_paper()["pending_entries"] == [], "no pending watch for a stale setup"


def t_B_valid_current_entry_ready_to_buy():
    pick = _fresh_pick("READY1.NS", entry=100, buy_low=98, buy_high=102, stop=95,
                       current_price=100)
    assert pick["actionable_status"] == "READY_TO_BUY"


def t_C_waiting_below_zone():
    pick = _fresh_pick("WAIT1.NS", entry=100, buy_low=98, buy_high=102, stop=95,
                       current_price=96)
    assert pick["actionable_status"] == "WAIT_FOR_ENTRY"
    swing_trading.paper_auto_buy_picks([pick])
    data = swing_trading._load_paper()
    assert data["positions"] == [], "WAIT_FOR_ENTRY must never open a position"
    pending = [p for p in data["pending_entries"] if p["symbol"] == "WAIT1.NS"]
    assert len(pending) == 1, "WAIT_FOR_ENTRY should be queued as pending only"


def t_D_gap_over_entry_missed_no_fill_at_suggested():
    result = swing_trading.determine_fill(
        buy_zone_low=98, buy_zone_high=102, max_entry_price=106, observed_price=108)
    assert result["filled"] is False
    assert result["status"] == "MISSED_ENTRY"
    assert result["fill_price"] is None, "must never fill at the old suggested price"


def t_E_chronology_no_retrospective_fill():
    # Price touched ₹100 before the signal; the only observable post-signal
    # price is ₹120 — a fill must never use the earlier ₹100 print.
    pick = _fresh_pick("CHRONO1.NS", entry=100, buy_low=98, buy_high=102, stop=95,
                       max_entry=104, current_price=120, status_override="WAIT_FOR_ENTRY")
    swing_trading._save_paper({"capital": 1_000_000, "cash": 1_000_000,
                                "pending_entries": [swing_trading._pending_entry_from_pick(pick, 5)],
                                "missed_entries": [], "positions": [], "closed_trades": [],
                                "start_date": TODAY, "day_count": 0, "daily_equity": []})
    orig_batch_ltp = swing_trading._batch_ltp
    swing_trading._batch_ltp = lambda symbols: {"CHRONO1.NS": 120.0}
    try:
        actions = swing_trading.paper_try_fill_pending()
    finally:
        swing_trading._batch_ltp = orig_batch_ltp
    assert actions and actions[0]["status"] == "missed", actions
    data = swing_trading._load_paper()
    assert data["positions"] == [], "no position may open"
    assert all(p.get("entry_price") != 100 for p in data["positions"])
    assert data["pending_entries"] == []
    assert any(m["symbol"] == "CHRONO1.NS" for m in data["missed_entries"])


def t_B_auto_buy_pending_then_fills_at_observed_price():
    pick = _fresh_pick("FILL1.NS", entry=100, buy_low=98, buy_high=102, stop=95,
                       max_entry=104, current_price=100)
    swing_trading.paper_reset(capital=1_000_000)
    orig_batch_ltp = swing_trading._batch_ltp
    swing_trading._batch_ltp = lambda symbols: {"FILL1.NS": 100.0}
    try:
        swing_trading.paper_auto_buy_picks([pick])
    finally:
        swing_trading._batch_ltp = orig_batch_ltp
    data = swing_trading._load_paper()
    assert data["pending_entries"] == [], "should have filled, not stayed pending"
    positions = [p for p in data["positions"] if p["symbol"] == "FILL1.NS"]
    assert len(positions) == 1, data["positions"]
    pos = positions[0]
    assert pos["actual_fill_price"] == pos["entry_price"]
    assert pos["suggested_entry"] == 100
    assert pos["fill_source"] == "auto_scan"
    assert "filled_at" in pos and "signal_timestamp" in pos


def t_defect_regression_auto_buy_never_uses_stale_entry():
    # The original defect: paper_auto_buy_picks used pick['entry'] (a support
    # level) as the fill even when the live price had already moved far away.
    # entry/support = 100, but the market has already moved to 130 (above the
    # buy zone and above max_entry_price) — must be rejected outright.
    pick = _fresh_pick("REGRESS1.NS", entry=100, buy_low=98, buy_high=102, stop=95,
                       max_entry=104, current_price=130)
    assert pick["actionable_status"] in ("MISSED_ENTRY", "TARGET_ALREADY_REACHED")
    swing_trading.paper_reset(capital=1_000_000)
    swing_trading.paper_auto_buy_picks([pick])
    data = swing_trading._load_paper()
    assert data["positions"] == [], "must never buy a setup price already overtook"
    assert data["pending_entries"] == []


check("A. stale target (entry 100/zone 90-110/target 130, price 130) -> excluded, no paper fill",
      t_A_stale_target_excluded)
check("B. valid current entry (zone 98-102, price 100) -> READY_TO_BUY", t_B_valid_current_entry_ready_to_buy)
check("C. waiting (zone 98-102, price 96 above stop 95) -> WAIT_FOR_ENTRY, pending only", t_C_waiting_below_zone)
check("D. gap over entry (zone 98-102, first price 108) -> MISSED_ENTRY, no fill at 100",
      t_D_gap_over_entry_missed_no_fill_at_suggested)
check("E. signal chronology — no retrospective fill at a pre-signal price", t_E_chronology_no_retrospective_fill)
check("B. paper auto-buy queues pending then fills at the observed price (not a historical level)",
      t_B_auto_buy_pending_then_fills_at_observed_price)
check("regression: paper_auto_buy_picks never fills at pick['entry'] once price has moved away",
      t_defect_regression_auto_buy_never_uses_stale_entry)

print("\n-- Stop/target re-anchor to the actual fill price --")


def t_adjust_levels_preserves_risk_distance_at_fill():
    # suggested_entry 100, stop 95 -> intended risk = 5/share. Filled at 103
    # (still inside the zone) -> stop must move to 98, NOT stay frozen at 95
    # (that would silently let the position carry more risk than the
    # strategy's own ATR sizing intended).
    stop, target = swing_trading.adjust_levels_for_fill(
        suggested_entry=100, stop_loss=95, target=None, fill_price=103)
    assert stop == 98, stop
    assert target is None

    # A real target's reward distance is preserved the same way.
    stop2, target2 = swing_trading.adjust_levels_for_fill(
        suggested_entry=100, stop_loss=95, target=110, fill_price=103)
    assert stop2 == 98 and target2 == 113, (stop2, target2)

    # Degenerate adjustment (fill far below its own stop) falls back to the
    # original stop rather than producing a negative/nonsensical level.
    stop3, _ = swing_trading.adjust_levels_for_fill(
        suggested_entry=100, stop_loss=95, target=None, fill_price=2)
    assert stop3 == 95, stop3

    # Missing suggested_entry -> no adjustment at all.
    stop4, target4 = swing_trading.adjust_levels_for_fill(
        suggested_entry=None, stop_loss=95, target=110, fill_price=103)
    assert stop4 == 95 and target4 == 110


def t_regression_stop_reanchors_to_fill_not_stale_suggested_entry():
    # This is the exact bug reported from the live app: ALKEM's suggested
    # entry was 5515.50 (stop 5199.07, risk 316.43/share) but it filled at
    # 5604.80 because price had drifted up by the time the fill happened.
    # The stop must move with the fill so the position still risks ~316.43/
    # share, not the now-understated distance to the stale 5199.07 level.
    pick = _fresh_pick("ALKEMLIKE.NS", entry=5515.50, buy_low=5405.19, buy_high=5625.81,
                       stop=5199.07, max_entry=5625.81 * 1.02, current_price=5604.80)
    swing_trading.paper_reset(capital=1_000_000)
    orig_batch_ltp = swing_trading._batch_ltp
    swing_trading._batch_ltp = lambda symbols: {"ALKEMLIKE.NS": 5604.80}
    try:
        swing_trading.paper_auto_buy_picks([pick])
    finally:
        swing_trading._batch_ltp = orig_batch_ltp
    pos = next(p for p in swing_trading._load_paper()["positions"] if p["symbol"] == "ALKEMLIKE.NS")
    assert pos["actual_fill_price"] == round(5604.8 * 1.0005, 2), pos["actual_fill_price"]
    intended_risk = 5515.50 - 5199.07
    expected_stop = round(pos["actual_fill_price"] - intended_risk, 2)
    assert pos["stop_loss"] == expected_stop, (pos["stop_loss"], expected_stop)
    assert pos["stop_loss"] != 5199.07, "stop must not stay pinned to the stale pre-fill level"


check("adjust_levels_for_fill preserves risk/reward distance, not the stale level",
      t_adjust_levels_preserves_risk_distance_at_fill)
check("regression: a fill above suggested_entry re-anchors the stop (ALKEM-shape bug)",
      t_regression_stop_reanchors_to_fill_not_stale_suggested_entry)

print("\n-- Manual paper buy (desk) validates against a fresh price --")


def t_F_desk_paper_buy_rejects_outside_zone_then_accepts_fresh_fill():
    swing_trading._save_desk({"records": [], "history": [], "last_reanalyze_date": None})
    pick = _fresh_pick("DESKBUY1.NS", entry=100, buy_low=98, buy_high=102, stop=95,
                       max_entry=104, current_price=100)
    swing_trading.desk_auto_select([pick])
    swing_trading.paper_reset(capital=1_000_000)

    orig_fetch_ltp = swing_trading._fetch_ltp
    swing_trading._fetch_ltp = lambda symbol: 130.0  # price moved above the zone
    try:
        r = swing_trading.desk_paper_buy("DESKBUY1.NS")
    finally:
        swing_trading._fetch_ltp = orig_fetch_ltp
    assert "error" in r, r
    assert r.get("status") == "MISSED_ENTRY", r
    assert r.get("observed_price") == 130.0
    assert swing_trading._load_paper()["positions"] == []
    rec = swing_trading._desk_find(swing_trading._load_desk(), "DESKBUY1.NS")
    assert rec["entered"] is False, "a rejected buy must not mark the desk record entered"

    orig_fetch_ltp = swing_trading._fetch_ltp
    swing_trading._fetch_ltp = lambda symbol: 100.0  # price back inside the zone
    try:
        r2 = swing_trading.desk_paper_buy("DESKBUY1.NS")
    finally:
        swing_trading._fetch_ltp = orig_fetch_ltp
    assert r2.get("status") == "bought", r2
    positions = swing_trading._load_paper()["positions"]
    assert len(positions) == 1 and positions[0]["symbol"] == "DESKBUY1.NS"
    assert positions[0]["fill_source"] == "desk_manual"
    rec = swing_trading._desk_find(swing_trading._load_desk(), "DESKBUY1.NS")
    assert rec["entered"] is True


check("F. manual desk paper-buy rejects outside the zone, accepts a fresh in-zone fill",
      t_F_desk_paper_buy_rejects_outside_zone_then_accepts_fresh_fill)


def t_desk_ready_conditions_capped_at_max_entry():
    # entry=100, buy zone 98-102, max_entry_price=104 — price has gapped to
    # 200. "triggered" (price >= entry) must NOT fire uncapped, else the desk
    # would keep showing BUY long after the setup is unchaseable.
    record = {"original_entry": 100.0, "original_stop_loss": 95.0,
              "buy_zone_low": 98.0, "buy_zone_high": 102.0, "max_entry_price": 104.0}
    snapshot = {"price": 200.0, "ema20": 90.0, "ema50": 85.0, "trend": "Up",
                "risk_reward": "1:2.0", "volume_ratio": 1.5, "grade": "A"}
    assert swing_trading._desk_ready_conditions_met(record, snapshot, days=1) is False
    # ...but a price genuinely inside the zone still triggers normally.
    snapshot_ok = {**snapshot, "price": 100.0}
    assert swing_trading._desk_ready_conditions_met(record, snapshot_ok, days=1) is True


check("desk readyConditionsMet caps 'triggered' at max_entry_price (no BUY once price gapped away)",
      t_desk_ready_conditions_capped_at_max_entry)

print("\n-- Reset All Swing Data --")


def t_G_reset_all_swing_data_clears_current_user_only():
    swing_trading.save_daily_picks("2020-01-01", [_fresh_pick("OLD1.NS")], overwrite=True)
    swing_trading.desk_auto_select([_fresh_pick("KEEP9.NS")])
    swing_trading.paper_reset(capital=1_000_000)
    pick = _fresh_pick("RESETPICK.NS", current_price=100)
    orig_batch_ltp = swing_trading._batch_ltp
    swing_trading._batch_ltp = lambda symbols: {s: 100.0 for s in symbols}
    try:
        swing_trading.paper_auto_buy_picks([pick])
    finally:
        swing_trading._batch_ltp = orig_batch_ltp
    assert swing_trading._load_paper()["positions"], "setup: expected an open position before reset"

    unrelated = part3_dir / "portfolio.json"
    unrelated.write_text('{"marker": "do-not-touch"}')

    summary = swing_trading.reset_all_swing_data(capital=250000)
    assert summary["capital"] == 250000
    assert summary["desk_active_records_removed"] >= 1
    assert summary["open_positions_removed"] >= 1

    assert swing_trading._load_picks_store()["dates"] == {}
    desk = swing_trading._load_desk()
    assert desk["records"] == [] and desk["history"] == []
    paper = swing_trading._load_paper()
    assert paper["cash"] == 250000 and paper["capital"] == 250000
    assert paper["positions"] == [] and paper["pending_entries"] == []
    assert paper["closed_trades"] == [] and paper["missed_entries"] == []

    assert unrelated.read_text() == '{"marker": "do-not-touch"}', \
        "reset must never touch unrelated (portfolio) files"


check("G. Reset All Swing Data clears picks/desk/paper for the current user, "
      "reinitializes capital, leaves unrelated files untouched",
      t_G_reset_all_swing_data_clears_current_user_only)

swing_trading.set_active_data_dir(None)
shutil.rmtree(tmp_root, ignore_errors=True)

print(f"\n{len(_passed)} passed, {len(_failed)} failed")
if _failed:
    for name, err in _failed:
        print(f"FAILED: {name}: {err!r}")
    sys.exit(1)
