"""Value averaging (rule 20) month-wise report: a PDF and one CSV per table.

Reads the ledger written by value_averaging_ledger.py and publishes it for
reading, not for recomputing. The PDF has a summary, a contents page, the
yearly roll-up and three sections, one per version (A value averaging, B same
Rs 10,000 budget, C fixed SIP). Each section opens with its own figures and a
chart, then lists every month year by year; sections and years are PDF
bookmarks.

    python research/scripts/value_averaging_ledger.py
    python research/scripts/build_value_averaging_report.py

Out: docs/reports/smart-sip/Value_Averaging_Month_Wise_1996_2026.pdf
     docs/reports/smart-sip/Month_Wise_A_Value_Averaging.csv
     docs/reports/smart-sip/Month_Wise_B_Same_Budget.csv
     docs/reports/smart-sip/Month_Wise_C_Fixed_SIP.csv
"""
import csv
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from smart_sip_backtest import xirr

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "research/data/smart_sip/value_averaging_ledger.csv"
NSE = ROOT / "research/data/nifty50_nse_daily_1999.csv"
DOCS = ROOT / "docs" / "reports" / "smart-sip"
PDF_OUT = DOCS / "Value_Averaging_Month_Wise_1996_2026.pdf"
SIP = 10_000
CAP = 3 * SIP

PAGE = landscape(A4)
MARGIN = 36
WIDTH = PAGE[0] - 2 * MARGIN

INK, ACCENT = colors.HexColor("#11161d"), colors.HexColor("#1f4f8f")
MUTED, LIGHT, LINE = colors.HexColor("#5b6775"), colors.HexColor("#f4f6f9"), colors.HexColor("#d7dde5")
MAX_BG, PART_BG, CASH_BG = colors.HexColor("#e3f4e8"), colors.HexColor("#fff4d6"), colors.HexColor("#f1e8f7")
ACTION_COL = {"Max ₹30k": "#0b7a51", "Partial": "#9a6a00", "Skip": "#7b8794", "All cash": "#7a3e9d",
              "Invest": "#1f4f8f"}
ACTION_BG = {"Max ₹30k": MAX_BG, "Partial": PART_BG, "All cash": CASH_BG}
# chart: validated categorical slots 1 and 2 (dataviz palette, light surface)
VALUE_COL, MONEY_COL = colors.HexColor("#2a78d6"), colors.HexColor("#eb6834")
SURFACE, GRID = colors.HexColor("#fcfcfb"), colors.HexColor("#e6e6e3")
TEXT_2 = colors.HexColor("#52514e")


def inr(v, decimals=0):
    """Indian digit grouping: 12,34,56,789."""
    v = float(v)
    whole, _, frac = f"{abs(v):.{decimals}f}".partition(".")
    tail, head, parts = whole[-3:], whole[:-3], []
    while head:
        parts.insert(0, head[-2:])
        head = head[:-2]
    s = ",".join(parts + [tail])
    return ("-" if v < 0 else "") + s + ("." + frac if frac else "")


def crore(v):
    v = float(v)
    return f"₹{v / 1e7:.2f} Cr" if v >= 1e7 else f"₹{v / 1e5:.2f} L"


def load():
    led = list(csv.DictReader(open(LEDGER)))
    nse = list(csv.DictReader(open(NSE)))
    val_date, val_close = date.fromisoformat(nse[-1]["date"]), float(nse[-1]["close"])
    for r in led:
        r["action"] = {"skip": "Skip", "partial": "Partial", "cap 30k": "Max ₹30k"}[r["action"]]
        r["d"] = date.fromisoformat(r["date"])
        fi, fg = int(r["fair_invest"]), int(r["fair_gap"])
        r["fair_action"] = ("Skip" if fi == 0 else "Max ₹30k" if fi >= CAP
                            else "All cash" if fi < min(fg, CAP) else "Partial")
    return led, val_date, val_close


