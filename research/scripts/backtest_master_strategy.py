"""A master strategy assembled from the mechanisms S1-S10 actually established.

The honest problem with a "master" strategy
-------------------------------------------
Every ingredient below was chosen because it won on THIS data. That is the
definition of overfitting, and no amount of care in the implementation fixes
it. What can be done is to (a) build only from effects that were measured more
than once, against different baselines, so the ingredient list is not a list of
flukes; (b) refuse ingredients whose evidence was thin even though they won;
and (c) test the result on a contribution schedule it was NOT designed against.
All three are done here, and the failures are reported alongside the wins.

What the ten strategies established
-----------------------------------
  KEPT — reinvest distributions. Measured three times on the monthly schedule
    (S2 to S6, S3 to S8, S7 to S10) and twice on the annual one, same sign and
    similar size every time. The largest single effect in the whole study.

  KEPT — do not trim narrowly. A 12.5% ceiling wins before tax and loses after
    it, on both schedules (S8 beats S6 pre-tax, loses post-tax). The trim is
    paid for in realised capital gains.

  KEPT — feed the laggards. On the monthly schedule S9's laggard tilt beat
    plain cash-flow rebalancing (14.99 vs 14.20 after tax) while S5's momentum
    tilt lost badly (11.27). The direction replicates the weaker version of the
    same idea: S2 already buys whatever is underweight, which is usually what
    has lagged.

  REJECTED — the 20% band. S10 beats S6 by 0.15 points monthly, on three
    trades. Three trades is not evidence, and the annual schedule could not
    separate them at all. A ceiling is kept anyway, but as RISK CONTROL at a
    level that almost never binds, not as a return-seeking rule.

  REJECTED — concentrating the contribution. Both tilts that bought only three
    names lost to spreading on the annual schedule. S9's monthly win is not
    enough to overturn that, so the master tilts the ORDER of deployment
    without restricting the NUMBER of names.

The master
----------
  M1  sweep distributions; trim only above 25%; deploy every rupee at the
      underweights, ordered by weakest twelve-month price change first.

Two controls are run beside it so its parts can be attributed rather than
assumed:

  M2  the same, but deployment ordered by largest rupee gap (this is S10's
      deployment rule). Isolates the laggard ordering.
  M3  the same as M1, but with no ceiling at all. Isolates the trim.

    python research/scripts/backtest_master_strategy.py

Out: research/data/strategies_master/results.json
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import backtest_strategies_v2 as v2  # noqa: E402
import backtest_strategies_monthly as mo  # noqa: E402
from backtest_five_verified import SYMS, Data, csvtext  # noqa: E402

OUT = ROOT / "research" / "data" / "strategies_master"

MASTER_NAMES = {
    11: "M1 Master (sweep + laggard-ordered deploy + 25% cap)",
    12: "M2 Control (sweep + gap-ordered deploy + 25% cap)",
    13: "M3 Control (sweep + laggard-ordered deploy, no cap)",
}
# A ceiling this high binds only on a genuine concentration problem. It is here
# so one name cannot become half the book, not to harvest a return — the 20%
# version's apparent edge rested on three trades and is not relied on.
MASTER_CAP = 0.25

for code, name in MASTER_NAMES.items():
    while len(v2.bfv.NAMES) < code:
        v2.bfv.NAMES.append("")
    v2.bfv.NAMES[code - 1] = name


class MasterBook(mo.MonthlyBook):
    """The master and its two controls, on whichever calendar it is given."""

    def deploy_laggards(self, dec, fill, d, prev):
        """Fill the underweights, weakest twelve-month performer first.

        Same set of names as a gap-ordered deploy and the same target — only
        the ORDER differs, so a difference against M2 is attributable to the
        ordering and nothing else. Names with no twelve-month history yet sort
        last rather than being excluded, so early months still deploy fully.
        """
        total = self.equity(dec, True) + self.cash
        gaps = {s: total * v2.TARGET - self.qty(s) * dec[s] for s in SYMS}
        under = [s for s in SYMS if gaps[s] > 0]
        under.sort(key=lambda s: (self.data.trailing(s, prev, 1)
                                  if self.data.trailing(s, prev, 1) is not None
                                  else 1e9))
        for s in under:
            self.buy(s, gaps[s], fill[s], d, "underweight, weakest first")
        # Whole-share prices always leave a remainder; the same three-pass
        # residual sweep the verified rig uses everywhere else.
        for _ in range(3):
            affordable = [s for s in SYMS
                          if self.cash >= fill[s] * (1 + self.rate)]
            if not affordable:
                break
            portion = self.cash / len(affordable)
            for s in affordable:
                self.buy(s, portion, fill[s], d, "residual sweep")

    def review(self, d, prev):
        if self.code < 11:
            return super().review(d, prev)

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
        self.sweep_distributions(d)          # every master variant sweeps
        if self.invested == self.ticket:
            per = self.cash / len(SYMS)
            for s in SYMS:
                self.buy(s, per, fill[s], d, "equal allocation")
            self.deploy(SYMS, v2.TARGET, dec, fill, d)
            assert self.cash >= -1e-6
            return

        if self.code in (11, 12):
            self.trim_to_band(d, dec, fill, MASTER_CAP)
        if self.code in (11, 13):
            self.deploy_laggards(dec, fill, d, prev)
        else:
            self.deploy(SYMS, v2.TARGET, dec, fill, d)
        assert self.cash >= -1e-6


def run_schedule(label, data, contrib, months, codes):
    """Run the given codes on one contribution calendar.

    `months` is what actually changes the calendar — an earlier version varied
    only the ticket size and left the monthly review dates in place, so the
    "annual" control was really a monthly run paying twelve times as much. The
    tell was M1 scoring an identical XIRR on both.
    """
    out, books = [], []
    for code in codes:
        b = MasterBook(data, code, months=months)
        b.ticket = contrib
        r = b.run()
        t = MasterBook(data, code, 12, after_tax=True, months=months)
        t.ticket = contrib
        rt = t.run()
        r["after_tax_xirr_pct"] = rt["xirr_pct"]
        r["after_tax_terminal"] = rt["terminal_after_cost"]
        r["ltcg_paid"] = t.ltcg_paid
        out.append(r)
        books.append(b)
        print(f"  {r['name']:<50} {r['terminal_after_cost']:>13,.0f} "
              f"pre {r['xirr_pct']:>6.2f}%  after-tax {rt['xirr_pct']:>6.2f}%"
              f"  sells={r['sells']}", flush=True)
    return out, books


def main():
    from datetime import date
    OUT.mkdir(parents=True, exist_ok=True)
    data = Data()
    codes = list(range(1, 14))
    payload = {}

    print("MONTHLY Rs 10,000 — the schedule the master was designed on")
    monthly, books = run_schedule("monthly", data, 10000, None, codes)
    payload["monthly"] = monthly

    print("\nANNUAL Rs 1,00,000 — a calendar the master was NOT designed on")
    annual, _ = run_schedule("annual", data, 100000, (1,), codes)
    payload["annual"] = annual

    print("\ncost sensitivity (monthly, after tax held at 12 bps pre-tax basis)")
    sens = []
    for bps in (0, 25):
        for code in (6, 10, 11):
            b = MasterBook(data, code, bps)
            b.ticket = 10000
            r = b.run()
            sens.append(dict(cost_bps=bps, code=code, name=r["name"],
                             xirr_pct=r["xirr_pct"]))
            print(f"  {bps:>2} bps  {r['name'][:46]:<46} {r['xirr_pct']:.2f}%",
                  flush=True)
    payload["cost_sensitivity"] = sens

    # Start-year robustness. Same rules, three different fifteen/twelve/nine-year
    # windows on the same prices. An edge that only exists from one start date
    # is a property of that start date.
    print("")
    print("start-year robustness (monthly, after tax)")
    starts = []
    for y in (2011, 2014, 2017):
        row = {"start_year": y}
        for code in (6, 8, 10, 11):
            b = MasterBook(data, code, 12, after_tax=True,
                           start=date(y, 1, 1))
            b.ticket = 10000
            r = b.run()
            row[f"S{code}" if code < 11 else "M1"] = round(r["xirr_pct"], 2)
        starts.append(row)
        best = max((k for k in row if k != "start_year"), key=lambda k: row[k])
        print(f"  from {y}: " + "  ".join(f"{k} {row[k]:.2f}%" for k in row
                                          if k != "start_year")
              + f"   -> best: {best}", flush=True)
    payload["start_year_robustness"] = starts
    payload["design_note"] = (
        "Every ingredient of M1 was selected using results measured on this "
        "same basket and period. That is overfitting by construction. The "
        "annual run is the only out-of-design evidence here: a different "
        "contribution calendar on the same prices. It is a weak test and is "
        "not a substitute for a different universe or period.")
    payload["master_cap"] = MASTER_CAP
    (OUT / "results.json").write_text(json.dumps(payload, indent=2),
                                      encoding="utf-8")
    with zipfile.ZipFile(OUT / "audit_ledgers.zip", "w",
                         zipfile.ZIP_DEFLATED) as z:
        for b in books:
            z.writestr(f"S{b.code}_transactions_and_events.csv", csvtext(b.logs))
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
