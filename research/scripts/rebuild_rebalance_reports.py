"""Regenerate every backtest scenario and both PDF reports in one pass."""

import subprocess
import sys
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).resolve().parents[2]
BT = ROOT / "research" / "scripts" / "rebalance_strategy_backtest.py"
RP = ROOT / "research" / "scripts" / "rebalance_report_pdf.py"
DATA = ROOT / "research" / "data"

RUNS = [
    ("v2_main.json", ["--basket", "v2", "--start", "2011-01-01"]),
    ("v2_large10.json", ["--basket", "large10", "--start", "2011-01-01"]),
    ("v2_div.json", ["--basket", "v2", "--start", "2011-01-01",
                     "--dividend-yield", "3.5"]),
    ("v2_nri.json", ["--basket", "v2", "--start", "2011-01-01",
                     "--residency", "nri"]),
    ("rebalance_backtest.json", ["--basket", "large10", "--start", "2010-01-01"]),
    ("rebalance_backtest_mixed10.json", ["--basket", "mixed10",
                                         "--start", "2010-01-01"]),
    ("rebalance_backtest_nri.json", ["--basket", "large10",
                                     "--start", "2010-01-01",
                                     "--residency", "nri"]),
    ("rebalance_backtest_div.json", ["--basket", "large10",
                                     "--start", "2010-01-01",
                                     "--dividend-yield", "1.2"]),
]


def run(cmd):
    p = subprocess.run([PY] + cmd, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        print("FAILED:", " ".join(cmd))
        print(p.stdout[-3000:])
        print(p.stderr[-3000:])
        sys.exit(1)
    return p.stdout


for name, args in RUNS:
    out = run([str(BT)] + args + ["--json-out", str(DATA / name)])
    head = [ln for ln in out.splitlines()
            if ln.startswith(("Window", "Winner", "Margin", "Note"))]
    print(f"--- {name}")
    for ln in head:
        print("   ", ln)

for tag in ("v2", "v1"):
    print(run([str(RP), tag]).strip())
