"""Year-by-year fundamentals for the ten-stock basket, as deep as they exist.

    python research/scripts/collect_s4_history.py

S4's real rule is a twelve-point fundamental screen. Running it over history
needs a fundamental series, and this assembles the deepest one obtainable
without a paid vendor: twelve financial years, Mar 2015 to Mar 2026.

WHY NOT 2006. Measured, not assumed — Yahoo carries five annual periods
(2022-2026); screener.in carries twelve (2015-2026); BSE's JSON endpoints
answer 302 without a browser session. 2006-2014 exists only in paid
point-in-time databases. Rather than fabricate it, the series starts where the
data starts and the gap is stated.

WHAT THIS IS NOT. Screener shows TODAY's figure for a past year, so a company
that restated FY2018 in 2020 shows the restated number here. A 2018 investor
saw the original. That is restatement bias, and it makes this series suitable
for studying the RULE, not for claiming a verified backtest.

Prices come from the project's own verified bhavcopy file, so P/E and P/B are
computed against the same prices every other study here uses, at each financial
year end.

Out: research/data/s4_fundamentals/history.json
"""
import html
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import httpx  # noqa: E402
from backtest_five_verified import SYMS, Data  # noqa: E402

OUT = ROOT / "research" / "data" / "s4_fundamentals"
CACHE = OUT / "cache"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Screener's slug is not always the NSE symbol.
SLUG = {"BHEL": "BHEL", "COALINDIA": "COALINDIA", "IOC": "IOC", "ITC": "ITC",
        "KTKBANK": "KTKBANK", "ONGC": "ONGC", "SCI": "SCI", "NTPC": "NTPC",
        "TATASTEEL": "TATASTEEL", "SOUTHBANK": "SOUTHBANK"}

# Banks do not report EBITDA and their leverage IS the business, so four of the
# twelve criteria are meaningless rather than missing for them.
BANKS = {"KTKBANK", "SOUTHBANK"}


