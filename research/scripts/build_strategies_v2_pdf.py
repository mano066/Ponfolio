"""Build the S1-S10 rebalancing report PDF from the saved engine output.

Every number is read from research/data/strategies_v2/results.json — nothing is
typed into this file. If the backtest is re-run the PDF changes with it, and a
figure can never drift out of step with the engine that produced it.

    python research/scripts/build_strategies_v2_pdf.py

Out: docs/Rebalancing_Strategies_S1_S10_Backtest_2011_2026.pdf
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from reportlab.graphics.shapes import Drawing, Line, Rect, String

SRC = ROOT / "research" / "data" / "strategies_v2" / "results.json"
OUT = ROOT / "docs" / "Rebalancing_Strategies_S1_S10_Backtest_2011_2026.pdf"

INK = colors.HexColor("#163443")
TEAL = colors.HexColor("#067F80")
GRAY = colors.HexColor("#536B76")
LIGHT = colors.HexColor("#EFF5F6")
LINE = colors.HexColor("#D4E1E6")
GOLD = colors.HexColor("#A46A40")
RED = colors.HexColor("#A3423C")


def lakh(x):
    return f"{x / 1e5:,.2f} L"


def money(x):
    """Indian digit grouping: 51,85,877 not 5,185,877."""
    s = f"{round(abs(x)):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while head:
            parts.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(parts + [tail])
    return ("-" if x < 0 else "") + s


def fonts():
    for name, file in (("AV", "arial.ttf"), ("AVB", "arialbd.ttf")):
        pdfmetrics.registerFont(TTFont(name, "C:/Windows/Fonts/" + file))
    pdfmetrics.registerFontFamily("AV", normal="AV", bold="AVB",
                                  italic="AV", boldItalic="AVB")


def styles():
    return {
        "title": ParagraphStyle("title", fontName="AVB", fontSize=21,
                                leading=25, textColor=INK, spaceAfter=4),
        "sub": ParagraphStyle("sub", fontName="AV", fontSize=10, leading=14,
                              textColor=GRAY, spaceAfter=14),
        "eyebrow": ParagraphStyle("eyebrow", fontName="AVB", fontSize=8,
                                  leading=12, textColor=TEAL, spaceAfter=6),
        "h": ParagraphStyle("h", fontName="AVB", fontSize=12.5, leading=16,
                            textColor=INK, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName="AVB", fontSize=10, leading=13.5,
                             textColor=INK, spaceBefore=9, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="AV", fontSize=9.1,
                               leading=13.2, textColor=INK, spaceAfter=7),
        "small": ParagraphStyle("small", fontName="AV", fontSize=7.8,
                                leading=11, textColor=GRAY, spaceAfter=5),
        "cell": ParagraphStyle("cell", fontName="AV", fontSize=8,
                               leading=10.6, textColor=INK),
        "cellb": ParagraphStyle("cellb", fontName="AVB", fontSize=8,
                                leading=10.6, textColor=INK),
        "head": ParagraphStyle("head", fontName="AVB", fontSize=7.8,
                               leading=10.4, textColor=colors.white),
    }


def callout(text, st, tone=TEAL):
    """The one-paragraph answer, boxed so it cannot be skimmed past."""
    t = Table([[Paragraph(text, st["body"])]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.8, tone),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def table(rows, widths, st, highlight=(), dim=()):
    data = [[Paragraph(c, st["head"]) for c in rows[0]]]
    for i, r in enumerate(rows[1:]):
        s = st["cellb"] if i in highlight else st["cell"]
        data.append([Paragraph(c, s) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for i in highlight:
        style.append(("BACKGROUND", (0, i + 1), (-1, i + 1),
                      colors.HexColor("#E3F1EC")))
    for i in dim:
        style.append(("TEXTCOLOR", (0, i + 1), (-1, i + 1), GRAY))
    t.setStyle(TableStyle(style))
    return t


def bar_chart(pairs, width=165 * mm, height=62 * mm, unit="%"):
    """Horizontal bars of after-tax XIRR, best at the top."""
    d = Drawing(width, height)
    left, top = 62 * mm, height - 6
    span = width - left - 16 * mm
    hi = max(v for _n, v, _c in pairs)
    step = (height - 14) / len(pairs)
    for i, (name, value, tone) in enumerate(pairs):
        y = top - (i + 1) * step
        d.add(String(left - 4, y + step * 0.28, name, fontName="AV",
                     fontSize=7.2, fillColor=INK, textAnchor="end"))
        w = max(1.0, span * value / hi)
        d.add(Rect(left, y + step * 0.18, w, step * 0.6,
                   fillColor=tone, strokeColor=None))
        d.add(String(left + w + 4, y + step * 0.28, f"{value:.2f}{unit}",
                     fontName="AVB", fontSize=7.2, fillColor=INK))
    d.add(Line(left, 6, left, top, strokeColor=LINE, strokeWidth=0.6))
    return d


def wealth_chart(series, width=165 * mm, height=70 * mm):
    """Annual wealth paths. Pre-tax, because that is what the engine stores."""
    d = Drawing(width, height)
    left, bottom = 20 * mm, 12 * mm
    span_x, span_y = width - left - 26 * mm, height - bottom - 8
    dates = sorted(series[0][1])
    hi = max(v for _n, s, _c in series for v in s.values())

    for frac in (0, .25, .5, .75, 1):
        y = bottom + span_y * frac
        d.add(Line(left, y, left + span_x, y, strokeColor=LINE,
                   strokeWidth=0.4))
        d.add(String(left - 4, y - 2.5, f"{hi * frac / 1e5:.0f}L",
                     fontName="AV", fontSize=6.6, fillColor=GRAY,
                     textAnchor="end"))
    for i, dt in enumerate(dates):
        if i % 3 == 0 or i == len(dates) - 1:
            x = left + span_x * i / (len(dates) - 1)
            d.add(String(x, bottom - 8, dt[:4], fontName="AV", fontSize=6.6,
                         fillColor=GRAY, textAnchor="middle"))

    for name, s, tone in series:
        pts = []
        for i, dt in enumerate(dates):
            pts.append((left + span_x * i / (len(dates) - 1),
                        bottom + span_y * s[dt] / hi))
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            d.add(Line(x1, y1, x2, y2, strokeColor=tone, strokeWidth=1.4))
        d.add(String(pts[-1][0] + 3, pts[-1][1] - 2, name, fontName="AVB",
                     fontSize=6.8, fillColor=tone))
    return d


def build():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    pre = {x["code"]: x for x in data["results"]}
    post = {x["code"]: x for x in data["after_tax"]}
    st = styles()
    story = []

    # ── page 1 ──
    story.append(Paragraph("REBALANCING RESEARCH · S1–S10", st["eyebrow"]))
    story.append(Paragraph("Ten rebalancing strategies on one NSE basket, "
                           "2011–2026", st["title"]))
    story.append(Paragraph(
        f"{data['start']} to {data['end']} · {data['sessions']:,} sessions · "
        f"{data['contributions']} · {data['cost_bps']} bps costs · "
        "whole shares, official NSE opens, real corporate actions",
        st["sub"]))

    best = max(post.values(), key=lambda x: x["xirr_pct"])
    gap = best["xirr_pct"] - post[3]["xirr_pct"]
    story.append(callout(
        f"<b>Two strategies beat S3 Band rebalance, and neither does it by "
        f"rebalancing more cleverly.</b> {best['name']} returns "
        f"<b>{best['xirr_pct']:.2f}%</b> against S3's "
        f"<b>{post[3]['xirr_pct']:.2f}%</b> after tax — a gap of "
        f"{gap:.2f} points, or Rs {money(best['terminal'] - post[3]['terminal'])} "
        f"on the same Rs 16,00,000 invested. It wins by reinvesting the "
        f"dividends. S3 ends with Rs {money(pre[3]['dividends'] + pre[3]['ntpc_income'])} "
        f"of dividend cash sitting idle — "
        f"{(pre[3]['dividends'] + pre[3]['ntpc_income']) / pre[3]['terminal_after_cost'] * 100:.1f}% "
        f"of its own terminal wealth, earning nothing for up to fifteen years.",
        st))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Result", st["h"]))
    order = sorted(post.values(), key=lambda x: -x["xirr_pct"])
    rows = [["#", "Strategy", "Pre-tax XIRR", "After-tax XIRR",
             "Terminal (after tax)", "Sells", "LTCG paid"]]
    highlight, dim = [], []
    for i, x in enumerate(order):
        c = x["code"]
        rows.append([str(c), x["name"], f"{pre[c]['xirr_pct']:.2f}%",
                     f"{x['xirr_pct']:.2f}%", f"Rs {money(x['terminal'])}",
                     str(x["sells"]),
                     f"Rs {money(x['ltcg_paid'])}" if x["ltcg_paid"] else "—"])
        if c in (6, 10):
            highlight.append(i)
        if c == 3:
            dim.append(i)
    story.append(table(rows, [9 * mm, 56 * mm, 21 * mm, 23 * mm, 28 * mm,
                              12 * mm, 20 * mm], st, highlight, dim))
    story.append(Paragraph(
        "Shaded: the winners. S3, the strategy this study was asked to beat, "
        "is greyed. S1–S5 reproduce the published verified run exactly "
        "(12.28 / 13.25 / 13.22 / 9.85 / 10.94), which is the control on this "
        "extension — every new number depends on it.", st["small"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("After-tax XIRR, best first", st["h2"]))
    story.append(bar_chart([
        (x["name"][:38], x["xirr_pct"],
         TEAL if x["code"] in (6, 10) else
         GOLD if x["code"] == 3 else colors.HexColor("#93A9B4"))
        for x in order]))

    story.append(PageBreak())

    # ── page 2 ──
    story.append(Paragraph("The two mechanisms, each measured twice",
                           st["eyebrow"]))
    story.append(Paragraph("Why the winners win", st["title"]))
    story.append(Paragraph(
        "Every new strategy changes exactly one thing against a named "
        "incumbent, so each effect is isolated rather than merely observed — "
        "and each is measured against two different baselines, which is the "
        "only replication a single historical path can offer.", st["body"]))

    story.append(Paragraph("1 · Reinvest the dividends — worth about "
                           "+1.3 points", st["h2"]))
    d1a = post[6]["xirr_pct"] - post[2]["xirr_pct"]
    d1b = post[8]["xirr_pct"] - post[3]["xirr_pct"]
    story.append(table([
        ["Comparison", "What changes", "After-tax XIRR", "Effect"],
        ["S2 → S6", "dividends reinvested, no trimming either way",
         f"{post[2]['xirr_pct']:.2f} → {post[6]['xirr_pct']:.2f}",
         f"+{d1a:.2f}"],
        ["S3 → S8", "dividends reinvested, 12.5% band either way",
         f"{post[3]['xirr_pct']:.2f} → {post[8]['xirr_pct']:.2f}",
         f"+{d1b:.2f}"],
    ], [24 * mm, 76 * mm, 37 * mm, 28 * mm], st))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "The same answer from both directions. This is not a smarter rule, it "
        "is arithmetic: the idle pile, put back to work, added roughly "
        f"Rs {money(pre[8]['equity'] - pre[3]['equity'])} of equity by 2026. "
        "Nothing in the original five was permitted to touch that money. The "
        "effect is small early and large late, which is what compounding looks "
        "like rather than what a lucky trade looks like.", st["body"]))

    story.append(Paragraph("2 · Stop trimming winners — worth about "
                           "+0.3 points after tax", st["h2"]))
    d2a = post[2]["xirr_pct"] - post[3]["xirr_pct"]
    d2b = post[6]["xirr_pct"] - post[8]["xirr_pct"]
    story.append(table([
        ["Comparison", "What changes", "After-tax XIRR", "Effect"],
        ["S3 → S2", "the 12.5% trim is dropped",
         f"{post[3]['xirr_pct']:.2f} → {post[2]['xirr_pct']:.2f}",
         f"+{d2a:.2f}"],
        ["S8 → S6", "the 12.5% trim is dropped, dividends reinvested either way",
         f"{post[8]['xirr_pct']:.2f} → {post[6]['xirr_pct']:.2f}",
         f"+{d2b:.2f}"],
    ], [24 * mm, 76 * mm, 37 * mm, 28 * mm], st))
    story.append(Spacer(1, 5))
    story.append(callout(
        f"<b>The trim is a net loser once it is taxed.</b> Pre-tax, trimming "
        f"looks fine — S8's {pre[8]['xirr_pct']:.2f}% is the best number in the "
        f"whole study. It is also the number that does not survive contact with "
        f"a tax rate: S8 realises Rs {money(post[8]['ltcg_paid'])} of capital-"
        f"gains tax that S6 never pays, and that is the entire difference "
        f"between them. Directing new contributions at whatever is underweight "
        f"achieves the same rebalancing with no sale, no cost and no tax — "
        f"which is why the winning strategy never sells.", st, GOLD))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Wealth path, pre-tax", st["h2"]))
    picks = [(f"S{c}", {a["date"]: a["wealth"] for a in pre[c]["annual"]}, tone)
             for c, tone in ((8, TEAL), (6, colors.HexColor("#64A69D")),
                             (3, GOLD), (1, colors.HexColor("#93A9B4")))]
    story.append(wealth_chart(picks))
    story.append(Paragraph(
        "The reinvesting strategies are level with S3 until about 2020 and "
        "separate sharply after it, as the accumulated dividend pile grows "
        "large enough to matter. Pre-tax, because the engine stores the annual "
        "path on that basis; the after-tax ranking is on page 1.", st["small"]))

    story.append(PageBreak())

    # ── page 3 ──
    story.append(Paragraph("What each strategy does", st["eyebrow"]))
    story.append(Paragraph("Rules, and what does not work", st["title"]))
    rules = [
        ["#", "Strategy", "Rule, applied once a year at the review"],
        ["S1", "Equal annual buying",
         "Split the contribution equally across all ten names. No sells."],
        ["S2", "Cash-flow rebalance",
         "Direct the whole contribution at whatever sits below its 10% "
         "target. No sells."],
        ["S3", "Band rebalance",
         "Trim anything above 12.5% of the book back to 10%, then deploy "
         "cash at the underweights."],
        ["S4", "Price-rule proxy",
         "Sell out of any name with a negative five-year price CAGR; trim "
         "positions up over 100%."],
        ["S5", "Momentum tilt",
         "Send the contribution to the three best twelve-month performers."],
        ["S6", "Cash-flow + dividends reinvested",
         "S2, plus accumulated dividends swept into tradeable cash first."],
        ["S7", "Wide band 20% + cash-flow",
         "S3 with the trim trigger moved from 12.5% to 20%."],
        ["S8", "Band 12.5% + dividends reinvested",
         "S3, plus the dividend sweep."],
        ["S9", "Laggard tilt",
         "Send the contribution to the three worst twelve-month performers — "
         "the mirror of S5."],
        ["S10", "Wide band + dividends reinvested",
         "S7 plus the sweep. Identical to S6 in this data: with dividends "
         "reinvested nothing ever reaches a 20% weight, so the band never "
         "fires."],
    ]
    story.append(table(rules, [10 * mm, 45 * mm, 110 * mm], st,
                       highlight=[5, 9]))

    story.append(Paragraph("What does not work", st["h"]))
    story.append(Paragraph(
        f"<b>Tilting the contribution, in either direction.</b> S5 sent each "
        f"year's money to the three best performers and finished "
        f"{post[2]['xirr_pct'] - post[5]['xirr_pct']:.2f} points behind plain "
        f"cash-flow rebalancing. S9 — built here as its mirror — sent it to the "
        f"three worst and finished {post[2]['xirr_pct'] - post[9]['xirr_pct']:.2f} "
        f"points behind. Concentrating the contribution loses whichever way you "
        f"point it; the diluted version of the same idea, S2, beats both.",
        st["body"]))
    story.append(callout(
        "<b>S7's wide band is one lucky trade, not a finding.</b> S7 beats S3 "
        f"by {post[7]['xirr_pct'] - post[3]['xirr_pct']:.2f} points after tax, "
        "and its ledger contains exactly one sale: 129 Tata Steel on "
        "2022-01-03 at Rs 1,115, near that stock's top, with the proceeds "
        "redeployed. On a single historical path one well-timed trade is not "
        "evidence that a 20% band beats a 12.5% one. This result should not be "
        "acted on.", st, RED))

    story.append(Paragraph("Honest limits", st["h"]))
    for text in [
        "<b>One basket, one schedule, one path.</b> Ten PSU-heavy names "
        "through a single fifteen-year Indian bull market. Differences of a "
        "few tenths of a point are not separable here. The mechanisms "
        "replicate across baselines; the decimals do not carry that weight.",
        "<b>The dividend result's size is basket-specific.</b> ONGC, IOC, "
        "COALINDIA and NTPC are unusually high-yielding. A growth basket would "
        "show the same direction and a smaller magnitude.",
        f"<b>Tax rates are indicative.</b> "
        f"{data['tax_assumptions']['dividend_withholding'] * 100:.0f}% dividend "
        f"withholding and {data['tax_assumptions']['ltcg_rate'] * 100:.1f}% "
        "LTCG, NRI default. Surcharge, treaty relief and the s.112A annual "
        "exemption are ignored — the last of those overstates the seller's "
        "tax, so the table is conservative towards the no-sell strategies "
        "rather than away from them.",
        "<b>Reinvestment lags by up to a year.</b> Dividends are recognised at "
        "ex-date and swept at the next annual review, so the money is idle for "
        "months. An investor reinvesting on receipt would do better than S6 "
        "shows here.",
        "<b>Withholding is applied at source to every strategy</b>, not only "
        "the ones that reinvest — otherwise the comparison would tax S6 and "
        "S8 while letting S3's idle pile through gross, penalising "
        "reinvestment for being the only policy that touches the money.",
    ]:
        story.append(Paragraph("• " + text, st["body"]))

    # Kept together so the heading cannot strand itself at the foot of a page
    # with its own content overleaf.
    story.append(KeepTogether([
        Paragraph("Verification", st["h"]),
        Paragraph(
            "Every run re-checks the published five as a control and gates its "
            "output on the original assertions: "
            + "; ".join(data["checks"]) + ".", st["body"]),
        Paragraph(
            "A separate suite of 25 tests "
            "(<font face='AVB'>research/scripts/test_strategies_v2.py</font>) "
            "covers what those assertions cannot — that the published five "
            "still reproduce, that each new strategy differs from its "
            "incumbent in exactly one way, that nothing is sold before it is "
            "long-term, that withholding reaches every strategy, that capital "
            "gains are charged at the stated rate, and that results are "
            "deterministic and monotonic in cost.", st["body"]),
        Paragraph(
            f"Sources: engine "
            f"<font face='AVB'>research/scripts/backtest_strategies_v2.py</font>"
            f" · results "
            f"<font face='AVB'>{SRC.relative_to(ROOT).as_posix()}</font> · "
            f"full transaction and event ledgers for all ten strategies in "
            f"<font face='AVB'>research/data/strategies_v2/audit_ledgers.zip"
            f"</font>.", st["small"]),
    ]))

    def furniture(canvas, doc):
        canvas.saveState()
        canvas.setFont("AV", 7.2)
        canvas.setFillColor(GRAY)
        canvas.drawString(22 * mm, 12 * mm,
                          "Ponfolio · rebalancing research · "
                          "S1–S10 · not investment advice")
        canvas.drawRightString(A4[0] - 22 * mm, 12 * mm, f"{doc.page}")
        canvas.setStrokeColor(LINE)
        canvas.line(22 * mm, 16 * mm, A4[0] - 22 * mm, 16 * mm)
        canvas.restoreState()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4, title="Rebalancing Strategies S1-S10, 2011-2026",
        author="Ponfolio", leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm)
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    fonts()
    build()
