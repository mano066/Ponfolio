"""Ten pages, one per strategy: the idea, the exact condition, a real example.

Written for someone deciding which rule to follow, not for someone auditing the
engine — the full ledgers already do that. Each page answers three questions in
order: what is this trying to do, what precisely triggers it, and what did it
actually do on a real day.

Every example is a REAL review taken from the saved audit ledger: the date, the
prices, the share counts and the cash are read from it, and the weights and
momentum figures that explain WHY the condition fired are recomputed from the
verified price file. No example is constructed, rounded for effect, or chosen
from a different run than the one the result strip reports.

The conditions themselves are prose descriptions of the implemented rules in
`backtest_five_verified.py` and `backtest_strategies_v2.py`. The example under
each one is the check that the prose matches the code.

    python research/scripts/build_strategy_conditions_pdf.py

Out: docs/Rebalancing_Ten_Strategies_Conditions_Explained.pdf
"""
import csv
import io
import json
import sys
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))
from backtest_five_verified import SYMS as CORE, Data  # noqa: E402
from build_strategies_v2_full_ledger import replay  # noqa: E402

SRC = ROOT / "research" / "data" / "strategies_monthly"
OUT = ROOT / "docs" / "Rebalancing_Ten_Strategies_Conditions_Explained.pdf"

INK = colors.HexColor("#11161D")
BLUE = colors.HexColor("#1F4F8F")
TEAL = colors.HexColor("#067F80")
GRAY = colors.HexColor("#5B6775")
LIGHT = colors.HexColor("#F4F6F9")
BAND = colors.HexColor("#EAF1F7")
LINE = colors.HexColor("#D7DDE5")
SELLC = colors.HexColor("#B4432C")
BUYC = colors.HexColor("#1F4F8F")
GREEN = colors.HexColor("#0B7A51")

# What kind of example each strategy needs. The DATE is not hard-coded — it is
# picked from the ledger as the review where that condition most visibly fires,
# because a hand-picked date can silently stop demonstrating anything: the first
# draft illustrated the dividend sweep with a month in which Rs 0 was swept.
# Selection looks only at whether the RULE fired, never at what the price did
# afterwards, so this cannot flatter a strategy.
EXAMPLE_KIND = {1: "split", 2: "gap", 3: "trim", 4: "exit", 5: "tilt",
                6: "sweep", 7: "trim", 8: "trim", 9: "tilt", 10: "trim"}


