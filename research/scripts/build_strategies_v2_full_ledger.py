"""Full event-level ledger for S1-S10, in the form of the published five.

Matches `Rebalancing_Five_Strategies_Full_Annual_Ledgers_2011_2026.pdf`
section for section, extended from five strategies to ten:

    cover                       result card for all ten, reading guide
    S<n> portfolio maps         weight % and net cash by stock and year
    S<n> <year> review          BUY/SELL/HOLD for every stock, with shares and
                                weights before and after, and net cash
    S<n> <year> why             the recorded reason for every one of those
                                decisions
    S<n> <year> annual balance   opening/closing cash, contributions, retained
                                distributions, and closing quantity, price and
                                weight for every instrument
    S<n> <year> full event ledger  every contribution, buy, sell, dividend,
                                split, bonus, demerger, rights lapse, buyback
                                and debt coupon, with running balances

NOTHING HERE IS INFERRED. Every quantity, price, cash movement and reason is
read from the saved audit ledger (`audit_ledgers.zip`) or the verified price
file, and positions are reconstructed by replaying that ledger event by event —
the same reconstruction the published document describes. Where a figure is not
in the data it is printed as "Unpriced" or "—", never estimated. The reason
column prints the note the engine recorded at the time; no reason is written
here and none is inferred from what the stock did afterwards.

    python research/scripts/build_strategies_v2_full_ledger.py
    python research/scripts/build_strategies_v2_full_ledger.py --schedule monthly

Out: docs/Rebalancing_Ten_Strategies_Full_Annual_Ledgers_2011_2026.pdf
"""
import argparse
import csv
import io
import json
import sys
import zipfile
from collections import defaultdict
from datetime import date
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
sys.path.insert(0, str(ROOT / "research" / "scripts"))
from backtest_five_verified import SYMS as CORE, Data  # noqa: E402

ALL = CORE + ["ITCHOTELS", "SCILAL"]

def tag(code):
    """S1-S10 keep their number; 11 and up are the masters, M1 onward.

    Zip entries stay keyed `S<code>` because that is how the engine writes
    them, but printing "S14" would name a strategy that does not exist.
    """
    return f"S{code}" if code <= 10 else f"M{code - 10}"


SCHEDULES = {
    "annual": dict(
        src=ROOT / "research/data/strategies_v2",
        out=ROOT / "docs/Rebalancing_Ten_Strategies_Full_Annual_Ledgers_2011_2026.pdf",
        kind="Annual Rs 1,00,000 contribution"),
    "monthly": dict(
        src=ROOT / "research/data/strategies_all",
        out=ROOT / "docs/Rebalancing_Ten_Strategies_Full_Monthly_Ledgers_2011_2026.pdf",
        kind="Monthly Rs 10,000 contribution"),
}

INK = colors.HexColor("#11161D")
BLUE = colors.HexColor("#1F4F8F")
GRAY = colors.HexColor("#5B6775")
LIGHT = colors.HexColor("#F4F6F9")
LINE = colors.HexColor("#D7DDE5")
BUYC = colors.HexColor("#1F4F8F")
SELLC = colors.HexColor("#B4432C")
BOTHC = colors.HexColor("#7A3E9D")
HOLDC = colors.HexColor("#5B6775")
EVENTC = colors.HexColor("#0B7A51")
PAGE = landscape(A4)
# Chosen so a year's event table never splits across a page break: a
# continuation page carries the repeated header but no title, which
# looks like a missing section rather than a long one.
ROWS_PER_EVENT_PAGE = 18

TRADE = {"BUY", "SELL"}
ACTION_EVENTS = {"SPLIT", "BONUS", "DEMERGER"}


