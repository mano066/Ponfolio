"""Month-by-month ledger for rule 20 (value averaging) in smart_sip_rules.py.

Value averaging: the portfolio has a target path, Rs 10,000 more each month
with the target itself growing 1% a month. Each month you invest
target - current value, never below 0 (it never sells) and at most Rs 30,000.
Buys at the first trading day's close; price index only.

Two versions side by side:
  plain  only what is invested counts (the 12.36% XIRR in the table)
  fair   Rs 10,000 is set aside every month; the investment is taken from
         that pile, the rest earns 6% a year in a liquid fund, and the pile
         left at the end counts (the 11.69% XIRR)

    python research/scripts/value_averaging_ledger.py

Out: research/data/smart_sip/value_averaging_ledger.csv  (one row a month)
     research/data/smart_sip/value_averaging_by_year.csv (one row a year)
"""
import csv
import os
from datetime import date

from smart_sip_backtest import OUT_DIR, SIP, load, month_days, xirr

START = date(1996, 1, 1)
GROWTH = 0.01
CAP = 3 * SIP
LIQ_M = 1.06 ** (1 / 12) - 1


def main():
    rows = load()
    days = month_days(rows, START)
    last = rows[-1]
    ledger = []
    units = units_f = pile = 0.0
    paid = 0.0
    flows, flows_f, flows_fixed = [], [], []
    units_fixed = 0.0
    for k, i in enumerate(days):
        r = rows[i]
        px = r["close"]
        target = SIP * ((1 + GROWTH) ** (k + 1) - 1) / GROWTH

        value_before = units * px
        gap = target - value_before
        put = min(CAP, max(0.0, gap))
        units += put / px
        paid += put
        if put:
            flows.append((r["date"], -put))

        pile = pile * (1 + LIQ_M) + SIP
        pile_before = pile
        value_f_before = units_f * px
        put_f = min(pile, CAP, max(0.0, target - value_f_before))
        pile -= put_f
        units_f += put_f / px
        flows_f.append((r["date"], -SIP))

        units_fixed += SIP / px
        flows_fixed.append((r["date"], -SIP))

        ledger.append({
            "month_no": k + 1,
            "date": r["date"].isoformat(),
            "nifty_close": round(px, 2),
            "pe": r["pe"] if r["pe"] is not None else "",
            "target_value": round(target),
            "value_before": round(value_before),
            "gap": round(gap),
            "invest": round(put),
            "action": "cap 30k" if put >= CAP - 0.5 else "skip" if put == 0 else "partial",
            "units_bought": round(put / px, 4),
            "total_units": round(units, 4),
            "total_invested": round(paid),
            "value_after": round(units * px),
            "fair_pile_before": round(pile_before),
            "fair_value_before": round(value_f_before),
            "fair_gap": round(target - value_f_before),
            "fair_invest": round(put_f),
            "fair_units_bought": round(put_f / px, 4),
            "fair_total_units": round(units_f, 4),
            "fair_pile_after": round(pile),
            "fair_units_value": round(units_f * px),
            "fair_value_total": round(units_f * px + pile),
            "fixed_units_bought": round(SIP / px, 4),
            "fixed_total_units": round(units_fixed, 4),
            "fixed_sip_value": round(units_fixed * px),
        })

    path = os.path.join(OUT_DIR, "value_averaging_ledger.csv")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ledger[0]))
        w.writeheader()
        w.writerows(ledger)

    years = {}
    for row in ledger:
        y = years.setdefault(row["date"][:4], {"year": row["date"][:4], "months": 0, "skip": 0,
                                               "cap": 0, "invested": 0, "fair_invested": 0})
        y["months"] += 1
        y["skip"] += row["action"] == "skip"
        y["cap"] += row["action"] == "cap 30k"
        y["invested"] += row["invest"]
        y["fair_invested"] += row["fair_invest"]
        y["nifty_close_end"] = row["nifty_close"]
        y["total_invested_end"] = row["total_invested"]
        y["value_end"] = row["value_after"]
        y["target_end"] = row["target_value"]
        y["fair_pile_end"] = row["fair_pile_after"]
        y["fair_value_end"] = row["fair_value_total"]
        y["fixed_sip_value_end"] = row["fixed_sip_value"]
    ypath = os.path.join(OUT_DIR, "value_averaging_by_year.csv")
    with open(ypath, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(next(iter(years.values()))))
        w.writeheader()
        w.writerows(years.values())

    end = last["date"]
    v_plain = units * last["close"]
    v_fair = units_f * last["close"] + pile
    v_fixed = units_fixed * last["close"]
    print(f"wrote {path} ({len(ledger)} months) and {ypath}")
    print(f"plain : invested {paid / 1e5:.1f} L -> {v_plain / 1e5:.1f} L  XIRR {xirr(flows + [(end, v_plain)]) * 100:.2f}%")
    print(f"fair  : set aside {SIP * len(days) / 1e5:.1f} L -> {v_fair / 1e5:.1f} L (cash {pile / 1e5:.1f} L)  "
          f"XIRR {xirr(flows_f + [(end, v_fair)]) * 100:.2f}%")
    print(f"fixed : invested {SIP * len(days) / 1e5:.1f} L -> {v_fixed / 1e5:.1f} L  "
          f"XIRR {xirr(flows_fixed + [(end, v_fixed)]) * 100:.2f}%")
    print(f"\n{'year':5s}{'nifty':>8s}{'skip':>5s}{'cap':>4s}{'invested':>10s}{'total in':>10s}"
          f"{'value':>10s}{'target':>10s}{'fair pile':>10s}{'fair tot':>10s}{'fixed':>10s}")
    for y in years.values():
        print(f"{y['year']:5s}{y['nifty_close_end']:>8.0f}{y['skip']:>5d}{y['cap']:>4d}{y['invested']:>10,}"
              f"{y['total_invested_end']:>10,}{y['value_end']:>10,}{y['target_end']:>10,}"
              f"{y['fair_pile_end']:>10,}{y['fair_value_end']:>10,}{y['fixed_sip_value_end']:>10,}")


if __name__ == "__main__":
    main()
