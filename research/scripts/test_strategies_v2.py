"""Tests for S1-S10 on the verified rebalancing rig.

    python research/scripts/test_strategies_v2.py

`backtest_five_verified.Book.run` already asserts the accounting invariants on
every run — cash reconciles, distributions reconcile, quantities replay from
the audit trail, fills are official opens. Those are necessary and not
sufficient: they would all pass for a strategy that traded the wrong rule, and
they say nothing about whether the EXTENSION changed the five published
strategies it inherits.

These tests cover what the built-in assertions cannot:

  * the published five still produce their published numbers (the control that
    makes every new number trustworthy);
  * the new strategies differ from their incumbents in exactly the one way
    each is supposed to, and in no other;
  * the dividend sweep and the tax model conserve value rather than creating
    or destroying it;
  * results are deterministic and costs behave monotonically.

The run builds each book once and shares it, because a full Book.run over 3,891
sessions is not free and nothing here mutates a finished book.
"""
import sys
import unittest
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import backtest_strategies_v2 as v2  # noqa: E402
from backtest_five_verified import SYMS, Data  # noqa: E402

# The published five, from research/data/five_strategy_verified/results.json.
PUBLISHED = {1: 12.28, 2: 13.25, 3: 13.22, 4: 9.85, 5: 10.94}
ALL_CODES = range(1, 11)


class Rig:
    """One Data load and one pass of each book, shared by every test."""
    data = None
    pre = {}
    post = {}

    @classmethod
    def build(cls):
        if cls.data is not None:
            return
        cls.data = Data()
        for code in ALL_CODES:
            b = v2.Book2(cls.data, code)
            cls.pre[code] = (b, b.run())
            t = v2.Book2(cls.data, code, 12, after_tax=True)
            cls.post[code] = (t, t.run())


def setUpModule():
    Rig.build()


def logs(book, event):
    return [l for l in book.logs if l["event"] == event]


class ControlTestCase(unittest.TestCase):
    """The published five must come back unchanged, or nothing else counts."""

    def test_the_published_five_reproduce(self):
        for code, xirr in PUBLISHED.items():
            with self.subTest(code=code):
                self.assertAlmostEqual(Rig.pre[code][1]["xirr_pct"], xirr,
                                       places=2)

    def test_the_published_five_are_untouched_by_the_extension(self):
        # Codes 1-5 are delegated to the original `Book.review`. If the
        # override ever starts handling them, this catches it.
        self.assertEqual(v2.Book2.review.__qualname__, "Book2.review")
        for code in range(1, 6):
            with self.subTest(code=code):
                self.assertEqual(Rig.pre[code][1]["sells"],
                                 {1: 0, 2: 0, 3: 15, 4: 26, 5: 0}[code])

    def test_every_strategy_contributes_the_same_capital(self):
        # A strategy that quietly invested more would beat the rest on wealth
        # while being worse per rupee, and XIRR alone would not show it.
        for code in ALL_CODES:
            with self.subTest(code=code):
                self.assertEqual(Rig.pre[code][1]["invested"], 1600000)
                self.assertEqual(
                    len(logs(Rig.pre[code][0], "CONTRIBUTION")), 16)


class LedgerTestCase(unittest.TestCase):
    def test_cash_never_goes_negative(self):
        for code in ALL_CODES:
            with self.subTest(code=code):
                self.assertGreaterEqual(Rig.pre[code][1]["cash"], -1e-6)

    def test_share_counts_are_whole_numbers(self):
        for code in ALL_CODES:
            book = Rig.pre[code][0]
            with self.subTest(code=code):
                for s, lots in book.lots.items():
                    for l in lots:
                        self.assertEqual(l["q"], int(l["q"]), f"{s} {l}")
                        self.assertGreaterEqual(l["q"], 0)

    def test_every_fill_is_an_official_open(self):
        for code in ALL_CODES:
            book = Rig.pre[code][0]
            with self.subTest(code=code):
                for t in book.logs:
                    if t["event"] in ("BUY", "SELL"):
                        d = date.fromisoformat(t["date"])
                        self.assertEqual(
                            t["price"], Rig.data.p[d][t["symbol"]]["open"])

    def test_nothing_is_sold_before_it_is_long_term(self):
        # The rig's whole tax story depends on this: every sale is of units
        # held over a year, which is why LTCG is the only rate applied.
        for code in ALL_CODES:
            book = Rig.pre[code][0]
            with self.subTest(code=code):
                bought = defaultdict(list)
                for t in book.logs:
                    d = date.fromisoformat(t["date"])
                    if t["event"] == "BUY":
                        bought[t["symbol"]].append(d)
                    elif t["event"] == "SELL":
                        oldest = min(bought[t["symbol"]])
                        self.assertGreater(
                            (d - oldest).days, 365,
                            f"S{code} sold {t['symbol']} on {d}")

    def test_results_are_deterministic(self):
        # No RNG, no dict-ordering dependence, no wall clock.
        again = v2.Book2(Rig.data, 8).run()
        self.assertEqual(again["terminal_after_cost"],
                         Rig.pre[8][1]["terminal_after_cost"])


