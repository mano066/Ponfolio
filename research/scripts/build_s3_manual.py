"""Create a standalone S3 manual and attach its complete existing audit chapter."""
import sys,tempfile,json,csv,io,zipfile,hashlib,math
from pathlib import Path
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(Path(tempfile.gettempdir())/'v2-pdf-deps'),str(ROOT/'tmp/pdf_audit_deps')]
import pymupdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak,Flowable
B=ROOT/'research/data/five_strategy_verified'
WORK=Path(tempfile.gettempdir())/'s3_professional_manual';WORK.mkdir(exist_ok=True)
OUT=WORK/'S3_Band_Rebalancing_Professional_Guide_and_Full_Ledger.pdf'
DATA=json.loads((B/'results.json').read_text());R=DATA['results'][2]
REV=json.loads((B/'decision_explanations.json').read_text())[2]['reviews']
SOURCE=ROOT/'docs/Rebalancing_Five_Strategies_Full_Annual_Ledgers_2011_2026.pdf'
def money(x):
 a,b=f'{abs(float(x)):.2f}'.split('.');tail=a[-3:];head=a[:-3];parts=[]
 while head:parts.insert(0,head[-2:]);head=head[:-2]
 return ('-' if float(x)<0 else '')+','.join(parts+[tail])+'.'+b
def csvrows(b):return list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))
with zipfile.ZipFile(B/'audit_ledgers.zip') as z:
 LOG=csvrows(z.read('S3_transactions_and_events.csv'));DAILY=csvrows(z.read('S3_daily_wealth.csv'))
YEARS=[next(x for x in reversed(DAILY) if x['date'].startswith(str(y))) for y in range(2011,2027)]
for name,file in [('S3','arial.ttf'),('S3B','arialbd.ttf')]:pdfmetrics.registerFont(TTFont(name,'C:/Windows/Fonts/'+file))
pdfmetrics.registerFontFamily('S3',normal='S3',bold='S3B',italic='S3',boldItalic='S3B')
NAVY=colors.HexColor('#14263d');BLUE=colors.HexColor('#1f4f8f');GRAY=colors.HexColor('#f0f4f8');GREEN=colors.HexColor('#0b7a51');RED=colors.HexColor('#b4432c')
W=A4[0]-88
ST={k:ParagraphStyle(k,fontName='S3B' if k in ['title','head','cover'] else 'S3',fontSize=size,leading=lead,textColor=NAVY,spaceAfter=gap) for k,size,lead,gap in [('body',10,14,9),('small',8,11,7),('cell',8.1,11,0),('head',8.1,11,0),('title',20,25,16),('cover',34,39,20),('code',8.2,12,8)]}
ST['head'].textColor=colors.white;ST['title'].textColor=BLUE
story=[];headings=[]
def p(s,style='body'):story.append(Paragraph(s,ST[style]))
def table(head,rows,widths=None):
 widths=widths or [W/len(head)]*len(head)
 cells=[[Paragraph(escape(str(x)),ST['head']) for x in head]]+[[Paragraph(escape(str(x)),ST['cell']) for x in row] for row in rows]
 t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,GRAY]),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#d7dde5')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
 story.append(t);story.append(Spacer(1,10))
def page(title):
 if story:story.append(PageBreak())
 headings.append(title);p(title,'title')
def link(label,url):p('<link href="'+escape(url,{'"':'&quot;'})+'" color="#1f4f8f">'+escape(label)+'</link>','small')
def box(title,body):table([title],[[body]],[W])
class WealthChart(Flowable):
 def __init__(self):Flowable.__init__(self);self.width=W;self.height=175
 def draw(self):
  c=self.canv;left=40;bottom=28;ww=W-55;hh=120;maximum=60
  c.setFont('S3',7)
  for v in [0,20,40,60]:
   y=bottom+hh*v/maximum;c.setStrokeColor(colors.HexColor('#d7dde5'));c.line(left,y,left+ww,y);c.setFillColor(NAVY);c.drawRightString(left-7,y-2,str(v))
  for field,col in [('wealth',BLUE),('invested',GREEN)]:
   path=c.beginPath()
   for i,r in enumerate(YEARS):
    x=left+ww*i/15;y=bottom+hh*float(r[field])/100000/maximum
    if i:path.lineTo(x,y)
    else:path.moveTo(x,y)
   c.setStrokeColor(col);c.setLineWidth(2);c.drawPath(path)
  c.setFillColor(NAVY);c.drawString(0,158,'Rs lakh');c.drawString(left,12,'2011');c.drawRightString(left+ww,12,'2026*')
  c.setFillColor(BLUE);c.drawString(140,158,'Known wealth before exit cost');c.setFillColor(GREEN);c.drawString(340,158,'Contributions')

page('S3 | Band rebalancing')
p('Strategy specification<br/>and implementation guide','cover')
p('A complete operating document, with the full S3 annual decision and event ledger attached.')
story.append(Spacer(1,20))
table(['TARGET PER STOCK','SALE TRIGGER','REVIEW'],[['10% of core equity','Strictly above 12.5%','Once per year']])
table(['MODEL CONTRIBUTION','SALE ELIGIBILITY','BACKTEST WINDOW'],[['Rs 1,00,000 each year','Lot age strictly >365 days','3 Jan 2011 - 11 Sep 2026']])
p('Prepared 13 September 2026 | Version 1.0 | INR | Historical model specification','small')
box('Purpose','Understand precisely what S3 does, reproduce the tested calculation, design an auditable implementation and recognize the assumptions that must change or be verified before real-money execution.')
p('<b>Evidence boundary:</b> this document explains the existing saved backtest. It does not claim newly downloaded prices, live quotes, verified dividend bank credits or an operational broker integration. Results are pre-tax and include declared/conditional entitlements. Historical performance is not a forecast.')
p('The standalone appendix contains all 16 S3 annual reviews, all 160 stock-level explanations, annual balances, dated events and the shared note glossary. Original source files and results remain unchanged.','small')

