"""A library of Nifty 50 SIP rules, price only, on official NSE data.

Rs 10,000 a month is the base. Rules fall in five groups:

  A  base            fixed SIP, step-ups
  B  fixed + top-up  fixed SIP every month PLUS fresh extra money when a
                     signal fires (more money in, so compare XIRR not corpus)
  C  scaled amount   the monthly amount itself moves with valuation
  D  same budget     Rs 10,000 a month total; what isn't invested waits in a
                     6% liquid fund and the pile goes in when the signal fires
  E  other           value averaging, buy-every-2%-fall day

Decisions use yesterday's close, buys use today's close (first trading day of
the month, or the day after the fall for the daily rule). Price index only, no
dividends, as asked. Cash still waiting at the end counts at its value.

    python research/scripts/smart_sip_rules.py

Needs research/data/nifty50_nse_daily_1999.csv (see smart_sip_backtest.py).
Out: research/data/smart_sip/rules.json
"""
import json
import os
from datetime import date

from smart_sip_backtest import OUT_DIR, SIP, add_indicators, load, month_days, xirr

LIQUID = 0.06
WINDOWS = [date(1996, 1, 1), date(2000, 1, 1), date(2008, 1, 1), date(2017, 1, 1)]


def add_extras(rows):
    low_on = False
    for i, r in enumerate(rows):
        window = [x["close"] for x in rows[max(0, i - 251):i + 1]]
        r["dd"] = 1 - r["close"] / max(window)
        if i >= 251:
            if r["close"] >= max(window):
                low_on = False
            elif r["close"] <= min(window):
                low_on = True
        r["low_on"] = low_on
        r["chg"] = r["close"] / rows[i - 1]["close"] - 1 if i else 0.0


# signals on yesterday's row; no P/E history before 1999 counts as "not cheap"
def pe_below_avg(r): return r["pe_avg"] is not None and r["pe"] < r["pe_avg"]
def pe_below(t): return lambda r: r["pe"] is not None and r["pe"] < t
def below_dma(r): return r["dma"] is not None and r["close"] < r["dma"]
def dip(d): return lambda r: r["dd"] >= d
def low_start(r): return r["low_on"]


def pe_band(r):
    """Monthly amount by absolute P/E band."""
    pe = r["pe"]
    if pe is None:
        return SIP
    if pe < 18:
        return 2 * SIP
    if pe < 22:
        return SIP
    if pe < 25:
        return SIP / 2
    return SIP / 4


def pe_scaled(r):
    """Monthly amount = SIP x (12m avg P/E / P/E)^3, capped at 3x."""
    if r["pe_avg"] is None:
        return SIP
    return min(3 * SIP, SIP * (r["pe_avg"] / r["pe"]) ** 3)


# (group, label, spec)
#   base:    fraction of SIP invested every month (stepup: yearly growth)
#   extra:   (signal, amount) fresh money added when the signal fires
#   pile:    (fraction of SIP sent to the pile, release signal)
#   amount:  function of yesterday's row giving this month's amount
RULES = [
    ("A", "1 Fixed SIP", {"base": 1.0}),
    ("A", "2 Step-up 10%/yr", {"base": 1.0, "stepup": 0.10}),
    ("A", "3 Step-up 5%/yr", {"base": 1.0, "stepup": 0.05}),
    ("B", "4 Fixed + 10k when PE < 12m avg", {"base": 1.0, "extra": (pe_below_avg, SIP)}),
    ("B", "5 Fixed + 10k when PE < 20", {"base": 1.0, "extra": (pe_below(20), SIP)}),
    ("B", "6 Fixed + 20k when PE < 18", {"base": 1.0, "extra": (pe_below(18), 2 * SIP)}),
    ("B", "7 Fixed + 10k when below 200 DMA", {"base": 1.0, "extra": (below_dma, SIP)}),
    ("B", "8 Fixed + 10k on 10% dip", {"base": 1.0, "extra": (dip(0.10), SIP)}),
    ("B", "9 Fixed + 20k on 20% dip", {"base": 1.0, "extra": (dip(0.20), 2 * SIP)}),
    ("B", "10 Fixed + 10k after 52w low", {"base": 1.0, "extra": (low_start, SIP)}),
    ("C", "11 PE band 2x/1x/0.5x/0.25x", {"amount": pe_band}),
    ("C", "12 PE-scaled (avg/PE)^3", {"amount": pe_scaled}),
    ("D", "13 PE < 12m avg pile (video)", {"base": 0.0, "pile": (1.0, pe_below_avg)}),
    ("D", "14 50% fixed + 50% PE pile", {"base": 0.5, "pile": (0.5, pe_below_avg)}),
    ("D", "15 PE < 20 pile", {"base": 0.0, "pile": (1.0, pe_below(20))}),
    ("D", "16 80% fixed + 20% PE<20 pile", {"base": 0.8, "pile": (0.2, pe_below(20))}),
    ("D", "17 Below 200 DMA pile", {"base": 0.0, "pile": (1.0, below_dma)}),
    ("D", "18 52w low start pile", {"base": 0.0, "pile": (1.0, low_start)}),
    ("D", "19 80% fixed + 20% dip-10% pile", {"base": 0.8, "pile": (0.2, dip(0.10))}),
    ("E", "20 Value averaging 1%/month", {"va": 0.01}),
    ("E", "21 Fixed + 10k every 2% fall day", {"base": 1.0, "daily_fall": 0.02}),
]