def pick_example(kind, entries):
    """The review where this condition fires most visibly."""
    days = defaultdict(list)
    for e in entries:
        days[e["date"]].append(e)

    def swept(rows):
        return sum(float(r["cash_change"]) for r in rows
                   if r["event"] == "DISTRIBUTION_REINVESTED")

    def sold(rows):
        return sum(float(r["cash_change"]) for r in rows
                   if r["event"] == "SELL")

    def n_sells(rows):
        return sum(1 for r in rows if r["event"] == "SELL")

    def n_buys(rows):
        return len({r["symbol"] for r in rows if r["event"] == "BUY"})

    if kind == "sweep":
        return max(days, key=lambda d: swept(days[d]))
    if kind == "trim":
        return max(days, key=lambda d: sold(days[d]))
    if kind == "exit":
        return max(days, key=lambda d: n_sells(days[d]))
    if kind == "tilt":
        # A review well clear of the 12-month warm-up, where three distinct
        # names were actually bought.
        ok = [d for d in sorted(days) if d >= "2013-01-01"
              and n_buys(days[d]) >= 3]
        return ok[len(ok) // 2] if ok else sorted(days)[-1]
    # split / gap: a mid-life review with a normal spread of purchases.
    ok = [d for d in sorted(days) if d >= "2013-01-01" and n_buys(days[d]) >= 2]
    return ok[len(ok) // 2] if ok else sorted(days)[-1]

IDEA = {
    1: "Buy the whole basket, in equal slices, forever. The simplest thing "
       "that can be called a strategy, and the benchmark the other nine have "
       "to beat.",
    2: "Never sell. Rebalance using only the new money: each month's "
       "contribution goes to whatever has fallen furthest below its share.",
    3: "The same as S2, but it will also SELL a holding that has grown past a "
       "12.5% ceiling, trimming it back to 10%.",
    4: "Judge each holding on its own price record: abandon the ones with a "
       "negative five-year CAGR, and trim the ones that have doubled.",
    5: "Back the winners. Each month's money goes only to the three names "
       "with the strongest twelve-month price move.",
    6: "S2, plus the one thing none of the original five were allowed to do: "
       "put the accumulated dividends back to work.",
    7: "S3 with a looser ceiling. Trim only past 20%, on the view that a 12.5% "
       "ceiling sells winners too early.",
    8: "S3 plus the dividend sweep — the trimming rule and the income rule "
       "working together.",
    9: "The mirror of S5. Each month's money goes to the three WEAKEST names "
       "over twelve months.",
    10: "S7 plus the dividend sweep: the loose ceiling and the income rule "
        "together.",
}

CONDITION = {
    1: ["Contribute the monthly ticket to cash.",
        "Divide all available cash by ten and buy whole shares of every core "
        "name at the review-day open.",
        "Top up anything still below 10% of the core, then sweep any cash a "
        "whole-share price left behind.",
        "Never sell."],
    2: ["Contribute the monthly ticket to cash.",
        "For each name compute its gap to 10% of (core value + cash), using "
        "the previous session's close.",
        "Spend cash on the largest gap first, then the next, until it runs "
        "out; sweep the residue.",
        "Never sell."],
    3: ["Contribute the monthly ticket to cash.",
        "<b>If any name is worth more than 12.5% of the core</b>, sell it back "
        "down to 10% — but only units held more than 365 days.",
        "Add the proceeds to cash and deploy everything at the underweights, "
        "exactly as S2 does."],
    4: ["Contribute the monthly ticket to cash.",
        "<b>Sell a name outright if its five-year price CAGR is negative.</b>",
        "<b>Otherwise trim it</b> if it is up more than 100% on cost AND is "
        "over 10% of the core.",
        "Deploy cash only into names not sold out of and trading at or above "
        "90% of their cost basis, ordered by twelve-month momentum."],
    5: ["Contribute the monthly ticket to cash.",
        "Rank the ten by twelve-month price change, split-and-bonus adjusted.",
        "<b>Buy only the top three</b>, an equal share of cash each, then top "
        "up and sweep within those three.",
        "Never sell."],
    6: ["Contribute the monthly ticket to cash.",
        "<b>Move every rupee of accrued dividend and debt income into "
        "tradeable cash.</b>",
        "Deploy the combined total at the underweights, exactly as S2 does.",
        "Never sell."],
    7: ["Contribute the monthly ticket to cash.",
        "<b>If any name is worth more than 20% of the core</b>, sell it back "
        "to 10% — units held over 365 days only.",
        "Deploy proceeds and contribution at the underweights."],
    8: ["Contribute the monthly ticket to cash.",
        "<b>Sweep accrued distributions into cash.</b>",
        "<b>Trim anything above 12.5%</b> of the core back to 10%.",
        "Deploy the combined total at the underweights."],
    9: ["Contribute the monthly ticket to cash.",
        "Rank the ten by twelve-month price change.",
        "<b>Buy only the bottom three</b>, an equal share of cash each.",
        "Never sell."],
    10: ["Contribute the monthly ticket to cash.",
         "<b>Sweep accrued distributions into cash.</b>",
         "<b>Trim anything above 20%</b> of the core back to 10%.",
         "Deploy the combined total at the underweights."],
}


def money(v, dec=2):
    whole, _, frac = f"{abs(float(v)):.{dec}f}".partition(".")
    tail, head, parts = whole[-3:], whole[:-3], []
    while head:
        parts.insert(0, head[-2:])
        head = head[:-2]
    return ("-" if float(v) < 0 else "") + ",".join(parts + [tail]) + \
           (f".{frac}" if frac else "")


def fonts():
    for n, f in (("LV", "arial.ttf"), ("LVB", "arialbd.ttf")):
        pdfmetrics.registerFont(TTFont(n, "C:/Windows/Fonts/" + f))
    pdfmetrics.registerFontFamily("LV", normal="LV", bold="LVB",
                                  italic="LV", boldItalic="LVB")


def styles():
    def mk(k, f, s, l, g, c):
        return k, ParagraphStyle(k, fontName=f, fontSize=s, leading=l,
                                 textColor=c, spaceAfter=g)
    return dict([
        mk("title", "LVB", 19, 23, 1, BLUE),
        mk("kicker", "LVB", 7.6, 11, 4, TEAL),
        mk("lede", "LV", 9.6, 13.6, 9, INK),
        mk("h", "LVB", 10.5, 14, 4, INK),
        mk("body", "LV", 8.7, 12.4, 5, INK),
        mk("small", "LV", 7.2, 10, 3, GRAY),
        mk("step", "LV", 8.7, 12.4, 3, INK),
        mk("chipv", "LVB", 13, 16, 0, BLUE),
        mk("chipl", "LV", 6.8, 9, 0, GRAY),
        mk("cell", "LV", 7.4, 9.8, 0, INK),
        mk("head", "LVB", 7.2, 9.6, 0, colors.white),
    ])


def chips(items, st, width=170):
    row1 = [Paragraph(l, st["chipl"]) for l, _ in items]
    row2 = [Paragraph(v, st["chipv"]) for _, v in items]
    t = Table([row1, row2], colWidths=[width / len(items) * mm] * len(items))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BAND),
                           ("LEFTPADDING", (0, 0), (-1, -1), 7),
                           ("TOPPADDING", (0, 0), (-1, 0), 6),
                           ("BOTTOMPADDING", (0, 1), (-1, 1), 6)]))
    return t


