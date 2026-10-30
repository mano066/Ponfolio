"""S1-S10 on a MONTHLY Rs 10,000 SIP, 2011-01 to the last session on file.

The published study and its S6-S10 extension both contribute Rs 1,00,000 once a
year. That is not how anyone actually invests, and the schedule is not
incidental to the result: a strategy whose whole mechanism is "steer the
contribution at whatever is underweight" gets sixteen chances to do it annually
and nearly two hundred monthly. Averaging in twelve times as often also removes
most of the luck in WHEN the money landed, which on a single historical path is
a real part of the annual study's noise.

So this re-runs every one of the ten strategies against:

    Rs 10,000 on the first trading day on/after the 1st of each month,
    2011-01 through the last session in the verified price file,
    into the same ten-name NSE basket.

Everything else is inherited from the verified rig and is NOT re-implemented
here: official NSE opens as fills, whole shares only, real corporate actions,
the 365-day restriction on what may be sold, 12 bps costs, the reconciled cash
and distribution ledgers, and the independent replay of every share quantity
from the audit trail. The strategy rules are the same objects the annual study
uses — only the calendar and the ticket size change.

What changes in character, and is reported rather than hidden:

  * The band strategies (S3, S7, S8, S10) now test their trim ~189 times
    instead of 16. A band rule evaluated monthly is a more active policy than
    the same rule evaluated annually, and the sell counts show it.
  * The tilts (S5, S9) re-pick their three names every month rather than once
    a year.
  * Rs 10,000 split ten ways is Rs 1,000 a name, which buys whole shares of a
    Rs 1,100 stock badly. The residual sweep in `deploy` mops up what integer
    share counts leave behind, exactly as it does annually.

    python research/scripts/backtest_strategies_monthly.py

Out: research/data/strategies_monthly/results.json
"""
import bisect
import json
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import backtest_strategies_v2 as v2  # noqa: E402
from backtest_five_verified import SYMS, Data, csvtext, irr  # noqa: E402

OUT = ROOT / "research" / "data" / "strategies_monthly"

CONTRIB = 10000          # rupees per month
START = date(2011, 1, 1)


class MonthlyData:
    """A Data view whose review calendar is monthly rather than annual.

    Wraps rather than mutates: one `Data` is shared by every book in the run,
    and `_NetDividends` may already be wrapping it for the after-tax pass.
    Both delegate unknown attributes, so the two compose in either order.
    """

    def __init__(self, data, start=START, months=None):
        # `months` selects which months carry a contribution. All twelve is the
        # SIP; (1,) reproduces an annual calendar, which is what makes an
        # out-of-design check on a different cadence possible at all.
        self._d = data
        self.review = {}
        last = data.days[-1]
        for y in range(start.year, last.year + 1):
            for m in (months or range(1, 13)):
                first = date(y, m, 1)
                if first < start or first > last:
                    continue
                i = bisect.bisect_left(data.days, first)
                if i < len(data.days):
                    self.review[data.days[i]] = (y, m)

    def __getattr__(self, name):
        return getattr(self._d, name)


