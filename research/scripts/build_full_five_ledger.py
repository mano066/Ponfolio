"""Publish every saved backtest event and annual balance; preserve source results."""
import sys,tempfile,csv,io,json,zipfile,hashlib,math,shutil
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(Path(tempfile.gettempdir())/'v2-pdf-deps'),str(ROOT/'tmp/pdf_audit_deps')]
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape,A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak,Spacer
from xml.sax.saxutils import escape
import pymupdf
from corporate_action_introduction import add_introduction
BASE=ROOT/'research/data/five_strategy_verified'
TARGET=ROOT/'docs/Rebalancing_Five_Strategies_Full_Annual_Ledgers_2011_2026.pdf'
OUT=TARGET.with_name(TARGET.stem+'_Redesign_Review.pdf')
SYMS='BHEL COALINDIA IOC ITC KTKBANK ONGC SCI NTPC TATASTEEL SOUTHBANK ITCHOTELS SCILAL'.split()
def rc(b):return list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))
def n(v):
 value=float(v);whole,frac=f'{abs(value):.2f}'.split('.');tail=whole[-3:];head=whole[:-3];parts=[]
 while head:parts.insert(0,head[-2:]);head=head[:-2]
 return ('-' if value<0 else '')+','.join(parts+[tail])+'.'+frac
