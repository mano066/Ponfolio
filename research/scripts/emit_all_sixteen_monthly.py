"""S1-S10 and M1-M6 in ONE dataset, on the monthly Rs 10,000 SIP.

    python research/scripts/emit_all_sixteen_monthly.py

The ledger PDF is deliberately dumb: it reads `results.json` and
`audit_ledgers.zip` and prints what it finds, so the document cannot disagree
with the engine. Adding the six masters to that document therefore means
producing the six masters in exactly the same artefact shape, not teaching the
builder to recompute anything.

S1-S10 are copied verbatim from the existing monthly run rather than re-run.
Re-running them would risk a silent drift between this document and the one
already published, and there is nothing to gain: the same code produced them.

M1-M6 are computed here on the same calendar, the same basket and the same
verified prices.

Out: research/data/strategies_all/{results.json, audit_ledgers.zip}
"""
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))

import backtest_master_guarded as gd  # noqa: E402
from backtest_five_verified import Data, csvtext  # noqa: E402

SRC = ROOT / "research" / "data" / "strategies_monthly"
OUT = ROOT / "research" / "data" / "strategies_all"

# 11-13 are the existing masters, 14-16 the guarded variants. Codes match the
# ones the backtests already use, so `S11` in the zip is M1 and so on.
MASTERS = [11, 12, 13, 14, 15, 16]
LABEL = {11: "M1", 12: "M2", 13: "M3", 14: "M4", 15: "M5", 16: "M6"}


def main():
    base = json.loads((SRC / "results.json").read_text(encoding="utf-8"))
    have = {r["code"] for r in base["results"]}
    if have != set(range(1, 11)):
        raise SystemExit(f"expected S1-S10 in the monthly run, found {sorted(have)}")

    print("running the six masters on the monthly calendar…")
    data = Data()
    books, results, after = [], [], []
    for code in MASTERS:
        b = gd.GuardedBook(data, code, months=None)
        b.ticket = 10000
        r = b.run()
        # The builder prints the name it is given, so make the master's
        # identity unambiguous next to S1-S10 on the same page.
        r["name"] = f"{LABEL[code]} {r['name'].split(' ', 1)[1]}"
        # The builder prints a pre-tax and an after-tax column for every
        # strategy, so both have to exist or the master rows would be missing
        # half the page.
        t = gd.GuardedBook(data, code, 12, after_tax=True, months=None)
        t.ticket = 10000
        rt = t.run()
        rt["name"] = r["name"]
        books.append(b)
        results.append(r)
        after.append(rt)
        print(f"  {r['name'][:52]:<54} {r['xirr_pct']:6.2f}%  "
              f"sells={r['sells']}", flush=True)

    # Contributions must match, or the columns are not comparable.
    want = base["results"][0]["contributions"]
    for r in results:
        if r["contributions"] != want:
            raise SystemExit(f"{r['name']} made {r['contributions']} "
                             f"contributions, S1 made {want}")

    OUT.mkdir(parents=True, exist_ok=True)
    payload = dict(base)
    payload["results"] = base["results"] + results
    payload["after_tax"] = base["after_tax"] + after
    payload["masters_note"] = (
        "S1-S10 copied verbatim from research/data/strategies_monthly. "
        "M1-M6 computed by backtest_master_guarded on the same calendar, "
        "basket and prices. All sixteen pay the same "
        f"{want} contributions of Rs 10,000.")
    (OUT / "results.json").write_text(json.dumps(payload, indent=2),
                                      encoding="utf-8")

    shutil.copy(SRC / "audit_ledgers.zip", OUT / "audit_ledgers.zip")
    with zipfile.ZipFile(OUT / "audit_ledgers.zip", "a",
                         zipfile.ZIP_DEFLATED) as z:
        for b in books:
            z.writestr(f"S{b.code}_transactions_and_events.csv",
                       csvtext(b.logs))
            z.writestr(f"S{b.code}_monthly_reviews.csv", csvtext(
                [{k: v for k, v in r.items() if k != "holdings"}
                 for r in b.reviews]))
    print(f"\nwrote {OUT} — {len(payload['results'])} strategies")


if __name__ == "__main__":
    main()