def totals(led, val_date, val_close):
    """(name, money put in, value on the valuation date, XIRR %) per version."""
    last = led[-1]
    f_units = x_units = 0.0
    flows, f_flows, x_flows = [], [], []
    for r in led:
        px = float(r["nifty_close"])
        f_units += int(r["fair_invest"]) / px
        x_units += SIP / px
        if int(r["invest"]):
            flows.append((r["d"], -int(r["invest"])))
        f_flows.append((r["d"], -SIP))
        x_flows.append((r["d"], -SIP))
    v = float(last["total_units"]) * val_close
    fv = f_units * val_close + int(last["fair_pile_after"])
    xv = x_units * val_close
    return {
        "A": (int(last["total_invested"]), v, xirr(flows + [(val_date, v)]) * 100),
        "B": (SIP * len(led), fv, xirr(f_flows + [(val_date, fv)]) * 100),
        "C": (SIP * len(led), xv, xirr(x_flows + [(val_date, xv)]) * 100),
    }


def sections(led):
    """The three month-wise tables.

    Columns are (header, pdf width, right-aligned); each row holds (pdf text,
    csv value) pairs so the PDF and the CSV come from one place.
    """
    def m(r):
        return [(r["month_no"], r["month_no"]), (r["d"].strftime("%d-%b-%Y"), r["d"].strftime("%d-%b-%Y")),
                (inr(float(r["nifty_close"]), 2), f"{float(r['nifty_close']):.2f}")]

    def rs(v):
        return (inr(v), int(v))

    def u(v):
        return (f"{float(v):,.4f}", v)

    a_rows, b_rows, c_rows = [], [], []
    for r in led:
        n = int(r["month_no"])
        a_rows.append(m(r) + [
            (f"{float(r['pe']):.2f}" if r["pe"] else "-", r["pe"]), rs(r["target_value"]),
            rs(r["value_before"]), rs(r["gap"]), rs(r["invest"]),
            (r["action"], r["action"].replace("₹", "Rs ")), u(r["units_bought"]), u(r["total_units"]),
            rs(r["total_invested"]), rs(r["value_after"]),
            rs(int(r["value_after"]) - int(r["total_invested"]))])
        b_rows.append(m(r) + [
            rs(r["target_value"]), rs(r["fair_pile_before"]), rs(r["fair_value_before"]), rs(r["fair_gap"]),
            rs(r["fair_invest"]), (r["fair_action"], r["fair_action"].replace("₹", "Rs ")),
            rs(r["fair_pile_after"]), u(r["fair_units_bought"]), u(r["fair_total_units"]),
            rs(SIP * n), rs(r["fair_units_value"]), rs(r["fair_value_total"]),
            rs(int(r["fair_value_total"]) - SIP * n)])
        c_rows.append(m(r) + [
            rs(SIP), ("Invest", "Invest"), u(r["fixed_units_bought"]), u(r["fixed_total_units"]),
            rs(SIP * n), rs(r["fixed_sip_value"]), rs(int(r["fixed_sip_value"]) - SIP * n)])
    first = [("#", 24, True), ("Date", 56, False), ("Nifty", 52, True)]
    return [
        {"key": "A", "name": "Value averaging (rule 20)", "csv": "Month_Wise_A_Value_Averaging.csv",
         "intro": "Each month, invest the gap between the target and what your units are worth, between ₹0 and "
                  "₹30,000. Only money actually invested counts, so the total put in is ₹22.29 L, not ₹37 L.",
         "money_label": "Money invested",
         "legend": [("Max ₹30k", "the gap was ₹30,000 or more"), ("Partial", "the gap was filled in full"),
                    ("Skip", "already above target, ₹0 invested")],
         "value": [int(r["value_after"]) for r in led], "money": [int(r["total_invested"]) for r in led],
         "action": [r["action"] for r in led],
         "cols": first + [("P/E", 30, True), ("Target", 60, True), ("Value before", 60, True),
                          ("Gap", 60, True), ("Invested", 52, True), ("Action", 54, False),
                          ("Units bought", 50, True), ("Total units", 54, True), ("Total invested", 60, True),
                          ("Value after", 62, True), ("Gain", 60, True)],
         "rows": a_rows,
         "year_line": lambda rs_, yr: (f"invested ₹{inr(sum(int(r['invest']) for r in rs_))}  ·  "
                                       f"total invested ₹{inr(rs_[-1]['total_invested'])}  ·  "
                                       f"value ₹{inr(rs_[-1]['value_after'])}")},
        {"key": "B", "name": "Same ₹10,000 budget", "csv": "Month_Wise_B_Same_Budget.csv",
         "intro": "₹10,000 goes into a cash pot every month and the pot earns 6% a year (liquid fund). The "
                  "value-averaging investment comes out of the pot, so it never uses money you have not set "
                  "aside. This is the fair comparison with a fixed SIP: both use exactly ₹37 L.",
         "money_label": "Money set aside",
         "legend": [("Max ₹30k", "invested the ₹30,000 limit"), ("All cash", "gap bigger than the cash, all of it went in"),
                    ("Partial", "the gap was filled in full"), ("Skip", "above target, cash kept in the liquid fund")],
         "value": [int(r["fair_value_total"]) for r in led], "money": [SIP * int(r["month_no"]) for r in led],
         "action": [r["fair_action"] for r in led],
         "cols": first + [("Target", 50, True), ("Cash before", 48, True), ("Units value before", 52, True),
                          ("Gap", 50, True), ("Invested", 44, True), ("Action", 46, False),
                          ("Cash left", 46, True), ("Units bought", 44, True), ("Total units", 46, True),
                          ("Set aside so far", 50, True), ("Units value", 52, True), ("Total value", 52, True),
                          ("Gain", 50, True)],
         "rows": b_rows,
         "year_line": lambda rs_, yr: (f"invested ₹{inr(sum(int(r['fair_invest']) for r in rs_))}  ·  "
                                       f"cash left ₹{inr(rs_[-1]['fair_pile_after'])}  ·  "
                                       f"total value ₹{inr(rs_[-1]['fair_value_total'])}")},
        {"key": "C", "name": "Fixed SIP", "csv": "Month_Wise_C_Fixed_SIP.csv",
         "intro": "₹10,000 invested on the first trading day of every month, whatever the market does. "
                  "The baseline for the other two sections.",
         "money_label": "Money invested",
         "legend": [("Invest", "₹10,000 every month")],
         "value": [int(r["fixed_sip_value"]) for r in led], "money": [SIP * int(r["month_no"]) for r in led],
         "action": ["Invest"] * len(led),
         "cols": first + [("Invested", 70, True), ("Action", 60, False), ("Units bought", 80, True),
                          ("Total units", 90, True), ("Total invested", 100, True), ("Value", 110, True),
                          ("Gain", 110, True)],
         "rows": c_rows,
         "year_line": lambda rs_, yr: (f"invested ₹{inr(SIP * len(rs_))}  ·  "
                                       f"total invested ₹{inr(SIP * int(rs_[-1]['month_no']))}  ·  "
                                       f"value ₹{inr(rs_[-1]['fixed_sip_value'])}")},
    ]


