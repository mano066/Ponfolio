"""Collect the fundamental data S4's real rule needs, for the ten-stock basket.

    python research/scripts/collect_s4_fundamentals.py

S4 in the backtest is a price-only proxy. The actual rule it stands for is a
twelve-point fundamental screen (ROE, ROCE, margins, growth, leverage, cash
flow, promoter integrity) followed by a P/E and P/B gate. None of that data is
in the price file, so step one is finding out how much of it can be obtained at
all.

Where the summary endpoint does not publish a figure, it is DERIVED from the
annual statements — ROE from net income over equity, ROCE from EBIT over
capital employed, interest coverage from EBIT over interest expense, and the
growth rates as compound rates across the years actually on file. Anything that
cannot be derived is reported as unavailable rather than defaulted, because a
missing ROE scored as a fail is a fabricated verdict.

Out: research/data/s4_fundamentals/fundamentals.json
"""
import json
import math
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import yfinance as yf  # noqa: E402
from backtest_five_verified import SYMS  # noqa: E402

OUT = ROOT / "research" / "data" / "s4_fundamentals"

# The basket the whole study runs on, as Yahoo tickers.
TICKER = {s: f"{s}.NS" for s in SYMS}

# Criteria that no public endpoint used here publishes. Named explicitly so the
# report says "not obtainable" rather than quietly scoring them zero.
UNOBTAINABLE = {
    "dii_change_6m": "DII shareholding change — NSE/BSE filings only",
    "fii_change_6m": "FII shareholding change — NSE/BSE filings only",
    "promoter_pledge_pct": "Promoter pledge — NSE/BSE filings only",
}


def pick(frame, *names):
    """First matching row of a statement, as a date-ordered list of floats."""
    if frame is None or getattr(frame, "empty", True):
        return []
    for n in names:
        for idx in frame.index:
            if str(idx).strip().lower() == n.lower():
                row = frame.loc[idx]
                out = []
                for v in row:
                    try:
                        f = float(v)
                    except (TypeError, ValueError):
                        continue
                    if not math.isnan(f):
                        out.append(f)
                # Yahoo returns newest-first; oldest-first reads better.
                return list(reversed(out))
    return []


def cagr(series):
    """Compound rate across the years on file, or None if it cannot be formed.

    A negative or zero starting value has no meaningful growth rate — a company
    that went from a loss to a profit cannot be said to have grown at x% a year.
    """
    if len(series) < 2 or series[0] <= 0:
        return None
    years = len(series) - 1
    return (series[-1] / series[0]) ** (1 / years) - 1


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def collect(sym, ticker):
    t = yf.Ticker(ticker)
    info = t.info or {}
    inc, bal, cf = t.financials, t.balance_sheet, t.cashflow

    revenue = pick(inc, "Total Revenue", "Operating Revenue")
    ebitda = pick(inc, "EBITDA", "Normalized EBITDA")
    ebit = pick(inc, "EBIT", "Operating Income")
    net = pick(inc, "Net Income", "Net Income Common Stockholders")
    eps = pick(inc, "Diluted EPS", "Basic EPS")
    interest = pick(inc, "Interest Expense", "Interest Expense Non Operating")
    equity = pick(bal, "Stockholders Equity", "Total Equity Gross Minority Interest")
    assets = pick(bal, "Total Assets")
    curliab = pick(bal, "Current Liabilities", "Total Current Liabilities")
    debt = pick(bal, "Total Debt")
    ocf = pick(cf, "Operating Cash Flow", "Total Cash From Operating Activities")

    yrs = len(revenue)
    roe_series = [n / e for n, e in zip(net, equity) if e]
    roce_series = [b / (a - c) for b, a, c in zip(ebit, assets, curliab)
                   if a and c is not None and (a - c)]
    margin_series = [e / r for e, r in zip(ebitda, revenue) if r]

    de = None
    if debt and equity and equity[-1]:
        de = debt[-1] / equity[-1]
    elif isinstance(info.get("debtToEquity"), (int, float)):
        de = info["debtToEquity"] / 100.0        # Yahoo reports this as a %

    cover = None
    if ebit and interest and interest[-1]:
        cover = ebit[-1] / abs(interest[-1])

    return {
        "symbol": sym,
        "ticker": ticker,
        "years_on_file": yrs,
        "roe_5y_avg": mean(roe_series),
        "roce_latest": roce_series[-1] if roce_series else None,
        "ebitda_margin_avg": mean(margin_series),
        "revenue_growth": cagr(revenue),
        "ebitda_growth": cagr(ebitda),
        "eps_growth": cagr(eps),
        "debt_to_equity": de,
        "interest_cover": cover,
        "operating_cash_flow": ocf[-1] if ocf else None,
        "pe": info.get("trailingPE"),
        "pb": info.get("priceToBook"),
        "sector": info.get("sector"),
        **{k: None for k in UNOBTAINABLE},
    }


