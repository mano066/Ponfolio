"""Import the three Kite exports into the running app, keeping periods clean.

The full ledger (3) spans 2026-03-01..2026-09-09 and therefore OVERLAPS the
three narrower ledgers imported earlier. Overlapping periods are summed, so
leaving them in place would double-count TDS. This drops the narrower ones and
keeps the single authoritative span.

Run with the app's own Python:
    installer\\python-embed\\python.exe tools\\dev\\import_kite_exports.py TRADEBOOK.xlsx PNL.xlsx LEDGER.xlsx

The three paths are your own Kite downloads; keep them in the git-ignored
private/broker-exports/ folder, never in the repo.
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = "http://localhost:8182"

if len(sys.argv) != 4:
    sys.exit("usage: import_kite_exports.py TRADEBOOK.xlsx PNL.xlsx LEDGER.xlsx")
TRADEBOOK, PNL, LEDGER = sys.argv[1:4]


def call(path, method="GET", data=None, headers=None):
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def upload(path, filepath):
    boundary = uuid.uuid4().hex
    with open(filepath, "rb") as handle:
        payload = handle.read()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{os.path.basename(filepath)}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    return call(path, "POST", body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}"})


print("== 1. tradebook ==")
code, body = upload("/api/portfolio/import-tradebook", TRADEBOOK)
print(f"   HTTP {code} added={body.get('added')} already={body.get('already_present')}"
      if isinstance(body, dict) else f"   HTTP {code} {body}")

print("== 2. P&L statement ==")
code, body = upload("/api/portfolio/import-kite-pnl", PNL)
print(f"   HTTP {code} realised={body.get('realized_pnl')} "
      f"charges={body.get('charges_actual')}"
      if isinstance(body, dict) else f"   HTTP {code} {body}")

print("== 3. full ledger ==")
code, body = upload("/api/portfolio/import-kite-ledger", LEDGER)
if isinstance(body, dict):
    period = body.get("period", {})
    print(f"   HTTP {code} {period.get('from')}..{period.get('to')} "
          f"tds={body.get('tds_deducted')} entries={body.get('entries')}")
    keep = f"{period.get('from')}..{period.get('to')}"
    for conflict in body.get("conflicts", []):
        c, _ = call(f"/api/portfolio/ledger-entries/{conflict}", "DELETE")
        print(f"   dropped overlapping period {conflict} (HTTP {c})")
else:
    print(f"   HTTP {code} {body}")
    keep = None

print()
print("== resulting book ==")
_, ledger = call("/api/portfolio/ledger-entries")
print(f"   ledger periods: {[p['period'] for p in ledger['periods']]}")
print(f"   overlaps: {ledger['overlapping_periods']}")
print(f"   TDS deducted={ledger['tds']['deducted']} "
      f"provisional_outstanding={ledger['tds']['provisional_outstanding']}")

_, cp = call("/api/portfolio/closed-positions")
tds, totals = cp["tds"], cp["totals"]
print()
print(f"   {'SYMBOL':12s} {'REALISED':>10s} {'CHARGES':>9s} {'TDS':>9s} {'NET':>10s}")
for row in cp["symbols"]:
    print(f"   {row['symbol']:12s} {row['gross_pnl']:10.2f} "
          f"{row['charges_estimated']:9.2f} {row['tds_attributed']:9.2f} "
          f"{row['net_after_tds']:10.2f}")
print(f"   {'TOTAL':12s} {totals['gross_pnl']:10.2f} "
      f"{totals['charges_estimated']:9.2f} {totals['tds_attributed']:9.2f} "
      f"{totals['net_after_tds']:10.2f}")
print(f"   TDS attributed={tds['attributed']} unattributed={tds['unattributed']}")
