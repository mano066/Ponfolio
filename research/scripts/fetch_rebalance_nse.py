from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import requests, json, hashlib
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/data/rebalance_audit_2010_2026'
SYMBOLS='BHEL COALINDIA IOC ITC KTKBANK ONGC SCI NTPC TATASTEEL SOUTHBANK'.split()

def fetch(symbol):
    session=requests.Session()
    session.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://www.nseindia.com/','Accept':'application/json'})
    session.get('https://www.nseindia.com',timeout=25)
    response=session.get('https://www.nseindia.com/api/corporates-corporateActions',params={'index':'equities','symbol':symbol,'from_date':'01-01-2010','to_date':'11-09-2026'},timeout=40)
    response.raise_for_status()
    rows=response.json()
    if not isinstance(rows,list):raise ValueError(symbol)
    (OUT/'raw'/f'NSE_{symbol}_actions.json').write_bytes(response.content)
    for row in rows:
        row['requested_symbol']=symbol
        row['source_url']=response.url
    print(symbol,len(rows),flush=True)
    return rows,dict(symbol=symbol,url=response.url,sha256=hashlib.sha256(response.content).hexdigest(),downloaded_utc=datetime.now(timezone.utc).isoformat())

if __name__=='__main__':
    all_rows=[];sources=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for rows,source in pool.map(fetch,SYMBOLS):all_rows.extend(rows);sources.append(source)
    pd.DataFrame(all_rows).to_csv(OUT/'nse_corporate_actions.csv',index=False)
    (OUT/'nse_sources.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