page('01 | Strategy in plain English')
p('S3 tries to control concentration in a fixed ten-stock portfolio. Each stock has a 10% reference target. Once a year, a stock above 12.5% of core equity is considered for a trim toward 10%. The model then invests new money, remaining cash and sale proceeds into allocation shortfalls.')
table(['What S3 does','What the tested rule does not do'],[
 ['Trims an overweight position when eligible old shares exist.','It does not sell simply because a price has fallen or a company has weak fundamentals.'],
 ['Uses a 2.5 percentage-point upper tolerance above the 10% target.','It does not use a symmetric 7.5%-12.5% trading band. There is no 7.5% buy trigger.'],
 ['Checks at the annual review.','It does not enforce a continuous daily 12.5% cap. Positions can exceed that weight between reviews.'],
 ['Adds cash to underweight candidates, then sweeps residual cash.','It does not guarantee every closing weight equals exactly 10%.'],
 ['Keeps demerged child shares outside the ten-stock target calculation.','It does not periodically replace the original basket.']],[W/2,W/2])
p('<b>Why a band?</b> A tolerance can avoid trading every small weight drift while still reducing larger concentration. That is the strategy rationale; it is not evidence that 12.5% is optimal for this basket.')
p('<b>Why a sale is not a company verdict:</b> S3 sells because a holding is large relative to the other core holdings. It can trim a successful company and add to a declining one. Business quality and valuation are not inputs.')
box('Reading the document','Sections 02-08 specify the rules and examples. Sections 09-13 describe data, technology and operations. Sections 14-17 report historical outcomes. Sections 18-20 cover risks, research changes and evidence. The final appendix reproduces the complete S3 audit chapter.')

page('02 | Exact tested configuration')
table(['Parameter','Specification'],[
 ['Core universe, fixed order','BHEL, COALINDIA, IOC, ITC, KTKBANK, ONGC, SCI, NTPC, TATASTEEL, SOUTHBANK.'],
 ['Capital / horizon','16 contributions of Rs 1,00,000 = Rs 16,00,000; 2011-2026. Final observation is 11 September 2026, a partial calendar year.'],
 ['Review date','First available common basket session on or after 3 January each year. The saved calendar contains 3,891 common observations.'],
 ['Decision prices','Previous common session close; first allocation uses that day\'s opens because there is no previous snapshot. Same-day split/bonus prices are translated to current units.'],
 ['Execution prices','Official review-day raw opens, with 12 basis points (0.12%) assumed cost on each buy and each sale. Actual execution at those prices is not guaranteed.'],
 ['Sale trigger / target','Weight >0.125; requested trim toward 0.10 of the fixed pre-sale core-equity total. Equality at 12.5% does not trigger.'],
 ['Eligible lots','More than 365 calendar days old; sell eligible lots in their stored acquisition order. Exactly 365 days old is ineligible.'],
 ['Purchases','Whole shares. Cash-inclusive 10% target gaps, ranked largest first; up to three residual sweeps afterward.'],
 ['Distributions','Declared dividends and scheduled NTPC debt income retained separately; not reinvested into trading cash.'],
 ['Corporate choices','No rights subscription/renunciation, no buyback tender, retain demerged child shares, exclude unverified fractional proceeds.'],
 ['End valuation','Priced shares + cash + retained declarations/scheduled income, less hypothetical 0.12% exit cost on priced equity. No actual terminal sale or tax deduction.']],[137,W-137])

page('03 | Annual process and timing')
table(['Step','Action and reason'],[
 ['1. Reconstruct state','Replay recorded holdings and cash. Recognize due declarations, share actions and scheduled debt income in the saved sequence. Check the entire core basket has valid prices.'],
 ['2. Freeze the signal','Use the previous session close, translated for a same-day split or bonus. The current day\'s closing price is never used to decide that morning\'s trades.'],
 ['3. Add annual capital','Credit Rs 1,00,000 to trading cash. It is available to buy, but does not enter the sale-weight denominator.'],
 ['4. First year only','Allocate the initial cash equally by budget among the ten stocks, using whole shares and costs, then run the allocation/sweep routine. There is no opening trim.'],
 ['5. Later years: sell stage','Freeze total core equity at reference prices. In fixed basket order, test each holding against 12.5%, calculate its requested trim and cap it by mature shares.'],
 ['6. Buy stage','Recalculate core equity plus cash after sales. Rank gaps once, fill positive gaps sequentially, then sweep affordable residual cash up to three times.'],
 ['7. Close and reconcile','Record every fill and reason; use that day\'s closes for reporting after-weights. Save cash, lots, retained distributions and a reproducible decision snapshot.']],[120,W-120])
