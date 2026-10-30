"""Replicates the seven SIP rules in "Normal SIP vs Smart SIP" on NSE data.

The video (Kirubakaran Rajendran, youtu.be/n8XSAVFOoLE) puts Rs 10,000 a month
into Nifty from Jan 1996 to 2026 (370 instalments, Rs 37 L) under seven rules,
each deciding on yesterday's close and buying at the next close:

    fixed      every month
    stepup     every month, +10% each January
    below200   only when Nifty is under its 200-day average
    above200   only when Nifty is over its 200-day average
    low_start  start at a 52-week low, stop at a 52-week high
    high_start start at a 52-week high, stop at a 52-week low
    pe         only when P/E is below its 12-month average

and scores them three ways, all reported here:

    Round 1   XIRR on the money each rule actually invested; skipped months
              are simply not invested
    Round 2   what that money is worth today
    Fair      every rule sets aside Rs 10,000 each month; skipped money waits
              in a 6% liquid fund and the whole pile moves into Nifty the next
              time the rule says buy, so every rule puts in the same Rs 37 L

Prices are the NIFTY 50 price index, as in the video. P/E starts in Jan 1999,
so before its 12-month average exists the P/E rule simply invests.

    python research/scripts/smart_sip_video_replica.py

Needs research/data/nifty50_nse_daily_1999.csv (see smart_sip_backtest.py).
Out: research/data/smart_sip/video_replica.json
"""
import json
import os
from datetime import date

from smart_sip_backtest import (DATA_CSV, OUT_DIR, SIP, add_indicators, load,
                                month_days, xirr)

LIQUID = 0.06
RULES = ["fixed", "stepup", "below200", "above200", "low_start", "high_start", "pe"]


def add_switches(rows):
    """52-week on/off states as of each close (a new high or low flips them)."""
    low_on = high_on = False
    for i, r in enumerate(rows):
        window = [x["close"] for x in rows[max(0, i - 251):i + 1]]
        if i >= 251:
            if r["close"] >= max(window):
                low_on, high_on = False, True
            elif r["close"] <= min(window):
                low_on, high_on = True, False
        r["low_on"], r["high_on"] = low_on, high_on


def buys(rule, r):
    if rule in ("fixed", "stepup"):
        return True
    if rule == "below200":
        return r["dma"] is not None and r["close"] < r["dma"]
    if rule == "above200":
        return r["dma"] is not None and r["close"] > r["dma"]
    if rule == "low_start":
        return r["low_on"]
    if rule == "high_start":
        return r["high_on"]
    # No P/E history before 1999 (no 12-month average until ~Jan 2000): invest,
    # as the video's months-bought chart shows the P/E rule doing in 1996-99.
    if r["pe_avg"] is None:
        return True
    return r["pe"] < r["pe_avg"]


def run(rows, days, rule, start_year):
    last = rows[-1]
    # Round 1 / Round 2: skipped months are not invested at all
    units, flows, months = 0.0, [], 0
    # Fair fight: skipped money waits in a liquid fund
    f_units, pile, f_flows = 0.0, 0.0, []
    monthly = (1 + LIQUID) ** (1 / 12) - 1
    for i in days:
        r = rows[i]
        amt = SIP * (1.1 ** (r["date"].year - start_year) if rule == "stepup" else 1)
        on = buys(rule, rows[i - 1])
        if on:
            units += amt / r["close"]
            flows.append((r["date"], -amt))
            months += 1
        pile = pile * (1 + monthly) + amt
        f_flows.append((r["date"], -amt))
        if on:
            f_units += pile / r["close"]
            pile = 0.0
    value = units * last["close"]
    paid = -sum(v for _, v in flows)
    f_value = f_units * last["close"] + pile
    return {
        "months_invested": months, "months": len(days),
        "round1_xirr_pct": round(xirr(flows + [(last["date"], value)]) * 100, 2) if flows else None,
        "round2_paid_lakh": round(paid / 1e5, 1),
        "round2_value_cr": round(value / 1e7, 2),
        "fair_value_cr": round(f_value / 1e7, 2),
        "fair_xirr_pct": round(xirr(f_flows + [(last["date"], f_value)]) * 100, 2),
    }


def run_combo(rows, days, fixed_share, extra=0.0):
    """Fixed SIP plus a P/E top-up.

    Each month SIP * fixed_share goes into Nifty regardless. The rest of the
    SIP waits in the liquid fund and the whole pile goes in whenever the P/E
    rule says buy. `extra` is fresh money added on top only in P/E-cheap months
    (no pile), for the "fixed SIP + buy more when cheap" reading.
    """
    last = rows[-1]
    monthly = (1 + LIQUID) ** (1 / 12) - 1
    units, pile, flows = 0.0, 0.0, []
    for i in days:
        r = rows[i]
        on = buys("pe", rows[i - 1])
        fixed = SIP * fixed_share
        pile = pile * (1 + monthly) + SIP - fixed
        put = fixed + (extra if on else 0.0)
        flows.append((r["date"], -(SIP + (extra if on else 0.0))))
        if on:
            put += pile
            pile = 0.0
        units += put / r["close"]
    value = units * last["close"] + pile
    paid = -sum(v for _, v in flows)
    return {
        "paid_lakh": round(paid / 1e5, 1),
        "value_cr": round(value / 1e7, 2),
        "xirr_pct": round(xirr(flows + [(last["date"], value)]) * 100, 2),
    }


COMBOS = [
    ("fixed 100%", 1.0, 0.0),
    ("fixed 75% + PE pile 25%", 0.75, 0.0),
    ("fixed 50% + PE pile 50%", 0.5, 0.0),
    ("fixed 25% + PE pile 75%", 0.25, 0.0),
    ("PE pile 100%", 0.0, 0.0),
    ("fixed 10k + extra 10k when PE cheap", 1.0, SIP),
]


def main():
    rows = load()
    add_indicators(rows)
    add_switches(rows)
    out = {"data": os.path.basename(DATA_CSV), "data_through": rows[-1]["date"].isoformat(),
           "windows": {}}
    for name, start, rules in (
        ("Jan 1996 onward", date(1996, 1, 1), RULES),
        ("Jan 2000 onward", date(2000, 1, 1), RULES),
        ("Jan 2017 onward", date(2017, 1, 1), RULES),
    ):
        days = month_days(rows, start)
        out["windows"][name] = {rule: run(rows, days, rule, start.year) for rule in rules}
        out["windows"][name]["combos"] = {label: run_combo(rows, days, share, extra)
                                          for label, share, extra in COMBOS}

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "video_replica.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"data through {out['data_through']}")
    for name, res in out["windows"].items():
        print(f"\n== {name}")
        print(f"  {'rule':11s} {'months':>9s} {'R1 XIRR':>8s} {'paid L':>7s} {'R2 Cr':>6s} {'fair Cr':>7s} {'fair XIRR':>9s}")
        for rule, m in res.items():
            if rule == "combos":
                for label, c in m.items():
                    print(f"  combo {label:38s} paid {c['paid_lakh']:6.1f} L  value {c['value_cr']:5.2f} Cr"
                          f"  XIRR {c['xirr_pct']:6.2f}%")
                continue
            print(f"  {rule:11s} {m['months_invested']:4d}/{m['months']:<4d} {m['round1_xirr_pct']:7.2f}% "
                  f"{m['round2_paid_lakh']:7.1f} {m['round2_value_cr']:6.2f} {m['fair_value_cr']:7.2f} {m['fair_xirr_pct']:8.2f}%")


if __name__ == "__main__":
    main()
