"""
Unit tests for the pure capital-deployment engine.

    python -m unittest test_deploy_engine -v

No network — every input is hand-fed so the maths is pinned down.

The load-bearing assertions here are:
  * an UNKNOWN factor never behaves like a factor scored 0;
  * the money always balances (allocations + unallocated == amount);
  * ranking is deterministic, so nothing flakes between runs.
"""

import unittest
from datetime import date

import deploy_engine as de


def _row(key, score, *, kind=de.KIND_FUND, price=100.0, confidence=100,
         name=None, why=None, at_or_over_target=False, dd=None):
    """A minimal ranked row, as allocate() consumes them."""
    return {
        "kind": kind,
        "key": key,
        "name": name or key,
        "price": price,
        "score": score,
        "confidence": confidence,
        "why": why or [],
        "at_or_over_target": at_or_over_target,
        "factors": {de.FACTOR_OWN_DRAWDOWN: {"score": dd, "value": dd,
                                             "unit": "% below peak"}},
    }


def _cand(key, **over):
    base = {
        "kind": de.KIND_FUND,
        "key": key,
        "name": key,
        "price": 100.0,
        "units": 100.0,
        "value": 10000.0,
        "avg_cost": 100.0,
        "peak": 100.0,
        "benchmark": "^NSEI",
        "target_pct": None,
    }
    base.update(over)
    return base


# ══════════════════════════════════════════════════════════════════════════
#  FACTOR 1 — OWN DRAWDOWN
# ══════════════════════════════════════════════════════════════════════════

class TestOwnDrawdown(unittest.TestCase):
    def test_dead_band_and_saturation(self):
        # 2% off peak is the dead-band edge, 25% is saturation.
        self.assertEqual(de.score_own_drawdown(98.0, 100.0), 0.0)
        self.assertEqual(de.score_own_drawdown(75.0, 100.0), 100.0)
        self.assertEqual(de.score_own_drawdown(60.0, 100.0), 100.0)

    def test_midpoint(self):
        # 13.5% below peak is halfway between the 2% floor and 25% saturation.
        self.assertEqual(de.score_own_drawdown(86.5, 100.0), 50.0)

    def test_at_peak_scores_zero(self):
        self.assertEqual(de.score_own_drawdown(100.0, 100.0), 0.0)

    def test_above_peak_is_floored_not_negative(self):
        self.assertEqual(de.score_own_drawdown(120.0, 100.0), 0.0)

    def test_precomputed_override_wins(self):
        """mf_analysis already gives current_dd; don't re-derive it."""
        self.assertEqual(de.score_own_drawdown(999.0, 999.0, own_dd_pct=-13.5), 50.0)

    def test_override_sign_is_ignored(self):
        self.assertEqual(de.score_own_drawdown(None, None, own_dd_pct=-13.5),
                         de.score_own_drawdown(None, None, own_dd_pct=13.5))

    def test_unknown_when_no_peak_or_price(self):
        self.assertIsNone(de.score_own_drawdown(100.0, None))
        self.assertIsNone(de.score_own_drawdown(None, 100.0))
        self.assertIsNone(de.score_own_drawdown(0, 100.0))
        self.assertIsNone(de.score_own_drawdown(100.0, 0))
        self.assertIsNone(de.score_own_drawdown("junk", "junk"))


# ══════════════════════════════════════════════════════════════════════════
#  FACTOR 2 — INDEX DIP
# ══════════════════════════════════════════════════════════════════════════

class TestIndexDip(unittest.TestCase):
    def test_dead_band_and_saturation(self):
        self.assertEqual(de.score_index_dip("^NSEI", {"^NSEI": 1.0}), 0.0)
        self.assertEqual(de.score_index_dip("^NSEI", {"^NSEI": 15.0}), 100.0)
        self.assertEqual(de.score_index_dip("^NSEI", {"^NSEI": 40.0}), 100.0)

    def test_midpoint(self):
        self.assertEqual(de.score_index_dip("^NSEI", {"^NSEI": 8.0}), 50.0)

    def test_saturates_earlier_than_own_drawdown(self):
        """An index is diversified; 15% is already a generational fall."""
        at_15 = de.score_index_dip("^NSEI", {"^NSEI": 15.0})
        own_at_15 = de.score_own_drawdown(85.0, 100.0)
        self.assertEqual(at_15, 100.0)
        self.assertLess(own_at_15, 100.0)

    def test_unknown_when_feed_is_down(self):
        """None means 'no reading'. It must NOT read as 'index at its high'."""
        self.assertIsNone(de.score_index_dip("^NSEI", {"^NSEI": None}))
        self.assertIsNone(de.score_index_dip("^NSEI", {}))
        self.assertIsNone(de.score_index_dip(None, {"^NSEI": 10.0}))
        self.assertIsNone(de.score_index_dip("", {"^NSEI": 10.0}))
        self.assertIsNone(de.score_index_dip("^NSEI", None))

    def test_at_high_is_zero_not_none(self):
        self.assertEqual(de.score_index_dip("^NSEI", {"^NSEI": 0.0}), 0.0)