p('<b>Same-date event order in the engine:</b> dividend recognition first; share/debt actions next; scheduled NTPC income next; annual review after those events. Eligibility for unusual overlapping actions requires an explicit source check before generalizing the engine to new data.')
p('<b>Demerger collision:</b> if a review falls on an ex-demerger date, the engine deliberately raises an error. It requires a separately specified pre-event decision snapshot; it does not invent a comparable price.')
box('Historical execution assumption','The simulation spends same-review sale proceeds on purchases at the same official open. A real sequence of sales, confirmations and purchases cannot be assumed to obtain one identical opening price. See the operating controls in Section 12.')

page('04 | Sell rule and percentage sold')
p('Let q be held shares, P the reference close and E the ten-stock equity total before any review sales. Cash, retained distributions, child shares and NTPC debt are excluded from E.')
table(['Calculation','Exact meaning'],[
 ['E = sum(q[i] x P[i])','One pre-sale total, frozen for all ten sale decisions.'],
 ['w[i] = q[i] x P[i] / E','Core portfolio weight. If E is zero, no weight sale is requested.'],
 ['Trigger: w[i] > 0.125','Strict comparison; 12.50% exactly does not trigger.'],
 ['Requested = floor((q[i] x P[i] - 0.10 x E) / P[i])','Whole shares needed to move toward 10% of the frozen core total, rounded down.'],
 ['Eligible = sum(lot shares with age >365 days)','Age is review date minus recorded acquisition date. This is a strategy convention, not a tax ruling.'],
 ['Sold = min(Requested, Eligible)','An overweight stock can have a partial sale or no sale when shares are too young.'],
 ['Sold % = 100 x Sold / q[i]','Percentage of the opening shares sold, not percentage points of portfolio weight.'],
 ['Net proceeds = Sold x open x (1 - 0.0012)','Sale receipts become trading cash.']],[W*.49,W*.51])
p('<b>Illustrative calculation:</b> E = Rs 1,00,000; a holding has 200 shares at Rs 100, giving 20% weight. Requested sale = floor((20,000 - 10,000) / 100) = 100 shares. If only 60 are old enough, sell 60: 30% of the opening position. The younger shares remain.')
p('<b>Rounding and changing denominators:</b> the trim is toward a reference target, not an exact post-sale 10% solution. The equity denominator changes after sales, prices can gap at the open, and new money changes the later buy targets.')

page('05 | Buy allocation and residual cash')
p('After the sale stage, let C be trading cash, including the annual contribution and net sale receipts. Revalue the remaining ten core holdings at the same decision prices.')
table(['Operation','Exact tested behavior'],[
 ['Cash-inclusive total','A = remaining core equity at decision prices + C. Retained dividends, child stocks and debt are excluded.'],
 ['Gap per stock','g[i] = 0.10 x A - q[i] x P[i]. A stock above 10% of equity alone can still have a positive gap once new cash is included.'],
 ['Ranking','Sort (gap, symbol) descending once. Equal gaps therefore use reverse alphabetical symbol order in this implementation.'],
 ['Gap fill','For a positive gap, buy floor((min(gap, current cash) + 0.00000001) / (open x 1.0012)) shares. The small epsilon only handles floating arithmetic boundaries.'],
 ['Cash update','Deduct shares x open x 1.0012. The next stock sees the remaining cash. Gaps are not reranked after each purchase.'],
 ['Residual sweep','Up to three passes. Identify affordable candidates in fixed basket order; divide current cash equally among them; attempt whole-share buys using that per-stock budget.'],
 ['Stopping','Stop if no candidate is affordable, or after three passes. Cash may remain even when a stock is affordable but the divided budget is too small.']],[145,W-145])
p('<b>Residual purchases are not strict target-gap trades.</b> The sweep can buy a stock even when its gap is zero or negative, and can leave some weights above 10%. This is part of the tested implementation.')
box('Why BUY+SELL is possible','The sale stage ignores cash in its denominator. The buy stage includes cash. A stock trimmed toward the smaller equity-only target can then fall short of the larger cash-inclusive target and be bought again. Removing these opposing trades would change fees, lot ages and future decisions; it needs a separately tested version.')

page('06 | Actual example: KTKBANK in 2013')
ex=next(x for x in REV[2]['rows'] if x['symbol']=='KTKBANK')
table(['Observed item','Verified saved-model value'],[
 ['Review / signal date','3 January 2013 / 2 January 2013'],['Opening shares / reference close',f'{ex["before"]} shares / Rs {money(ex["reference"])}'],['Core weight before',f'{ex["weight_before"]:.4f}% > 12.50%'],['Sale request / eligible quantity','125 requested / 257 shares older than 365 days'],['Sale executed',f'125 shares at Rs {money(ex["fill"])}; {ex["sold_pct"]:.4f}% of opening shares'],['Net sale proceeds','Rs '+money(ex['received'])],['Subsequent allocation gap','Rs 9,893.37 under the cash-inclusive target'],['Buy executed',f'57 shares at Rs {money(ex["fill"])}; Rs {money(ex["spent"])} including cost'],['Closing review quantity','257 - 125 + 57 = 189 shares'],['Core weight after',f'{ex["weight_after"]:.4f}% using review-day closes'],['Net trading-cash effect','Rs '+money(ex['net_cash'])+' received']],[W*.49,W*.51])
