"""Tests for the monthly Rs 10,000 SIP run of S1-S10.

    python research/scripts/test_strategies_monthly.py

`MonthlyBook.run` re-implements the verified run loop in order to drop the two
assertions that encode the ANNUAL study's shape (exactly 16 contributions of
Rs 1,00,000). Re-implementing a verified loop is the risky part of this whole
exercise, so these tests exist mainly to prove that nothing ELSE was dropped
with them: the ledgers must still reconcile, the quantities must still replay
from the audit trail, and every fill must still be an official NSE open.

They also pin the things specific to a monthly schedule — the contribution
calendar itself, and the fact that a band rule evaluated 189 times is a more
active policy than the same rule evaluated 16 times.
"""
import sys
import unittest
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import backtest_strategies_monthly as mo  # noqa: E402
import backtest_strategies_v2 as v2  # noqa: E402
from backtest_five_verified import SYMS, Data  # noqa: E402

ALL_CODES = range(1, 11)


class Rig:
    data = None
    pre = {}
    post = {}

    @classmethod
    def build(cls):
        if cls.data is not None:
            return
        cls.data = Data()
        for code in ALL_CODES:
            b = mo.MonthlyBook(cls.data, code)
            cls.pre[code] = (b, b.run())
            t = mo.MonthlyBook(cls.data, code, 12, after_tax=True)
            cls.post[code] = (t, t.run())


def setUpModule():
    Rig.build()


class ScheduleTestCase(unittest.TestCase):
    def test_one_contribution_per_month_with_no_gaps(self):
        book = Rig.pre[1][0]
        months = [(int(r["date"][:4]), int(r["date"][5:7]))
                  for r in book.reviews]
        self.assertEqual(len(months), len(set(months)), "a month paid twice")
        # Consecutive, start to finish — a skipped month would quietly reduce
        # invested capital and flatter every XIRR in the study.
        for (y1, m1), (y2, m2) in zip(months, months[1:]):
            self.assertEqual((y2, m2),
                             (y1 + 1, 1) if m1 == 12 else (y1, m1 + 1))
        self.assertEqual(months[0], (2011, 1))

    def test_every_strategy_invests_the_same_capital(self):
        n = Rig.pre[1][1]["contributions"]
        for code in ALL_CODES:
            with self.subTest(code=code):
                self.assertEqual(Rig.pre[code][1]["contributions"], n)
                self.assertEqual(Rig.pre[code][1]["invested"], mo.CONTRIB * n)

    def test_the_schedule_is_monthly_not_annual(self):
        self.assertGreater(Rig.pre[1][1]["contributions"], 180)
        self.assertEqual(mo.CONTRIB, 10000)

    def test_contributions_are_all_on_trading_days(self):
        book = Rig.pre[1][0]
        for r in book.reviews:
            self.assertIn(date.fromisoformat(r["date"]), Rig.data.p)


class LedgerTestCase(unittest.TestCase):
    """The invariants the re-implemented run loop must not have lost."""

    def test_cash_ledger_reconciles(self):
        for code in ALL_CODES:
            book = Rig.pre[code][0]
            with self.subTest(code=code):
                self.assertAlmostEqual(
                    book.cash, sum(x["cash_change"] for x in book.logs),
                    places=4)

    def test_distribution_ledger_reconciles(self):
        for code in ALL_CODES:
            book = Rig.pre[code][0]
            with self.subTest(code=code):
                self.assertAlmostEqual(
                    book.distributions + book.ntpc_income,
                    sum(x["earned_change"] for x in book.logs), places=4)

    def test_quantities_replay_from_the_audit_trail(self):
        for code in ALL_CODES:
            book = Rig.pre[code][0]
            qty = defaultdict(float)
            for t in book.logs:
                if t["event"] in ("BUY", "SPLIT", "BONUS", "DEMERGER"):
                    qty[t["symbol"]] += t["quantity"]
                elif t["event"] == "SELL":
                    qty[t["symbol"]] -= t["quantity"]
            with self.subTest(code=code):
                for s in book.lots:
                    self.assertAlmostEqual(qty[s], book.qty(s), places=6)

    def test_every_fill_is_an_official_open(self):
        for code in ALL_CODES:
            book = Rig.pre[code][0]
            with self.subTest(code=code):
                for t in book.logs:
                    if t["event"] in ("BUY", "SELL"):
                        d = date.fromisoformat(t["date"])
                        self.assertEqual(
                            t["price"], Rig.data.p[d][t["symbol"]]["open"])

    def test_cash_never_goes_negative_and_shares_stay_whole(self):
        for code in ALL_CODES:
            book, res = Rig.pre[code]
            with self.subTest(code=code):
                self.assertGreaterEqual(res["cash"], -1e-6)
                for lots in book.lots.values():
                    for l in lots:
                        self.assertEqual(l["q"], int(l["q"]))
                        self.assertGreaterEqual(l["q"], 0)

    def test_nothing_is_sold_before_it_is_long_term(self):
        for code in ALL_CODES:
            book = Rig.pre[code][0]
            bought = defaultdict(list)
            with self.subTest(code=code):
                for t in book.logs:
                    d = date.fromisoformat(t["date"])
                    if t["event"] == "BUY":
                        bought[t["symbol"]].append(d)
                    elif t["event"] == "SELL":
                        self.assertGreater(
                            (d - min(bought[t["symbol"]])).days, 365)

    def test_results_are_deterministic(self):
        again = mo.MonthlyBook(Rig.data, 6).run()
        self.assertEqual(again["terminal_after_cost"],
                         Rig.pre[6][1]["terminal_after_cost"])


