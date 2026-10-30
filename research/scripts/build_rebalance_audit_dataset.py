"""Download immutable vendor snapshots; do not silently repair missing observations."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/data/rebalance_audit_2010_2026'
SYMBOLS = 'BHEL COALINDIA IOC ITC KTKBANK ONGC SCI NTPC TATASTEEL SOUTHBANK'.split()

def fetch(symbol):
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + symbol + '.NS'
    params = dict(period1=1262304000, period2=int(time.time()), interval='1d', events='div,splits,capitalGains')
    response = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=45)
    response.raise_for_status()
    raw = response.content
    (OUT/'raw'/f'{symbol}.json').write_bytes(raw)
    result = response.json()['chart']['result'][0]
    quote = result['indicators']['quote'][0]
    frame = pd.DataFrame(quote)
    frame['date'] = pd.to_datetime(result['timestamp'], unit='s', utc=True).tz_convert('Asia/Kolkata').date
    frame['symbol'] = symbol
    frame['vendor_adjusted_close'] = result['indicators']['adjclose'][0]['adjclose']
    # Exclude the current Indian calendar date: today's bar may be intraday.
    today = pd.Timestamp.now(tz='Asia/Kolkata').date()
    frame = frame[frame.date < today].copy()
    frame['price_basis'] = 'Yahoo historical OHLC; vendor split-adjusted, NOT certified exchange raw prices'
    frame.to_csv(OUT/'prices'/f'{symbol}.csv', index=False)
    events=[]
    for kind, values in result.get('events', {}).items():
        for event in values.values():
            events.append(dict(symbol=symbol, date=str(pd.to_datetime(event['date'], unit='s', utc=True).tz_convert('Asia/Kolkata').date()), kind=kind,
                               amount=event.get('amount'), numerator=event.get('numerator'), denominator=event.get('denominator'),
                               ratio=event.get('splitRatio'), source_url=response.url,
                               status='vendor_reported_not_independently_verified'))
    print(symbol, len(frame), str(frame.date.min()), str(frame.date.max()), len(events), flush=True)
    return frame, events, dict(symbol=symbol, url=response.url, sha256=hashlib.sha256(raw).hexdigest(), downloaded_utc=datetime.now(timezone.utc).isoformat())

def main():
    for folder in ['raw','prices']:
        (OUT/folder).mkdir(parents=True, exist_ok=True)
    frames=[]; events=[]; sources=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for frame, ev, source in pool.map(fetch, SYMBOLS + ['ITCHOTELS','SCILAL']):
            frames.append(frame); events.extend(ev); sources.append(source)
    combined=pd.concat(frames).sort_values(['symbol','date'])
    combined.to_csv(OUT/'daily_prices.csv',index=False)
    pd.DataFrame(events).sort_values(['date','symbol']).to_csv(OUT/'vendor_actions.csv',index=False)
    (OUT/'sources.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
    checks=[]
    for symbol, g in combined.groupby('symbol'):
        invalid=g[g[['open','high','low','close','vendor_adjusted_close']].isna().any(axis=1) | (g.close<=0)]
        jumps=g.assign(change=g.vendor_adjusted_close.pct_change(fill_method=None)).query('abs(change)>0.25')
        checks.append(dict(symbol=symbol, rows=len(g), first=str(g.date.min()), last=str(g.date.max()), duplicate_dates=int(g.date.duplicated().sum()),
                           missing_or_nonpositive_prices=len(invalid), large_moves=[dict(date=str(r.date),return_pct=100*r.change) for r in jumps.itertuples()]))
    (OUT/'quality_checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')

if __name__=='__main__':main()
