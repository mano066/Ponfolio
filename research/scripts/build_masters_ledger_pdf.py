"""M1-M6 ledger report, with S10 as the benchmark they have to beat.

    python research/scripts/build_masters_ledger_pdf.py

Six master variants share one engine and differ only in the sell leg, so a
"full ledger" of all 189 monthly reviews x 7 books would be thousands of
identical HOLD rows. What actually differs is:

  * every SELL each variant made, and
  * every trim a guard REFUSED to make,

so those are printed in full, dated, priced, with the weight that triggered
them. The year-end state of each book is printed beside them so the compounding
is visible rather than asserted.

Out: docs/Masters_M1_M6_Ledger_vs_S10.pdf
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,  # noqa: E402
                                Spacer, Table, TableStyle)

import backtest_master_guarded as gd  # noqa: E402
from backtest_five_verified import Data  # noqa: E402

OUT = ROOT / "docs" / "Masters_M1_M6_Ledger_vs_S10.pdf"

# S10 first: it is the incumbent, and three of the six masters lose to it.
BENCH = 10
MASTERS = [11, 12, 13, 14, 15, 16]

INK = colors.HexColor("#1F3A34")
MUTED = colors.HexColor("#6B7280")
RULE = colors.HexColor("#C9D6D1")
BAND = colors.HexColor("#EEF3F1")
RED = colors.HexColor("#B3261E")
GREEN = colors.HexColor("#1B5E20")

S = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=S["Title"], fontSize=17, leading=21,
                    textColor=INK, alignment=0, spaceAfter=4)
H2 = ParagraphStyle("H2", parent=S["Heading2"], fontSize=11.5, leading=14,
                    textColor=INK, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("BODY", parent=S["BodyText"], fontSize=8.6, leading=11.6,
                      textColor=colors.HexColor("#333333"))
NOTE = ParagraphStyle("NOTE", parent=BODY, fontSize=7.6, leading=10,
                      textColor=MUTED)


def rupees(v, dec=0):
    """Indian digit grouping: 1,08,254 not 108,254."""
    neg = v < 0
    s = f"{abs(v):.{dec}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    out = whole + ("." + frac if frac else "")
    return ("-" if neg else "") + out


def grid(data, widths, align_right=(), head_bg=INK, font=7.4):
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), head_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font),
        ("LEADING", (0, 0), (-1, -1), font + 2.4),
        ("GRID", (0, 0), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
    ]
    for c in align_right:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def run_books():
    """Every book we report on, plus its pre- and after-tax result."""
    data = Data()
    books, rows = {}, {}
    for code in [BENCH] + MASTERS:
        b = gd.GuardedBook(data, code, months=None)
        b.ticket = 10000
        r = b.run()
        t = gd.GuardedBook(data, code, 12, after_tax=True, months=None)
        t.ticket = 10000
        rt = t.run()
        r["after_tax_xirr_pct"] = rt["xirr_pct"]
        r["ltcg_paid"] = t.ltcg_paid
        r["skips"] = [x for x in b.logs if x["event"] == "SKIP_TRIM"]
        r["sell_log"] = [x for x in b.logs if x["event"] == "SELL"]
        books[code], rows[code] = b, r
        print(f"  {r['name'][:46]:<48} {r['xirr_pct']:6.2f}%  "
              f"sells={r['sells']:<3} skips={len(r['skips'])}", flush=True)
    return books, rows


SHORT = {
    10: "Wide 20% band + dividends",
    11: "Master: 25% cap, weakest-first",
    12: "Control: 25% cap, shortfall-first",
    13: "Control: no cap, weakest-first",
    14: "25% cap + peak guard",
    15: "12.5% cap + peak guard",
    16: "12.5% cap, no guard",
}


def short(code, rows):
    """Hand-written, because splitting the run names left M2 and M3 both
    reading "Control" — two different controls, indistinguishable on the page."""
    return SHORT.get(code, rows[code]["name"][:34])


def front(story, rows):
    story.append(Paragraph("M1–M6 versus S10", H1))
    story.append(Paragraph(
        "Ten-stock NSE core · Rs 10,000 on the first trading day of each month "
        "· January 2011 to the last session on file · whole shares · official "
        "opens as fills · 12 bps costs · real corporate actions · nothing sold "
        "before it is 365 days old.", NOTE))

    story.append(Paragraph("What the six masters change", H2))
    story.append(Paragraph(
        "All six sweep dividends back into the next top-up and all six aim "
        "every holding at a 10% target. They differ only in how the sell leg "
        "behaves, so any gap between them is attributable to that and nothing "
        "else. S10 is the incumbent: wide 20% band, dividends reinvested, "
        "shortfall-ordered deployment.", BODY))
    spec = [["", "Ceiling", "Deploy order", "Trim guard", "What it isolates"],
            ["S10", "20%", "largest shortfall", "none",
             "the benchmark the masters must beat"],
            ["M1", "25%", "weakest first", "none", "the current master"],
            ["M2", "25%", "largest shortfall", "none",
             "control: is weakest-first ordering worth anything?"],
            ["M3", "no cap", "weakest first", "none",
             "control: is the cap worth anything?"],
            ["M4", "25%", "weakest first", "trailing peak",
             "M1 plus the guard"],
            ["M5", "12.5%", "weakest first", "trailing peak",
             "does a guard make a TIGHT band safe?"],
            ["M6", "12.5%", "weakest first", "none",
             "control for M5: the tight band alone"]]
    story.append(Spacer(1, 3))
    story.append(grid(spec, [16 * mm, 17 * mm, 30 * mm, 22 * mm, 105 * mm],
                      align_right=()))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "The trailing-peak guard refuses a trim while the holding sits more "
        "than 5% below its own highest close of the past twelve months. The "
        "reasoning is that such a sale is late: the weight breach was caused "
        "by the price falling, or by the rest of the book falling, not by this "
        "holding growing into its ceiling.", BODY))

    story.append(Paragraph("Scoreboard", H2))
    head = ["", "Strategy", "Terminal (Rs)", "XIRR", "After tax", "Sells",
            "Trims refused", "LTCG paid (Rs)"]
    body = [head]
    for code in [BENCH] + MASTERS:
        r = rows[code]
        body.append([
            "S10" if code == BENCH else f"M{code - 10}",
            short(code, rows),
            rupees(r["terminal_after_cost"]),
            f"{r['xirr_pct']:.2f}%",
            f"{r['after_tax_xirr_pct']:.2f}%",
            str(r["sells"]),
            str(len(r["skips"])),
            rupees(r["ltcg_paid"]),
        ])
    story.append(Spacer(1, 3))
    story.append(grid(body, [12 * mm, 62 * mm, 30 * mm, 18 * mm, 20 * mm,
                             14 * mm, 24 * mm, 26 * mm],
                      align_right=(2, 3, 4, 5, 6, 7)))

    bench = rows[BENCH]
    beat = [c for c in MASTERS if rows[c]["xirr_pct"] > bench["xirr_pct"]]
    lost = [c for c in MASTERS if rows[c]["xirr_pct"] <= bench["xirr_pct"]]
    story.append(Spacer(1, 6))
    words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}
    story.append(Paragraph(
        f"<b>{words.get(len(beat), len(beat))} of the six beat S10 and "
        f"{words.get(len(lost), len(lost)).lower()} do not.</b> Ahead: "
        f"{', '.join('M%d' % (c - 10) for c in beat)}. Behind: "
        f"{', '.join('M%d' % (c - 10) for c in lost)}. "
        f"M6 in particular — the tight 12.5% band with no guard — finishes "
        f"{bench['xirr_pct'] - rows[16]['xirr_pct']:.2f} points BELOW S10 "
        f"while making {rows[16]['sells']} sales against S10's "
        f"{bench['sells']}. Trading more did not pay.", BODY))
    story.append(PageBreak())


def head_to_head_m6(story, rows):
    """The instructive loser: S10 against M6."""
    story.append(Paragraph("S10 against M6 — what actually differs", H1))
    s10, m6 = rows[BENCH], rows[16]
    story.append(Paragraph(
        "Both reinvest dividends. Both aim at a 10% target. M6 deploys to the "
        "weakest holding first where S10 fills the largest rupee shortfall — "
        "and M2 versus M1 shows that ordering is worth little. The material "
        "difference is the ceiling: 12.5% against 20%.", BODY))

    cmp_rows = [["", "S10", "M6", "Difference"],
                ["Ceiling", "20%", "12.5%", "M6 trims far sooner"],
                ["Sells made", str(s10["sells"]), str(m6["sells"]),
                 f"{m6['sells'] - s10['sells']:+d} more sales"],
                ["XIRR, pre-tax", f"{s10['xirr_pct']:.2f}%",
                 f"{m6['xirr_pct']:.2f}%",
                 f"{m6['xirr_pct'] - s10['xirr_pct']:+.2f} pts"],
                ["XIRR, after tax", f"{s10['after_tax_xirr_pct']:.2f}%",
                 f"{m6['after_tax_xirr_pct']:.2f}%",
                 f"{m6['after_tax_xirr_pct'] - s10['after_tax_xirr_pct']:+.2f} pts"],
                ["Terminal wealth", rupees(s10["terminal_after_cost"]),
                 rupees(m6["terminal_after_cost"]),
                 rupees(m6["terminal_after_cost"] - s10["terminal_after_cost"])],
                ["Capital gains tax", rupees(s10["ltcg_paid"]),
                 rupees(m6["ltcg_paid"]),
                 rupees(m6["ltcg_paid"] - s10["ltcg_paid"])]]
    story.append(Spacer(1, 4))
    story.append(grid(cmp_rows, [40 * mm, 34 * mm, 34 * mm, 62 * mm],
                      align_right=(1, 2)))
    story.append(Spacer(1, 7))
    story.append(Paragraph(
        f"<b>The answer to \"what is different\".</b> M6 sells "
        f"{m6['sells']} times where S10 sells {s10['sells']}. Every one of "
        f"those extra sales takes a holding that had grown and cuts it back to "
        f"10%, paying 12 bps on the way out and — once the units are long-term "
        f"— capital gains tax on the realised profit. M6 paid "
        f"{rupees(m6['ltcg_paid'])} against S10's {rupees(s10['ltcg_paid'])}. "
        f"In exchange it gets a more evenly weighted book. Over this basket and "
        f"this period the even weighting was worth less than the tax and the "
        f"forgone compounding, and M6 finishes "
        f"{rupees(s10['terminal_after_cost'] - m6['terminal_after_cost'])} "
        f"rupees poorer.", BODY))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "M5 is the same 12.5% band with the peak guard attached. It recovers "
        f"{rows[15]['xirr_pct'] - m6['xirr_pct']:+.2f} points pre-tax and "
        f"{rows[15]['after_tax_xirr_pct'] - m6['after_tax_xirr_pct']:+.2f} "
        "after tax by refusing "
        f"{len(rows[15]['skips'])} of the trims M6 makes — but it does not "
        "recover enough to overtake S10. The guard improves a tight band; it "
        "does not rescue one.", BODY))
    story.append(PageBreak())


def head_to_head_m4(story, rows):
    """S10 against M4 — the variant that actually wins, and where it wins.

    Three things change at once between S10 and M4, so the headline gap is
    useless on its own. The controls already in this run let the gap be walked
    one change at a time along a single path, which is the only way to say
    which ingredient earned what.
    """
    s10, m4 = rows[BENCH], rows[14]
    story.append(Paragraph("S10 against M4 — what actually differs", H1))
    story.append(Paragraph(
        "M4 is the best of the six on both bases. It differs from S10 in three "
        "ways at once — a wider ceiling, a different deployment order, and the "
        "trailing-peak guard — so the headline gap has to be taken apart "
        "before it means anything.", BODY))

    cmp_rows = [["", "S10", "M4", "Difference"],
                ["Ceiling", "20%", "25%", "M4 trims later"],
                ["Deploy order", "largest shortfall", "weakest first",
                 "M4 feeds the worst performer"],
                ["Trim guard", "none", "trailing peak, 5%",
                 "M4 refuses a late sale"],
                ["Sells made", str(s10["sells"]), str(m4["sells"]),
                 f"{m4['sells'] - s10['sells']:+d}"],
                ["Trims refused", "0", str(len(m4["skips"])),
                 "the guard fired once in 189 reviews"],
                ["XIRR, pre-tax", f"{s10['xirr_pct']:.2f}%",
                 f"{m4['xirr_pct']:.2f}%",
                 f"{m4['xirr_pct'] - s10['xirr_pct']:+.2f} pts"],
                ["XIRR, after tax", f"{s10['after_tax_xirr_pct']:.2f}%",
                 f"{m4['after_tax_xirr_pct']:.2f}%",
                 f"{m4['after_tax_xirr_pct'] - s10['after_tax_xirr_pct']:+.2f} pts"],
                ["Terminal wealth", rupees(s10["terminal_after_cost"]),
                 rupees(m4["terminal_after_cost"]),
                 rupees(m4["terminal_after_cost"] - s10["terminal_after_cost"])],
                ["Capital gains tax", rupees(s10["ltcg_paid"]),
                 rupees(m4["ltcg_paid"]),
                 rupees(m4["ltcg_paid"] - s10["ltcg_paid"])]]
    story.append(Spacer(1, 4))
    story.append(grid(cmp_rows, [34 * mm, 34 * mm, 34 * mm, 66 * mm],
                      align_right=(1, 2)))

    story.append(Paragraph("Where the gain comes from", H2))
    story.append(Paragraph(
        "One change per step, each step an actual run in this study rather "
        "than an estimate. Read down: S10 becomes M4.", BODY))
    steps = [("S10", BENCH, "20% ceiling, shortfall-ordered, no guard",
              "the incumbent"),
             ("M2", 12, "ceiling widened to 25%", "fewer trims: 3 sells to 1"),
             ("M1", 11, "deployment reordered to weakest-first",
              "same money, different destination each month"),
             ("M4", 14, "trailing-peak guard added", "one late sale refused")]
    body = [["", "Change from the row above", "XIRR", "Step", "After tax",
             "Step", "What the step buys"]]
    prev = None
    for tag, code, change, buys in steps:
        r = rows[code]
        pre = r["xirr_pct"]
        aft = r["after_tax_xirr_pct"]
        body.append([
            tag, change, f"{pre:.2f}%",
            "—" if prev is None else f"{pre - prev[0]:+.2f}",
            f"{aft:.2f}%",
            "—" if prev is None else f"{aft - prev[1]:+.2f}",
            buys])
        prev = (pre, aft)
    story.append(Spacer(1, 3))
    story.append(grid(body, [12 * mm, 62 * mm, 17 * mm, 14 * mm, 19 * mm,
                             14 * mm, 70 * mm],
                      align_right=(2, 3, 4, 5)))

    total_pre = m4["xirr_pct"] - s10["xirr_pct"]
    total_aft = m4["after_tax_xirr_pct"] - s10["after_tax_xirr_pct"]
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>The gap is {total_pre:+.2f} points pre-tax and {total_aft:+.2f} "
        f"after tax, and no single ingredient supplies it.</b> It arrives in "
        f"three comparable pieces: widening the ceiling, reordering the "
        f"deployment, and guarding the trim. Anyone adopting only one of the "
        f"three should expect roughly a third of the improvement, not all of "
        f"it.", BODY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"<b>And the weakest link is the guard.</b> It fires "
        f"{len(m4['skips'])} time in 189 reviews here, because a 25% ceiling "
        f"is breached so rarely that there is almost nothing to guard. A "
        f"{rupees(abs(m4['xirr_pct'] - rows[11]['xirr_pct']), 2)}-point step "
        f"produced by a single decision is not a demonstrated effect — it is "
        f"one trade that happened to go the right way. The honest evidence "
        f"for the guard is M5, where it fires {len(rows[15]['skips'])} times "
        f"for a smaller and more trustworthy "
        f"{rows[15]['xirr_pct'] - rows[16]['xirr_pct']:+.2f} points against "
        f"its own control.", BODY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"M4 also pays far less tax than S10 — {rupees(m4['ltcg_paid'])} "
        f"against {rupees(s10['ltcg_paid'])} — which is why its after-tax "
        f"edge ({total_aft:+.2f}) is wider than its pre-tax edge "
        f"({total_pre:+.2f}). Selling once instead of three times is worth "
        f"more to a taxpayer than to the gross return.", BODY))
    story.append(PageBreak())


def sells_table(story, code, rows):
    r = rows[code]
    tag = "S10" if code == BENCH else f"M{code - 10}"
    story.append(Paragraph(f"{tag} · {short(code, rows)}", H1))
    story.append(Paragraph(
        f"Terminal {rupees(r['terminal_after_cost'])} · XIRR "
        f"{r['xirr_pct']:.2f}% pre-tax, {r['after_tax_xirr_pct']:.2f}% after "
        f"tax · {r['sells']} sales · {len(r['skips'])} trims refused · "
        f"capital gains tax {rupees(r['ltcg_paid'])}", NOTE))

    story.append(Paragraph("Every sale this variant made", H2))
    if not r["sell_log"]:
        story.append(Paragraph(
            "None. The ceiling was never breached by enough to trigger a "
            "trim, so this variant is a pure buy-and-hold with dividends "
            "swept back in.", BODY))
    else:
        body = [["Date", "Stock", "Shares sold", "Fill (Rs)",
                 "Proceeds net of cost (Rs)", "Why"]]
        for x in r["sell_log"]:
            body.append([x["date"], x["symbol"].split(".")[0],
                         rupees(x["quantity"]), f"{x['price']:.2f}",
                         rupees(x["cash_change"], 2), x["note"][:52]])
        story.append(grid(body, [22 * mm, 24 * mm, 22 * mm, 20 * mm,
                                 38 * mm, 44 * mm],
                          align_right=(2, 3, 4)))

    if r["skips"]:
        story.append(Paragraph("Every trim the guard refused", H2))
        story.append(Paragraph(
            "These are breaches the ceiling would have acted on. The guard "
            "held the position instead, on the grounds that the sale was "
            "late.", NOTE))
        body = [["Date", "Stock", "Why it was refused"]]
        for x in r["skips"]:
            body.append([x["date"], x["symbol"].split(".")[0], x["note"][:112]])
        story.append(Spacer(1, 2))
        story.append(grid(body, [22 * mm, 24 * mm, 124 * mm]))
    story.append(PageBreak())


def annual_state(story, books, rows):
    """Year-end wealth for every variant, side by side."""
    story.append(Paragraph("Year-end state, all seven books", H1))
    story.append(Paragraph(
        "Portfolio value at each year end, so the compounding is visible "
        "rather than asserted. Same contributions in every column — Rs 10,000 "
        "a month — so a gap between columns is the strategy, not the saving.",
        NOTE))
    years = sorted({row["year"] for row in books[BENCH].annual})
    head = ["Year", "S10"] + [f"M{c - 10}" for c in MASTERS]
    body = [head]
    by_code = {c: {row["year"]: row for row in books[c].annual}
               for c in [BENCH] + MASTERS}
    for y in years:
        line = [str(y)]
        for c in [BENCH] + MASTERS:
            row = by_code[c].get(y)
            line.append(rupees(row["wealth"]) if row else "—")
        body.append(line)
    final = ["Final"] + [rupees(rows[c]["terminal_after_cost"])
                         for c in [BENCH] + MASTERS]
    body.append(final)
    w = [14 * mm] + [23 * mm] * 7
    t = grid(body, w, align_right=tuple(range(1, 8)))
    t.setStyle(TableStyle([("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                           ("BACKGROUND", (0, -1), (-1, -1), BAND)]))
    story.append(Spacer(1, 3))
    story.append(t)
    story.append(PageBreak())


def verification(story, books, rows):
    story.append(Paragraph("Verification and what this is not", H1))
    story.append(Paragraph("Ledger checks", H2))
    body = [["", "Cash ledger reconciles", "Shares replay from the audit "
             "trail", "Every fill an official open", "Nothing sold under "
             "365 days"]]
    for code in [BENCH] + MASTERS:
        b = books[code]
        cash_ok = abs(b.cash - sum(x["cash_change"] for x in b.logs)) < 1e-4
        qty = defaultdict(float)
        for t in b.logs:
            if t["event"] in ("BUY", "SPLIT", "BONUS", "DEMERGER"):
                qty[t["symbol"]] += t["quantity"]
            elif t["event"] == "SELL":
                qty[t["symbol"]] -= t["quantity"]
        replay_ok = all(abs(qty[s] - b.qty(s)) < 1e-6 for s in b.lots)
        from datetime import date as _d
        fills_ok = all(
            t["price"] == b.data.p[_d.fromisoformat(t["date"])][t["symbol"]]["open"]
            for t in b.logs if t["event"] in ("BUY", "SELL"))
        bought = defaultdict(list)
        age_ok = True
        for t in b.logs:
            when = _d.fromisoformat(t["date"])
            if t["event"] == "BUY":
                bought[t["symbol"]].append(when)
            elif t["event"] == "SELL":
                if (when - min(bought[t["symbol"]])).days <= 365:
                    age_ok = False
        tag = "S10" if code == BENCH else f"M{code - 10}"
        body.append([tag] + ["yes" if ok else "NO" for ok in
                             (cash_ok, replay_ok, fills_ok, age_ok)])
    story.append(grid(body, [16 * mm, 42 * mm, 46 * mm, 42 * mm, 40 * mm]))

    story.append(Paragraph("What this evidence cannot carry", H2))
    for line in [
        "<b>The guard was designed after seeing the trade it prevents.</b> The "
        "trailing-peak rule came from one page of the S10 ledger — SCI sold in "
        "July 2020 at a price below where it had been held, unsold, in "
        "December 2019. Selecting a rule on the same data you then measure it "
        "on is overfitting by construction.",
        "<b>One basket, one path.</b> Ten NSE names over a single historical "
        "run. A different ten, or a different fifteen years, is a different "
        "answer, and nothing here measures that.",
        "<b>M4's headline edge rests on a single decision.</b> It refuses one "
        "trim across 189 reviews. A 0.4-point gap produced by one trade is not "
        "a demonstrated effect. The honest evidence for the guard is the "
        "variant that fires it repeatedly.",
        "<b>The annual calendar is silent.</b> On yearly contributions these "
        "variants make no sales at all, so neither guard ever runs and the "
        "out-of-design test returns no verdict either way.",
        "<b>Costs modelled, slippage not.</b> 12 bps each way and Indian "
        "capital gains on the after-tax column. No impact, no stamp duty, no "
        "dividend TDS beyond the rates stated in the study.",
    ]:
        story.append(Paragraph(line, BODY))
        story.append(Spacer(1, 3))


def main():
    print("running books…")
    books, rows = run_books()
    story = []
    front(story, rows)
    head_to_head_m4(story, rows)
    head_to_head_m6(story, rows)
    for code in [BENCH] + MASTERS:
        sells_table(story, code, rows)
    annual_state(story, books, rows)
    verification(story, books, rows)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    def furniture(canvas, document):
        """Title and page number on every sheet.

        Long sell logs spill across pages, and reportlab repeats only the
        table header — so the continuation sheets opened with the word "Date"
        and nothing else. A reader who prints this needs to know which
        variant's ledger they are holding.
        """
        canvas.saveState()
        w, h = landscape(A4)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(12 * mm, h - 7 * mm,
                          "M1-M6 ledger versus S10  ·  ten-stock NSE core  ·  "
                          "Rs 10,000 monthly  ·  2011 to date")
        canvas.drawRightString(w - 12 * mm, 6 * mm, f"page {document.page}")
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.3)
        canvas.line(12 * mm, h - 9 * mm, w - 12 * mm, h - 9 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUT), pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=14 * mm, bottomMargin=11 * mm,
        title="M1-M6 ledger versus S10",
        author="Ponfolio research")
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    print(f"wrote {OUT}")
    return rows


if __name__ == "__main__":
    main()