def money(v, dec=2):
    """Indian digit grouping, as the published ledger prints it."""
    whole, _, frac = f"{abs(float(v)):.{dec}f}".partition(".")
    tail, head, parts = whole[-3:], whole[:-3], []
    while head:
        parts.insert(0, head[-2:])
        head = head[:-2]
    out = ",".join(parts + [tail])
    return ("-" if float(v) < 0 else "") + out + (f".{frac}" if frac else "")


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
        mk("title", "LVB", 16, 20, 5, BLUE),
        mk("sub", "LV", 8.2, 11.5, 8, INK),
        mk("body", "LV", 7.6, 10.6, 5, INK),
        mk("small", "LV", 6.8, 9.4, 4, GRAY),
        mk("big", "LVB", 15, 19, 0, BLUE),
        mk("biglab", "LV", 7.2, 10, 0, GRAY),
        mk("cell", "LV", 6.6, 8.8, 0, INK),
        mk("cellb", "LVB", 6.6, 8.8, 0, INK),
        mk("head", "LVB", 6.6, 8.8, 0, colors.white),
    ])


def tint(hexcode, f):
    c = colors.HexColor(hexcode)
    f = max(0.0, min(1.0, f))
    return colors.Color(1 - (1 - c.red) * f, 1 - (1 - c.green) * f,
                        1 - (1 - c.blue) * f)


def weight_shade(pct):
    """Orange above the 10% core target, blue below — the published key."""
    return (tint("#E0952F", (pct - 10) / 15) if pct > 10
            else tint("#6FA8D0", (10 - pct) / 12))


def action_colour(a):
    return {"BUY": BUYC, "SELL": SELLC, "BUY+SELL": BOTHC}.get(a, HOLDC)


def hexs(c):
    """'#rrggbb' — reportlab's inline <font color> needs the hash."""
    return "#" + c.hexval()[2:]


def grid(head, rows, widths, st, cell_styles=(), align_right=()):
    data = [[Paragraph(str(c), st["head"]) for c in head]]
    for r in rows:
        data.append([Paragraph(str(c), st["cell"]) for c in r])
    # Widths are given in MILLIMETRES throughout — passing them as raw points
    # made every table a third of its intended width, which wrapped "Stock"
    # onto two lines and pushed each review onto a second page.
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1,
              hAlign="LEFT")
    s = [("BACKGROUND", (0, 0), (-1, 0), INK),
         ("GRID", (0, 0), (-1, -1), 0.35, LINE),
         ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
         ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
         ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
         ("TOPPADDING", (0, 0), (-1, -1), 2.4),
         ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4)]
    for i in range(1, len(data)):
        if i % 2 == 0:
            s.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    s.extend(cell_styles)
    t.setStyle(TableStyle(s))
    return t


# ── reconstruction from the audit ledger ────────────────────────────────────
def replay(rows):
    """Walk the ledger and attach running state to every entry.

    This is the "independently reconstructed from the event ledger" step the
    published document describes: quantities and balances are rebuilt from the
    recorded events rather than taken from the engine's own final state, so a
    disagreement between the two would show up rather than be hidden.
    """
    qty = defaultdict(float)
    cash = retained = 0.0
    out = []
    for i, r in enumerate(rows, 1):
        e = r["event"]
        q = float(r["quantity"] or 0)
        cash += float(r["cash_change"] or 0)
        retained += float(r["earned_change"] or 0)
        if e == "BUY":
            qty[r["symbol"]] += q
        elif e == "SELL":
            qty[r["symbol"]] -= q
        elif e in ACTION_EVENTS:
            qty[r["symbol"]] += q
        out.append(dict(r, idx=i, cash_balance=cash, retained_balance=retained,
                        qty_after=dict(qty)))
    return out


def review_dates(entries):
    """The dates a contribution was booked — the strategy's decision points."""
    seen = []
    for e in entries:
        if e["event"] == "CONTRIBUTION" and e["date"] not in seen:
            seen.append(e["date"])
    return seen


def year_of(d):
    return int(d[:4])


def prev_session(data, d):
    """The trading day before `d`, for the decision-reference close."""
    import bisect
    i = bisect.bisect_left(data.days, date.fromisoformat(d))
    return data.days[i - 1] if i > 0 else None


