"""Full annual ledger for S1-S10, every year, in at most 25 pages.

The companion to the result PDF. That one argues; this one shows the working —
for each of the ten strategies, what it held, what it bought and sold, what it
was owed and what it was worth, at every one of the sixteen annual reviews.

Layout is two pages per strategy plus one of front matter (21 total):

    page A   the money — contribution, trades, equity, cash, distributions,
             wealth and the multiple on invested capital, year by year
    page B   the shares — closing quantity of every instrument at every
             review, with the corporate actions that changed them

Landscape, because a twelve-instrument holdings matrix does not fit portrait
without shrinking past readability.

Every figure is read from the saved engine output and the audit ledgers —
`research/data/strategies_v2/results.json` and `audit_ledgers.zip`. Nothing is
recomputed here, so this document cannot disagree with the engine.

    python research/scripts/build_strategies_v2_ledger_pdf.py

Out: docs/Rebalancing_Strategies_S1_S10_Full_Annual_Ledgers_2011_2026.pdf
"""
import csv
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[2]

# One builder, two schedules. The annual study and the monthly SIP emit the
# same result shape, so the only thing that differs is where to read and what
# to call the output.
SCHEDULES = {
    "annual": dict(
        src=ROOT / "research/data/strategies_v2",
        out=ROOT / "docs/Rebalancing_Strategies_S1_S10_Full_Annual_Ledgers_2011_2026.pdf",
        title="S1-S10, every year, 2011-2026",
        eyebrow="FULL ANNUAL LEDGERS", review_phrase="sixteen annual reviews", footer="full annual ledgers",
        row="Review"),
    # The published monthly document now carries the six masters beside the
    # ten strategies, so it reads the combined dataset.
    "monthly": dict(
        src=ROOT / "research/data/strategies_all",
        out=ROOT / "docs/Rebalancing_Strategies_S1_S10_Monthly_SIP_Ledgers_2011_2026.pdf",
        title="S1-S10 and M1-M6 on a monthly Rs 10,000 SIP, 2011-2026",
        eyebrow="MONTHLY SIP LEDGERS", review_phrase="sixteen year-end reviews (the last of each year's twelve monthly contributions; every month is in the CSV ledgers)", footer="monthly SIP ledgers",
        row="Year end"),
}
BASE = SCHEDULES["annual"]["src"]
OUT = SCHEDULES["annual"]["out"]

# The ten core names plus the two instruments that arrive only by demerger.
SYMS = ("BHEL COALINDIA IOC ITC KTKBANK ONGC SCI NTPC TATASTEEL SOUTHBANK "
        "ITCHOTELS SCILAL").split()
# Column headings. The full symbols wrap mid-word in a 15mm column
# ("COALINDI/A"), which reads worse than a familiar abbreviation.
SHORT = {"COALINDIA": "COAL IND", "KTKBANK": "KTK BANK",
         "TATASTEEL": "TATA STL", "SOUTHBANK": "STH BANK",
         "ITCHOTELS": "ITC HOTL"}

INK = colors.HexColor("#163443")
TEAL = colors.HexColor("#067F80")
GRAY = colors.HexColor("#536B76")
LIGHT = colors.HexColor("#EFF5F6")
LINE = colors.HexColor("#D4E1E6")
BUY = colors.HexColor("#0B7A51")
SELL = colors.HexColor("#B4432C")
GOLD = colors.HexColor("#A46A40")
PAGE = landscape(A4)


def money(x, dec=0):
    """Indian digit grouping: 51,85,877 not 5,185,877."""
    whole, _, frac = f"{abs(float(x)):.{dec}f}".partition(".")
    tail, head, parts = whole[-3:], whole[:-3], []
    while head:
        parts.insert(0, head[-2:])
        head = head[:-2]
    out = ",".join(parts + [tail])
    return ("-" if float(x) < 0 else "") + out + (f".{frac}" if frac else "")


def fonts():
    for name, file in (("LV", "arial.ttf"), ("LVB", "arialbd.ttf")):
        pdfmetrics.registerFont(TTFont(name, "C:/Windows/Fonts/" + file))
    pdfmetrics.registerFontFamily("LV", normal="LV", bold="LVB",
                                  italic="LV", boldItalic="LVB")


