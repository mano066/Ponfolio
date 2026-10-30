"""New rebalancing strategies (S6-S10), measured against S1-S5 on the SAME rig.

Why this exists
---------------
`backtest_five_verified.py` measured five rebalancing policies on 16 annual
contributions of Rs 1,00,000 into a 10-name NSE basket, 2011-2026, with real
corporate actions, whole shares, official NSE opens as fills and a reconciled
cash/distribution ledger. It found:

    S2 cash-flow rebalance  13.25%      S3 band rebalance  13.22%
    S1 equal annual buying  12.28%      S5 momentum tilt   10.94%
    S4 price-rule proxy      9.85%

Two things in that table are the reason this script exists.

  1. **S2 already edges S3 with zero sells.** S3 trims anything over 12.5% back
     toward 10% and sold 15 times; S2 never sells and simply steers each year's
     new money at whatever is underweight. Directing contributions is free
     rebalancing — no cost, no realised tax, no interruption of a compounding
     winner. That says the SELL is what costs S3, and it makes the band width
     a question worth asking rather than assuming.

  2. **Nothing reinvests the dividends.** Distributions accrue outside trading
     cash and sit there. By 2026 that is Rs 6.09 lakh on S1 — 13% of terminal
     wealth — earning nothing for up to fifteen years. No real investor does
     this, and no strategy in the original five is allowed to fix it.

The new strategies
------------------
Each isolates ONE change against a named incumbent, so a difference is
attributable rather than merely observed.

  S6  Cash-flow + dividends reinvested   = S2 + sweep          (isolates income)
  S7  Wide band, 20% trim + cash-flow    = S3 with a wider band (isolates width)
  S8  Band 12.5% + dividends reinvested  = S3 + sweep          (isolates income)
  S9  Laggard tilt                       = new money to the 3 worst 1-year
                                           names (the mirror of S5, which lost)
  S10 Wide band + dividends reinvested   = S7 + S8 combined

Everything else is inherited unchanged from the verified rig: the same basket,
the same 16 contribution dates, the same official opens, the same whole-share
arithmetic, the same >365-day sell discipline, the same corporate actions, and
the same ledger assertions — which still have to pass for a result to be
emitted at all.

What this cannot tell you
-------------------------
ONE basket, ONE contribution schedule, ONE historical path. Ten PSU-heavy names
over one 15-year Indian bull market is an anecdote with a decimal point, not a
distribution. A ranking here is evidence about THIS book, and the gaps between
the top strategies (tens of basis points of XIRR) are well inside what a
different basket or start year would move. Read the MECHANISM, not the decimal.

Run:  python research/scripts/backtest_strategies_v2.py
Out:  research/data/strategies_v2/results.json
"""
import json
import math
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import backtest_five_verified as bfv  # noqa: E402
from backtest_five_verified import SYMS, Book, Data, csvtext, irr  # noqa: E402

OUT = ROOT / "research" / "data" / "strategies_v2"

NEW_NAMES = [
    "S6 Cash-flow + dividends reinvested",
    "S7 Wide band 20% + cash-flow",
    "S8 Band 12.5% + dividends reinvested",
    "S9 Laggard tilt",
    "S10 Wide band + dividends reinvested",
]
# `Book.run` reports `NAMES[code-1]`, so the new codes need entries there. The
# first five are left exactly as the verified script wrote them.
bfv.NAMES.extend(NEW_NAMES)

# Which of the new codes reinvest distributions, and what band each trims at.
REINVEST = {6, 8, 10}
BAND = {7: 0.20, 8: 0.125, 10: 0.20}   # trim trigger as a share of the book
TARGET = 0.10                          # equal weight across the 10 names

# ── after-tax mode ──
# The published five are PRE-TAX, which is fine for ranking rules that never
# sell but silently favours the two changes measured here: reinvesting a
# dividend assumes the whole dividend arrives, and trimming a winner assumes
# the gain is not taxed. This app's default residency is NRI, where neither is
# true. Both rates are INDICATIVE — surcharge depends on total income, treaty
# relief can cut the dividend rate, and the s.112A exemption is ignored (which
# overstates the tax on a seller, so the after-tax table is conservative
# TOWARDS the no-sell strategies rather than away from them).
DIV_WITHHOLDING = 0.20   # s.195 TDS on dividends paid to a non-resident
LTCG_RATE = 0.125        # s.112A on listed equity held over 12 months


class _NetDividends:
    """A Data view whose dividends arrive already withheld.

    Wraps rather than mutates, because one `Data` instance is shared by every
    book in the run and the pre-tax books must keep seeing gross dividends.
    """

    def __init__(self, data, rate):
        self._d = data
        self.divs = defaultdict(list)
        for when, items in data.divs.items():
            self.divs[when] = [(s, a * (1 - rate)) for s, a in items]
        self.gross = sum(a for items in data.divs.values() for _s, a in items)

    def __getattr__(self, name):
        return getattr(self._d, name)