class NewStrategyTestCase(unittest.TestCase):
    """Each new strategy must differ from its incumbent in exactly one way."""

    def test_the_sweep_is_the_only_difference_between_s2_and_s6(self):
        s2, s6 = Rig.pre[2][0], Rig.pre[6][0]
        self.assertEqual(len(logs(s2, "DISTRIBUTION_REINVESTED")), 0)
        self.assertGreater(len(logs(s6, "DISTRIBUTION_REINVESTED")), 0)
        # Neither ever sells, so the extra wealth cannot come from trading.
        self.assertEqual(Rig.pre[2][1]["sells"], 0)
        self.assertEqual(Rig.pre[6][1]["sells"], 0)
        self.assertGreater(Rig.pre[6][1]["terminal_after_cost"],
                           Rig.pre[2][1]["terminal_after_cost"])

    def test_the_sweep_is_the_only_difference_between_s3_and_s8(self):
        s3, s8 = Rig.pre[3][0], Rig.pre[8][0]
        self.assertEqual(len(logs(s3, "DISTRIBUTION_REINVESTED")), 0)
        self.assertGreater(len(logs(s8, "DISTRIBUTION_REINVESTED")), 0)
        # Same trim rule, so the same trims fire — on a larger book.
        self.assertGreaterEqual(Rig.pre[8][1]["sells"], Rig.pre[3][1]["sells"])

    def test_a_swept_strategy_leaves_almost_nothing_idle(self):
        # Only dividends declared AFTER the final review can still be idle.
        for code in (6, 8, 10):
            book, res = Rig.pre[code]
            idle = res["dividends"] + res["ntpc_income"]
            with self.subTest(code=code):
                self.assertLess(idle, 0.25 * Rig.pre[3][1]["dividends"],
                                f"S{code} left {idle:,.0f} uninvested")

    def test_an_unswept_strategy_leaves_a_large_idle_pile(self):
        # The premise of the whole study.
        res = Rig.pre[3][1]
        idle = res["dividends"] + res["ntpc_income"]
        self.assertGreater(idle / res["terminal_after_cost"], 0.10)

    def test_the_wide_band_almost_never_fires(self):
        self.assertEqual(Rig.pre[7][1]["sells"], 1)

    def test_s10_collapses_onto_s6(self):
        # With dividends reinvested no weight reaches 20%, so S10's band is
        # inert and the two strategies are the same policy. Asserted because
        # it is reported as a finding, and a future change to either would
        # silently falsify it.
        self.assertEqual(Rig.pre[10][1]["terminal_after_cost"],
                         Rig.pre[6][1]["terminal_after_cost"])
        self.assertEqual(Rig.pre[10][1]["sells"], 0)

    def test_the_laggard_tilt_buys_only_three_names_a_year(self):
        buys = defaultdict(set)
        for t in logs(Rig.pre[9][0], "BUY"):
            buys[t["date"]].add(t["symbol"])
        # The first review is the common equal-weight start; after that the
        # tilt concentrates.
        later = sorted(buys)[1:]
        for d in later:
            self.assertLessEqual(len(buys[d]), 3, f"{d}: {buys[d]}")