def styles():
    mk = lambda k, f, s, l, g, c: (k, ParagraphStyle(
        k, fontName=f, fontSize=s, leading=l, textColor=c, spaceAfter=g))
    return dict([
        mk("title", "LVB", 18, 22, 4, INK),
        mk("sub", "LV", 9, 12.5, 10, GRAY),
        mk("eyebrow", "LVB", 7.6, 11, 5, TEAL),
        mk("h", "LVB", 11.5, 15, 5, INK),
        mk("body", "LV", 8.4, 12, 6, INK),
        mk("small", "LV", 7, 9.8, 4, GRAY),
        mk("cell", "LV", 6.6, 8.6, 0, INK),
        mk("cellb", "LVB", 6.6, 8.6, 0, INK),
        mk("head", "LVB", 6.6, 8.6, 0, colors.white),
    ])


def grid(head, rows, widths, st, bold_rows=(), tints=()):
    data = [[Paragraph(str(c), st["head"]) for c in head]]
    for i, r in enumerate(rows):
        s = st["cellb"] if i in bold_rows else st["cell"]
        data.append([Paragraph(str(c), s) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
    ]
    for i in bold_rows:
        style.append(("BACKGROUND", (0, i + 1), (-1, i + 1), LIGHT))
    style.extend(tints)
    t.setStyle(TableStyle(style))
    return t


def load(src):
    data = json.loads((src / "results.json").read_text(encoding="utf-8"))
    ledgers = {}
    # Whatever the dataset contains, rather than a hardcoded ten — the same
    # builder now has to render S1-S10 alone or S1-S10 beside M1-M6.
    codes = [r["code"] for r in data["results"]]
    with zipfile.ZipFile(src / "audit_ledgers.zip") as z:
        for code in codes:
            raw = z.read(f"S{code}_transactions_and_events.csv").decode("utf-8-sig")
            ledgers[code] = list(csv.DictReader(io.StringIO(raw)))
    return data, ledgers, codes


def tag(code):
    """S1-S10 keep their number; 11 and up are the masters, M1 onward.

    The zip entries are all keyed `S<code>` because that is how the engine
    writes them, but printing "S14" on a master's page would name a strategy
    that does not exist.
    """
    return f"S{code}" if code <= 10 else f"M{code - 10}"


def per_year(rows):
    """Trades and corporate actions grouped by calendar year."""
    out = defaultdict(lambda: dict(buy_n=0, buy_rs=0.0, sell_n=0, sell_rs=0.0,
                                   swept=0.0, paid=0.0, paid_n=0, events=[]))
    for r in rows:
        y = int(r["date"][:4])
        e, q = r["event"], float(r["quantity"] or 0)
        cash = float(r["cash_change"] or 0)
        if e == "CONTRIBUTION":
            out[y]["paid"] += cash
            out[y]["paid_n"] += 1
        elif e == "BUY":
            out[y]["buy_n"] += 1
            out[y]["buy_rs"] += -cash
        elif e == "SELL":
            out[y]["sell_n"] += 1
            out[y]["sell_rs"] += cash
        elif e == "DISTRIBUTION_REINVESTED":
            out[y]["swept"] += cash
        elif e in ("SPLIT", "BONUS", "DEMERGER", "RIGHTS_LAPSE",
                   "DEBENTURE_ENTITLEMENT", "BUYBACK_NOT_TENDERED"):
            label = {"RIGHTS_LAPSE": "rights lapsed",
                     "DEBENTURE_ENTITLEMENT": "NCD entitlement",
                     "BUYBACK_NOT_TENDERED": "buyback not tendered"}.get(
                         e, e.lower())
            out[y]["events"].append(f"{r['symbol']} {label}"
                                    + (f" +{q:,.0f}" if q and e in
                                       ("SPLIT", "BONUS", "DEMERGER") else ""))
    return out


def money_page(res, yearly, st, row_label='Review'):
    """Page A — the money, year by year."""
    head = [row_label, "Paid in year", "Invested (cum)", "Buys", "Sells",
            "Swept in", "Equity", "Cash", "Distributions held", "Wealth",
            "× invested"]
    rows, bold = [], []
    for a in res["annual"]:
        y = int(a["date"][:4])
        k = yearly[y]
        dist = a["dividends_earned"] + a["ntpc_scheduled_income"]
        rows.append([
            a["date"],
            f"{money(k['paid'])} ({k['paid_n']})" if k["paid_n"] else "—",
            money(a["invested"]),
            f"{money(k['buy_rs'])} ({k['buy_n']})" if k["buy_n"] else "—",
            f"{money(k['sell_rs'])} ({k['sell_n']})" if k["sell_n"] else "—",
            money(k["swept"]) if k["swept"] else "—",
            money(a["equity"]), money(a["cash"]), money(dist),
            money(a["wealth"]),
            f"{a['wealth'] / a['invested']:.2f}×",
        ])
    final_dist = res["dividends"] + res["ntpc_income"]
    rows.append([f"{FINAL_DATE} FINAL", "—", money(res["invested"]), "—", "—",
                 "—", money(res["equity"]), money(res["cash"]),
                 money(final_dist), money(res["wealth"]),
                 f"{res['wealth'] / res['invested']:.2f}×"])
    bold.append(len(rows) - 1)
    widths = [24, 21, 24, 30, 30, 20, 27, 18, 25, 27, 17]
    return grid(head, rows, [w * mm for w in widths], st, bold)


def holdings_page(res, yearly, st, row_label='Review'):
    """Page B — the shares, and the events that changed them."""
    head = ([row_label] + [SHORT.get(s, s) for s in SYMS]
            + ["Corporate actions that year"])
    rows, bold = [], []
    for a in res["annual"]:
        h = a["holdings"]
        rows.append([a["date"]] + [f"{h.get(s, 0):,}" if h.get(s) else "·"
                                   for s in SYMS]
                    + ["; ".join(yearly[int(a["date"][:4])]["events"]) or "—"])
    final = {x["symbol"]: x["quantity"] for x in res["holdings"]}
    rows.append(["FINAL"] + [f"{final.get(s, 0):,.0f}" if final.get(s) else "·"
                             for s in SYMS] + ["—"])
    bold.append(len(rows) - 1)
    widths = [19] + [15] * len(SYMS) + [45]
    return grid(head, rows, [w * mm for w in widths], st, bold)


def build(cfg):
    global FINAL_DATE
    data, ledgers, codes = load(cfg['src'])
    FINAL_DATE = data['end']
    row_label = cfg['row']
    pre = {x["code"]: x for x in data["results"]}
    post = {x["code"]: x for x in data["after_tax"]}
    st = styles()
    story = []

    # ── front matter ──
    story.append(Paragraph(f"REBALANCING RESEARCH · {cfg['eyebrow']}",
                           st["eyebrow"]))
    story.append(Paragraph(cfg["title"].replace("-", "–"), st["title"]))
    story.append(Paragraph(
        f"{data['start']} to {data['end']} · {data['sessions']:,} sessions · "
        f"{data.get('schedule') or data['contributions']} · "
        f"{data['cost_bps']} bps costs · whole "
        f"shares, official NSE opens, real corporate actions · basket: "
        f"{', '.join(data['basket'])}", st["sub"]))
    story.append(Paragraph(
        "This is the working behind the result PDF. For each strategy, page A "
        "is the money — what went in, what was traded, what was held in cash "
        f"and distributions, and what the book was worth at each of the "
        f"{cfg['review_phrase']}. Page B is the shares — the closing quantity "
        f"of every instrument at those same points, alongside the corporate "
        f"actions that "
        "changed them. Both are read from the saved engine output and the "
        "audit ledgers, so neither can disagree with the engine that produced "
        "them.", st["body"]))
    story.append(Paragraph(
        "<b>Reading the columns.</b> <i>Paid in year</i> is what was "
        "contributed that year and how many payments made it up. "
        "<i>Invested</i> is cumulative contributions. "
        "<i>Distributions held</i> is dividend and scheduled debt income "
        "accrued but not yet spent — it is the number the reinvesting "
        "strategies drive to nearly zero and the others let grow. "
        "<i>Swept in</i> is that pile moved into tradeable cash, and appears "
        "only for S6, S8 and S10. <i>Wealth</i> is equity plus cash plus "
        "distributions held. <i>× invested</i> is wealth over contributions "
        "to date — a multiple, not a return; the XIRR is on the summary "
        "below because a multiple ignores when each rupee arrived.",
        st["body"]))
    story.append(Spacer(1, 6))

    summary_head = ["#", "Strategy", "Pre-tax XIRR", "After-tax XIRR",
                    "Terminal (pre-tax)", "Buys", "Sells",
                    "Distributions held", "Ledger pages"]
    srows = []
    for c in codes:
        r = pre[c]
        srows.append([tag(c), r["name"], f"{r['xirr_pct']:.2f}%",
                      f"{post[c]['xirr_pct']:.2f}%",
                      money(r["terminal_after_cost"]),
                      str(r["trades"] - r["sells"]), str(r["sells"]),
                      money(r["dividends"] + r["ntpc_income"]),
                      f"{2 + codes.index(c) * 2}–{3 + codes.index(c) * 2}"])
    # Shade whichever two actually lead after tax, found rather than fixed.
    # The old hardcoded pair pointed at S6 and S10 while the caption named the
    # computed leaders, so the table highlighted two rows and the sentence
    # beneath it named two others.
    top2 = sorted(post.values(), key=lambda x: -x["xirr_pct"])[:2]
    lead = {x["code"] for x in top2}
    story.append(grid(summary_head, srows,
                      [10 * mm, 62 * mm, 22 * mm, 24 * mm, 30 * mm, 14 * mm,
                       14 * mm, 30 * mm, 22 * mm], st,
                      # 0-based over the DATA rows, header excluded — the
                      # original [5, 9] meant S6 and S10.
                      bold_rows=[i for i, c in enumerate(codes)
                                 if c in lead]))
    same = (abs(pre[6]["terminal_after_cost"] - pre[10]["terminal_after_cost"])
            < 1.0)
    story.append(Paragraph(
        f"Shaded: {tag(top2[0]['code'])} and {tag(top2[1]['code'])}, the two best "
        f"after tax, both ahead of S3's {post[3]['xirr_pct']:.2f}%. "
        + ("S6 and S10 are identical on this data — with dividends reinvested "
           "the book never reaches a 20% weight, so S10's wider band never "
           "fires and the two ledgers match line for line."
           if same else
           f"Unlike the annual schedule, S10 is NOT identical to S6 here: "
           f"evaluated monthly its 20% band does fire ({pre[10]['sells']} "
           f"sells), which is what separates them."), st["small"]))
    story.append(PageBreak())

    # ── two pages per strategy ──
    for code in codes:
        res, yearly = pre[code], per_year(ledgers[code])
        for page, make in (("A · the money", money_page),
                           ("B · the shares", holdings_page)):
            story.append(Paragraph(f"{tag(code)} · {res['name'].split(' ', 1)[1]}"
                                   f" — page {page}", st["eyebrow"]))
            story.append(Paragraph(
                f"{res['name']} &nbsp;·&nbsp; pre-tax "
                f"{res['xirr_pct']:.2f}% &nbsp;·&nbsp; after tax "
                f"{post[code]['xirr_pct']:.2f}% &nbsp;·&nbsp; "
                f"{res['trades'] - res['sells']} buys, {res['sells']} sells "
                f"&nbsp;·&nbsp; terminal Rs {money(res['terminal_after_cost'])}",
                st["h"]))
            story.append(make(res, yearly, st, row_label))
            if make is holdings_page and res["fractions"]:
                story.append(Spacer(1, 4))
                story.append(Paragraph(
                    "Fractional entitlements excluded (no verified proceeds): "
                    + "; ".join(f"{f['symbol']} {f['quantity']:.4f} on "
                                f"{f['date']}" for f in res["fractions"]),
                    st["small"]))
            story.append(PageBreak())

    story.pop()  # trailing PageBreak

    def furniture(canvas, doc):
        canvas.saveState()
        canvas.setFont("LV", 6.8)
        canvas.setFillColor(GRAY)
        canvas.drawString(14 * mm, 9 * mm,
                          "Ponfolio · rebalancing research · "
                          f"S1–S10 {cfg['footer']} · pre-tax unless a "
                          "column says otherwise · not investment advice")
        canvas.drawRightString(PAGE[0] - 14 * mm, 9 * mm, f"{doc.page}")
        canvas.setStrokeColor(LINE)
        canvas.line(14 * mm, 12 * mm, PAGE[0] - 14 * mm, 12 * mm)
        canvas.restoreState()

    cfg["out"].parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(cfg["out"]), pagesize=PAGE,
        title=f"Rebalancing Strategies — {cfg['title']}",
        author="Ponfolio",
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=12 * mm, bottomMargin=14 * mm)
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    print(f"wrote {cfg['out'].name}  "
          f"({cfg['out'].stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schedule", choices=list(SCHEDULES) + ["both"],
                    default="annual")
    a = ap.parse_args()
    fonts()
    for key in (list(SCHEDULES) if a.schedule == "both" else [a.schedule]):
        build(SCHEDULES[key])
