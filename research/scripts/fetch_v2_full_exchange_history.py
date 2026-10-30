"""Resumable, dated NSE raw EOD archive for the V2 basket; no adjusted prices.

Fetch every weekday plus locally observed weekend sessions. Missing responses
remain explicit; a weekday without a file is not automatically called a holiday.
"""
import concurrent.futures
import datetime as dt
import hashlib
import json
import shutil
import time
import urllib.request
from pathlib import Path
from verify_v2_exchange_data import bhav, write_csv, BASE, SYMBOLS

OUT = BASE / 'full_exchange_history'


def fetch(day):
    d = dt.date.fromisoformat(day)
    if d >= dt.date(2024,7,8):
        name = f'BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip'
        url = 'https://nsearchives.nseindia.com/content/cm/' + name
    else:
        month = d.strftime('%b').upper()
        name = f'cm{d.day:02d}{month}{d.year}bhav.csv.zip'
        url = f'https://nsearchives.nseindia.com/content/historical/EQUITIES/{d.year}/{month}/' + name
    target = OUT / name
    entry = dict(date=day, file=name, url=url)
    try:
        if not target.exists():
            for attempt in range(2):
                try:
                    request = urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
                    with urllib.request.urlopen(request,timeout=20) as response:
                        body = response.read()
                    temporary = target.with_suffix('.part')
                    temporary.write_bytes(body)
                    list(bhav(temporary))  # Reject malformed downloads before promotion.
                    temporary.replace(target)
                    break
                except Exception as exc:
                    if getattr(exc,'code',None) == 404 or attempt == 1:
                        raise
                    time.sleep(.5)
        body = target.read_bytes()
        rows = list(bhav(target))
        if any(row['date'] != day for row in rows):
            raise ValueError('Unexpected trading date')
        entry.update(status='downloaded',sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),
                     symbols=sorted(r['symbol'] for r in rows),rows=rows)
    except Exception as exc:
        entry.update(status='unavailable',error=str(exc))
    return entry


def main(weekends_only=False):
    OUT.mkdir(parents=True,exist_ok=True)
    for folder in [BASE/'event_bhavcopies'] + [p for p in BASE.iterdir() if p.name[0].isdigit()]:
        for path in folder.glob('*.zip'):
            target = OUT/path.name
            if not target.exists():
                shutil.copyfile(path,target)
    start, end = dt.date(2011,1,1), dt.date(2026,9,11)
    days = set()
    d = start
    while d <= end:
        if (d.weekday() >= 5) if weekends_only else (d.weekday() < 5):
            days.add(d.isoformat())
        d += dt.timedelta(days=1)
    import csv
    if not weekends_only:
        with (BASE.parent/'rebalance_audit_2010_2026/daily_prices_clean.csv').open() as stream:
            for row in csv.DictReader(stream):
                if row['symbol'] in SYMBOLS and start.isoformat() <= row['date'] <= end.isoformat():
                    days.add(row['date'])
    manifest = OUT/('weekend_manifest.jsonl' if weekends_only else 'manifest.jsonl')
    entries = []
    with manifest.open('w',encoding='utf-8') as log, concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for i,entry in enumerate(pool.map(fetch, sorted(days)),1):
            entries.append(entry)
            log.write(json.dumps({k:v for k,v in entry.items() if k!='rows'})+'\n')
            log.flush()
            if i % 100 == 0:
                print(f'{i}/{len(days)} dates; {sum(e["status"]=="downloaded" for e in entries)} files; latest {entry["date"]}',flush=True)
    all_rows = [r for e in entries for r in e.get('rows',[])]
    write_csv(OUT/('weekend_prices.csv' if weekends_only else 'official_daily_prices.csv'),all_rows)
    summary = dict(start=str(start),end=str(end),attempted_dates=len(days),
                   downloaded_dates=sum(e['status']=='downloaded' for e in entries),rows=len(all_rows),
                   unavailable=[{k:v for k,v in e.items() if k!='rows'} for e in entries if e['status']!='downloaded'])
    (OUT/('weekend_coverage.json' if weekends_only else 'coverage.json')).write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('COMPLETE',len(all_rows),'observations;',summary['downloaded_dates'],'exchange files;',len(summary['unavailable']),'unavailable dates',flush=True)


if __name__=='__main__':
    import sys
    main(weekends_only='--weekends-only' in sys.argv)
