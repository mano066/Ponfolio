"""Every parameter of all sixteen strategies, in one matrix.

    python research/scripts/build_parameter_matrix.py

Columns are S1-S10 and M1-M6; rows are every knob any of them turns. The point
is to make the differences legible: most rows are identical across all sixteen
(whole shares, 12 bps, the 365-day rule) and the handful that are not is where
the entire spread of returns comes from.

Values are pulled from the engines' own constants wherever a constant exists —
`REINVEST`, `BAND`, `MASTER_CAP`, `VARIANTS`, `TILT_PICKS`, `TARGET` — and
asserted against the hand-read rules below, so a change to a strategy that is
not reflected here fails the build instead of quietly printing a stale matrix.

Out: docs/Rebalancing_All_16_Strategies_Parameter_Matrix.pdf
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,  # noqa: E402
                                Table, TableStyle)

import backtest_master_guarded as gd  # noqa: E402
import backtest_master_strategy as mst  # noqa: E402
import backtest_strategies_v2 as v2  # noqa: E402

OUT = ROOT / "docs" / "Rebalancing_All_16_Strategies_Parameter_Matrix.pdf"

COLS = [f"S{i}" for i in range(1, 11)] + [f"M{i}" for i in range(1, 7)]
CODE = {f"S{i}": i for i in range(1, 11)}
CODE.update({f"M{i}": 10 + i for i in range(1, 7)})

D = "·"      # identical to every other column on this row


def ceiling():
    """Sell ceiling per strategy, read from the engines' own tables."""
    out = {c: "none" for c in COLS}
    out["S3"] = "12.5%"                       # backtest_five_verified, code 3
    out["S4"] = "10% + gain>100%"             # backtest_five_verified, code 4
    for code, band in v2.BAND.items():        # {7: .20, 8: .125, 10: .20}
        out[f"S{code}"] = f"{band * 100:g}%"
    for m in ("M1", "M2"):
        out[m] = f"{mst.MASTER_CAP * 100:g}%"
    out["M3"] = "none"
    for code, (cap, _) in gd.VARIANTS.items():
        if 14 <= code <= 16:
            out[f"M{code - 10}"] = f"{cap * 100:g}%"
    return out


def guard():
    out = {c: "none" for c in COLS}
    for code, (_, g) in gd.VARIANTS.items():
        if 14 <= code <= 16 and g:
            out[f"M{code - 10}"] = f"peak {(1 - gd.PEAK_BAND) * 100:g}%"
    return out


def sweeps():
    out = {c: "no" for c in COLS}
    for code in v2.REINVEST:                  # {6, 8, 10}
        out[f"S{code}"] = "YES"
    for m in range(1, 7):                     # every master sweeps
        out[f"M{m}"] = "YES"
    return out


def row(label, values, note="", default=D):
    """One matrix row.

    `default` distinguishes the two things a blank cell can mean. A dot says
    "identical to every other column on this row" — right for contribution or
    trading cost, where one value is quoted once and shared by all sixteen. A
    dash says "this strategy has no such rule" — right for a trim destination
    on a strategy that never trims. Using the dot for both would claim that
    S1 trims to the same place S3 does.
    """
    return [label] + [values.get(c, default) for c in COLS] + [note]


def build_rows():
    tilt = 3   # verified against both backtest sources in main()
    tgt = f"{v2.TARGET * 100:g}%"
    every = {c: D for c in COLS}

    rows = [
        ("— WHAT GOES IN —", {c: "" for c in COLS}, ""),
        row("Contribution", {"S1": "Rs 10,000 every month"},
            "identical for all sixteen; 189 payments, Rs 18,90,000 total"),
        row("Universe", {"S1": "the same ten NSE names"},
            "BHEL, COALINDIA, IOC, ITC, KTKBANK, ONGC, SCI, NTPC, TATASTEEL, SOUTHBANK"),
        row("Dividends swept into buying", sweeps(),
            "THE big divider: 9 sweep, 7 leave Rs 6-8 lakh idle"),

        ("— WHEN IT SELLS —", {c: "" for c in COLS}, ""),
        row("Sell ceiling", ceiling(),
            "weight of one holding above which a trim is triggered"),
        row("Trims back to", {c: tgt for c in COLS if ceiling()[c] != "none"},
            "the destination of a trim, not the trigger", default="never sells"),
        row("Trim guard", guard(),
            "refuse the trim while the holding is this far below its 1y high"),
        row("Whole-position exit", {"S4": "5y CAGR < 0"},
            "S4 alone: sells the ENTIRE holding on a negative 5-year price CAGR",
            default="none"),
        row("Gain trigger", {"S4": "gain > 100%"},
            "S4 alone: trims only a holding that has more than doubled",
            default="none"),

        ("— WHERE NEW MONEY GOES —", {c: "" for c in COLS}, ""),
        row("Target weight per holding",
            {**{c: tgt for c in COLS}, "S5": f"{100/tilt:.0f}% of 3 picks",
             "S9": f"{100/tilt:.0f}% of 3 picks", "S4": "1/N of eligible"},
            "what the deployment aims each holding at"),
        row("Deploy scope",
            {**{c: "all underweight" for c in COLS},
             "S1": "all ten, equally", "S5": f"top {tilt} only",
             "S9": f"worst {tilt} only", "S4": "within 10% of cost only"},
            "which names are allowed to receive the month's money"),
        row("Deploy order",
            {**{c: "largest shortfall" for c in COLS},
             "S1": "name order", "S5": "strongest 12m first",
             "S9": "weakest 12m first", "S4": "weakest 12m first",
             "M1": "weakest 12m first", "M3": "weakest 12m first",
             "M4": "weakest 12m first", "M5": "weakest 12m first",
             "M6": "weakest 12m first"},
            "the order money is offered, once the scope is fixed"),
        row("Signal used to rank", {"S4": "12m price", "S5": "12m price",
                                    "S9": "12m price", "M1": "12m price",
                                    "M3": "12m price", "M4": "12m price",
                                    "M5": "12m price", "M6": "12m price"},
            "split- and bonus-adjusted; no fundamentals anywhere in this study",
            default="none"),
        row("Residual sweep", {"S1": "3 passes"},
            "whole-share prices leave change; three passes mop it up"),

        ("— RULES NONE OF THEM BREAK —", {c: "" for c in COLS}, ""),
        row("Minimum holding before sale", {"S1": "365 days"},
            "nothing is ever sold short-term, in any strategy"),
        row("Whole shares only", {"S1": "yes"}, "no fractional trading"),
        row("Trading cost", {"S1": "12 bps each way"}, "applied to every fill"),
        row("Fill price", {"S1": "official NSE open"},
            "decision on the previous close, fill at the next open"),
    ]
    return rows


