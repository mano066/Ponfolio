"""Trace unchanged strategy execution; reconcile every event to saved ledgers."""
import csv,io,json,zipfile
from collections import defaultdict
from backtest_five_verified import Book,Data,SYMS,OUT

def pc(v):return 'unavailable' if v is None else f'{100*v:.2f}%'
class ExplainedBook(Book):
 def __init__(self,*args):
  super().__init__(*args);self.reviews=[];self.trace=None
 def buy(self,s,budget,p,d,note):
  before=self.qty(s);cash=self.cash
  super().buy(s,budget,p,d,note)
  if self.trace is not None:self.trace['buys'].append(dict(symbol=s,budget=budget,cash=cash,qty=self.qty(s)-before,note=note))
 def sell(self,s,wanted,p,d,note):
  before=self.qty(s);eligible=sum(l['q'] for l in self.lots[s] if (d-l['bought']).days>365)
  super().sell(s,wanted,p,d,note)
  if self.trace is not None:self.trace['sales'].append(dict(symbol=s,wanted=wanted,eligible=eligible,qty=before-self.qty(s),held=before,note=note))
 def deploy(self,candidates,target,decision,fill,d):
  if self.trace is not None:
   total=self.equity(decision,True)+self.cash
   self.trace['deploy']=dict(candidates=list(candidates),target=target,gaps={s:total*target-self.qty(s)*decision[s] for s in candidates})
  super().deploy(candidates,target,decision,fill,d)
 def review(self,d,prev):
  ref={s:self.data.p[prev][s]['close'] if prev else self.data.p[d][s]['open'] for s in SYMS}
  before={s:self.qty(s) for s in SYMS};total=sum(before[s]*ref[s] for s in SYMS)
  cagr={s:self.data.trailing(s,prev,5) if prev else None for s in SYMS}
  mom={s:self.data.trailing(s,prev,1) if prev else None for s in SYMS}
  ret={s:before[s]*ref[s]/self.basis(s)-1 if self.basis(s) else None for s in SYMS}
  rank=sorted(SYMS,key=lambda s:mom[s] if mom[s] is not None else -999,reverse=True)
  self.trace=dict(buys=[],sales=[]);cashbefore=self.cash;mark=len(self.logs)
  super().review(d,prev)
  trace=self.trace;self.trace=None
  trades=self.logs[mark:];aftertotal=sum(self.qty(s)*self.data.p[d][s]['close'] for s in SYMS);result=[]
  for s in SYMS:
   b=[x for x in trace['buys'] if x['symbol']==s];sales=[x for x in trace['sales'] if x['symbol']==s]
   bought=sum(x['qty'] for x in b);sold=sum(x['qty'] for x in sales);after=self.qty(s)
   action='BUY+SELL' if bought and sold else 'SELL / EXIT' if sold and after==0 else 'SELL / TRIM' if sold else 'BUY / ADD' if bought and before[s] else 'BUY' if bought else 'HOLD' if before[s] else 'NO POSITION'
   weight=before[s]*ref[s]/total if total else 0;wa=after*self.data.p[d][s]['close']/aftertotal
   reasons=[]
   if sales:
    for x in sales:
     if self.code==3:trigger=f'Weight {pc(weight)} exceeded 12.50%; trim toward 10%.'
     elif 'negative 5-year' in x['note']:trigger=f'Five-year price CAGR {pc(cagr[s])} was negative; request an exit.'
     else:trigger=f'Economic-cost gain {pc(ret[s])} exceeded 100% and weight {pc(weight)} exceeded 10%; trim.'
     reasons.append(trigger+f" Requested {x['wanted']} shares; {x['eligible']} eligible (>365 days); sold {x['qty']}.")
     if x['qty']<x['wanted']:reasons.append('The maturity limit prevented the full requested sale.')
   elif self.code in [1,2,5]:reasons.append('No sale: this strategy never sells.')
   elif not before[s]:reasons.append('No sale: no opening position.')
   elif self.code==3:reasons.append(f'No sale: weight {pc(weight)} did not exceed 12.50%.')
   else:reasons.append(f'No sale trigger: five-year CAGR {pc(cagr[s])}; economic gain {pc(ret[s])}; weight {pc(weight)}.')
   actualnotes=list(dict.fromkeys(x['note'] for x in b if x['qty']))
   if self.code==5 and d.year>2011 and mom[s] is None:reasons.append('Full one-year lookback unavailable; missing signals tie and use fixed basket order, not measured momentum leadership.')
   if bought:
    if d.year==2011:reasons.append('Common initial equal allocation; whole-share rounding and residual sweep.')
    elif self.code==1:reasons.append('Annual equal-cash allocation across all ten, then residual sweep.')
    elif self.code==5:reasons.append(f'Momentum rank {rank.index(s)+1}/10; one-year price return {pc(mom[s])}. New cash goes to the top three, then residual sweep.')
    else:
     target=trace['deploy']['target'];gap=trace['deploy']['gaps'][s]
     reasons.append(f'Cash-inclusive target {pc(target)}; opening allocation gap Rs {gap:,.2f}. Executed: '+', '.join(actualnotes)+'.')
     if sold:reasons.append('The equity-only trim ran first; cash-inclusive targets were then recalculated, causing a buy after the sale.')
     if self.code==4 and ret[s] is not None and ret[s]<-.1:reasons.append('The no-eligible-candidates fallback relaxed the loss screen.')
   else:
    candidates=trace.get('deploy',{}).get('candidates',[])
    if s not in candidates:
     if self.code==5:reasons.append(f'No buy: momentum rank {rank.index(s)+1}/10, return {pc(mom[s])}; outside top three.')
     elif self.code==4 and cagr[s] is not None and cagr[s]<0 and before[s]:reasons.append('No buy: blocked for this review by the exit rule.')
     else:reasons.append(f'No buy: not in the eligible addition set; economic gain {pc(ret[s])} versus the -10% loss screen.')
    elif b:reasons.append('No buy: attempted cash allocation could not purchase one whole share after costs.')
    else:reasons.append('No buy: no funded target gap or affordable residual allocation remained after earlier allocations.')
   mine=[t for t in trades if t['symbol']==s and t['event'] in ['BUY','SELL']]
   spent=-sum(t['cash_change'] for t in mine if t['event']=='BUY');received=sum(t['cash_change'] for t in mine if t['event']=='SELL')
   result.append(dict(symbol=s,before=before[s],after=after,weight_before=weight*100,weight_after=wa*100,reference=ref[s],fill=self.data.p[d][s]['open'],bought=bought,sold=sold,sold_pct=100*sold/before[s] if before[s] else 0,action=action,spent=spent,received=received,net_cash=received-spent,cagr5=cagr[s],momentum=mom[s],gain=ret[s],reason=' '.join(reasons)))
  assert abs(sum(x['weight_after'] for x in result)-100)<1e-8
  self.reviews.append(dict(date=str(d),signal_date=str(prev) if prev else str(d),rows=result,cash_before=cashbefore,cash_after=self.cash,review_equity=aftertotal,sales=trace['sales']))

def build():
 data=Data();saved=json.loads((OUT/'results.json').read_text());explanations=[]
 with zipfile.ZipFile(OUT/'audit_ledgers.zip') as z:
  for code in range(1,6):
   book=ExplainedBook(data,code);result=book.run()
   original=list(csv.DictReader(io.StringIO(z.read(f'S{code}_transactions_and_events.csv').decode())))
   assert len(original)==len(book.logs)
   for expected,actual in zip(original,book.logs):
    for k,v in expected.items():
     if k in ['quantity','price','cash_change','earned_change']:assert abs(float(v)-actual[k])<1e-7,(code,k,v,actual)
     else:assert str(actual[k])==v,(code,k,v,actual)
   assert abs(result['terminal_after_cost']-saved['results'][code-1]['terminal_after_cost'])<1e-6
   explanations.append(dict(code=code,reviews=book.reviews))
   print('Explained and reconciled S'+str(code),flush=True)
 (OUT/'decision_explanations.json').write_text(json.dumps(explanations,indent=2))
 return explanations
if __name__=='__main__':build()