p('<b>Why sell?</b> Weight 19.62% exceeded the 12.5% trigger. The reason was concentration, not a negative price outlook or a need to recognize a tax profit.')
p('<b>Why buy again?</b> After the trim, the annual contribution and sales cash raised the amount targeted per stock. The same holding qualified for a top-up. The ledger correctly shows both gross trades rather than silently reporting only the net reduction of 68 shares.')
p('<b>What 48.64% means:</b> 125 / 257 x 100. It does not mean the portfolio lost 48.64%, nor that the stock had a 48.64% portfolio weight.')

page('07 | Corporate actions and economic accounting')
table(['Event','S3 treatment and important distinction'],[
 ['Cash dividends','Eligible shares x declared amount on the then-existing share basis. Accumulate outside trading cash. Eligibility/recognition dates are not verified payment dates; some declarations remain conditional.'],
 ['Stock split','Multiply units and retain original lot dates; total economic basis stays unchanged. Example: BHEL 2011 5x and TATASTEEL 2022 10x.'],
 ['Equity bonus','Add whole shares, store fractions separately and allocate economic basis across old/new shares. New bonus lots use ex-date as their model age start. Actual credit/tax acquisition treatment requires separate verification.'],
 ['Combined ONGC event','8 February 2011 split plus bonus gives a combined 4x equity multiplier. Applying only one 2x adjustment is incorrect.'],
 ['Demerger','Retain whole SCILAL and ITCHOTELS shares, excluded from core targets. Use issuer economic-cost allocation. No invented price before listing; retain unresolved fractions separately.'],
 ['NTPC bonus debentures','2015 debt entitlement is not equity. Track Rs 12.50 original principal per eligible unit, 8.49% scheduled coupons and staged 2023-2025 principal repayments outside trading cash.'],
 ['Buyback / meeting notice','No buyback tender or automatic receipts. A meeting-only notice does not itself add cash or shares.']],[132,W-132])
p('Raw NSE prices are used for fills. Split/bonus share adjustments are explicit. S3 does not use the trailing momentum/CAGR signals that the shared engine also computes for other strategies.')
p('ITCHOTELS reports distributing fractional-entitlement proceeds, but S3\'s investor-specific amounts are unreconciled and excluded. SCILAL\'s 2026 Rs 0.55 declaration is conditional at the 11 September cutoff. These limitations matter when reading modeled wealth as if it were cash received.','small')
link('Issuer: ITC Hotels dividend and fractional-entitlement information','https://www.itchotels.com/dividend-iepf')

page('08 | Rights lapse: an explicit model choice')
p('A rights offer lets an eligible shareholder subscribe for additional shares at the issue price. It does not automatically add paid-up shares. S3 assumes no subscription and no sale or renunciation of the entitlement.')
table(['NSE ex-date','Offer','Subscription terms per new share'],[
 ['2011-02-25','KTKBANK 2:5','Rs 85'],['2016-10-24','KTKBANK 1:2','Rs 70'],['2017-02-16','SOUTHBANK 1:3','Rs 14'],['2018-01-31','TATASTEEL 4:25 fully paid; 2:25 partly paid','Rs 510 fully paid; Rs 615 total partly-paid issue price, with call schedule not reconciled'],['2024-02-27','SOUTHBANK 1:4','Rs 22']],[91,190,W-281])
p('<b>What the ledger means:</b> RIGHTS LAPSE quantity is held shares x offer ratio. It is informational, not a sale and not an addition to equity holdings. Zero reference price is a placeholder; the subscription price is not zero. Cash and distribution changes are zero.')
p('<b>Timing correction:</b> the row sits on the ex-date and records assumed non-participation. It is not evidence that legal expiry happened on that day. Unused rights expire after the issue closes; actual closing and renunciation deadlines need each offer document.')
p('<b>Fraction example:</b> 62 shares x 2/5 = 24.8 mathematical entitlement units. This does not establish a right to receive 24.8 tradable equity shares. The specific issue\'s fractional-entitlement rules must be checked.')
p('<b>Implementation decision:</b> preserving lapse reproduces this backtest. Choosing to subscribe or monetize rights is a different policy; specify funding, deadlines, fees, fractional treatment and subsequent lot dates, then rerun the test. Letting valuable rights lapse can forgo value and dilute ownership.')
link('NSE FAQ: rights entitlements, subscription, renunciation and lapse','https://www.nseindia.com/static/trade/members-faqs-rights-entitlement-trading')

page('09 | Required data and evidence controls')
table(['Input','Minimum fields and validation'],[
 ['Price observations','Exchange, symbol/ISIN, series, trading date, raw open/close, source URL/file, retrieval timestamp, checksum. Reject duplicate keys, invalid prices and silent forward-filled execution prices.'],
 ['Corporate actions','Stable event ID, issuer/security, type, ex-date, record date, ratio, amount, subscription terms, declaration/approval/payment status and evidence. Keep distinct date types.'],
 ['Tax lots / economic lots','Lot ID, quantity, acquisition date, economic basis and action lineage. Tax basis must be a separate ledger; the backtest economic basis is not a tax computation.'],
 ['Cash and entitlement accounts','External contribution, purchase/sale cash, actual fees, declaration receivable, confirmed payment, scheduled debt and fractions. Do not spend an unconfirmed receivable.'],
 ['Trading calendar','Use exchange sessions and validated security availability. A missing source file must not silently be interpreted as an exchange holiday.'],
 ['Decision snapshot','Versioned rules, source hashes, state before contribution, price timestamp, core total, weights, mature quantities, requests, fills and reason codes.']],[133,W-133])
