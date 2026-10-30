"""Recover valid cached files rejected by parsing and preserve EQ/BE series."""
import hashlib
import json
from verify_v2_exchange_data import BASE,bhav,write_csv


def main():
    root=BASE/'full_exchange_history'
    for stem,price_file,coverage_file in [('manifest','official_daily_prices.csv','coverage.json'),
                                         ('weekend_manifest','weekend_prices.csv','weekend_coverage.json')]:
        path=root/(stem+'.jsonl')
        entries=[json.loads(line) for line in path.read_text().splitlines()]
        backup=root/(stem+'_before_parser_repair.jsonl')
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        all_rows=[]
        for entry in entries:
            target=root/entry['file']
            partial=target.with_suffix('.part')
            if entry['status']!='downloaded' and partial.exists():
                recovered=list(bhav(partial))
                if not recovered or any(r['date']!=entry['date'] for r in recovered):
                    raise ValueError('Cached partial is not the expected exchange file')
                partial.replace(target)
                entry['previous_error']=entry.pop('error',None)
                entry['status']='downloaded'
                entry['parser_recovery']='two-digit year accepted; original response bytes preserved'
                print('Recovered',entry['date'],flush=True)
            if entry['status']=='downloaded':
                rows=list(bhav(target))
                if any(r['date']!=entry['date'] for r in rows):
                    raise ValueError('Unexpected session date')
                all_rows.extend(rows)
                entry.update(sha256=hashlib.sha256(target.read_bytes()).hexdigest(),bytes=target.stat().st_size,
                             symbols=sorted(r['symbol'] for r in rows))
        path.write_text(''.join(json.dumps(e)+'\n' for e in entries),encoding='utf-8')
        write_csv(root/price_file,all_rows)
        coverage=json.loads((root/coverage_file).read_text())
        coverage.update(downloaded_dates=sum(e['status']=='downloaded' for e in entries),rows=len(all_rows),
                        unavailable=[e for e in entries if e['status']!='downloaded'])
        (root/coverage_file).write_text(json.dumps(coverage,indent=2),encoding='utf-8')
        print(stem,len(all_rows),'rows',flush=True)


if __name__=='__main__':
    main()