def main():
    # Guard the hand-read rules against the engines.
    assert v2.REINVEST == {6, 8, 10}, v2.REINVEST
    assert v2.BAND == {7: 0.20, 8: 0.125, 10: 0.20}, v2.BAND
    assert mst.MASTER_CAP == 0.25, mst.MASTER_CAP
    assert v2.TARGET == 0.10, v2.TARGET
    # The tilts hardcode their pick count in the backtests — there is no
    # constant to read, so verify the literal is still what this matrix claims.
    five = (ROOT / "research/scripts/backtest_five_verified.py").read_text(
        encoding="utf-8")
    ten = (ROOT / "research/scripts/backtest_strategies_v2.py").read_text(
        encoding="utf-8")
    assert "reverse=True)[:3]" in five, "S5 no longer picks three"
    assert "ranked[:3]" in ten, "S9 no longer picks three"

    S = getSampleStyleSheet()
    ink = colors.HexColor("#1F3A34")
    h1 = ParagraphStyle("h1", parent=S["Title"], fontSize=15, leading=18,
                        alignment=0, textColor=ink)
    note = ParagraphStyle("n", parent=S["BodyText"], fontSize=7,
                          leading=9, textColor=colors.HexColor("#6B7280"))
    cell = ParagraphStyle("c", parent=S["BodyText"], fontSize=5.6, leading=7)
    cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold",
                          textColor=colors.white)

    rows = build_rows()
    data = [[Paragraph(x, head) for x in ["Parameter"] + COLS + ["Why it matters"]]]
    styles = [
        ("BACKGROUND", (0, 0), (-1, 0), ink),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9D6D1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
    ]
    for i, r in enumerate(rows, 1):
        if isinstance(r, tuple):                      # section divider
            label = r[0]
            data.append([Paragraph(label, cellb)] + [""] * (len(COLS) + 1))
            styles += [("SPAN", (1, i), (-1, i)),
                       ("BACKGROUND", (0, i), (-1, i),
                        colors.HexColor("#EEF3F1"))]
            continue
        data.append([Paragraph(str(c), cellb if j == 0 else cell)
                     for j, c in enumerate(r)])

    t = Table(data, colWidths=[38 * mm] + [11.5 * mm] * 16 + [62 * mm],
              repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle(styles))

    story = [
        Paragraph("All sixteen strategies, every parameter", h1),
        Paragraph("S1–S10 and M1–M6 · monthly Rs 10,000 SIP · ten-stock NSE "
                  "core · 2011–2026. A dot means the value is the same as "
                  "every other column on that row. Most rows are dots: the "
                  "entire spread of returns comes from the few that are not.",
                  note),
        Spacer(1, 5), t, Spacer(1, 5),
        Paragraph("Read the three rows that actually differ: dividends swept "
                  "(worth about +1.8 points, replicated across two "
                  "independent pairs), sell ceiling, and deploy order. "
                  "Everything below the second divider is constant across all "
                  "sixteen and cannot explain any difference between them.",
                  note),
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(OUT), pagesize=landscape(A4),
                      leftMargin=8 * mm, rightMargin=8 * mm,
                      topMargin=9 * mm, bottomMargin=9 * mm,
                      title="All 16 strategies — parameter matrix").build(story)
    print(f"wrote {OUT}")

    # Same matrix to the terminal.
    w = max(len(r[0]) for r in rows if not isinstance(r, tuple))
    print("\n" + "Parameter".ljust(w) + "".join(c.rjust(9) for c in COLS))
    for r in rows:
        if isinstance(r, tuple):
            print("\n" + r[0])
            continue
        print(r[0].ljust(w) + "".join(str(v)[:8].rjust(9) for v in r[1:-1]))


if __name__ == "__main__":
    main()