def main():
 data=json.loads((BASE/'results.json').read_text());prices=defaultdict(dict)
 explanations=json.loads((BASE/'decision_explanations.json').read_text())
 backup=TARGET.with_name(TARGET.stem+'_Before_Redesign.pdf')
 if TARGET.exists() and not backup.exists():shutil.copy2(TARGET,backup)
 for r in rc((ROOT/'research/data/v2_source_verification/verified/official_daily_prices.csv').read_bytes()):prices[r['date']][r['symbol']]=float(r['close'])
 hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [BASE/'results.json',BASE/'audit_ledgers.zip']}
 for name,file in [('LV','arial.ttf'),('LVB','arialbd.ttf')]:pdfmetrics.registerFont(TTFont(name,'C:/Windows/Fonts/'+file))
 pdfmetrics.registerFontFamily('LV',normal='LV',bold='LVB',italic='LV',boldItalic='LVB')
 ink=colors.HexColor('#11161d');light=colors.HexColor('#f4f6f9');accent=colors.HexColor('#1f4f8f');line=colors.HexColor('#d7dde5')
 buy=colors.HexColor('#0b7a51');sell=colors.HexColor('#b4432c')
 styles={k:ParagraphStyle(k,fontName='LVB' if k in ['title','head'] else 'LV',fontSize=size,leading=lead,textColor=colors.white if k=='head' else ink,spaceAfter=gap) for k,size,lead,gap in [('body',9,12,7),('small',7.4,10,5),('title',17,21,8),('cell',7.2,9,0),('head',7.2,9,0)]}
 styles['title'].textColor=accent
 story=[];manifest=[];event_count=0;notes={};ids=[];review_count=0
 def tint(hexcode,f):
  c=colors.HexColor(hexcode);f=max(0,min(1,f));return colors.Color(1-(1-c.red)*f,1-(1-c.green)*f,1-(1-c.blue)*f)
 def weightshade(x):return tint('#e0952f',(x-10)/15) if x>10 else tint('#6fa8d0',(10-x)/12)
 def p(t,s='body'):story.append(Paragraph(t,styles[s]))
 def table(head,rows,widths):
  cells=[[Paragraph(escape(str(c)),styles['head']) for c in head]];extra=[]
  for i,row in enumerate(rows,1):
   cr=[]
   for j,c in enumerate(row):
    value=str(c);col=None
    if head[j] in ['Action','Event']:
     if 'BUY' in value and 'SELL' in value:col='#7a3e9d';extra.append(('BACKGROUND',(j,i),(j,i),tint(col,.12)))
     elif value.startswith('BUY'):col='#1f4f8f';extra.append(('BACKGROUND',(j,i),(j,i),colors.HexColor('#eaf0f8')))
     elif value.startswith('SELL'):col='#b4432c';extra.append(('BACKGROUND',(j,i),(j,i),colors.HexColor('#fdf0ec')))
     elif value in ['HOLD','NO POSITION']:col='#5b6775'
     elif value.startswith(('BONUS','SPLIT','DEMERGER','DIVIDEND','SCHEDULED')):col='#0b7a51'
    if head[j] in ['W% before','W% after','Core W%'] and value!='-':extra.append(('BACKGROUND',(j,i),(j,i),weightshade(float(value.rstrip('%')))))
    text=escape(value)
    if col:text='<font color="'+col+'"><b>'+text+'</b></font>'
    cr.append(Paragraph(text,styles['cell']))
   cells.append(cr)
  t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
  t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),ink),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,light]),('GRID',(0,0),(-1,-1),.35,line),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]+extra));story.append(t);story.append(Spacer(1,5));return t
 def cards(items):
  rows=[[Paragraph(escape(label),styles['small']) for label,value in items],[Paragraph('<font size="15" color="#1f4f8f"><b>'+escape(value)+'</b></font>',styles['body']) for label,value in items]]
  t=Table(rows,colWidths=[762/len(items)]*len(items));t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),light),('BOX',(0,0),(-1,-1),.5,line),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(t);story.append(Spacer(1,10))
 def new():story.append(PageBreak())
 p('Five strategy chapters | Decisions and full ledgers','title')
 p('3 January 2011 to 11 September 2026 | 80 strategy-year sections | INR')
 p('Every saved contribution, purchase, sale and corporate-action entry is included. Calendar-year closing balances and stock quantities are independently reconstructed from the event ledger. 2026 is a partial year ending 11 September. Previously reported strategy results are unchanged.')
 table(['Strategy','Contributed (Rs)','Final modeled wealth (Rs)','Model XIRR'],[[r['name'],n(r['invested']),n(r['terminal_after_cost']),f"{r['xirr_pct']:.2f}%"] for r in data['results']],[310,140,190,122])
 p('<b>Reading each chapter:</b> strategy rules and result cards; maps of percentage holdings and cash allocation; then every annual BUY / SELL / HOLD decision with shares before/after, position percentage sold and measured reasons. Calendar-year balances and the complete dated event ledger follow each review. N-codes in raw event tables refer to the complete note appendix.')
 p('<b>Colors:</b> blue action cells = BUY / ADD; red = SELL / TRIM / EXIT; purple = BUY+SELL; gray = HOLD. Weight cells shade orange above the 10% core target and blue below it. Buying cash is green and selling cash red in the cash map. A color is a description of the action, not an investment recommendation.')
 p('<b>Percentage sold</b> = shares sold at the annual review / shares held immediately before that review. It is different from portfolio weight. Before-weight uses the prior session close; after-weight uses the review-day close. Market movement and new contributions can change weights even with no sale.')
 p('<b>Assumptions preserved:</b> pre-tax; dividends and scheduled NTPC debt income are not reinvested; rights lapse; buybacks are not tendered; fractional proceeds are excluded. S4 is a price-rule proxy, not a reconstructed fundamental strategy. Negative cash movements represent purchases; sale receipts are net of modeled trading costs.')
 p('<b>Dates:</b> dividend dates are eligibility/recognition dates, not verified payment dates. Some declarations are conditional. Unpriced demerged shares and outstanding NTPC debt are not assigned invented market prices. Annual known-wealth totals omit those components. This is a model ledger, not a payment-verified broker statement.')
 p('The companion audit_ledgers.zip also retains all 19,455 daily valuation observations. This PDF prints all transactions/events and all annual closing positions, rather than repeating daily marks.','small')
 corporate_ids=add_introduction(ROOT,p,table,new)
 with zipfile.ZipFile(BASE/'audit_ledgers.zip') as z:
  for result in data['results']:
   code=result['code'];logs=rc(z.read(f'S{code}_transactions_and_events.csv'));daily=rc(z.read(f'S{code}_daily_wealth.csv'))
   reviews=explanations[code-1]['reviews']
   new();p(f'Chapter {code} | {result["name"]}','title')
   cards([('Total contributed','Rs '+n(result['invested'])),('Final modeled wealth','Rs '+n(result['terminal_after_cost'])),('Model XIRR',f"{result['xirr_pct']:.2f}%"),('Executed sales',str(result['sells']))])
   rules={1:'Never sell. Divide annual contribution cash equally among ten stocks, then use the residual sweep.',2:'Never sell. New cash fills the largest shortfalls against 10% core-stock targets; remaining affordable cash is swept.',3:'When prior-close core weight exceeds 12.50%, request enough shares to trim toward 10%. Sell only eligible lots older than 365 days, then allocate cash to gaps.',4:'Price-rule proxy: request an exit if five-year split/bonus-adjusted price CAGR is negative. Otherwise trim when economic-cost gain exceeds 100% and core weight exceeds 10%. Add to eligible names; the -10% loss filter has the original fallback if no candidates qualify.',5:'Never sell. After the common first allocation, new cash goes to the top three stocks by one-year split/bonus-adjusted price return, then residual cash is swept.'}
   p('<b>Rule followed:</b> '+rules[code])
   p('<b>Annual timing:</b> first basket session on/after 3 January. Signals use the previous session close; execution uses official review-day opens. The opening allocation has no previous signal and is shared by all strategies. Only whole shares trade; 12 basis points is charged on buys and sales.')
   p('<b>Why a SELL may be partial:</b> the model first calculates the requested quantity, then caps it at shares older than 365 days. A request to exit can leave younger shares behind. The reason tables show this explicitly, including requests that produced no sale.')
   p('<b>What HOLD means:</b> no trade in that stock at the annual review. The reason table distinguishes a no-sell policy, a missing sale trigger, a failed maturity test, an excluded buy candidate and a budget too small to buy a whole share. HOLD does not prevent later corporate-action share additions.')
   if code==4:p('<b>S4 limitation:</b> the rules use price signals and economic holding cost. They do not use verified historical ROE, ROCE or other fundamentals. An exit label is not a finding that the business failed.')
   if code==5:p('<b>S5 fallback:</b> unavailable one-year returns rank last; ties follow fixed basket order. At the 2012 review there is no full one-year lookback at the prior-close signal date, so the top-three selection follows that fallback, not measured momentum leadership.')
   p('<b>Excluded from core target weights:</b> ITCHOTELS and SCILAL, cash, retained distributions and NTPC debt. Their whole-share holdings and the percentage of all priced equity appear in calendar-year balance tables.')
   p('In every year: decision table -> measured reasons -> calendar-year balance -> full dated events. Use the PDF bookmarks to jump directly to a chapter or year.')
   new();p(f'S{code} | Portfolio maps | 2011-2026','title')
   p('Map 1 - percentage of the ten-stock core after each annual review. Orange = above 10%; blue = below 10%. Each year totals 100% before display rounding.','small')
   headers=['Stock']+[str(y) for y in range(2011,2027)];widths=[92]+[670/16]*16
   wt=[[s]+[f"{next(r for r in rv['rows'] if r['symbol']==s)['weight_after']:.1f}" for rv in reviews] for s in SYMS[:10]]
   t=table(headers,wt,widths)
   t.setStyle(TableStyle([('BACKGROUND',(j,i),(j,i),weightshade(float(wt[i-1][j]))) for i in range(1,11) for j in range(1,17)]))
   p('Map 2 - net cash invested in each stock at the review, Rs thousands. Positive green = purchases exceed sale receipts; negative red = sale receipts exceed purchases. Both gross buys and gross sales remain visible in the review table and event ledger.','small')
   cashmap=[[s]+[f"{-next(r for r in rv['rows'] if r['symbol']==s)['net_cash']/1000:.1f}" for rv in reviews] for s in SYMS[:10]]
   t=table(headers,cashmap,widths)
   t.setStyle(TableStyle([('BACKGROUND',(j,i),(j,i),tint('#0b7a51' if float(cashmap[i-1][j])>0 else '#b4432c',min(.55,abs(float(cashmap[i-1][j]))/100))) for i in range(1,11) for j in range(1,17)]))
   holdings=defaultdict(float);cash=earned=invested=0.;lastprice={};ntpcunits=0
   for i,t in enumerate(logs):t['id']=f'S{code}-{i+1:04d}';ids.append(t['id'])
   for year in range(2011,2027):
    review=reviews[year-2011];rr=review['rows'];review_count+=1
    new();p(f'S{code} | {year} | BUY / SELL / HOLD review','title')
    p(f"Review {review['date']} | Signal reference {review['signal_date']} | Annual contribution Rs 1,00,000 | Ten-stock core")
    cards([('Cash before contribution','Rs '+n(review['cash_before'])),('Cash after review','Rs '+n(review['cash_after'])),('Review closing core value','Rs '+n(review['review_equity']))])
    table(['Stock','Held before','Fill (Rs)','Value before (Rs)','W% before','Action','Bought','Sold','Sold % of held','Held after','W% after','Net cash +/-'],[[r['symbol'],str(r['before']),n(r['fill']),n(r['before']*r['reference']),f"{r['weight_before']:.2f}%",r['action'],str(r['bought']),str(r['sold']),f"{r['sold_pct']:.2f}%",str(r['after']),f"{r['weight_after']:.2f}%",n(r['net_cash'])] for r in rr],[85,55,60,83,48,75,44,44,55,55,53,105])
    p('Held = whole shares. Value before uses signal-reference prices; fill is the official review-day open. W% after uses review-day closes. Core weights exclude cash, distributions and demerged stocks. Net cash is positive for net sale receipts and negative for net purchases; trading costs are included.','small')
    p('Sold % is shares sold divided by the opening position, not a reduction in portfolio weight. BUY+SELL means both occurred during the review; an EXIT closes the position, while TRIM leaves shares. No-sale rows show 0.00%.','small')
    table(['Review totals','Bought (Rs incl. costs)','Sold (Rs net of costs)','Core W% after'],[['All ten stocks',n(sum(r['spent'] for r in rr)),n(sum(r['received'] for r in rr)),f"{sum(r['weight_after'] for r in rr):.2f}%"]],[282,180,180,120])
    new();p(f'S{code} | {year} | Why every stock was bought, sold or held','title')
    p('These explanations trace the executed model, including failed sale/buy attempts. They are reconciled to the saved ledger; no reason is inferred from later stock performance.','small')
    table(['Stock','Action','Measured trigger and allocation reason'],[[r['symbol'],r['action'],r['reason']] for r in rr],[92,88,582])
    p('Economic-cost gain is market value versus the model economic basis after share adjustments, not a tax calculation. CAGR and momentum are price-only signals. The absence of a sale does not imply a recommendation to keep the stock.','small')
    yr=[t for t in logs if t['date'].startswith(str(year))];closing=[r for r in daily if r['date'].startswith(str(year))][-1]
    end=closing['date'];opening=dict(holdings);co=cash;eo=earned;vo=invested;mov=defaultdict(lambda:defaultdict(float));printed=[]
    for t in yr:
     q=float(t['quantity']);dc=float(t['cash_change']);de=float(t['earned_change']);s=t['symbol'];kind=t['event']
     if kind=='BUY':holdings[s]+=q;mov[s]['buy']+=q
     elif kind=='SELL':holdings[s]-=q;mov[s]['sell']+=q
     elif kind in ['SPLIT','BONUS','DEMERGER']:holdings[s]+=q;mov[s]['action']+=q
     if kind=='CONTRIBUTION':invested+=dc
     if kind=='DEBENTURE_ENTITLEMENT':ntpcunits+=q
     cash+=dc;earned+=de
     if t['note'] not in notes:notes[t['note']]='N'+str(len(notes)+1).zfill(2)
     printed.append([t['id'],t['date'],s,kind.replace('_',' '),n(q),n(t['price']),n(dc),n(cash),n(de),n(earned),notes[t['note']]])
    assert abs(cash-float(closing['cash']))<1e-5
    assert abs(earned-float(closing['dividends_earned'])-float(closing['ntpc_scheduled_income']))<1e-5
    for ds in sorted(prices):
     if ds<=end:lastprice.update(prices[ds])
    equity=sum(q*lastprice.get(s,0) for s,q in holdings.items());assert abs(equity-float(closing['equity']))<1e-4
    new();p(f'S{code} | {result["name"][3:]} | {year} annual balance','title')
    p(f'Closing observation: {end} | Calendar year, not financial year | {len(yr)} ledger entries | INR')
    table(['Balance','Opening','Change during year','Closing'],[['Cumulative external contributions',n(vo),n(invested-vo),n(invested)],['Trading cash',n(co),n(cash-co),n(cash)],['Declared/scheduled distributions retained',n(eo),n(earned-eo),n(earned)]],[282,160,160,160])
    pr=[]
    for s in SYMS:
     q=holdings[s];px=lastprice.get(s);value=q*px if px is not None else None
     core=sum(holdings[a]*lastprice.get(a,0) for a in SYMS[:10])
     pr.append([s,n(opening.get(s,0)),n(mov[s]['buy']),n(mov[s]['sell']),n(mov[s]['action']),n(q),n(px) if px is not None else 'Unpriced',n(value) if value is not None else ('0.00' if q==0 else 'Excluded'),f'{100*value/core:.2f}%' if s in SYMS[:10] and core else '-',f'{100*value/equity:.2f}%' if value is not None and equity else '-'])
    table(['Stock','Opening qty','Bought','Sold','Action adds','Closing qty','Last close (Rs)','Value (Rs)','Core W%','Priced equity %'],pr,[95,60,55,55,60,65,75,130,75,92])
    p(f'<b>Priced equity:</b> {n(equity)} | <b>Trading cash:</b> {n(cash)} | <b>Retained distributions:</b> {n(earned)} | <b>Known wealth:</b> {n(equity+cash+earned)}','small')
    principal=12.5 if year<2023 else 10 if year==2023 else 5 if year==2024 else 0
    p(f'Core W% uses ten stocks only; priced equity % includes priced spinoffs. Both exclude cash and distributions. Unpriced equity entitlements: {closing["unpriced_entitlements"] or "none"}. NTPC scheduled principal outstanding: Rs {n(ntpcunits*principal)} (nominal, excluded from known wealth; unpaid accrued coupons also excluded). Fractional proceeds excluded. Final-year wealth is before estimated exit cost.','small')
    for j in range(0,len(printed),12):
     new();p(f'S{code} | {year} | Full event ledger {j//12+1}/{math.ceil(len(printed)/12)}','title')
     p('INR. Cash = trading cash; retained = distributions not reinvested. Rights/buyback quantities are informational, not share additions. Notes: see N-code appendix.','small')
     table(['Entry ID','Date','Symbol','Event','Qty','Ref price','Cash +/-','Cash balance','Retained +/-','Retained balance','Note'],printed[j:j+12],[57,65,66,111,55,58,74,74,74,88,40])
     p('BUY/SELL reference prices are official NSE opens; dividend reference prices are stated per-share amounts; zero means not applicable. Trading-cash movements include modeled costs. DIVIDEND EARNED means declaration recognition, not verified payment.','small');event_count+=len(printed[j:j+12])
    fractions=[f for f in result['fractions'] if f['date'].startswith(str(year))]
    if fractions:
     new();p(f'S{code} | {year} | Fractional entitlements','title')
     p('Preserved separately from whole-share positions. No verified cash-in-lieu amount or payment date is available; proceeds are excluded.')
     table(['Event date','Security','Fractional units','Treatment'],[[f['date'],f['symbol'],n(f['quantity']),f['reason']] for f in fractions],[120,150,130,362])
    manifest.append(dict(strategy=code,year=year,closing_date=end,event_count=len(yr),closing_cash=cash,retained_distributions=earned,equity=equity))
   assert all(abs(holdings[h['symbol']]-h['quantity'])<1e-8 for h in result['holdings'])
   assert abs(equity+cash+earned-result['wealth'])<1e-4
   new();p(f'S{code} | Final reconciliation','title')
   table(['Final component','Rs'],[['Priced shares',n(equity)],['Trading cash',n(cash)],['Retained declared/scheduled distributions',n(earned)],['Wealth before estimated exit cost',n(equity+cash+earned)],['Less hypothetical exit cost',n(result['exit_cost'])],['Final modeled wealth, pre-tax',n(result['terminal_after_cost'])]],[552,210])
   p('Estimated exit cost is a valuation deduction, not an executed sale. Final holdings remain in this ledger; this creates no SELL events and does not override the one-year sale restriction.')
 allnotes=list(notes.items())
 for j in range(0,len(allnotes),9):
  new();p('Complete ledger-note appendix','title');p('N-codes reproduce the complete original note for every event. A blank source note is explicitly identified.')
  table(['Code','Full original note'],[[code,note or '(No note in source ledger)'] for note,code in allnotes[j:j+9]],[62,700])
 new();p('Source trail and verification','title')
 p(f'All {event_count:,} saved transaction/event rows are printed exactly once. All 80 annual balances reconcile to saved daily valuations. All {review_count*10} stock-review explanations were generated by tracing unchanged execution and checking every event against the saved source ledger. Closing quantities and strategy results are unchanged.')
 p('Inputs: research/data/five_strategy_verified/results.json and audit_ledgers.zip. Prices: research/data/v2_source_verification/verified/official_daily_prices.csv. Issuer and exchange source links appear in the accompanying five-strategy backtest report.')
 for file,h in hashes.items():p(escape(file)+' SHA-256: '+h,'small')
 p('Reproduce: python research/scripts/build_full_five_ledger.py. This builder expands saved results; it does not recalculate strategy returns. PDF values round to two decimals, so visible subtotals can differ slightly from full-precision source CSV arithmetic.')
 def footer(c,d):
  c.setFont('LV',7);c.setFillColor(ink);c.drawString(40,23,'Full annual ledger | Pre-tax entitlement model | 2011-2026 | 2026 through 11 Sep');c.drawRightString(802,23,str(d.page))
 SimpleDocTemplate(str(OUT),pagesize=landscape(A4),leftMargin=40,rightMargin=40,topMargin=32,bottomMargin=38,title='Five Strategies - Full Annual Ledgers 2011-2026',author='Research backtest').build(story,onFirstPage=footer,onLaterPages=footer)
 with pymupdf.open(OUT) as pdf:
  text='\n'.join(pg.get_text() for pg in pdf)
  for key in ids:assert text.count(key)==1,key
  for key in corporate_ids:assert text.count(key)==1,key
  assert review_count==80
  for i,pg in enumerate(pdf):
   for b in pg.get_text('blocks'):assert b[0]>=35 and b[2]<=808 and b[3]<=580,(i,b)
  pages=len(pdf)
  toc=[];active=None
  for i,pg in enumerate(pdf):
   lines=pg.get_text().splitlines()
   heading=next((line for line in lines if line.startswith(('Chapter ','Introduction |')) or line.startswith(tuple('S'+str(k)+' |' for k in range(1,6))) or line in ['Complete ledger-note appendix','Source trail and verification']),'')
   if heading.startswith('Introduction |'):
    toc.append([1,heading,i+1]);continue
   if heading.startswith('Chapter '):
    active='S'+heading.split()[1];toc.append([1,heading,i+1]);continue
   if heading.startswith(tuple('S'+str(k)+' |' for k in range(1,6))):
    code=heading[:2]
    if code!=active:
     toc.append([1,data['results'][int(code[1])-1]['name'],i+1]);active=code
    if 'BUY / SELL / HOLD review' in heading or 'Portfolio maps' in heading:toc.append([2,heading,i+1])
    elif 'annual balance' in heading:toc.append([3,heading,i+1])
    elif 'Final reconciliation' in heading:toc.append([2,heading,i+1])
    else:toc.append([3,heading,i+1])
   elif heading in ['Complete ledger-note appendix','Source trail and verification']:toc.append([1,heading,i+1])
  pdf.set_toc(toc,collapse=1)
  pdf.saveIncr()
 assert all(hashlib.sha256((BASE/k).read_bytes()).hexdigest()==v for k,v in hashes.items())
 (BASE/'full_ledger_validation.json').write_text(json.dumps(dict(pages=pages,events=event_count,annual_sections=manifest,input_hashes=hashes),indent=2))
 print('Created',OUT,'pages',pages,'events',event_count,'bytes',OUT.stat().st_size,flush=True)
if __name__=='__main__':main()
