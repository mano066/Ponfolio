"""Independent re-computation of research/data/smart_sip/rules.json.

Shares no code with smart_sip_backtest.py / smart_sip_rules.py: it re-reads the
csv, rebuilds every indicator a different way (prefix sums for the 200-day
average, explicit 252-session windows, its own P/E average), re-implements all
21 rules from their written definitions, solves XIRR by Newton's method with a
bisection fallback, and checks NPV at the solved rate is ~0. It then compares
every XIRR, rupees-in and value against rules.json.

Also checks the data itself: no gaps over 6 calendar days, positive closes, no
day-on-day move beyond 15% other than known circuit days, and P/E present from
1999 on.

    python research/scripts/verify_smart_sip_rules.py
"""
import csv
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "nifty50_nse_daily_1999.csv")
RES = os.path.join(ROOT, "data", "smart_sip", "rules.json")
SIP = 10_000.0
LIQ_M = 1.06 ** (1 / 12) - 1


def read():
    d, c, pe = [], [], []
    last_pe = None
    with open(CSV) as fh:
        for r in csv.DictReader(fh):
            d.append(date.fromisoformat(r["date"]))
            c.append(float(r["close"]))
            if r["pe"]:
                last_pe = float(r["pe"])
            pe.append(last_pe)
    return d, c, pe


def check_data(d, c, pe):
    problems = []
    for a, b in zip(d, d[1:]):
        if (b - a).days > 6:
            problems.append(f"gap {a}..{b}")
        if b <= a:
            problems.append(f"order {a} {b}")
    big = [(d[i], round(c[i] / c[i - 1] - 1, 3)) for i in range(1, len(c)) if abs(c[i] / c[i - 1] - 1) > 0.15]
    if any(x <= 0 for x in c):
        problems.append("non-positive close")
    first_pe = next(i for i, x in enumerate(pe) if x is not None)
    return problems, big, d[first_pe]


def indicators(c, pe):
    n = len(c)
    pre = [0.0]
    for x in c:
        pre.append(pre[-1] + x)
    dma = [(pre[i + 1] - pre[i - 199]) / 200 if i >= 199 else None for i in range(n)]
    hi = [max(c[max(0, i - 251):i + 1]) for i in range(n)]
    lo = [min(c[max(0, i - 251):i + 1]) for i in range(n)]
    pe_avg = []
    for i in range(n):
        w = [x for x in pe[max(0, i - 251):i + 1] if x is not None]
        pe_avg.append(sum(w) / len(w) if len(w) >= 240 else None)
    low_on, state = [], False
    for i in range(n):
        if i >= 251:
            if c[i] >= hi[i]:
                state = False
            elif c[i] <= lo[i]:
                state = True
        low_on.append(state)
    dd = [1 - c[i] / hi[i] for i in range(n)]
    return dma, pe_avg, low_on, dd


def first_days(d, start):
    seen, out = set(), []
    for i, x in enumerate(d):
        if x >= start and (x.year, x.month) not in seen:
            seen.add((x.year, x.month))
            out.append(i)
    return out


def npv(rate, flows):
    t0 = flows[0][0]
    return sum(v / (1 + rate) ** ((t - t0).days / 365.0) for t, v in flows)


def solve_xirr(flows):
    flows = sorted(flows)
    r = 0.1
    for _ in range(100):
        f = npv(r, flows)
        h = 1e-6
        df = (npv(r + h, flows) - f) / h
        if df == 0:
            break
        nr = r - f / df
        if abs(nr - r) < 1e-10:
            r = nr
            break
        r = max(-0.9, nr)
    if abs(npv(r, flows)) > 1e-3 * sum(abs(v) for _, v in flows):
        lo, hi = -0.9, 1.0
        for _ in range(300):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if npv(mid, flows) > 0 else (lo, mid)
        r = (lo + hi) / 2
    assert abs(npv(r, flows)) < 1.0, "NPV not ~0 at solved rate"
    return r