# ══════════════════════════════════════════════════════════════════════════
#  FACTOR 3 — BELOW AVERAGE COST
# ══════════════════════════════════════════════════════════════════════════

class TestBelowAvgCost(unittest.TestCase):
    def test_saturation_and_midpoint(self):
        self.assertEqual(de.score_below_avg_cost(85.0, 100.0), 100.0)
        self.assertEqual(de.score_below_avg_cost(92.5, 100.0), 50.0)
        self.assertEqual(de.score_below_avg_cost(70.0, 100.0), 100.0)

    def test_above_cost_is_zero_never_negative(self):
        """A winner must not drag down its own composite."""
        self.assertEqual(de.score_below_avg_cost(150.0, 100.0), 0.0)
        self.assertEqual(de.score_below_avg_cost(100.0, 100.0), 0.0)

    def test_no_dead_band(self):
        self.assertGreater(de.score_below_avg_cost(99.0, 100.0), 0)

    def test_unknown_without_a_cost_basis(self):
        """A brand-new holding has no cost. That is not 'no discount'."""
        self.assertIsNone(de.score_below_avg_cost(100.0, None))
        self.assertIsNone(de.score_below_avg_cost(100.0, 0))
        self.assertIsNone(de.score_below_avg_cost(None, 100.0))


# ══════════════════════════════════════════════════════════════════════════
#  FACTOR 4 — UNDERWEIGHT
# ══════════════════════════════════════════════════════════════════════════

class TestUnderweight(unittest.TestCase):
    def test_half_of_target_saturates(self):
        # Holding 10% against a 20% target = half of intent.
        self.assertEqual(de.score_underweight(10.0, 100.0, 20.0), 100.0)

    def test_midpoint(self):
        # 15 against a 20 target: gap 5, relative shortfall 0.25 -> 50.
        self.assertEqual(de.score_underweight(15.0, 100.0, 20.0), 50.0)

    def test_on_target_and_overweight_are_zero(self):
        self.assertEqual(de.score_underweight(20.0, 100.0, 20.0), 0.0)
        self.assertEqual(de.score_underweight(35.0, 100.0, 20.0), 0.0)

    def test_small_gap_is_inside_the_dead_band(self):
        self.assertEqual(de.score_underweight(19.6, 100.0, 20.0), 0.0)

    def test_relative_not_absolute_shortfall(self):
        """The same 2pp gap must mean far more against a small target."""
        small = de.score_underweight(3.0, 100.0, 5.0)     # 2pp of a 5% target
        large = de.score_underweight(28.0, 100.0, 30.0)   # 2pp of a 30% target
        self.assertGreater(small, large)
        self.assertEqual(small, 80.0)

    def test_unknown_without_a_target(self):
        """'No target set' is not 'perfectly at target'."""
        self.assertIsNone(de.score_underweight(10.0, 100.0, None))
        self.assertIsNone(de.score_underweight(10.0, 100.0, 0))
        self.assertIsNone(de.score_underweight(10.0, 0, 20.0))


# ══════════════════════════════════════════════════════════════════════════
#  WEIGHTS
# ══════════════════════════════════════════════════════════════════════════

