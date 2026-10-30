"""
Unit tests for the pure mutual-fund dip layer.

    python -m unittest test_mf_dip -v
"""

import unittest

import mf_dip as md


def _txn(date, nav, units, invested=None, redeemed=0.0):
    return {"date": date, "nav": nav, "units": units,
            "invested": invested if invested is not None else nav * units,
            "redeemed": redeemed}


BUYS = [
    _txn("2024-01-05", 100.0, 10.0),   # 1,000
    _txn("2024-06-05", 110.0, 10.0),   # 1,100
]


class TestPurchaseStats(unittest.TestCase):
    def test_low_high_and_ratio(self):
        s = md.purchase_stats(BUYS)
        self.assertEqual(s["lowest_buy_nav"], 100.0)
        self.assertEqual(s["highest_buy_nav"], 110.0)
        self.assertAlmostEqual(s["high_low_ratio"], 1.10)
        self.assertEqual(s["buys"], 2)

    def test_weighted_average_not_simple_average(self):
        """
        The spec's own example uses a simple mean of 105; the weighted figure
        is the correct one and differs whenever the units differ.
        """
        txns = [_txn("2024-01-05", 100.0, 90.0),    # 9,000 for 90 units
                _txn("2024-06-05", 110.0, 10.0)]    # 1,100 for 10 units
        s = md.purchase_stats(txns)
        self.assertAlmostEqual(s["weighted_avg_nav"], 101.0)   # not 105

    def test_redemptions_are_excluded(self):
        """A sale says nothing about the price the user was willing to pay."""
        txns = BUYS + [{"date": "2024-09-01", "nav": 200.0, "units": 5.0,
                        "invested": 0.0, "redeemed": 1000.0}]
        s = md.purchase_stats(txns)
        self.assertEqual(s["highest_buy_nav"], 110.0)   # the 200 sale ignored
        self.assertEqual(s["buys"], 2)

    def test_transactions_without_nav_are_skipped_and_counted(self):
        txns = BUYS + [{"date": "2024-07-01", "nav": None, "units": 5.0}]
        s = md.purchase_stats(txns)
        self.assertEqual(s["buys"], 2)
        self.assertEqual(s["skipped"], 1)

    def test_invested_falls_back_to_nav_times_units(self):
        s = md.purchase_stats([{"date": "2024-01-01", "nav": 50.0, "units": 2.0}])
        self.assertAlmostEqual(s["total_cost"], 100.0)
        self.assertAlmostEqual(s["weighted_avg_nav"], 50.0)

    def test_no_history_yields_unknowns_not_zeros(self):
        s = md.purchase_stats([])
        self.assertIsNone(s["lowest_buy_nav"])
        self.assertIsNone(s["weighted_avg_nav"])
        self.assertIsNone(s["high_low_ratio"])
        self.assertEqual(s["buys"], 0)

    def test_first_and_last_buy_dates(self):
        s = md.purchase_stats(BUYS)
        self.assertEqual(s["first_buy"], "2024-01-05")
        self.assertEqual(s["last_buy"], "2024-06-05")


class TestPositionInRange(unittest.TestCase):
    def setUp(self):
        self.stats = md.purchase_stats(BUYS)   # low 100, high 110, avg 105

    def test_below_everything_paid(self):
        p = md.position_in_range(95.0, self.stats)
        self.assertEqual(p["position"], md.POS_BELOW_LOWEST)

    def test_near_lowest(self):
        p = md.position_in_range(102.0, self.stats)
        self.assertEqual(p["position"], md.POS_NEAR_LOWEST)

    def test_below_average(self):
        p = md.position_in_range(104.0, self.stats)
        self.assertEqual(p["position"], md.POS_BELOW_AVERAGE)

    def test_above_highest(self):
        p = md.position_in_range(130.0, self.stats)
        self.assertEqual(p["position"], md.POS_ABOVE_HIGHEST)

    def test_percentages_match_hand_computation(self):
        p = md.position_in_range(98.0, self.stats)
        self.assertAlmostEqual(p["vs_avg_pct"], round((98 - 105) / 105 * 100, 2))
        self.assertAlmostEqual(p["vs_lowest_pct"], -2.0)

    def test_cheap_looking_positions_carry_the_valuation_caution(self):
        """
        The single most important guard in this module: "below my average" is a
        fact about the user's history, not a statement that the fund is cheap.
        Every position that invites that misreading must say so.
        """
        for nav in (95.0, 102.0, 104.0):
            self.assertTrue(md.position_in_range(nav, self.stats)["caution"])

    def test_expensive_positions_carry_no_caution(self):
        self.assertIsNone(md.position_in_range(130.0, self.stats)["caution"])

    def test_no_history_is_unknown(self):
        p = md.position_in_range(100.0, md.purchase_stats([]))
        self.assertEqual(p["position"], md.POS_UNKNOWN)


