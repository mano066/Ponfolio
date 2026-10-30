"""Create a separate, data-backed verification edition; preserve the old PDF."""
import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/pdf_audit_deps'))
sys.path.insert(0,str(Path(tempfile.gettempdir())/'v2-pdf-deps'))
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT,TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
import pymupdf
from build_v2_verified_report import NOTES,ISSUER_SOURCES

BASE=ROOT/'research/data/v2_source_verification/verified'
OUT=ROOT/'docs/Rebalancing_Strategy_V2_NSE_Verification_2011_2026.pdf'
INK=colors.HexColor('#152D3A')
MUTED=colors.HexColor('#526773')
TEAL=colors.HexColor('#087F80')
LIGHT=colors.HexColor('#EFF6F7')
LINE=colors.HexColor('#D5E1E6')
AMBER=colors.HexColor('#854C0B')
PALE=colors.HexColor('#FFF4E2')


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


def money(value):
    text=str(round(float(value)))
    tail=text[-3:]
    head=text[:-3]
    chunks=[]
    while head:
        chunks.insert(0,head[-2:]);head=head[:-2]
    return 'Rs '+','.join(chunks+[tail])


def main():
    pdfmetrics.registerFont(TTFont('ArialV2','C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('ArialV2Bold','C:/Windows/Fonts/arialbd.ttf'))
    pdfmetrics.registerFontFamily('ArialV2',normal='ArialV2',bold='ArialV2Bold',italic='ArialV2',boldItalic='ArialV2Bold')
    styles={
        'body':ParagraphStyle('body',fontName='ArialV2',fontSize=9.4,leading=14,textColor=INK,spaceAfter=8),
        'small':ParagraphStyle('small',fontName='ArialV2',fontSize=8,leading=11.6,textColor=MUTED,spaceAfter=6),
        'title':ParagraphStyle('title',fontName='ArialV2Bold',fontSize=24,leading=29,textColor=INK,spaceAfter=12),
        'h2':ParagraphStyle('h2',fontName='ArialV2Bold',fontSize=13,leading=17,textColor=INK,spaceBefore=12,spaceAfter=8),
        'cell':ParagraphStyle('cell',fontName='ArialV2',fontSize=8.4,leading=11.6,textColor=INK),
        'head':ParagraphStyle('head',fontName='ArialV2Bold',fontSize=8,leading=10.5,textColor=colors.white),
        'label':ParagraphStyle('label',fontName='ArialV2Bold',fontSize=8.5,leading=12,textColor=TEAL,spaceAfter=7),
    }
    story=[]
    def p(text,style='body'):
        return Paragraph(text,styles[style])
    def para(text,style='body'):
        story.append(p(text,style))
    def heading(kicker,title,subtitle):
        para(kicker.upper(),'label');para(title,'title');para(subtitle)
    def table(headers,rows,widths):
        grid=[[p(escape(str(h)),'head') for h in headers]]
        grid += [[p(escape(str(v)),'cell') for v in row] for row in rows]
        t=Table(grid,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),
                              ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
                              ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
                              ('LINEBELOW',(0,-1),(-1,-1),.5,LINE)]))
        story.append(t);story.append(Spacer(1,10))
    def callout(title,text):
        t=Table([[p('<b>'+title+'</b><br/>'+text)]],colWidths=[499])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#E7D2AF')),
                              ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.append(t);story.append(Spacer(1,10))
    def link(label,url):
        safe_url=escape(url,{'"':'&quot;'})
        para(f'<a href="{safe_url}" color="#087F80">{escape(label)}</a>','small')
    def newpage():story.append(PageBreak())

    summary=json.loads((BASE/'full_verification_summary.json').read_text())
    audit=json.loads((BASE/'pdf_comparison/summary.json').read_text())
    prices=read_csv(BASE/'latest_official_prices.csv')
    first=read_csv(BASE/'pdf_comparison/first_purchase_prices.csv')
    historical=read_csv(BASE/'historical_symbol_summary.csv')
    endings=read_csv(BASE/'pdf_comparison/same_date_and_latest_prices.csv')
    actions=read_csv(BASE/'nse_corporate_actions_verified_source.csv')
    divs=read_csv(BASE/'declared_dividends.csv')
    old=json.loads((ROOT/'research/data/v2_main.json').read_text())
    original=ROOT/'docs/Rebalancing_Strategy_Backtest_V2_2011_2026.pdf'
    if hashlib.sha256(original.read_bytes()).hexdigest()!=audit['pdf_sha256']:
        raise ValueError('Original PDF changed since the saved audit')
    if summary['checksum_failures'] or summary['duplicate_keys'] or summary['invalid_ohlc']:
        raise ValueError('Source integrity check failed')

    heading('Verification edition | 12 September 2026','Rebalancing V2\nNSE data verification'.replace('\n','<br/>'),
            'Ten stocks, actual exchange observations, and a check of the original 2011-2026 backtest.')
    callout('Data verified; strategy returns remain unverified',
            'This is a new verification report. The original 41-page PDF is unchanged. Its 15.91% after-tax return and winning strategy are not validated by this audit. No new strategy return is claimed.')
    para('Latest official closing prices','h2')
    para('Session: <b>11 September 2026</b> | Currency: INR | Official end-of-day closes, not streaming quotes. All ten agree with Yahoo daily closes within Rs 0.01.','small')
    table(['Stock','NSE close','Stock','NSE close'],
          [[prices[i]['symbol'],f"Rs {float(prices[i]['nse_close']):,.2f}",prices[i+5]['symbol'],f"Rs {float(prices[i+5]['nse_close']):,.2f}"] for i in range(5)],
          [139,110,139,111])
    para('What was checked','h2')
    table(['Coverage','Verified result'],[
        ['Historical prices','3,891 daily observations per stock, 2011-01-03 to 2026-09-11'],
        ['Corporate actions',f'{len(actions)} NSE records; {len(divs)} declared dividend entries'],
        ['Original PDF',f'{audit["pdf_ledger_rows_checked"]} annual ledger prices; {audit["unique_stock_dates"]} unique stock/date combinations'],
        ['Source integrity','No checksum failures, duplicate stock/date keys or invalid OHLC prices']], [133,366])
    link('Source: NSE official daily price file, 11 September 2026','https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20260911_F_0000.csv.zip')
    para('Quote/action snapshot: 11 September 2026, 12:31 UTC. NSE live-quote API returned HTTP 403; no live-quote freshness is claimed. Full-history verification finished at '+summary['generated_utc']+'.','small')

    newpage()
    heading('01 | Historical purchases','The opening-share test','The original PDF uses adjusted prices in its first-purchase tables on pages 9, 16, 23, 30 and 37.')
    table(['Stock','PDF price','Actual NSE close','Split/bonus-only price','PDF shares'],
          [[r['symbol'],f"{float(r['pdf_price']):.2f}",f"{float(r['nse_raw_close']):.2f}",f"{float(r['nse_split_bonus_only_price']):.2f}",r['pdf_qty_after']] for r in first],
          [102,86,109,115,87])
    para('Prices in rupees. Date: 3 January 2011. The split/bonus-only column is a diagnostic common-unit price, not an executable historical price.','small')
    callout('Rs 1 lakh contributed; Rs 6.22 lakh needed for those actual shares',
            'Treated as actual historical shares, the displayed opening quantities cost <b>'+money(audit['first_purchase_reported_units_at_actual_nse_price'])+'</b> before costs, or <b>'+money(audit['first_purchase_cost_including_pdf_fee'])+'</b> using the PDF\'s 12-basis-point buy cost. Its stated first contribution is only <b>Rs 1,00,000</b>.')
    para('What this establishes','h2')
    para('Adjusted prices can support return analysis. They do not support describing the displayed opening quantities as executable whole-share purchases on that historical date. The correct ledger must use the original exchange price and then apply dated share and cash entitlements.')
    para(f'All {audit["pdf_ledger_rows_checked"]} printed ledger prices agree with the saved simulation JSON. However, {audit["unique_prices_not_split_bonus_only"]} of {audit["unique_stock_dates"]} unique prices differ by more than Rs 0.05 from NSE prices adjusted solely for splits and equity bonuses. A faithful rendering of a simulation is not proof of correct investment accounting.')
    link('Price-adjustment definition: Yahoo adjusted close includes splits and dividends','https://help.yahoo.com/kb/SLN28256.html')

    newpage()
    heading('02 | Full-history cross-check','What differs in the old data','Every calendar date was attempted, including weekends. The downloaded exchange observations provide the new raw-price baseline.')
    table(['Stock','Official rows','Compared','Differences','Largest difference'],
          [[r['symbol'],r['official_rows'],r['compared'],r['mismatched'],f"{float(r['worst_difference_pct']):.4f}%"] for r in historical],
          [111,86,86,99,117])
    para('Comparison: old candidate_unadjusted_close versus actual NSE close. A difference means more than Rs 0.05. Rights/demerger adjustments and vendor discrepancies can explain differences; this table does not label all adjusted observations fictitious.','small')
    para('Coverage and recovered records','h2')
    para(f'Attempted <b>{summary["coverage"]["attempted_dates"]:,} calendar dates</b>; retrieved <b>{summary["coverage"]["downloaded_dates"]:,} exchange files</b>. The combined file contains <b>{summary["coverage"]["rows"]:,} observations</b> for the ten stocks plus available ITCHOTELS and SCILAL records. All ten basket stocks cover the same 3,891 retrieved sessions.')
    para('SCI moved temporarily to the BE series after its 2023 demerger. Those observations were recovered and their series/ISIN preserved. A July 2020 file used a two-digit year; the parser was corrected. No prices were forward-filled.')
    para(f'{len(summary["coverage"]["unavailable"]):,} requested dates returned no usable file. They remain explicitly recorded; no automatic holiday label was assigned. The old vendor file has 60 rows on six dates without matching NSE observations. Several are confirmed NSE holidays.','small')
    link('NSE holiday calendar','https://www.nseindia.com/resources/exchange-communication-holidays')
    link('NSE clearing notice: trading holiday on 15 January 2026','https://nsearchives.nseindia.com/content/circulars/CMPT72278.pdf')

    for index,symbols in enumerate([old['basket'][:5],old['basket'][5:]]):
        newpage()
        heading(f'0{3+index} | Corporate actions',f'The ten-stock event check - {index+1}/2',
                'Key changes to shares or capital. Ex-dates, record dates, allotment dates, listing dates and payment dates are not interchangeable.')
        for symbol in symbols:
            entries=[r for r in actions if r['symbol']==symbol]
            dividend_count=sum('dividend' in r['kind'] for r in entries)
            block=[p(symbol,'h2'),p(escape(NOTES[symbol])),p(f'{len(entries)} NSE records; {dividend_count} dividend entries.','small')]
            if symbol=='ITC':
                block.append(p('Issuer-stated demerger cost allocation: 86.49% ITC / 13.51% ITC Hotels. Fractional-share proceeds and payment dates still require ledger evidence.','small'))
            if symbol=='SCI':
                block.append(p('Issuer-stated demerger cost allocation: 59.68% SCI / 40.32% SCILAL. An unlisted entitlement must not be given an invented tradable quote.','small'))
            story.append(KeepTogether(block))
        para('Evidence: fetched NSE corporate-action responses, dated price files and issuer notices. Complete source wording and URLs are preserved in the companion corporate-action CSV. See source references on page 8.','small')

    newpage()
    heading('05 | Dividends and cash','Declared amounts are not payment dates',
            f'{len(divs)} declared dividend entries were identified, including older records abbreviated as "Int Div".')
    table(['Stock','Latest ex-date','Declared Rs/share'],
          [[s,(r:=max([d for d in divs if d['symbol']==s],key=lambda d:d['ex_date']))['ex_date'],f"{float(r['declared_rupees_per_share']):.2f}"] for s in old['basket']],
          [166,166,167])
    para('These are the latest dividend ex-dates in the fetched records, not confirmations that cash has been paid on those dates. Amounts are per share as declared at the time, not restated to current share counts.','small')
    para('Two parsing corrections','h2')
    table(['Record','Old parsing','Correct declared amount'],[
        ['ITC | 2016-05-30','Rs 10.50','Rs 8.50: the Rs 2 special dividend was already included'],
        ['SOUTHBANK | 2017-07-03','Missing','Rs 0.40: source omitted the currency prefix']], [166,106,227])
    callout('No invented cash receipts','The source CSV leaves unverified payment dates blank. Before rerunning a cash/share strategy, reconcile dividend receipts, NTPC debenture interest and redemptions, rights subscription payments/calls, and demerger fractional proceeds.')
    para('The old optional flat dividend yield does not replace actual payouts. Its adjusted-price archive already reflects dividends, so that additional assumed cash yield overlaps with distributions represented in prices.')

    newpage()
    heading('06 | Previous results','Keep the old result separate','All ten prices at the original end date, 17 July 2026, agree with NSE within Rs 0.05. This validates the last-price comparison, not the preceding trades or tax accounting.')
    callout('Historical simulation - unverified','The figures below are retained only as a record of the original PDF. They are <b>not new results</b> from the verified dataset and should not be used to select a strategy.')
    table(['Old strategy','Old ending value','Old after-exit-tax value','Old net XIRR'],
          [[r['strategy'].replace(' (your PDF)',''),money(r['paper_value']),money(r['net_value']),f"{r['xirr_net_pct']:.2f}%"] for r in old['results']],
          [153,118,135,93])
    para('Why no updated winner appears here','h2')
    para('Replacing the last price or repricing the old share quantities does not reconstruct the trades a corrected strategy would have made. It also does not recover omitted entitlements or establish correct cost bases and taxes. A new ranking requires a new, validated cash/share ledger.')
    para('The original rulebook strategy also substitutes five-year price CAGR for its intended fundamental score. The new price history does not supply historical ROE, ROCE, pledge or holding-change inputs. That limitation remains.')
    para('Required next calculation','h2')
    para('Use actual prices for fills; apply corporate actions to dated lots; reconcile cash receipts and payments; then recompute portfolio values, costs, tax treatment, drawdown and XIRR. Until that work is complete, the original 15.91% after-tax result remains unverified.')
    para('Original PDF preserved: Rebalancing_Strategy_Backtest_V2_2011_2026.pdf. Its audit fingerprint and all 800 page-numbered price comparisons are included in the companion data directory.','small')

    newpage()
    heading('07 | Evidence and reproducibility','Sources and companion data','The report is based on saved source responses and reproducible checks. It is a data-verification edition, not a completed replacement backtest.')
    para('Primary references','h2')
    link('1. NSE official daily prices - 11 September 2026','https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20260911_F_0000.csv.zip')
    link('2. NSE corporate-action records','https://www.nseindia.com/companies-listing/corporate-filings-actions')
    for n,(s,(url,note)) in enumerate(ISSUER_SOURCES.items(),3):
        link(f'{n}. {s} issuer evidence',url)
    link('9. Yahoo adjusted-close definition','https://help.yahoo.com/kb/SLN28256.html')
    para('Companion files','h2')
    para('Location: <b>research/data/v2_source_verification/verified/</b>','small')
    table(['File','Contents'],[
        ['official_daily_prices.csv','Raw exchange OHLCV with symbol, date, ISIN, series and source file'],
        ['latest_official_prices.csv','Latest NSE closes and timestamped vendor comparison'],
        ['nse_corporate_actions_verified_source.csv','303 fetched action records with original terms and URLs'],
        ['declared_dividends.csv','252 declared amounts; unverified payment dates blank'],
        ['full_historical_price_reconciliation.csv','Every comparable old-versus-NSE raw price'],
        ['pdf_comparison/all_800_pdf_price_rows.csv','All original ledger prices, with PDF page numbers'],
        ['full_verification_summary.json','Source integrity, coverage, corrections and remaining limitations']], [248,251])
    para('Reproduce this report','h2')
    para('Run <b>python research/scripts/build_v2_nse_verification_pdf.py</b> from the project root. The builder reads saved verification results and checks the original PDF fingerprint. It never overwrites the original PDF.','small')
    para('No checksum failures, duplicate keys or invalid OHLC prices were found. Source integrity does not establish a complete cash ledger or certify legal/tax treatment. The original report is archived in place and is not presented as validated.','small')

    def furniture(canvas,doc):
        width,height=A4
        canvas.setStrokeColor(LINE);canvas.setLineWidth(.5);canvas.line(48,42,width-48,42)
        canvas.setFont('ArialV2',7.4);canvas.setFillColor(MUTED)
        canvas.drawString(48,29,'V2 | NSE verification | Prices through 11 Sep 2026 | Returns not verified')
        canvas.drawRightString(width-48,29,f'{doc.page}')
    doc=SimpleDocTemplate(str(OUT),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=43,bottomMargin=55,
                          title='Rebalancing V2 - NSE Data Verification 2011-2026',author='Research verification',
                          subject='Verified stock data and audit of the original backtest; no new strategy return')
    doc.build(story,onFirstPage=furniture,onLaterPages=furniture)
    render=ROOT/'tmp/pdfs/v2_verification_edition'
    render.mkdir(parents=True,exist_ok=True)
    with pymupdf.open(OUT) as checked:
        if len(checked)!=8:
            raise ValueError(f'Unexpected pagination: {len(checked)} pages, expected 8')
        for i,page in enumerate(checked):
            page.get_pixmap(matrix=pymupdf.Matrix(1.35,1.35)).save(str(render/f'page_{i+1}.png'))
        extracted='\n'.join(page.get_text() for page in checked)
        for token in ['431.00','426.40','252','303','6,22,121','15.91%']:
            if token not in extracted:
                raise ValueError('Expected data missing from PDF: '+token)
    if hashlib.sha256(original.read_bytes()).hexdigest()!=audit['pdf_sha256']:
        raise ValueError('Original PDF changed during creation')
    print('Created',OUT,'| 8 pages | original unchanged',flush=True)


if __name__=='__main__':main()