class TestNormalizeWeights(unittest.TestCase):
    def test_defaults_sum_to_one(self):
        self.assertAlmostEqual(sum(de.DEFAULT_WEIGHTS.values()), 1.0, places=6)

    def test_none_and_junk_fall_back_to_defaults(self):
        for raw in (None, {}, "junk", {"nonsense": 1.0}, {de.FACTOR_INDEX_DIP: 0}):
            self.assertEqual(de.normalize_weights(raw), dict(de.DEFAULT_WEIGHTS))

    def test_partial_map_is_renormalised(self):
        w = de.normalize_weights({de.FACTOR_OWN_DRAWDOWN: 3,
                                  de.FACTOR_UNDERWEIGHT: 1})
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)
        self.assertAlmostEqual(w[de.FACTOR_OWN_DRAWDOWN], 0.75, places=4)
        self.assertNotIn(de.FACTOR_INDEX_DIP, w)

    def test_unknown_keys_are_dropped(self):
        w = de.normalize_weights({de.FACTOR_OWN_DRAWDOWN: 1, "moon_phase": 99})
        self.assertNotIn("moon_phase", w)


# ══════════════════════════════════════════════════════════════════════════
#  COMPOSITE — the "unknown is not zero" guarantee
# ══════════════════════════════════════════════════════════════════════════

class TestComposite(unittest.TestCase):
    def test_all_four_known_blends_by_weight(self):
        row = de.score_candidate(
            _cand("F", price=75.0, peak=100.0, avg_cost=100.0,
                  value=10.0, target_pct=20.0),
            index_dips={"^NSEI": 8.0}, total_value=100.0)
        f = row["factors"]
        self.assertEqual(f[de.FACTOR_OWN_DRAWDOWN]["score"], 100.0)
        self.assertEqual(f[de.FACTOR_INDEX_DIP]["score"], 50.0)
        self.assertEqual(f[de.FACTOR_BELOW_AVG_COST]["score"], 100.0)
        self.assertEqual(f[de.FACTOR_UNDERWEIGHT]["score"], 100.0)
        expected = 0.35 * 100 + 0.30 * 100 + 0.20 * 100 + 0.15 * 50
        self.assertAlmostEqual(row["score"], expected, places=2)
        self.assertEqual(row["confidence"], 100)

    def test_unknown_factor_differs_from_that_factor_scored_zero(self):
        """THE core guarantee of this module."""
        base = dict(price=75.0, peak=100.0, avg_cost=None,
                    value=10.0, target_pct=None)
        # A: index known and at its high -> that factor really is 0.
        a = de.score_candidate(_cand("A", **base),
                               index_dips={"^NSEI": 0.0}, total_value=100.0)
        # B: identical, but no index reading at all -> unknown.
        b = de.score_candidate(_cand("B", benchmark=None, **base),
                               index_dips={}, total_value=100.0)

        self.assertEqual(a["factors"][de.FACTOR_INDEX_DIP]["score"], 0.0)
        self.assertIsNone(b["factors"][de.FACTOR_INDEX_DIP]["score"])
        self.assertNotEqual(a["score"], b["score"])
        # A is dragged down by a real zero; B is judged only on what is known.
        self.assertAlmostEqual(a["score"], 70.0, places=2)
        self.assertAlmostEqual(b["score"], 100.0, places=2)
        self.assertEqual(a["confidence"], 50)
        self.assertEqual(b["confidence"], 35)

    def test_confidence_reflects_known_weight(self):
        row = de.score_candidate(
            _cand("F", price=75.0, peak=100.0, avg_cost=None,
                  target_pct=None, benchmark=None),
            index_dips={}, total_value=0)
        self.assertEqual(row["confidence"], 35)   # own_drawdown only
        self.assertEqual(row["known_factors"], [de.FACTOR_OWN_DRAWDOWN])
        self.assertEqual(len(row["missing_factors"]), 3)

    def test_all_unknown_scores_none_not_zero(self):
        row = de.score_candidate(
            _cand("F", price=None, peak=None, avg_cost=None,
                  target_pct=None, benchmark=None, value=0),
            index_dips={}, total_value=0)
        self.assertIsNone(row["score"])
        self.assertEqual(row["confidence"], 0)
        self.assertFalse(row["eligible"])

    def test_low_confidence_is_not_eligible(self):
        """index_dip alone can score 100 and mean nothing."""
        row = de.score_candidate(
            _cand("F", price=None, peak=None, avg_cost=None, target_pct=None),
            index_dips={"^NSEI": 20.0}, total_value=0)
        self.assertEqual(row["score"], 100.0)
        self.assertEqual(row["confidence"], 15)
        self.assertFalse(row["eligible"])

    def test_value_is_derived_when_absent(self):
        row = de.score_candidate({"kind": "fund", "key": "F", "price": 50.0,
                                  "units": 10.0}, total_value=1000.0)
        self.assertEqual(row["value"], 500.0)

    def test_why_strings_are_plain_english(self):
        row = de.score_candidate(
            _cand("F", price=75.0, peak=100.0, avg_cost=100.0,
                  value=10.0, target_pct=20.0, benchmark_label="Nifty IT"),
            index_dips={"^NSEI": 8.0}, total_value=100.0)
        joined = " | ".join(row["why"])
        self.assertIn("below its own NAV peak", joined)
        self.assertIn("below your 20% target", joined)
        self.assertIn("below what you paid", joined)
        self.assertIn("Nifty IT is", joined)

    def test_stock_why_says_price_not_nav(self):
        row = de.score_candidate(
            _cand("ITC.NS", kind=de.KIND_STOCK, price=75.0, peak=100.0),
            total_value=100.0)
        self.assertIn("price peak", " ".join(row["why"]))


