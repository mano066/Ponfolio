"""Build explicit event fields and quarantine invalid prices without inventing data."""
from pathlib import Path
import pandas as pd
import json,re,hashlib
from rebalance_corporate_actions import dividend_amount

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/data/rebalance_audit_2010_2026'

def parse(row):
    text=row['subject']; lower=text.lower(); factor=1.; kind=[];amount=None
    if 'bonus' in lower and 'debenture' not in lower:
        m=re.search(r'bonus\s*(\d+)\s*:\s*(\d+)',lower)
        if m:factor*=1+int(m[1])/int(m[2]);kind.append('bonus')
    if 'split' in lower or 'sub-division' in lower:
        m=re.search(r'from\s*(?:rs\.?|re\.?)\s*(\d+(?:\.\d+)?)\D+?to\s*(?:rs\.?|re\.?)\s*(\d+(?:\.\d+)?)',lower)
        if m:factor*=float(m[1])/float(m[2]);kind.append('split')
    if 'dividend' in lower or re.search(r'\bdiv\b',lower):
        kind.append('dividend')
        amount=dividend_amount(text)
    if 'rights' in lower:kind.append('rights')
    if 'demerger' in lower:kind.append('demerger')
    if 'debenture' in lower:kind.append('bonus_debenture')
    if 'buyback' in lower or 'buy-back' in lower or 'buy back' in lower:kind.append('buyback')
    return dict(symbol=row['requested_symbol'],ex_date=pd.to_datetime(row['exDate'],format='%d-%b-%Y').date().isoformat(),
                record_date=row.get('recDate'),kind='+'.join(kind) or 'other',share_factor=factor,
                dividend_per_share=amount,source_text=text,source_url=row['source_url'],
                status='NSE_reported; parsed terms require instrument-specific reconciliation')

def main():
    actions=pd.read_csv(OUT/'nse_corporate_actions.csv').fillna('')
    events=pd.DataFrame([parse(row) for row in actions.to_dict('records')]).sort_values(['ex_date','symbol'])
    events.to_csv(OUT/'corporate_actions.csv',index=False)
    raw=pd.read_csv(OUT/'daily_prices.csv')
    bad=raw[['open','high','low','close','vendor_adjusted_close']].isna().any(axis=1) | (raw.close<=0)
    raw[bad].to_csv(OUT/'quarantined_prices.csv',index=False)
    clean=raw[~bad].copy()
    assert not clean.duplicated(['symbol','date']).any()
    clean['future_share_factor']=1.
    for event in events[events.share_factor!=1].itertuples():
        clean.loc[(clean.symbol==event.symbol)&(clean.date<event.ex_date),'future_share_factor']*=event.share_factor
    clean['candidate_unadjusted_close']=clean.close*clean.future_share_factor
    clean['candidate_basis_status']='RECONSTRUCTED; not exchange-verified; rights/demerger adjustments may remain'
    clean.to_csv(OUT/'daily_prices_clean.csv',index=False)
    mismatch=[]
    vendor=pd.read_csv(OUT/'vendor_actions.csv')
    for event in events[events.share_factor!=1].itertuples():
        other=vendor[(vendor.symbol==event.symbol)&(vendor.date==event.ex_date)&(vendor.kind=='splits')]
        factor=float(other.numerator.iloc[0]/other.denominator.iloc[0]) if len(other) else None
        if factor is None or abs(factor-event.share_factor)>1e-6:
            mismatch.append(dict(symbol=event.symbol,date=event.ex_date,nse_factor=event.share_factor,vendor_factor=factor,source_text=event.source_text))
    (OUT/'action_discrepancies.json').write_text(json.dumps(mismatch,indent=2),encoding='utf-8')
    inventory=[]
    for symbol,g in clean.groupby('symbol'):
        inventory.append(dict(symbol=symbol,rows=len(g),first=g.date.min(),last=g.date.max(),
                              actions=int((events.symbol==symbol).sum()),quarantined=int(((raw.symbol==symbol)&bad).sum())))
    (OUT/'coverage.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    print('Clean',len(clean),'quarantined',sum(bad),'NSE events',len(events),'factor discrepancies',mismatch)

if __name__=='__main__':main()
