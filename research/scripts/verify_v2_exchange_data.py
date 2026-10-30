"""Reconcile V2 downloads with dated NSE bhavcopies and corporate-action files."""
import csv
import datetime as dt
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'research/data/v2_source_verification'
OLD = ROOT / 'research/data/rebalance_audit_2010_2026'
SYMBOLS = 'BHEL COALINDIA IOC ITC KTKBANK ONGC SCI NTPC TATASTEEL SOUTHBANK'.split()


def write_csv(path, rows):
    if rows:
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def bhav(path):
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith('.csv'))
        for raw in csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig'))):
            old = 'SYMBOL' in raw
            symbol = raw.get('SYMBOL' if old else 'TckrSymb')
            series = raw.get('SERIES' if old else 'SctySrs')
            if symbol not in SYMBOLS + ['ITCHOTELS', 'SCILAL'] or series not in ('EQ','BE'):
                continue
            if old:
                try:
                    day=dt.datetime.strptime(raw['TIMESTAMP'],'%d-%b-%Y').date().isoformat()
                except ValueError:
                    day=dt.datetime.strptime(raw['TIMESTAMP'],'%d-%b-%y').date().isoformat()
            else:
                day=raw['TradDt']
            yield dict(symbol=symbol, date=day, isin=raw.get('ISIN', ''),series=series,
                       open=float(raw['OPEN' if old else 'OpnPric']), high=float(raw['HIGH' if old else 'HghPric']),
                       low=float(raw['LOW' if old else 'LwPric']), close=float(raw['CLOSE' if old else 'ClsPric']),
                       last=float(raw['LAST' if old else 'LastPric']),
                       volume=int(raw['TOTTRDQTY' if old else 'TtlTradgVol']), source_file=path.name)


def main():
    latest = sorted(p for p in BASE.iterdir() if p.is_dir() and p.name[0].isdigit())[-1]
    out = BASE / 'verified'
    out.mkdir(exist_ok=True)
    exchange = {}
    for path in sorted((BASE / 'event_bhavcopies').glob('*.zip')) + sorted(latest.glob('*.zip')):
        for row in bhav(path):
            k = (row['symbol'], row['date'])
            if k in exchange and exchange[k]['close'] != row['close']:
                raise ValueError(f'Conflicting exchange close: {k}')
            exchange[k] = row
    print('Exchange observations', len(exchange), flush=True)
    with (OLD / 'daily_prices_clean.csv').open() as stream:
        downloaded = {(r['symbol'], r['date']): r for r in csv.DictReader(stream)}
    comparisons = []
    for k, official in sorted(exchange.items()):
        if k not in downloaded:
            continue
        vendor = downloaded[k]
        candidate = float(vendor['candidate_unadjusted_close'])
        difference = candidate - official['close']
        comparisons.append(dict(symbol=k[0], date=k[1], nse_close=official['close'],
                                vendor_close=float(vendor['close']), candidate_unadjusted_close=candidate,
                                difference_rupees=round(difference, 6),
                                difference_pct=round(difference / official['close'] * 100, 6),
                                within_5_paise=abs(difference) <= .05,
                                nse_file=official['source_file']))
    write_csv(out / 'exchange_price_observations.csv', list(exchange.values()))
    write_csv(out / 'historical_price_reconciliation.csv', comparisons)

    actions = []
    changed = []
    for symbol in SYMBOLS:
        fresh = json.loads((latest / f'{symbol}_actions.json').read_text())
        previous = json.loads((OLD / 'raw' / f'NSE_{symbol}_actions.json').read_text())
        identity = lambda row: (row.get('symbol'), row.get('exDate'), row.get('subject'))
        newkeys, oldkeys = set(map(identity, fresh)), set(map(identity, previous))
        changed.append(dict(symbol=symbol, added=list(newkeys-oldkeys), removed=list(oldkeys-newkeys)))
        for row in fresh:
            if row['symbol'] != symbol:
                raise ValueError('Wrong symbol in corporate-action response')
            terms = row['subject'].strip()
            text = terms.lower()
            kinds = [k for k in ['dividend', 'bonus', 'split', 'rights', 'demerger', 'buyback'] if k in text]
            if re.search(r'\bdiv\b',text) and 'dividend' not in kinds:
                kinds.append('dividend')
            if 'debenture' in text:
                kinds = ['bonus_debenture']
            if 'sub-division' in text and 'split' not in kinds:
                kinds.append('split')
            if 'buy back' in text or 'buy-back' in text:
                kinds.append('buyback')
            actions.append(dict(symbol=symbol, ex_date=dt.datetime.strptime(row['exDate'], '%d-%b-%Y').date().isoformat(),
                                record_date=row.get('recDate', ''), kind='+'.join(kinds) or 'other',
                                source_text=terms, source_file=f'{symbol}_actions.json',
                                source_url=next(e['url'] for e in json.loads((latest/'manifest.json').read_text()) if e['name']==f'{symbol}_actions.json')))
    actions.sort(key=lambda r: (r['symbol'], r['ex_date'], r['source_text']))
    write_csv(out / 'nse_corporate_actions_verified_source.csv', actions)
    current = []
    for symbol in SYMBOLS:
        observations = sorted((r for r in exchange.values() if r['symbol']==symbol), key=lambda r:r['date'])
        r = observations[-1]
        yahoo = json.loads((latest / f'{symbol}_yahoo.json').read_text())['chart']['result'][0]
        timestamp = dt.datetime.fromtimestamp(yahoo['meta']['regularMarketTime'], dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat()
        yh = dict(zip([dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=5,minutes=30))).date().isoformat() for t in yahoo['timestamp']], yahoo['indicators']['quote'][0]['close']))
        yc = yh.get(r['date'])
        current.append(dict(symbol=symbol, isin=r['isin'], session_date=r['date'], nse_close=r['close'],
                            nse_last_trade=r['last'], yahoo_daily_close=yc,
                            yahoo_quote_time_ist=timestamp,
                            close_difference_rupees=round(yc-r['close'], 6) if yc is not None else None,
                            source_file=r['source_file']))
    write_csv(out / 'latest_official_prices.csv', current)
    summaries = []
    for symbol in SYMBOLS:
        checks = [r for r in comparisons if r['symbol']==symbol]
        events = [r for r in actions if r['symbol']==symbol]
        summaries.append(dict(symbol=symbol, checked_prices=len(checks), passed=sum(r['within_5_paise'] for r in checks),
                              failed=sum(not r['within_5_paise'] for r in checks),
                              maximum_difference_pct=max(abs(r['difference_pct']) for r in checks),
                              action_rows=len(events), dividend_rows=sum('dividend' in r['kind'] for r in events)))
    results = dict(snapshot=latest.name, latest_prices=current, price_checks=summaries,
                   corporate_action_changes=changed, status='PRICE_AND_ACTION_EVIDENCE; NOT_A_CERTIFIED_BACKTEST',
                   old_nse_history_file_is_json=False)
    try:
        json.loads((OLD/'raw/NSE_BHEL_history.json').read_text())
        results['old_nse_history_file_is_json'] = True
    except ValueError:
        pass
    (out/'verification_summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(summaries, indent=2), flush=True)
    print('ONGC event evidence',json.dumps([r for r in comparisons if r['symbol']=='ONGC' and r['date'] in ['2011-02-07','2011-02-08']],indent=2),flush=True)


if __name__ == '__main__':
    main()