# ══════════════════════════════════════════════════════════════════════════
#  RANKING
# ══════════════════════════════════════════════════════════════════════════

class TestRanking(unittest.TestCase):
    def test_sorted_by_score_descending(self):
        cands = [
            _cand("low", price=99.0, peak=100.0),
            _cand("high", price=70.0, peak=100.0),
            _cand("mid", price=88.0, peak=100.0),
        ]
        rows = de.rank_candidates(cands, total_value=100000.0)
        self.assertEqual([r["key"] for r in rows], ["high", "mid", "low"])
        self.assertEqual([r["rank"] for r in rows], [1, 2, 3])

    def test_ties_break_on_key_for_determinism(self):
        cands = [_cand("zebra", price=75.0, peak=100.0),
                 _cand("alpha", price=75.0, peak=100.0)]
        for _ in range(5):
            rows = de.rank_candidates(cands, total_value=100000.0)
            self.assertEqual([r["key"] for r in rows], ["alpha", "zebra"])

    def test_unscored_candidates_sink_to_the_bottom(self):
        cands = [_cand("dead", price=None, peak=None, avg_cost=None,
                       target_pct=None, benchmark=None),
                 _cand("live", price=75.0, peak=100.0)]
        rows = de.rank_candidates(cands, total_value=100000.0)
        self.assertEqual(rows[0]["key"], "live")
        self.assertIsNone(rows[-1]["score"])

    def test_ignores_non_dict_entries(self):
        rows = de.rank_candidates([None, "junk", _cand("ok", price=75.0, peak=100.0)],
                                  total_value=1000.0)
        self.assertEqual(len(rows), 1)


# ══════════════════════════════════════════════════════════════════════════
#  ALLOCATION
# ══════════════════════════════════════════════════════════════════════════