def write_csvs(secs):
    plain = ("#", "Date", "Nifty", "P/E", "Action", "Units bought", "Total units")
    written = []
    for s in secs:
        try:
            fh = open(DOCS / s["csv"], "w", newline="", encoding="utf-8-sig")
        except PermissionError:
            print(f"skipped {s['csv']}: file is open in another program (close it and re-run)")
            continue
        with fh:
            w = csv.writer(fh)
            w.writerow([h if h in plain else h + " (Rs)" for h, _w, _r in s["cols"]])
            for row in s["rows"]:
                w.writerow([csv_v for _pdf, csv_v in row])
        written.append(s)
    return written


def chart(dates, value, money, money_label, width=WIDTH, height=190):
    """Value vs money in, one shared rupee axis (crore), end labels + legend."""
    d = Drawing(width, height)
    left, right, bottom, top = 46, 150, 22, 12
    pw, ph = width - left - right, height - bottom - top
    vmax = max(max(value), max(money))
    step = next(s for s in (0.25, 0.5, 1, 2, 5) if vmax / 1e7 / s <= 6) * 1e7
    ymax = step * (int(vmax / step) + 1)
    x0, x1 = dates[0].toordinal(), dates[-1].toordinal()

    def px(dt):
        return left + (dt.toordinal() - x0) / (x1 - x0) * pw

    def py(v):
        return bottom + v / ymax * ph

    k = 0
    while k * step <= ymax + 1:
        y = py(k * step)
        d.add(Line(left, y, left + pw, y, strokeColor=GRID, strokeWidth=0.5))
        d.add(String(left - 6, y - 3, f"₹{k * step / 1e7:g} Cr", fontName="LV", fontSize=7,
                     fillColor=TEXT_2, textAnchor="end"))
        k += 1
    for yr in range(dates[0].year, dates[-1].year + 1, 5):
        x = px(date(yr, 1, 1))
        d.add(Line(x, bottom, x, bottom - 3, strokeColor=TEXT_2, strokeWidth=0.5))
        d.add(String(x, bottom - 13, str(yr), fontName="LV", fontSize=7, fillColor=TEXT_2, textAnchor="middle"))
    d.add(Line(left, bottom, left + pw, bottom, strokeColor=TEXT_2, strokeWidth=0.6))

    for series, col, dash in ((money, MONEY_COL, (4, 2)), (value, VALUE_COL, None)):
        pts = []
        for dt, v in zip(dates, series):
            pts += [px(dt), py(v)]
        d.add(PolyLine(pts, strokeColor=col, strokeWidth=1.6, strokeDashArray=dash, strokeLineJoin=1))
    lv, lm = py(value[-1]), py(money[-1])
    if abs(lv - lm) < 12:
        lv, lm = (lv + 6, lm - 6) if lv >= lm else (lv - 6, lm + 6)
    for y, text, col, dash in ((lv, f"Value {crore(value[-1])}", VALUE_COL, None),
                               (lm, f"{money_label} {crore(money[-1])}", MONEY_COL, (4, 2))):
        xe = left + pw + 6
        d.add(Line(xe, y + 2.5, xe + 14, y + 2.5, strokeColor=col, strokeWidth=1.6, strokeDashArray=dash))
        d.add(String(xe + 18, y, text, fontName="LV", fontSize=7.5, fillColor=INK))
    return d