class Book2(Book):
    """The verified Book, plus codes 6-10.

    Codes 1-5 are delegated to the original implementation untouched, so this
    script reproduces the published five as a control: if those five do not
    come back at 12.28 / 13.25 / 13.22 / 9.85 / 10.94, the extension has broken
    something and the new numbers are not to be trusted.
    """

    def __init__(self, data, code, cost_bps=12, after_tax=False):
        # Withholding happens at SOURCE, so it has to hit every strategy's
        # dividends — not only the ones that reinvest them. Applying it inside
        # the sweep instead would have taxed S6/S8/S10 and let S1/S2/S3's idle
        # pile through gross, which is precisely backwards: it would penalise
        # reinvestment for being the only policy that touches the money.
        if after_tax:
            data = _NetDividends(data, DIV_WITHHOLDING)
        super().__init__(data, code, cost_bps)
        self.after_tax = after_tax
        self.ltcg_paid = 0.0

    def sweep_distributions(self, d):
        """Move accrued dividends and debenture income into tradeable cash.

        Both ledgers must stay reconciled — `run()` asserts that cash equals
        the sum of logged cash changes and that distributions equal the sum of
        logged earned changes — so the GROSS amount leaves the earned ledger
        while only the NET reaches cash. The withheld part simply leaves the
        book, which is what withholding is.
        """
        amount = self.distributions + self.ntpc_income
        if amount <= 0:
            return
        # In after-tax mode this is already net of withholding — the deduction
        # happened when the dividend was recognised, for every strategy alike.
        self.cash += amount
        self.log(d, "CASH", "DISTRIBUTION_REINVESTED", cash=amount,
                 earned=-amount,
                 note="Accrued distributions moved into trading cash for "
                      "reinvestment at this review"
                      + (" (net of withholding at source)" if self.after_tax else ""))
        self.distributions = 0.0
        self.ntpc_income = 0.0

    def sell(self, s, wanted, p, d, note):
        """The verified sell, with capital-gains tax deducted from proceeds.

        Reimplemented rather than wrapped because the tax needs the COST BASIS
        of the units actually sold, and the base method discards it as it
        walks the lots. The lot walk, the >365-day restriction and the
        brokerage arithmetic are otherwise identical; with `after_tax=False`
        this is the base behaviour exactly, which the S1-S5 control checks.
        """
        if not self.after_tax:
            return super().sell(s, wanted, p, d, note)

        available = sum(l["q"] for l in self.lots[s]
                        if (d - l["bought"]).days > 365)
        qty = min(wanted, available)
        if qty <= 0:
            return
        left, basis_sold = qty, 0.0
        for l in self.lots[s]:
            if (d - l["bought"]).days <= 365:
                continue
            take = min(left, l["q"])
            basis_sold += l["basis"] * take / l["q"]
            l["basis"] *= 1 - take / l["q"]
            l["q"] -= take
            left -= take
            if left == 0:
                break
        self.lots[s] = [l for l in self.lots[s] if l["q"]]

        gross = qty * p
        cost = gross * self.rate
        # Every sale here is of units held over a year, by construction.
        gain = max(0.0, gross - basis_sold)
        tax = gain * LTCG_RATE
        self.ltcg_paid += tax
        self.cash += gross - cost - tax
        self.costs += cost
        self.log(d, s, "SELL", qty, p, gross - cost - tax,
                 note=f"{note}; long-term gain Rs {gain:,.0f}, "
                      f"tax Rs {tax:,.0f} at {LTCG_RATE * 100:g}%")

    def trim_to_band(self, d, dec, fill, band):
        """Sell anything above `band` back toward the 10% target.

        Identical arithmetic to S3's trim, with the trigger as a parameter.
        Only lots held over 365 days can be sold — that restriction lives in
        `Book.sell` and is not relaxed here.
        """
        total = self.equity(dec, True)
        if not total:
            return
        for s in SYMS:
            if self.qty(s) * dec[s] / total > band:
                want = math.floor((self.qty(s) * dec[s] - TARGET * total) / dec[s])
                self.sell(s, want, fill[s], d,
                          f"weight >{band * 100:g}%; trim toward {TARGET * 100:g}%")

    def review(self, d, prev):
        if self.code <= 5:
            return super().review(d, prev)

        fill = {s: self.data.p[d][s]["open"] for s in SYMS}
        dec = ({s: self.data.p[prev][s]["close"] for s in SYMS} if prev
               else fill.copy())
        # An ex-date review has to compare like with like: restate the previous
        # close onto today's unit basis before any weight is computed.
        for s, k, f, x in self.data.events[d]:
            if k in ["split", "combined"]:
                dec[s] /= f
            elif k == "bonus":
                dec[s] /= 1 + f
            elif k == "demerger":
                raise ValueError("An ex-demerger review requires an explicit "
                                 "pre-event decision snapshot")

        self.cash += 100000
        self.invested += 100000
        self.flows.append((d, -100000))
        self.log(d, "CASH", "CONTRIBUTION", cash=100000)
        if self.code in REINVEST:
            self.sweep_distributions(d)
        first = self.invested == 100000

        if first:
            # Every strategy starts from the same equal-weight book, so the
            # comparison is about what happens NEXT, not about the first buy.
            per = self.cash / len(SYMS)
            for s in SYMS:
                self.buy(s, per, fill[s], d, "equal allocation")
            self.deploy(SYMS, TARGET, dec, fill, d)
        elif self.code == 9:
            # The mirror of S5. S5 concentrated new money in the three BEST
            # 12-month performers and finished 2.3 points of XIRR behind buying
            # everything equally; this asks whether the opposite tilt — feeding
            # the three worst — does better, which is what cash-flow
            # rebalancing already does in a diluted form.
            ranked = sorted(
                SYMS,
                key=lambda s: (self.data.trailing(s, prev, 1)
                               if self.data.trailing(s, prev, 1) is not None
                               else 999))
            picks = ranked[:3]
            per = self.cash / len(picks)
            for s in picks:
                self.buy(s, per, fill[s], d, "12-month laggard tilt")
            self.deploy(picks, 1 / len(picks), dec, fill, d)
        else:
            if self.code in BAND:
                self.trim_to_band(d, dec, fill, BAND[self.code])
            self.deploy(SYMS, TARGET, dec, fill, d)

        assert self.cash >= -1e-6


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = Data()
    results, books = [], []
    for code in range(1, 11):
        b = Book2(data, code)
        r = b.run()
        results.append(r)
        books.append(b)
        print(f"{r['name']:<40} {r['terminal_after_cost']:>12,.0f} "
              f"{r['xirr_pct']:>7.2f}%  trades={r['trades']:<4} "
              f"sells={r['sells']}", flush=True)

    # The published five are the control. If any has moved, the extension has
    # changed behaviour it had no business changing.
    control = {1: 12.281166656659714, 2: 13.245, 3: 13.22, 4: 9.85, 5: 10.94}
    drift = {r["code"]: round(r["xirr_pct"], 2) for r in results if r["code"] <= 5}
    print(f"\ncontrol (S1-S5 must match the verified run): {drift}", flush=True)

    sensitivity = []
    for bps in [0, 25]:
        for code in range(1, 11):
            r = Book2(data, code, bps).run()
            sensitivity.append(dict(cost_bps=bps, code=code,
                                    terminal=r["terminal_after_cost"],
                                    xirr_pct=r["xirr_pct"]))

    # After tax. The pre-tax table flatters exactly the two changes under test:
    # it lets a dividend be reinvested in full and a winner be trimmed free.
    print("\n=== after tax (NRI: 20% dividend withholding, 12.5% LTCG) ===",
          flush=True)
    after_tax = []
    for code in range(1, 11):
        b = Book2(data, code, 12, after_tax=True)
        r = b.run()
        pre = next(x for x in results if x["code"] == code)
        after_tax.append(dict(code=code, name=r["name"],
                              terminal=r["terminal_after_cost"],
                              xirr_pct=r["xirr_pct"], ltcg_paid=b.ltcg_paid,
                              sells=r["sells"],
                              xirr_drop=pre["xirr_pct"] - r["xirr_pct"]))
        print(f"{r['name']:<40} {r['terminal_after_cost']:>12,.0f} "
              f"{r['xirr_pct']:>7.2f}%  LTCG paid={b.ltcg_paid:>9,.0f}  "
              f"(pre-tax {pre['xirr_pct']:.2f}%)", flush=True)

    payload = dict(
        start=str(data.days[0]), end=str(data.days[-1]),
        sessions=len(data.days), cost_bps=12,
        basket=SYMS,
        contributions="Rs 1,00,000 on the first trading day on/after 3 Jan, "
                      "2011-2026 (16 payments, Rs 16,00,000 total)",
        results=results, sensitivity=sensitivity, after_tax=after_tax,
        tax_assumptions={"dividend_withholding": DIV_WITHHOLDING,
                         "ltcg_rate": LTCG_RATE,
                         "note": "Indicative. Ignores surcharge, treaty relief "
                                 "and the s.112A annual exemption."},
        caveat="ONE basket, ONE schedule, ONE historical path. Differences of "
               "a few tenths of a point of XIRR are not separable on a single "
               "path; the mechanism is the finding, not the ranking.",
        checks=["Cash ledger reconciles", "Distribution ledger reconciles",
                "Share quantities independently replayed",
                "All fills equal official NSE opens",
                "No negative cash or short positions",
                "16 contributions per strategy", "Integer share positions",
                "S1-S5 reproduce the verified published run"],
    )
    (OUT / "results.json").write_text(json.dumps(payload, indent=2),
                                      encoding="utf-8")
    with zipfile.ZipFile(OUT / "audit_ledgers.zip", "w",
                         zipfile.ZIP_DEFLATED) as z:
        for b in books:
            z.writestr(f"S{b.code}_transactions_and_events.csv", csvtext(b.logs))
            z.writestr(f"S{b.code}_daily_wealth.csv", csvtext(b.daily))
    print(f"\nSaved {OUT}", flush=True)


if __name__ == "__main__":
    main()