def _study(threshold_rows, years=9.8, status="ok"):
    return {
        "status": status,
        "years": years,
        "baseline": {"1y": {"mean_pct": 13.0}},
        "thresholds": threshold_rows,
    }


def _row(pct, signals, reliable, mean, edge):
    return {"threshold_pct": pct, "signals": signals, "reliable": reliable,
            "forward": {"1y": {"mean_pct": mean}},
            "edge": {"1y": {"mean_pp": edge}}}


class TestBuyZones(unittest.TestCase):
    def test_levels_are_cut_from_the_peak(self):
        zones = md.buy_zones(peak_nav=100.0, current_nav=95.0)
        levels = {z["zone"]: z["nav_at_or_below"] for z in zones}
        self.assertAlmostEqual(levels[md.ZONE_GOOD], 90.0)
        self.assertAlmostEqual(levels[md.ZONE_STRONG], 85.0)
        self.assertAlmostEqual(levels[md.ZONE_EXTREME], 80.0)

    def test_reached_flag_follows_current_nav(self):
        zones = md.buy_zones(100.0, 84.0)
        by = {z["zone"]: z for z in zones}
        self.assertTrue(by[md.ZONE_GOOD]["reached"])
        self.assertTrue(by[md.ZONE_STRONG]["reached"])
        self.assertFalse(by[md.ZONE_EXTREME]["reached"])

    def test_no_peak_means_no_zones_rather_than_invented_ones(self):
        self.assertEqual(md.buy_zones(None, 95.0), [])
        self.assertEqual(md.buy_zones(0.0, 95.0), [])

    def test_evidence_reports_a_positive_edge(self):
        study = _study([_row(10.0, 9, True, 15.2, 1.9)])
        zones = md.buy_zones(100.0, 95.0, study)
        ev = next(z for z in zones if z["zone"] == md.ZONE_GOOD)["evidence"]
        self.assertTrue(ev["tested"])
        self.assertTrue(ev["reliable"])
        self.assertAlmostEqual(ev["edge_pp"], 1.9)
        self.assertIn("Beat", ev["note"])

    def test_evidence_says_so_when_the_signal_did_not_beat_the_baseline(self):
        """
        A zone must be allowed to argue against itself. The measured result for
        shallow dips is frequently negative, and hiding that would turn the
        panel into an advocate rather than an instrument.
        """
        study = _study([_row(10.0, 9, True, 9.1, -9.5)])
        ev = md.buy_zones(100.0, 95.0, study)[0]["evidence"]
        self.assertIn("did NOT beat", ev["note"].lower().replace("not", "NOT"))
        self.assertLess(ev["edge_pp"], 0)

    def test_thin_evidence_is_flagged_unreliable(self):
        study = _study([_row(10.0, 2, False, 53.5, 40.2)])
        ev = md.buy_zones(100.0, 95.0, study)[0]["evidence"]
        self.assertFalse(ev["reliable"])
        self.assertIn("too few", ev["note"])

    def test_missing_study_is_explicit_not_silent(self):
        ev = md.buy_zones(100.0, 95.0, None)[0]["evidence"]
        self.assertFalse(ev["tested"])
        self.assertIsNone(ev["edge_pp"])
        self.assertTrue(ev["note"])

    def test_untested_depth_is_named(self):
        study = _study([_row(5.0, 20, True, 10.8, -2.5)])   # no 10% row
        ev = md.buy_zones(100.0, 95.0, study)[0]["evidence"]
        self.assertFalse(ev["tested"])
        self.assertIn("not tested", ev["note"])


class TestNextTrigger(unittest.TestCase):
    def test_returns_the_shallowest_unreached_zone(self):
        zones = md.buy_zones(100.0, 88.0)      # good (90) reached
        trig = md.next_trigger(zones, 88.0)
        self.assertEqual(trig["zone"], md.ZONE_STRONG)
        self.assertAlmostEqual(trig["nav_at_or_below"], 85.0)
        self.assertAlmostEqual(trig["fall_needed_pct"], round(3 / 88 * 100, 2))

    def test_none_when_every_zone_is_reached(self):
        zones = md.buy_zones(100.0, 50.0)
        self.assertIsNone(md.next_trigger(zones, 50.0))

    def test_none_without_a_nav(self):
        self.assertIsNone(md.next_trigger(md.buy_zones(100.0, 95.0), None))