class Report(BaseDocTemplate):
    """Bookmarks, contents entries and the running section name."""

    def __init__(self, path, **kw):
        super().__init__(path, pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=40,
                         bottomMargin=34, **kw)
        self.section = ""
        frame = Frame(MARGIN, 34, WIDTH, PAGE[1] - 74, id="body", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        # drawn when the page ends, so the header names the section the page belongs to
        self.addPageTemplates([PageTemplate(id="page", frames=[frame], onPageEnd=self.decorate)])

    def beforeDocument(self):
        self.section = ""

    def afterFlowable(self, f):
        mark = getattr(f, "_mark", None)
        if not mark:
            return
        title, level, key, section, in_toc = mark
        if section is not None:
            self.section = section
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level=level, closed=level == 0)
        if in_toc:
            self.notify("TOCEntry", (level, title, self.page, key))

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("LV", 7.5)
        canvas.setFillColor(MUTED)
        if self.section:
            canvas.drawString(MARGIN, PAGE[1] - 24, self.section)
        canvas.drawRightString(PAGE[0] - MARGIN, PAGE[1] - 24, "Nifty 50 SIP  |  Jan 1996 to Oct 2026  |  price index")
        canvas.setStrokeColor(LINE)
        canvas.line(MARGIN, PAGE[1] - 30, PAGE[0] - MARGIN, PAGE[1] - 30)
        canvas.drawString(MARGIN, 18, "Source: NSE index data. Past results, not a forecast or investment advice.")
        canvas.drawRightString(PAGE[0] - MARGIN, 18, f"Page {doc.page}")
        canvas.restoreState()


