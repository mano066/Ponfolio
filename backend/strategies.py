"""
strategies.py — Simple but REAL rules-based backtests over the Nifty50 universe.

Each strategy:
  - Selects picks from the Nifty50 universe on a rule (momentum / low-vol / value proxy).
  - Backtests over the last ~3 years of daily data, equal-weighted, quarterly rebalance.
  - Computes cagr_3y (%), max_drawdown (%), win_rate (% of rebalance periods that beat
    the ^NSEI benchmark), current holdings (latest-period picks), and benchmark_cagr.

All yfinance access is guarded; a strategy that cannot be computed is dropped from the
result. If everything fails, an empty list is returned.
"""

import datetime
import math

import pandas as pd
import yfinance as yf


BENCHMARK = "^NSEI"
_TRADING_DAYS = 252


def _cagr(start_val: float, end_val: float, years: float) -> float:
    """Compound annual growth rate as a percentage. None if not computable."""
    if start_val is None or end_val is None or start_val <= 0 or years <= 0:
        return None
    try:
        return round(((end_val / start_val) ** (1.0 / years) - 1.0) * 100, 2)
    except Exception:
        return None


def _max_drawdown_pct(value_series: pd.Series) -> float:
    """Maximum peak-to-trough drawdown of an equity curve, as a negative %."""
    if value_series is None or len(value_series) < 2:
        return None
    running_max = value_series.cummax()
    drawdown = (value_series - running_max) / running_max
    return round(float(drawdown.min()) * 100, 2)


def _download_universe(symbols: list, years: int = 3) -> pd.DataFrame:
    """Download all universe + benchmark closes once. Returns a wide close DataFrame."""
    all_syms = list(dict.fromkeys(symbols + [BENCHMARK]))
    period = f"{years}y"
    data = yf.download(all_syms, period=period, group_by="ticker", progress=False, threads=True)
    closes = {}
    for sym in all_syms:
        try:
            s = data[sym]["Close"].dropna()
            if len(s) > 0:
                closes[sym] = s
        except Exception:
            continue
    if not closes:
        return pd.DataFrame()
    df = pd.DataFrame(closes)
    # Forward-fill small gaps, then drop rows where the benchmark is missing
    df = df.sort_index()
    return df


def _quarter_start_indices(index: pd.DatetimeIndex) -> list:
    """Return positional indices marking the first trading day of each quarter."""
    marks = []
    last_q = None
    for i, ts in enumerate(index):
        q = (ts.year, (ts.month - 1) // 3)
        if q != last_q:
            marks.append(i)
            last_q = q
    return marks


def _trailing_return(series: pd.Series, lookback: int) -> float:
    """Trailing return over `lookback` rows ending at the last available value."""
    s = series.dropna()
    if len(s) < lookback + 1:
        if len(s) < 2:
            return None
        lookback = len(s) - 1
    start = float(s.iloc[-lookback - 1])
    end = float(s.iloc[-1])
    if start <= 0:
        return None
    return end / start - 1.0


def _pick_momentum(hist: pd.DataFrame, universe: list, top_n: int = 5) -> list:
    """Top N by trailing 12-month (~252d) return."""
    scored = []
    for sym in universe:
        if sym not in hist.columns:
            continue
        r = _trailing_return(hist[sym], _TRADING_DAYS)
        if r is not None:
            scored.append((sym, r))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in scored[:top_n]]


def _pick_low_vol(hist: pd.DataFrame, universe: list, top_n: int = 5) -> list:
    """Bottom N by trailing 1Y daily-return stddev."""
    scored = []
    for sym in universe:
        if sym not in hist.columns:
            continue
        s = hist[sym].dropna().iloc[-_TRADING_DAYS:]
        if len(s) < 30:
            continue
        vol = float(s.pct_change().dropna().std())
        if not math.isnan(vol):
            scored.append((sym, vol))
    scored.sort(key=lambda x: x[1])
    return [s for s, _ in scored[:top_n]]


def _pick_quality_value(hist: pd.DataFrame, universe: list, top_n: int = 5) -> list:
    """Approximation: top N by trailing 6-month (~126d) return among the universe."""
    scored = []
    for sym in universe:
        if sym not in hist.columns:
            continue
        r = _trailing_return(hist[sym], _TRADING_DAYS // 2)
        if r is not None:
            scored.append((sym, r))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in scored[:top_n]]


