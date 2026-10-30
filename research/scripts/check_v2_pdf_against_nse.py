"""Audit the existing V2 PDF against saved official NSE observations.

No strategy rerun, assumed cash payments, or replacement of the original PDF.
"""
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/pdf_audit_deps'))
import pymupdf
from verify_v2_exchange_data import write_csv


def csv_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


def indian(value):
    digits=str(round(value))
    tail=digits[-3:]
    head=digits[:-3]
    parts=[]
    while head:
        parts.insert(0,head[-2:])
        head=head[:-2]
    return ','.join(parts+[tail])


def main():
    pdf=ROOT/'docs/Rebalancing_Strategy_Backtest_V2_2011_2026.pdf'
    data=ROOT/'research/data'
    official_dir=data/'v2_source_verification/verified'
    out=official_dir/'pdf_comparison'
    out.mkdir(exist_ok=True)
    run=json.loads((data/'v2_main.json').read_text())
    doc=pymupdf.open(pdf)
    pages=[p.get_text() for p in doc]
    nse={(r['symbol'],r['date']):r for r in csv_rows(official_dir/'official_daily_prices.csv')}
    old_factors={(r['symbol'],r['date']):float(r['future_share_factor']) for r in csv_rows(data/'rebalance_audit_2010_2026/daily_prices_clean.csv')}
    results=run['results']
    rows=[]
    page_start={}
    for result in results:
        hits=[i for i,text in enumerate(pages) if result['strategy']+' — year by year' in text]
        if len(hits)!=1:
            raise ValueError('Cannot uniquely locate PDF strategy ledger')
        page_start[result['strategy']]=hits[0]
    for result in results:
        start=page_start[result['strategy']]
        stop=min([p for p in page_start.values() if p>start]+[len(pages)])
        for entry in result['ledger']:
            marker=f'Year {entry["year"]} of {result["contributions"]}'
            matches=[(i,pages[i]) for i in range(start,stop) if marker in pages[i]]
            if len(matches)!=1:
                raise ValueError(f'Cannot uniquely locate ledger year: {result["strategy"]}/{marker}')
            page_index,text=matches[0]
            section=text.split(marker,1)[1]
            section=re.split(r'Year \d+ of \d+',section,maxsplit=1)[0]
            if entry['date'] not in section:
                raise ValueError('PDF/JSON ledger date mismatch')
            for row in entry['rows']:
                price_match=re.search(r'\n'+re.escape(row['symbol'])+r'\n[^\n]+\n([^\n]+)\n',section)
                if not price_match:
                    raise ValueError(f'Cannot read printed price: page {page_index+1}/{row["symbol"]}')
                printed=float(price_match[1].replace(',',''))
                if abs(printed-row['price'])>.005:
                    raise ValueError('PDF and supporting JSON disagree')
                official=nse[row['symbol'],entry['date']]
                raw=float(official['close'])
                factor=old_factors[row['symbol'],entry['date']]
                split_only=raw/factor
                rows.append(dict(strategy=result['strategy'],pdf_page=page_index+1,year=entry['year'],
                                 date=entry['date'],symbol=row['symbol'],pdf_price=printed,nse_raw_close=raw,
                                 future_split_bonus_factor=factor,nse_split_bonus_only_price=round(split_only,6),
                                 pdf_vs_split_only_pct=round((printed/split_only-1)*100,6),
                                 raw_price_matches_within_5_paise=abs(printed-raw)<=.05,
                                 split_only_matches_within_5_paise=abs(printed-split_only)<=.05,
                                 pdf_units_bought_minus_sold=row['units'],
                                 pdf_qty_after=row['qty_after'],nse_series=official['series'],nse_source_file=official['source_file']))
    write_csv(out/'all_800_pdf_price_rows.csv',rows)
    starts=[r for r in rows if r['year']==1 and r['strategy']==results[0]['strategy']]
    write_csv(out/'first_purchase_prices.csv',starts)
    end_checks=[]
    for symbol in run['basket']:
        old_end=results[0]['end_prices'][symbol]
        same=float(nse[symbol,run['end']]['close'])
        latest_day=max(day for s,day in nse if s==symbol)
        latest=float(nse[symbol,latest_day]['close'])
        end_checks.append(dict(symbol=symbol,pdf_end_date=run['end'],pdf_end_price=old_end,
                               nse_same_date_close=same,same_date_difference=round(same-old_end,6),
                               latest_date=latest_day,latest_nse_close=latest))
    write_csv(out/'same_date_and_latest_prices.csv',end_checks)
    # Frozen holdings are a valuation sensitivity only, not a new backtest.
    values=[]
    for result in results:
        same=sum(result['per_symbol'][s]['final_qty']*float(nse[s,run['end']]['close']) for s in run['basket'])+result['cash_left']
        latest=sum(result['per_symbol'][s]['final_qty']*float(nse[s,end_checks[0]['latest_date']]['close']) for s in run['basket'])+result['cash_left']
        values.append(dict(strategy=result['strategy'],reported_paper_value=result['paper_value'],
                           reported_net_value=result['net_value'],reported_net_xirr_pct=result['xirr_net_pct'],
                           same_date_frozen_holdings_nse_value=same,
                           latest_frozen_holdings_nse_value=latest,
                           calculation_status='FROZEN REPORTED HOLDINGS ONLY; not a rerun or corrected investment return'))
    write_csv(out/'frozen_reported_holdings_valuation.csv',values)
    winner=max(results,key=lambda r:r['net_value'])
    if indian(winner['net_value']) not in pages[0] or f'{winner["xirr_net_pct"]:.2f}%' not in pages[0]:
        raise ValueError('PDF headline does not match supplied run JSON')
    unique={(r['date'],r['symbol']):r for r in rows}
    price_only_failures=sum(not r['split_only_matches_within_5_paise'] for r in unique.values())
    first=sum(r['pdf_qty_after']*r['nse_raw_close'] for r in starts)
    report=dict(pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),pdf_pages=len(doc),
                pdf_ledger_rows_checked=len(rows),unique_stock_dates=len(unique),
                pdf_json_ledger_price_agreement=True,
                unique_prices_not_split_bonus_only=price_only_failures,
                first_purchase_reported_units_at_actual_nse_price=first,
                first_purchase_cost_including_pdf_fee=first*(1+run['cost_bps']/10000),
                first_contribution=run['contribution'],
                same_date_end_prices_matching=sum(abs(r['same_date_difference'])<=.05 for r in end_checks),
                original_winner=winner['strategy'],reported_net_value=winner['net_value'],
                reported_net_xirr_pct=winner['xirr_net_pct'],
                verdict='FAIL: PDF is not a verified executable whole-share/cash backtest',
                new_strategy_ranking=None)
    (out/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    lines=['# V2 PDF checked against the new NSE data','',
           '**Result: the PDF does not pass as a verified executable whole-share backtest.** Its numbers match its saved simulation, but the simulation price basis and event accounting do not establish an actual cash/share result.', '',
           f'Original: {pdf.name}, {len(doc)} pages. PDF end date {run["end"]}; latest verified NSE date {end_checks[0]["latest_date"]}. Original PDF preserved. SHA-256: {report["pdf_sha256"]}.','',
           f'Checked all {len(rows)} printed annual ledger prices across five strategies ({len(unique)} unique stock/date combinations). All printed prices match v2_main.json. Of the {len(unique)} unique prices, {price_only_failures} differ from actual NSE prices adjusted solely for the recorded splits and equity bonuses by more than Rs 0.05.', '',
           '## First purchase: 2011-01-03','',
           'The first-purchase tables appear on PDF pages 9, 16, 23, 30 and 37. Adjusted prices can be useful for return analysis; they are not prices at which the displayed number of whole shares could have been bought on that date.','',
           '| Stock | PDF price (Rs) | Actual NSE close (Rs) | NSE split/bonus-only price (Rs) | PDF opening shares |',
           '| --- | ---: | ---: | ---: | ---: |']
    for r in starts:
        lines.append(f'| {r["symbol"]} | {r["pdf_price"]:.2f} | {r["nse_raw_close"]:.2f} | {r["nse_split_bonus_only_price"]:.2f} | {r["pdf_qty_after"]} |')
    lines += ['',f'The displayed opening quantities would cost **Rs {indian(first)} before costs**, or Rs {indian(report["first_purchase_cost_including_pdf_fee"])} with the PDF\'s 12-basis-point buy cost, at that day\'s actual NSE closes. The stated first contribution is only Rs {indian(run["contribution"])}. This does not mean every adjusted-price observation is fictitious; it means the displayed units cannot be described as executable historical whole shares.', '',
              'Split/bonus-only prices above are a diagnostic common-unit representation, not replacement execution prices. Factors come from the NSE event record used in the preceding data audit. Dividend, rights and demerger adjustments are deliberately not included in that diagnostic column.', '',
              '## End-date comparison','',
              f'{report["same_date_end_prices_matching"]}/10 of the PDF\'s prices on {run["end"]} match the official NSE close within Rs 0.05. Agreement on the last price does not validate the historical purchases, entitlements, tax basis or strategy ranking.', '',
              '| Stock | PDF end price | NSE same-day close | NSE latest close |','| --- | ---: | ---: | ---: |']
    for r in end_checks:
        lines.append(f'| {r["symbol"]} | {r["pdf_end_price"]:.2f} | {r["nse_same_date_close"]:.2f} | {r["latest_nse_close"]:.2f} |')
    lines += ['', '## What happens to the claimed winner?', '',
              f'Page 1 reports {winner["strategy"]} at Rs {indian(winner["net_value"])} after exit tax and {winner["xirr_net_pct"]:.2f}% net XIRR. Those are faithfully reproduced statements of the old simulation, **not verified returns from the new data**. There is no defensible replacement ranking from a price-column substitution alone.', '',
              'The CSV frozen_reported_holdings_valuation.csv marks the old reported share quantities at NSE prices on the original end date and the latest date. It is explicitly a frozen-holdings sensitivity. It excludes subsequent cash receipts, changed trades, any omitted instruments and recomputed taxes, and must not be presented as a new backtest.', '',
              '## Corrections required by the evidence','',
              '- Use actual historical NSE prices for fills and dated share lots. Apply splits and equity bonuses explicitly to units; do not buy back-adjusted whole shares.',
              '- The archive field used by the engine is Yahoo Adj Close, which includes dividends. It cannot support the PDF claim that headline dividends are excluded; adding a flat assumed dividend yield also overlaps with distributions already represented in adjusted prices. [Yahoo definition](https://help.yahoo.com/kb/SLN28256.html).',
              '- Account for ONGC\'s combined 4x split/bonus in 2011; ITC Hotels and SCILAL demerged entitlements; NTPC bonus-debenture interest and principal; rights subscriptions/calls and fractional proceeds. Preserve SCI\'s BE-series observations.',
              '- The new source audit corrected ITC\'s 2016 stated Rs 8.50 dividend being parsed as Rs 10.50, and South Indian Bank\'s 2017 Rs 0.40 dividend being missed. Declared ex-date amounts are available, but verified payment dates are not yet a complete cash ledger.',
              '- Page 4 explicitly substitutes five-year price CAGR for the intended fundamental score. Updating prices will not turn that proxy into historical ROE/ROCE or other point-in-time fundamentals.',
              '- Recompute costs, tax lots, cash flows, drawdown and XIRR after reconstructing holdings. The old after-tax figures must not be carried over into an updated report.', '',
              '## Files','',
              '- research/data/v2_source_verification/verified/pdf_comparison/all_800_pdf_price_rows.csv: page-numbered audit of every printed ledger price.',
              '- research/data/v2_source_verification/verified/pdf_comparison/first_purchase_prices.csv: first-day ten-stock comparison.',
              '- research/data/v2_source_verification/verified/pdf_comparison/same_date_and_latest_prices.csv: original-end-date and latest price checks.',
              '- research/data/v2_source_verification/verified/pdf_comparison/summary.json: machine-readable verdict and original PDF hash.',
              '- docs/Rebalancing_V2_Verified_Stock_Data.md: underlying full-source audit and corporate-action references.', '',
              'Reproduce: python research/scripts/check_v2_pdf_against_nse.py. This audits the existing report without overwriting it or inventing a new result.', '']
    (ROOT/'docs/Rebalancing_V2_PDF_Check_With_New_Data.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    main()
