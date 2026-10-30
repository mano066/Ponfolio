"""Normal SIP vs "Smart SIP" on the Nifty 50, from official NSE data.

Prompted by Kirubakaran Rajendran's video "Normal SIP vs Smart SIP"
(youtu.be/n8XSAVFOoLE), which compares a fixed monthly SIP with SIPs that only
buy when one of three signals says the market is cheap:

    PE    Nifty P/E below its own trailing 12-month average P/E
    DMA   Nifty below its 200-day moving average
    52W   Nifty in the lower half of its 52-week high-low range

and reports roughly 11.5% (fixed) vs 11.7% (PE), 12.05% (DMA), 12.1% (52W).

Rules used here (the video's exact rules could not be recovered from its
captions, so these are the plain-reading versions):

  * Rs 10,000 arrives on the first trading day of every month.
  * Normal SIP buys with it at that day's close.
  * A smart SIP adds it to a cash pot. If the signal, computed from the PREVIOUS
    session's close (no look-ahead), is on, the whole pot is invested at that
    day's close; otherwise the pot waits. Cash earns either 0% or a 6% a year
    liquid-fund rate, and both are reported.
  * At the end, units are valued at the last close plus whatever cash is still
    waiting. XIRR is on the monthly contributions against that terminal value.
  * "Price" uses the NIFTY 50 price index. "TR" adds back dividends from NSE's
    published daily dividend yield (where NSE has none, before Nov 2015, 1.3%
    a year is assumed), which is what an index fund actually earns, before TER.

Data: NSE historicalOR/indicesHistory (prices) and historicalOR/indicesYield
(P/E, P/B, dividend yield). NSE's yield API starts on 9 Nov 2015; earlier P/E
comes from Kaggle's "NIFTY 50 Historical PE, PB, DIV Yield" (1999-2024), which
matches NSE exactly wherever the two overlap.

    python research/scripts/smart_sip_backtest.py --raw <dir of NSE monthly json> --old-pe <kaggle csv>
    python research/scripts/smart_sip_backtest.py

Out: research/data/nifty50_nse_daily_1999.csv (with --raw),
     research/data/smart_sip/results.json
"""
import argparse
import csv
import glob
import json
import os
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CSV = os.path.join(ROOT, "data", "nifty50_nse_daily_1999.csv")
OUT_DIR = os.path.join(ROOT, "data", "smart_sip")

SIP = 10_000
ASSUMED_DY = 1.3      # % a year, only where NSE publishes no dividend yield
LIQUID = 0.06         # % a year earned by the waiting cash in the "6%" runs
STRATEGIES = ["normal", "pe", "dma", "w52", "all3"]


def build_csv(raw_dir, old_pe=None):
    """Merge the NSE monthly json chunks into one daily csv.

    `old_pe` is the Kaggle "NIFTY 50_Historical_PE_PB_DIV.csv" (1999-2024), used
    only for the days before NSE's own yield series begins. It is NSE data: on
    every overlapping day its close and P/E equal NSE's to the paisa.
    """
    px, yld = {}, {}
    if old_pe:
        for r in csv.DictReader(open(old_pe)):
            d = datetime.strptime(r["Date"], "%d-%b-%y").date()
            yld[d] = (r["P/E"], r["P/B"], r["Div Yield %"])
    for f in glob.glob(os.path.join(raw_dir, "indicesHistory_*.json")):
        for r in json.load(open(f))["data"]:
            d = datetime.strptime(r["EOD_TIMESTAMP"], "%d-%b-%Y").date()
            px[d] = r["EOD_CLOSE_INDEX_VAL"]
    for f in glob.glob(os.path.join(raw_dir, "indicesYield_*.json")):
        for r in json.load(open(f))["data"]:
            d = datetime.strptime(r["IY_DT"], "%d-%b-%Y").date()
            yld[d] = (r["IY_PE"], r["IY_PB"], r["IY_DY"])
    with open(DATA_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "close", "pe", "pb", "dy"])
        for d in sorted(px):
            pe, pb, dy = yld.get(d, ("", "", ""))
            w.writerow([d.isoformat(), px[d], pe, pb, dy])
    print(f"wrote {DATA_CSV}: {len(px)} sessions, {len(yld)} with P/E")


def load():
    """Daily rows; a day NSE skipped in its yield series keeps the last P/E."""
    rows, pe, dy = [], None, None
    with open(DATA_CSV) as fh:
        for r in csv.DictReader(fh):
            pe = float(r["pe"]) if r["pe"] else pe
            dy = float(r["dy"]) if r["dy"] else dy
            rows.append({
                "date": date.fromisoformat(r["date"]),
                "close": float(r["close"]),
                "pe": pe,
                "dy": dy,
            })
    return rows


