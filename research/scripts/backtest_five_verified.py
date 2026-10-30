"""Raw NSE, whole-share, pre-tax backtests; no invented dividend payment dates.

Distributions accumulate outside trading cash. Rights are deliberately allowed
to lapse. The fourth strategy is explicitly a price-rule proxy, not fundamentals.
"""
import bisect,csv,hashlib,io,json,math,zipfile
from collections import defaultdict
from datetime import date,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'research/data/v2_source_verification/verified'
OUT=ROOT/'research/data/five_strategy_verified'
SYMS='BHEL COALINDIA IOC ITC KTKBANK ONGC SCI NTPC TATASTEEL SOUTHBANK'.split()
NAMES=['S1 Equal annual buying','S2 Cash-flow rebalance','S3 Band rebalance','S4 Price-rule proxy','S5 Momentum tilt']
# date, symbol, type, factor, extra. All dates are source ex-dates.
EVENTS=[
 ('2011-02-08','ONGC','combined',4,None),
 ('2011-02-25','KTKBANK','rights',.4,85),
 ('2011-10-03','BHEL','split',5,None),
 ('2015-03-20','NTPC','debenture',1,None),
 ('2016-07-01','ITC','bonus',.5,None),
 ('2016-10-18','IOC','bonus',1,None),
 ('2016-10-24','KTKBANK','rights',.5,70),
 ('2016-12-15','ONGC','bonus',.5,None),
 ('2017-02-16','SOUTHBANK','rights',1/3,14),
 ('2017-09-28','BHEL','bonus',.5,None),
 ('2018-01-31','TATASTEEL','rights',.24,'4:25 at 510 and 2:25 partly paid at 615 total'),
 ('2018-03-15','IOC','bonus',1,None),
 ('2019-03-19','NTPC','bonus',.2,None),
 ('2020-03-17','KTKBANK','bonus',.1,None),
 ('2022-06-30','IOC','bonus',.5,None),
 ('2022-07-28','TATASTEEL','split',10,None),
 ('2023-03-31','SCI','demerger',1,('SCILAL',.4032)),
 ('2024-02-27','SOUTHBANK','rights',.25,22),
 ('2025-01-06','ITC','demerger',.1,('ITCHOTELS',.1351)),
]