def _backtest(hist: pd.DataFrame, universe: list, picker, top_n: int = 5):
    """Equal-weighted, quarterly-rebalanced backtest.

    Returns (equity_curve: pd.Series, period_returns, benchmark_period_returns,
             latest_picks: list). None on failure.
    """
    if hist.empty or BENCHMARK not in hist.columns:
        return None
    df = hist.dropna(subset=[BENCHMARK])
    if len(df) < _TRADING_DAYS:  # need at least ~1Y so trailing lookbacks work
        return None

    q_marks = _quarter_start_indices(df.index)
    # Need at least one rebalance with a full lookback window behind it.
    # Start rebalancing only after we have ~1Y of lookback history.
    min_start_pos = _TRADING_DAYS
    reb_positions = [p for p in q_marks if p >= min_start_pos]
    if len(reb_positions) < 2:
        return None

    equity = 1.0
    equity_points = []          # (timestamp, equity)
    period_returns = []         # strategy return each rebalance period
    bench_period_returns = []   # benchmark return each rebalance period
    latest_picks = []

    for i, start_pos in enumerate(reb_positions):
        end_pos = reb_positions[i + 1] if i + 1 < len(reb_positions) else len(df) - 1
        if end_pos <= start_pos:
            continue
        lookback_hist = df.iloc[: start_pos + 1]
        picks = picker(lookback_hist, universe, top_n)
        picks = [p for p in picks if p in df.columns]
        if not picks:
            continue
        latest_picks = picks  # last non-empty pick set = current holdings

        # Equal-weighted return over this period
        start_prices = df[picks].iloc[start_pos]
        end_prices = df[picks].iloc[end_pos]
        rets = (end_prices / start_prices - 1.0).dropna()
        if len(rets) == 0:
            continue
        period_ret = float(rets.mean())
        period_returns.append(period_ret)
        equity *= (1.0 + period_ret)
        equity_points.append((df.index[end_pos], equity))

        # Benchmark return over the same window
        b_start = float(df[BENCHMARK].iloc[start_pos])
        b_end = float(df[BENCHMARK].iloc[end_pos])
        bench_period_returns.append((b_end / b_start - 1.0) if b_start > 0 else 0.0)

    if not equity_points:
        return None

    curve = pd.Series([v for _, v in equity_points], index=[t for t, _ in equity_points])
    # Prepend the starting point (equity = 1.0) for a correct drawdown curve
    curve = pd.concat([pd.Series([1.0], index=[df.index[reb_positions[0]]]), curve])
    return curve, period_returns, bench_period_returns, latest_picks


def _win_rate(period_returns: list, bench_returns: list) -> float:
    """% of rebalance periods where the strategy beat the benchmark."""
    n = min(len(period_returns), len(bench_returns))
    if n == 0:
        return None
    wins = sum(1 for i in range(n) if period_returns[i] > bench_returns[i])
    return round(wins / n * 100, 1)


def _benchmark_cagr(hist: pd.DataFrame, years: int = 3) -> float:
    if hist.empty or BENCHMARK not in hist.columns:
        return None
    s = hist[BENCHMARK].dropna()
    if len(s) < 2:
        return None
    span_years = (s.index[-1] - s.index[0]).days / 365.25
    span_years = span_years if span_years > 0 else years
    return _cagr(float(s.iloc[0]), float(s.iloc[-1]), span_years)


_STRATEGY_DEFS = [
    {
        "id": "momentum",
        "name": "Momentum",
        "description": "Top 5 Nifty50 stocks by trailing 12-month return, rebalanced quarterly.",
        "risk_label": "High",
        "picker": _pick_momentum,
    },
    {
        "id": "low_volatility",
        "name": "Low Volatility",
        "description": "5 Nifty50 stocks with the lowest trailing 1-year daily-return volatility, rebalanced quarterly.",
        "risk_label": "Low",
        "picker": _pick_low_vol,
    },
    {
        "id": "quality_value",
        "name": "Quality Value",
        "description": "Top 5 large-cap Nifty50 stocks by trailing 6-month return (quality-value proxy), rebalanced quarterly.",
        "risk_label": "Medium",
        "picker": _pick_quality_value,
    },
]


def run_strategies(universe: list, name_by_symbol: dict = None, years: int = 3) -> list:
    """Backtest all defined strategies over `universe` (list of .NS symbols).

    `name_by_symbol` maps symbol -> readable name for holdings output.
    Returns a list of strategy result dicts. Empty list if all fail.
    """
    name_by_symbol = name_by_symbol or {}
    as_of = datetime.date.today().isoformat()

    try:
        hist = _download_universe(universe, years=years)
    except Exception as e:
        print(f"[Strategies] Universe download failed: {e}")
        return []
    if hist.empty:
        return []

    bench_cagr = _benchmark_cagr(hist, years=years)

    def _readable(sym: str) -> str:
        return name_by_symbol.get(sym, sym.replace(".NS", "").replace(".BO", ""))

    results = []
    for sdef in _STRATEGY_DEFS:
        try:
            bt = _backtest(hist, universe, sdef["picker"], top_n=5)
            if bt is None:
                continue
            curve, period_returns, bench_returns, latest_picks = bt
            span_years = (curve.index[-1] - curve.index[0]).days / 365.25
            span_years = span_years if span_years > 0 else years
            cagr = _cagr(float(curve.iloc[0]), float(curve.iloc[-1]), span_years)
            mdd = _max_drawdown_pct(curve)
            wr = _win_rate(period_returns, bench_returns)
            holdings = [{"symbol": s.replace(".NS", "").replace(".BO", ""), "name": _readable(s)}
                        for s in latest_picks]
            results.append({
                "id": sdef["id"],
                "name": sdef["name"],
                "description": sdef["description"],
                "risk_label": sdef["risk_label"],
                "cagr_3y": cagr,
                "benchmark_cagr": bench_cagr,
                "max_drawdown": mdd,
                "win_rate": wr,
                "holdings": holdings,
                "as_of_date": as_of,
            })
        except Exception as e:
            print(f"[Strategies] Backtest failed for {sdef['id']}: {e}")
            continue

    return results
