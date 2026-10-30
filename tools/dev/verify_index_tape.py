"""Rebuild the tape with the fix and audit every index against its own data."""
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
sys.path.insert(0, REPO)
os.chdir(REPO)

import main  # noqa: E402  (boots the same pipeline the app uses)

tape = main._get_index_tape(force=True)
rows = tape["indices"]

print(f"as_of={tape['as_of']}  breadth={tape['breadth']}")
print()
print(f"{'LABEL':14s} {'LAST':>10s} {'DAY%':>7s} {'1W%':>7s} {'GAP':>4s} "
      f"{'PREV BAR':>11s} {'LAST BAR':>11s}  VERDICT")
suspicious = 0
for r in rows:
    if r.get("status") != "ok":
        print(f"{r['label']:14s} {'—':>10s} {'—':>7s} {'—':>7s} {'—':>4s} "
              f"{'—':>11s} {'—':>11s}  no data")
        continue
    day = r.get("day_chg_pct")
    week = r.get("chg_1w_pct")
    gap = r.get("day_chg_span_days")
    # The arithmetic tell: a single session cannot out-move the week holding
    # it in the same direction.
    impossible = (day is not None and week is not None
                  and abs(day) > abs(week) + 0.05
                  and (day > 0) == (week > 0))
    verdict = ("NO PRIOR SESSION" if day is None
               else "SUSPECT: day > week" if impossible else "ok")
    if verdict != "ok":
        suspicious += 1
    print(f"{r['label']:14s} {r.get('last'):>10} "
          f"{('—' if day is None else f'{day:+.2f}'):>7} "
          f"{('—' if week is None else f'{week:+.2f}'):>7} "
          f"{str(gap or '—'):>4} {str(r.get('prev_bar_date') or '—'):>11} "
          f"{str(r.get('last_bar_date') or '—'):>11}  {verdict}")

print()
print(f"rows needing a caveat: {suspicious} of {len(rows)}")