class TestAnalyseFund(unittest.TestCase):
    FUND = {"scheme_name": "ABC Small Cap", "category": "Small Cap",
            "nav": 98.0, "units": 50.0, "invested": 5000.0,
            "current_value": 4900.0, "return_pct": -2.0,
            "transactions": BUYS}

    def test_combines_history_benchmark_and_zones(self):
        r = md.analyse_fund(self.FUND, peak_nav=120.0,
                            benchmark="NIFTYSMLCAP250.NS",
                            benchmark_label="SMALLCAP 250",
                            benchmark_drawdown_pct=14.8,
                            study=_study([_row(15.0, 7, True, 20.1, 1.5)]))
        self.assertEqual(r["purchase"]["lowest_buy_nav"], 100.0)
        self.assertEqual(r["position"]["position"], md.POS_BELOW_LOWEST)
        self.assertAlmostEqual(r["benchmark_drawdown_pct"], 14.8)
        self.assertEqual(len(r["zones"]), 3)
        self.assertFalse(r["peak_is_purchase_high"])

    def test_missing_peak_falls_back_to_purchase_high_and_says_so(self):
        r = md.analyse_fund(self.FUND)
        self.assertTrue(r["peak_is_purchase_high"])
        self.assertEqual(r["peak_nav"], 110.0)

    def test_fund_with_no_transactions_still_returns_a_full_shape(self):
        bare = dict(self.FUND, transactions=[])
        rich = md.analyse_fund(self.FUND, peak_nav=120.0)
        thin = md.analyse_fund(bare)
        self.assertEqual(set(rich), set(thin))
        self.assertEqual(thin["position"]["position"], md.POS_UNKNOWN)
        # With no purchase history the anchor falls back to today's NAV, which
        # is a coherent (if weak) peak, so zones still exist and are flagged.
        self.assertTrue(thin["peak_is_purchase_high"])
        self.assertEqual(thin["peak_nav"], self.FUND["nav"])

    def test_fund_with_neither_nav_nor_history_has_no_zones(self):
        # Nothing to anchor on at all: zones would be invented numbers.
        r = md.analyse_fund({"scheme_name": "X", "nav": None, "transactions": []})
        self.assertEqual(r["zones"], [])
        self.assertIsNone(r["next_trigger"])


class TestPeakAnchor(unittest.TestCase):
    """
    Zones are cut from a peak. If the anchor is below today's NAV it is not a
    peak, and every zone derived from it describes a fall that has already
    happened — the exact reading a live fund (NAV 24.07, single purchase at
    19.53) produced before this guard existed.
    """

    FUND = {"scheme_name": "X", "nav": 24.07,
            "transactions": [_txn("2024-01-01", 19.53, 10.0)]}

    def test_real_peak_is_preferred_and_flagged_as_real(self):
        r = md.analyse_fund(self.FUND, peak_nav=30.0)
        self.assertEqual(r["peak_nav"], 30.0)
        self.assertFalse(r["peak_is_purchase_high"])

    def test_fallback_never_sits_below_todays_nav(self):
        r = md.analyse_fund(self.FUND)
        self.assertTrue(r["peak_is_purchase_high"])
        self.assertGreaterEqual(r["peak_nav"], self.FUND["nav"])

    def test_fallback_zones_are_all_below_todays_nav(self):
        r = md.analyse_fund(self.FUND)
        for z in r["zones"]:
            self.assertLess(z["nav_at_or_below"], self.FUND["nav"])
            self.assertFalse(z["reached"])


class TestBenchmarkDipTaper(unittest.TestCase):
    """
    Found on the live dashboard: the silver ETF proxy sits 38.8% below its
    high. market_indices calls that HIGH RISK, while this factor — saturating
    at 15% — scored it a flat 100 and the card read "Consider adding". The
    tape and the card were describing the same instrument in opposite terms.
    """

    def test_factor_peaks_in_the_correction_band(self):
        self.assertEqual(md.score_benchmark_dip(15.0), 100.0)
        self.assertEqual(md.score_benchmark_dip(25.0), 100.0)

    def test_factor_gives_ground_past_the_high_risk_depth(self):
        deep = md.score_benchmark_dip(38.8)
        self.assertLess(deep, 100.0)
        self.assertGreater(deep, md.BENCH_DIP_DEEP_FLOOR - 1)

    def test_decay_is_monotonic_and_floored(self):
        a = md.score_benchmark_dip(35.0)
        b = md.score_benchmark_dip(45.0)
        c = md.score_benchmark_dip(80.0)
        self.assertGreater(a, b)
        self.assertGreaterEqual(b, c)
        self.assertEqual(c, md.BENCH_DIP_DEEP_FLOOR)

    def test_shallow_falls_are_unaffected(self):
        self.assertEqual(md.score_benchmark_dip(1.0), 0.0)
        self.assertIsNone(md.score_benchmark_dip(None))

    def test_deep_fall_risk_is_flagged_on_the_card(self):
        fund = {"scheme_name": "Silver FoF", "nav": 37.18, "transactions": []}
        deep = md.analyse_fund(fund, peak_nav=61.4,
                               benchmark_drawdown_pct=38.8)
        shallow = md.analyse_fund(fund, peak_nav=61.4,
                                  benchmark_drawdown_pct=9.0)
        self.assertTrue(deep["deep_fall_risk"])
        self.assertFalse(shallow["deep_fall_risk"])


if __name__ == "__main__":
    unittest.main()
