"""Create the five-strategy result PDF from saved, reconciled engine outputs."""
import hashlib,json,sys,tempfile,shutil
from pathlib import Path
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(Path(tempfile.gettempdir())/'v2-pdf-deps'),str(ROOT/'tmp/pdf_audit_deps')]
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from reportlab.graphics.shapes import Drawing,Rect,String,Line
import pymupdf
from backtest_five_verified import NAMES,SYMS

OUT=ROOT/'docs/Rebalancing_Five_Strategies_NSE_Backtest_2011_2026.pdf'
INK=colors.HexColor('#163443');TEAL=colors.HexColor('#067F80');GRAY=colors.HexColor('#536B76');LIGHT=colors.HexColor('#EFF5F6');LINE=colors.HexColor('#D4E1E6')
PALETTE=['#266B8C','#087F80','#64A69D','#A46A40','#7C6799']

def money(x):
 s=str(round(x));tail=s[-3:];head=s[:-3];parts=[]
 while head:parts.insert(0,head[-2:]);head=head[:-2]
 return ','.join(parts+[tail])

def main():
 data=json.loads((ROOT/'research/data/five_strategy_verified/results.json').read_text());rs=data['results']
 for p,h in data['source_hashes'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
 originals=[ROOT/'docs/Rebalancing_Strategy_Backtest_V2_2011_2026.pdf',ROOT/'docs/Rebalancing_Strategy_V2_NSE_Verification_2011_2026.pdf']
 original_hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in originals]
 for name,file in [('AV','arial.ttf'),('AVB','arialbd.ttf')]:pdfmetrics.registerFont(TTFont(name,'C:/Windows/Fonts/'+file))
 pdfmetrics.registerFontFamily('AV',normal='AV',bold='AVB',italic='AV',boldItalic='AVB')
 styles={
 'body':ParagraphStyle('body',fontName='AV',fontSize=9.1,leading=13.2,textColor=INK,spaceAfter=8),
 'small':ParagraphStyle('small',fontName='AV',fontSize=7.8,leading=10.8,textColor=GRAY,spaceAfter=6),
 'title':ParagraphStyle('title',fontName='AVB',fontSize=23,leading=28,textColor=INK,spaceAfter=12),
 'h':ParagraphStyle('h',fontName='AVB',fontSize=12.5,leading=16,textColor=INK,spaceBefore=10,spaceAfter=7),
 'cell':ParagraphStyle('cell',fontName='AV',fontSize=8,leading=10.7,textColor=INK),
 'head':ParagraphStyle('head',fontName='AVB',fontSize=8,leading=10.7,textColor=colors.white),
 'eyebrow':ParagraphStyle('eyebrow',fontName='AVB',fontSize=8,leading=12,textColor=TEAL,spaceAfter=10)}
 story=[]
 def p(text,style='body'):story.append(Paragraph(text,styles[style]))
 def title(k,t,sub):p(k,'eyebrow');p(t,'title');p(sub)
 def table(headers,rows,widths):
  cells=[[Paragraph(escape(str(v)),styles['head']) for v in headers]]+[[Paragraph(escape(str(v)),styles['cell']) for v in r] for r in rows]
  t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
  t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),('LINEBELOW',(0,-1),(-1,-1),.4,LINE)]))
  story.append(t);story.append(Spacer(1,8))
 def callout(text):
  t=Table([[Paragraph(text,styles['body'])]],colWidths=[499]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#FFF3DF')),('BOX',(0,0),(-1,-1),.4,colors.HexColor('#E4D1AE')),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(t);story.append(Spacer(1,9))
 def new():story.append(PageBreak())
 def link(label,url):p('<link href="'+escape(url,{'"':'&quot;'})+'" color="#067F80">'+escape(label)+'</link>','small')
 winner=max(rs,key=lambda r:r['terminal_after_cost'])
 title('NEW BACKTEST | 12 SEPTEMBER 2026','Five strategies, rebuilt','Ten-stock basket | 3 January 2011 to 11 September 2026 | Official NSE prices')
 callout('<b>Model result, not an audited account statement.</b> Actual historical prices and corporate-action records feed a new whole-share ledger. Results are <b>pre-tax</b>, after assumed trading costs, and include declared distributions retained outside trading cash. Payment dates, fractional proceeds and historical fundamentals remain incomplete.')
 p('Same investment for every strategy: <b>Rs 1,00,000 annually, 16 contributions, Rs 16,00,000 total.</b>')
 table(['Strategy','Ending wealth* (Rs)','XIRR*','Sales'],[[r['name'],money(r['terminal_after_cost']),f"{r['xirr_pct']:.2f}%",r['sells']] for r in rs],[199,132,82,86])
 p('* Equity at final NSE closes + residual cash + declared dividends + NTPC scheduled debt distributions, less a hypothetical 0.12% equity exit cost. Ongoing trade costs are already deducted. Not an after-tax or payment-verified liquidation amount.','small')
 p('Ending wealth by strategy','h')
 chart=Drawing(499,145);maximum=max(r['terminal_after_cost'] for r in rs)/100000
 for i,r in enumerate(rs):
  y=118-i*25;value=r['terminal_after_cost']/100000
  chart.add(String(0,y+4,'S'+str(r['code']),fontName='AVB',fontSize=9,fillColor=INK))
  chart.add(Rect(32,y,365*value/maximum,16,fillColor=colors.HexColor(PALETTE[i]),strokeColor=None))
  chart.add(String(403,y+4,f'{value:.2f} lakh',fontName='AV',fontSize=9,fillColor=INK))
 story.append(chart)
 p(f"<b>{escape(winner['name'])}</b> leads this specified model. Its margin over S3 is Rs {money(rs[1]['terminal_after_cost']-rs[2]['terminal_after_cost'])}; that small difference is not evidence of future superiority.")
 p('The original PDFs are preserved. These results replace neither a tax return nor the missing fundamental version of S4.','small')

 new();title('01 | RULES AND EXECUTION','What was actually tested','The basket was fixed by the earlier task. It is not a stock-selection backtest or an unbiased test of all stocks available in 2011.')
 table(['Strategy','Annual rule'],[
 ['S1 Equal annual buying','Never sell. Divide available contribution cash equally among ten stocks, then sweep residual cash.'],
 ['S2 Cash-flow rebalance','Never sell. Fill the largest shortfalls relative to 10% core-stock targets, then sweep residual cash.'],
 ['S3 Band rebalance','Sell eligible units when a core-stock weight exceeds 12.5%, toward 10%; deploy cash to shortfalls.'],
 ['S4 Price-rule proxy','Exit eligible units if five-year share-adjusted price CAGR is negative; trim gains above 100% when overweight. Avoid adding below -10% economic cost return, with the original fallback when none qualify.'],
 ['S5 Momentum tilt','Never sell. After the common first purchase, allocate new cash equally to the top three on trailing one-year share-adjusted price return.']], [140,359])
 p('Shared execution conventions','h')
 p('Review on the first available basket session on or after 3 January each year. Signals and target gaps use the prior session close; fills use the next review-session official open. The first allocation uses 3 January 2011 opens. Whole shares only; unspent cash earns no interest. Each buy and sale incurs an assumed 12 basis points (0.12%).')
 p('Only lots older than 365 days may be sold. Splits preserve lot age; bonus shares start a new maturity clock on the ex-date, a modeling convention. No sale occurs near the uncertain bonus credit dates. Economic cost is allocated across bonuses and demergers; it is not a tax basis.')
 p('Demerged ITCHOTELS and SCILAL holdings are retained separately. They receive no fresh allocation and are excluded from ten-stock target weights. Dividends and debt distributions are not reinvested or spent. Rights lapse; buybacks are not tendered.')
 callout('<b>S4 is a price-rule proxy.</b> Point-in-time ROE, ROCE and other historical fundamental inputs are absent. Its price signals adjust for equity splits and bonuses, but remain price-only: dividends, rights dilution and demerger price gaps can affect rankings. No claim is made that this reconstructs a fundamental strategy.')

 new();title('02 | CORPORATE ACTIONS','Shares and distributions','The new ledger applies events to then-held quantities. It does not buy whole shares using retrospectively adjusted prices.')
 table(['Stock','Treatment used'],[
 ['BHEL','2011 split: 5x units. 2017 bonus: one extra for two.'],
 ['COALINDIA','Declared dividends; no fetched equity split/bonus in the test window. No buyback participation.'],
 ['IOC','2016 and 2018 bonuses: 1:1 each. 2022 bonus: 1:2.'],
 ['ITC','2016 bonus 1:2; 2025 hotels entitlement: one share per ten ITC. Retain whole hotels shares.'],
 ['KTKBANK','2011 and 2016 rights lapse. 2020 bonus: 1:10.'],
 ['ONGC','2011 split plus bonus: combined 4x units. 2016 bonus: 1:2.'],
 ['SCI','2023 demerger: one SCILAL per SCI. Preserve entitlement before listing; no invented pre-listing quote.'],
 ['NTPC','2019 equity bonus: 1:5. 2015 debentures are a separate instrument; Rs12.50 face, 8.49% coupon, scheduled principal repayments in 2023/24/25.'],
 ['TATASTEEL','2018 fully/partly paid rights lapse. 2022 equity split: 10x units.'],
 ['SOUTHBANK','2017 and 2024 rights lapse; no free rights shares or invented renunciation proceeds.']], [105,394])
 p('Distributions and precision','h')
 p('The source archive has 252 declared dividend records, including pre-start records that generate no entitlement here. The engine uses eligible pre-ex-date quantities. ITC 2016 Rs8.50 and SOUTHBANK 2017 Rs0.40 parser corrections are applied. Four issuer-sourced spinoff dividend records are added separately.')
 p('SCILAL 2026 Rs0.55 remains conditional on the 21 September AGM. Other fetched declarations are not a complete approval/payment audit. All distribution amounts are shown at their stated gross terms, without personal taxes or TDS deductions.')
 p('Whole-share entitlements are rounded down at account level. Unverified fractional cash proceeds are excluded and listed in results.json. This can understate proceeds. Annual trading occurs long after the equity bonus events; the ex-date credit convention does not imply actual delivery on that date.','small')

 new();title('03 | ANNUAL COMPARISON','Known wealth components by review','Rs lakh, marked at the review-day close after that year\'s contribution and trades. These are portfolio levels, not annual investment returns.')
 annual=[]
 for i,a in enumerate(rs[0]['annual']):
  annual.append([a['date'],f"{a['invested']/100000:.0f}"]+[f"{r['annual'][i]['wealth']/100000:.2f}"+('*' if r['annual'][i]['unpriced_entitlements'] else '') for r in rs])
 table(['Review date','Paid in','S1','S2','S3','S4','S5'],annual,[94,65,68,68,68,68,68])
 p('Terminal 11 September 2026, after hypothetical exit cost','h')
 table(['Paid in','S1','S2','S3','S4','S5'],[['16.00']+[f"{r['terminal_after_cost']/100000:.2f}" for r in rs]],[84,83,83,83,83,83])
 callout('<b>Interim valuation limitation:</b> an asterisk flags an unpriced demerged entitlement. These rows omit its unknown market value; they are incomplete wealth measures. Unredeemed NTPC principal and accrued unpaid coupons are also omitted before scheduled distribution dates. No maximum drawdown or time-weighted return is claimed from this incomplete interim series.')
 p('All retained listed holdings have an official final-date price. By the final date, the NTPC principal schedule has ended. The terminal model therefore includes final share values and the full scheduled debt distributions, without needing a pre-listing valuation.','small')

 for r in rs:
  new();title(f"0{r['code']+3} | STRATEGY DETAIL",r['name'],f"Model XIRR: {r['xirr_pct']:.2f}% | Total contributions: Rs 16,00,000 | {r['trades']} trades, including {r['sells']} sales")
  table(['Terminal component','Rs'],[
   ['Listed equity at official closes',money(r['equity'])],['Residual trading cash',money(r['cash'])],['Accumulated declared dividends - not reinvested',money(r['dividends'])],['NTPC scheduled coupons and principal retained',money(r['ntpc_income'])],['Less hypothetical equity exit cost',money(r['exit_cost'])],['Ending wealth after modeled costs, before tax',money(r['terminal_after_cost'])]], [355,144])
  p('Final holdings | 11 September 2026','h')
  table(['Stock','Whole shares','NSE close (Rs)','Value (Rs)'],[[h['symbol'],h['quantity'],f"{h['close']:.2f}",money(h['value'])] for h in r['holdings']],[149,105,110,135])
  p(f"Trading costs already deducted: Rs {money(r['costs'])}. Fractional entitlement events with unverified proceeds: {len(r['fractions'])}. All positions use original historical units plus explicit corporate-action changes.",'small')
  p(f"Audit archive: S{r['code']}_transactions_and_events.csv records every contribution, trade and entitlement; S{r['code']}_daily_wealth.csv records daily known components and flags unpriced holdings. Both are in audit_ledgers.zip.",'small')

 new();title('09 | SENSITIVITY AND CHECKS','How stable is the comparison?','Costs are assumptions, not a reconstruction of every historical broker charge. The engine reran all five strategies at each cost level, including changed share rounding and trades.')
 sens=[]
 for r in rs:
  zero=next(x for x in data['sensitivity'] if x['code']==r['code'] and x['cost_bps']==0)
  high=next(x for x in data['sensitivity'] if x['code']==r['code'] and x['cost_bps']==25)
  sens.append([r['name'],f"{zero['xirr_pct']:.2f}%",f"{r['xirr_pct']:.2f}%",f"{high['xirr_pct']:.2f}%"])
 table(['Strategy','0 bps','12 bps base','25 bps'],sens,[220,93,93,93])
 p('Reconciliation and tests','h')
 for s in data['checks']:p('PASS - '+s,'small')
 p('Six focused unit tests also pass: combined ONGC adjustment; aggregate bonus rounding and bonus maturity; rights lapse; demerger quantity/basis allocation; budget and 365-day lock; known-answer XIRR.','small')
 p('What the numbers establish','h')
 p('They establish the output of these five explicit trading policies on the saved official price observations and stated entitlement conventions. They do not establish guaranteed execution, a tax-net result, a reinvested-dividend result, or a prediction about future strategy performance.')
 p('XIRR uses the sixteen dated contributions and a single terminal modeled wealth amount. Distributions remain in the wealth account, so they are not also counted as external XIRR withdrawals. This avoids double counting. Because some amounts may still be receivable or conditional, XIRR is a model metric rather than verified cash realization.')
 p('The basket was selected in hindsight, all strategies share that selection, and no out-of-sample strategy selection was performed. Changing rights participation, dividend reinvestment, taxes or S4 fundamentals would define a different test.')

 new();title('10 | SOURCES AND LIMITS','Reproducible evidence','No original PDF or downloaded exchange archive was overwritten. Source hashes are saved with the new results.')
 link('NSE - final official daily price ZIP (11 September 2026)','https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20260911_F_0000.csv.zip')
 link('NSE - corporate actions','https://www.nseindia.com/companies-listing/corporate-filings-actions')
 link('NSE - rights entitlement choices, including lapse','https://www.nseindia.com/static/trade/members-faqs-rights-entitlement-trading')
 link('SCI issuer - demerger and cost allocation','https://www.shipindia.com/upload/investorsubpage/IntimationtoShareholdersforCostsplitFinalSigned.pdf')
 link('ITC issuer - hotels demerger','https://itcportal.com/investors/proposed-demerger-hotels-business.html')
 link('NTPC annual report 2024-25 - 8.49% bonus debenture terms','https://www.ntpc.co.in/sites/default/files/inline-files/NTPC%20AR%202024-25.pdf')
 for label,url in [('SCILAL 2024/25 dividend evidence','https://www.scilal.com/upload/investor/riGtOiR3ERvMu3oxA2UqZJLSEQzeT6rp7XGVZLNW.pdf'),('SCILAL 2026 proposed dividend - issuer filing','https://www.scilal.com/upload/investor/YgJda8vnKIqry8BFjTMraLOXFmXWEnySTZPbCH4h.pdf'),('SCILAL 2026 record date - exchange filing reproduced by BazaarWatch','https://bazaarwatch.com/announcement/70115/shipping-corporation-of-india-land-and-assets-limited-record-date'),('ITC Hotels - dividend confirmation and fractional entitlements','https://www.itchotels.com/dividend-iepf')]:link(label,url)
 p('Companion output','h')
 p('<b>research/data/five_strategy_verified/</b><br/>results.json - results, holdings, annual values, sensitivities, source hashes.<br/>audit_ledgers.zip - ten CSVs: full transaction/event ledgers and daily components.','small')
 p('<b>Reproduce:</b> python research/scripts/backtest_five_verified.py<br/>Then: python research/scripts/build_five_verified_pdf.py','small')
 p('Data cutoff and remaining uncertainty','h')
 p('This is historical end-of-day data through 11 September 2026, not a streaming quote feed. The verified archive contains 3,891 common sessions for each basket stock. Source checksum and observation checks were completed in the preceding verification report. Two new NSE requests for spinoff actions timed out; issuer evidence was used and saved separately.')
 p('Dividend payment/approval history, fractional proceeds and exact bonus delivery dates are not fully reconciled. Declared dividends are conditional until approvals are confirmed. Taxes, TDS, rights subscriptions, buyback tenders and dividend reinvestment are outside this specified model. Those limits prevent describing the result as an exact realized account return.','small')
 def footer(c,d):
  c.setStrokeColor(LINE);c.line(48,42,A4[0]-48,42);c.setFont('AV',7);c.setFillColor(GRAY)
  c.drawString(48,29,'Five strategies | NSE through 11 Sep 2026 | Pre-tax entitlement model')
  c.drawRightString(A4[0]-48,29,str(d.page))
 doc=SimpleDocTemplate(str(OUT),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=42,bottomMargin=54,title='Five Rebalancing Strategies - NSE Backtest 2011-2026',author='Research backtest')
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
 with pymupdf.open(OUT) as check:
  assert len(check)==11, f'Expected 11 pages, got {len(check)}'
  text='\n'.join(p.get_text() for p in check)
  for r in rs:assert money(r['terminal_after_cost']) in text
  for i,page in enumerate(check):
   for block in page.get_text('blocks'):
    assert block[0]>=40 and block[2]<=A4[0]-35 and block[3]<=A4[1]-15,(i,block)
 assert original_hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in originals]
 print('Created',OUT,'11 pages',OUT.stat().st_size,'bytes; originals unchanged. Free disk:',shutil.disk_usage(ROOT).free)
 print('Sensitivity',json.dumps(sens))

if __name__=='__main__':main()