p('<b>Existing evidence:</b> 39,928 raw price rows cover the core and available spinoff observations; 3,891 common core sessions feed the saved model. Corporate actions and corrected declared amounts are saved separately. This guide uses that evidence unchanged; it is not a fresh September 13 market-data audit.')
p('<b>Missingness policy:</b> for production, stop the affected review until a missing price, unexplained position difference or material unresolved corporate action is resolved. Do not substitute a guessed number to finish the calculation.')

page('10 | Technology and system design')
p('The reproducible research engine is Python using CSV/JSON data and ZIP audit exports. A production system can reuse its pure calculation rules, while keeping data ingestion, accounting and broker execution separate. No broker connection or live deployment is supplied by this PDF.')
table(['Component','Implementation responsibility'],[
 ['Source collector','Download official daily files and issuer action evidence. Store immutable originals, request status and checksums. A corrected source creates a new version.'],
 ['Normalizer / validator','Map ISINs and symbols; validate dates, prices and action terms; flag duplicates and missing observations.'],
 ['State and event store','A transactional database can store lots, cash movements, actions, order intents and fills. Keep an append-only event history with unique IDs and recoverable backups.'],
 ['Strategy calculator','Pure functions for weights, maturity, trim requests, target gaps and rounding. Run on a frozen snapshot with a versioned configuration.'],
 ['Execution adapter','Convert approved intents to broker orders; receive acknowledgments/fills; handle rejection, partial execution and cancellation. Never treat submission as a fill.'],
 ['Reconciler / reporter','Compare holdings, funds and fees against the broker/depository. Export decision logs, ledger, exceptions and the annual report.'],
 ['Scheduler / monitoring','Daily evidence/account checks; annual signal job; event notifications and controlled recovery. Alert on stale data or unmatched fills.']],[138,W-138])
box('Separation of concerns','Official sources -> validated snapshot -> portfolio state -> S3 calculation -> reviewable order intents -> execution -> actual fills -> reconciled state -> report. Research fills may be simulated; live accounting must use actual confirmations.')
p('Use fixed-precision money and explicit rounding in a new production implementation. The saved research engine uses floats with small tolerances. Changing numerical conventions needs reconciliation against the historical outputs before calling the implementations equivalent.','small')

page('11 | Data model and reproducible algorithm')
table(['Record','Suggested key fields'],[
 ['security / price','security_id, ISIN, symbol, date, raw_open, raw_close, source_id'],['action / lot','action_id, type, date_basis, terms, status; lot_id, security_id, qty, acquired_date, economic_basis, parent_lot_id'],['cash / entitlement','event_id, date, account, amount, source_id, status; payment confirmation remains distinct from declaration'],['decision / order / fill','run_id, config_hash, snapshot_hash, stock, trigger, requested_qty, eligible_qty, reason; order_id, broker_id, fill_id, qty, price, fee']],[140,W-140])
p('<b>Algorithm outline for reviews after the opening allocation:</b>')
p('1. Apply validated due events; obtain reference prices P and review fills F.<br/>2. Add annual contribution to C; freeze E = sum(q x P).<br/>3. For each core stock in fixed order:<br/>&nbsp;&nbsp;&nbsp;If E &gt; 0 and q x P / E &gt; 0.125:<br/>&nbsp;&nbsp;&nbsp;request = floor((q x P - 0.10 x E) / P).<br/>&nbsp;&nbsp;&nbsp;sell min(request, mature quantity) using eligible lots; update C.<br/>4. Freeze A = sum(remaining q x P) + C.<br/>5. Sort (0.10 x A - q x P, symbol) descending.<br/>6. For each positive gap, buy whole affordable shares at F with costs.<br/>7. Run up to three fixed-order residual sweeps.<br/>8. Save decisions, fills, cash and lots; reconcile every balance.','code')
p('<b>Idempotency:</b> a rerun of the same review must not add another contribution or send duplicate orders. Use a unique review/run key and deduplicate action IDs and broker fill IDs. Resume from confirmed state after a crash.')
p('<b>Auditability:</b> keep attempted and blocked orders as decisions even when no trade occurs. HOLD must distinguish no trigger, immature shares, insufficient whole-share budget and an execution failure.')

page('12 | Practical operating procedure')
table(['Stage','Operator action / acceptance condition'],[
 ['Before first use','Document capital availability and the fixed basket. Import real holdings, acquisition lots and cash. Resolve any differences from the historical model; do not pretend a new account has the model\'s old lots.'],
 ['Before annual review','Confirm session calendar, fresh reference prices, corporate actions and available funds. Freeze and archive the input snapshot.'],
 ['Generate proposals','Produce stock-by-stock before-weight, trigger, requested/mature shares, proposed sell/buy quantity, estimated costs and reasons. Show opposing buy/sell intents explicitly.'],
 ['Execute under a written policy','Select order types, price tolerances and maximum acceptable slippage. Use actual tradable lot availability and broker funds rules. There is no guarantee of fills at the archived open.'],
 ['Handle exceptions','Record partial fills and failed orders. Recompute funding from confirmed fills; do not automatically assume all sale proceeds exist or rerun the whole review as a new contribution.'],
 ['After execution','Reconcile actual quantities, contract-note fees and cash. Archive the variance from the simulated open-price result. Any materially changed allocation policy requires a separate strategy version.'],
 ['Between reviews','Monitor corporate actions and payment status, account discrepancies and business events. S3 has no automatic fundamental exit; any discretionary intervention must be logged separately.']],[130,W-130])