def rows(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def irr(flows):
 t=flows[0][0]
 def npv(r):return sum(v/(1+r)**((d-t).days/365) for d,v in flows)
 lo,hi=-.999,10
 assert npv(lo)*npv(hi)<0
 for _ in range(150):
  mid=(lo+hi)/2
  if npv(mid)>0:lo=mid
  else:hi=mid
 return (lo+hi)/2*100

class Data:
 def __init__(self):
  self.p=defaultdict(dict)
  source=rows(BASE/'official_daily_prices.csv')
  assert len(source)==39928
  for r in source:
   d=date.fromisoformat(r['date']);s=r['symbol']
   assert s not in self.p[d]
   self.p[d][s]={k:float(r[k]) for k in ['open','close']}
  self.days=sorted(d for d,p in self.p.items() if all(s in p for s in SYMS))
  assert len(self.days)==3891 and str(self.days[-1])=='2026-09-11'
  self.events=defaultdict(list)
  for ds,s,k,f,x in EVENTS:self.events[date.fromisoformat(ds)].append((s,k,f,x))
  for r in rows(BASE/'nse_corporate_actions_verified_source.csv'):
   if r['kind']=='buyback':self.events[date.fromisoformat(r['ex_date'])].append((r['symbol'],'buyback',0,None))
  self.divs=defaultdict(list)
  for r in rows(BASE/'declared_dividends.csv'):
   self.divs[date.fromisoformat(r['ex_date'])].append((r['symbol'],float(r['declared_rupees_per_share'])))
  extra=ROOT/'research/data/v2_source_verification/five_strategy_extra'
  self.extra_actions=[]
  for e in json.loads((extra/'issuer_dividends.json').read_text()):
   d=date.fromisoformat(e['recognition_date']);s=e['symbol'];amount=e['amount']
   self.divs[d].append((s,amount));self.extra_actions.append(e)
  self.review={}
  for y in range(2011,2027):
   i=bisect.bisect_left(self.days,date(y,1,3))
   if i<len(self.days):self.review[self.days[i]]=y
  # Forward share-adjusted price index. Uses no future event information.
  factors={s:1 for s in SYMS};self.signal={}
  for d in self.days:
   for s,k,f,x in self.events[d]:
    if k in ['split','combined']:factors[s]*=f
    if k=='bonus':factors[s]*=1+f
   self.signal[d]={s:self.p[d][s]['close']*factors[s] for s in SYMS}
 def trailing(self,s,d,years):
  i=bisect.bisect_right(self.days,d-timedelta(days=365*years))-1
  if i<0:return None
  return (self.signal[d][s]/self.signal[self.days[i]][s])**(1/years)-1

class Book:
 def __init__(self,data,code,cost_bps=12):
  self.data=data;self.code=code;self.rate=cost_bps/10000
  self.lots=defaultdict(list);self.cash=0.;self.distributions=0.;self.costs=0.;self.invested=0.
  self.logs=[];self.annual=[];self.daily=[];self.flows=[];self.ntpc_units=0;self.ntpc_income=0.;self.last={};self.fractions=[]
 def qty(self,s):return sum(l['q'] for l in self.lots[s])
 def basis(self,s):return sum(l['basis'] for l in self.lots[s])
 def log(self,d,s,kind,q=0,price=0,cash=0,earned=0,note=''):
  self.logs.append(dict(strategy=self.code,date=str(d),symbol=s,event=kind,quantity=q,price=price,cash_change=cash,earned_change=earned,note=note))
 def buy(self,s,budget,p,d,note):
  q=math.floor((min(budget,self.cash)+1e-8)/(p*(1+self.rate)))
  if q<=0:return
  cost=q*p*self.rate;spent=q*p+cost
  self.cash-=spent;self.costs+=cost
  self.lots[s].append(dict(q=q,basis=q*p,bought=d))
  self.log(d,s,'BUY',q,p,-spent,note=note)
 def sell(self,s,wanted,p,d,note):
  available=sum(l['q'] for l in self.lots[s] if (d-l['bought']).days>365)
  qty=min(wanted,available);left=qty
  if qty<=0:return
  for l in self.lots[s]:
   if (d-l['bought']).days<=365:continue
   take=min(left,l['q']);l['basis']*=1-take/l['q'];l['q']-=take;left-=take
   if left==0:break
  self.lots[s]=[l for l in self.lots[s] if l['q']]
  gross=qty*p;cost=gross*self.rate;self.cash+=gross-cost;self.costs+=cost
  self.log(d,s,'SELL',qty,p,gross-cost,note=note)
 def event(self,d,s,k,f,x):
  qty=self.qty(s)
  if not qty:return
  if k=='split':
   for l in self.lots[s]:l['q']*=int(f)
   self.log(d,s,'SPLIT',qty*(f-1),note=str(f)+'x units; total economic basis unchanged')
  elif k in ['bonus','combined']:
   # Combined ONGC: split doubles original lots, then 1:1 bonus.
   if k=='combined':
    for l in self.lots[s]:l['q']*=2
    self.log(d,s,'SPLIT',qty,note='ONGC face value 10 to 5')
    qty*=2;f=1
   exact=qty*f;new=math.floor(exact+1e-9);fraction=exact-new
   oldbasis=self.basis(s);newbasis=oldbasis*new/(qty+new)
   for l in self.lots[s]:l['basis']*=qty/(qty+new)
   if new:self.lots[s].append(dict(q=new,basis=newbasis,bought=d))
   self.log(d,s,'BONUS',new,note='Economic basis allocated; bonus maturity starts on ex-date')
   if fraction>1e-8:self.fractions.append(dict(date=str(d),symbol=s,quantity=fraction,reason='Unverified fractional proceeds excluded'))
  elif k=='demerger':
   child,allocation=x;new=math.floor(qty*f+1e-9);newbasis=self.basis(s)*allocation
   for l in self.lots[s]:l['basis']*=1-allocation
   if new:self.lots[child].append(dict(q=new,basis=newbasis,bought=d))
   self.log(d,child,'DEMERGER',new,note=f'{s} entitlement retained; no fresh investment; not sold')
   frac=qty*f-new
   if frac>1e-8:self.fractions.append(dict(date=str(d),symbol=child,quantity=frac,reason='Unverified fractional proceeds excluded'))
  elif k=='rights':self.log(d,s,'RIGHTS_LAPSE',qty*f,note='No subscription, renunciation or invented proceeds; terms '+str(x))
  elif k=='buyback':self.log(d,s,'BUYBACK_NOT_TENDERED',qty,note='No participation; no automatic cash receipt')
  elif k=='debenture':
   self.ntpc_units=qty
   self.log(d,s,'DEBENTURE_ENTITLEMENT',qty,note='One Rs12.50 bonus debenture per eligible share; excluded from trade cash')
 def equity(self,p,core=False):return sum(self.qty(s)*p.get(s,0) for s in (SYMS if core else self.lots))
 def deploy(self,candidates,target,decision,fill,d):
  total=self.equity(decision,True)+self.cash
  gaps=sorted([(total*target-self.qty(s)*decision[s],s) for s in candidates],reverse=True)
  for gap,s in gaps:
   if gap>0:self.buy(s,gap,fill[s],d,'underweight top-up')
  for _ in range(3):
   affordable=[s for s in candidates if self.cash>=fill[s]*(1+self.rate)]
   if not affordable:break
   portion=self.cash/len(affordable)
   for s in affordable:self.buy(s,portion,fill[s],d,'residual sweep')
 def review(self,d,prev):
  fill={s:self.data.p[d][s]['open'] for s in SYMS}
  dec={s:self.data.p[prev][s]['close'] for s in SYMS} if prev else fill.copy()
  # For an ex-date review, translate previous prices onto the current unit basis.
  for s,k,f,x in self.data.events[d]:
   if k in ['split','combined']:dec[s]/=f
   elif k=='bonus':dec[s]/=1+f
   elif k=='demerger':raise ValueError('An ex-demerger review requires an explicit pre-event decision snapshot')
  self.cash+=100000;self.invested+=100000;self.flows.append((d,-100000));self.log(d,'CASH','CONTRIBUTION',cash=100000)
  first=self.invested==100000
  if first or self.code in [1,5]:
   candidates=SYMS[:]
   if self.code==5 and not first:
    candidates=sorted(SYMS,key=lambda s:(self.data.trailing(s,prev,1) if self.data.trailing(s,prev,1) is not None else -999),reverse=True)[:3]
   per=self.cash/len(candidates)
   for s in candidates:self.buy(s,per,fill[s],d,'equal allocation' if len(candidates)==10 else '12-month price momentum')
   self.deploy(candidates,1/len(candidates),dec,fill,d)
  elif self.code==2:self.deploy(SYMS,.1,dec,fill,d)
  elif self.code==3:
   total=self.equity(dec,True)
   for s in SYMS:
    if total and self.qty(s)*dec[s]/total>.125:
     self.sell(s,math.floor((self.qty(s)*dec[s]-.1*total)/dec[s]),fill[s],d,'weight >12.5%; trim toward 10%')
   self.deploy(SYMS,.1,dec,fill,d)
  elif self.code==4:
   total=self.equity(dec,True);blocked=set()
   for s in SYMS:
    cagr=self.data.trailing(s,prev,5);basis=self.basis(s);q=self.qty(s)
    ret=q*dec[s]/basis-1 if basis else 0
    if cagr is not None and cagr<0 and q:
     self.sell(s,q,fill[s],d,'negative 5-year split/bonus price CAGR');blocked.add(s)
    elif ret>1 and total and q*dec[s]/total>.1:
     self.sell(s,math.floor((q*dec[s]-.1*total)/dec[s]),fill[s],d,'gain >100%; trim overweight')
   adds=[s for s in SYMS if s not in blocked and (not self.basis(s) or self.qty(s)*dec[s]/self.basis(s)>=.9)]
   if not adds:adds=[s for s in SYMS if s not in blocked] or SYMS[:]
   adds.sort(key=lambda s:self.data.trailing(s,prev,1) or 0)
   self.deploy(adds,1/len(adds),dec,fill,d)
  assert self.cash>=-1e-6
 def run(self):
  days=self.data.days;previous=None
  # Iterate calendar dates too: cash entitlements can fall on non-trading dates.
  d=days[0]
  while d<=days[-1]:
   for s,amount in self.data.divs[d]:
    earned=self.qty(s)*amount
    if earned:self.distributions+=earned;self.log(d,s,'DIVIDEND_EARNED',self.qty(s),amount,earned=earned,note=('Issuer recognition date; see issuer_dividends.json' if s not in SYMS else 'NSE ex-date declared entitlement')+'; not payment date; not reinvested; pending declarations conditional')
   for s,k,f,x in self.data.events[d]:self.event(d,s,k,f,x)
   if self.ntpc_units and d.month==3 and d.day==25 and 2016<=d.year<=2025:
    principal=12.5 if d.year<=2023 else 10 if d.year==2024 else 5
    redemption=2.5 if d.year==2023 else 5 if d.year>=2024 else 0
    earned=self.ntpc_units*(principal*.0849+redemption)
    self.ntpc_income+=earned
    self.log(d,'NTPC_NCD','SCHEDULED_DEBT_INCOME',self.ntpc_units,earned=earned,note='Issuer schedule; retained outside trading cash; coupon plus principal')
   if d in self.data.p:
    self.last.update({s:r['close'] for s,r in self.data.p[d].items()})
   if d in self.data.review:self.review(d,previous)
   if d in self.data.days:
    equity=self.equity(self.last);wealth=equity+self.cash+self.distributions+self.ntpc_income
    unpriced=[s for s in self.lots if self.qty(s) and s not in self.last]
    row=dict(date=str(d),invested=self.invested,equity=equity,cash=self.cash,dividends_earned=self.distributions,ntpc_scheduled_income=self.ntpc_income,wealth=wealth,unpriced_entitlements=','.join(unpriced))
    self.daily.append(row)
    if d in self.data.review:self.annual.append(dict(row,holdings={s:self.qty(s) for s in SYMS+['ITCHOTELS','SCILAL']}))
    previous=d
   d+=timedelta(days=1)
  end=days[-1];equity=self.equity(self.last);wealth=equity+self.cash+self.distributions+self.ntpc_income
  exitcost=equity*self.rate;terminal=wealth-exitcost
  assert abs(self.cash-sum(x['cash_change'] for x in self.logs))<.0001
  assert abs(self.distributions+self.ntpc_income-sum(x['earned_change'] for x in self.logs))<.0001
  assert all(l['q']==int(l['q']) and l['q']>=0 and l['basis']>=-1e-8 for ls in self.lots.values() for l in ls)
  assert self.invested==1600000 and len(self.annual)==16
  # Independent quantity reconstruction from event/trade audit trail.
  qty=defaultdict(float)
  for t in self.logs:
   if t['event'] in ['BUY','SPLIT','BONUS','DEMERGER']:qty[t['symbol']]+=t['quantity']
   if t['event']=='SELL':qty[t['symbol']]-=t['quantity']
  assert all(abs(qty[s]-self.qty(s))<1e-8 for s in self.lots)
  trades=[x for x in self.logs if x['event'] in ['BUY','SELL']]
  for t in trades:assert t['price']==self.data.p[date.fromisoformat(t['date'])][t['symbol']]['open']
  return dict(code=self.code,name=NAMES[self.code-1],invested=self.invested,equity=equity,cash=self.cash,dividends=self.distributions,ntpc_income=self.ntpc_income,wealth=wealth,exit_cost=exitcost,terminal_after_cost=terminal,xirr_pct=irr(self.flows+[(end,terminal)]),costs=self.costs,trades=len(trades),sells=sum(t['event']=='SELL' for t in trades),annual=self.annual,holdings=[dict(symbol=s,quantity=self.qty(s),close=self.last.get(s,0),value=self.qty(s)*self.last.get(s,0)) for s in SYMS+['ITCHOTELS','SCILAL']],fractions=self.fractions)

def csvtext(items):
 f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items);return f.getvalue()