# ── page builders ───────────────────────────────────────────────────────────
def review_page(code, name, d, entries, data, st, contrib_label):
    """BUY / SELL / HOLD for every stock at one review."""
    same_day = [e for e in entries if e["date"] == d]
    first = same_day[0]
    before = {s: (first["qty_after"].get(s, 0.0)
                  - (float(first["quantity"] or 0)
                     if first["symbol"] == s and first["event"] == "BUY" else 0.0))
              for s in ALL}
    # Position immediately BEFORE the first event of the day, rebuilt from the
    # entry that precedes it in the ledger.
    idx = entries.index(first)
    prior = entries[idx - 1]["qty_after"] if idx else {}
    before = {s: prior.get(s, 0.0) for s in ALL}
    after = {s: same_day[-1]["qty_after"].get(s, 0.0) for s in ALL}

    cash_before = entries[idx - 1]["cash_balance"] if idx else 0.0
    cash_after = same_day[-1]["cash_balance"]

    prev = prev_session(data, d)
    ref = ({s: data.p[prev][s]["close"] for s in CORE} if prev
           else {s: data.p[date.fromisoformat(d)][s]["open"] for s in CORE})
    fills = {}
    bought, sold, netcash = defaultdict(float), defaultdict(float), defaultdict(float)
    for e in same_day:
        if e["event"] in TRADE:
            fills[e["symbol"]] = float(e["price"])
            netcash[e["symbol"]] += float(e["cash_change"])
            (bought if e["event"] == "BUY" else sold)[e["symbol"]] += float(e["quantity"])

    day_close = data.p[date.fromisoformat(d)]
    val_before = sum(before.get(s, 0) * ref.get(s, 0) for s in CORE)
    val_after = sum(after.get(s, 0) * day_close[s]["close"] for s in CORE)

    rows, shades = [], []
    for i, s in enumerate(CORE, 1):
        b, a = before.get(s, 0.0), after.get(s, 0.0)
        wb = (b * ref[s] / val_before * 100) if val_before else 0.0
        wa = (a * day_close[s]["close"] / val_after * 100) if val_after else 0.0
        act = ("BUY+SELL" if bought[s] and sold[s] else
               "BUY" if bought[s] else "SELL" if sold[s] else "HOLD")
        rows.append([s, f"{b:,.0f}",
                     money(fills[s]) if s in fills else "—",
                     money(b * ref[s]), f"{wb:.2f}%",
                     f'<font color="{hexs(action_colour(act))}"><b>{act}</b></font>',
                     f"{bought[s]:,.0f}", f"{sold[s]:,.0f}",
                     f"{(sold[s] / b * 100) if b else 0:.2f}%",
                     f"{a:,.0f}", f"{wa:.2f}%", money(netcash[s])])
        shades += [("BACKGROUND", (4, i), (4, i), weight_shade(wb)),
                   ("BACKGROUND", (10, i), (10, i), weight_shade(wa))]

    out = [Paragraph(f"{tag(code)} | {year_of(d)} | BUY / SELL / HOLD review",
                     st["title"]),
           Paragraph(f"Review {d} | Signal reference "
                     f"{prev.isoformat() if prev else d} | {contrib_label} | "
                     f"Ten-stock core", st["sub"])]
    band = Table([[Paragraph("Cash before contribution", st["biglab"]),
                   Paragraph("Cash after review", st["biglab"]),
                   Paragraph("Review closing core value", st["biglab"])],
                  [Paragraph(f"Rs {money(cash_before)}", st["big"]),
                   Paragraph(f"Rs {money(cash_after)}", st["big"]),
                   Paragraph(f"Rs {money(val_after)}", st["big"])]],
                 colWidths=[90 * mm, 90 * mm, 89 * mm])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                              ("TOPPADDING", (0, 0), (-1, -1), 5),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                              ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    out += [band, Spacer(1, 5)]
    out.append(grid(
        ["Stock", "Held before", "Fill (Rs)", "Value before (Rs)", "W% before",
         "Action", "Bought", "Sold", "Sold % of held", "Held after", "W% after",
         "Net cash +/-"], rows,
        [24, 18, 20, 26, 17, 20, 15, 14, 19, 17, 16, 23],
        st, shades))
    out.append(Paragraph(
        "Held = whole shares. Value before uses the previous session's close; "
        "fill is the official review-day open recorded in the ledger. W% after "
        "uses review-day closes. Core weights exclude cash, distributions and "
        "demerged stocks. Net cash is positive for net sale receipts and "
        "negative for net purchases; trading costs are included. Sold % is "
        "shares sold divided by the opening position, not a change in "
        "portfolio weight.", st["small"]))
    out.append(grid(["Review totals", "Bought (Rs incl. costs)",
                     "Sold (Rs net of costs)", "Core W% after"],
                    [["All ten stocks",
                      money(sum(-netcash[s] for s in CORE if netcash[s] < 0)),
                      money(sum(netcash[s] for s in CORE if netcash[s] > 0)),
                      "100.00%" if val_after else "0.00%"]],
                    [95, 55, 55, 44], st))
    return out


