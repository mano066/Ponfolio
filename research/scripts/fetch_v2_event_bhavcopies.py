"""Acquire exchange price evidence around share-changing events and anniversaries."""
import concurrent.futures
import csv
import datetime as dt
import json
from pathlib import Path
import fetch_v2_source_verification as source


def main():
    source.OUT = source.ROOT / 'research/data/v2_source_verification/event_bhavcopies'
    source.OUT.mkdir(parents=True, exist_ok=True)
    old = source.ROOT / 'research/data/rebalance_audit_2010_2026'
    dates = set()
    with (old / 'daily_prices_clean.csv').open() as stream:
        for row in csv.DictReader(stream):
            if row['symbol'] == 'BHEL':
                dates.add(row['date'])
    ordered = sorted(dates)
    needed = set()
    with (old / 'corporate_actions.csv').open() as stream:
        for row in csv.DictReader(stream):
            if any(kind in row['kind'] for kind in ['split', 'bonus', 'rights', 'demerger']):
                event = row['ex_date']
                before = [d for d in ordered if d < event]
                after = [d for d in ordered if d >= event]
                needed.update(before[-1:] + after[:1])
    for year in range(2011, 2027):
        needed.add(next(d for d in ordered if d >= f'{year}-01-03'))
    tasks = []
    for day in sorted(needed):
        d = dt.date.fromisoformat(day)
        if d >= dt.date(2024, 7, 8):
            name = f'BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip'
            url = 'https://nsearchives.nseindia.com/content/cm/' + name
        else:
            name = f'cm{d:%d%b%Y}bhav.csv.zip'.replace(d.strftime('%b'), d.strftime('%b').upper())
            url = f'https://nsearchives.nseindia.com/content/historical/EQUITIES/{d:%Y}/{d:%b}/'.replace(d.strftime('%b'), d.strftime('%b').upper()) + name
        if not (source.OUT / name).exists():
            tasks.append((name, url))
    manifest = source.OUT / 'manifest.json'
    entries = json.loads(manifest.read_text()) if manifest.exists() else []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        entries.extend(pool.map(source.fetch, tasks))
    manifest.write_text(json.dumps(entries, indent=2), encoding='utf-8')
    print('Saved', len(entries), 'fetch records', flush=True)


if __name__ == '__main__':
    main()