def main():
 OUT.mkdir(exist_ok=True)
 data=Data();results=[];books=[]
 for code in range(1,6):
  b=Book(data,code);r=b.run();results.append(r);books.append(b)
  print(r['name'],round(r['terminal_after_cost'],2),round(r['xirr_pct'],4),flush=True)
 sensitivity=[]
 for bps in [0,25]:
  for code in range(1,6):
   r=Book(data,code,bps).run();sensitivity.append(dict(cost_bps=bps,code=code,terminal=r['terminal_after_cost'],xirr_pct=r['xirr_pct']))
  source_files=[BASE/'official_daily_prices.csv',BASE/'declared_dividends.csv',BASE/'nse_corporate_actions_verified_source.csv',ROOT/'research/data/v2_source_verification/five_strategy_extra/issuer_dividends.json',Path(__file__)]
 payload=dict(start=str(data.days[0]),end=str(data.days[-1]),sessions=len(data.days),cost_bps=12,results=results,sensitivity=sensitivity,spinoff_dividends=data.extra_actions,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},checks=['Cash ledger reconciles','Distribution ledger reconciles','Share quantities independently replayed','All fills equal official NSE opens','No negative cash or short positions','16 contributions per strategy','Integer share positions'])
 (OUT/'results.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
 with zipfile.ZipFile(OUT/'audit_ledgers.zip','w',zipfile.ZIP_DEFLATED) as z:
  for b in books:
   z.writestr(f'S{b.code}_transactions_and_events.csv',csvtext(b.logs))
   z.writestr(f'S{b.code}_daily_wealth.csv',csvtext(b.daily))
 print('Saved',OUT,flush=True)

if __name__=='__main__':main()