def fetch(sym):
    """The company page, CONSOLIDATED where it exists, cached.

    The consolidated view matters enormously for a holding company. Coal India's
    standalone page shows Rs 387 crore of sales against Rs 13,383 crore of net
    profit, because the mines sit in subsidiaries and the parent books their
    dividends as other income. Scored on that, Coal India reads as a company
    with a -62% operating margin. The consolidated page shows the actual
    business.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{sym}.html"
    if f.exists() and f.stat().st_size > 50_000:
        return f.read_text(encoding="utf-8")
    # Banks are the exception. Their consolidated pages carry only six or seven
    # years here, and a bank's consolidated accounts add little beyond small
    # subsidiaries — so standalone is both longer and the more standard view.
    order = ((SLUG[sym], f"{SLUG[sym]}/consolidated") if sym in BANKS
             else (f"{SLUG[sym]}/consolidated", SLUG[sym]))
    for path in order:
        r = httpx.get(f"https://www.screener.in/company/{path}/",
                      headers=UA, timeout=40, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 50_000:
            f.write_text(r.text, encoding="utf-8")
            time.sleep(2.0)   # one page every two seconds; be a good guest
            return r.text
        time.sleep(2.0)
    raise RuntimeError(f"no usable screener page for {sym}")


def clean(cell):
    return html.unescape(re.sub("<[^>]+>", "", cell)).replace("\xa0", " ").strip()


def number(s):
    s = s.replace(",", "").replace("%", "").strip()
    if not s or s in {"-", "—"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def section(page, sec):
    """One screener table as {row label: {year: value}}."""
    i = page.find(f'id="{sec}"')
    if i < 0:
        return {}, []
    tab = page[i:page.find("</table>", i)]
    years = [clean(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", tab, re.S)]
    years = [y for y in years if re.match(r"^\w{3} 20\d\d$", y)]
    out = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tab, re.S):
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 2:
            continue
        label = cells[0].rstrip("+ ").strip()
        out[label] = {y: number(v) for y, v in zip(years, cells[1:])}
    return out, years


def series(table, *labels):
    for lab in labels:
        if lab in table:
            return table[lab]
    return {}


def cagr(values, years, end, back=5):
    """Compound rate over `back` years ending at `end`, or None."""
    if end not in years:
        return None
    i = years.index(end)
    j = i - back
    if j < 0:
        return None
    a, b = values.get(years[j]), values.get(end)
    # Both ends must be positive. A negative endpoint makes the fractional
    # power complex in Python, and more to the point a company that swung from
    # profit to loss has no compound growth rate — reporting one would be
    # inventing a number where the concept does not apply.
    if a is None or b is None or a <= 0 or b <= 0:
        return None
    return (b / a) ** (1 / back) - 1


def avg(values, years, end, back=5):
    if end not in years:
        return None
    i = years.index(end)
    xs = [values.get(y) for y in years[max(0, i - back + 1):i + 1]]
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def sane(sym, sales, net, years):
    """Reject a parse that cannot describe a real company.

    Net profit larger than sales is the signature of a standalone holding-company
    page, and it is silent: every ratio computes, every number looks plausible on
    its own, and the series is worthless. Better to stop here than to publish it.
    """
    bad = [y for y in years
           if sales.get(y) and net.get(y) and net[y] > sales[y]]
    if bad:
        raise RuntimeError(
            f"{sym}: net profit exceeds sales in {len(bad)} year(s) "
            f"({', '.join(bad[:3])}) — looks like a standalone page")


def collect(sym, prices):
    page = fetch(sym)
    pl, years = section(page, "profit-loss")
    bs, _ = section(page, "balance-sheet")
    cf, _ = section(page, "cash-flow")
    rt, _ = section(page, "ratios")

    sales = series(pl, "Sales", "Revenue")
    op = series(pl, "Operating Profit")
    opm = series(pl, "OPM %")
    interest = series(pl, "Interest")
    net = series(pl, "Net Profit")
    eps = series(pl, "EPS in Rs")
    cap = series(bs, "Equity Capital")
    res = series(bs, "Reserves")
    debt = series(bs, "Borrowings")
    ocf = series(cf, "Cash from Operating Activity")
    roce = series(rt, "ROCE %")
    sane(sym, sales, net, years)

    rows = []
    for y in years:
        equity = None
        if cap.get(y) is not None and res.get(y) is not None:
            equity = cap[y] + res[y]
        # Share count backed out of net profit and EPS, which lets book value
        # per share — and therefore P/B — be computed for a PAST year, which no
        # endpoint publishes directly.
        shares = (net[y] * 1e7 / eps[y]
                  if net.get(y) and eps.get(y) else None)
        bvps = (equity * 1e7 / shares) if (equity and shares) else None
        px = prices.get((sym, y))
        rows.append({
            "year": y,
            "roe_5y_avg": avg({k: (net[k] / (cap[k] + res[k]))
                               for k in years
                               if net.get(k) is not None
                               and cap.get(k) is not None
                               and res.get(k) not in (None,)
                               and (cap[k] + res[k])}, years, y),
            "roce": (roce.get(y) / 100.0) if roce.get(y) is not None else None,
            "ebitda_margin_5y_avg": (lambda v: v / 100.0 if v is not None else None)(
                avg(opm, years, y)),
            "revenue_growth_5y": cagr(sales, years, y),
            "ebitda_growth_5y": cagr(op, years, y),
            "eps_growth_5y": cagr(eps, years, y),
            "debt_to_equity": (debt[y] / equity) if (debt.get(y) is not None
                                                     and equity) else None,
            "interest_cover": (op[y] / interest[y]) if (op.get(y) and
                                                        interest.get(y)) else None,
            "operating_cash_flow": ocf.get(y),
            "price": px,
            "eps": eps.get(y),
            "pe": (px / eps[y]) if (px and eps.get(y) and eps[y] > 0) else None,
            "pb": (px / bvps) if (px and bvps and bvps > 0) else None,
        })
    return rows


TESTS = [
    ("roe_5y_avg", "ROE>15%", lambda v: v > 0.15, "A"),
    ("roce", "ROCE>15%", lambda v: v > 0.15, "A"),
    ("ebitda_margin_5y_avg", "EBITDA%>=15", lambda v: v >= 0.15, "A"),
    ("revenue_growth_5y", "Rev g>=10%", lambda v: v >= 0.10, "B"),
    ("ebitda_growth_5y", "EBITDA g>=10%", lambda v: v >= 0.10, "B"),
    ("eps_growth_5y", "EPS g>=10%", lambda v: v >= 0.10, "B"),
    ("debt_to_equity", "D/E<1", lambda v: v < 1, "C"),
    ("interest_cover", "ICov>3", lambda v: v > 3, "C"),
    ("operating_cash_flow", "OCF+", lambda v: v > 0, "C"),
]


def score(row, bank):
    pts, unknown, na = 0, [], []
    cats = {}
    for key, label, test, cat in TESTS:
        if bank and key in ("roce", "ebitda_margin_5y_avg", "ebitda_growth_5y",
                            "interest_cover"):
            na.append(label)
            continue
        v = row.get(key)
        cats.setdefault(cat, 0)
        if v is None:
            unknown.append(label)
        elif test(v):
            pts += 1
            cats[cat] += 1
    return {"points": pts, "of": 9 - len(na) - len(unknown),
            "not_applicable": na, "unknown": unknown, "by_category": cats}


def year_end_prices():
    """Closing price at each 31 March, from the project's verified price file."""
    d = Data()
    out = {}
    for sym in SYMS:
        for y in range(2015, 2027):
            cut = [x for x in d.days if x.year == y and x.month <= 3]
            if not cut:
                continue
            day = cut[-1]
            bar = d.p.get(day, {}).get(sym)
            if bar:
                out[(sym, f"Mar {y}")] = bar["close"]
    return out


