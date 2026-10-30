"""Render research/data/smart_sip/rules.json as a PNG table.

Cells are tinted by their gap to the Fixed SIP in the same column, so the
"beats fixed in every period" rows read at a glance.

    python research/scripts/render_smart_sip_rules_png.py

Needs Pillow. Out: docs/reports/smart-sip/smart_sip_rules_table.png
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "data", "smart_sip", "rules.json")
OUT = os.path.join(os.path.dirname(ROOT), "docs", "reports", "smart-sip", "smart_sip_rules_table.png")
FONTS = "C:/Windows/Fonts/"

GROUPS = {"A": "A  Base", "B": "B  Fixed SIP + extra money when cheap",
          "C": "C  Monthly amount moves with P/E",
          "D": "D  Same Rs 10k budget, skipped money waits in 6% liquid fund",
          "E": "E  Other"}
YEARS = ["1996", "2000", "2008", "2017"]

BG, INK, MUTED, RULE = "#ffffff", "#1d2430", "#6b7280", "#e5e7eb"
HEAD_BG, GROUP_BG, FIXED_BG = "#f3f4f6", "#f9fafb", "#fff7e0"
UP, UP_STRONG, DOWN = "#e3f4e8", "#bfe6cb", "#fbe3e1"


def font(name, size):
    return ImageFont.truetype(FONTS + name, size)


def money(lakh):
    return f"Rs {lakh / 100:.2f} Cr" if lakh >= 100 else f"Rs {lakh:.1f} L"


def main():
    res = json.load(open(RES))
    rules = res["rules"]
    fixed = rules["1 Fixed SIP"]

    f_title, f_sub = font("segoeuib.ttf", 34), font("segoeui.ttf", 20)
    f_head, f_cell = font("segoeuib.ttf", 19), font("segoeui.ttf", 19)
    f_bold, f_group = font("segoeuib.ttf", 19), font("segoeuib.ttf", 18)
    f_note = font("segoeui.ttf", 16)

    cols = [("Rule", 470, "l")] + [(f"From {y}", 130, "r") for y in YEARS] + [("1996: put in -> value today", 330, "r")]
    pad, row_h, x0 = 40, 40, 40
    width = x0 * 2 + sum(w for _, w, _ in cols)
    n_rows = len(rules) + len(GROUPS)
    height = 150 + row_h * (n_rows + 1) + 190
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)

    d.text((x0, 30), "Nifty 50 SIP: 21 rules, price-only XIRR", font=f_title, fill=INK)
    d.text((x0, 78), f"Rs 10,000 a month base, official NSE data to {res['data_through']}. "
           "Decide on yesterday's close, buy at today's close. No dividends.", font=f_sub, fill=MUTED)

    y = 130
    d.rectangle((x0, y, width - x0, y + row_h), fill=HEAD_BG)
    x = x0
    for name, w, al in cols:
        tw = d.textlength(name, font=f_head)
        d.text((x + 12 if al == "l" else x + w - tw - 12, y + 9), name, font=f_head, fill=INK)
        x += w
    y += row_h

    current = None
    for label, by in rules.items():
        if by["group"] != current:
            current = by["group"]
            d.rectangle((x0, y, width - x0, y + row_h), fill=GROUP_BG)
            d.text((x0 + 12, y + 10), GROUPS[current], font=f_group, fill=MUTED)
            d.line((x0, y + row_h, width - x0, y + row_h), fill=RULE)
            y += row_h
        is_fixed = label == "1 Fixed SIP"
        if is_fixed:
            d.rectangle((x0, y, width - x0, y + row_h), fill=FIXED_BG)
        num, _, name = label.partition(" ")
        d.text((x0 + 12, y + 9), f"{num:>2}", font=f_cell, fill=MUTED)
        d.text((x0 + 52, y + 9), name, font=f_bold if is_fixed else f_cell, fill=INK)
        x = x0 + cols[0][1]
        for yr in YEARS:
            v = by[yr]["xirr_pct"]
            gap = v - fixed[yr]["xirr_pct"]
            if not is_fixed:
                tint = UP_STRONG if gap >= 0.3 else UP if gap >= 0.1 else DOWN if gap <= -0.1 else None
                if tint:
                    d.rectangle((x + 4, y + 4, x + 130 - 4, y + row_h - 4), fill=tint)
            txt = f"{v:.2f}%"
            fnt = f_bold if v >= 12 or is_fixed else f_cell
            tw = d.textlength(txt, font=fnt)
            d.text((x + 130 - tw - 12, y + 9), txt, font=fnt, fill=INK)
            x += 130
        r96 = by["1996"]
        txt = f"{money(r96['paid_lakh'])}  ->  {money(r96['value_lakh'])}"
        tw = d.textlength(txt, font=f_cell)
        d.text((x + 330 - tw - 12, y + 9), txt, font=f_cell, fill=INK)
        d.line((x0, y + row_h, width - x0, y + row_h), fill=RULE)
        y += row_h

    y += 22
    for i, (tint, text) in enumerate([(UP_STRONG, "beats Fixed SIP by 0.3+ pts"),
                                      (UP, "beats by 0.1-0.3 pts"),
                                      (DOWN, "trails by 0.1+ pts")]):
        lx = x0 + i * 300
        d.rectangle((lx, y + 2, lx + 22, y + 22), fill=tint, outline=RULE)
        d.text((lx + 32, y), text, font=f_note, fill=INK)
    d.text((x0 + 900, y), "Bold = 12% or more", font=f_note, fill=INK)
    notes = [
        "Group B and step-ups put in more money, so compare their XIRR, not the corpus.",
        "Rule 20 invests only Rs 22 L of Rs 37 L. Same budget: 11.53 / 11.55 / 9.87 / 8.86% (30k cap), 11.69 / 11.91 / 9.88 / 8.88% (no cap).",
        "Rules 15 and 18 look strong since 2017 only because they held cash into the March 2020 crash; ended Dec 2019, both gave 5.7% vs 9.9% fixed.",
        "Independently re-computed (verify_smart_sip_rules.py): all 84 results match within 0.005 pts. Past data, not a forecast or advice.",
    ]
    for k, note in enumerate(notes):
        d.text((x0, y + 40 + k * 28), note, font=f_note, fill=MUTED)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    print(f"wrote {OUT} ({width}x{height})")


if __name__ == "__main__":
    main()