p('NSE explains that market impact depends on order-book liquidity and order size. Therefore a flat 12-basis-point charge is an assumption, not an execution guarantee or a complete broker-fee quotation. [E1]','small')
link('E1 | NSE: impact cost and market liquidity','https://www.nseindia.com/static/products-services/indices-impact-cost')

page('13 | Verification and acceptance tests')
table(['Test','Required outcome'],[
 ['Trigger boundary','Exactly 12.5% produces no sale; slightly above triggers a request. A position below the threshold is not sold by S3.'],
 ['Lot-age boundary','365-day lots are blocked; 366-day lots qualify. Young and mature lots mixed in one holding yield a capped sale.'],
 ['Rounding / affordability','No fractional equity trades, negative holdings or overspent cash. Test one-share affordability including fees.'],
 ['Action continuity','BHEL 5x, ONGC combined 4x, IOC bonuses and TATASTEEL 10x preserve the intended unit/basis relation. NTPC debt must not become equity.'],
 ['Calendar / timing','Review uses the prior signal snapshot, not current close. Missing price and same-day demerger collision raise an explicit exception.'],
 ['Cash-inclusive repurchase','Reproduce KTKBANK 2013: sell 125, buy 57, finish 189; retain both gross trades and fees.'],
 ['Rights / distributions','Rights non-participation adds no shares or cash. Declaration recognition does not make trading cash; conditional approval is visible.'],
 ['Replay / duplication','Replaying saved events reconstructs holdings, trading cash and retained distributions. Re-running an already applied review creates no duplicate live effects.'],
 ['Execution failures','A rejected or partial broker order updates only confirmed fills; stale prices and unmatched fills block subsequent automated actions.']],[143,W-143])
p('<b>Already checked in the saved research run:</b> cash, distribution and share replay; whole-share positions; nonnegative cash; 16 annual contributions; fills matching official opens. The existing explanation trace was reconciled event by event. The full S3 appendix is copied from that verified report.')
p('<b>Still required for a live implementation:</b> broker-integration tests, exchange-calendar failure handling, order idempotency, partial-fill recovery, settlement/funds checks and account reconciliation. Describing these controls does not mean they have already been built or passed.')

page('14 | Historical results and interpretation')
table(['Measure','S3 saved result'],[
 ['Total external contributions','Rs '+money(R['invested'])],['Final modeled wealth after hypothetical exit cost','Rs '+money(R['terminal_after_cost'])],['Money-weighted XIRR',f'{R["xirr_pct"]:.4f}% per year'],['Priced equity / trading cash','Rs '+money(R['equity'])+' / Rs '+money(R['cash'])],['Retained declared dividends','Rs '+money(R['dividends'])],['Retained scheduled NTPC debt income','Rs '+money(R['ntpc_income'])],['Executed trades / sale entries',f'{R["trades"]} total / {R["sells"]} sales'],['Trading costs already charged','Rs '+money(R['costs'])],['Hypothetical final exit deduction','Rs '+money(R['exit_cost'])]],[W*.55,W*.45])
story.append(WealthChart())
p('Calendar-end known wealth and cumulative contributions, Rs lakh. *2026 ends 11 September. Wealth includes external cash additions and recognized distributions; this is not a time-weighted return chart.','small')
p('XIRR uses the actual annual contribution dates as negative external flows and modeled terminal wealth as the final positive flow, with days/365 discounting. It is not a simple CAGR on Rs 16 lakh invested on day one. No benchmark-relative outperformance or drawdown conclusion is established by these figures.','small')

page('15 | Every year: closing balances')
p('Calendar-year last available observations. Values below are rounded Rs lakh, before hypothetical final exit cost. Annual external contribution is Rs 1 lakh. These are balances, not annual returns.','small')
table(['Year / as of','Contrib. total','Equity','Trading cash','Retained income','Known wealth'],[[x['date'],f'{float(x["invested"])/100000:.3f}',f'{float(x["equity"])/100000:.3f}',f'{float(x["cash"])/100000:.3f}',f'{(float(x["dividends_earned"])+float(x["ntpc_scheduled_income"]))/100000:.3f}',f'{float(x["wealth"])/100000:.3f}'] for x in YEARS],[85,75,78,77,90,W-405])
p('Known wealth = priced equity + trading cash + retained dividend declarations + scheduled NTPC income. Unpriced child entitlements, unpaid accrued debt coupons and unverified fractional proceeds are excluded. Dividend payment timing is not fully reconciled.')
p('The appendix gives exact rupee balances and stock quantities for all 16 years. A rise in wealth can reflect both investment outcomes and the new contribution; do not call the year-to-year wealth percentage change a strategy return.')

page('16 | All 15 executed sales')
sales=[]
for rv in REV:
 for x in rv['rows']:
  if x['sold']:sales.append([rv['date'],x['symbol'],str(x['before']),str(x['sold']),f'{x["sold_pct"]:.2f}%',f'{x["weight_before"]:.2f}%',money(x['received'])])
