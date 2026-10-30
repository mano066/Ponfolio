import requests,json
from pathlib import Path
s=requests.Session();s.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://www.nseindia.com/'})
s.get('https://www.nseindia.com',timeout=20)
r=s.get('https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData',params={'symbol':'BHEL','series':'EQ','from':'01-01-2010','to':'10-09-2026','type':'priceVolumeDeliverable'},timeout=40)
print(r.status_code,r.text[:650],flush=True)
Path('research/data/rebalance_audit_2010_2026/raw/NSE_BHEL_history.json').write_bytes(r.content)
print('rows',len(r.json().get('data',[])))
