"""Render a 5-strategy rebalancing backtest into a printable PDF.

Every sentence that quotes a number reads it from the backtest JSON. Nothing
in this file hardcodes a result.

Usage:
    py -3.9 research/scripts/rebalance_report_pdf.py v2
    py -3.9 research/scripts/rebalance_report_pdf.py v1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research" / "data"
DOCS = ROOT / "docs"

RUN_SETS = {
    "v1": {
        "out": "Rebalancing_Strategy_Backtest_2010_2026.pdf",
        "main": "rebalance_backtest.json",
        "variations": [
            ("A basket with real losers in it", "rebalance_backtest_mixed10.json",
             "Same rules and same money, but half the basket is swapped for "
             "long-term laggards. Rebalancing should either prove itself here or "
             "fall apart, because there is finally something worth harvesting "
             "from and something worth feeding."),
            ("Dividends switched on", "rebalance_backtest_div.json",
             "An assumed flat dividend yield, collected each year and reinvested "
             "at the next anniversary. This is a modelled assumption, not a "
             "record of actual payouts."),
            ("NRI tax treatment", "rebalance_backtest_nri.json",
             "Gains withheld at source with surcharge applied instead of billed "
             "at filing."),
        ],
    },
    "v2": {
        "out": "Rebalancing_Strategy_Backtest_V2_2011_2026.pdf",
        "main": "v2_main.json",
        "variations": [
            ("The same rules on a strong basket", "v2_large10.json",
             "Identical rules, identical dates, identical money, but run on ten "
             "large-cap compounders instead. This separates how much of the "
             "result came from the rule from how much came from the stocks."),
            ("Dividends switched on", "v2_div.json",
             "An assumed flat dividend yield, collected each year and reinvested "
             "at the next anniversary. This basket is unusually dividend-heavy, "
             "so the assumption matters more here than it would elsewhere. It is "
             "a modelled assumption, not a record of actual payouts."),
            ("NRI tax treatment", "v2_nri.json",
             "Gains withheld at source with surcharge applied instead of billed "
             "at filing."),
        ],
    },
}

INK = colors.HexColor("#11161d")
MUTED = colors.HexColor("#5b6775")
FAINT = colors.HexColor("#93a0b0")
LINE = colors.HexColor("#d7dde5")
BAND = colors.HexColor("#f4f6f9")
WIN = colors.HexColor("#0b7a51")
WIN_BG = colors.HexColor("#e6f4ee")
WARN = colors.HexColor("#b4432c")
WARN_BG = colors.HexColor("#fdf0ec")
ACCENT = colors.HexColor("#1f4f8f")
ACCENT_BG = colors.HexColor("#eaf0f8")
OVER = colors.HexColor("#e0952f")
UNDER = colors.HexColor("#6fa8d0")

SERIES_COLOURS = [
    colors.HexColor("#0b7a51"), colors.HexColor("#1f4f8f"),
    colors.HexColor("#9a6b00"), colors.HexColor("#7a3e9d"),
    colors.HexColor("#b4432c"),
]


def register_fonts() -> tuple:
    for name, regular, bold in [
        ("Arial", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        ("Segoe", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    ]:
        if Path(regular).exists() and Path(bold).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, regular))
                pdfmetrics.registerFont(TTFont(name + "-Bold", bold))
                pdfmetrics.registerFontFamily(name, normal=name, bold=name + "-Bold")
                return name, name + "-Bold", "\u20b9"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold", "Rs "


FONT, FONT_B, RUPEE = register_fonts()
DASH = "\u2014"


def money(x: float, sign: bool = False) -> str:
    neg = x < 0
    n = int(round(abs(x)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts: List[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    prefix = "-" if neg else ("+" if sign and n else "")
    return f"{prefix}{RUPEE}{s}"


def pct(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}%"


def ordinal(n: int) -> str:
    return {1: "first", 2: "second", 3: "third", 4: "fourth",
            5: "fifth"}.get(n, str(n))


def shade(base: colors.Color, weight: float) -> colors.Color:
    """Blend `base` towards white. 0 = white, 1 = full colour."""
    w = max(0.0, min(1.0, weight))
    return colors.Color(1 - (1 - base.red) * w,
                        1 - (1 - base.green) * w,
                        1 - (1 - base.blue) * w)


# ------------------------------------------------------------------ styles

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_ss["Title"], fontName=FONT_B, fontSize=20,
                    leading=24, textColor=INK, alignment=TA_LEFT, spaceAfter=2)
SUB = ParagraphStyle("SUB", fontName=FONT, fontSize=9.5, leading=13,
                     textColor=MUTED, spaceAfter=10)
H2 = ParagraphStyle("H2", fontName=FONT_B, fontSize=12.5, leading=16,
                    textColor=ACCENT, spaceBefore=12, spaceAfter=5)
H3 = ParagraphStyle("H3", fontName=FONT_B, fontSize=10, leading=13,
                    textColor=INK, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("BODY", fontName=FONT, fontSize=9, leading=12.6,
                      textColor=INK, spaceAfter=5)
SMALL = ParagraphStyle("SMALL", fontName=FONT, fontSize=7.8, leading=10.5,
                       textColor=MUTED, spaceAfter=4)
CELL = ParagraphStyle("CELL", fontName=FONT, fontSize=8, leading=10.5,
                      textColor=INK)
CELL_B = ParagraphStyle("CELL_B", fontName=FONT_B, fontSize=8, leading=10.5,
                        textColor=INK)


def bullets(items: List[str]) -> Table:
    rows = [[Paragraph("\u2022", BODY), Paragraph(t, BODY)] for t in items]
    t = Table(rows, colWidths=[6 * mm, 172 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def grid(data: List[List], widths: List[float],
         highlight_row: Optional[int] = None, align_right_from: int = 1,
         font_size: float = 8) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("FONT", (0, 0), (-1, 0), FONT_B, font_size),
        ("FONT", (0, 1), (-1, -1), FONT, font_size),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
    ]
    if highlight_row is not None:
        r = highlight_row
        style += [
            ("BACKGROUND", (0, r), (-1, r), WIN_BG),
            ("FONT", (0, r), (-1, r), FONT_B, font_size),
            ("TEXTCOLOR", (0, r), (-1, r), WIN),
        ]
    t.setStyle(TableStyle(style))
    return t


def stat_cards(cards: List[tuple]) -> Table:
    row_top = [Paragraph(f'<font size="7.5" color="#5b6775">{c[0]}</font>', CELL)
               for c in cards]
    row_val = [Paragraph(f'<font size="13" color="{c[2]}"><b>{c[1]}</b></font>', CELL)
               for c in cards]
    row_note = [Paragraph(f'<font size="7" color="#5b6775">{c[3]}</font>', CELL)
                for c in cards]
    w = 178 * mm / len(cards)
    t = Table([row_top, row_val, row_note], colWidths=[w] * len(cards))
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def callout(title: str, text: str, tone: colors.Color = WIN) -> Table:
    bg = WIN_BG if tone == WIN else (ACCENT_BG if tone == ACCENT else WARN_BG)
    body = Paragraph(
        f'<font name="{FONT_B}" size="10" color="{tone}">{title}</font><br/>'
        f'<font size="9" color="#11161d">{text}</font>', BODY)
    t = Table([[body]], colWidths=[178 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, tone),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def legend_strip(items: List[tuple]) -> Table:
    cells = []
    for colour, label in items:
        if colour is None:
            cells.append(Paragraph(
                f'<font size="6.5" color="#5b6775">{label}</font>', CELL))
        else:
            cells.append(Paragraph(
                f'<font size="6.5" color="{colour}">\u25a0</font>'
                f'<font size="6.5" color="#5b6775"> {label}</font>', CELL))
    t = Table([cells], colWidths=[178 * mm / len(cells)] * len(cells))
    t.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# ------------------------------------------------------------ derived facts

def analyse(main: dict, variations: List[tuple]) -> dict:
    res = sorted(main["results"], key=lambda r: r["xirr_net_pct"], reverse=True)
    by_name = {r["strategy"]: r for r in res}
    ranks = {r["strategy"]: i + 1 for i, r in enumerate(res)}
    best, worst = res[0], res[-1]

    var_winners = []
    for label, payload, _desc in variations:
        vres = sorted(payload["results"], key=lambda r: r["xirr_net_pct"],
                      reverse=True)
        var_winners.append((label, vres[0]["strategy"], vres))
    all_won = all(w == best["strategy"] for _l, w, _v in var_winners)

    n_years = len(best["yearly"])
    diverge_at = None
    for i in range(n_years):
        vals = [r["yearly"][i]["value"] for r in res]
        hi, lo = max(vals), min(vals)
        if hi > 0 and (hi - lo) / hi >= 0.05:
            diverge_at = i
            break

    spreads = {}
    for r in res:
        w = r["final_weights"]
        top = max(w, key=lambda k: w[k])
        bottom = min(w, key=lambda k: w[k])
        spreads[r["strategy"]] = (top, w[top], bottom, w[bottom], w[top] - w[bottom])

    return {"res": res, "by_name": by_name, "ranks": ranks, "best": best,
            "second": res[1], "worst": worst, "var_winners": var_winners,
            "all_won": all_won, "diverge_at": diverge_at, "n_years": n_years,
            "spreads": spreads}


def exit_events(r: dict) -> List[dict]:
    """Every EXIT, and whether that stock was bought back in a later year."""
    out = []
    ledger = r["ledger"]
    for i, det in enumerate(ledger):
        for row in det["rows"]:
            if row["action"] != "EXIT":
                continue
            back = None
            for j in range(i + 1, len(ledger)):
                nxt = next((x for x in ledger[j]["rows"]
                            if x["symbol"] == row["symbol"]), None)
                if nxt and nxt["action"] == "ADD":
                    back = {"date": ledger[j]["date"], "price": nxt["price"],
                            "years": ledger[j]["year"] - det["year"]}
                    break
            out.append({"symbol": row["symbol"], "date": det["date"],
                        "year": det["year"], "price": row["price"],
                        "proceeds": -row["amount"], "tax": row["tax"],
                        "back": back,
                        "higher": bool(back and back["price"] > row["price"])})
    return out


def trim_events(r: dict, end_prices: Dict[str, float]) -> List[dict]:
    out = []
    for det in r["ledger"]:
        for row in det["rows"]:
            if row["action"] not in ("TRIM", "SWAP"):
                continue
            end = end_prices.get(row["symbol"])
            out.append({"symbol": row["symbol"], "date": det["date"],
                        "year": det["year"], "price": row["price"],
                        "proceeds": -row["amount"], "tax": row["tax"],
                        "note": row["note"], "end_price": end,
                        "rose_after": bool(end and end > row["price"])})
    return out


# -------------------------------------------------------------------- chart

def growth_chart(res: List[dict]) -> Drawing:
    d = Drawing(505, 235)
    chart = HorizontalLineChart()
    chart.x = 46
    chart.y = 38
    chart.width = 398
    chart.height = 180
    chart.data = [[y["value"] / 100000.0 for y in r["yearly"]] for r in res]
    chart.categoryAxis.categoryNames = [y["date"][:4] for y in res[0]["yearly"]]
    chart.categoryAxis.labels.fontName = FONT
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.angle = 90
    chart.categoryAxis.labels.dy = -9
    chart.categoryAxis.labels.boxAnchor = "e"

    peak = max(max(s) for s in chart.data)
    step = 10.0
    while peak / step > 9:
        step += 10.0
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = step * (int(peak / step) + 1)
    chart.valueAxis.valueStep = step
    chart.valueAxis.labels.fontName = FONT
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.gridStrokeColor = LINE
    chart.valueAxis.gridStrokeWidth = 0.4
    chart.valueAxis.visibleGrid = 1
    for i in range(len(chart.data)):
        chart.lines[i].strokeColor = SERIES_COLOURS[i % len(SERIES_COLOURS)]
        chart.lines[i].strokeWidth = 2.2 if i == 0 else 1.1
    d.add(chart)
    d.add(String(6, 225,
                 "Portfolio value in lakh rupees, measured at each anniversary",
                 fontName=FONT, fontSize=7.5, fillColor=MUTED))

    legend = Legend()
    legend.x = 452
    legend.y = 200
    legend.fontName = FONT
    legend.fontSize = 7
    legend.alignment = "right"
    legend.dxTextSpace = 4
    legend.deltay = 11
    legend.columnMaximum = 6
    legend.colorNamePairs = [
        (SERIES_COLOURS[i % len(SERIES_COLOURS)], r["strategy"].split(" ")[0])
        for i, r in enumerate(res)
    ]
    d.add(legend)
    return d


# ------------------------------------------------------------- summary bits

def headline_table(res: List[dict]) -> Table:
    rows = [["#", "Strategy", "Invested", "Value today", "After exit tax",
             "XIRR", "XIRR net", "Tax paid", "Max fall", "Sells"]]
    for i, r in enumerate(res, 1):
        rows.append([str(i), r["strategy"], money(r["invested"]),
                     money(r["paper_value"]), money(r["net_value"]),
                     pct(r["xirr_paper_pct"]), pct(r["xirr_net_pct"]),
                     money(r["tax_total"]), pct(r["max_drawdown_pct"], 1),
                     str(r["sell_trades"])])
    widths = [7, 34, 21, 23, 24, 15, 16, 20, 15, 11]
    return grid(rows, [w * mm for w in widths], highlight_row=1,
                align_right_from=2)


def compact_table(res: List[dict]) -> Table:
    rows = [["Strategy", "Value today", "After exit tax", "XIRR net",
             "Tax paid", "Max fall", "Sells"]]
    for r in res:
        rows.append([r["strategy"], money(r["paper_value"]),
                     money(r["net_value"]), pct(r["xirr_net_pct"]),
                     money(r["tax_total"]), pct(r["max_drawdown_pct"], 1),
                     str(r["sell_trades"])])
    widths = [38, 26, 28, 18, 24, 16, 14]
    return grid(rows, [w * mm for w in widths], highlight_row=1,
                align_right_from=1, font_size=7.6)


def yearly_table(res: List[dict]) -> Table:
    head = ["Anniversary", "Put in"] + [r["strategy"].split(" ")[0] for r in res]
    rows = [head]
    for i, y in enumerate(res[0]["yearly"]):
        rows.append([y["date"], money(y["invested"])] +
                    [money(r["yearly"][i]["value"]) for r in res])
    widths = [24, 23, 26, 26, 26, 26, 26]
    t = grid(rows, [w * mm for w in widths], align_right_from=1, font_size=7.4)
    t.setStyle(TableStyle([
        ("TEXTCOLOR", (2, 1), (2, -1), WIN),
        ("FONT", (2, 1), (2, -1), FONT_B, 7.4),
    ]))
    return t


def weights_table(res: List[dict]) -> Table:
    symbols = sorted(res[0]["final_weights"].keys())
    rows = [["Strategy"] + symbols]
    for r in res:
        rows.append([r["strategy"]] +
                    [f'{r["final_weights"][s]:.1f}' for s in symbols])
    widths = [30] + [14.8] * len(symbols)
    t = grid(rows, [w * mm for w in widths], align_right_from=1, font_size=6.0)
    t.setStyle(TableStyle([
        ("LEFTPADDING", (1, 0), (-1, -1), 2),
        ("RIGHTPADDING", (1, 0), (-1, -1), 2),
    ]))
    return t


# ------------------------------------------------------------ ledger visuals

def _map_table(rows: List[List], n_cols: int, style: List[tuple]) -> Table:
    col = (178 - 24) / n_cols
    t = Table(rows, colWidths=[24 * mm] + [col * mm] * n_cols)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), FONT_B, 5.8),
        ("FONT", (0, 1), (0, -1), FONT_B, 5.8),
        ("FONT", (1, 1), (-1, -1), FONT, 5.8),
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.white),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ] + style))
    return t


def weight_map(r: dict, symbols: Sequence[str]) -> Table:
    target = 100.0 / len(symbols)
    ledger = r["ledger"]
    rows = [["Stock"] + [d["date"][:4] for d in ledger]]
    style: List[tuple] = []
    for ri, s in enumerate(symbols, start=1):
        line = [s]
        for ci, det in enumerate(ledger, start=1):
            row = next(x for x in det["rows"] if x["symbol"] == s)
            w = row["weight_after"]
            line.append(f"{w:.1f}" if w else DASH)
            if w <= 0:
                style.append(("BACKGROUND", (ci, ri), (ci, ri),
                              colors.HexColor("#eceff3")))
                style.append(("TEXTCOLOR", (ci, ri), (ci, ri), FAINT))
                continue
            dev = (w - target) / target
            style.append(("BACKGROUND", (ci, ri), (ci, ri),
                          shade(OVER if dev > 0 else UNDER,
                                min(1.0, abs(dev) / 0.8))))
        rows.append(line)
    return _map_table(rows, len(ledger), style)


def money_map(r: dict, symbols: Sequence[str]) -> Table:
    ledger = r["ledger"]
    biggest = max((abs(x["amount"]) for d in ledger for x in d["rows"]),
                  default=1.0) or 1.0
    rows = [["Stock"] + [d["date"][:4] for d in ledger]]
    style: List[tuple] = []
    for ri, s in enumerate(symbols, start=1):
        line = [s]
        for ci, det in enumerate(ledger, start=1):
            row = next(x for x in det["rows"] if x["symbol"] == s)
            amt = row["amount"]
            if not amt:
                line.append(DASH)
                style.append(("TEXTCOLOR", (ci, ri), (ci, ri), FAINT))
                continue
            line.append(f"{amt / 1000.0:+.0f}")
            style.append(("BACKGROUND", (ci, ri), (ci, ri),
                          shade(WIN if amt > 0 else WARN,
                                min(1.0, abs(amt) / biggest))))
            if amt < 0:
                style.append(("FONT", (ci, ri), (ci, ri), FONT_B, 5.8))
        rows.append(line)
    return _map_table(rows, len(ledger), style)


def per_stock_table(r: dict, symbols: Sequence[str]) -> Table:
    ps = r["per_symbol"]
    starts, ends = r["start_prices"], r["end_prices"]
    rows = [["Stock", "Price then", "Price now", "Change", "Money in",
             "Money out", "Realised", "Tax", "Held now", "Worth now", "Wt %"]]
    style: List[tuple] = []
    for i, s in enumerate(symbols, start=1):
        d = ps[s]
        chg = (ends[s] / starts[s] - 1.0) * 100.0 if starts[s] else 0.0
        rows.append([s, f'{starts[s]:,.2f}', f'{ends[s]:,.2f}', f'{chg:+.0f}%',
                     money(d["buy_value"]),
                     money(-d["sell_value"]) if d["sell_value"] else DASH,
                     money(d["realised_gain"]) if d["sells"] else DASH,
                     money(d["tax"]) if d["tax"] else DASH,
                     f'{d["final_qty"]:,}', money(d["final_value"]),
                     f'{r["final_weights"][s]:.1f}'])
        style.append(("TEXTCOLOR", (3, i), (3, i), WIN if chg >= 0 else WARN))
        if d["sell_value"]:
            style.append(("TEXTCOLOR", (5, i), (5, i), WARN))
    tot_out = sum(ps[s]["sell_value"] for s in symbols)
    tot_tax = sum(ps[s]["tax"] for s in symbols)
    rows.append(["All ten", "", "", "",
                 money(sum(ps[s]["buy_value"] for s in symbols)),
                 money(-tot_out) if tot_out else DASH,
                 money(sum(ps[s]["realised_gain"] for s in symbols))
                 if tot_out else DASH,
                 money(tot_tax) if tot_tax else DASH, "",
                 money(sum(ps[s]["final_value"] for s in symbols)), "100.0"])

    widths = [22, 15, 15, 12, 21, 21, 19, 16, 13, 21, 10]
    t = Table(rows, colWidths=[w * mm for w in widths])
    last = len(rows) - 1
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), FONT_B, 6.4),
        ("FONT", (0, 1), (-1, -1), FONT, 6.4),
        ("FONT", (0, 1), (0, -1), FONT_B, 6.4),
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, last - 1), [colors.white, BAND]),
        ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#e8edf3")),
        ("FONT", (0, last), (-1, last), FONT_B, 6.4),
        ("LINEABOVE", (0, last), (-1, last), 0.7, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ] + style))
    return t


ACTION_COLOUR = {"ADD": ACCENT, "TRIM": WARN,
                 "EXIT": colors.HexColor("#8c1d10"), "SWAP": WARN, "HOLD": FAINT}
ACTION_BG = {"ADD": ACCENT_BG, "TRIM": WARN_BG,
             "EXIT": colors.HexColor("#f7ded8"), "SWAP": WARN_BG,
             "HOLD": colors.white}


def year_block(det: dict, total_years: int, symbols: Sequence[str]) -> KeepTogether:
    target = 100.0 / len(symbols)
    bits = [f'added {money(det["added"])}',
            f'portfolio {money(det["value_after"])}']
    if det["sells_this_year"]:
        bits.append(f'{det["sells_this_year"]} sold')
    if det["tax_this_year"]:
        bits.append(f'tax {money(det["tax_this_year"])}')
    if det["cash_after"] >= 1:
        bits.append(f'cash left {money(det["cash_after"])}')
    header = Paragraph(
        f'<font name="{FONT_B}" size="9" color="#1f4f8f">Year {det["year"]} of '
        f'{total_years}</font>'
        f'<font name="{FONT_B}" size="9" color="#11161d"> &nbsp;{det["date"]}</font>'
        f'<font size="7.5" color="#5b6775"> &nbsp;&mdash;&nbsp; '
        f'{" &middot; ".join(bits)}'
        f'{" &middot; first purchase" if det["year"] == 1 else ""}</font>',
        ParagraphStyle("YH", fontName=FONT, fontSize=9, leading=12,
                       spaceBefore=7, spaceAfter=2.5))

    data = [["Stock", "Held", "Price", "Value", "Wt %", "Action", "Units",
             "Amount", "Tax", "Wt % after"]]
    style: List[tuple] = []
    for i, r in enumerate(det["rows"], start=1):
        units = r["units"]
        data.append([r["symbol"],
                     f'{r["qty_before"]:,}' if r["qty_before"] else DASH,
                     f'{r["price"]:,.2f}',
                     money(r["value_before"]) if r["value_before"] else DASH,
                     f'{r["weight_before"]:.1f}' if r["weight_before"] else DASH,
                     r["action"],
                     f'{units:+,}' if units else DASH,
                     money(r["amount"], sign=True) if r["amount"] else DASH,
                     money(r["tax"]) if r["tax"] else DASH,
                     f'{r["weight_after"]:.1f}'])
        act = r["action"]
        style.append(("BACKGROUND", (5, i), (5, i), ACTION_BG[act]))
        style.append(("TEXTCOLOR", (5, i), (5, i), ACTION_COLOUR[act]))
        style.append(("FONT", (5, i), (5, i), FONT_B, 6.6))
        if act == "HOLD":
            style.append(("TEXTCOLOR", (0, i), (4, i), MUTED))
            style.append(("TEXTCOLOR", (6, i), (8, i), FAINT))
        if act in ("TRIM", "EXIT", "SWAP"):
            style.append(("FONT", (6, i), (7, i), FONT_B, 6.6))
        w = r["weight_after"]
        if w > 0:
            dev = (w - target) / target
            style.append(("BACKGROUND", (9, i), (9, i),
                          shade(OVER if dev > 0 else UNDER,
                                min(1.0, abs(dev) / 0.8))))

    net = sum(r["amount"] for r in det["rows"])
    tax = sum(r["tax"] for r in det["rows"])
    data.append(["All ten", "", "",
                 money(det["value_before"]) if det["value_before"] else DASH,
                 "100.0" if det["value_before"] else DASH, "", "",
                 money(net, sign=True), money(tax) if tax else DASH, "100.0"])

    widths = [23, 12, 16, 23, 12, 16, 13, 24, 19, 20]
    t = Table(data, colWidths=[w * mm for w in widths])
    last = len(data) - 1
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), FONT_B, 6.6),
        ("FONT", (0, 1), (-1, -1), FONT, 6.6),
        ("FONT", (0, 1), (0, last - 1), FONT_B, 6.6),
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (5, 0), (5, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, last - 1), [colors.white, BAND]),
        ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#e8edf3")),
        ("FONT", (0, last), (-1, last), FONT_B, 6.6),
        ("LINEABOVE", (0, last), (-1, last), 0.7, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ] + style))

    reasons = [f'<b>{r["symbol"]}</b> {r["note"]}' for r in det["rows"]
               if r["note"] and r["action"] in ("TRIM", "EXIT", "SWAP")]
    block = [header, t]
    if reasons:
        block.append(Paragraph(
            "Why sold: " + " &nbsp;&middot;&nbsp; ".join(reasons),
            ParagraphStyle("WHY", fontName=FONT, fontSize=6.4, leading=8.6,
                           textColor=MUTED, spaceBefore=1.5)))
    return KeepTogether(block)


STRATEGY_DETAIL = {
    "S1 Buy & Hold": (
        "Never sell anything.",
        "Each anniversary the fresh money is split ten ways, an equal slice per "
        "stock, regardless of what each one is now worth. This is the "
        "do-nothing benchmark every other rule has to beat.",
    ),
    "S2 Cash-Flow Rebalance": (
        "Never sell. Steer only the new money.",
        "Each anniversary the fresh money goes entirely to the names that have "
        "fallen furthest below a ten per cent share, most underweight first. "
        "Weights get pulled back towards target without a single sale, so no "
        "capital-gains tax is ever triggered by rebalancing.",
    ),
    "S3 Band Rebalance": (
        "Trim above 12.5 per cent, then top up.",
        "Each anniversary, any holding above 12.5 per cent of the sleeve, that "
        "is target times 1.25, is trimmed back to exactly ten per cent using "
        "long-term lots only. Sale proceeds plus the fresh money are then poured "
        "into whatever sits below target. The band stops it reacting to noise.",
    ),
    "S4 Rulebook (your PDF)": (
        "Exit weak, take profit at +100 per cent, add to cheap.",
        "Your written rules, annual version. Exit completely when the business "
        "has failed to compound over five years. Partial-sell back to target "
        "when a holding is up more than one hundred per cent. Deploy new money "
        "into the cheapest eligible names, skipping anything down more than ten "
        "per cent. The fundamental score is proxied by five-year price CAGR, "
        "because no point-in-time ROE, ROCE, pledge or holding-change data "
        "exists in this dataset for the start of the window.",
    ),
    "S5 Momentum Tilt": (
        "Never sell. Buy last year's winners.",
        "Each anniversary the fresh money is split between the three best "
        "performers of the previous twelve months. Included as the mirror image "
        "of the take-profit rule: if trimming winners is wrong, then feeding "
        "them should be right.",
    ),
}


def chapter(r: dict, rank: int, total: int, symbols: Sequence[str]) -> List:
    name = r["strategy"]
    head, detail = STRATEGY_DETAIL[name]
    years = len(r["ledger"])
    target = 100.0 / len(symbols)
    story: List = [
        Paragraph(name, ParagraphStyle("CH", fontName=FONT_B, fontSize=17,
                                       leading=20, textColor=INK, spaceAfter=1)),
        Paragraph(head, ParagraphStyle("CHS", fontName=FONT, fontSize=10.5,
                                       leading=14, textColor=MUTED, spaceAfter=7)),
        stat_cards([
            ("FINISHED", ordinal(rank).title() + f" of {total}",
             "#0b7a51" if rank == 1 else "#11161d", "ranked on XIRR net"),
            ("VALUE TODAY", money(r["paper_value"]), "#11161d",
             f'from {money(r["invested"])} put in'),
            ("AFTER EXIT TAX", money(r["net_value"]), "#11161d",
             f'{pct(r["xirr_net_pct"])} a year'),
            ("TOTAL TAX", money(r["tax_total"]), "#11161d",
             f'{money(r["tax_paid"])} paid on the way'),
            ("SELL DECISIONS", str(r["sell_trades"]), "#11161d",
             f'deepest fall {pct(r["max_drawdown_pct"], 1)}'),
        ]),
        Spacer(1, 5),
        Paragraph(detail, BODY),

        Paragraph("Map 1 &mdash; what share of the portfolio each stock held, "
                  "after every year's decision", H3),
        Paragraph(
            f'Each cell is that stock\'s weight in per cent once the year\'s '
            f'buying and selling was done. Target is {target:.0f} per cent. The '
            f'further a cell drifts from target the stronger its colour, so a '
            f'rule that controls weight shows up as a pale grid and a rule that '
            f'lets winners run shows up as deepening colour.', SMALL),
        legend_strip([(OVER.hexval(), "above target"),
                      (UNDER.hexval(), "below target"),
                      (None, "pale means close to target"),
                      (None, f"{DASH} means not held that year")]),
        weight_map(r, symbols),
        Spacer(1, 7),

        Paragraph("Map 2 &mdash; money into and out of each stock, every year", H3),
        Paragraph(
            "Each cell is thousands of rupees. A positive green figure is money "
            "bought into that stock, a negative red figure is a sale. Colour "
            "depth is scaled to the largest single move this rule made, so the "
            "deepest cells are the decisions that mattered most.", SMALL),
        legend_strip([(WIN.hexval(), "money in, thousands"),
                      (WARN.hexval(), "money out, thousands"),
                      (None, f"{DASH} means untouched that year")]),
        money_map(r, symbols),
        Spacer(1, 7),

        Paragraph("Where each stock finished after the full run", H3),
        per_stock_table(r, symbols),
        Spacer(1, 4),
        Paragraph(
            '<b>Price then</b> and <b>Price now</b> are the split and bonus '
            'adjusted closes on the first and last day of the window. '
            '<b>Money in</b> is everything ever spent buying that stock, '
            '<b>Money out</b> everything ever received selling it, '
            '<b>Realised</b> the gain actually booked and <b>Tax</b> what that '
            'cost. <b>Worth now</b> values the surviving shares at the last '
            'close.', SMALL),

        PageBreak(),
        Paragraph(f'{name} &mdash; year by year', H2),
        Paragraph(
            'Each table is one anniversary. <b>Held</b>, <b>Value</b> and '
            '<b>Wt %</b> are the position as it stood before that year\'s '
            'decision. <b>Action</b>, <b>Units</b>, <b>Amount</b> and <b>Tax</b> '
            'are what was done. <b>Wt % after</b> is where it ended up, shaded '
            'the same way as Map 1.', SMALL),
        Spacer(1, 1),
    ]
    for det in r["ledger"]:
        story.append(year_block(det, years, symbols))
    return story


# -------------------------------------------------------------------- build

def build(tag: str) -> None:
    spec = RUN_SETS[tag]
    main = json.loads((DATA / spec["main"]).read_text())
    variations = []
    for label, fname, desc in spec["variations"]:
        path = DATA / fname
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run the backtest first.")
        variations.append((label, json.loads(path.read_text()), desc))

    f = analyse(main, variations)
    res, best, second, worst = f["res"], f["best"], f["second"], f["worst"]
    ranks, by_name = f["ranks"], f["by_name"]
    symbols = main["basket"]
    years = f["n_years"]
    target = 100.0 / len(symbols)

    out = DOCS / spec["out"]
    doc = BaseDocTemplate(
        str(out), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=15 * mm, bottomMargin=16 * mm,
        title=f'Rebalancing strategy backtest {main["start"]} to {main["end"]}',
        author="aiei_wealth research")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="body")

    def decorate(canvas, _doc):
        canvas.saveState()
        canvas.setFont(FONT, 7.2)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 10 * mm,
                          f'Rebalancing strategy backtest  |  {main["start"]} to '
                          f'{main["end"]}  |  historical simulation, not '
                          f'financial advice')
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm,
                               f"Page {canvas.getPageNumber()}")
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(16 * mm, 13 * mm, A4[0] - 16 * mm, 13 * mm)
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="std", frames=[frame], onPage=decorate)])
    story: List = []

    # ---------------------------------------------------------- page one
    story.append(Paragraph("Which rebalancing rule actually won?", H1))
    story.append(Paragraph(
        f'Five rules, one basket, {best["years"]} years. {main["start"]} to '
        f'{main["end"]}. {money(main["contribution"])} invested on day one '
        f'across {len(symbols)} stocks, then {money(main["contribution"])} more '
        f'every anniversary, {years} instalments in all. Nothing is ever sold '
        f'before it is 365 days old.', SUB))

    story.append(stat_cards([
        ("TOTAL PUT IN", money(best["invested"]), "#11161d",
         f'{years} yearly instalments'),
        ("BEST ENDING VALUE", money(best["paper_value"]), "#0b7a51",
         best["strategy"]),
        ("AFTER EXIT TAX", money(best["net_value"]), "#0b7a51",
         "if you sold everything today"),
        ("XIRR", pct(best["xirr_net_pct"]), "#0b7a51", "net of all tax"),
        ("BEATS LAST PLACE BY", money(best["net_value"] - worst["net_value"]),
         "#1f4f8f", f'vs {worst["strategy"]}'),
    ]))
    story.append(Spacer(1, 9))

    story.append(Paragraph("The result", H2))
    story.append(headline_table(res))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        '<b>XIRR net</b> is the number that matters. It liquidates the whole '
        'portfolio on the last day and pays the deferred capital-gains bill, so '
        'a rule that merely postponed its tax gets no free credit. <b>Max '
        'fall</b> is the deepest peak-to-trough drop the portfolio ever '
        'suffered. <b>Sells</b> counts every trim or exit over the whole run.',
        SMALL))
    story.append(Spacer(1, 8))

    if f["all_won"]:
        won_line = "It won every variation tested as well."
    else:
        lost = "; ".join(f'{lbl} went to {w}' for lbl, w, _v in f["var_winners"]
                         if w != best["strategy"])
        won_line = f'It did not win every variation: {lost}.'
    story.append(callout(
        f'Winner: {best["strategy"]} at {pct(best["xirr_net_pct"])} a year after tax',
        f'It ends {money(best["net_value"] - second["net_value"])} ahead of '
        f'{second["strategy"]} and {money(best["net_value"] - worst["net_value"])} '
        f'ahead of {worst["strategy"]}. {won_line} It paid '
        f'{money(best["tax_total"])} in total tax and took '
        f'{best["sell_trades"]} sell decisions across {years} years.'))
    story.append(Spacer(1, 8))

    story.append(Paragraph("How the test was set up", H2))
    setup = [
        ["Window", f'{main["start"]} to {main["end"]}, {best["years"]} years. The '
                   f'end date is the last day of price data in the local store.'],
        ["Basket", ", ".join(symbols)],
        ["Money in", f'{money(main["contribution"])} on day one split '
                     f'{money(main["contribution"] / len(symbols))} into each of '
                     f'{len(symbols)} stocks, then {money(main["contribution"])} '
                     f'on every anniversary. {money(best["invested"])} in total.'],
        ["Sell rule", "Nothing is sold before 365 days. Every rule obeys this, so "
                      "no result here depends on short-term trading."],
        ["Prices", "Split and bonus adjusted daily closes from the local NSE "
                   "store. Whole shares only; leftover rupees sit in cash earning "
                   "nothing."],
        ["Costs", f'{main["cost_bps"]} basis points per side, covering STT, '
                  f'exchange charges, stamp duty and GST.'],
        ["Tax", "The rate that actually applied on each trade date. Long-term "
                "equity gains were exempt before April 2018, taxed at ten per "
                "cent until 23 July 2024 and 12.5 per cent after, with the 31 "
                "January 2018 grandfathering step-up and the yearly exemption "
                "applied per financial year."],
        ["Residency", main["residency"]],
    ]
    integrity = main.get("integrity") or {}
    if integrity:
        noisiest = max(integrity.items(), key=lambda kv: kv[1]["max_move_pct"])
        flagged = [(s, m) for s, r in integrity.items()
                   for m in r["suspect_moves"]]
        note = (
            f'Split and bonus adjusted closes from '
            f'<b>{main.get("price_source", "the local archive")}</b>. The '
            f'per-symbol parquet store was rejected for this test: several of '
            f'its files are only partly adjusted and at least one has a second '
            f'instrument merged into it, which invents trades at impossible '
            f'prices and changes the ranking outright. Every series used here '
            f'was checked first. The largest single-day move anywhere in the '
            f'basket is {noisiest[1]["max_move_pct"]:.1f} per cent '
            f'({noisiest[0]}), which is a real market move.')
        if flagged:
            note += (" Moves of thirty per cent or more, left in the data and "
                     "listed so they can be checked: " +
                     "; ".join(f'{s} {m["date"]} {m["move_pct"]:+.1f}%'
                               for s, m in flagged) + ".")
        else:
            note += (" No series contains a move of thirty per cent or more, so "
                     "nothing had to be dropped or rescaled.")
        setup.append(["Data check", note])
    rows = [[Paragraph(f"<b>{a}</b>", CELL_B), Paragraph(b, CELL)] for a, b in setup]
    t = Table(rows, colWidths=[26 * mm, 152 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BAND]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)

    # ---------------------------------------------------------- page two
    story.append(PageBreak())
    story.append(Paragraph("How the money grew", H2))
    story.append(growth_chart(res))
    story.append(Spacer(1, 2))
    if f["diverge_at"] is None:
        gap_text = ("The five lines never separate by more than five per cent. "
                    "On this basket the choice of rule barely mattered.")
    else:
        i = f["diverge_at"]
        vals = [r["yearly"][i]["value"] for r in res]
        end_vals = [r["yearly"][-1]["value"] for r in res]
        gap_text = (
            f'The five lines stay within five per cent of each other until '
            f'{res[0]["yearly"][i]["date"]}, year {i + 1}, when the spread first '
            f'opens to {money(max(vals) - min(vals))}. By the final anniversary '
            f'that spread has grown to {money(max(end_vals) - min(end_vals))}. '
            f'Rebalancing earns nothing until the holdings have drifted far '
            f'enough apart to be worth correcting.')
    story.append(Paragraph(gap_text, BODY))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Year by year, in full rupees", H3))
    story.append(yearly_table(res))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Each row is the portfolio value on that anniversary, immediately after "
        "the new instalment was invested. Columns run best to worst. The figures "
        "on page one are measured on the last day of price data, which falls "
        "after the last anniversary, so they are larger than the bottom row "
        "here.", SMALL))

    # -------------------------------------------------------- page three
    story.append(PageBreak())
    story.append(Paragraph("Does the winner survive a harder test?", H2))
    story.append(Paragraph(
        f'One backtest on {len(symbols)} stocks proves very little on its own. '
        f'Three variation runs follow. The ranking has to hold in each.', BODY))
    main_margin = best["net_value"] - second["net_value"]
    for label, payload, desc in variations:
        vres = sorted(payload["results"], key=lambda r: r["xirr_net_pct"],
                      reverse=True)
        story.append(Paragraph(label, H3))
        story.append(Paragraph(desc, BODY))
        story.append(compact_table(vres))
        v_margin = vres[0]["net_value"] - vres[1]["net_value"]
        if vres[0]["strategy"] == best["strategy"]:
            comp = "by more" if v_margin > main_margin else "by less"
            verdict = (f'{best["strategy"]} wins again, {comp}: '
                       f'{money(v_margin)} ahead of second place against '
                       f'{money(main_margin)} in the main run.')
        else:
            place = [r["strategy"] for r in vres].index(best["strategy"]) + 1
            verdict = (f'The order changes here. {vres[0]["strategy"]} comes '
                       f'first and {best["strategy"]} finishes {ordinal(place)}.')
        story.append(Spacer(1, 2))
        story.append(Paragraph(verdict, BODY))
        story.append(Spacer(1, 6))

    # --------------------------------------------------------- page four
    story.append(PageBreak())
    story.append(Paragraph("What each of the five rules actually does", H2))
    for r in res:
        head, detail = STRATEGY_DETAIL[r["strategy"]]
        story.append(KeepTogether([
            Paragraph(f'{r["strategy"]} &mdash; <font color="#5b6775">{head}</font>',
                      H3),
            Paragraph(detail, BODY),
            Paragraph(
                f'<font color="#5b6775">Ended at <b>{money(r["net_value"])}</b> '
                f'after exit tax &nbsp;|&nbsp; {pct(r["xirr_net_pct"])} XIRR '
                f'&nbsp;|&nbsp; {r["sell_trades"]} sells &nbsp;|&nbsp; '
                f'{money(r["tax_total"])} total tax &nbsp;|&nbsp; deepest fall '
                f'{pct(r["max_drawdown_pct"], 1)}</font>', SMALL),
        ]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Where every holding ended up, as a share of the "
                           "stock sleeve", H3))
    story.append(weights_table(res))
    story.append(Spacer(1, 3))
    sp_best = f["spreads"][best["strategy"]]
    spread_text = (
        f'{best["strategy"]} finished with its largest holding at '
        f'{sp_best[1]:.1f} per cent ({sp_best[0]}) and its smallest at '
        f'{sp_best[3]:.1f} per cent ({sp_best[2]}), a spread of {sp_best[4]:.1f} '
        f'points against a {target:.0f} per cent target.')
    sp_s1 = f["spreads"].get("S1 Buy & Hold")
    if sp_s1 and best["strategy"] != "S1 Buy & Hold":
        spread_text += (
            f' Buy and hold let {sp_s1[0]} drift to {sp_s1[1]:.1f} per cent while '
            f'{sp_s1[2]} shrank to {sp_s1[3]:.1f} per cent, a spread of '
            f'{sp_s1[4]:.1f} points.')
    story.append(Paragraph(spread_text, SMALL))

    # --------------------------------------------------------- page five
    story.append(PageBreak())
    story.append(Paragraph("What this changes in your rulebook", H2))
    s1 = by_name.get("S1 Buy & Hold")
    s2 = by_name.get("S2 Cash-Flow Rebalance")
    lead_pp = best["xirr_net_pct"] - second["xirr_net_pct"]
    if lead_pp < 0.5:
        simpler = min([best, second], key=lambda r: r["sell_trades"])
        other = second if simpler is best else best
        story.append(callout(
            f'Treat {best["strategy"]} and {second["strategy"]} as a tie, '
            f'then pick {simpler["strategy"]}',
            f'They finish {lead_pp:.2f} percentage points apart, '
            f'{money(best["net_value"] - second["net_value"])} on '
            f'{money(best["invested"])} invested. That is inside the noise of a '
            f'single basket over one market path, so calling either one the '
            f'winner would be overreading the data. What does separate them is '
            f'work and tax: {simpler["strategy"]} reached the same place with '
            f'{simpler["sell_trades"]} sell decisions and '
            f'{money(simpler["tax_total"])} of tax, against '
            f'{other["sell_trades"]} sells and {money(other["tax_total"])} for '
            f'the other. Fewer decisions, fewer chances to be wrong.',
            ACCENT))
    elif (best["strategy"] == "S3 Band Rebalance" and s1 and s2
            and best["net_value"] > s1["net_value"]):
        free = ((s2["net_value"] - s1["net_value"]) /
                (best["net_value"] - s1["net_value"]) * 100.0)
        story.append(callout(
            "Use S3, but fund it the S2 way",
            f'Point the fresh {money(main["contribution"])} at your most '
            f'underweight holdings first. Only after that money is spent should '
            f'you sell anything, and only from names still above '
            f'{target * 1.25:.1f} per cent of the sleeve. Of the whole advantage '
            f'over buy and hold, {free:.0f} per cent was already captured by '
            f'steering new money alone, which costs no tax at all. Only the '
            f'remaining {100 - free:.0f} per cent required actual selling.'))
    else:
        extra = ""
        if s1 and best["net_value"] > s1["net_value"] and s2:
            free = ((s2["net_value"] - s1["net_value"]) /
                    (best["net_value"] - s1["net_value"]) * 100.0)
            extra = (f' Worth knowing before you copy it: of the whole advantage '
                     f'over buy and hold, {free:.0f} per cent was already '
                     f'captured by simply steering new money to the most '
                     f'underweight names, which costs no tax at all. The other '
                     f'{100 - free:.0f} per cent is what the selling bought you, '
                     f'and it came with {best["sell_trades"]} sell decisions and '
                     f'{money(best["tax_total"])} of tax.')
        story.append(callout(
            f'Run {best["strategy"]}',
            f'It finished first on this basket at {pct(best["xirr_net_pct"])} a '
            f'year after tax, {lead_pp:.2f} percentage points and '
            f'{money(best["net_value"] - second["net_value"])} ahead of '
            f'{second["strategy"]}, and '
            f'{money(best["net_value"] - worst["net_value"])} ahead of '
            f'{worst["strategy"]}.{extra}'))
    story.append(Spacer(1, 8))

    s4 = by_name.get("S4 Rulebook (your PDF)")
    if s4:
        exits = exit_events(s4)
        trims = trim_events(s4, s4["end_prices"])
        back = [e for e in exits if e["back"]]
        higher = [e for e in back if e["higher"]]
        rose = [t for t in trims if t["rose_after"]]
        s4_rank = ranks[s4["strategy"]]
        story.append(Paragraph("How your written rules actually did, measured", H3))
        if s4_rank == 1:
            gap_pp = s4["xirr_net_pct"] - second["xirr_net_pct"]
            if gap_pp >= 1.0:
                verdict = (f'That is a decisive margin, not a rounding error, '
                           f'and it survives the tax bill.')
            elif gap_pp >= 0.5:
                verdict = (f'That is a real but modest margin.')
            else:
                verdict = (f'That margin is small enough to be luck.')
            opener = (
                f'<b>Your rulebook finished first of {len(res)}</b>, ending at '
                f'{money(s4["net_value"])} after exit tax, '
                f'{money(s4["net_value"] - second["net_value"])} ahead of '
                f'{second["strategy"]} and '
                f'{money(s4["net_value"] - worst["net_value"])} ahead of '
                f'{worst["strategy"]}. {verdict} It got there with '
                f'{s4["sell_trades"]} sell decisions and '
                f'{money(s4["tax_total"])} of tax, against '
                f'{second["sell_trades"]} sells and '
                f'{money(second["tax_total"])} for the runner-up, so it is also '
                f'the most work of the rules tested.')
        else:
            opener = (
                f'<b>Your rulebook finished {ordinal(s4_rank)} of {len(res)}</b>, '
                f'ending at {money(s4["net_value"])} after exit tax against '
                f'{money(best["net_value"])} for {best["strategy"]}, a gap of '
                f'{money(best["net_value"] - s4["net_value"])}. It made '
                f'{s4["sell_trades"]} sell decisions to get there, against '
                f'{best["sell_trades"]} for the winner.')
        points = [opener]
        if trims:
            points.append(
                f'<b>Taking profit above one hundred per cent fired '
                f'{len(trims)} times.</b> Of those, {len(rose)} were in stocks '
                f'whose price was still higher on the last day of the window than '
                f'on the day of the sale. Selling because a holding is up a lot '
                f'is not the same as selling because it has grown too large, and '
                f'this is where the rule leaks.')
        if exits:
            reentry = ""
            if len(back) == len(exits):
                reentry = (f' Every one of them was bought back in a later year, '
                           f'and {len(higher)} of those repurchases were at a '
                           f'higher price than the exit.')
            elif back:
                reentry = (f' {len(back)} of them were bought back in a later '
                           f'year, and {len(higher)} of those repurchases were at '
                           f'a higher price than the exit.')
            points.append(
                f'<b>Exit completely fired {len(exits)} times.</b>{reentry} The '
                f'rule sells into weakness, and the buy condition then blocks '
                f're-entry while the same name recovers. Keep a full exit for a '
                f'genuinely broken business, but require a second confirmation '
                f'and allow re-entry as soon as the score recovers.')
        points.append(
            f'<b>A two to ten per cent band cannot work with {len(symbols)} '
            f'holdings.</b> Equal weight is already {target:.0f} per cent, so a '
            f'{target:.0f} per cent ceiling puts every position in permanent '
            f'breach. Express the band as a multiple of target instead: trim '
            f'above 1.25 times target, top up below 0.75 times.')
        story.append(bullets(points))
        story.append(Spacer(1, 6))

    story.append(Paragraph("The rule to run from here", H3))
    story.append(bullets([
        'Review once a year on a fixed date.',
        f'Target weight is 100 divided by the number of holdings, '
        f'{target:.0f} per cent here.',
        f'Trim only what is above {target * 1.25:.1f} per cent, and only from '
        f'lots older than 365 days. If the lot is not yet mature, wait rather '
        f'than pay short-term rates.',
        'Spend new money before you sell. Most drift can be corrected with '
        'contributions alone.',
        'Watch the yearly long-term exemption. Splitting a large trim across two '
        'financial years uses two exemptions instead of one.',
        'Never sell a position simply because it has doubled.',
    ]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("What this test cannot tell you", H2))
    story.append(bullets([
        f'The {len(symbols)} names were chosen from companies that still trade '
        f'today, so the basket is flattered by survivorship. The comparison '
        f'between rules is still fair, because all five ran on exactly the same '
        f'stocks, dates and money.',
        'The rulebook rule could not use real fundamentals. No point-in-time ROE, '
        'ROCE, pledge or holding-change data exists in this dataset for the start '
        'of the window, so five-year price CAGR stood in for the twelve-point '
        'score. A genuine fundamental score could rank differently.',
        'Dividends are excluded from the headline table. The dividend variation '
        'applies a flat assumed yield, not actual payout records.',
        'One market path, one country, one window. Expect smaller gaps between '
        'the rules in a flatter market.',
        f'Prices run to {main["end"]}, the last date in the local store. Nothing '
        f'after that is included.',
    ]))

    # ------------------------------------------------- part two: chapters
    order = sorted(by_name, key=lambda n: n[:2])
    story.append(PageBreak())
    story.append(Paragraph("Part two &mdash; the full ledger", H1))
    story.append(Paragraph(
        f'Every decision, every year, every stock. Five chapters, one per rule, '
        f'{years} anniversaries each. Same {len(symbols)} stocks, same money, '
        f'same dates. The only thing that changes between chapters is the rule '
        f'being followed.', SUB))
    contents = [["Chapter", "Rule in one line", "Finished", "XIRR net",
                 "Value after exit tax"]]
    for name in order:
        contents.append([name, STRATEGY_DETAIL[name][0],
                         ordinal(ranks[name]).title(),
                         pct(by_name[name]["xirr_net_pct"]),
                         money(by_name[name]["net_value"])])
    story.append(grid(contents, [36 * mm, 66 * mm, 22 * mm, 22 * mm, 32 * mm],
                      highlight_row=order.index(best["strategy"]) + 1,
                      align_right_from=2, font_size=8))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Each chapter opens with three views", H3))
    story.append(bullets([
        '<b>Map 1</b> is the weight of every stock after every year\'s decision, '
        'one column per year, shaded by how far it sits from target. This is the '
        'fastest way to see what a rule really does: a disciplined rule produces '
        'a pale, even grid, a passive rule produces deepening colour as the '
        'winners take over.',
        '<b>Map 2</b> is the rupees moved into or out of each stock each year, in '
        'thousands, green for buying and red for selling. Read it alongside Map 1 '
        'to see which decision caused which weight change.',
        '<b>The per-stock table</b> settles the whole run for each holding: price '
        'then and now, everything spent, everything received, gain booked, tax '
        'paid and what is left.',
        'Then the year tables give the full detail. <b>ADD</b> means new money '
        'went in, <b>TRIM</b> means part of the position was sold back to target, '
        '<b>EXIT</b> means the whole position was closed, <b>HOLD</b> means '
        'nothing was done. Holdings are whole shares only, so amounts rarely land '
        'on a round number; anything left over sits in cash and is shown in the '
        'year heading.',
    ]))

    for name in order:
        story.append(PageBreak())
        story.extend(chapter(by_name[name], ranks[name], len(res), symbols))

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)
    print(f"Wrote {out}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "v2")