def main():
    print("prices from the verified bhavcopy file…")
    prices = year_end_prices()
    data = {}
    for sym in SYMS:
        try:
            rows = collect(sym, prices)
        except Exception as e:
            print(f"  {sym:<12} FAILED {type(e).__name__}: {e}")
            continue
        bank = sym in BANKS
        for r in rows:
            r["score"] = score(r, bank)
        data[sym] = rows
        got = [r for r in rows if r["score"]["of"] > 0]
        print(f"  {sym:<12} {len(rows)} years  "
              f"{rows[0]['year']} .. {rows[-1]['year']}"
              f"{'   (bank: 4 criteria N/A)' if bank else ''}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "history.json").write_text(json.dumps({
        "source": "screener.in company pages; prices from the project's "
                  "verified bhavcopy file",
        "coverage": "Mar 2015 to Mar 2026",
        "why_not_2006": "Yahoo carries 5 annual periods, screener.in 12, BSE's "
                        "JSON endpoints refuse without a browser session. "
                        "2006-2014 is available only from paid point-in-time "
                        "vendors.",
        "bias": "Screener reports today's figure for a past year, so "
                "restatements are baked in. Suitable for studying the rule, "
                "not for claiming a verified backtest.",
        "stocks": data,
    }, indent=1), encoding="utf-8")

    hdr = (f"{'YEAR':<10}{'ROE5y':>8}{'ROCE':>8}{'EBITDA%':>9}{'REVg':>8}"
           f"{'EBITDAg':>9}{'EPSg':>8}{'D/E':>7}{'ICOV':>7}{'OCF':>6}"
           f"{'PE':>8}{'PB':>7}{'SCORE':>8}")
    def pct(v): return "—" if v is None else f"{v*100:.1f}%"
    def num(v, d=2): return "—" if v is None else f"{v:.{d}f}"
    for sym, rows in data.items():
        print(f"\n{sym}")
        print(hdr); print("-" * len(hdr))
        for r in rows:
            s = r["score"]
            tally = f"{s['points']}/{s['of']}"
            print(f"{r['year']:<10}{pct(r['roe_5y_avg']):>8}{pct(r['roce']):>8}"
                  f"{pct(r['ebitda_margin_5y_avg']):>9}{pct(r['revenue_growth_5y']):>8}"
                  f"{pct(r['ebitda_growth_5y']):>9}{pct(r['eps_growth_5y']):>8}"
                  f"{num(r['debt_to_equity']):>7}{num(r['interest_cover'],1):>7}"
                  f"{('—' if r['operating_cash_flow'] is None else ('+' if r['operating_cash_flow']>0 else '-')):>6}"
                  f"{num(r['pe'],1):>8}{num(r['pb']):>7}"
                  f"{tally:>8}")
    print(f"\nwrote {OUT / 'history.json'}")


if __name__ == "__main__":
    main()