def why_page(code, d, entries, st):
    """The recorded reason for each decision. Notes only — nothing inferred."""
    same_day = [e for e in entries if e["date"] == d]
    reasons = defaultdict(list)
    acts = {}
    for e in same_day:
        if e["event"] in TRADE:
            note = (e["note"] or "").strip()
            if note and note not in reasons[e["symbol"]]:
                reasons[e["symbol"]].append(note)
            acts[e["symbol"]] = ("BUY+SELL" if acts.get(e["symbol"]) not in
                                 (None, e["event"]) else e["event"])
    rows = []
    for s in CORE:
        act = acts.get(s, "HOLD")
        why = "; ".join(reasons[s]) if reasons[s] else (
            "No trade recorded for this stock at this review.")
        rows.append([s, f'<font color="{hexs(action_colour(act))}">'
                        f"<b>{act}</b></font>", why])
    return [Paragraph(f"{tag(code)} | {year_of(d)} | Why every stock was bought, "
                      f"sold or held", st["title"]),
            Paragraph("Each reason is the note the engine recorded when it "
                      "placed the order. No reason is written here, and none "
                      "is inferred from what the stock did afterwards.",
                      st["sub"]),
            grid(["Stock", "Action", "Recorded reason"], rows,
                 [26, 22, 181], st)]


