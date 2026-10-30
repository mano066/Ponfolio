"""Does guarding the trim beat the unguarded master? S1-S10, M1, and four new variants.

    python research/scripts/backtest_master_guarded.py

The question comes from a real page of the S10 ledger:

    2019-12-02  SCI 3,325 sh  Rs 2,01,162.50  17.96% of book  HOLD
    2020-07-01  SCI 3,325 sh  Rs 1,89,857.50  20.44% of book  SELL 1,698 @ 57.00

SCI never grew. Its own price fell 5.6% across those seven months; the rest of
the book fell 17.7% in the COVID crash, so SCI's WEIGHT breached the 20% ceiling
from the denominator. The rule then sold half the position — at Rs 57, eleven
thousand rupees of position value below where the same holding had sat, unsold,
at the previous review.

Two candidate guards, both asking "is this sale late?" before making it:

  peak  Sell only while the holding is within PEAK_BAND of its own trailing
        one-year high. A holding already well off its high is not being
        harvested, it is being dumped after the fact.
  gain  Sell only while the holding is above its cost basis. Cheaper to state,
        and it is the version now shipping in the app's rebalance engine.

Variants, all sweeping distributions and deploying weakest-first like M1, so the
only thing that moves between them is the trim:

  M4  25% cap, peak guard          — M1 plus the guard
  M5  12.5% cap, peak guard        — the real hypothesis: a guard should make a
                                     TIGHT band safe, and a tight band catches a
                                     breach while the price is still near its high
  M6  12.5% cap, no guard          — control, isolates the guard in M5
  M7  12.5% cap, gain guard        — the app's version, measured against M5/M6

M6 is the control that matters. M5 minus M6 is the guard; M5 minus M4 is the band.

Out: research/data/strategies_guarded/results.json
"""
import bisect
import json
import math
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import backtest_master_strategy as mst  # noqa: E402
import backtest_strategies_v2 as v2  # noqa: E402
from backtest_five_verified import SYMS, Data  # noqa: E402

OUT = ROOT / "research" / "data" / "strategies_guarded"

# Within 5% of its own one-year high counts as "still near the peak". Wide
# enough that ordinary noise does not veto a legitimate trim, tight enough that
# SCI at 5.6% below a falling high does not qualify.
PEAK_BAND = 0.95

# code -> (ceiling, guard)
VARIANTS = {
    14: (0.25, "peak"),
    15: (0.125, "peak"),
    16: (0.125, None),
    17: (0.125, "gain"),
    # Exactly what the app now ships: M1's cap with the cost-basis guard.
    18: (0.25, "gain"),
    # S10's own ceiling, which is the band the SCI page was written under.
    19: (0.20, None),
    20: (0.20, "gain"),
    21: (0.20, "peak"),
}
NAMES = {
    14: "M4 25% cap + peak guard",
    15: "M5 12.5% cap + peak guard",
    16: "M6 12.5% cap, no guard (control)",
    17: "M7 12.5% cap + gain guard",
    18: "M8 25% cap + gain guard (ships in app)",
    19: "M9  20% cap, no guard (S10 band)",
    20: "M10 20% cap + gain guard",
    21: "M11 20% cap + peak guard",
}
for code, name in NAMES.items():
    while len(v2.bfv.NAMES) < code:
        v2.bfv.NAMES.append("")
    v2.bfv.NAMES[code - 1] = name


class GuardedBook(mst.MasterBook):
    """M1's machinery with a condition attached to the sell leg."""

    def peak_ratio(self, s, d):
        """Today's adjusted price over its highest adjusted close in a year.

        Measured on `data.signal`, the split- and bonus-adjusted series, because
        a raw close series shows a 1:1 bonus as a 50% crash and would veto every
        trim in the year after a corporate action.
        """
        days = self.data.days
        lo = bisect.bisect_left(days, d - timedelta(days=365))
        hi = bisect.bisect_right(days, d)
        window = days[lo:hi]
        if not window or d not in self.data.signal:
            return None
        high = max(self.data.signal[x][s] for x in window)
        if high <= 0:
            return None
        return self.data.signal[d][s] / high

    def trim_guarded(self, d, dec, fill, band, guard):
        """Sell back toward the 10% target, unless the guard says it is late."""
        total = self.equity(dec, True)
        if not total:
            return
        for s in SYMS:
            value = self.qty(s) * dec[s]
            if not value or value / total <= band:
                continue
            if guard == "peak":
                ratio = self.peak_ratio(s, d)
                if ratio is not None and ratio < PEAK_BAND:
                    self.log(d, s, "SKIP_TRIM", note=(
                        f"weight {value / total * 100:.1f}% over {band * 100:g}%"
                        f" but {(1 - ratio) * 100:.1f}% off its 1y high"))
                    continue
            elif guard == "gain":
                basis = self.basis(s)
                if basis and value <= basis:
                    self.log(d, s, "SKIP_TRIM", note=(
                        f"weight {value / total * 100:.1f}% over {band * 100:g}%"
                        f" but under water on cost"))
                    continue
            want = math.floor((value - v2.TARGET * total) / dec[s])
            self.sell(s, want, fill[s], d,
                      f"weight >{band * 100:g}%; trim toward "
                      f"{v2.TARGET * 100:g}%")

    def review(self, d, prev):
        if self.code not in VARIANTS:
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
        self.sweep_distributions(d)
        if self.invested == self.ticket:
            per = self.cash / len(SYMS)
            for s in SYMS:
                self.buy(s, per, fill[s], d, "equal allocation")
            self.deploy(SYMS, v2.TARGET, dec, fill, d)
            assert self.cash >= -1e-6
            return

        cap, guard = VARIANTS[self.code]
        self.trim_guarded(d, dec, fill, cap, guard)
        self.deploy_laggards(dec, fill, d, prev)
        assert self.cash >= -1e-6


def run(label, data, contrib, months, codes):
    rows = []
    print(f"\n{label}")
    for code in codes:
        b = GuardedBook(data, code, months=months)
        b.ticket = contrib
        r = b.run()
        t = GuardedBook(data, code, 12, after_tax=True, months=months)
        t.ticket = contrib
        rt = t.run()
        r["after_tax_xirr_pct"] = rt["xirr_pct"]
        r["skipped_trims"] = sum(1 for x in b.logs if x["event"] == "SKIP_TRIM")
        rows.append(r)
        print(f"  {r['name']:<36} {r['terminal_after_cost']:>13,.0f} "
              f"pre {r['xirr_pct']:>6.2f}%  after-tax {rt['xirr_pct']:>6.2f}%"
              f"  sells={r['sells']:<3} skipped={r['skipped_trims']}",
              flush=True)
    return rows


def main():
    data = Data()
    codes = [6, 8, 10, 11] + list(VARIANTS)
    monthly = run("MONTHLY  Rs 10,000/month", data, 10000, None, codes)
    annual = run("ANNUAL   Rs 1,00,000/year", data, 100000, (1,), codes)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({
        "peak_band": PEAK_BAND,
        "variants": {str(k): {"cap": v[0], "guard": v[1]}
                     for k, v in VARIANTS.items()},
        "monthly": monthly,
        "annual": annual,
        "caveat": "Both guards were designed after seeing the SCI trade in this "
                  "same basket and period. The annual run is the only "
                  "out-of-design evidence here, and it is a weak test: a "
                  "different contribution calendar over identical prices.",
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