class MonthlyBook(v2.Book2):
    """Book2 on the monthly calendar.

    `run` is overridden rather than reused because the inherited one asserts
    the annual study's shape — exactly 16 contributions totalling Rs 16,00,000.
    Every OTHER assertion it makes is kept verbatim, including the ones that
    actually protect the result: the cash ledger, the distribution ledger, the
    independent quantity replay, and that every fill is an official open.
    """

    def __init__(self, data, code, cost_bps=12, after_tax=False, months=None,
                 start=None):
        if after_tax:
            data = v2._NetDividends(data, v2.DIV_WITHHOLDING)
        # Skip Book2.__init__'s own wrapping — it would double-withhold.
        super(v2.Book2, self).__init__(
            MonthlyData(data, start=start or START, months=months),
            code, cost_bps)
        self.after_tax = after_tax
        self.ltcg_paid = 0.0
        self.reviews = []          # one row per monthly review
        self.year_end = []         # last review of each calendar year

    def contribute(self, d):
        # Instance-level so a single process can run more than one calendar;
        # defaults to the module ticket, which is what the SIP study uses.
        amount = getattr(self, "ticket", CONTRIB)
        self.cash += amount
        self.invested += amount
        self.flows.append((d, -amount))
        self.log(d, "CASH", "CONTRIBUTION", cash=amount)

    def review(self, d, prev):
        """The annual `review`, with a monthly ticket.

        `Book.review` and `Book2.review` hard-code the Rs 1,00,000
        contribution and the "is this the first one" test against it, so the
        contribution is booked here and those methods are entered with the cash
        already in place.
        """
        fill = {s: self.data.p[d][s]["open"] for s in SYMS}
        dec = ({s: self.data.p[prev][s]["close"] for s in SYMS} if prev
               else fill.copy())
        for s, k, f, x in self.data.events[d]:
            if k in ("split", "combined"):
                dec[s] /= f
            elif k == "bonus":
                dec[s] /= 1 + f
            elif k == "demerger":
                raise ValueError("An ex-demerger review requires an explicit "
                                 "pre-event decision snapshot")

        self.contribute(d)
        if self.code in v2.REINVEST:
            self.sweep_distributions(d)
        first = self.invested == getattr(self, "ticket", CONTRIB)

        if first:
            per = self.cash / len(SYMS)
            for s in SYMS:
                self.buy(s, per, fill[s], d, "equal allocation")
            self.deploy(SYMS, v2.TARGET, dec, fill, d)
        elif self.code == 1:
            per = self.cash / len(SYMS)
            for s in SYMS:
                self.buy(s, per, fill[s], d, "equal allocation")
            self.deploy(SYMS, v2.TARGET, dec, fill, d)
        elif self.code in (5, 9):
            # S5 takes the three strongest twelve-month names, S9 the three
            # weakest. `trailing` returns None before a year of history, which
            # sorts to the far end rather than crashing.
            best = self.code == 5
            ranked = sorted(
                SYMS,
                key=lambda s: (self.data.trailing(s, prev, 1)
                               if self.data.trailing(s, prev, 1) is not None
                               else (-999 if best else 999)),
                reverse=best)
            picks = ranked[:3]
            per = self.cash / len(picks)
            for s in picks:
                self.buy(s, per, fill[s], d,
                         "12-month price momentum" if best
                         else "12-month laggard tilt")
            self.deploy(picks, 1 / len(picks), dec, fill, d)
        elif self.code == 4:
            total = self.equity(dec, True)
            blocked = set()
            for s in SYMS:
                cagr = self.data.trailing(s, prev, 5)
                basis, q = self.basis(s), self.qty(s)
                ret = q * dec[s] / basis - 1 if basis else 0
                if cagr is not None and cagr < 0 and q:
                    self.sell(s, q, fill[s], d,
                              "negative 5-year split/bonus price CAGR")
                    blocked.add(s)
                elif ret > 1 and total and q * dec[s] / total > .1:
                    self.sell(s, (q * dec[s] - .1 * total) // dec[s], fill[s],
                              d, "gain >100%; trim overweight")
            adds = [s for s in SYMS if s not in blocked
                    and (not self.basis(s)
                         or self.qty(s) * dec[s] / self.basis(s) >= .9)]
            if not adds:
                adds = [s for s in SYMS if s not in blocked] or SYMS[:]
            adds.sort(key=lambda s: self.data.trailing(s, prev, 1) or 0)
            self.deploy(adds, 1 / len(adds), dec, fill, d)
        else:
            if self.code in v2.BAND:
                self.trim_to_band(d, dec, fill, v2.BAND[self.code])
            elif self.code == 3:
                self.trim_to_band(d, dec, fill, 0.125)
            self.deploy(SYMS, v2.TARGET, dec, fill, d)

        assert self.cash >= -1e-6

    def run(self):
        days = self.data.days
        previous = None
        d = days[0]
        while d <= days[-1]:
            for s, amount in self.data.divs[d]:
                earned = self.qty(s) * amount
                if earned:
                    self.distributions += earned
                    self.log(d, s, "DIVIDEND_EARNED", self.qty(s), amount,
                             earned=earned, note="entitlement; not payment date")
            for s, k, f, x in self.data.events[d]:
                self.event(d, s, k, f, x)
            if (self.ntpc_units and d.month == 3 and d.day == 25
                    and 2016 <= d.year <= 2025):
                principal = 12.5 if d.year <= 2023 else 10 if d.year == 2024 else 5
                redemption = 2.5 if d.year == 2023 else 5 if d.year >= 2024 else 0
                earned = self.ntpc_units * (principal * .0849 + redemption)
                self.ntpc_income += earned
                self.log(d, "NTPC_NCD", "SCHEDULED_DEBT_INCOME",
                         self.ntpc_units, earned=earned,
                         note="Issuer schedule; coupon plus principal")
            if d in self.data.p:
                self.last.update({s: r["close"] for s, r in self.data.p[d].items()})
            if d in self.data.review:
                self.review(d, previous)
            if d in self.data.days:
                equity = self.equity(self.last)
                wealth = equity + self.cash + self.distributions + self.ntpc_income
                row = dict(date=str(d), invested=self.invested, equity=equity,
                           cash=self.cash, dividends_earned=self.distributions,
                           ntpc_scheduled_income=self.ntpc_income, wealth=wealth)
                self.daily.append(row)
                if d in self.data.review:
                    self.reviews.append(dict(
                        row, holdings={s: self.qty(s)
                                       for s in SYMS + ["ITCHOTELS", "SCILAL"]}))
                previous = d
            d += timedelta(days=1)

        end = days[-1]
        equity = self.equity(self.last)
        wealth = equity + self.cash + self.distributions + self.ntpc_income
        exitcost = equity * self.rate
        terminal = wealth - exitcost

        # Every invariant the verified rig checks, minus the two that encode
        # the annual study's shape.
        assert abs(self.cash - sum(x["cash_change"] for x in self.logs)) < 1e-4
        assert abs(self.distributions + self.ntpc_income
                   - sum(x["earned_change"] for x in self.logs)) < 1e-4
        assert all(l["q"] == int(l["q"]) and l["q"] >= 0 and l["basis"] >= -1e-8
                   for ls in self.lots.values() for l in ls)
        assert self.invested == getattr(self, "ticket", CONTRIB) * len(self.reviews)
        qty = defaultdict(float)
        for t in self.logs:
            if t["event"] in ("BUY", "SPLIT", "BONUS", "DEMERGER"):
                qty[t["symbol"]] += t["quantity"]
            if t["event"] == "SELL":
                qty[t["symbol"]] -= t["quantity"]
        assert all(abs(qty[s] - self.qty(s)) < 1e-8 for s in self.lots)
        trades = [x for x in self.logs if x["event"] in ("BUY", "SELL")]
        for t in trades:
            assert t["price"] == self.data.p[date.fromisoformat(t["date"])][
                t["symbol"]]["open"]

        # One snapshot per calendar year, for the ledger report.
        by_year = {}
        for r in self.reviews:
            by_year[r["date"][:4]] = r
        self.year_end = [by_year[k] for k in sorted(by_year)]

        return dict(
            code=self.code, name=v2.bfv.NAMES[self.code - 1],
            invested=self.invested, equity=equity, cash=self.cash,
            dividends=self.distributions, ntpc_income=self.ntpc_income,
            wealth=wealth, exit_cost=exitcost, terminal_after_cost=terminal,
            xirr_pct=irr(self.flows + [(end, terminal)]), costs=self.costs,
            trades=len(trades), sells=sum(t["event"] == "SELL" for t in trades),
            contributions=len(self.reviews), annual=self.year_end,
            holdings=[dict(symbol=s, quantity=self.qty(s),
                           close=self.last.get(s, 0),
                           value=self.qty(s) * self.last.get(s, 0))
                      for s in SYMS + ["ITCHOTELS", "SCILAL"]],
            fractions=self.fractions)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = Data()
    results, books = [], []
    print(f"monthly Rs {CONTRIB:,} SIP, {START} to {data.days[-1]}\n")
    for code in range(1, 11):
        b = MonthlyBook(data, code)
        r = b.run()
        results.append(r)
        books.append(b)
        print(f"{r['name']:<40} {r['terminal_after_cost']:>13,.0f} "
              f"{r['xirr_pct']:>7.2f}%  buys={r['trades'] - r['sells']:<5} "
              f"sells={r['sells']}", flush=True)

    print("\n=== after tax (NRI: 20% dividend withholding, 12.5% LTCG) ===")
    after_tax = []
    for code in range(1, 11):
        b = MonthlyBook(data, code, 12, after_tax=True)
        r = b.run()
        pre = next(x for x in results if x["code"] == code)
        after_tax.append(dict(code=code, name=r["name"],
                              terminal=r["terminal_after_cost"],
                              xirr_pct=r["xirr_pct"], ltcg_paid=b.ltcg_paid,
                              sells=r["sells"],
                              xirr_drop=pre["xirr_pct"] - r["xirr_pct"]))
        print(f"{r['name']:<40} {r['terminal_after_cost']:>13,.0f} "
              f"{r['xirr_pct']:>7.2f}%  LTCG={b.ltcg_paid:>10,.0f}", flush=True)

    sensitivity = []
    for bps in (0, 25):
        for code in range(1, 11):
            r = MonthlyBook(data, code, bps).run()
            sensitivity.append(dict(cost_bps=bps, code=code,
                                    terminal=r["terminal_after_cost"],
                                    xirr_pct=r["xirr_pct"]))

    n = results[0]["contributions"]
    payload = dict(
        schedule=f"Rs {CONTRIB:,} on the first trading day on/after the 1st of "
                 f"each month, {START} to {data.days[-1]} "
                 f"({n} payments, Rs {CONTRIB * n:,} total)",
        start=str(data.days[0]), end=str(data.days[-1]),
        sessions=len(data.days), cost_bps=12, contributions=n,
        contribution_amount=CONTRIB, basket=SYMS,
        results=results, after_tax=after_tax, sensitivity=sensitivity,
        tax_assumptions={"dividend_withholding": v2.DIV_WITHHOLDING,
                         "ltcg_rate": v2.LTCG_RATE,
                         "note": "Indicative. Ignores surcharge, treaty relief "
                                 "and the s.112A annual exemption."},
        caveat="ONE basket, ONE schedule, ONE historical path. A monthly "
               "schedule removes much of the timing luck in the annual study "
               "but adds none of the breadth: it is still ten PSU-heavy names "
               "through a single Indian bull market.",
        checks=["Cash ledger reconciles", "Distribution ledger reconciles",
                "Share quantities independently replayed",
                "All fills equal official NSE opens",
                "No negative cash or short positions",
                "Integer share positions",
                f"{n} contributions of Rs {CONTRIB:,} per strategy"],
    )
    (OUT / "results.json").write_text(json.dumps(payload, indent=2),
                                      encoding="utf-8")
    with zipfile.ZipFile(OUT / "audit_ledgers.zip", "w",
                         zipfile.ZIP_DEFLATED) as z:
        for b in books:
            z.writestr(f"S{b.code}_transactions_and_events.csv", csvtext(b.logs))
            z.writestr(f"S{b.code}_monthly_reviews.csv", csvtext(
                [{k: v for k, v in r.items() if k != "holdings"}
                 for r in b.reviews]))
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