class TestAllocation(unittest.TestCase):
    def assertBalances(self, result):
        """The invariant: money never vanishes and is never invented."""
        total = sum(a["amount"] for a in result["allocations"])
        self.assertAlmostEqual(round(total + result["unallocated"], 2),
                               round(result["amount"], 2), places=2)

    def test_single_candidate_takes_everything(self):
        """With one name, a concentration cap would strand the rest."""
        res = de.allocate(20000, [_row("A", 80.0)])
        self.assertBalances(res)
        self.assertEqual(len(res["allocations"]), 1)
        self.assertEqual(res["allocations"][0]["amount"], 20000.0)
        self.assertEqual(res["unallocated"], 0.0)

    def test_two_candidates_can_absorb_the_whole_amount(self):
        """A 40% cap over 2 names would place only 80% — it must loosen."""
        res = de.allocate(20000, [_row("A", 80.0), _row("B", 40.0)])
        self.assertBalances(res)
        self.assertEqual(res["unallocated"], 0.0)
        self.assertEqual(res["allocated"], 20000.0)

    def test_excess_score_weighting_not_raw(self):
        """80 vs 40 above a floor of 35 should be far more than raw score's 2:1.

        The cap is lifted here so this measures the WEIGHTING alone — with the
        default 40% cap in play the ratio is compressed by the redistribution,
        which is the cap doing its job, not the weighting failing.
        """
        res = de.allocate(60000, [_row("A", 80.0), _row("B", 40.0),
                                  _row("C", 39.0)], max_concentration_pct=100)
        amounts = {a["key"]: a["amount"] for a in res["allocations"]}
        self.assertBalances(res)
        self.assertGreater(amounts["A"] / amounts["B"], 2.5)

    def test_cap_compresses_the_spread(self):
        """The flip side: with the cap on, a runaway winner is reined in."""
        res = de.allocate(60000, [_row("A", 80.0), _row("B", 40.0),
                                  _row("C", 39.0)])
        amounts = {a["key"]: a["amount"] for a in res["allocations"]}
        self.assertBalances(res)
        self.assertEqual(amounts["A"], 24000.0)      # exactly the 40% cap
        self.assertEqual(res["unallocated"], 0.0)

    def test_concentration_cap_applies_with_enough_names(self):
        res = de.allocate(100000, [_row("A", 100.0), _row("B", 50.0),
                                   _row("C", 45.0), _row("D", 40.0)])
        self.assertBalances(res)
        for a in res["allocations"]:
            self.assertLessEqual(a["amount"], 40000.0 + 1e-6)

    def test_truncates_to_max_candidates(self):
        rows = [_row(f"F{i}", 90.0 - i) for i in range(8)]
        res = de.allocate(100000, rows)
        self.assertBalances(res)
        self.assertLessEqual(len(res["allocations"]), de.MAX_CANDIDATES_PER_DEPLOY)
        self.assertTrue(any(s["skip_reason"] == "not_selected"
                            for s in res["skipped"]))

    def test_below_floor_gets_nothing_with_a_reason(self):
        res = de.allocate(20000, [_row("A", 20.0), _row("B", 10.0)])
        self.assertBalances(res)
        self.assertEqual(res["allocations"], [])
        self.assertEqual(res["unallocated"], 20000.0)
        self.assertEqual(res["unallocated_reason"], "no_eligible_candidate")
        self.assertTrue(all(s["skip_reason"] == "below_score_floor"
                            for s in res["skipped"]))

    def test_low_confidence_gets_nothing_with_a_reason(self):
        res = de.allocate(20000, [_row("A", 100.0, confidence=15)])
        self.assertBalances(res)
        self.assertEqual(res["allocations"], [])
        self.assertEqual(res["skipped"][0]["skip_reason"], "low_confidence")

    def test_unscored_and_priceless_are_skipped(self):
        res = de.allocate(20000, [_row("A", None), _row("B", 90.0, price=0)])
        reasons = {s["skip_reason"] for s in res["skipped"]}
        self.assertEqual(reasons, {"unscored", "no_price"})
        self.assertBalances(res)

    def test_amount_below_min_ticket_reports_what_is_needed(self):
        res = de.allocate(300, [_row("A", 80.0)])
        self.assertBalances(res)
        self.assertEqual(res["allocations"], [])
        self.assertEqual(res["unallocated"], 300.0)
        self.assertEqual(res["unallocated_reason"], "amount_below_min_ticket")
        self.assertEqual(res["min_ticket_needed"], 500.0)

    def test_small_amount_still_finds_one_ticket(self):
        """₹700 must find its single ₹500 fund ticket, not give up."""
        res = de.allocate(700, [_row("A", 80.0), _row("B", 70.0)])
        self.assertBalances(res)
        self.assertEqual(len(res["allocations"]), 1)
        self.assertEqual(res["allocations"][0]["amount"], 700.0)

    def test_fund_amounts_are_rounded_to_the_step(self):
        res = de.allocate(20333, [_row("A", 80.0), _row("B", 60.0),
                                  _row("C", 50.0)])
        self.assertBalances(res)
        for a in res["allocations"]:
            self.assertEqual(a["amount"] % de.ROUNDING_STEP_MF, 0)

    def test_equity_buys_whole_shares_only(self):
        res = de.allocate(20000, [_row("ITC.NS", 80.0, kind=de.KIND_STOCK,
                                       price=288.05)])
        self.assertBalances(res)
        alloc = res["allocations"][0]
        self.assertIsInstance(alloc["shares"], int)
        self.assertEqual(alloc["shares"], 69)          # 20000 // 288.05
        self.assertAlmostEqual(alloc["amount"], round(69 * 288.05, 2), places=2)
        self.assertGreater(res["unallocated"], 0)      # the odd-lot remainder

    def test_share_price_above_budget_is_skipped(self):
        res = de.allocate(1000, [_row("PAGE", 90.0, kind=de.KIND_STOCK,
                                      price=40000.0)])
        self.assertBalances(res)
        self.assertEqual(res["allocations"], [])
        self.assertEqual(res["skipped"][0]["skip_reason"], "below_one_share")
        self.assertEqual(res["min_ticket_needed"], 40000.0)

    def test_units_are_estimated_for_funds(self):
        res = de.allocate(10000, [_row("A", 80.0, price=62.5)])
        self.assertAlmostEqual(res["allocations"][0]["units"], 160.0, places=3)

    def test_zero_and_negative_amounts(self):
        for amount in (0, -500, None):
            res = de.allocate(amount, [_row("A", 80.0)])
            self.assertEqual(res["allocations"], [])
            self.assertEqual(res["unallocated"], 0.0)
            self.assertBalances(res)

    def test_no_candidates_at_all(self):
        res = de.allocate(20000, [])
        self.assertBalances(res)
        self.assertEqual(res["unallocated"], 20000.0)
        self.assertEqual(res["unallocated_reason"], "no_eligible_candidate")

    def test_balances_across_many_shapes(self):
        """Fuzz the invariant over mixed fund/stock books."""
        prices = [62.5, 288.05, 1240.0, 99.99, 7.5]
        for amount in (500, 700, 1234, 10000, 20000, 33333, 100000):
            rows = [_row(f"F{i}", 90.0 - i * 7,
                         kind=de.KIND_STOCK if i % 2 else de.KIND_FUND,
                         price=prices[i % len(prices)])
                    for i in range(5)]
            self.assertBalances(de.allocate(amount, rows))