def balance_page(code, name, year, entries, data, st):
    """Opening/closing balances and closing positions for one calendar year."""
    in_year = [e for e in entries if year_of(e["date"]) == year]
    if not in_year:
        return []
    before = entries[entries.index(in_year[0]) - 1] if entries.index(in_year[0]) else None
    open_qty = before["qty_after"] if before else {}
    close_qty = in_year[-1]["qty_after"]
    open_cash = before["cash_balance"] if before else 0.0
    open_ret = before["retained_balance"] if before else 0.0
    close_cash = in_year[-1]["cash_balance"]
    close_ret = in_year[-1]["retained_balance"]
    contributed = sum(float(e["cash_change"]) for e in in_year
                      if e["event"] == "CONTRIBUTION")
    open_contrib = sum(float(e["cash_change"]) for e in entries
                       if e["event"] == "CONTRIBUTION"
                       and year_of(e["date"]) < year)

    last_day = max(d for d in data.days if d.year == year)
    closes = data.p[last_day]
    bought = defaultdict(float)
    sold = defaultdict(float)
    adds = defaultdict(float)
    for e in in_year:
        q = float(e["quantity"] or 0)
        if e["event"] == "BUY":
            bought[e["symbol"]] += q
        elif e["event"] == "SELL":
            sold[e["symbol"]] += q
        elif e["event"] in ACTION_EVENTS:
            adds[e["symbol"]] += q

    core_value = sum(close_qty.get(s, 0) * closes[s]["close"] for s in CORE)
    priced_value = core_value
    rows, shades = [], []
    for i, s in enumerate(ALL, 1):
        q = close_qty.get(s, 0.0)
        px = closes[s]["close"] if s in closes else None
        val = q * px if px is not None else 0.0
        if s not in CORE and px is not None:
            priced_value += val
        w = (q * px / core_value * 100) if (px is not None and core_value
                                            and s in CORE) else None
        rows.append([s, f"{open_qty.get(s, 0.0):,.2f}", f"{bought[s]:,.2f}",
                     f"{sold[s]:,.2f}", f"{adds[s]:,.2f}", f"{q:,.2f}",
                     money(px) if px is not None else "Unpriced",
                     money(val) if px is not None else "0.00",
                     f"{w:.2f}%" if w is not None else "-"])
        if w is not None:
            shades.append(("BACKGROUND", (8, i), (8, i), weight_shade(w)))

    bal = grid(["Balance", "Opening", "Change during year", "Closing"],
               [["Cumulative external contributions", money(open_contrib),
                 money(contributed), money(open_contrib + contributed)],
                ["Trading cash", money(open_cash),
                 money(close_cash - open_cash), money(close_cash)],
                ["Declared/scheduled distributions retained", money(open_ret),
                 money(close_ret - open_ret), money(close_ret)]],
               [110, 45, 50, 46], st)
    label = name.split(" ", 1)[1] if name.startswith(f"{tag(code)} ") else name
    return [Paragraph(f"{tag(code)} | {label} | {year} annual balance",
                      st["title"]),
            Paragraph(f"Closing observation: {last_day} | Calendar year, not "
                      f"financial year | {len(in_year)} ledger entries | INR",
                      st["sub"]),
            bal, Spacer(1, 5),
            grid(["Stock", "Opening qty", "Bought", "Sold", "Action adds",
                  "Closing qty", "Last close (Rs)", "Value (Rs)", "Core W%"],
                 rows, [26, 22, 20, 20, 22, 22, 25, 28, 24], st, shades),
            Paragraph(
                f"<b>Priced equity:</b> {money(priced_value)} | "
                f"<b>Trading cash:</b> {money(close_cash)} | "
                f"<b>Retained distributions:</b> {money(close_ret)} | "
                f"<b>Known wealth:</b> "
                f"{money(priced_value + close_cash + close_ret)}", st["body"]),
            Paragraph("Core W% uses the ten core stocks only. Cash and "
                      "distributions are excluded from it. An instrument with "
                      "no close on the final session of the year is shown as "
                      "Unpriced and contributes nothing to value — it is never "
                      "given an estimated price.", st["small"])]


def event_pages(code, year, entries, notes, st):
    """Every ledger entry for one calendar year, paginated."""
    in_year = [e for e in entries if year_of(e["date"]) == year]
    if not in_year:
        return []
    chunks = [in_year[i:i + ROWS_PER_EVENT_PAGE]
              for i in range(0, len(in_year), ROWS_PER_EVENT_PAGE)]
    out = []
    for n, chunk in enumerate(chunks, 1):
        rows = []
        for e in chunk:
            ev = e["event"]
            colour = (action_colour(ev) if ev in TRADE
                      else EVENTC if ev != "CONTRIBUTION" else INK)
            rows.append([
                f"{tag(code)}-{e['idx']:04d}", e["date"], e["symbol"],
                f'<font color="{hexs(colour)}"><b>{ev}</b></font>',
                f"{float(e['quantity'] or 0):,.2f}",
                money(e["price"] or 0), money(e["cash_change"] or 0),
                money(e["cash_balance"]), money(e["earned_change"] or 0),
                money(e["retained_balance"]), notes[(e["note"] or "").strip()]])
        out += [Paragraph(f"{tag(code)} | {year} | Full event ledger "
                          f"{n}/{len(chunks)}", st["title"]),
                Paragraph("INR. Cash = trading cash; retained = distributions "
                          "not reinvested. Rights and buyback quantities are "
                          "informational, not share additions. Notes: see the "
                          "N-code appendix.", st["sub"]),
                grid(["Entry ID", "Date", "Symbol", "Event", "Qty",
                      "Ref price", "Cash +/-", "Cash balance", "Retained +/-",
                      "Retained balance", "Note"], rows,
                     [22, 20, 24, 30, 17, 20, 23, 25, 20, 25, 13], st),
                PageBreak()]
    return out[:-1]


