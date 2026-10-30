"""Can a Nifty 50 SIP reach 12%+ XIRR? Fixed SIP, P/E and dip rules compared.

Every rule gets the same Rs 10,000 a month (fair fight): the part not invested
straight away waits in a 6% liquid fund and the whole pile goes into Nifty when
the rule's trigger fires; anything still waiting at the end counts at its cash
value. Decisions use yesterday's close, buys use today's close.

Returns are what a Nifty 50 index fund holder earns: the price index plus
NSE's published dividend yield, less a 0.20% a year expense ratio. The
price-only column is there to tie back to the video and earlier runs.

    python research/scripts/smart_sip_variants.py

Needs research/data/nifty50_nse_daily_1999.csv (see smart_sip_backtest.py).
Out: research/data/smart_sip/variants.json
"""
import json
import os
from datetime import date

from smart_sip_backtest import (ASSUMED_DY, OUT_DIR, SIP, add_indicators, load,
                                month_days, xirr)

LIQUID = 0.06
TER = 0.0020


def add_fund_nav(rows):
    nav = 1.0
    for i, r in enumerate(rows):
        if i:
            dy = r["dy"] if r["dy"] is not None else ASSUMED_DY
            nav *= r["close"] / rows[i - 1]["close"] * (1 + dy / 100 / 252) * (1 - TER / 252)
        r["fund"] = nav
        hi = max(x["close"] for x in rows[max(0, i - 251):i + 1])
        r["dd"] = 1 - r["close"] / hi


def pe_cheap(r):
    return r["pe_avg"] is None or r["pe"] < r["pe_avg"]


# (label, share invested every month, trigger that releases the pile)
VARIANTS = [
    ("Fixed SIP", 1.0, None),
    ("PE rule (all money waits)", 0.0, pe_cheap),
    ("50% fixed + 50% PE pile", 0.5, pe_cheap),
    ("PE below 20 (absolute)", 0.0, lambda r: r["pe"] is None or r["pe"] < 20),
    ("PE < avg by 5%+", 0.0, lambda r: r["pe_avg"] is None or r["pe"] < 0.95 * r["pe_avg"]),
    ("Dip 5% from 52w high", 0.0, lambda r: r["dd"] >= 0.05),
    ("Dip 10% from 52w high", 0.0, lambda r: r["dd"] >= 0.10),
    ("50% fixed + 50% dip-10% pile", 0.5, lambda r: r["dd"] >= 0.10),
    ("PE cheap OR dip 10%", 0.0, lambda r: pe_cheap(r) or r["dd"] >= 0.10),
    ("Dip 20% from 52w high", 0.0, lambda r: r["dd"] >= 0.20),
]


def run(rows, days, share, trigger, basis):
    last = rows[-1]
    monthly = (1 + LIQUID) ** (1 / 12) - 1
    units, pile, flows = 0.0, 0.0, []
    for i in days:
        r = rows[i]
        flows.append((r["date"], -SIP))
        pile = pile * (1 + monthly) + SIP * (1 - share)
        put = SIP * share
        if trigger is None or trigger(rows[i - 1]):
            put += pile
            pile = 0.0
        units += put / r[basis]
    value = units * last[basis] + pile
    return round(xirr(flows + [(last["date"], value)]) * 100, 2), value


def main():
    rows = load()
    add_indicators(rows)
    add_fund_nav(rows)
    windows = [("1996", date(1996, 1, 1)), ("2000", date(2000, 1, 1)),
               ("2008 peak", date(2008, 1, 1)), ("2017", date(2017, 1, 1))]
    out = {"data_through": rows[-1]["date"].isoformat(), "variants": {}}
    for label, share, trigger in VARIANTS:
        res = {}
        for wname, start in windows:
            days = month_days(rows, start)
            x_fund, v_fund = run(rows, days, share, trigger, "fund")
            x_px, _ = run(rows, days, share, trigger, "close")
            res[wname] = {"fund_xirr_pct": x_fund, "price_xirr_pct": x_px,
                          "fund_value_lakh": round(v_fund / 1e5, 1),
                          "paid_lakh": round(SIP * len(days) / 1e5, 1)}
        out["variants"][label] = res

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "variants.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"data through {out['data_through']}  (index fund = price + dividends - {TER:.2%} TER)")
    head = "".join(f"{w:>20s}" for w, _ in windows)
    print(f"{'rule':30s}{head}")
    print(f"{'':30s}" + "".join(f"{'fund / price':>20s}" for _ in windows))
    for label, res in out["variants"].items():
        cells = "".join(f"{res[w]['fund_xirr_pct']:>11.2f}% /{res[w]['price_xirr_pct']:5.2f}%" for w, _ in windows)
        print(f"{label:30s}{cells}")
    print("\nvalue today, index fund (Rs lakh):")
    for label, res in out["variants"].items():
        print(f"{label:30s}" + "".join(f"{res[w]['fund_value_lakh']:>13.1f} of {res[w]['paid_lakh']:5.1f}" for w, _ in windows))


if __name__ == "__main__":
    main()
