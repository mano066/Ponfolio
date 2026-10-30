---
name: research-report
description: Use when running a backtest or market study (SIP rules, index comparisons, strategy tests, fund or stock analysis) in this repository, or when producing its report, tables, charts, PDF or CSV for the owner.
---

# Research report

## Data

- Prices and valuations from official sources: NSE `historicalOR/indicesHistory`
  (prices, 70 rows per request, so fetch monthly chunks) and
  `historicalOR/indicesYield` (P/E, P/B, dividend yield from Nov 2015).
  Earlier Nifty 50 P/E: the Kaggle "NIFTY 50 Historical PE, PB, DIV Yield" file,
  which matches NSE exactly on every overlapping day.
- Raw downloads stay out of git (see `.gitignore`); commit the download script
  and small derived results.
- Never use the owner's holdings as a study universe for anything that will be
  committed (see `privacy-guard`).

## Method

- Decide on yesterday's close, trade at today's close: no look-ahead.
- Compare strategies on the **same money**. A rule that skips months must park
  the skipped cash (state the rate, e.g. 6% liquid fund) and count it at the end;
  XIRR on deployed money only is reported separately and labelled as such.
- Price-only unless the owner asks for total return; say which.
- Report XIRR from dated cash flows, money put in, final value, and how many
  months each rule acted.
- Test robustness before claiming an edge: several start years and end dates,
  and neighbouring thresholds. A result that flips on a 1-point change is luck.

## Verification (required before reporting)

- An independent re-computation that shares no code with the backtest
  (see `research/scripts/verify_smart_sip_rules.py`) and agrees within rounding.
- Spot-check known index levels and data gaps.
- Any number shown in two places (card, chart, table) must come from one source.

## Deliverables

What the owner reads, in this order of preference:
1. **PDF**, A4 landscape, reportlab, Arial: summary page with the answer first,
   contents with bookmarks, one section per strategy, each opening with key
   figures and a value-vs-money chart, then month-wise tables grouped by year
   with a year summary band. Running header with the section name.
2. **One CSV per table**, `utf-8-sig`, plain-English headers with units.
- Indian digit grouping (₹3,04,55,016), ₹ L / ₹ Cr in summaries.
- Simple English, ₹ examples, short sentences.
- Render every PDF page to an image and look at it before saying it is done.

Template: `research/scripts/build_value_averaging_report.py`.
Output folder: `docs/reports/<study>/`.
