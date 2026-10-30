"""Validate the complete exchange archive and publish the data-first dossier."""
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from verify_v2_exchange_data import ROOT, BASE, OLD, SYMBOLS, write_csv
from rebalance_corporate_actions import dividend_amount

NOTES = {
    'BHEL': '2011-10-03: face value Rs 10 to Rs 2 (5 shares for 1). 2017-09-28: bonus 1:2 (1.5x). 2018 buyback requires a participation rule.',
    'COALINDIA': 'No split or equity bonus appears in the fetched 2010-2026 action records. Dividends and 2016/2019 buybacks appear; do not automatically treat buybacks as shareholder cash receipts.',
    'IOC': 'Bonus 1:1 on 2016-10-18; bonus 1:1 on 2018-03-15; bonus 1:2 on 2022-06-30. Combined factor for pre-2016 shares: 6x. 2018 buyback recorded.',
    'ITC': 'Bonus 1:2 on 2016-07-01. Hotels demerger record/ex-date 2025-01-06: 1 ITCHOTELS share per 10 ITC shares. The 2010-08-03 1:1 bonus predates the V2 start.',
    'KTKBANK': 'Rights 2:5 in February 2011 (Rs 75 premium plus Rs 10 face value); rights 1:2 in October 2016 (Rs 60 premium plus Rs 10 face value). Bonus 1:10 on 2020-03-17. Rights require subscription cash or an explicit alternative, not free bonus shares.',
    'ONGC': '2011-02-08: 1:1 bonus plus face-value split Rs 10 to Rs 5, combined factor 4x. Bonus 1:2 on 2016-12-15. 2019 buyback recorded. The vendor event factor of 2 is incomplete even though its price series reflects the combined adjustment.',
    'SCI': 'Demerger record/ex-date 2023-03-31: 1 SCILAL share per SCI share; allotment 2023-04-06. Preserve the unlisted entitlement before SCILAL starts trading; do not invent a tradable quote during that interval.',
    'NTPC': '2015-03-20: bonus debentures, not equity bonus shares. One Rs 12.50 debenture per eligible share; 8.49% coupon. Principal scheduled as Rs 2.50 / Rs 5 / Rs 5 in March 2023 / 2024 / 2025. Equity bonus 1:5 on 2019-03-19. 2020 buyback recorded.',
    'TATASTEEL': '2018 rights: 4 fully paid shares per 25 at Rs 510; 2 partly paid shares per 25 at total Rs 615 with separate payment calls. 2022-07-28: face value Rs 10 to Rs 1 (10x). Keep partly paid securities separate from ordinary shares.',
    'SOUTHBANK': 'Rights 1:3 in February 2017 (Rs 13 premium plus Rs 1 face value); rights 1:4 on 2024-02-27 at Rs 22 including premium. The 2010 split from Rs 10 to Rs 1 predates the V2 start.',
}
ISSUER_SOURCES = {
    'ITC': ('https://itcportal.com/investors/proposed-demerger-hotels-business.html', 'Issuer demerger documents: 1-for-10 entitlement; stated cost allocation 86.49% ITC and 13.51% ITC Hotels. Use the revised communication, which corrects an arithmetic example.'),
    'SCI': ('https://www.shipindia.com/upload/investorsubpage/IntimationtoShareholdersforCostsplitFinalSigned.pdf', 'Issuer notice dated 2023-05-12: 1-for-1 entitlement; stated cost allocation 59.68% SCI and 40.32% SCILAL.'),
    'NTPC': ('https://www.ntpc.co.in/sites/default/files/inline-files/LettertoSE44thNTPCAR201920.pdf', 'Issuer annual-report terms identify the 8.49% Rs 12.50 bonus debenture and the three scheduled principal instalments. Actual payment dates and interest cash entries must be reconciled before an executable ledger is certified.'),
    'TATASTEEL': ('https://www.tatasteel.com/newsroom/press-releases/india/2022/tata-steel-stock-split-of-equity-shares/', 'Issuer confirms the July 28, 2022 split ex-date.'),
    'KTKBANK': ('https://karnatakabank.com/sites/default/files/corportate_announcement/ppd_0.pdf', 'Issuer capital-history tables confirm the rights issue prices and the March 2020 1-for-10 bonus.'),
    'SOUTHBANK': ('https://www.southindianbank.bank.in/UserFiles/file/Annual_Report_SIB_2023-24.pdf', 'Issuer annual report confirms the 2024 1-for-4 rights issue at Rs 22.'),
}


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    full = BASE / 'full_exchange_history'
    verified = BASE / 'verified'
    if not (full / 'coverage.json').exists():
        raise SystemExit('Full download not finished; refusing to publish a completed verification report.')
    coverage = json.loads((full / 'coverage.json').read_text())
    manifests = [json.loads(line) for line in (full / 'manifest.jsonl').read_text().splitlines()]
    if not (full/'weekend_coverage.json').exists():
        raise SystemExit('Weekend calendar verification has not finished.')
    weekend_manifest = [json.loads(line) for line in (full/'weekend_manifest.jsonl').read_text().splitlines()]
    by_date = {e['date']:e for e in manifests}
    for entry in weekend_manifest:
        if entry['date'] not in by_date or entry['status']=='downloaded':
            by_date[entry['date']] = entry
    manifests = sorted(by_date.values(),key=lambda e:e['date'])
    hash_failures = []
    for entry in manifests:
        if entry['status'] == 'downloaded':
            actual = hashlib.sha256((full / entry['file']).read_bytes()).hexdigest()
            if actual != entry['sha256']:
                hash_failures.append(entry['file'])
    official = read_csv(full / 'official_daily_prices.csv')
    if len(official) != coverage['rows']:
        raise ValueError('Row count disagrees with download manifest')
    combined = {(r['symbol'],r['date']):r for r in official}
    for row in read_csv(full/'weekend_prices.csv'):
        key = row['symbol'],row['date']
        if key in combined and row != combined[key]:
            raise ValueError(f'Conflicting weekday/weekend extraction: {key}')
        combined[key]=row
    official = sorted(combined.values(),key=lambda r:(r['date'],r['symbol']))
    coverage = dict(start=coverage['start'],end=coverage['end'],attempted_dates=len(manifests),
                    downloaded_dates=sum(e['status']=='downloaded' for e in manifests),rows=len(official),
                    unavailable=[e for e in manifests if e['status']!='downloaded'])
    expected_days = (dt.date.fromisoformat(coverage['end'])-dt.date.fromisoformat(coverage['start'])).days+1
    if len(manifests)!=expected_days:
        raise ValueError('Not every calendar day was attempted')
    (verified/'all_calendar_coverage.json').write_text(json.dumps(coverage,indent=2),encoding='utf-8')
    write_csv(verified/'official_daily_prices.csv',official)
    keys = [(r['symbol'], r['date']) for r in official]
    duplicates = [k for k,n in Counter(keys).items() if n>1]
    bad_prices = []
    for row in official:
        o,h,l,c = (float(row[k]) for k in ['open','high','low','close'])
        if not (all(math.isfinite(v) and v>0 for v in [o,h,l,c]) and l<=min(o,c)<=max(o,c)<=h and int(row['volume'])>=0):
            bad_prices.append(dict(symbol=row['symbol'],date=row['date'],file=row['source_file']))
    by_key = {(r['symbol'],r['date']):r for r in official}
    by_symbol = defaultdict(list)
    for row in official:
        by_symbol[row['symbol']].append(row)
    prior = read_csv(OLD/'daily_prices_clean.csv')
    comparable = []
    missing_vendor_dates = []
    for row in prior:
        symbol,day = row['symbol'],row['date']
        if symbol not in SYMBOLS or not coverage['start']<=day<=coverage['end']:
            continue
        if (symbol,day) not in by_key:
            missing_vendor_dates.append(dict(symbol=symbol,date=day))
            continue
        nse = by_key[symbol,day]
        candidate = float(row['candidate_unadjusted_close'])
        diff = candidate-float(nse['close'])
        comparable.append(dict(symbol=symbol,date=day,nse_raw_close=float(nse['close']),
                               old_candidate_raw_close=candidate,difference_rupees=round(diff,6),
                               difference_pct=round(diff/float(nse['close'])*100,6),
                               within_5_paise=abs(diff)<=.05,source_file=nse['source_file']))
    write_csv(verified/'full_historical_price_reconciliation.csv',comparable)
    write_csv(verified/'vendor_dates_without_nse_observation.csv',missing_vendor_dates)
    summaries = []
    session_dates = sorted(set(r['date'] for r in official if r['symbol'] in SYMBOLS))
    for symbol in SYMBOLS:
        group = sorted(by_symbol[symbol],key=lambda r:r['date'])
        checks = [r for r in comparable if r['symbol']==symbol]
        days = set(r['date'] for r in group)
        summaries.append(dict(symbol=symbol,official_rows=len(group),first=group[0]['date'],last=group[-1]['date'],
                              compared=len(checks),matched=sum(r['within_5_paise'] for r in checks),
                              mismatched=sum(not r['within_5_paise'] for r in checks),
                              worst_difference_pct=max(abs(r['difference_pct']) for r in checks),
                              missing_common_sessions=[d for d in session_dates if d not in days]))
    write_csv(verified/'historical_symbol_summary.csv',summaries)
    actions = read_csv(verified/'nse_corporate_actions_verified_source.csv')
    dividends = []
    prior_events = {(r['symbol'],r['ex_date'],r['source_text'].strip()):r for r in read_csv(OLD/'corporate_actions.csv')}
    dividend_corrections = []
    for event in actions:
        if 'dividend' not in event['kind']:
            continue
        amount = dividend_amount(event['source_text'])
        dividends.append(dict(symbol=event['symbol'],ex_date=event['ex_date'],record_date=event['record_date'],
                              declared_rupees_per_share=amount,payment_date='',
                              amount_basis='NSE declared per-share terms; not adjusted to current share count',
                              payment_status='payment date not verified',source_text=event['source_text'],source_url=event['source_url']))
        previous = prior_events.get((event['symbol'],event['ex_date'],event['source_text'].strip()),{}).get('dividend_per_share')
        before = float(previous) if previous else None
        if (before is None) != (amount is None) or (before is not None and amount is not None and abs(before-amount)>1e-9):
            dividend_corrections.append(dict(symbol=event['symbol'],ex_date=event['ex_date'],
                                             previous_parsed_amount=before,corrected_declared_amount=amount,
                                             source_text=event['source_text']))
    write_csv(verified/'declared_dividends.csv',dividends)
    (verified/'dividend_parser_corrections.json').write_text(json.dumps(dividend_corrections,indent=2),encoding='utf-8')
    prices = read_csv(verified/'latest_official_prices.csv')
    existing_check = json.loads((verified/'verification_summary.json').read_text())
    snapshot_dir = BASE/existing_check['snapshot']
    for entry in json.loads((snapshot_dir/'manifest.json').read_text()):
        if entry.get('status')==200:
            if hashlib.sha256((snapshot_dir/entry['name']).read_bytes()).hexdigest()!=entry['sha256']:
                hash_failures.append(str(Path(existing_check['snapshot'])/entry['name']))
    status = dict(generated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  source_snapshot=existing_check['snapshot'],coverage=coverage,
                  checksum_failures=hash_failures,duplicate_keys=duplicates,invalid_ohlc=bad_prices,
                  exchange_files_with_no_selected_symbols=[e for e in manifests if e['status']=='downloaded' and not e.get('symbols')],
                  symbols=summaries,old_dates_without_official_observation=missing_vendor_dates,
                  current_close_comparison_tolerance_rupees=.01,
                  current_closes_match=all(abs(float(r['close_difference_rupees']))<=.01 for r in prices),
                  dividend_parser_corrections=dividend_corrections,
                  unparsed_dividend_rows=[r for r in dividends if r['declared_rupees_per_share'] is None],
                  price_source='NSE official daily bhavcopy; unadjusted exchange OHLC',
                  backtest_status='NOT RERUN: data verification delivered first; corporate-action cash ledger still required')
    (verified/'full_verification_summary.json').write_text(json.dumps(status,indent=2),encoding='utf-8')

    lines = ['# V2 ten-stock source verification', '',
             'This report verifies data before any new strategy test. The previous V2 PDF is not a verified cash/share backtest.', '',
             f'Generated UTC: {status["generated_utc"]}. Latest price session: {prices[0]["session_date"]}. Currency: INR. Prices below are official end-of-day closes, not streaming quotes.', '',
             '## Latest official prices', '',
             '| Stock | ISIN | NSE close (Rs) | NSE last trade (Rs) | Yahoo daily close agrees within Rs 0.01 |',
             '| --- | --- | ---: | ---: | --- |']
    for r in prices:
        lines.append(f'| {r["symbol"]} | {r["isin"]} | {float(r["nse_close"]):.2f} | {float(r["nse_last_trade"]):.2f} | {abs(float(r["close_difference_rupees"]))<=.01} |')
    lines += ['', 'Source: [NSE official 2026-09-11 daily bhavcopy](https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20260911_F_0000.csv.zip). The close and last-trade price are different fields; SCI and Karnataka Bank demonstrate why they must not be mixed.',
              f'The quote/action snapshot was fetched at {existing_check["snapshot"]} UTC. NSE quote API requests returned HTTP 403; the report therefore uses the official daily file. Yahoo daily bars are a secondary cross-check, not proof of streaming freshness. Per-symbol vendor quote timestamps are preserved in latest_official_prices.csv.', '',
              '## Full daily price verification', '',
             f'Requested all {coverage["attempted_dates"]:,} calendar dates from {coverage["start"]} through {coverage["end"]}, including every weekend. Retrieved {coverage["downloaded_dates"]:,} official exchange files containing {len(official):,} observations for the ten stocks plus available ITCHOTELS/SCILAL records.',
              f'Checksum failures: {len(hash_failures)}. Duplicate symbol/date keys: {len(duplicates)}. Invalid positive-price/OHLC checks: {len(bad_prices)}.',
              f'{len(coverage["unavailable"])} attempted dates returned no usable file. They are recorded individually in all_calendar_coverage.json; they are not silently labelled holidays or filled with made-up prices.', '',
              'The series column preserves EQ and BE records. SCI temporarily traded in BE after its 2023 demerger; the source ISIN remains visible. The parser also accepts the two-digit year used in the 2020-07-13 exchange file. No missing values were forward-filled.', '',
              '| Stock | Official daily rows | First | Last | Old reconstructed prices compared | Match within Rs 0.05 | Differ | Largest difference |',
              '| --- | ---: | --- | --- | ---: | ---: | ---: | ---: |']
    for s in summaries:
        lines.append(f'| {s["symbol"]} | {s["official_rows"]} | {s["first"]} | {s["last"]} | {s["compared"]} | {s["matched"]} | {s["mismatched"]} | {s["worst_difference_pct"]:.4f}% |')
    lines += ['', 'Comparison basis: old candidate_unadjusted_close (vendor close multiplied by parsed future split/bonus factors) versus actual NSE raw close. Differences do not establish fraud: rights/demerger adjustments, vendor errors or other basis differences can explain them. They establish that the reconstructed series cannot be assumed to be executable historical prices.',
              f'Old vendor observations with no matching downloaded NSE row: {len(missing_vendor_dates)}. See vendor_dates_without_nse_observation.csv. Missing per-stock sessions are listed in full_verification_summary.json.', '',
              'The unmatched vendor dates include dates on which NSE explicitly closed the market: 2026-01-15 (municipal elections), 2026-05-01, 2026-05-28 and 2026-06-26. Such vendor rows must not be used as executable trading sessions. [NSE January notice](https://nsearchives.nseindia.com/content/circulars/CMPT72278.pdf); [NSE holiday calendar](https://www.nseindia.com/resources/exchange-communication-holidays). Other unavailable dates remain separately recorded rather than being guessed to be holidays.', '',
              '## Corporate actions for each stock', '',
              f'Refetched {len(actions)} NSE records from 2010 onward for the ten stocks. Their symbol/ex-date/subject identities match the earlier action download. The complete source wording and record dates are in nse_corporate_actions_verified_source.csv; source URLs and timestamped raw responses are retained.',
              'These are exchange-reported records, not a claim that every cash payment or instrument lifecycle has been independently reconciled. Ex-date, record date, allotment date, listing date and payment date are different.', '']
    lines += [f'Declared dividend amounts were parsed for {len(dividends)} records, with {len(dividend_corrections)} corrections to the old parser. The corrected parser does not add a special dividend twice when it is explicitly included in a stated total, and it handles a missing currency prefix. Payment dates remain blank rather than invented. See declared_dividends.csv and dividend_parser_corrections.json.', '']
    for symbol in SYMBOLS:
        group = [r for r in actions if r['symbol']==symbol]
        dividends = [r for r in group if 'dividend' in r['kind']]
        last_div = max(dividends,key=lambda r:r['ex_date']) if dividends else None
        lines += [f'### {symbol}', '', NOTES[symbol], '',
                  f'NSE records: {len(group)}; dividend-labelled rows: {len(dividends)}.']
        if last_div:
            lines.append(f'Latest recorded dividend ex-date: {last_div["ex_date"]}; source terms: {last_div["source_text"]}. This is not a confirmation of the date cash was paid.')
        if symbol in ISSUER_SOURCES:
            url,note = ISSUER_SOURCES[symbol]
            lines.append(f'{note} [Issuer source]({url}).')
        lines += ['', '| Ex-date | Record date as supplied | Action | NSE terms |', '| --- | --- | --- | --- |']
        for r in group:
            if r['kind'] not in ['dividend','other']:
                lines.append(f'| {r["ex_date"]} | {r["record_date"]} | {r["kind"]} | {r["source_text"].replace("|","/")} |')
        lines += ['', f'[NSE corporate-action query]({group[0]["source_url"]}).', '']
    lines += ['## Why the previous PDF should not be treated as verified', '',
              '- The engine uses the old archive ending 2026-07-17, not the new official daily history.',
              '- download_2010.py writes Yahoo Adj Close into adjusted_close. Yahoo defines that field as adjusted for splits and dividends. The PDF labels its headline as dividends excluded, and an optional flat dividend yield adds cash on top of those adjusted returns. [Yahoo definition](https://help.yahoo.com/kb/SLN28256.html).',
              '- Buying whole shares at historically back-adjusted prices is not the same as buying executable shares at the original exchange price and receiving actual corporate-action entitlements.',
              '- ONGC is resolved at the event boundary: actual NSE closes are Rs 1,194.55 on 2011-02-07 and Rs 282.05 on 2011-02-08. The combined 4x factor reconstructs those prices; the vendor split-event record alone reports only 2x.',
              '- The saved file called NSE_BHEL_history.json is not JSON price data. It is an unsuccessful response and must not count as verified history. The new bhavcopies supply actual dated exchange records.',
              '- Cash dividends, rights participation and partly paid calls, demerger shares and fractional proceeds, NTPC debenture interest/redemptions, and any buyback participation need explicit ledger treatment. Tax and transaction-cost assumptions need their own verification; this report does not certify them.', '',
              '## Deliverables and reproduction', '',
              '- research/data/v2_source_verification/verified/official_daily_prices.csv: actual exchange OHLCV observations, including retrieved weekend sessions.',
              '- research/data/v2_source_verification/verified/latest_official_prices.csv: latest dated closes and vendor comparison.',
              '- research/data/v2_source_verification/verified/nse_corporate_actions_verified_source.csv: complete fetched action records.',
              '- research/data/v2_source_verification/verified/declared_dividends.csv: declared per-share amounts and ex-dates; unverified payment dates left blank.',
              '- research/data/v2_source_verification/verified/full_historical_price_reconciliation.csv: every comparable old/new price.',
              '- research/data/v2_source_verification/verified/full_verification_summary.json: coverage and validation results.',
              '- Raw ZIPs, JSON source responses and SHA-256 manifests remain in the source directory.', '',
              'Reproduce source extraction with python research/scripts/reextract_v2_exchange_history.py, then run python research/scripts/verify_v2_exchange_data.py and python research/scripts/build_v2_verified_report.py. These commands read saved source files. No new strategy ranking has been generated from unverified assumptions.', '']
    (ROOT/'docs/Rebalancing_V2_Verified_Stock_Data.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:status[k] for k in ['checksum_failures','duplicate_keys','invalid_ohlc','current_closes_match']},indent=2))
    print('REPORT READY: docs/Rebalancing_V2_Verified_Stock_Data.md',flush=True)


if __name__=='__main__':
    main()