def add_indicators(rows):
    """Signals as of each session's close; trading uses the previous row's."""
    tr = 1.0
    for i, r in enumerate(rows):
        if i:
            dy = r["dy"] if r["dy"] is not None else ASSUMED_DY
            tr *= r["close"] / rows[i - 1]["close"] * (1 + dy / 100 / 252)
        r["tr"] = tr
        closes = [x["close"] for x in rows[max(0, i - 251):i + 1]]
        r["dma"] = sum(closes[-200:]) / 200 if i >= 199 else None
        if i >= 251:
            hi, lo = max(closes), min(closes)
            r["w52_pos"] = (r["close"] - lo) / (hi - lo) if hi > lo else 0.5
        else:
            r["w52_pos"] = None
        pes = [x["pe"] for x in rows[max(0, i - 251):i + 1] if x["pe"] is not None]
        r["pe_avg"] = sum(pes) / len(pes) if len(pes) >= 240 else None


def signals(r):
    pe = r["pe"] is not None and r["pe_avg"] is not None and r["pe"] < r["pe_avg"]
    dma = r["dma"] is not None and r["close"] < r["dma"]
    w52 = r["w52_pos"] is not None and r["w52_pos"] < 0.5
    return {"normal": True, "pe": pe, "dma": dma, "w52": w52,
            "all3": pe and dma and w52}


def month_days(rows, start, at_end=False):
    """Index of the first (or last) session of each month from `start`."""
    by_month = {}
    for i, r in enumerate(rows):
        if r["date"] < start:
            continue
        key = (r["date"].year, r["date"].month)
        if at_end or key not in by_month:
            by_month[key] = i
    return sorted(by_month.values())


def xirr(flows):
    t0 = flows[0][0]

    def npv(rate):
        return sum(v / (1 + rate) ** ((d - t0).days / 365.0) for d, v in flows)

    lo, hi = -0.99, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def run(rows, days, strategy, basis, cash_rate):
    monthly = (1 + cash_rate) ** (1 / 12) - 1
    units = cash = 0.0
    flows, buys, max_cash = [], 0, 0.0
    deployed = []  # the same money dated when it is invested, not when it arrived
    for i in days:
        r = rows[i]
        cash = cash * (1 + monthly) + SIP
        flows.append((r["date"], -SIP))
        if signals(rows[i - 1])[strategy]:
            units += cash / r[basis]
            deployed.append((r["date"], -cash))
            cash = 0.0
            buys += 1
        max_cash = max(max_cash, cash)
    last = rows[-1]
    value = units * last[basis] + cash
    flows.append((last["date"], value))
    deployed.append((last["date"], units * last[basis]))
    paid = SIP * len(days)
    return {
        "xirr_pct": round(xirr(flows) * 100, 2),
        # Flattering and wrong as a comparison: ignores the months cash waited.
        "xirr_on_deployed_only_pct": round(xirr(deployed) * 100, 2),
        "months": len(days), "months_bought": buys,
        "paid": paid, "final_value": round(value),
        "cash_left": round(cash), "max_cash_waiting": round(max_cash),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", help="dir of NSE monthly json chunks to rebuild the csv")
    ap.add_argument("--old-pe", help="Kaggle NIFTY 50_Historical_PE_PB_DIV.csv for pre-Nov 2015 P/E")
    args = ap.parse_args()
    if args.raw:
        build_csv(args.raw, args.old_pe)
    rows = load()
    add_indicators(rows)

    windows = {
        "2016-11 onward": (date(2016, 11, 1), STRATEGIES),
        "2000-01 onward": (date(2000, 1, 1), STRATEGIES),
    }
    out = {"data_through": rows[-1]["date"].isoformat(), "windows": {}}
    for name, (start, strats) in windows.items():
        res = {}
        for basis, label in (("close", "price"), ("tr", "tr")):
            for cash_rate in (0.0, LIQUID):
                key = f"{label}, cash {int(cash_rate * 100)}%"
                res[key] = {s: run(rows, month_days(rows, start), s, basis, cash_rate)
                            for s in strats}
        res["normal SIP, end of month (tr)"] = run(
            rows, month_days(rows, start, at_end=True), "normal", "tr", 0.0)
        out["windows"][name] = res

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "results.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"data through {out['data_through']}")
    for name, res in out["windows"].items():
        print(f"\n== {name}")
        for key, by in res.items():
            if "xirr_pct" in by:
                print(f"  {key:32s} XIRR {by['xirr_pct']:6.2f}%")
                continue
            print(f"  {key}")
            for s, m in by.items():
                print(f"    {s:7s} XIRR {m['xirr_pct']:6.2f}%  (deployed-only {m['xirr_on_deployed_only_pct']:6.2f}%)"
                      f"  bought {m['months_bought']:3d}/{m['months']}"
                      f"  max cash waiting {m['max_cash_waiting']:>8,}  left {m['cash_left']:>7,}")


if __name__ == "__main__":
    main()