def maps_page(code, entries, data, st):
    """Weight and net-cash matrices for every stock and year."""
    years = sorted({year_of(e["date"]) for e in entries})
    wmap, cmap = {}, {}
    for y in years:
        in_year = [e for e in entries if year_of(e["date"]) == y]
        close_qty = in_year[-1]["qty_after"]
        last_day = max(d for d in data.days if d.year == y)
        closes = data.p[last_day]
        tot = sum(close_qty.get(s, 0) * closes[s]["close"] for s in CORE)
        for s in CORE:
            wmap[(s, y)] = (close_qty.get(s, 0) * closes[s]["close"] / tot * 100
                            if tot else 0.0)
            cmap[(s, y)] = -sum(float(e["cash_change"]) for e in in_year
                                if e["symbol"] == s and e["event"] in TRADE)
    wrows, wsh, crows, csh = [], [], [], []
    for i, s in enumerate(CORE, 1):
        wrows.append([s] + [f"{wmap[(s, y)]:.1f}" for y in years])
        crows.append([s] + [f"{cmap[(s, y)] / 1000:.1f}" for y in years])
        for j, y in enumerate(years, 1):
            wsh.append(("BACKGROUND", (j, i), (j, i), weight_shade(wmap[(s, y)])))
            v = cmap[(s, y)]
            csh.append(("BACKGROUND", (j, i), (j, i),
                        tint("#0B7A51", min(1, abs(v) / 150000)) if v >= 0
                        else tint("#B4432C", min(1, abs(v) / 150000))))
    w = [24] + [(231 - 24) / len(years)] * len(years)
    return [Paragraph(f"{tag(code)} | Portfolio maps | {years[0]}-{years[-1]}",
                      st["title"]),
            Paragraph("Map 1 — percentage of the ten-stock core at each "
                      "calendar year end. Orange = above 10%; blue = below "
                      "10%. Each year totals 100% before display rounding.",
                      st["sub"]),
            grid(["Stock"] + [str(y) for y in years], wrows, w, st, wsh),
            Spacer(1, 6),
            Paragraph("Map 2 — net cash invested in each stock that year, Rs "
                      "thousands. Positive green = purchases exceed sale "
                      "receipts; negative red = sale receipts exceed "
                      "purchases. Gross buys and sells remain visible in the "
                      "review tables and the event ledger.", st["sub"]),
            grid(["Stock"] + [str(y) for y in years], crows, w, st, csh)]