def run(rows, days, spec, start):
    last = rows[-1]
    monthly = (1 + LIQUID) ** (1 / 12) - 1
    units, pile, flows, extras = 0.0, 0.0, [], 0
    for k, i in enumerate(days):
        r, prev = rows[i], rows[i - 1]
        if "va" in spec:
            g = spec["va"]
            target = SIP * ((1 + g) ** (k + 1) - 1) / g
            put = min(3 * SIP, max(0.0, target - units * r["close"]))
            units += put / r["close"]
            flows.append((r["date"], -put))
            continue
        if "amount" in spec:
            put = spec["amount"](prev)
            units += put / r["close"]
            flows.append((r["date"], -put))
            continue
        size = SIP * (1 + spec.get("stepup", 0.0)) ** (r["date"].year - start.year)
        put = size * spec["base"]
        paid = put
        if "extra" in spec and spec["extra"][0](prev):
            put += spec["extra"][1]
            paid += spec["extra"][1]
            extras += 1
        if "pile" in spec:
            share, release = spec["pile"]
            pile = pile * (1 + monthly) + size * share
            paid += size * share
            if release(prev):
                put += pile
                pile = 0.0
                extras += 1
        units += put / r["close"]
        flows.append((r["date"], -paid))
    if "daily_fall" in spec:
        for j in range(days[0] + 1, len(rows)):
            if rows[j - 1]["chg"] <= -spec["daily_fall"]:
                units += SIP / rows[j]["close"]
                flows.append((rows[j]["date"], -SIP))
                extras += 1
    flows.sort(key=lambda f: f[0])
    value = units * last["close"] + pile
    paid = -sum(v for _, v in flows)
    return {
        "xirr_pct": round(xirr(flows + [(last["date"], value)]) * 100, 2),
        "paid_lakh": round(paid / 1e5, 1),
        "value_lakh": round(value / 1e5, 1),
        "signal_count": extras,
    }


def main():
    rows = load()
    add_indicators(rows)
    add_extras(rows)
    out = {"data_through": rows[-1]["date"].isoformat(), "basis": "price index only",
           "rules": {}}
    for group, label, spec in RULES:
        out["rules"][label] = {"group": group}
        for w in WINDOWS:
            out["rules"][label][str(w.year)] = run(rows, month_days(rows, w), spec, w)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "rules.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"price only, data through {out['data_through']}")
    print(f"{'rule':36s}" + "".join(f"{w.year:>8d}" for w in WINDOWS) + "   1996: paid L -> value L")
    for label, res in out["rules"].items():
        cells = "".join(f"{res[str(w.year)]['xirr_pct']:7.2f}%" for w in WINDOWS)
        r96 = res["1996"]
        print(f"{res['group']} {label:34s}{cells}   {r96['paid_lakh']:7.1f} -> {r96['value_lakh']:7.1f}")


if __name__ == "__main__":
    main()
