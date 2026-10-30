"""Auditable introductory pages for the five-strategy ledger."""
import csv,json,math
from collections import Counter
from xml.sax.saxutils import escape

def add_introduction(root,p,table,new):
 base=root/'research/data/v2_source_verification/verified'
 def read(name):
  with (base/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
 actions=read('nse_corporate_actions_verified_source.csv')
 divs=read('declared_dividends.csv')
 amounts={(x['symbol'],x['ex_date'],x['source_text']):x['declared_rupees_per_share'] for x in divs}
 assert len(actions)==303 and len(divs)==252
 ids=[]
 def page(title):new();p('Introduction | '+title,'title')
 def link(label,url):p('<link href="'+escape(url,{'"':'&quot;'})+'" color="#1f4f8f">'+escape(label)+'</link>','small')
 page('What actually happened to your shares')
 p('Corporate actions explained | Ten original stocks and two demerged holdings | Evidence cutoff: 11 September 2026')
 p('This introduction separates company announcements, shareholder choices and backtest accounting. A dividend is a cash distribution; a split or equity bonus changes share units; a rights issue offers additional shares for payment. They must not all be treated as investment returns or as automatic cash receipts.')
 counts=Counter(x['kind'] for x in actions)
 pre=sum(x['ex_date']<'2011-01-03' for x in actions)
 table(['Register coverage','What is included'],[
  ['303 saved NSE notices',f'{303-pre} within the backtest window; {pre} before 3 January 2011, explicitly labeled PRE-START. All saved notices are listed once, including meeting notices.'],
  ['252 declared dividend records','Per-share amounts joined to the corrected dividend source by stock, ex-date and exact source wording. Amounts are on the share basis that existed at the time.'],
  ['Other notice types',', '.join(f'{k.replace("_"," ")}: {v}' for k,v in counts.items() if k!='dividend')],
  ['Two retained demerged stocks','Four additional issuer dividend records for SCILAL and ITCHOTELS appear separately with their precise date basis and approval status.'],
  ['Verification limit','This is the complete saved source register, not a claim that every possible issuer event or payment has been independently reconciled. Missing payment days, rights deadlines and investor-specific fractional proceeds remain unverified.']],[180,582])
 p('<b>Why companies do these things:</b> the following pages explain the general purpose and mechanics. An individual board\'s commercial motive is not inferred from a price chart or a short exchange notice. Where the source only names an action, the company-specific reason remains unstated.')
 p('<b>Reading order:</b> dates and dividends; share changes; rights and lapse; demergers and NTPC debt; all ten company event registers; issuer additions and sources; then Chapters 1-5 with the unchanged annual decisions and full ledgers.')
 page('Dividends | When, why and how much')
 table(['Question','Plain-language explanation'],[
  ['Why pay a dividend?','A company distributes cash to eligible shareholders, commonly from distributable profits or reserves. A particular payout can be interim, final or special. The register preserves these labels where the notice supplies them; it does not invent a board rationale.'],
  ['How much do I receive?','Gross entitlement = eligible shares x declared rupees per share. Example: 100 eligible shares x Rs 5 = Rs 500 gross. Actual bank credit can differ because of tax withholding. This report is pre-tax.'],
  ['What does dividend percentage mean?','If a notice states a percentage of face value, that is not the yield on the market price. Example: 100% of Rs 2 face value is Rs 2 per share. The register gives rupees per share, not an assumed investment return.'],
  ['Interim / final / special','Interim distributions are declared during the year; a recommended final dividend may still require shareholder approval. Special describes an additional or exceptional distribution, not a guaranteed recurring payment.'],
  ['Ex-date','The market eligibility boundary for the action. Buying on the ex-date normally does not carry that entitlement. It is not the bank-payment date or necessarily the meeting date.'],
  ['Record date','The date used to identify eligible registered holders. It can differ from the ex-date. A dash in the register means the saved notice did not supply the date.'],
  ['Declaration / approval / payment','These are separate milestones. A recommendation is not an approved cash payment. No core-stock payment date is filled in without evidence. The backtest recognizes declarations at eligibility dates and retains them outside trading cash.']],[175,587])
 p('<b>Do not double-count:</b> ITC\'s 30 May 2016 amount is Rs 8.50, including its Rs 2 special component, not Rs 10.50. SOUTHBANK\'s 3 July 2017 amount is Rs 0.40. These are the corrected amounts used in the existing ledger.','small')
 page('Splits and bonuses | Shares change, value is not created')
 table(['Type','Example from this basket','What changes in the model'],[
  ['Split','BHEL, 3 Oct 2011: face value Rs 10 to Rs 2. One old share becomes five; 100 become 500.','Multiply shares by 5 and divide per-share economic cost by 5. This changes unit size, not proportional ownership by itself.'],
  ['Equity bonus','IOC, 30 Jun 2022: 1:2. One additional share for every two held; 100 become 150.','Add 50% shares before whole-share/fraction treatment. Bonus shares capitalize reserves; no shareholder subscription cash is paid.'],
  ['Combined split + bonus','ONGC, 8 Feb 2011: split Rs 10 to Rs 5 and 1:1 bonus. Combined multiplier is 4; 100 become 400.','Apply both changes once. Applying only a 2x multiplier would undercount shares.'],
  ['Further share changes','IOC bonuses in 2016 and 2018 each double units; its 2022 bonus adds 50%. TATASTEEL split in 2022 multiplies units by 10.','Adjust holding quantities and price-signal continuity explicitly. Execute using raw NSE prices, not dividend-adjusted prices.'],
  ['Fractional units','A 1:2 bonus on an odd holding can produce a fractional entitlement.','Hold whole shares and record fractions separately. Do not fabricate cash-in-lieu amounts or payment dates.']],[125,320,317])
 p('<b>Why do it?</b> A split reduces the nominal size of each share; an equity bonus capitalizes reserves into share capital. Companies may discuss liquidity or accessibility, but the saved short notices do not establish each issuer\'s motive. More units alone do not mean more economic wealth: market prices reflect the changed unit basis and other trading forces.')
 p('<b>Dividend amounts are not rescaled here:</b> an old Rs 10 dividend remains Rs 10 per then-existing eligible share. The model multiplies it by shares held at that time, after applicable earlier actions. Simply adding old and new per-share dividends can mislead when the share count changed.')
 page('Rights issues | Why rights lapsed in this backtest')
 p('A rights issue offers existing holders additional shares in a specified ratio for a subscription price. It can raise company capital; the specific use of proceeds must come from its offer document. A rights entitlement is an opportunity to subscribe, not an automatically paid-up share.')
 table(['NSE ex-date','Company / offered ratio','Price per new share','Backtest decision'],[
  ['2011-02-25','KTKBANK: 2 for every 5','Rs 85 = Rs 10 face + Rs 75 premium','No subscription; no renunciation proceeds.'],
  ['2016-10-24','KTKBANK: 1 for every 2','Rs 70 = Rs 10 face + Rs 60 premium','No subscription; no renunciation proceeds.'],
  ['2017-02-16','SOUTHBANK: 1 for every 3','Rs 14 = Rs 1 face + Rs 13 premium','No subscription; no renunciation proceeds.'],
  ['2018-01-31','TATASTEEL: 4 fully paid + 2 partly paid for every 25','Fully paid: Rs 510. Partly paid: Rs 615 total issue price; not all necessarily due initially.','Both offers lapse in model. Partly-paid call schedule not reconciled.'],
  ['2024-02-27','SOUTHBANK: 1 for every 4','Rs 22 = Rs 1 face + Rs 21 premium','No subscription; no renunciation proceeds.']],[80,210,252,220])
 p('<b>Concrete example:</b> 100 eligible SOUTHBANK shares in the 2024 issue offer 25 new shares. Subscribing at Rs 22 would require Rs 550, excluding any applicable costs. This backtest spends Rs 0, adds 0 rights shares and receives Rs 0 from selling rights. The original 100 shares are not cancelled.')
 p('<b>Why lapse?</b> All five strategies preserve the existing assumption of no rights subscription and no sale/renunciation of rights. Unused rights expire after the issue closes. This can forgo value and allow percentage ownership to be diluted; it is a modeling choice, not evidence that the issuer cancelled the offer or that lapse was optimal.')
 p('<b>When exactly?</b> Ex-dates above establish event eligibility. Actual issue-opening, last-renunciation and subscription-closing dates were not reconciled in the saved dataset. Ledger entries placed on ex-dates describe the intended non-participation, not proof that legal expiry occurred on that day. Historical renunciation arrangements must be checked in each offer document.','small')
 link('Source: NSE FAQ - rights entitlement, subscription, renunciation and expiry','https://www.nseindia.com/static/trade/members-faqs-rights-entitlement-trading')
 page('Demergers, buybacks and meeting notices')
 table(['Event','What actually happened / economic meaning','How the backtest handles it'],[
  ['ITC / ITCHOTELS','6 Jan 2025: eligible ITC holders receive 1 ITCHOTELS share for every 10 ITC shares under the demerger. The businesses become separately held securities.','Retain whole child shares without buying more. Economic cost allocation: 86.49% ITC / 13.51% ITCHOTELS.'],
  ['SCI / SCILAL','31 Mar 2023 eligibility; 6 Apr 2023 allotment: 1 SCILAL share per SCI share. SCILAL first listed on 19 Mar 2024.','Retain child shares. Economic cost allocation: 59.68% SCI / 40.32% SCILAL. No invented pre-listing market price.'],
  ['Fractional ITCHOTELS proceeds','The issuer reports that consolidated fractional entitlements were sold and net proceeds distributed. This is a real corporate process.','Individual amounts and dates for modeled holdings remain unreconciled, so no cash-in-lieu is included. Exclusion is not a claim that the issuer never paid.'],
  ['Buyback','A company offers to repurchase its shares under its announced terms. A notice alone does not prove that this portfolio tendered shares or received consideration.','No tender participation and no automatic share reduction or cash receipt. All six saved notices remain in the register.'],
  ['AGM / EGM notice','Shareholder meeting or related eligibility/book-closure notice. The recorded NSE ex-date must not be called the actual meeting date without checking the meeting notice.','No automatic distribution or share change from a meeting-only notice. A separately recorded dividend is handled on its own terms.']],[145,320,297])
 p('A demerger redistributes business ownership; child shares are not free additional economic value independent of the parent. Issuer scheme documents establish the arrangement. This introduction does not assign an unverified strategic motive to either company.','small')
 link('ITC Hotels: dividend and fractional-entitlement status','https://www.itchotels.com/dividend-iepf')
 link('SCI: issuer cost allocation communication','https://www.shipindia.com/upload/investorsubpage/IntimationtoShareholdersforCostsplitFinalSigned.pdf')
 page('NTPC bonus debentures | Debt, coupons and repayment')
 p('The 20 March 2015 eligibility event was a 1:1 bonus debenture distribution, not an equity bonus. Each eligible NTPC equity share generated one debt instrument with Rs 12.50 face value and an 8.49% annual coupon. Issue date: 25 March 2015. Equity share quantities do not increase from this debt event.')
 table(['Scheduled date / period','Per debenture amount (Rs)','What it means'],[
  ['25 March 2016 through 25 March 2022, annually','Coupon 1.06125 each year','12.50 x 8.49%; scheduled interest, kept outside trading cash.'],
  ['25 March 2023','Coupon 1.06125 + principal 2.50','Principal after repayment becomes Rs 10.00. Principal repayment returns debt capital; it is not an extra dividend.'],
  ['25 March 2024','Coupon 0.84900 + principal 5.00','Coupon is based on Rs 10 outstanding; remaining principal becomes Rs 5.00.'],
  ['25 March 2025','Coupon 0.42450 + principal 5.00','Coupon is based on Rs 5 outstanding; scheduled principal becomes zero.'],
  ['19 March 2019 equity bonus','1 new equity share for every 5 held','A separate equity event. Unlike the 2015 debt distribution, it increases NTPC equity shares by 20% before fraction handling.']],[230,200,332])
 p('<b>Example:</b> 100 eligible shares at the 2015 event create 100 debentures with Rs 1,250 original principal. A full-year coupon on that original principal is Rs 106.125 before tax. Later coupon bases fall as principal is repaid.')
 p('<b>Evidence versus accounting:</b> the dates and amounts above are the schedule used in the existing model, not investor-bank-credit verification. The outstanding debt is tracked nominally and excluded from known market wealth until scheduled income is recognized. The report does not invent a traded debenture market price.')
 link('NTPC annual report 2019-20: historical debenture terms','https://www.ntpc.co.in/sites/default/files/inline-files/LettertoSE44thNTPCAR201920.pdf')
 link('NTPC annual report 2024-25: issuer reporting','https://www.ntpc.co.in/sites/default/files/inline-files/NTPC%20AR%202024-25.pdf')
 syms='BHEL COALINDIA IOC ITC KTKBANK ONGC SCI NTPC TATASTEEL SOUTHBANK'.split()
 treatments={'bonus':'Equity units increase by stated ratio; fractions separate.','split':'Equity units change by face-value ratio; cost per unit adjusts.','bonus+split':'Apply both once: combined 4x equity units.','bonus_debenture':'Debt entitlement; no equity units added. See NTPC schedule.','demerger':'Retain child shares; see demerger explanation.','rights':'No subscription or renunciation; model lapse, not ex-day legal expiry.','buyback':'No tender; no automatic portfolio cash/share change.','other':'Meeting notice only; no automatic cash/share change.'}
 for sym in syms:
  aa=sorted([x for x in actions if x['symbol']==sym],key=lambda x:(x['ex_date'],x['kind'],x['source_text']))
  for start in range(0,len(aa),8):
   page(f'{sym} | Dated event register {start//8+1}/{math.ceil(len(aa)/8)}')
   p('NSE ex-dates and record dates are different from payment, allotment, meeting or issue-closing dates. Rs/share is the declared gross amount on the then-existing share basis. PRE-START events do not create backtest entitlements.','small')
   rows=[]
   for x in aa[start:start+8]:
    ident=f'CA{len(ids)+1:03d}';ids.append(ident)
    key=(sym,x['ex_date'],x['source_text'])
    amt=f"Rs {float(amounts[key]):.2f}/share" if x['kind']=='dividend' else '-'
    treatment='Gross declaration retained; exact payment date unverified.' if x['kind']=='dividend' else treatments[x['kind']]
    if x['ex_date']<'2011-01-03':treatment='PRE-START: historical context only. No model entitlement.'
    rows.append([ident,x['ex_date'],x['record_date'] if x['record_date'] not in ('','-','None') else '-',x['kind'].replace('_',' ').upper(),amt,x['source_text'],treatment])
   table(['ID','Ex-date','Record date','Event','Declared amount','Saved exchange terms','Effect / status'],rows,[44,69,76,92,88,197,196])
   p(f'Source: {aa[0]["source_file"]}; saved NSE response, requested coverage 1 January 2010 to 11 September 2026. A missing year means no notice in this saved register, not proof that no event occurred.','small')
   link(f'{sym}: original NSE corporate-action query',aa[0]['source_url'])
 page('Demerged holdings | Additional dividend evidence')
 extra=json.loads((root/'research/data/v2_source_verification/five_strategy_extra/issuer_dividends.json').read_text())
 assert len(extra)==4
 for i,x in enumerate(extra,1):
  table(['ID / stock','Date used by model','Rs per share','Exact date basis and status'],[[f'IS{i:03d} / {x["symbol"]}',x['recognition_date'],f'{x["amount"]:.2f}',x['date_basis']]],[115,115,92,440])
  link(f'IS{i:03d} issuer evidence',x['source_url'])
 p('<b>As of the cutoff:</b> SCILAL\'s 2026 Rs 0.55 is conditional, with AGM approval still pending on 21 September 2026. The saved model includes a conditional entitlement; it must not be described as received cash. ITCHOTELS confirms its Rs 1 final dividend was approved on 6 August 2026 and paid to eligible holders, but an exact payment day is not modeled.','small')
 p('SCILAL 2026 record-date support was saved from a secondary announcement mirror, not independently reconciled to the issuer notice here. Its issuer board filing supports the recommended amount. Earlier SCILAL recognition dates have the distinct bases shown above; they are not substituted ex-dates.','small')
 if extra[-1].get('record_date_source'):link('SCILAL 2026 record-date support: secondary announcement mirror',extra[-1]['record_date_source'])
 page('Sources, omissions and how to audit an event')
 p(f'The event register prints all {len(ids)} saved NSE notices exactly once. Its 252 dividend amounts come from the corrected declared-dividends table. Four issuer additions are listed separately. The raw strategy ledger can have many rows for a single company action because each strategy holds a different quantity; it is not a second company announcement.')
 table(['To verify','Use this evidence / interpretation'],[
  ['Dividend amount and eligibility','Match stock + ex-date + exact notice wording between nse_corporate_actions_verified_source.csv and declared_dividends.csv in research/data/v2_source_verification/verified/.'],
  ['Actual receipt','A dividend declaration or ex-date does not prove a payment. Bank/depository or issuer payment evidence is needed. Exact core-stock payment dates remain blank in the source.'],
  ['Rights terms and expiry','Check the relevant letter of offer for eligibility, issue price, application/call schedule, renunciation terms and closing date. The saved action row alone is insufficient for a legal expiry date.'],
  ['Company-specific why','Check board disclosures, offer-document objects and scheme rationale. Generic mechanics in this introduction are not claimed to be the board\'s stated motivation.'],
  ['Price / return audit','Official NSE end-of-day data ends 11 September 2026. These are historical observations, not live streaming quotes. All five previously reconciled model results are unchanged by this editorial addition.'],
  ['Other events and remaining gaps','All saved meeting notices are shown. Absence of a notice is not proof of absence of every possible event. Unverified payment timing, rights proceeds, fractional proceeds and taxes are not invented.']],[180,582])
 link('NSE corporate-action filing portal','https://www.nseindia.com/companies-listing/corporate-filings-actions')
 link('ITC: hotels demerger documents','https://itcportal.com/investors/proposed-demerger-hotels-business.html')
 link('Tata Steel: issuer split announcement','https://www.tatasteel.com/newsroom/press-releases/india/2022/tata-steel-stock-split-of-equity-shares/')
 return ids