# ══════════════════════════════════════════════════════════════════════════
#  SIP PLAN STATUS
# ══════════════════════════════════════════════════════════════════════════

def _leg(key, amount=10000.0, due_day=5, kind=de.KIND_FUND, active=True):
    return {"id": f"leg_{key}", "kind": kind, "key": key, "label": key,
            "amount": amount, "due_day": due_day, "active": active}


def _fund(name, txns):
    return {"scheme_name": name, "transactions": txns}


class TestPlanStatus(unittest.TestCase):
    AS_OF = date(2026, 9, 15)

    def test_done_when_full_amount_recorded(self):
        funds = [_fund("A", [{"date": "2026-09-05", "invested": 10000.0}])]
        st = de.plan_status([_leg("A")], mf_portfolio=funds, as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_DONE)
        self.assertEqual(st["legs"][0]["deployed_this_month"], 10000.0)

    def test_done_within_tolerance(self):
        """AMC rounding means an exact match is rare."""
        funds = [_fund("A", [{"date": "2026-09-05", "invested": 9600.0}])]
        st = de.plan_status([_leg("A")], mf_portfolio=funds, as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_DONE)

    def test_partial(self):
        funds = [_fund("A", [{"date": "2026-09-05", "invested": 4000.0}])]
        st = de.plan_status([_leg("A")], mf_portfolio=funds, as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_PARTIAL)
        self.assertEqual(st["legs"][0]["shortfall"], 6000.0)

    def test_scheduled_before_the_due_day(self):
        funds = [_fund("A", [])]
        st = de.plan_status([_leg("A", due_day=25)], mf_portfolio=funds,
                            as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_SCHEDULED)
        self.assertEqual(st["legs"][0]["days_to_due"], 10)

    def test_due_inside_the_grace_window(self):
        funds = [_fund("A", [])]
        st = de.plan_status([_leg("A", due_day=14)], mf_portfolio=funds,
                            as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_DUE)

    def test_overdue_past_the_grace_window(self):
        funds = [_fund("A", [])]
        st = de.plan_status([_leg("A", due_day=5)], mf_portfolio=funds,
                            as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_OVERDUE)
        self.assertEqual(st["legs"][0]["days_overdue"], 10)

    def test_due_day_31_resolves_in_february(self):
        """A due_day of 31 must still fire in a short month."""
        funds = [_fund("A", [])]
        st = de.plan_status([_leg("A", due_day=31)], mf_portfolio=funds,
                            as_of=date(2026, 2, 27))
        self.assertEqual(st["legs"][0]["effective_due_day"], 28)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_SCHEDULED)

    def test_only_this_month_counts(self):
        funds = [_fund("A", [{"date": "2026-08-05", "invested": 10000.0},
                             {"date": "2026-10-05", "invested": 10000.0}])]
        st = de.plan_status([_leg("A")], mf_portfolio=funds, as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["deployed_this_month"], 0.0)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_OVERDUE)

    def test_multiple_transactions_accumulate(self):
        funds = [_fund("A", [{"date": "2026-09-05", "invested": 6000.0},
                             {"date": "2026-09-12", "invested": 4000.0}])]
        st = de.plan_status([_leg("A")], mf_portfolio=funds, as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_DONE)

    def test_stock_leg_reads_the_equity_ledger(self):
        ledger = {"ITC.NS": [{"date": "2026-09-05", "type": "BUY", "amount": 10000.0}]}
        st = de.plan_status([_leg("ITC.NS", kind=de.KIND_STOCK)],
                            equity_ledger=ledger, as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_DONE)

    def test_a_sale_does_not_undo_a_sip(self):
        ledger = {"ITC.NS": [{"date": "2026-09-05", "type": "BUY", "amount": 10000.0},
                             {"date": "2026-09-10", "type": "SELL", "amount": 9000.0}]}
        st = de.plan_status([_leg("ITC.NS", kind=de.KIND_STOCK)],
                            equity_ledger=ledger, as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_DONE)
        self.assertEqual(st["legs"][0]["deployed_this_month"], 10000.0)

    def test_missing_holding_is_unknown_not_overdue(self):
        st = de.plan_status([_leg("Ghost Fund")], mf_portfolio=[], as_of=self.AS_OF)
        self.assertEqual(st["legs"][0]["status"], de.STATUS_UNKNOWN)
        self.assertTrue(st["legs"][0]["missing_holding"])

    def test_inactive_leg_is_excluded_from_totals(self):
        funds = [_fund("A", []), _fund("B", [])]
        st = de.plan_status([_leg("A"), _leg("B", active=False)],
                            mf_portfolio=funds, as_of=self.AS_OF)
        self.assertEqual(st["legs"][1]["status"], de.STATUS_INACTIVE)
        self.assertEqual(st["budget_total"], 10000.0)
        self.assertEqual(st["total_count"], 1)

    def test_totals_and_month_label(self):
        funds = [_fund("A", [{"date": "2026-09-05", "invested": 10000.0}]),
                 _fund("B", [])]
        st = de.plan_status([_leg("A"), _leg("B", amount=20000.0)],
                            mf_portfolio=funds, as_of=self.AS_OF)
        self.assertEqual(st["month"], "2026-09")
        self.assertEqual(st["budget_total"], 30000.0)
        self.assertEqual(st["deployed_total"], 10000.0)
        self.assertEqual(st["remaining"], 20000.0)
        self.assertEqual(st["done_count"], 1)

    def test_overpayment_does_not_inflate_deployed_total(self):
        funds = [_fund("A", [{"date": "2026-09-05", "invested": 50000.0}])]
        st = de.plan_status([_leg("A", amount=10000.0)], mf_portfolio=funds,
                            as_of=self.AS_OF)
        self.assertEqual(st["deployed_total"], 10000.0)
        self.assertEqual(st["remaining"], 0.0)

    def test_empty_plan(self):
        st = de.plan_status([], as_of=self.AS_OF)
        self.assertEqual(st["legs"], [])
        self.assertEqual(st["budget_total"], 0.0)

    def test_ignores_malformed_legs(self):
        st = de.plan_status([None, "junk", _leg("A")], mf_portfolio=[_fund("A", [])],
                            as_of=self.AS_OF)
        self.assertEqual(len(st["legs"]), 1)