assert len(sales)==15
table(['Date','Stock','Held before','Sold','Sold %','Core W% before','Net receipt (Rs)'],sales,[72,83,48,40,55,70,W-368])
p('<b>Reason shared by every sale:</b> pre-review core weight exceeded 12.5%; the engine requested a trim toward 10% and restricted execution to shares older than 365 days. The appendix gives the measured trigger, requested quantity and eligible quantity for each stock-year.')
p('The table reports gross sale legs. A later purchase in the same review is separately preserved. Net receipts include the modeled sale cost; sold percentage uses opening share quantity, while core weight uses market value.')
p('The final exit-cost deduction is hypothetical and creates no additional sale entries. No actual liquidation of younger lots is implied by the final valuation.')

page('17 | Final holdings and cost sensitivity')
core=sum(x['value'] for x in R['holdings'][:10])
table(['Stock','Shares','Close (Rs)','Value (Rs)','Core weight'],[[x['symbol'],str(x['quantity']),money(x['close']),money(x['value']),f'{x["value"]/core*100:.2f}%' if i<10 else 'Outside core'] for i,x in enumerate(R['holdings'])],[100,65,88,135,W-388])
p('As of 11 September 2026. Core weights exclude child holdings and cash. A weight above 12.5% at this date is not a daily trigger: S3 only checks on its annual review.','small')
sens=[x for x in DATA['sensitivity'] if x['code']==3]
table(['Cost assumption per side','Final modeled wealth (Rs)','XIRR'],[['0 bps',money(sens[0]['terminal']),f'{sens[0]["xirr_pct"]:.4f}%'],['12 bps - base',money(R['terminal_after_cost']),f'{R["xirr_pct"]:.4f}%'],['25 bps',money(sens[1]['terminal']),f'{sens[1]["xirr_pct"]:.4f}%']],[160,210,W-370])
p('These saved reruns change proportional trading costs and the exit deduction. Whole-share affordability can change positions. They do not model a tax schedule, variable spreads, market impact, rights monetization or different dividend-payment timing.','small')

page('18 | Risks and limitations to consider')
table(['Issue','Practical implication'],[
 ['Fixed-basket selection','Historical inclusion criteria were not reconstructed point in time. Hindsight/selection and survivorship bias cannot be ruled out. This is not evidence that these ten stocks are the best current portfolio.'],
 ['Concentrated exposures','Ten names are not broad diversification. Several are exposed to banks, energy, commodities, industrial cycles or public-sector policy. Equal nominal weights do not equalize risk.'],
 ['Adding to a deteriorating business','S3 can repeatedly buy a falling stock because its weight shrinks. It has no verified fundamental-quality screen, stop-loss or automatic replacement rule.'],
 ['Trimming persistent winners','Selling concentration can reduce participation in prolonged outperformance. A rebalancing benefit is not guaranteed.'],
 ['Annual frequency / age block','Concentration can grow between reviews or remain high because lots are too young to sell. The 12.5% threshold is not a guaranteed risk ceiling.'],
 ['Tax and actual charges','The report is pre-tax; economic basis and >365-day eligibility are not tax advice. Verify current applicable taxation, lot treatment and broker charges separately before implementation.'],
 ['Entitlement valuation','Recognizing a conditional dividend before approval or payment can overstate readily available cash. Unpriced holdings and excluded fractional proceeds also affect comparisons.'],
 ['Execution / operational risk','Opening-price fills, immediate reuse of sales cash and uninterrupted data availability are simplifying assumptions. Poor reconciliation can create duplicate or unfunded orders.']],[143,W-143])
p('General rebalancing guidance also emphasizes transaction fees and tax consequences. This is a general investing consideration, not an Indian tax-rate source. [E2]','small')
link('E2 | Investor.gov: asset allocation, diversification and rebalancing','https://www.investor.gov/additional-resources/general-resources/publications-research/info-sheets/beginners-guide-asset')

page('19 | Changes to research before live use')
table(['Possible change','How to evaluate it fairly'],[
 ['Avoid opposing trades','Test a cash-first or net-order variant. Keep base S3 intact; compare fees, lots and future eligibility. Do not claim identical results after changing the sequence.'],
 ['Monetize or subscribe to rights','Reconstruct issue/renunciation windows and investor fractional terms. Include funding, fees, actual prices and future lots.'],
 ['Payment-based distributions','Separate confirmed cash from receivables; compare realistic payment timing and optional reinvestment as a new version.'],
 ['Alternative bands / cadence','Test prespecified bands and quarterly/annual schedules out of sample. Avoid selecting the best setting after observing all historical outcomes.'],
 ['Basket governance','Define entry, replacement, suspension and delisting rules using information available at the time. Record discretionary changes separately.'],
 ['Risk and benchmark evaluation','Compute contribution-adjusted returns, drawdowns and rolling outcomes. Compare with an appropriate investable total-return benchmark using matching cash-flow dates and costs.'],
 ['Stress execution and data','Test gaps, slippage, delayed sale funding, outages, partial fills and corporate-action collisions. Include periods before and after the development sample when available.']],[146,W-146])
box('Ready-to-operate evidence','A versioned rulebook; reconciled starting lots and funds; validated source history; passing calculation tests; paper-trading reconciliation; tested broker failure recovery; and a documented policy for rights, taxes, corporate actions and discretionary exceptions. These are acceptance conditions for future implementation, not claims that the research script is already a live system.')
p('The decision to use S3 depends on objectives, investment horizon, loss capacity and the ability to follow the process. This document supplies the strategy mechanics and evidence limitations; it does not establish suitability for a particular investor.')

