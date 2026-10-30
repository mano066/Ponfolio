"""Independent verification of the rebalance backtest.

Re-derives the results from the engine and checks them against identities that
must hold regardless of strategy: cash conservation, unit conservation, the
365-day sell rule, weight arithmetic, XIRR, and the integrity of the price
archive itself. Writes a PASS/FAIL report.

    python research/scripts/verify_rebalance_backtest.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rebalance_strategy_backtest as bt  # noqa: E402

DATA = ROOT / "research" / "data"
ARCHIVE = DATA / "nse_universe_2010_ohlcv.csv.gz"
RUPEE_TOL = 1.0          # rupee rounding in the stored ledger
WEIGHT_TOL = 0.6         # 10 weights each rounded to one decimal
RATIO_NOISE = 1e-4       # float noise floor in the adjustment factor

# NSE trades on a handful of Saturdays and Sundays: Diwali Muhurat sessions and
# Budget days. A weekend bar is only suspicious if it is not shared by every
# symbol, which would mean a stray row rather than a real session.
KNOWN_TATASTEEL_DAMAGE = (2018, 2020)   # rights-issue contamination in parquet

results: List[Tuple[str, str, bool, str]] = []


def check(section: str, name: str, ok: bool, detail: str = "") -> None:
    results.append((section, name, bool(ok), detail))


# --------------------------------------------------------------- A. archive

def verify_archive(symbols: List[str], start: str) -> None:
    raw = pd.read_csv(ARCHIVE, usecols=["date", "symbol", "close",
                                        "adjusted_close"])
    raw = raw[raw["symbol"].isin(symbols)].copy()
    raw["date"] = pd.to_datetime(raw["date"])

    weekend = raw[raw["date"].dt.dayofweek >= 5]
    sessions = weekend.groupby("date").size()
    check("archive", "weekend bars are whole market sessions, not stray rows",
          bool((sessions == len(symbols)).all()),
          "; ".join(f"{d.date()} {d.day_name()} x{n}"
                    for d, n in sessions.items()) or "none")

    for s in symbols:
        g = raw[raw["symbol"] == s].sort_values("date")
        a = g["adjusted_close"].to_numpy(dtype="float64")
        d = g["date"]

        check("archive", f"{s}: no duplicate dates",
              not d.duplicated().any())
        check("archive", f"{s}: dates strictly increasing",
              bool((d.diff().dropna() > pd.Timedelta(0)).all()))
        check("archive", f"{s}: all prices positive and finite",
              bool(np.isfinite(a).all() and (a > 0).all()))

        moves = np.abs(np.diff(a) / a[:-1]) * 100
        worst = float(moves.max()) if len(moves) else 0.0
        check("archive", f"{s}: no daily move above 30%", worst < 30.0,
              f"largest {worst:.1f}%")

        # adjusted_close / close is a back-adjustment factor: a step function
        # that never falls going forward and reaches exactly 1 at the last bar.
        ratio = (g["adjusted_close"] / g["close"]).to_numpy(dtype="float64")
        steps = int((np.abs(np.diff(ratio)) > RATIO_NOISE).sum())
        check("archive", f"{s}: adjustment factor never falls",
              bool((np.diff(ratio) >= -RATIO_NOISE).all()),
              f"{steps} corporate-action steps")
        check("archive", f"{s}: adjustment factor ends at 1",
              abs(ratio[-1] - 1.0) < 1e-6, f"ends {ratio[-1]:.6f}")
        check("archive", f"{s}: adjustment factor never exceeds 1",
              bool(ratio.max() <= 1.0 + 1e-6))


def verify_archive_vs_store(symbols: List[str], start: str) -> None:
    """Daily returns from the archive must match the parquet store wherever
    the store is undamaged. This catches a bad archive, not just a bad store."""
    raw = pd.read_csv(ARCHIVE, usecols=["date", "symbol", "adjusted_close"])
    raw = raw[raw["symbol"].isin(symbols)].copy()
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()

    for s in symbols:
        path = bt.PRICE_DIR / f"{s}.parquet"
        if not path.exists():
            check("cross-check", f"{s}: parquet present", False, "missing file")
            continue
        pq = pd.read_parquet(path, columns=["ts", "close"])
        pq["ts"] = pd.to_datetime(pq["ts"]).dt.normalize()
        pq = pq.drop_duplicates("ts").set_index("ts")["close"]

        g = raw[raw["symbol"] == s].sort_values("date")
        ar = pd.Series(g["adjusted_close"].to_numpy(dtype="float64"),
                       index=g["date"])
        ar = ar[ar.index >= pd.Timestamp(start)]

        common = ar.index.intersection(pq.index)
        if len(common) < 100:
            check("cross-check", f"{s}: enough overlapping bars", False,
                  f"{len(common)} bars")
            continue
        r_arch = np.log(ar.reindex(common)).diff().dropna()
        r_store = np.log(pq.reindex(common)).diff().dropna()
        idx = r_arch.index.intersection(r_store.index)
        diff = (r_arch.reindex(idx) - r_store.reindex(idx)).abs()
        bad = diff[diff >= 0.005]
        agree = float((1 - len(bad) / len(idx)) * 100)
        if s == "TATASTEEL":
            # The parquet file for this symbol is known to be damaged by the
            # 2018 rights issue. Disagreement is expected, but it must be
            # confined to that window or the archive is the suspect one.
            years = sorted({d.year for d in bad.index})
            inside = [y for y in years
                      if KNOWN_TATASTEEL_DAMAGE[0] <= y <= KNOWN_TATASTEEL_DAMAGE[1]]
            share = len(bad[(bad.index.year >= KNOWN_TATASTEEL_DAMAGE[0])
                            & (bad.index.year <= KNOWN_TATASTEEL_DAMAGE[1])])
            check("cross-check",
                  f"{s}: parquet damage confined to "
                  f"{KNOWN_TATASTEEL_DAMAGE[0]}-{KNOWN_TATASTEEL_DAMAGE[1]}",
                  share / max(len(bad), 1) >= 0.95,
                  f"{share} of {len(bad)} disagreeing bars inside the window, "
                  f"years touched {inside}")
        else:
            check("cross-check", f"{s}: daily returns agree with parquet store",
                  agree >= 99.0,
                  f"{agree:.2f}% of {len(idx)} bars within 0.5%")


# ---------------------------------------------------------------- B. engine

def verify_engine(basket: str, start: str, contribution: float) -> dict:
    symbols = bt.BASKETS[basket]
    px, _integrity = bt.load_prices(symbols, start)

    violations: List[str] = []
    original_sell = bt.Book.sell

    def traced_sell(self, symbol, qty_wanted, price, day,
                    long_term_only=True, note=""):
        before = [(lot, lot.qty) for lot in self.lots[symbol]]
        sold = original_sell(self, symbol, qty_wanted, price, day,
                             long_term_only, note)
        for lot, qty0 in before:
            taken = qty0 - lot.qty
            if taken > 0 and long_term_only:
                age = (day - lot.bought).days
                if age <= bt.LONG_TERM_DAYS:
                    violations.append(
                        f"{symbol} sold {taken} units on {day} from a lot "
                        f"bought {lot.bought}, only {age} days old")
        return sold

    bt.Book.sell = traced_sell
    try:
        runs = [bt.run_strategy(name, fn, px, contribution, 12.0, "resident", 0.0)
                for name, (fn, _d) in bt.STRATEGIES.items()]
    finally:
        bt.Book.sell = original_sell

    check("365-day rule", "no lot younger than 365 days was ever sold",
          not violations, "; ".join(violations[:3]))

    n_years = len(runs[0]["yearly"])
    for r in runs:
        tag = r["strategy"].split(" ")[0]

        # cash identity. buy_value and sell_value are stored rounded to the
        # rupee for every symbol, so allow half a rupee each way per symbol.
        round_tol = len(r["per_symbol"]) * 0.5 + RUPEE_TOL
        spent = sum(v["buy_value"] for v in r["per_symbol"].values())
        got = sum(v["sell_value"] for v in r["per_symbol"].values())
        expect_cash = (contribution * n_years + got - spent
                       - r["costs_paid"] - r["tax_paid"])
        check("accounting", f"{tag}: cash reconciles",
              abs(expect_cash - r["cash_left"]) < round_tol,
              f"expected {expect_cash:.2f}, book {r['cash_left']:.2f}")

        check("accounting", f"{tag}: invested equals instalments",
              abs(r["invested"] - contribution * n_years) < RUPEE_TOL)

        for s, v in r["per_symbol"].items():
            check("accounting", f"{tag}/{s}: units reconcile",
                  v["bought_units"] - v["sold_units"] == v["final_qty"],
                  f"{v['bought_units']} - {v['sold_units']} != {v['final_qty']}")
            check("accounting", f"{tag}/{s}: final value matches price",
                  abs(v["final_qty"] * r["end_prices"][s]
                      - v["final_value"]) < RUPEE_TOL)
            check("accounting", f"{tag}/{s}: no short position",
                  v["final_qty"] >= 0)

        # ledger arithmetic. price is stored to two decimals, so a position of
        # n shares carries up to n/200 rupees of rounding.
        for det in r["ledger"]:
            wsum = sum(x["weight_after"] for x in det["rows"])
            check("ledger", f"{tag} {det['date'][:4]}: weights sum to 100",
                  abs(wsum - 100.0) < WEIGHT_TOL, f"{wsum:.2f}")
            for x in det["rows"]:
                check("ledger",
                      f"{tag} {det['date'][:4]}/{x['symbol']}: qty rolls forward",
                      x["qty_before"] + x["units"] == x["qty_after"])
                tol = x["qty_after"] / 200.0 + RUPEE_TOL
                check("ledger",
                      f"{tag} {det['date'][:4]}/{x['symbol']}: value = qty x price",
                      abs(x["qty_after"] * x["price"] - x["value_after"]) < tol)
            held = sum(x["value_after"] for x in det["rows"])
            slack = sum(x["qty_after"] for x in det["rows"]) / 200.0 + RUPEE_TOL
            check("ledger", f"{tag} {det['date'][:4]}: portfolio adds up",
                  abs(held + det["cash_after"] - det["value_after"]) < slack,
                  f"{held:.0f} + {det['cash_after']:.0f} vs "
                  f"{det['value_after']:.0f}")

        # cash is never negative at a decision point
        check("accounting", f"{tag}: cash never goes negative",
              all(d["cash_after"] >= -RUPEE_TOL for d in r["ledger"]))

        # per-symbol money moved must match the ledger
        for s in r["per_symbol"]:
            net = sum(next(x for x in d["rows"] if x["symbol"] == s)["amount"]
                      for d in r["ledger"])
            book = r["per_symbol"][s]["buy_value"] - r["per_symbol"][s]["sell_value"]
            check("ledger", f"{tag}/{s}: ledger amounts match trade totals",
                  abs(net - book) < len(r["ledger"]) + RUPEE_TOL,
                  f"{net:.0f} vs {book:.0f}")

        # XIRR recomputed from scratch
        flows = [(pd.Timestamp(d["date"]).date(), -contribution)
                 for d in r["ledger"]]
        flows.append((pd.Timestamp(r["end"]).date(), r["net_value"]))
        rate = bt.xirr(flows)
        check("xirr", f"{tag}: XIRR net reproduces",
              rate is not None and abs(rate * 100 - r["xirr_net_pct"]) < 0.01,
              f"recomputed {rate * 100:.4f} vs stored {r['xirr_net_pct']:.4f}")
        npv = sum(cf / (1 + rate) ** ((d - flows[0][0]).days / 365.0)
                  for d, cf in flows)
        check("xirr", f"{tag}: NPV at reported XIRR is zero", abs(npv) < 1.0,
              f"NPV {npv:.4f}")

        check("accounting", f"{tag}: exit tax is non-negative",
              r["exit_tax"] >= 0)
        check("accounting", f"{tag}: net value below paper value",
              r["net_value"] <= r["paper_value"] + RUPEE_TOL)

    return {r["strategy"]: r for r in runs}


# ------------------------------------------------------------------ C. json

def verify_json(tag: str, files: List[str], live: dict) -> None:
    payloads = {}
    for f in files:
        p = DATA / f
        if not p.exists():
            check("json", f"{f} exists", False)
            continue
        payloads[f] = json.loads(p.read_text())
        check("json", f"{f} exists", True)

    if not payloads:
        return

    base = payloads[files[0]]
    for f, doc in payloads.items():
        check("json", f"{f}: basket matches", doc["basket"] == base["basket"])
        check("json", f"{f}: window matches",
              doc["start"] == base["start"] and doc["end"] == base["end"])
        check("json", f"{f}: uses the adjusted archive",
              doc.get("price_source") == ARCHIVE.name,
              str(doc.get("price_source")))
        check("json", f"{f}: five strategies present",
              len(doc["results"]) == 5)

    # the stored main run must equal a fresh in-process run
    for r in base["results"]:
        fresh = live.get(r["strategy"])
        if fresh is None:
            check("json", f"{r['strategy']}: present in live run", False)
            continue
        check("reproducible", f"{tag}/{r['strategy']}: value reproduces",
              abs(fresh["paper_value"] - r["paper_value"]) < RUPEE_TOL,
              f"{fresh['paper_value']:.0f} vs {r['paper_value']:.0f}")
        check("reproducible", f"{tag}/{r['strategy']}: XIRR reproduces",
              abs(fresh["xirr_net_pct"] - r["xirr_net_pct"]) < 0.001)
        check("reproducible", f"{tag}/{r['strategy']}: tax reproduces",
              abs(fresh["tax_total"] - r["tax_total"]) < RUPEE_TOL)


def verify_tax_regime() -> None:
    from datetime import date
    cases = [
        (date(2012, 6, 1), 0.0, "LTCG exempt before Apr 2018"),
        (date(2019, 6, 1), 10.0, "LTCG 10% from Apr 2018"),
        (date(2025, 6, 1), 12.5, "LTCG 12.5% from 23 Jul 2024"),
    ]
    for d, expect, label in cases:
        check("tax", label, abs(bt.ltcg_rate_pct(d) - expect) < 1e-9,
              f"{bt.ltcg_rate_pct(d)}")
    check("tax", "STCG 15% before 23 Jul 2024",
          abs(bt.stcg_rate_pct(date(2020, 1, 1)) - 15.0) < 1e-9)
    check("tax", "STCG 20% after 23 Jul 2024",
          abs(bt.stcg_rate_pct(date(2025, 1, 1)) - 20.0) < 1e-9)
    check("tax", "LTCG exemption 1.25 lakh after 23 Jul 2024",
          abs(bt.ltcg_exemption(date(2025, 1, 1)) - 125000.0) < 1e-9)
    check("tax", "financial year starts in April",
          bt.financial_year(date(2024, 3, 31)) == 2023
          and bt.financial_year(date(2024, 4, 1)) == 2024)


# ------------------------------------------------------------------- report

def main() -> None:
    symbols = bt.BASKETS["v2"]
    verify_archive(symbols, "2011-01-01")
    verify_archive_vs_store(symbols, "2011-01-01")
    verify_tax_regime()
    live = verify_engine("v2", "2011-01-01", 100000.0)
    verify_json("v2", ["v2_main.json", "v2_nri.json", "v2_div.json"], live)

    order, seen = [], set()
    for section, _n, _ok, _d in results:
        if section not in seen:
            seen.add(section)
            order.append(section)

    lines = []
    total_fail = 0
    for section in order:
        rows = [r for r in results if r[0] == section]
        failed = [r for r in rows if not r[2]]
        total_fail += len(failed)
        lines.append(f"{section:<14} {len(rows) - len(failed):>4} passed"
                     f"{'':4}{len(failed):>3} failed")
        for _s, name, _ok, detail in failed:
            lines.append(f"    FAIL  {name}" + (f"  [{detail}]" if detail else ""))

    head = [f"checks run : {len(results)}",
            f"failed     : {total_fail}",
            ""]
    out = "\n".join(head + lines)
    print(out)
    (ROOT / "research" / "data" / "verification_report.txt").write_text(out)
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