def simulate(rule, d, c, pe, ind, start):
    dma, pe_avg, low_on, dd = ind
    days = first_days(d, start)
    cheap_avg = lambda j: pe_avg[j] is not None and pe[j] < pe_avg[j]
    pe_lt = lambda t: (lambda j: pe[j] is not None and pe[j] < t)
    below = lambda j: dma[j] is not None and c[j] < dma[j]
    dip = lambda x: (lambda j: dd[j] >= x)
    low = lambda j: low_on[j]

    def band(j):
        p = pe[j]
        if p is None:
            return SIP
        return 2 * SIP if p < 18 else SIP if p < 22 else SIP / 2 if p < 25 else SIP / 4

    def scaled(j):
        return SIP if pe_avg[j] is None else min(3 * SIP, SIP * (pe_avg[j] / pe[j]) ** 3)

    # rule -> (base share, stepup, extra signal, extra amt, pile share, pile signal, amount fn)
    R = {
        "1": (1, 0, None, 0, 0, None, None), "2": (1, .10, None, 0, 0, None, None),
        "3": (1, .05, None, 0, 0, None, None),
        "4": (1, 0, cheap_avg, SIP, 0, None, None), "5": (1, 0, pe_lt(20), SIP, 0, None, None),
        "6": (1, 0, pe_lt(18), 2 * SIP, 0, None, None), "7": (1, 0, below, SIP, 0, None, None),
        "8": (1, 0, dip(.10), SIP, 0, None, None), "9": (1, 0, dip(.20), 2 * SIP, 0, None, None),
        "10": (1, 0, low, SIP, 0, None, None),
        "11": (0, 0, None, 0, 0, None, band), "12": (0, 0, None, 0, 0, None, scaled),
        "13": (0, 0, None, 0, 1, cheap_avg, None), "14": (.5, 0, None, 0, .5, cheap_avg, None),
        "15": (0, 0, None, 0, 1, pe_lt(20), None), "16": (.8, 0, None, 0, .2, pe_lt(20), None),
        "17": (0, 0, None, 0, 1, below, None), "18": (0, 0, None, 0, 1, low, None),
        "19": (.8, 0, None, 0, .2, dip(.10), None),
        "21": (1, 0, None, 0, 0, None, None),
    }
    units, pile, flows = 0.0, 0.0, []
    if rule == "20":
        for k, i in enumerate(days):
            target = SIP * (1.01 ** (k + 1) - 1) / 0.01
            amt = min(3 * SIP, max(0.0, target - units * c[i]))
            units += amt / c[i]
            flows.append((d[i], -amt))
    else:
        base, step, xs, xa, ps, psig, amtf = R[rule]
        for i in days:
            j = i - 1
            if amtf:
                amt = amtf(j)
                units += amt / c[i]
                flows.append((d[i], -amt))
                continue
            size = SIP * (1 + step) ** (d[i].year - start.year)
            buy, paid = size * base, size * base
            if xs and xs(j):
                buy += xa
                paid += xa
            if psig:
                pile = pile * (1 + LIQ_M) + size * ps
                paid += size * ps
                if psig(j):
                    buy += pile
                    pile = 0.0
            units += buy / c[i]
            flows.append((d[i], -paid))
        if rule == "21":
            for i in range(days[0] + 1, len(c)):
                if c[i - 1] / c[i - 2] - 1 <= -0.02:
                    units += SIP / c[i]
                    flows.append((d[i], -SIP))
    value = units * c[-1] + pile
    paid = -sum(v for _, v in flows)
    return solve_xirr(flows + [(d[-1], value)]) * 100, paid / 1e5, value / 1e5


def main():
    d, c, pe = read()
    problems, big, pe_from = check_data(d, c, pe)
    print(f"data: {len(d)} sessions {d[0]}..{d[-1]}, P/E from {pe_from}")
    print(f"  problems: {problems or 'none'}")
    print(f"  daily moves over 15%: {big or 'none'}")
    ind = indicators(c, pe)
    res = json.load(open(RES))
    worst, rows = 0.0, 0
    for label, by in res["rules"].items():
        rule = label.split()[0]
        for wy, m in by.items():
            if wy == "group":
                continue
            x, paid, val = simulate(rule, d, c, pe, ind, date(int(wy), 1, 1))
            dx = abs(x - m["xirr_pct"])
            dp = abs(paid - m["paid_lakh"])
            dv = abs(val - m["value_lakh"])
            worst = max(worst, dx)
            rows += 1
            if dx > 0.011 or dp > 0.11 or dv > 0.11:
                print(f"  MISMATCH {label} {wy}: xirr {x:.3f} vs {m['xirr_pct']}, "
                      f"paid {paid:.2f} vs {m['paid_lakh']}, value {val:.2f} vs {m['value_lakh']}")
    print(f"checked {rows} results, worst XIRR difference {worst:.4f} pct points")
    return 0 if worst <= 0.011 else 1


if __name__ == "__main__":
    sys.exit(main())