def build(cfg):
    data = json.loads((cfg["src"] / "results.json").read_text(encoding="utf-8"))
    pre = {x["code"]: x for x in data["results"]}
    post = {x["code"]: x for x in data["after_tax"]}
    # Whatever the dataset holds — ten strategies alone, or ten beside the six
    # masters. Hardcoding the range silently dropped anything past S10.
    codes = [x["code"] for x in data["results"]]
    prices = Data()
    st = styles()
    ledgers = {}
    with zipfile.ZipFile(cfg["src"] / "audit_ledgers.zip") as z:
        for c in codes:
            raw = z.read(f"S{c}_transactions_and_events.csv").decode("utf-8-sig")
            ledgers[c] = replay(list(csv.DictReader(io.StringIO(raw))))

    # N-codes: one per distinct recorded note, so the event table stays narrow
    # and every note is reproduced verbatim in the appendix.
    seen = []
    for c in codes:
        for e in ledgers[c]:
            n = (e["note"] or "").strip()
            if n not in seen:
                seen.append(n)
    notes = {n: f"N{i:02d}" for i, n in enumerate(seen, 1)}

    contrib_label = cfg["kind"]
    # Counted, not stated. Both numbers were hardcoded for ten strategies and
    # went stale the moment the six masters joined the document.
    words = {5: "Five", 10: "Ten", 11: "Eleven", 16: "Sixteen"}
    chapters = words.get(len(codes), str(len(codes)))
    years_covered = len({year_of(e["date"]) for e in ledgers[codes[0]]})
    story = [Paragraph(f"{chapters} strategy chapters | Decisions and full "
                       f"ledgers", st["title"]),
             Paragraph(f"{data['start']} to {data['end']} | "
                       f"{len(codes) * years_covered} "
                       f"strategy-year sections | {contrib_label} | INR",
                       st["sub"]),
             Paragraph("Every saved contribution, purchase, sale and "
                       "corporate-action entry is included. Calendar-year "
                       "closing balances and stock quantities are "
                       "independently reconstructed by replaying the event "
                       "ledger, not copied from the engine's final state.",
                       st["body"])]
    srows = []
    for c in codes:
        srows.append([pre[c]["name"], money(pre[c]["invested"]),
                      money(pre[c]["terminal_after_cost"]),
                      f"{pre[c]['xirr_pct']:.2f}%",
                      f"{post[c]['xirr_pct']:.2f}%",
                      str(pre[c]["trades"] - pre[c]["sells"]),
                      str(pre[c]["sells"])])
    story.append(grid(["Strategy", "Contributed (Rs)",
                       "Final modeled wealth (Rs)", "Model XIRR",
                       "After-tax XIRR", "Buys", "Sells"], srows,
                      [66, 32, 40, 24, 26, 20, 23], st))
    for text in [
        "<b>Reading each chapter:</b> portfolio maps; then, for every year, "
        "the BUY / SELL / HOLD decision for all ten stocks with shares and "
        "weights before and after; the recorded reason for each; the annual "
        "balance; and the complete dated event ledger. N-codes in the event "
        "tables refer to the note appendix at the end.",
        "<b>Colours:</b> blue = BUY; red = SELL; purple = both occurred at "
        "the same review; grey = HOLD. Weight cells shade orange above the "
        "10% core target and blue below it. A colour describes the recorded "
        "action, not a recommendation.",
        "<b>Nothing is inferred.</b> Quantities, prices, cash movements and "
        "reasons are read from the saved audit ledger and the verified price "
        "file. An instrument with no close on a given session prints as "
        "Unpriced and is never assigned an estimated price. Reason cells "
        "reproduce the note the engine recorded at order time.",
        "<b>Model basis:</b> pre-tax unless a column says otherwise; rights "
        "lapse; buybacks are not tendered; fractional proceeds are excluded. "
        "Dividend dates are eligibility/recognition dates, not verified "
        "payment dates. This is a model ledger, not a broker statement.",
    ]:
        story.append(Paragraph(text, st["body"]))
    story.append(PageBreak())

    for c in codes:
        entries = ledgers[c]
        years = sorted({year_of(e["date"]) for e in entries})
        story += maps_page(c, entries, prices, st) + [PageBreak()]
        for d in review_dates(entries):
            story += review_page(c, pre[c]["name"], d, entries, prices, st,
                                 contrib_label) + [PageBreak()]
            story += why_page(c, d, entries, st) + [PageBreak()]
        for y in years:
            story += balance_page(c, pre[c]["name"], y, entries, prices, st)
            story.append(PageBreak())
            story += event_pages(c, y, entries, notes, st)
            story.append(PageBreak())

    story.append(Paragraph("Note appendix", st["title"]))
    story.append(Paragraph("Every N-code used in the event tables, with the "
                           "note exactly as the engine recorded it.", st["sub"]))
    story.append(grid(["Code", "Recorded note"],
                      [[v, k or "(no note recorded)"] for k, v in notes.items()],
                      [16, 213], st))

    def furniture(canvas, doc):
        canvas.saveState()
        canvas.setFont("LV", 6.6)
        canvas.setFillColor(GRAY)
        canvas.drawString(14 * mm, 9 * mm,
                          f"Full ledger | Pre-tax entitlement model | "
                          f"{cfg['kind']} | {data['start']} to {data['end']}")
        canvas.drawRightString(PAGE[0] - 14 * mm, 9 * mm, f"{doc.page}")
        canvas.restoreState()

    cfg["out"].parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(cfg["out"]), pagesize=PAGE,
                            title="Rebalancing — Ten Strategies Full Ledgers",
                            author="Ponfolio",
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=13 * mm)
    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    print(f"wrote {cfg['out'].name}  "
          f"({cfg['out'].stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schedule", choices=list(SCHEDULES), default="annual")
    a = ap.parse_args()
    fonts()
    build(SCHEDULES[a.schedule])