# (key, label, test) — the twelve points, in the order the framework states them.
CRITERIA = [
    ("roe_5y_avg", "5y ROE >15%", lambda v: v > 0.15),
    ("roce_latest", "ROCE >15%", lambda v: v > 0.15),
    ("ebitda_margin_avg", "EBITDA margin >=15%", lambda v: v >= 0.15),
    ("revenue_growth", "Revenue growth >=10%", lambda v: v >= 0.10),
    ("ebitda_growth", "EBITDA growth >=10%", lambda v: v >= 0.10),
    ("eps_growth", "EPS growth >=10%", lambda v: v >= 0.10),
    ("debt_to_equity", "Debt/Equity <1", lambda v: v < 1),
    ("interest_cover", "Interest cover >3", lambda v: v > 3),
    ("operating_cash_flow", "Operating cash flow +", lambda v: v > 0),
    ("dii_change_6m", "DII change not negative", lambda v: v >= 0),
    ("fii_change_6m", "FII change not negative", lambda v: v >= 0),
    ("promoter_pledge_pct", "Promoter pledge <10%", lambda v: v < 10),
]
CATEGORY = {0: "A profitability", 1: "A profitability", 2: "A profitability",
            3: "B growth", 4: "B growth", 5: "B growth",
            6: "C cash flow", 7: "C cash flow", 8: "C cash flow",
            9: "D promoter", 10: "D promoter", 11: "D promoter"}


def score(row):
    """The twelve-point score, with unscorable criteria kept separate.

    Scored, failed and unavailable are three different outcomes. Collapsing the
    third into the second would let a data gap eliminate a company.
    """
    points, fails, unknown, by_cat = 0, [], [], {}
    for i, (key, label, test) in enumerate(CRITERIA):
        cat = CATEGORY[i]
        by_cat.setdefault(cat, {"points": 0, "unknown": 0})
        v = row.get(key)
        if v is None:
            unknown.append(label)
            by_cat[cat]["unknown"] += 1
        elif test(v):
            points += 1
            by_cat[cat]["points"] += 1
        else:
            fails.append(label)
    return {"points": points, "of_scorable": 12 - len(unknown),
            "unknown": unknown, "failed": fails, "by_category": by_cat}


def pct(v, dec=1):
    return "—" if v is None else f"{v * 100:.{dec}f}%"


def main():
    rows = []
    for sym in SYMS:
        try:
            r = collect(sym, TICKER[sym])
        except Exception as e:
            print(f"  {sym:<12} FAILED {type(e).__name__}: {e}", flush=True)
            continue
        r["score"] = score(r)
        rows.append(r)
        print(f"  {sym:<12} {r['years_on_file']}y on file  "
              f"score {r['score']['points']}/{r['score']['of_scorable']} "
              f"scorable  ({len(r['score']['unknown'])} unavailable)", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fundamentals.json").write_text(
        json.dumps({"unobtainable": UNOBTAINABLE, "stocks": rows}, indent=1),
        encoding="utf-8")

    hdr = (f"{'STOCK':<12}{'ROE5y':>8}{'ROCE':>8}{'EBITDA%':>9}{'REV g':>8}"
           f"{'EBITDA g':>9}{'EPS g':>8}{'D/E':>7}{'ICOV':>7}{'OCF':>6}"
           f"{'PE':>7}{'PB':>6}{'SCORE':>8}")
    print("\n" + hdr)
    print("-" * len(hdr))
    def num(v, dec=2, width=7):
        return ("—" if v is None else f"{v:.{dec}f}").rjust(width)

    def sign(v):
        return "—" if v is None else ("+" if v > 0 else "-")

    for r in rows:
        s = r["score"]
        tally = f"{s['points']}/{s['of_scorable']}"
        print(f"{r['symbol']:<12}"
              f"{pct(r['roe_5y_avg']):>8}{pct(r['roce_latest']):>8}"
              f"{pct(r['ebitda_margin_avg']):>9}{pct(r['revenue_growth']):>8}"
              f"{pct(r['ebitda_growth']):>9}{pct(r['eps_growth']):>8}"
              f"{num(r['debt_to_equity'], 2, 7)}"
              f"{num(r['interest_cover'], 1, 7)}"
              f"{sign(r['operating_cash_flow']):>6}"
              f"{num(r['pe'], 1, 7)}{num(r['pb'], 2, 6)}"
              f"{tally:>8}")

    print(f"\nwrote {OUT / 'fundamentals.json'}")


if __name__ == "__main__":
    main()