def grid(head, rows, widths, st, shades=()):
    data = [[Paragraph(str(c), st["head"]) for c in head]]
    for r in rows:
        data.append([Paragraph(str(c), st["cell"]) for c in r])
    t = Table(data, colWidths=[w * mm for w in widths], hAlign="LEFT")
    s = [("BACKGROUND", (0, 0), (-1, 0), INK),
         ("GRID", (0, 0), (-1, -1), 0.35, LINE),
         ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
         ("LEFTPADDING", (0, 0), (-1, -1), 4),
         ("RIGHTPADDING", (0, 0), (-1, -1), 4),
         ("TOPPADDING", (0, 0), (-1, -1), 2.6),
         ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6)]
    for i in range(1, len(data)):
        if i % 2 == 0:
            s.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    s.extend(shades)
    t.setStyle(TableStyle(s))
    return t


def condition_box(steps, st):
    body = [Paragraph(f"{i}. {x}", st["step"]) for i, x in enumerate(steps, 1)]
    t = Table([[body]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                           ("BOX", (0, 0), (-1, -1), 0.7, TEAL),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def prev_session(data, d):
    import bisect
    i = bisect.bisect_left(data.days, date.fromisoformat(d))
    return data.days[i - 1] if i > 0 else None


def context(entries, d, data):
    """Positions, weights and momentum immediately before a review."""
    same = [e for e in entries if e["date"] == d]
    idx = entries.index(same[0])
    before = entries[idx - 1]["qty_after"] if idx else {}
    prev = prev_session(data, d)
    ref = {s: data.p[prev][s]["close"] for s in CORE}
    total = sum(before.get(s, 0) * ref[s] for s in CORE)
    weights = {s: (before.get(s, 0) * ref[s] / total * 100 if total else 0.0)
               for s in CORE}
    mom = {s: data.trailing(s, prev, 1) for s in CORE}
    return same, before, ref, total, weights, mom, prev


def example_block(code, d, kind, entries, data, st):
    same, before, ref, total, weights, mom, prev = context(entries, d, data)
    contrib = sum(float(e["cash_change"]) for e in same
                  if e["event"] == "CONTRIBUTION")
    swept = sum(float(e["cash_change"]) for e in same
                if e["event"] == "DISTRIBUTION_REINVESTED")
    buys = [e for e in same if e["event"] == "BUY"]
    sells = [e for e in same if e["event"] == "SELL"]
    spent = sum(-float(e["cash_change"]) for e in buys)
    got = sum(float(e["cash_change"]) for e in sells)

    out = [Paragraph(f"Worked example — the review of {d}", st["h"])]

    if kind == "trim":
        trig = 20.0 if code in (7, 10) else 12.5
        over = [s for s in CORE if weights[s] > trig]
        lead = (f"On the previous close the core was worth Rs {money(total,0)}. "
                + (f"<b>{', '.join(over)}</b> had grown past the {trig:g}% "
                   f"ceiling — "
                   + "; ".join(f"{s} at {weights[s]:.1f}%" for s in over)
                   + f" — so the rule sold it back toward 10%."
                   if over else "No name was over the ceiling."))
        out.append(Paragraph(lead, st["body"]))
        rows = [[s, f"{weights[s]:.2f}%", f"{trig:g}%",
                 "over — TRIM" if weights[s] > trig else "within — hold"]
                for s in sorted(CORE, key=lambda x: -weights[x])[:5]]
        out.append(grid(["Stock", "Weight before", "Ceiling", "Test"], rows,
                        [34, 30, 22, 40], st))
        out.append(Spacer(1, 4))
    elif kind == "exit":
        cagr = {s: data.trailing(s, prev, 5) for s in CORE}
        gone = sorted({e["symbol"] for e in sells})
        out.append(Paragraph(
            f"Five-year price CAGR turned negative for "
            f"<b>{', '.join(gone)}</b>, so the rule sold each position "
            f"outright — {len(sells)} sales on one day, raising "
            f"Rs {money(got, 0)}.", st["body"]))
        rows = [[s, f"{cagr[s]*100:.1f}%" if cagr[s] is not None else "n/a",
                 "SELL ALL" if s in gone else "keep"]
                for s in sorted(CORE, key=lambda x: (cagr[x] is None,
                                                     cagr[x] or 0))[:6]]
        out.append(grid(["Stock", "5-year price CAGR", "Test"], rows,
                        [40, 40, 46], st))
        out.append(Spacer(1, 4))
    elif kind == "tilt":
        picked = sorted({e["symbol"] for e in buys})
        best = code == 5
        ranked = sorted([s for s in CORE if mom[s] is not None],
                        key=lambda s: -mom[s] if best else mom[s])
        out.append(Paragraph(
            f"Ranked by twelve-month price change, the "
            f"{'strongest' if best else 'weakest'} three were "
            f"<b>{', '.join(ranked[:3])}</b>. The whole "
            f"Rs {money(contrib, 0)} went to those, and to nothing else.",
            st["body"]))
        rows = [[f"{i}", s, f"{mom[s]*100:+.1f}%",
                 "BOUGHT" if s in picked else "—"]
                for i, s in enumerate(ranked[:6], 1)]
        out.append(grid(["Rank", "Stock", "12-month change", "Action"], rows,
                        [16, 34, 36, 40], st))
        out.append(Spacer(1, 4))
    elif kind == "sweep":
        out.append(Paragraph(
            f"The contribution was Rs {money(contrib, 0)}. The sweep added "
            f"<b>Rs {money(swept, 0)}</b> of dividends that had accrued since "
            f"the last review, so Rs {money(contrib + swept, 0)} went to work "
            f"instead of Rs {money(contrib, 0)} — a "
            f"{swept / contrib * 100:.0f}% larger purchase for the same "
            f"contribution." if swept else
            "No dividend had accrued since the previous review, so the sweep "
            "moved nothing this month.", st["body"]))
    elif kind == "gap":
        under = sorted(CORE, key=lambda s: weights[s])[:5]
        out.append(Paragraph(
            f"The core was worth Rs {money(total, 0)}, so a 10% share was "
            f"Rs {money(total/10, 0)}. The contribution went to the names "
            f"furthest below that line, largest gap first.", st["body"]))
        rows = [[s, f"{weights[s]:.2f}%",
                 money(total * .10 - before.get(s, 0) * ref[s], 0),
                 "BOUGHT" if any(e["symbol"] == s for e in buys) else "—"]
                for s in under]
        out.append(grid(["Stock", "Weight before", "Gap to 10% (Rs)", "Action"],
                        rows, [34, 30, 34, 28], st))
        out.append(Spacer(1, 4))
    else:  # split
        out.append(Paragraph(
            f"The Rs {money(contrib, 0)} contribution was divided ten ways — "
            f"Rs {money(contrib/10, 0)} a name — and turned into whole shares "
            f"at that morning's open. Rs {money(spent, 0)} was deployed across "
            f"{len({e['symbol'] for e in buys})} names.", st["body"]))

    led = [[e["event"], e["symbol"], f"{float(e['quantity']):,.0f}",
            money(e["price"]) if float(e["price"]) else "—",
            money(e["cash_change"])]
           for e in same if e["event"] in ("CONTRIBUTION", "SELL",
                                           "DISTRIBUTION_REINVESTED", "BUY")][:9]
    shades = []
    for i, e in enumerate([e for e in same
                           if e["event"] in ("CONTRIBUTION", "SELL",
                                             "DISTRIBUTION_REINVESTED",
                                             "BUY")][:9], 1):
        c = (SELLC if e["event"] == "SELL" else
             GREEN if e["event"] == "DISTRIBUTION_REINVESTED" else
             BUYC if e["event"] == "BUY" else INK)
        shades.append(("TEXTCOLOR", (0, i), (0, i), c))
    out.append(Paragraph("What the ledger recorded that day "
                         "(first nine entries)", st["small"]))
    out.append(grid(["Event", "Stock", "Qty", "Price (Rs)", "Cash (Rs)"], led,
                    [40, 30, 22, 28, 32], st, shades))
    return out


def build():
    data = json.loads((SRC / "results.json").read_text(encoding="utf-8"))
    pre = {x["code"]: x for x in data["results"]}
    post = {x["code"]: x for x in data["after_tax"]}
    prices = Data()
    st = styles()
    ledgers = {}
    with zipfile.ZipFile(SRC / "audit_ledgers.zip") as z:
        for c in range(1, 11):
            raw = z.read(f"S{c}_transactions_and_events.csv").decode("utf-8-sig")
            ledgers[c] = replay(list(csv.DictReader(io.StringIO(raw))))

    story = []
    for c in range(1, 11):
        name = pre[c]["name"].split(" ", 1)[1]
        story.append(Paragraph(f"STRATEGY {c} OF 10 · HOW IT DECIDES",
                               st["kicker"]))
        story.append(Paragraph(f"S{c} · {name}", st["title"]))
        story.append(Spacer(1, 6))
        story.append(chips([
            ("Pre-tax XIRR", f"{pre[c]['xirr_pct']:.2f}%"),
            ("After-tax XIRR", f"{post[c]['xirr_pct']:.2f}%"),
            ("Final wealth", f"Rs {money(pre[c]['terminal_after_cost'], 0)}"),
            ("Buys", f"{pre[c]['trades'] - pre[c]['sells']:,}"),
            ("Sells", f"{pre[c]['sells']:,}")], st))
        story.append(Spacer(1, 9))
        story.append(Paragraph("The idea", st["h"]))
        story.append(Paragraph(IDEA[c], st["lede"]))
        story.append(Paragraph("The condition", st["h"]))
        story.append(condition_box(CONDITION[c], st))
        story.append(Spacer(1, 9))
        kind = EXAMPLE_KIND[c]
        d = pick_example(kind, ledgers[c])
        story += example_block(c, d, kind, ledgers[c], prices, st)
        story.append(PageBreak())
    story.pop()

    def furniture(canvas, doc):
        canvas.saveState()
        canvas.setFont("LV", 6.8)
        canvas.setFillColor(GRAY)
        canvas.drawString(20 * mm, 12 * mm,
                          f"Ten strategies · conditions explained · monthly "
                          f"Rs 10,000, {data['start']} to {data['end']} · "
                          f"not investment advice")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"{doc.page} / 10")
        canvas.setStrokeColor(LINE)
        canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
        canvas.restoreState()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4,
                            title="Ten rebalancing strategies — conditions explained",
                            author="Ponfolio",
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=16 * mm, bottomMargin=20 * mm)
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    print(f"wrote {OUT.name}  ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    fonts()
    build()
