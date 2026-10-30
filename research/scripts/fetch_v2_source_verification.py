"""Fetch timestamped public source snapshots; never overwrite earlier downloads."""
import concurrent.futures
import datetime as dt
import hashlib
import http.cookiejar
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SYMBOLS = 'BHEL COALINDIA IOC ITC KTKBANK ONGC SCI NTPC TATASTEEL SOUTHBANK'.split()
STAMP = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT = ROOT / 'research/data/v2_source_verification' / STAMP


def fetch(task):
    name, url = task
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
               'Accept': '*/*', 'Referer': 'https://www.nseindia.com/'}
    entry = dict(name=name, url=url, retrieved_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    try:
        if 'www.nseindia.com/api/' in url:
            try:
                opener.open(urllib.request.Request('https://www.nseindia.com/', headers=headers), timeout=12).read()
            except Exception:
                pass
        with opener.open(urllib.request.Request(url, headers=headers), timeout=25) as response:
            body = response.read()
            entry.update(status=response.status, content_type=response.headers.get('Content-Type'),
                         sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
            (OUT / name).write_bytes(body)
    except Exception as exc:
        entry['error'] = str(exc)
    print(name, entry.get('status', entry.get('error')), flush=True)
    return entry


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
    tasks = []
    for symbol in SYMBOLS:
        tasks += [(f'{symbol}_quote.json', 'https://www.nseindia.com/api/quote-equity?' + urllib.parse.urlencode({'symbol': symbol})),
                  (f'{symbol}_actions.json', 'https://www.nseindia.com/api/corporates-corporateActions?' + urllib.parse.urlencode(dict(index='equities',symbol=symbol,from_date='01-01-2010',to_date=today.strftime('%d-%m-%Y')))),
                  (f'{symbol}_yahoo.json', f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?range=1mo&interval=1d&events=div%2Csplits')]
    for days in (0, 1):
        day = today - dt.timedelta(days=days)
        filename = f'BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip'
        tasks.append((filename, 'https://nsearchives.nseindia.com/content/cm/' + filename))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        entries = list(pool.map(fetch, tasks))
    (OUT / 'manifest.json').write_text(json.dumps(entries, indent=2), encoding='utf-8')
    print('Saved', OUT, flush=True)


if __name__ == '__main__':
    main()