# ══════════════════════════════════════════════════════════════════════════
#  DEFAULTS
# ══════════════════════════════════════════════════════════════════════════

class TestDefaults(unittest.TestCase):
    def test_legs_split_budget_evenly_across_funds(self):
        funds = [{"scheme_name": f"F{i}"} for i in range(5)]
        legs = de.default_legs_from_portfolio(funds, monthly_budget=30000)
        self.assertEqual(len(legs), 5)
        self.assertTrue(all(l["amount"] == 6000.0 for l in legs))
        self.assertTrue(all(l["due_day"] == 5 for l in legs))

    def test_no_funds_gives_no_legs(self):
        self.assertEqual(de.default_legs_from_portfolio([], []), [])

    def test_targets_mirror_current_weights_and_sum_to_100(self):
        funds = [{"scheme_name": "A", "current_value": 60000.0},
                 {"scheme_name": "B", "current_value": 20000.0}]
        stocks = [{"symbol": "ITC.NS", "shares": 100, "avg_cost": 200.0}]
        targets = de.default_targets_from_portfolio(funds, stocks)
        self.assertAlmostEqual(sum(targets.values()), 100.0, places=1)
        self.assertAlmostEqual(targets["A"], 60.0, places=1)
        self.assertAlmostEqual(targets["ITC.NS"], 20.0, places=1)

    def test_targets_prefer_live_prices(self):
        stocks = [{"symbol": "ITC.NS", "shares": 100, "avg_cost": 200.0}]
        targets = de.default_targets_from_portfolio([], stocks,
                                                    prices={"ITC.NS": 400.0})
        self.assertEqual(targets["ITC.NS"], 100.0)

    def test_empty_portfolio_gives_no_targets(self):
        self.assertEqual(de.default_targets_from_portfolio([], []), {})