def build_pdf(led, val_date, val_close, secs):
    for name, file in (("LV", "arial.ttf"), ("LVB", "arialbd.ttf")):
        pdfmetrics.registerFont(TTFont(name, "C:/Windows/Fonts/" + file))
    pdfmetrics.registerFontFamily("LV", normal="LV", bold="LVB", italic="LV", boldItalic="LVB")
    st = {k: ParagraphStyle(k, fontName="LVB" if k in ("title", "head", "h2", "band") else "LV", fontSize=s,
                            leading=ld, textColor=INK, spaceAfter=g)
          for k, s, ld, g in (("body", 9.5, 13.5, 5), ("small", 8, 11, 3), ("title", 19, 24, 6),
                              ("h2", 12.5, 16, 5), ("cell", 7.4, 9, 0), ("head", 7.2, 8.6, 0),
                              ("band", 8.6, 11, 0), ("kicker", 8.5, 11, 2))}
    st["title"].textColor = st["h2"].textColor = ACCENT
    st["head"].textColor = colors.white
    st["kicker"].textColor = MUTED
    cell_r = ParagraphStyle("cell_r", parent=st["cell"], alignment=2)
    head_r = ParagraphStyle("head_r", parent=st["head"], alignment=2)
    tot = totals(led, val_date, val_close)
    story = []

    def p(text, style="body", mark=None):
        para = Paragraph(text, st[style])
        if mark:
            para._mark = mark
        story.append(para)
        return para

    def grid(head, rows, widths, right=(), shade=None, pad=2.2):
        data = [[Paragraph(escape(h), head_r if j in right else st["head"]) for j, h in enumerate(head)]]
        extra = []
        for i, row in enumerate(rows, 1):
            cells = []
            for j, v in enumerate(row):
                text = escape(str(v))
                col = ACTION_COL.get(str(v))
                if col:
                    text = f'<font color="{col}"><b>{text}</b></font>'
                cells.append(Paragraph(text, cell_r if j in right else st["cell"]))
            data.append(cells)
            bg = shade(i - 1) if shade else None
            if bg is not None:
                extra.append(("BACKGROUND", (0, i), (-1, i), bg))
        t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ] + extra))
        return t

    def cards(items, width=WIDTH):
        rows = [[Paragraph(escape(lbl), st["small"]) for lbl, _ in items],
                [Paragraph(f'<font size="17" color="#1f4f8f"><b>{escape(v)}</b></font>', st["body"])
                 for _, v in items]]
        t = Table(rows, colWidths=[width / len(items)] * len(items))
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                               ("LINEAFTER", (0, 0), (-2, -1), 0.5, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        story.append(t)
        story.append(Spacer(1, 10))

    order = ["Skip", "Partial", "All cash", "Max ₹30k", "Invest"]
    counts = {s["key"]: {a: s["action"].count(a) for a in order if a in s["action"]} for s in secs}

    # 1. summary
    p("Value Averaging on Nifty 50", "title", mark=("Summary", 0, "summary", "Summary", True))
    p(f"Every month from Jan 1996 to Oct 2026 ({len(led)} months) | Nifty 50 price index, no dividends | "
      f"valued at the NSE close of {val_date.strftime('%d %b %Y')} ({inr(val_close, 2)})", "kicker")
    story.append(Spacer(1, 6))
    cards([(f"{s['key']}  {s['name']}  XIRR", f"{tot[s['key']][2]:.2f}%") for s in secs]
          + [("Fair edge: B minus C", f"{tot['B'][2] - tot['C'][2]:+.2f} pts a year")])
    story.append(grid(
        ["Section", "Version", "Money put in", "Value today", "XIRR", "Months by action", "What it means"],
        [[s["key"], s["name"], crore(tot[s["key"]][0]), crore(tot[s["key"]][1]), f"{tot[s['key']][2]:.2f}%",
          ", ".join(f"{a} {n}" for a, n in counts[s["key"]].items()),
          {"A": "Counts only money invested; skipped months are ignored",
           "B": "Fair: the full ₹10,000 is set aside every month",
           "C": "Baseline: ₹10,000 every month, no rule"}[s["key"]]] for s in secs],
        [44, 128, 70, 70, 50, 190, 218], right=(2, 3, 4), pad=4))
    story.append(Spacer(1, 12))
    p("The answer in three lines", "h2")
    early = sum(int(r["invest"]) for r in led if r["d"].year <= 2003)
    for line in (
        f"<b>1.</b> Value averaging shows <b>{tot['A'][2]:.2f}%</b>, but it invested only "
        f"{crore(tot['A'][0])} of the ₹37 L budget; {early / tot['A'][0]:.0%} of that went in during 1996 to 2003, "
        "when Nifty was 800 to 1,650.",
        f"<b>2.</b> Counted fairly with the same ₹37 L (section B), it gives <b>{tot['B'][2]:.2f}%</b>: "
        f"{tot['B'][2] - tot['C'][2]:.2f} points a year more than a fixed SIP, "
        f"{crore(tot['B'][1] - tot['C'][1])} more after 30 years.",
        f"<b>3.</b> It skipped {counts['A'].get('Skip', 0)} of {len(led)} months and needed the full ₹30,000 in "
        f"{counts['A'].get('Max ₹30k', 0)} months, mostly in crashes (1998, 2001 to 2002, 2020, 2026).",
    ):
        p(line)
    story.append(PageBreak())

    # 2. contents + how it works
    p("Contents", "title", mark=("Contents", 0, "contents", "Contents", False))
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("toc0", fontName="LV", fontSize=11, leading=20, leftIndent=8,
                                      textColor=INK)]
    toc.dotsMinLevel = 0
    story.append(toc)
    story.append(Spacer(1, 10))
    p("How the rule works", "h2", mark=("How the rule works", 0, "how", None, True))
    for line in (
        "<b>Target.</b> The portfolio should be worth ₹10,000 after month 1, ₹20,100 after month 2, ₹30,301 after "
        "month 3 and so on: ₹10,000 more each month, with the target itself growing 1% a month (about 12.7% a year).",
        "<b>Each month</b> invest the gap: target minus what your units are worth today. After a fall the gap is "
        "big and you invest more; after a rise you may already be above target and invest ₹0.",
        "<b>Limits.</b> Never more than ₹30,000 in a month and never below ₹0: the rule never sells.",
        "<b>Timing.</b> Bought at the close of the first NSE trading day of the month. Price index only.",
        "<b>Reading the tables.</b> Each section lists every month, grouped by year, with a one-line year summary "
        "above each year. Coloured rows show the action; white rows are skipped months. Use the PDF bookmarks to "
        "jump to any section or year.",
    ):
        p(line)
    p("Sources: prices NSE historicalOR/indicesHistory; P/E NSE historicalOR/indicesYield from Nov 2015 and, "
      "before that, the Kaggle 'NIFTY 50 Historical PE, PB, DIV Yield' file, which matches NSE exactly wherever "
      "both exist. Results re-computed independently (verify_smart_sip_rules.py) and in Excel.", "small")
    story.append(PageBreak())

    # 3. year by year
    p("Year by year, all three", "title", mark=("Year by year", 0, "years", "Year by year", True))
    p("Year-end figures at the last SIP date of each year, in rupees. Shaded years: value averaging invested "
      "something.", "kicker")
    years = {}
    for r in led:
        y = years.setdefault(r["d"].year, {"inv": 0, "rows": []})
        y["inv"] += int(r["invest"])
        y["rows"].append(r)
    yrows = []
    for yr, y in years.items():
        last = y["rows"][-1]
        acts = [r["action"] for r in y["rows"]]
        yrows.append([yr, inr(float(last["nifty_close"])), acts.count("Skip"), acts.count("Partial"),
                      acts.count("Max ₹30k"), inr(y["inv"]), inr(last["total_invested"]), inr(last["value_after"]),
                      inr(last["fair_value_total"]), inr(last["fixed_sip_value"])])
    story.append(grid(["Year", "Nifty", "A skip", "A partial", "A max", "A invested in year", "A total invested",
                       "A value", "B total value", "C value"], yrows,
                      [44, 56, 48, 52, 46, 96, 104, 108, 108, 108], right=tuple(range(1, 10)),
                      shade=lambda i: PART_BG if yrows[i][5] != "0" else None, pad=2.4))

    # 4. the three sections; charts run to the valuation date so they end on the card's value
    dates = [r["d"] for r in led] + [val_date]
    for s in secs:
        key = s["key"]
        story.append(PageBreak())
        p(f"SECTION {key}", "kicker")
        p(s["name"], "title", mark=(f"Section {key}: {s['name']}", 0, f"sec{key}",
                                    f"Section {key}  |  {s['name']}", True))
        p(s["intro"])
        money, value, x = tot[key]
        c = counts[key]
        cards([(s["money_label"], crore(money)), (f"Value on {val_date.strftime('%d %b %Y')}", crore(value)),
               ("XIRR", f"{x:.2f}%"), ("Months: " + " / ".join(c), " / ".join(str(n) for n in c.values()))])
        story.append(chart(dates, s["value"] + [value], s["money"] + [money], s["money_label"]))
        legend = "  ·  ".join(f'<font color="{ACTION_COL[a]}"><b>{escape(a)}</b></font> {escape(t)}'
                              for a, t in s["legend"])
        p(f"<b>Actions:</b> {legend}", "small")
        story.append(Spacer(1, 8))
        heads = [h for h, _w, _r in s["cols"]]
        widths = [w for _h, w, _r in s["cols"]]
        right = tuple(j for j, (_h, _w, r) in enumerate(s["cols"]) if r)
        act = heads.index("Action")
        for yr in years:
            idx = [i for i, r in enumerate(led) if r["d"].year == yr]
            texts = [[pdf for pdf, _csv in s["rows"][i]] for i in idx]
            ys = [led[i] for i in idx]
            acts = [s["action"][i] for i in idx]
            summary = ", ".join(f"{a} {acts.count(a)}" for a in dict.fromkeys(acts))
            band = Table([[Paragraph(f"{yr}", st["band"]),
                           Paragraph(f"{escape(s['year_line'](ys, yr))}  ·  {escape(summary)}", st["cell"])]],
                         colWidths=[60, sum(widths) - 60], hAlign="LEFT")
            band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8eef7")),
                                      ("LINEBELOW", (0, 0), (-1, -1), 0.8, ACCENT),
                                      ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                      ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
            band._mark = (f"{key} {yr}", 1, f"{key}{yr}", None, False)
            block = grid(heads, texts, widths, right=right, shade=lambda i, t=texts: ACTION_BG.get(t[i][act]))
            story.append(KeepTogether([band, block, Spacer(1, 9)]))

    doc = Report(str(PDF_OUT), title="Value Averaging on Nifty 50, month-wise", author="smart_sip research")
    doc.multiBuild(story)


def main():
    led, val_date, val_close = load()
    secs = sections(led)
    written = write_csvs(secs)
    build_pdf(led, val_date, val_close, secs)
    print(f"wrote {PDF_OUT}")
    for s in written:
        print(f"wrote {DOCS / s['csv']} ({len(s['rows'])} months)")


if __name__ == "__main__":
    main()