page('20 | Reproduction, sources and appendix map')
p('<b>Authoritative source for exact S3 behavior:</b> research/scripts/backtest_five_verified.py, especially Book.review, Book.deploy, Book.sell and Book.event. The saved results and trace take precedence over a generic description of rebalancing.')
table(['Local evidence','Purpose'],[
 ['research/data/five_strategy_verified/results.json','Full-precision results and cost sensitivity.'],['research/data/five_strategy_verified/decision_explanations.json','All 160 S3 stock-year explanations and requested/eligible sale quantities.'],['research/data/five_strategy_verified/audit_ledgers.zip','S3 transaction/event CSV and 3,891 daily valuation observations.'],['research/data/v2_source_verification/verified/','Official raw prices, corporate-action notices and corrected per-share declarations.'],['research/scripts/test_five_verified.py','Existing focused model tests. Run in a working copy when modifying rules.'],['research/scripts/build_s3_manual.py','Rebuild this guide from saved evidence; does not rerun or alter strategy returns.']],[246,W-246])
p('<b>Reproduction:</b> python research/scripts/backtest_five_verified.py recalculates and overwrites shared result exports, so use an isolated copy for experiments. python research/scripts/explain_five_decisions.py rebuilds the decision trace. Preserve input hashes and compare all events, not only terminal wealth.','small')
for file in [B/'results.json',B/'audit_ledgers.zip',ROOT/'research/scripts/backtest_five_verified.py']:
 p(escape(file.name)+' SHA-256:<br/>'+hashlib.sha256(file.read_bytes()).hexdigest(),'small')
link('NSE: corporate-action filing portal','https://www.nseindia.com/companies-listing/corporate-filings-actions')
p('<b>Appendix:</b> the next pages reproduce S3\'s chapter from the full five-strategy report: chapter overview, allocation maps, 2011-2026 reviews, measured reasons, annual balances, complete event ledger, fractions and final reconciliation. The shared N-code note glossary follows; it may contain codes used only by other strategies. Bookmarks and footer numbers refer to this standalone PDF.','small')

def footer(c,d):
 c.setFillColor(BLUE);c.rect(44,A4[1]-27,W,3,fill=1,stroke=0)
 c.setFont('S3',7);c.setFillColor(NAVY);c.drawString(44,23,'S3 | Strategy specification and operating guide | Historical pre-tax model');c.drawRightString(A4[0]-44,23,str(d.page))
manual=WORK/'manual_only.pdf'
SimpleDocTemplate(str(manual),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=45,bottomMargin=44,title='S3 Band Rebalancing - Professional Guide and Full Ledger',author='Research strategy documentation').build(story,onFirstPage=footer,onLaterPages=footer)
with pymupdf.open(manual) as doc,pymupdf.open(SOURCE) as src:
 manual_pages=len(doc);toc=[]
 for i,pg in enumerate(doc):
  text=pg.get_text()
  for h in headings:
   if h in text:toc.append([1,h,i+1])
 assert len(toc)==len(headings),(len(toc),len(headings))
 source_toc=src.get_toc();begin=next(x[2]-1 for x in source_toc if x[1].startswith('Chapter 3 |'));end=next(x[2]-2 for x in source_toc if x[1].startswith('Chapter 4 |'))
 doc.insert_pdf(src,from_page=begin,to_page=end)
 for level,title,pno in source_toc:
  if begin<=pno-1<=end:toc.append([level,title,manual_pages+pno-begin])
 note_pages=[x[2]-1 for x in source_toc if x[1]=='Complete ledger-note appendix']
 for pn in note_pages:
  doc.insert_pdf(src,from_page=pn,to_page=pn);toc.append([1,'Appendix | Shared ledger notes',len(doc)])
 for i in range(manual_pages,len(doc)):
  pg=doc[i];h=pg.rect.height;w=pg.rect.width
  rect=pymupdf.Rect(35,h-34,w-35,h-12)
  pg.add_redact_annot(rect,fill=(1,1,1));pg.apply_redactions()
  pg.insert_text((40,h-21),'S3 | Full historical ledger appendix | Pre-tax entitlement model',fontsize=7,color=(.08,.15,.24))
  pg.insert_text((w-60,h-21),str(i+1),fontsize=7,color=(.08,.15,.24))
 doc.set_toc(toc,collapse=1)
 doc.set_metadata({'title':'S3 Band Rebalancing - Professional Guide and Full Ledger','author':'Research strategy documentation','subject':'Exact rules, implementation, evidence limitations and complete S3 annual audit'})
 doc.save(OUT,garbage=4,deflate=True)
with pymupdf.open(OUT) as d:
 full='\n'.join(pg.get_text() for pg in d)
 for j in range(1,len(LOG)+1):assert full.count(f'S3-{j:04d}')==1,(j,full.count(f'S3-{j:04d}'))
 assert sum('BUY / SELL / HOLD review' in pg.get_text() for pg in d)==16
 for pg in d[:manual_pages]:
  for block in pg.get_text('blocks'):assert block[0]>=39 and block[2]<=A4[0]-39 and block[3]<A4[1]-14,block
 report={'manual_pages':manual_pages,'total_pages':len(d),'s3_events':len(LOG),'s3_sales':len(sales),'annual_reviews':16,'source_pdf_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'output_bytes':OUT.stat().st_size,'output':str(OUT)}
 (WORK/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