class CadenceTestCase(unittest.TestCase):
    def test_a_band_evaluated_monthly_trades_more_than_one_evaluated_yearly(self):
        # Not a defect — a consequence, and one the write-up has to state.
        import json
        annual = json.loads(
            (ROOT / "research/data/strategies_v2/results.json")
            .read_text(encoding="utf-8"))
        ann = {x["code"]: x for x in annual["results"]}
        for code in (3, 8):
            with self.subTest(code=code):
                self.assertGreater(Rig.pre[code][1]["sells"],
                                   ann[code]["sells"])

    def test_the_no_sell_strategies_still_never_sell(self):
        for code in (1, 2, 5, 6, 9):
            with self.subTest(code=code):
                self.assertEqual(Rig.pre[code][1]["sells"], 0)

    def test_the_wide_band_no_longer_rests_on_a_single_trade(self):
        # In the annual study S7's entire edge was ONE Tata Steel trim. On the
        # monthly calendar it fires on three separate dates in two different
        # names, which weakens that objection without retiring it — three
        # trades is still too few to call the 20% band demonstrated.
        book = Rig.pre[7][0]
        sells = [t for t in book.logs if t["event"] == "SELL"]
        self.assertGreaterEqual(len(sells), 3)
        self.assertGreaterEqual(len({t["date"] for t in sells}), 3)
        self.assertGreaterEqual(len({t["symbol"] for t in sells}), 2)


class FindingsTestCase(unittest.TestCase):
    """The claims the write-up makes, pinned so a rerun cannot quietly break them."""

    def test_reinvesting_dividends_still_wins(self):
        for plain, swept in ((2, 6), (3, 8), (7, 10)):
            with self.subTest(pair=(plain, swept)):
                self.assertGreater(Rig.post[swept][1]["xirr_pct"],
                                   Rig.post[plain][1]["xirr_pct"])

    def test_the_narrow_trim_still_costs_after_tax(self):
        # S8 (12.5% band) vs S6 (no band), both reinvesting.
        self.assertGreater(Rig.pre[8][1]["xirr_pct"], Rig.pre[6][1]["xirr_pct"])
        self.assertLess(Rig.post[8][1]["xirr_pct"], Rig.post[6][1]["xirr_pct"])

    def test_the_winner_beats_s3_on_both_bases(self):
        for basis in (Rig.pre, Rig.post):
            best = max(basis[c][1]["xirr_pct"] for c in ALL_CODES)
            self.assertGreater(best, basis[3][1]["xirr_pct"])

    def test_only_sellers_pay_capital_gains(self):
        for code in ALL_CODES:
            book, res = Rig.post[code]
            with self.subTest(code=code):
                self.assertEqual(book.ltcg_paid == 0, res["sells"] == 0)

    def test_tax_never_improves_a_strategy(self):
        for code in ALL_CODES:
            with self.subTest(code=code):
                self.assertLessEqual(Rig.post[code][1]["xirr_pct"],
                                     Rig.pre[code][1]["xirr_pct"] + 1e-9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