# ══════════════════════════════════════════════════════════════════════════
#  BOARD
# ══════════════════════════════════════════════════════════════════════════

class TestBuildBoard(unittest.TestCase):
    def test_empty_board_matches_populated_shape(self):
        populated = de.build_deploy_board([_cand("A", price=75.0, peak=100.0)],
                                          amount=10000)
        self.assertEqual(set(de.empty_board()), set(populated))

    def test_empty_board_is_safe(self):
        board = de.empty_board(20000)
        self.assertEqual(board["candidates"], [])
        self.assertEqual(board["suggestion"]["unallocated"], 20000.0)
        self.assertEqual(board["total_value"], 0.0)

    def test_total_value_is_derived_when_absent(self):
        board = de.build_deploy_board([
            _cand("A", value=60000.0), _cand("B", value=40000.0)])
        self.assertEqual(board["total_value"], 100000.0)

    def test_amount_zero_still_ranks(self):
        board = de.build_deploy_board([_cand("A", price=75.0, peak=100.0)],
                                      amount=0)
        self.assertEqual(len(board["candidates"]), 1)
        self.assertEqual(board["suggestion"]["allocations"], [])

    def test_needs_data_lists_missing_factors(self):
        board = de.build_deploy_board([
            _cand("A", price=75.0, peak=100.0, avg_cost=None,
                  target_pct=None, benchmark=None)])
        self.assertEqual(board["needs_data"][0]["key"], "A")
        self.assertIn(de.FACTOR_UNDERWEIGHT, board["needs_data"][0]["missing"])

    def test_alert_when_no_targets_configured(self):
        board = de.build_deploy_board([_cand("A", price=75.0, peak=100.0)])
        self.assertFalse(board["targets"]["configured"])
        self.assertTrue(any("target shares" in a["msg"] for a in board["alerts"]))

    def test_alert_when_targets_do_not_sum_to_100(self):
        board = de.build_deploy_board([
            _cand("A", target_pct=30.0, value=1000.0),
            _cand("B", target_pct=30.0, value=1000.0)])
        self.assertEqual(board["targets"]["sum_pct"], 60.0)
        self.assertIsNotNone(board["targets"]["warning"])

    def test_alert_on_overdue_legs(self):
        board = de.build_deploy_board(
            [_cand("A", price=75.0, peak=100.0)],
            legs=[_leg("A", due_day=1)],
            mf_portfolio=[_fund("A", [])],
            as_of=date(2026, 9, 20))
        self.assertTrue(any("overdue" in a["msg"] for a in board["alerts"]))

    def test_custom_weights_are_normalised_and_echoed(self):
        board = de.build_deploy_board([_cand("A", price=75.0, peak=100.0)],
                                      weights={de.FACTOR_OWN_DRAWDOWN: 5})
        self.assertAlmostEqual(sum(board["weights"].values()), 1.0, places=6)
        self.assertEqual(board["disclosure"]["weights"], board["weights"])

    def test_disclosure_states_no_broker_order(self):
        board = de.empty_board()
        self.assertIn("no broker order", board["disclosure"]["note"])

    def test_alloc_options_pass_through(self):
        """A floor above any achievable score must starve the suggestion."""
        cand = _cand("A", price=75.0, peak=100.0)
        allowed = de.build_deploy_board([cand], amount=20000)
        self.assertEqual(len(allowed["suggestion"]["allocations"]), 1)

        blocked = de.build_deploy_board([cand], amount=20000, score_floor=100.5)
        self.assertEqual(blocked["suggestion"]["allocations"], [])
        self.assertEqual(blocked["suggestion"]["skipped"][0]["skip_reason"],
                         "below_score_floor")
        self.assertEqual(blocked["disclosure"]["score_floor"], 100.5)


if __name__ == "__main__":
    unittest.main()
