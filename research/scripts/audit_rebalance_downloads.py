"""Read-only source audit; write evidence separately from prices and PDF results.

Run with Python 3, without third-party dependencies.
"""
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'research/data/rebalance_audit_2010_2026'


def rows(name):
    with (DATA / name).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def number(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return float('nan')


def main():
    hashes = []
    for manifest, prefix, suffix in [('sources.json', '', ''),
                                      ('nse_sources.json', 'NSE_', '_actions')]:
        for source in json.loads((DATA / manifest).read_text()):
            path = DATA / 'raw' / (prefix + source['symbol'] + suffix + '.json')
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            hashes.append(dict(file=path.name, matches=actual == source['sha256']))

    raw = rows('daily_prices.csv')
    clean = rows('daily_prices_clean.csv')
    quarantine = rows('quarantined_prices.csv')
    key = lambda row: (row['symbol'], row['date'])
    raw_keys, clean_keys, bad_keys = map(lambda rs: set(map(key, rs)), (raw, clean, quarantine))
    partition_ok = (clean_keys.isdisjoint(bad_keys) and raw_keys == clean_keys | bad_keys
                    and len(raw) == len(clean) + len(quarantine))
    grouped = defaultdict(list)
    for row in clean:
        grouped[row['symbol']].append(row)
    coverage = []
    for symbol, group in sorted(grouped.items()):
        dates = sorted(r['date'] for r in group)
        invalid, ohlc = [], []
        for row in group:
            o, h, l, c, a = [number(row[col]) for col in
                              ['open', 'high', 'low', 'close', 'vendor_adjusted_close']]
            if not all(math.isfinite(x) and x > 0 for x in (o, h, l, c, a)):
                invalid.append(row['date'])
            if not (l <= min(o, c) <= max(o, c) <= h):
                ohlc.append(row['date'])
        coverage.append(dict(symbol=symbol, rows=len(group), first=dates[0], last=dates[-1],
                             duplicates=len(dates)-len(set(dates)), invalid_prices=invalid,
                             ohlc_violations=ohlc))

    # Compare the exact input archive used by both reports with the new snapshot.
    archive_rows = defaultdict(list)
    all_symbols = set()
    with gzip.open(ROOT / 'research/data/nse_universe_2010_ohlcv.csv.gz', 'rt') as stream:
        for row in csv.DictReader(stream):
            all_symbols.add(row['symbol'])
            if row['symbol'] in grouped:
                archive_rows[row['symbol']].append(row)
    comparisons = []
    for symbol, group in sorted(archive_rows.items()):
        group.sort(key=lambda r: r['date'])
        lookup = {r['date']: r for r in grouped[symbol]}
        matches = [(r, lookup[r['date']]) for r in group if r['date'] in lookup]
        errors = [abs(number(a['close']) / number(b['close']) - 1) * 100
                  for a, b in matches if number(b['close']) > 0]
        comparisons.append(dict(symbol=symbol, archive_first=group[0]['date'],
                                archive_last=group[-1]['date'], overlap=len(matches),
                                median_close_difference_pct=sorted(errors)[len(errors)//2] if errors else None,
                                max_close_difference_pct=max(errors) if errors else None,
                                first_adjusted_to_close=number(group[0]['adjusted_close']) / number(group[0]['close'])))

    actions = rows('corporate_actions.csv')
    unresolved = [dict(symbol=r['symbol'], date=r['ex_date'], kind=r['kind'], terms=r['source_text'])
                  for r in actions if any(k in r['kind'] for k in ['rights', 'demerger', 'bonus_debenture'])]
    discrepancies = json.loads((DATA / 'action_discrepancies.json').read_text())
    large10 = 'RELIANCE TCS INFY HDFCBANK ICICIBANK ITC HINDUNILVR LT SUNPHARMA MARUTI'.split()
    missing = sorted(set(large10) - grouped.keys())
    result = dict(source_hashes=hashes, partition_ok=partition_ok,
                  raw_rows=len(raw), clean_rows=len(clean), quarantined_rows=len(quarantine),
                  coverage=coverage, archive_comparison=comparisons,
                  corporate_action_rows=len(actions), unresolved_actions=unresolved,
                  factor_discrepancies=discrepancies, v1_symbols_missing_from_new_audit=missing,
                  status='NOT_READY_FOR_VERIFIED_CASH_SHARE_BACKTEST')
    (DATA / 'download_audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    lines = ['# Rebalancing download audit and continuation checkpoint', '',
             'The download integrity check is complete. A corrected cash/share backtest is still pending.', '',
             f'- Raw-file checksums: {sum(h["matches"] for h in hashes)}/{len(hashes)} match the saved manifests.',
             f'- Price rows: {len(raw):,} downloaded; {len(clean):,} retained; {len(quarantine):,} quarantined.',
             f'- Clean/quarantine partition reproduces the downloaded key set: {partition_ok}.',
             f'- Saved NSE corporate-action rows: {len(actions)}.', '',
             '| Symbol | Clean rows | First date | Last date | Duplicate dates | Invalid prices | OHLC violations |',
             '| --- | ---: | --- | --- | ---: | ---: | ---: |']
    for c in coverage:
        lines.append(f'| {c["symbol"]} | {c["rows"]} | {c["first"]} | {c["last"]} | {c["duplicates"]} | {len(c["invalid_prices"])} | {len(c["ohlc_violations"])} |')
    lines += ['', '## Findings that prevent certification', '',
              '1. Both PDFs end on 2026-07-17. The new audit snapshot extends to 2026-09-10; the engine still loads the older gzip archive.',
              '2. `download_2010.py` stores Yahoo `Adj Close` as `adjusted_close`, and `rebalance_strategy_backtest.py` trades on that field. Yahoo defines it as adjusted for both splits and dividends. Thus the headline is not a dividends-excluded simulation. Adding an assumed dividend yield on top overlaps with distributions already reflected in prices. Source: https://help.yahoo.com/kb/SLN28256.html',
              '3. Whole-share purchases on back-adjusted prices are not historical executable share quantities. A cash/share ledger requires contemporaneous prices and explicit split/bonus events, dividend cash, rights decisions, and demerger entitlements. `candidate_unadjusted_close` is explicitly unverified and must not silently become the trade price.',
              '4. ONGC 2011-02-08: the downloaded NSE text combines a 1:1 bonus and a face-value split from 10 to 5 (combined factor 4); the vendor split record says 2. Resolve against exchange prices and event terms before reconstructing holdings.',
              f'5. {len(unresolved)} rights/demerger/bonus-debenture records need instrument-specific treatment. Full records are in `download_audit.json`.',
              '6. The new audit lacks these V1 basket symbols: ' + ', '.join(missing) + '. Their older archive data exists, but this download does not independently refresh/verify them.',
              '7. The existing verification_report.txt records 2,114 passing checks from a previous run. Those checks are not evidence that dividend treatment, raw execution prices or corporate-action entitlements are correct. This audit does not certify tax rules.', '',
              '## Resume steps', '',
              '1. Resolve the ONGC event and reconcile reconstructed prices to saved/official exchange observations.',
              '2. Complete explicit rights and demerger terms, including entitlement dates, allocation ratios and cost-basis treatment; distinguish ex-dates from cash payment dates.',
              '3. Extend the independent source audit to the missing V1 symbols and SBIN for the mixed-basket variation.',
              '4. Implement the cash/share ledger using verified event-aware data, then rerun all scenarios and accounting checks.',
              '5. Rebuild and visually inspect both PDFs only after the corrected results pass verification.', '',
              'Run this audit again with `python research/scripts/audit_rebalance_downloads.py`. It requires only the Python standard library and does not modify raw data, the engine, stored results, or PDFs.',
              'Environment checkpoint: Python 3.13 is available; pandas/numpy/pyarrow are not installed in it, and the prior backend/.venv is absent. The full engine verification has not been rerun on this machine.', '']
    (ROOT / 'docs/Rebalancing_Data_Audit.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['status', 'raw_rows', 'clean_rows', 'quarantined_rows', 'partition_ok', 'corporate_action_rows']}, indent=2))
    print('Checksums:', sum(h['matches'] for h in hashes), '/', len(hashes))
    print('OHLC violations:', sum(len(c['ohlc_violations']) for c in coverage))
    print('Audit saved: docs/Rebalancing_Data_Audit.md')


if __name__ == '__main__':
    main()
