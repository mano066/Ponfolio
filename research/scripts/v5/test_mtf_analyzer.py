"""Tests for the v5 multi-timeframe analyzer — focus on leakage safety and
session-anchored resampling (the two things most likely to silently overstate
performance). Run:

  backend/.venv/Scripts/python.exe -m unittest \
      research.scripts.v5.test_mtf_analyzer
"""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.scripts.v5.mtf_analyzer import (
    add_indicators,
    analyze_multiframe,
    completed_daily,
    completed_intraday,
    resample_session_anchored,
)

NSE = "Asia/Kolkata"


def _one_session_1m(day: str, n: int = 375, start_price: float = 100.0):
    """n one-minute bars from 09:15 IST on `day` (n<=375 = full session)."""
    idx = pd.date_range(f"{day} 09:15", periods=n, freq="1min", tz=NSE)
    price = start_price + np.linspace(0, 5, n)
    return pd.DataFrame({
        "open": price, "high": price + 0.2, "low": price - 0.2,
        "close": price, "volume": np.full(n, 1000.0),
    }, index=idx)


class ResampleTests(unittest.TestCase):
    def test_no_bar_crosses_a_session(self):
        two = pd.concat([_one_session_1m("2026-07-23"), _one_session_1m("2026-07-24")])
        bars = resample_session_anchored(two, "60min")
        # Every 60m bar must belong to exactly one calendar session.
        for ts, row in bars.iterrows():
            self.assertLessEqual(row["source_minutes"], 60)
        # No bar spans the overnight gap: group by date, each date's first bar
        # opens at 09:15.
        for _, g in bars.groupby(bars.index.date):
            self.assertEqual(g.index[0].strftime("%H:%M"), "09:15")

    def test_five_hour_bar_leaves_a_partial_remainder(self):
        # A 6h15m session (375 min) -> one full 300-min bar + one 75-min partial.
        bars = resample_session_anchored(_one_session_1m("2026-07-23"), "300min")
        self.assertEqual(len(bars), 2)
        self.assertEqual(int(bars["source_minutes"].iloc[0]), 300)
        self.assertEqual(int(bars["source_minutes"].iloc[1]), 75)

    def test_first_bar_anchored_to_open_not_midnight(self):
        bars = resample_session_anchored(_one_session_1m("2026-07-23"), "15min")
        self.assertEqual(bars.index[0].strftime("%H:%M"), "09:15")


class AsOfLeakageTests(unittest.TestCase):
    def test_intraday_bar_hidden_until_it_closes(self):
        frame = _one_session_1m("2026-07-23", n=60)
        f15 = add_indicators(resample_session_anchored(frame, "15min"))
        # A 15m bar opening 09:15 CLOSES at 09:30. As of 09:29 it must be unseen.
        as_of_before = pd.Timestamp("2026-07-23 09:29", tz=NSE)
        as_of_after = pd.Timestamp("2026-07-23 09:30", tz=NSE)
        self.assertEqual(len(completed_intraday(f15, "15m", as_of_before)), 0)
        self.assertGreaterEqual(len(completed_intraday(f15, "15m", as_of_after)), 1)

    def test_daily_uses_only_completed_sessions(self):
        daily = pd.DataFrame(
            {"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3],
             "close": [1, 2, 3], "volume": [1, 1, 1]},
            index=pd.to_datetime(["2026-07-22", "2026-07-23", "2026-07-24"]),
        )
        # Mid-session on the 24th: the 24th's daily bar is NOT complete yet.
        midday = pd.Timestamp("2026-07-24 12:00", tz=NSE)
        seen = completed_daily(daily, midday)
        self.assertNotIn(pd.Timestamp("2026-07-24"), seen.index)
        self.assertIn(pd.Timestamp("2026-07-23"), seen.index)
        # After the close, it becomes visible.
        after = pd.Timestamp("2026-07-24 15:30", tz=NSE)
        self.assertIn(pd.Timestamp("2026-07-24"), completed_daily(daily, after).index)

    def test_analyze_never_reads_future_daily_bar(self):
        # 120 up-trending sessions; a future spike on the LAST date must not
        # influence a read taken mid-session that day.
        dates = pd.bdate_range("2026-01-01", periods=120)
        close = np.linspace(100, 160, 120)
        daily = add_indicators(pd.DataFrame(
            {"open": close, "high": close + 1, "low": close - 1,
             "close": close, "volume": np.full(120, 1e6)}, index=dates))
        daily.loc[dates[-1], ["open", "high", "low", "close"]] = 9999  # future spike
        as_of = pd.Timestamp(dates[-1].strftime("%Y-%m-%d") + " 12:00", tz=NSE)
        res = analyze_multiframe(daily, {}, as_of)
        # The spike (last, still-open session) must be excluded.
        self.assertLess(res.daily["close"], 200)


class CategoryTests(unittest.TestCase):
    def _uptrend_daily(self, n=260, top=160):
        dates = pd.bdate_range("2025-01-01", periods=n)
        close = np.linspace(100, top, n)
        return add_indicators(pd.DataFrame(
            {"open": close, "high": close + 1, "low": close - 1,
             "close": close, "volume": np.full(n, 1e6)}, index=dates))

    def _intraday_above_vwap(self, day):
        f = _one_session_1m(day, n=120)
        frames = {}
        for tf, rule in (("15m", "15min"), ("60m", "60min"), ("5m", "5min")):
            frames[tf] = add_indicators(resample_session_anchored(f, rule))
        return frames

    def test_relative_strength_momentum_detected(self):
        daily = self._uptrend_daily()
        frames = self._intraday_above_vwap("2025-12-31")
        as_of = pd.Timestamp("2025-12-31 15:30", tz=NSE)
        res = analyze_multiframe(daily, frames, as_of, nifty_ret_63d=0.0)
        self.assertIn(res.category, (
            "RELATIVE_STRENGTH_MOMENTUM", "TREND_PULLBACK_CONTINUATION"))
        self.assertTrue(res.alignment_score >= 50)
        self.assertIsNotNone(res.stop)

    def test_no_setup_when_daily_downtrend_and_no_intraday(self):
        dates = pd.bdate_range("2025-01-01", periods=120)
        close = np.linspace(160, 100, 120)  # downtrend
        daily = add_indicators(pd.DataFrame(
            {"open": close, "high": close + 1, "low": close - 1,
             "close": close, "volume": np.full(120, 1e6)}, index=dates))
        res = analyze_multiframe(daily, {}, pd.Timestamp("2025-06-30 15:30", tz=NSE))
        self.assertEqual(res.category, "NO_SETUP")
        self.assertFalse(res.actionable)


if __name__ == "__main__":
    unittest.main()