class TaxTestCase(unittest.TestCase):
    def test_withholding_is_applied_at_source(self):
        # Asserted on the dividend STREAM, not on accumulated totals: an
        # after-tax book has less cash, so it buys fewer shares and collects
        # different dividends. Comparing end-of-run piles would conflate the
        # tax with that second-order effect.
        view = v2._NetDividends(Rig.data, v2.DIV_WITHHOLDING)
        checked = 0
        for when, items in Rig.data.divs.items():
            for (sym, gross), (sym2, net) in zip(items, view.divs[when]):
                self.assertEqual(sym, sym2)
                self.assertAlmostEqual(net, gross * (1 - v2.DIV_WITHHOLDING),
                                       places=9)
                checked += 1
        self.assertGreater(checked, 200)

    def test_every_strategy_sees_the_withheld_stream_not_just_the_sweepers(self):
        # The bug this guards against: taxing only the strategies that
        # reinvest, which would penalise reinvestment for being the only
        # policy that touches the money.
        for code in ALL_CODES:
            with self.subTest(code=code):
                self.assertIsInstance(Rig.post[code][0].data, v2._NetDividends)
                self.assertNotIsInstance(Rig.pre[code][0].data, v2._NetDividends)

    def test_a_non_trading_strategy_collects_exactly_the_net_dividend(self):
        # S1, S2, S5 and S9 never sell and never sweep, so their share counts
        # are identical with and without tax — which makes the ratio of their
        # dividend piles a clean read on the withholding alone.
        for code in (1, 2, 5, 9):
            with self.subTest(code=code):
                self.assertEqual(Rig.pre[code][1]["sells"], 0)
                self.assertAlmostEqual(
                    Rig.post[code][1]["dividends"] / Rig.pre[code][1]["dividends"],
                    1 - v2.DIV_WITHHOLDING, places=6)

    def test_tax_never_improves_a_strategy(self):
        for code in ALL_CODES:
            with self.subTest(code=code):
                self.assertLessEqual(Rig.post[code][1]["xirr_pct"],
                                     Rig.pre[code][1]["xirr_pct"] + 1e-9)

    def test_only_sellers_pay_capital_gains(self):
        for code in ALL_CODES:
            book, res = Rig.post[code]
            with self.subTest(code=code):
                if res["sells"] == 0:
                    self.assertEqual(book.ltcg_paid, 0.0)
                else:
                    self.assertGreater(book.ltcg_paid, 0.0)

    def test_capital_gains_are_charged_at_the_stated_rate(self):
        book = Rig.post[8][0]
        charged = 0.0
        for t in book.logs:
            if t["event"] == "SELL":
                # note carries "long-term gain Rs X, tax Rs Y at 12.5%"
                # Split on ", tax" rather than "," — the amounts carry
                # thousands separators, so a bare comma splits inside a number.
                gain = float(t["note"].split("long-term gain Rs ")[1]
                             .split(", tax")[0].replace(",", ""))
                tax = float(t["note"].split("tax Rs ")[1]
                            .split(" at")[0].replace(",", ""))
                self.assertAlmostEqual(tax, gain * v2.LTCG_RATE, delta=1.0)
                charged += tax
        self.assertAlmostEqual(charged, book.ltcg_paid, delta=len(SYMS))

    def test_the_trim_stops_paying_once_it_is_taxed(self):
        # The headline reversal. Pre-tax the trimming variant wins; after tax
        # it does not. If this ever flips, the write-up is wrong.
        self.assertGreater(Rig.pre[8][1]["xirr_pct"], Rig.pre[6][1]["xirr_pct"])
        self.assertLess(Rig.post[8][1]["xirr_pct"], Rig.post[6][1]["xirr_pct"])

    def test_the_winner_beats_s3_on_both_bases(self):
        for basis in (Rig.pre, Rig.post):
            self.assertGreater(basis[6][1]["xirr_pct"], basis[3][1]["xirr_pct"])


class CostTestCase(unittest.TestCase):
    def test_higher_costs_never_help_a_strategy_that_trades(self):
        for code in ALL_CODES:
            cheap = v2.Book2(Rig.data, code, 0).run()["terminal_after_cost"]
            dear = v2.Book2(Rig.data, code, 25).run()["terminal_after_cost"]
            with self.subTest(code=code):
                # S4 is the documented exception: its sells are rule-driven,
                # so a higher cost changes WHICH whole shares it can afford
                # and the path diverges rather than merely shrinking.
                if code == 4:
                    continue
                self.assertLessEqual(dear, cheap + 1e-6)

    def test_the_ranking_survives_the_cost_range(self):
        for bps in (0, 12, 25):
            top = max(ALL_CODES,
                      key=lambda c: v2.Book2(Rig.data, c, bps).run()["xirr_pct"])
            with self.subTest(bps=bps):
                self.assertIn(top, (6, 8, 10))


if __name__ == "__main__":
    unittest.main(verbosity=2)
