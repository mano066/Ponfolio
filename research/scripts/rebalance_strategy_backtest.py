"""Compare 5 rebalancing strategies on a fixed 10-stock basket, 2010 -> latest.

Rules held constant across every strategy so the only variable is the
rebalancing policy:
  * Year 1: Rs 1,00,000 split Rs 10,000 into each of 10 stocks.
  * Every anniversary after that: another Rs 1,00,000 of fresh money, deployed
    the way that strategy says.
  * Nothing is ever sold before it is 365 days old (your "1 year mature" rule).
  * Whole shares only, leftover rupees sit in cash.
  * Costs and Indian capital-gains tax are charged with the rates that were
    actually in force on the trade date, including the 31-Jan-2018
    grandfathering step-up.

Prices are split/bonus adjusted closes from dataset/store/daily. Dividends are
excluded unless --dividend-yield is passed.

Usage:
    py -3.9 research/scripts/rebalance_strategy_backtest.py
    py -3.9 research/scripts/rebalance_strategy_backtest.py --basket mixed10
    py -3.9 research/scripts/rebalance_strategy_backtest.py --residency nri
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PRICE_DIR = ROOT / "dataset" / "store" / "daily"
OUT_DIR = ROOT / "research" / "data"

BASKETS = {
    # Nifty large caps that were all listed and liquid on 2010-01-04.
    "large10": [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "ITC", "HINDUNILVR", "LT", "SUNPHARMA", "MARUTI",
    ],
    # Deliberately includes long-term laggards. Rebalancing rules only earn
    # their keep when the basket contains losers, so this is the honest test.
    "mixed10": [
        "RELIANCE", "TCS", "HDFCBANK", "ITC", "LT",
        "ONGC", "SBIN", "TATASTEEL", "BHEL", "NTPC",
    ],
    # PSU / cyclical / small-bank basket. COALINDIA listed 2010-11-04, which
    # is what sets the start date for this run.
    "v2": [
        "BHEL", "COALINDIA", "IOC", "ITC", "KTKBANK",
        "ONGC", "SCI", "NTPC", "TATASTEEL", "SOUTHBANK",
    ],
}

LONG_TERM_DAYS = 365
GRANDFATHER_DATE = pd.Timestamp("2018-01-31")
CESS_PCT = 4.0


# ---------------------------------------------------------------- tax rules

def ltcg_rate_pct(d: date) -> float:
    """Listed-equity LTCG rate in force on `d` (before cess)."""
    if d < date(2018, 4, 1):
        return 0.0            # s.10(38) exemption
    if d < date(2024, 7, 23):
        return 10.0
    return 12.5


def ltcg_exemption(d: date) -> float:
    """Per-financial-year LTCG exemption in force on `d`."""
    if d < date(2018, 4, 1):
        return 0.0            # irrelevant, rate is zero
    if d < date(2024, 7, 23):
        return 100000.0
    return 125000.0


def stcg_rate_pct(d: date) -> float:
    return 15.0 if d < date(2024, 7, 23) else 20.0


def financial_year(d: date) -> int:
    return d.year if d.month >= 4 else d.year - 1


def nri_surcharge_pct(gain: float) -> float:
    if gain > 10_000_000:
        return 15.0
    if gain > 5_000_000:
        return 10.0
    return 0.0


# ------------------------------------------------------------------- ledger

@dataclass
class Lot:
    bought: date
    qty: int
    price: float


@dataclass
class Trade:
    day: date
    symbol: str
    side: str
    qty: int
    price: float
    value: float
    gain: float = 0.0
    tax: float = 0.0
    note: str = ""


@dataclass
class Book:
    symbols: List[str]
    cost_bps: float
    residency: str
    grandfather_fmv: Dict[str, float]
    lots: Dict[str, List[Lot]] = field(default_factory=dict)
    cash: float = 0.0
    tax_paid: float = 0.0
    realised_gain: float = 0.0
    costs_paid: float = 0.0
    buy_value: float = 0.0
    sell_value: float = 0.0
    exemption_used: Dict[int, float] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)

    def __post_init__(self) -> None:
        for s in self.symbols:
            self.lots.setdefault(s, [])

    # -- positions -------------------------------------------------------
    def qty(self, symbol: str) -> int:
        return sum(l.qty for l in self.lots[symbol])

    def cost_basis(self, symbol: str) -> float:
        return sum(l.qty * l.price for l in self.lots[symbol])

    def holdings_value(self, px: pd.Series) -> float:
        return sum(self.qty(s) * float(px[s]) for s in self.symbols)

    def total_value(self, px: pd.Series) -> float:
        return self.holdings_value(px) + self.cash

    def weights(self, px: pd.Series) -> Dict[str, float]:
        total = self.holdings_value(px)
        if total <= 0:
            return {s: 0.0 for s in self.symbols}
        return {s: self.qty(s) * float(px[s]) / total * 100.0 for s in self.symbols}

    def long_term_qty(self, symbol: str, day: date) -> int:
        return sum(l.qty for l in self.lots[symbol]
                   if (day - l.bought).days > LONG_TERM_DAYS)

    # -- trading ---------------------------------------------------------
    def buy(self, symbol: str, rupees: float, price: float, day: date,
            note: str = "") -> int:
        unit = price * (1.0 + self.cost_bps / 10000.0)
        qty = int(rupees // unit) if unit > 0 else 0
        if qty <= 0:
            return 0
        gross = qty * price
        cost = gross * self.cost_bps / 10000.0
        self.cash -= gross + cost
        self.costs_paid += cost
        self.buy_value += gross
        self.lots[symbol].append(Lot(bought=day, qty=qty, price=price))
        self.trades.append(Trade(day, symbol, "BUY", qty, price, gross, note=note))
        return qty

    def sell(self, symbol: str, qty_wanted: int, price: float, day: date,
             long_term_only: bool = True, note: str = "") -> int:
        """FIFO sale. Returns units actually sold; proceeds land in cash."""
        if qty_wanted <= 0:
            return 0
        eligible = [l for l in self.lots[symbol]
                    if not long_term_only or (day - l.bought).days > LONG_TERM_DAYS]
        available = sum(l.qty for l in eligible)
        qty = min(qty_wanted, available)
        if qty <= 0:
            return 0

        left = qty
        gain = 0.0
        st_gain = 0.0
        lt_gain = 0.0
        for lot in list(self.lots[symbol]):
            if left <= 0:
                break
            if long_term_only and (day - lot.bought).days <= LONG_TERM_DAYS:
                continue
            take = min(left, lot.qty)
            basis = lot.price
            long_term = (day - lot.bought).days > LONG_TERM_DAYS
            if long_term and pd.Timestamp(lot.bought) < GRANDFATHER_DATE:
                fmv = self.grandfather_fmv.get(symbol)
                if fmv:
                    basis = max(basis, min(fmv, price))
            lot_gain = (price - basis) * take
            if long_term:
                lt_gain += lot_gain
            else:
                st_gain += lot_gain
            gain += lot_gain
            lot.qty -= take
            left -= take
        self.lots[symbol] = [l for l in self.lots[symbol] if l.qty > 0]

        gross = qty * price
        cost = gross * self.cost_bps / 10000.0
        tax = self._tax(lt_gain, st_gain, day)
        self.cash += gross - cost - tax
        self.costs_paid += cost
        self.sell_value += gross
        self.tax_paid += tax
        self.realised_gain += gain
        self.trades.append(Trade(day, symbol, "SELL", qty, price, gross,
                                 gain=gain, tax=tax, note=note))
        return qty

    def _tax(self, lt_gain: float, st_gain: float, day: date) -> float:
        total = 0.0
        if lt_gain > 0:
            rate = ltcg_rate_pct(day)
            if rate > 0:
                fy = financial_year(day)
                allowance = ltcg_exemption(day)
                used = self.exemption_used.get(fy, 0.0)
                shielded = max(0.0, min(lt_gain, allowance - used))
                self.exemption_used[fy] = used + shielded
                taxable = lt_gain - shielded
                base = taxable * rate / 100.0
                if self.residency == "nri":
                    base *= 1.0 + nri_surcharge_pct(lt_gain) / 100.0
                total += base * (1.0 + CESS_PCT / 100.0)
        if st_gain > 0:
            base = st_gain * stcg_rate_pct(day) / 100.0
            if self.residency == "nri":
                base *= 1.0 + nri_surcharge_pct(st_gain) / 100.0
            total += base * (1.0 + CESS_PCT / 100.0)
        return total

    def deferred_tax(self, px: pd.Series, day: date) -> float:
        """Tax that would fall due if everything were sold today."""
        lt_gain = 0.0
        st_gain = 0.0
        for s in self.symbols:
            price = float(px[s])
            for lot in self.lots[s]:
                basis = lot.price
                long_term = (day - lot.bought).days > LONG_TERM_DAYS
                if long_term and pd.Timestamp(lot.bought) < GRANDFATHER_DATE:
                    fmv = self.grandfather_fmv.get(s)
                    if fmv:
                        basis = max(basis, min(fmv, price))
                g = (price - basis) * lot.qty
                if long_term:
                    lt_gain += g
                else:
                    st_gain += g
        return self._tax(lt_gain, st_gain, day)


# ------------------------------------------------------------------ helpers

# The per-symbol parquet store is only partly adjusted: some files never had a
# split or bonus applied, and at least one has a second instrument merged into
# it. This archive carries an explicit adjusted_close and verifies clean.
PRICE_ARCHIVE = ROOT / "research" / "data" / "nse_universe_2010_ohlcv.csv.gz"
SUSPECT_MOVE_PCT = 30.0


def load_prices(symbols: Sequence[str],
                start: str) -> Tuple[pd.DataFrame, Dict[str, dict]]:
    if not PRICE_ARCHIVE.exists():
        raise SystemExit(f"Missing price archive {PRICE_ARCHIVE}")
    wanted = set(symbols)
    raw = pd.read_csv(PRICE_ARCHIVE,
                      usecols=["date", "symbol", "adjusted_close"])
    raw = raw[raw["symbol"].isin(wanted)]
    missing = sorted(wanted - set(raw["symbol"].unique()))
    if missing:
        raise SystemExit(f"No price history for: {', '.join(missing)}")

    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
    series, first_seen, report = {}, {}, {}
    for s in symbols:
        g = raw[raw["symbol"] == s].sort_values("date")
        ser = pd.Series(g["adjusted_close"].to_numpy(dtype="float64"),
                        index=g["date"])
        ser = ser[~ser.index.duplicated(keep="last")]
        ser = ser[ser > 0]
        ser = ser.loc[ser.index >= pd.Timestamp(start)]
        if ser.empty:
            raise SystemExit(f"No price history for {s} after {start}")
        moves = ser.pct_change().abs() * 100.0
        flagged = moves[moves >= SUSPECT_MOVE_PCT]
        report[s] = {
            "bars": int(len(ser)),
            "max_move_pct": round(float(moves.max()), 1),
            "suspect_moves": [{"date": str(d.date()),
                               "move_pct": round(float(v), 1)}
                              for d, v in flagged.items()],
        }
        series[s] = ser
        first_seen[s] = ser.index[0]

    flagged_any = {s: r for s, r in report.items() if r["suspect_moves"]}
    if flagged_any:
        print(f"Note     : single-day moves of {SUSPECT_MOVE_PCT:.0f}% or more "
              f"(left in the data, listed so they can be checked):")
        for s, r in flagged_any.items():
            for m in r["suspect_moves"]:
                print(f"           {s} {m['date']}  {m['move_pct']:+.1f}%")

    requested = pd.Timestamp(start)
    binding = max(first_seen, key=lambda s: first_seen[s])
    if first_seen[binding] > requested:
        print(f"Note     : {binding} has no price before "
              f"{first_seen[binding].date()}, so the test starts there, "
              f"not {requested.date()}.")
        for s in sorted(first_seen, key=lambda k: first_seen[k], reverse=True)[:3]:
            print(f"           {s} first traded {first_seen[s].date()}")

    px = pd.DataFrame(series).sort_index().ffill()
    px = px.loc[px.index >= requested].dropna()
    if px.empty:
        raise SystemExit("No overlapping price history for this basket.")
    return px, report


def grandfather_prices(px: pd.DataFrame) -> Dict[str, float]:
    """Last cleaned close on or before 31 Jan 2018, per symbol."""
    upto = px.loc[px.index <= GRANDFATHER_DATE]
    if upto.empty:
        return {}
    return {s: float(upto[s].iloc[-1]) for s in px.columns}


def anniversary_rows(px: pd.DataFrame) -> List[pd.Timestamp]:
    """First trading day on/after each anniversary of the first bar."""
    first = px.index[0]
    days: List[pd.Timestamp] = [first]
    year = 1
    while True:
        try:
            target = first.replace(year=first.year + year)
        except ValueError:                       # 29 Feb start
            target = first.replace(year=first.year + year, day=28)
        later = px.index[px.index >= target]
        if len(later) == 0:
            break
        days.append(later[0])
        year += 1
    return days


def xirr(flows: List[tuple], guess_lo: float = -0.95, guess_hi: float = 5.0) -> Optional[float]:
    if len(flows) < 2:
        return None
    base = flows[0][0]

    def npv(rate: float) -> float:
        total = 0.0
        for when, amount in flows:
            years = (when - base).days / 365.0
            total += amount / ((1.0 + rate) ** years)
        return total

    lo, hi = guess_lo, guess_hi
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            return mid
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def trailing_return(px: pd.DataFrame, day: pd.Timestamp, symbol: str,
                    days: int) -> Optional[float]:
    past = px.index[px.index <= day - pd.Timedelta(days=days)]
    if len(past) == 0:
        return None
    then = float(px.loc[past[-1], symbol])
    now = float(px.loc[day, symbol])
    if then <= 0:
        return None
    return (now / then - 1.0) * 100.0


def trailing_cagr(px: pd.DataFrame, day: pd.Timestamp, symbol: str,
                  years: int) -> Optional[float]:
    r = trailing_return(px, day, symbol, 365 * years)
    if r is None:
        return None
    return ((1.0 + r / 100.0) ** (1.0 / years) - 1.0) * 100.0


def deploy_to_underweight(book: Book, px_row: pd.Series, day: pd.Timestamp,
                          candidates: Sequence[str], target_pct: float,
                          note: str) -> None:
    """Waterfall: top up the most underweight names first, then spread the rest."""
    budget = book.cash
    if budget <= 0 or not candidates:
        return
    total_after = book.holdings_value(px_row) + budget
    gaps = []
    for s in candidates:
        want = total_after * target_pct / 100.0
        have = book.qty(s) * float(px_row[s])
        if want > have:
            gaps.append((want - have, s))
    gaps.sort(reverse=True)
    for gap, s in gaps:
        if book.cash <= 0:
            break
        book.buy(s, min(gap, book.cash), float(px_row[s]), day.date(), note)
    # leftover rupees spread evenly so nothing idles
    for _ in range(3):
        spendable = [s for s in candidates
                     if book.cash >= float(px_row[s]) * 1.01]
        if not spendable:
            break
        slice_size = book.cash / len(spendable)
        for s in spendable:
            book.buy(s, min(slice_size, book.cash), float(px_row[s]), day.date(), note)


# --------------------------------------------------------------- strategies

def strat_buy_and_hold(book: Book, px: pd.DataFrame, day: pd.Timestamp,
                       first: bool) -> None:
    row = px.loc[day]
    per = book.cash / len(book.symbols)
    for s in book.symbols:
        book.buy(s, per, float(row[s]), day.date(), "equal split")
    deploy_to_underweight(book, row, day, book.symbols, 100.0 / len(book.symbols),
                          "sweep")


def strat_cashflow_only(book: Book, px: pd.DataFrame, day: pd.Timestamp,
                        first: bool) -> None:
    row = px.loc[day]
    deploy_to_underweight(book, row, day, book.symbols,
                          100.0 / len(book.symbols), "top-up underweight")


def strat_band_rebalance(book: Book, px: pd.DataFrame, day: pd.Timestamp,
                         first: bool, band: float = 0.25) -> None:
    row = px.loc[day]
    target = 100.0 / len(book.symbols)
    if not first:
        total = book.holdings_value(row)
        ceiling = target * (1.0 + band)
        for s in book.symbols:
            price = float(row[s])
            weight = book.qty(s) * price / total * 100.0 if total > 0 else 0.0
            if weight > ceiling:
                excess = (weight - target) / 100.0 * total
                book.sell(s, int(excess // price), price, day.date(),
                          long_term_only=True, note="trim to target")
    deploy_to_underweight(book, row, day, book.symbols, target, "restore target")


def strat_rulebook(book: Book, px: pd.DataFrame, day: pd.Timestamp,
                   first: bool) -> None:
    """Your PDF's annual review, with price-based proxies for the FA score.

    Proxies (no point-in-time fundamentals exist for 2010-2026):
      quality  -> trailing 5-year price CAGR   (negative = "score below 6")
      value    -> trailing 12-month return     (lowest = "PE below sector median")
    """
    row = px.loc[day]
    target = 100.0 / len(book.symbols)
    blocked: set = set()

    if not first:
        total = book.holdings_value(row)
        for s in book.symbols:
            price = float(row[s])
            qty = book.qty(s)
            cagr5 = trailing_cagr(px, day, s, 5)
            basis = book.cost_basis(s)
            ret = ((qty * price) / basis - 1.0) * 100.0 if basis > 0 else 0.0

            # Action 3 - exit completely
            if cagr5 is not None and cagr5 < 0 and qty > 0:
                book.sell(s, qty, price, day.date(), long_term_only=True,
                          note="exit: 5y CAGR negative")
                blocked.add(s)
                continue
            # Action 2 - partial sell, take profit above +100%
            weight = qty * price / total * 100.0 if total > 0 else 0.0
            if ret > 100.0 and weight > target:
                excess = (weight - target) / 100.0 * total
                book.sell(s, int(excess // price), price, day.date(),
                          long_term_only=True, note="partial sell: +100%")

    # Action 1 - buy/add: skip exited names and anything down more than 10%
    adds = []
    for s in book.symbols:
        if s in blocked:
            continue
        basis = book.cost_basis(s)
        qty = book.qty(s)
        if basis > 0:
            ret = ((qty * float(row[s])) / basis - 1.0) * 100.0
            if ret < -10.0:
                continue
        adds.append(s)
    if not adds:
        adds = [s for s in book.symbols if s not in blocked] or list(book.symbols)
    # cheapest-first within the eligible set
    adds.sort(key=lambda s: trailing_return(px, day, s, 365) or 0.0)
    deploy_to_underweight(book, row, day, adds, 100.0 / len(adds), "buy/add")


def strat_momentum(book: Book, px: pd.DataFrame, day: pd.Timestamp,
                   first: bool, top_n: int = 3) -> None:
    row = px.loc[day]
    if first:
        per = book.cash / len(book.symbols)
        for s in book.symbols:
            book.buy(s, per, float(row[s]), day.date(), "equal split")
        deploy_to_underweight(book, row, day, book.symbols,
                              100.0 / len(book.symbols), "sweep")
        return
    ranked = sorted(book.symbols,
                    key=lambda s: trailing_return(px, day, s, 365) or -999.0,
                    reverse=True)
    winners = ranked[:top_n]
    per = book.cash / len(winners)
    for s in winners:
        book.buy(s, per, float(row[s]), day.date(), "add to winner")
    deploy_to_underweight(book, row, day, winners, 100.0 / len(winners), "sweep")


STRATEGIES: Dict[str, tuple] = {
    "S1 Buy & Hold": (
        strat_buy_and_hold,
        "Never sell. Every year the new Rs 1L is split equally over all 10.",
    ),
    "S2 Cash-Flow Rebalance": (
        strat_cashflow_only,
        "Never sell. New money goes only to the most underweight names.",
    ),
    "S3 Band Rebalance": (
        strat_band_rebalance,
        "Trim anything above target x1.25 back to target, then top up the rest.",
    ),
    "S4 Rulebook (your PDF)": (
        strat_rulebook,
        "Exit weak compounders, take profit above +100%, add to the cheap ones.",
    ),
    "S5 Momentum Tilt": (
        strat_momentum,
        "Never sell. New money goes to the top 3 by 12-month return.",
    ),
}


# ------------------------------------------------------------------- engine

def run_strategy(name: str, fn: Callable, px: pd.DataFrame, contribution: float,
                 cost_bps: float, residency: str,
                 dividend_yield: float) -> dict:
    symbols = list(px.columns)
    book = Book(symbols=symbols, cost_bps=cost_bps, residency=residency,
                grandfather_fmv=grandfather_prices(px))

    rebal_days = anniversary_rows(px)
    flows: List[tuple] = []
    yearly: List[dict] = []
    ledger: List[dict] = []

    last_dividend_day = rebal_days[0]
    for i, day in enumerate(rebal_days):
        row = px.loc[day]
        if dividend_yield > 0 and i > 0:
            span = (day - last_dividend_day).days / 365.0
            book.cash += book.holdings_value(row) * dividend_yield / 100.0 * span
            last_dividend_day = day

        qty_before = {s: book.qty(s) for s in symbols}
        value_before = {s: qty_before[s] * float(row[s]) for s in symbols}
        held_before = sum(value_before.values())
        trade_mark = len(book.trades)

        book.cash += contribution
        flows.append((day.to_pydatetime().date(), -contribution))
        fn(book, px, day, i == 0)

        new_trades = book.trades[trade_mark:]
        qty_after = {s: book.qty(s) for s in symbols}
        value_after = {s: qty_after[s] * float(row[s]) for s in symbols}
        held_after = sum(value_after.values())

        rows: List[dict] = []
        for s in symbols:
            mine = [t for t in new_trades if t.symbol == s]
            bought = sum(t.qty for t in mine if t.side == "BUY")
            sold = sum(t.qty for t in mine if t.side == "SELL")
            buy_amt = sum(t.value for t in mine if t.side == "BUY")
            sell_amt = sum(t.value for t in mine if t.side == "SELL")
            tax = sum(t.tax for t in mine)
            gain = sum(t.gain for t in mine)
            if sold and qty_after[s] == 0:
                action = "EXIT"
            elif sold and bought:
                action = "SWAP"
            elif sold:
                action = "TRIM"
            elif bought:
                action = "ADD"
            else:
                action = "HOLD"
            note = next((t.note for t in mine if t.note), "")
            rows.append({
                "symbol": s,
                "price": round(float(row[s]), 2),
                "qty_before": qty_before[s],
                "value_before": round(value_before[s], 0),
                "weight_before": round(value_before[s] / held_before * 100.0, 1)
                                 if held_before > 0 else 0.0,
                "action": action,
                "units": bought - sold,
                "amount": round(buy_amt - sell_amt, 0),
                "gain": round(gain, 0),
                "tax": round(tax, 0),
                "qty_after": qty_after[s],
                "value_after": round(value_after[s], 0),
                "weight_after": round(value_after[s] / held_after * 100.0, 1)
                                if held_after > 0 else 0.0,
                "note": note,
            })

        ledger.append({
            "year": i + 1,
            "date": str(day.date()),
            "added": contribution,
            "value_before": round(held_before, 0),
            "value_after": round(book.total_value(row), 0),
            "cash_after": round(book.cash, 0),
            "tax_this_year": round(sum(t.tax for t in new_trades), 0),
            "sells_this_year": sum(1 for t in new_trades if t.side == "SELL"),
            "rows": rows,
        })
        yearly.append({
            "date": str(day.date()),
            "value": round(book.total_value(row), 0),
            "invested": round(contribution * (i + 1), 0),
            "cash": round(book.cash, 0),
            "tax_paid_cum": round(book.tax_paid, 0),
        })

    end = px.index[-1]
    end_row = px.loc[end]
    paper_value = book.total_value(end_row)
    exit_tax = book.deferred_tax(end_row, end.date())
    exit_cost = book.holdings_value(end_row) * cost_bps / 10000.0
    net_value = paper_value - exit_tax - exit_cost

    paper_flows = flows + [(end.to_pydatetime().date(), paper_value)]
    net_flows = flows + [(end.to_pydatetime().date(), net_value)]

    # daily equity curve for drawdown
    curve = []
    qty_at = {}
    for s in symbols:
        qty_at[s] = book.qty(s)
    # rebuild value path from the trade log
    holdings = {s: 0 for s in symbols}
    cash_path = 0.0
    trades_by_day: Dict[date, List[Trade]] = {}
    for t in book.trades:
        trades_by_day.setdefault(t.day, []).append(t)
    contrib_days = {d.date() for d in rebal_days}
    values = []
    for ts in px.index:
        d = ts.date()
        if d in contrib_days:
            cash_path += contribution
        for t in trades_by_day.get(d, []):
            if t.side == "BUY":
                holdings[t.symbol] += t.qty
                cash_path -= t.value * (1 + cost_bps / 10000.0)
            else:
                holdings[t.symbol] -= t.qty
                cash_path += t.value * (1 - cost_bps / 10000.0) - t.tax
        row = px.loc[ts]
        values.append(sum(holdings[s] * float(row[s]) for s in symbols) + cash_path)
    curve = pd.Series(values, index=px.index)
    peak = curve.cummax()
    drawdown = ((curve - peak) / peak.replace(0, pd.NA)).astype("float64")
    max_dd = float(drawdown.min() * 100.0) if len(drawdown) else 0.0

    invested = contribution * len(rebal_days)
    sells = [t for t in book.trades if t.side == "SELL"]

    per_symbol = {}
    for s in symbols:
        mine = [t for t in book.trades if t.symbol == s]
        final_qty = book.qty(s)
        per_symbol[s] = {
            "bought_units": sum(t.qty for t in mine if t.side == "BUY"),
            "sold_units": sum(t.qty for t in mine if t.side == "SELL"),
            "buy_value": round(sum(t.value for t in mine if t.side == "BUY"), 0),
            "sell_value": round(sum(t.value for t in mine if t.side == "SELL"), 0),
            "realised_gain": round(sum(t.gain for t in mine), 0),
            "tax": round(sum(t.tax for t in mine), 0),
            "buys": sum(1 for t in mine if t.side == "BUY"),
            "sells": sum(1 for t in mine if t.side == "SELL"),
            "final_qty": final_qty,
            "final_value": round(final_qty * float(end_row[s]), 0),
            "cost_basis": round(book.cost_basis(s), 0),
        }

    return {
        "strategy": name,
        "start": str(px.index[0].date()),
        "end": str(end.date()),
        "years": round((end - px.index[0]).days / 365.25, 1),
        "contributions": len(rebal_days),
        "invested": invested,
        "paper_value": paper_value,
        "exit_tax": exit_tax,
        "net_value": net_value,
        "multiple": paper_value / invested,
        "xirr_paper_pct": (xirr(paper_flows) or 0.0) * 100.0,
        "xirr_net_pct": (xirr(net_flows) or 0.0) * 100.0,
        "tax_paid": book.tax_paid,
        "tax_total": book.tax_paid + exit_tax,
        "costs_paid": book.costs_paid,
        "realised_gain": book.realised_gain,
        "sell_trades": len(sells),
        "sold_value": book.sell_value,
        "turnover_pct": (book.sell_value / invested * 100.0) if invested else 0.0,
        "cash_left": book.cash,
        "max_drawdown_pct": max_dd,
        "final_weights": {k: round(v, 1) for k, v in book.weights(end_row).items()},
        "start_prices": {s: round(float(px.iloc[0][s]), 2) for s in symbols},
        "end_prices": {s: round(float(end_row[s]), 2) for s in symbols},
        "per_symbol": per_symbol,
        "yearly": yearly,
        "ledger": ledger,
    }


# --------------------------------------------------------------------- main

def rupees(x: float) -> str:
    """Indian grouping, full digits, no K/L/Cr shorthand."""
    neg = x < 0
    n = int(round(abs(x)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "Rs " + s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--basket", choices=sorted(BASKETS), default="large10")
    ap.add_argument("--symbols", help="comma-separated override for the basket")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--contribution", type=float, default=100000.0)
    ap.add_argument("--cost-bps", type=float, default=12.0,
                    help="STT + exchange + stamp + GST per side, basis points")
    ap.add_argument("--residency", choices=["resident", "nri"], default="resident")
    ap.add_argument("--dividend-yield", type=float, default=0.0,
                    help="assumed annual dividend yield %%, reinvested")
    ap.add_argument("--json-out", default=str(OUT_DIR / "rebalance_backtest.json"))
    args = ap.parse_args()
    symbols = ([s.strip().upper() for s in args.symbols.split(",")]
               if args.symbols else BASKETS[args.basket])
    px, integrity = load_prices(symbols, args.start)

    print(f"Basket   : {args.basket} -> {', '.join(symbols)}")
    print(f"Window   : {px.index[0].date()} to {px.index[-1].date()}"
          f"  ({(px.index[-1] - px.index[0]).days / 365.25:.1f} years)")
    print(f"Money in : {rupees(args.contribution)} on day one, then every anniversary")
    print(f"Costs    : {args.cost_bps} bps per side | Tax: {args.residency}, "
          f"rates as they stood on each trade date")
    print()

    results = []
    for name, (fn, _desc) in STRATEGIES.items():
        results.append(run_strategy(name, fn, px, args.contribution,
                                    args.cost_bps, args.residency,
                                    args.dividend_yield))

    results.sort(key=lambda r: r["xirr_net_pct"], reverse=True)

    head = (f"{'Strategy':<24}{'Invested':>14}{'Value today':>16}"
            f"{'After exit tax':>17}{'XIRR':>8}{'XIRR net':>10}"
            f"{'Tax paid':>14}{'Max DD':>9}{'Sells':>7}")
    print(head)
    print("-" * len(head))
    for r in results:
        print(f"{r['strategy']:<24}"
              f"{rupees(r['invested']):>14}"
              f"{rupees(r['paper_value']):>16}"
              f"{rupees(r['net_value']):>17}"
              f"{r['xirr_paper_pct']:>7.2f}%"
              f"{r['xirr_net_pct']:>9.2f}%"
              f"{rupees(r['tax_total']):>14}"
              f"{r['max_drawdown_pct']:>8.1f}%"
              f"{r['sell_trades']:>7}")
    print()

    best = results[0]
    runner = results[1]
    print(f"Winner   : {best['strategy']}  "
          f"({best['xirr_net_pct']:.2f}% XIRR after exit tax)")
    print(f"Margin   : {rupees(best['net_value'] - runner['net_value'])} ahead of "
          f"{runner['strategy']}")
    print()
    print("What each rule does")
    for name, (_fn, desc) in STRATEGIES.items():
        print(f"  {name:<24} {desc}")
    print()

    print("Year-by-year portfolio value (Rs, full digits)")
    years = [y["date"] for y in results[0]["yearly"]]
    print(f"{'Date':<12}" + "".join(f"{r['strategy'][:3]:>16}" for r in results))
    for i, d in enumerate(years):
        line = f"{d:<12}"
        for r in results:
            line += f"{rupees(r['yearly'][i]['value']):>16}"
        print(line)
    print()

    print("Final weights (%)")
    for r in results:
        pairs = ", ".join(f"{k} {v}" for k, v in
                          sorted(r["final_weights"].items(),
                                 key=lambda kv: -kv[1]))
        print(f"  {r['strategy']:<24} {pairs}")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "basket": symbols,
        "start": str(px.index[0].date()),
        "end": str(px.index[-1].date()),
        "contribution": args.contribution,
        "residency": args.residency,
        "cost_bps": args.cost_bps,
        "price_source": PRICE_ARCHIVE.name,
        "integrity": integrity,
        "results": results,
    }, indent=2))
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
