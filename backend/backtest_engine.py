"""
Dip-threshold backtest — pure computation layer.

Answers one question, per benchmark, from a decade of daily closes:

    "If I had put extra money in every time this index was X% below its peak,
     what actually happened next?"

Everything here is deterministic and network-free so it can be unit-tested
without touching yfinance.  ``main.py`` supplies the closes (from the same
cached ten-year download the tape uses) and calls :func:`backtest_benchmark`.

Design notes
------------
* **A forward return that has not finished yet is ``None``, never ``0``.**  The
  last five years of any series cannot answer a five-year question.  Counting
  those days as zero would drag every long-horizon average toward nothing and
  make deep dips — which cluster late in this particular decade — look worse
  than they were.  Each horizon therefore reports its own ``n``, and a horizon
  with no completed observations reports ``None`` rather than a number.

* **Every result is quoted against a baseline of investing on a random day.**
  This is the single most important number in the module.  "Buying at -15%
  returned +18% over a year" means nothing on its own; if every random day
  returned +17%, the signal is worth one percentage point, not eighteen.  The
  ``edge`` field is the only honest way to read a dip strategy, and it is what
  stops this feature from being an elaborate way to confirm what we hoped.

* **Overlapping days in one selloff are not independent signals.**  A bear
  market spends months below -15%; counting each of those ~120 days as a
  separate signal would report a huge sample that is really one observation,
  with a confidence interval to match.  :func:`find_signals` fires once per
  episode and re-arms only after the index recovers — see
  :data:`REARM_RECOVERY_FRACTION`.

* **Thresholds are chosen out-of-sample or not at all.**  Picking the
  best-performing threshold on the whole history and then reporting how well it
  did on that same history is circular, and with five candidate thresholds and
  one lifetime of Indian equity data it is very easy to do by accident.
  :func:`walk_forward` selects on the first part of the series and scores on
  the part it never saw.

* A study built on too few episodes is labelled ``reliable=False`` and carries
  its ``n``.  It is still shown — the user asked what history says, and "only
  twice, so this is anecdote" is a real answer — but it must never be presented
  with the same authority as a thirty-signal study.
"""

from __future__ import annotations

import statistics
from typing import Sequence

# Pure, network-free sibling module; shares the series-hygiene primitive so the
# split detector cannot drift between the tape and the backtest.
import market_indices

# ── Horizons ──────────────────────────────────────────────────────────────
# Trading days, matching the tape's convention (~252 per year).
HORIZON_DAYS = {
    "3m": 63,
    "6m": 126,
    "1y": 252,
    "3y": 756,
    "5y": 1260,
}
HORIZONS = ("3m", "6m", "1y", "3y", "5y")

HORIZON_LABELS = {
    "3m": "3 months",
    "6m": "6 months",
    "1y": "1 year",
    "3y": "3 years",
    "5y": "5 years",
}

# Horizons at or beyond a year also report a compound annual rate, because a
# "+62% over five years" figure is easy to misread as a yearly number.
ANNUALISE_FROM_DAYS = 252

# ── Thresholds ────────────────────────────────────────────────────────────
# Candidate drawdown bands, in percent below the running peak.  Deliberately
# the round numbers a person would actually think in; the point of the study is
# to find which of them carried an edge for THIS index, not to discover an
# exotic cut point that only exists in one decade of noise.
DEFAULT_THRESHOLDS = (5.0, 10.0, 15.0, 20.0, 30.0)

# After a signal fires at threshold T, the index must recover to shallower than
# T * this before the threshold can fire again.  Without a re-arm rule a single
# bear market emits a signal every day it stays below the line, and the study
# reports 120 "independent" observations of one event.  Half the threshold is
# strict enough to separate genuine episodes and loose enough that a choppy
# bottom does not re-trigger three times.
REARM_RECOVERY_FRACTION = 0.5

# Below this many episodes the statistics are anecdote, not evidence.
MIN_SIGNALS_FOR_RELIABLE = 5

# A study needs enough history that at least the one-year horizon can complete
# for a reasonable number of days.
MIN_POINTS_FOR_STUDY = 252 * 2

STATUS_OK = "ok"
STATUS_INSUFFICIENT_HISTORY = "insufficient_history"


# ══════════════════════════════════════════════════════════════════════════
#  PRIMITIVES
# ══════════════════════════════════════════════════════════════════════════

def _clean(closes: Sequence[float] | None) -> list[float]:
    """Drop non-numeric / non-positive / non-finite closes, preserving order."""
    out: list[float] = []
    for value in (closes or []):
        try:
            f = float(value)
        except (TypeError, ValueError):
            continue
        if f != f or f in (float("inf"), float("-inf")) or f <= 0:
            continue
        out.append(f)
    return out


def drawdown_series(closes: Sequence[float]) -> list[float]:
    """
    Percent below the running peak, for every bar.

    The peak is the highest close SEEN SO FAR, never the highest in the whole
    series.  Using the full-series maximum would leak the future into every
    early signal: in 2016 nobody knew where the 2024 top would be, and a
    strategy that needs to know it is not a strategy.

    Values are positive magnitudes: 0.0 at a new high, 12.5 when 12.5% below it.
    """
    out: list[float] = []
    peak = float("-inf")
    for close in closes:
        if close > peak:
            peak = close
        out.append(0.0 if peak <= 0 else (peak - close) / peak * 100.0)
    return out


def find_signals(drawdowns: Sequence[float], threshold: float, *,
                 rearm_fraction: float = REARM_RECOVERY_FRACTION) -> list[int]:
    """
    Indices where a fresh dip episode reaches ``threshold``.

    Fires on the first bar at or beyond the threshold, then stays silent until
    the drawdown recovers to shallower than ``threshold * rearm_fraction``.
    See :data:`REARM_RECOVERY_FRACTION` for why the re-arm exists at all.
    """
    if threshold <= 0:
        return []
    rearm_at = threshold * rearm_fraction
    signals: list[int] = []
    armed = True
    for i, dd in enumerate(drawdowns):
        if armed and dd >= threshold:
            signals.append(i)
            armed = False
        elif not armed and dd < rearm_at:
            armed = True
    return signals


def forward_return(closes: Sequence[float], index: int, days: int) -> float | None:
    """
    Percent change from ``index`` to ``index + days``.

    ``None`` when the series does not extend that far — the observation has not
    finished, and an unfinished observation is not a zero.
    """
    end = index + days
    if index < 0 or end >= len(closes):
        return None
    start = closes[index]
    if start <= 0:
        return None
    return (closes[end] - start) / start * 100.0


def max_drawdown(closes: Sequence[float]) -> float | None:
    """Deepest peak-to-trough fall within the given window, as a positive %."""
    if len(closes) < 2:
        return None
    worst = 0.0
    peak = closes[0]
    for close in closes[1:]:
        if close > peak:
            peak = close
        elif peak > 0:
            worst = max(worst, (peak - close) / peak * 100.0)
    return worst


def _annualised(total_pct: float, days: int) -> float | None:
    """Compound annual rate for a total return over ``days`` trading days."""
    if days < ANNUALISE_FROM_DAYS:
        return None
    years = days / ANNUALISE_FROM_DAYS
    growth = 1.0 + total_pct / 100.0
    if growth <= 0:
        return None
    return (growth ** (1.0 / years) - 1.0) * 100.0


# ══════════════════════════════════════════════════════════════════════════
#  STATISTICS OVER A SET OF ENTRY DAYS
# ══════════════════════════════════════════════════════════════════════════

def _empty_horizon(days: int) -> dict:
    """A horizon with nothing completed. Every statistic unknown, n = 0."""
    return {
        "horizon_days": days,
        "n": 0,
        "mean_pct": None,
        "median_pct": None,
        "positive_rate_pct": None,
        "worst_pct": None,
        "best_pct": None,
        "mean_cagr_pct": None,
        "worst_drawdown_pct": None,
    }


def horizon_stats(closes: Sequence[float], entries: Sequence[int],
                  days: int, *, with_drawdown: bool = True) -> dict:
    """
    Forward-return statistics for a set of entry days at one horizon.

    Entries whose window runs past the end of the series are DROPPED, and the
    surviving count is reported as ``n``.  This is the difference between "the
    five-year answer rests on four completed observations" and a confident
    average silently computed from four.
    """
    returns: list[float] = []
    troughs: list[float] = []
    for i in entries:
        r = forward_return(closes, i, days)
        if r is None:
            continue
        returns.append(r)
        if with_drawdown:
            dd = max_drawdown(closes[i:i + days + 1])
            if dd is not None:
                troughs.append(dd)

    if not returns:
        return _empty_horizon(days)

    mean_pct = statistics.fmean(returns)
    positive = sum(1 for r in returns if r > 0)
    return {
        "horizon_days": days,
        "n": len(returns),
        "mean_pct": round(mean_pct, 2),
        "median_pct": round(statistics.median(returns), 2),
        "positive_rate_pct": round(positive / len(returns) * 100.0, 1),
        "worst_pct": round(min(returns), 2),
        "best_pct": round(max(returns), 2),
        "mean_cagr_pct": (round(_annualised(mean_pct, days), 2)
                          if _annualised(mean_pct, days) is not None else None),
        # The drawdown an investor would have had to sit through AFTER buying.
        # A signal with a great average and a 40% interim fall is not the same
        # product as one with the same average and a 10% fall.
        "worst_drawdown_pct": round(max(troughs), 2) if troughs else None,
    }


def profile(closes: Sequence[float], entries: Sequence[int], *,
            with_drawdown: bool = True) -> dict:
    """Forward-return statistics across every horizon for one set of entries."""
    return {h: horizon_stats(closes, entries, HORIZON_DAYS[h],
                             with_drawdown=with_drawdown) for h in HORIZONS}


def baseline_profile(closes: Sequence[float]) -> dict:
    """
    The null: buying on every single day, with no signal at all.

    This is what any dip rule has to beat.  A rule that matches it is a rule
    that has discovered the equity risk premium and dressed it up as insight.
    """
    # with_drawdown is off here purely for cost: the interim-drawdown figure
    # needs a fresh max over every one of ~2,500 windows per horizon, and the
    # baseline's value is its RETURN distribution. The signal profiles, which
    # have a few dozen entries, still compute it.
    return profile(closes, range(len(closes)), with_drawdown=False)


def _edge(signal_stats: dict, base_stats: dict) -> dict:
    """Signal-minus-baseline at each horizon, in percentage points."""
    out: dict = {}
    for h in HORIZONS:
        s, b = signal_stats.get(h, {}), base_stats.get(h, {})
        sm, bm = s.get("mean_pct"), b.get("mean_pct")
        sp, bp = s.get("positive_rate_pct"), b.get("positive_rate_pct")
        out[h] = {
            "mean_pp": round(sm - bm, 2) if sm is not None and bm is not None else None,
            "positive_rate_pp": (round(sp - bp, 1)
                                 if sp is not None and bp is not None else None),
        }
    return out


# ══════════════════════════════════════════════════════════════════════════
#  THRESHOLD STUDY
# ══════════════════════════════════════════════════════════════════════════

def study_threshold(closes: Sequence[float], drawdowns: Sequence[float],
                    threshold: float, baseline: dict) -> dict:
    """One threshold, fully characterised and quoted against the baseline."""
    signals = find_signals(drawdowns, threshold)
    stats = profile(closes, signals)
    return {
        "threshold_pct": threshold,
        "signals": len(signals),
        "signal_indices": list(signals),
        "reliable": len(signals) >= MIN_SIGNALS_FOR_RELIABLE,
        "forward": stats,
        "edge": _edge(stats, baseline),
    }


def _score_threshold(study: dict, horizon: str = "1y") -> float | None:
    """
    Ranking key for threshold selection: edge over baseline at one horizon.

    Edge, not raw return — a threshold that only fires in bull markets will
    post a fine absolute number while adding nothing. Unreliable studies are
    refused outright rather than ranked low, so a two-signal fluke cannot win.
    """
    if not study.get("reliable"):
        return None
    return (study.get("edge", {}).get(horizon) or {}).get("mean_pp")


def _insufficient(label: str, symbol: str, points: int) -> dict:
    """A well-formed report for a series too short to study."""
    return {
        "symbol": symbol,
        "label": label,
        "status": STATUS_INSUFFICIENT_HISTORY,
        "points": points,
        "years": round(points / 252.0, 1) if points else 0.0,
        "current_drawdown_pct": None,
        "history": {"trimmed": False, "dropped": 0, "events": [],
                    "threshold_pct": market_indices.CORPORATE_ACTION_1D_MOVE_PCT},
        "baseline": None,
        "thresholds": [],
        "best_threshold_pct": None,
        "walk_forward": None,
        "note": (f"Only {points} daily closes available; at least "
                 f"{MIN_POINTS_FOR_STUDY} are needed before forward returns "
                 f"mean anything."),
    }


def walk_forward(closes: Sequence[float], drawdowns: Sequence[float],
                 thresholds: Sequence[float], *,
                 split: float = 0.6, horizon: str = "1y") -> dict:
    """
    Choose a threshold on early history, then score it on history it never saw.

    With five candidate thresholds and one decade of data, picking the winner
    in-sample and reporting its in-sample performance is close to guaranteed to
    flatter the strategy. This splits the series, selects on the first
    ``split`` of it, and reports what that choice actually delivered afterwards.

    ``selected_threshold_pct`` is None when no threshold produced enough
    episodes in the training half to be worth selecting — which is itself a
    finding, and a more honest one than picking the least-bad of five flukes.
    """
    n = len(closes)
    cut = int(n * split)
    if cut < MIN_POINTS_FOR_STUDY or (n - cut) < HORIZON_DAYS[horizon]:
        return {
            "status": STATUS_INSUFFICIENT_HISTORY,
            "selected_threshold_pct": None,
            "in_sample": None,
            "out_of_sample": None,
            "note": "Not enough history to train on one half and test on the other.",
        }

    train_closes = list(closes[:cut])
    train_dd = drawdown_series(train_closes)
    train_base = baseline_profile(train_closes)

    ranked = []
    for t in thresholds:
        study = study_threshold(train_closes, train_dd, t, train_base)
        score = _score_threshold(study, horizon)
        if score is not None:
            ranked.append((score, t, study))
    if not ranked:
        return {
            "status": STATUS_OK,
            "selected_threshold_pct": None,
            "in_sample": None,
            "out_of_sample": None,
            "note": ("No threshold produced enough separate episodes in the "
                     "training period to be worth carrying forward."),
        }

    ranked.sort(key=lambda r: r[0], reverse=True)
    best_score, best_t, best_study = ranked[0]

    # Score the chosen threshold on the held-out tail. Signals are found on the
    # FULL drawdown series and then filtered to the test window, so an episode
    # that began before the split is not re-detected as though it were new.
    test_signals = [i for i in find_signals(drawdowns, best_t) if i >= cut]
    test_stats = profile(closes, test_signals)
    test_base = baseline_profile(list(closes[cut:]))

    return {
        "status": STATUS_OK,
        "split_index": cut,
        "selected_threshold_pct": best_t,
        "selected_on_horizon": horizon,
        "in_sample": {
            "signals": best_study["signals"],
            "edge_pp": best_score,
            "forward": best_study["forward"][horizon],
        },
        "out_of_sample": {
            "signals": len(test_signals),
            "forward": test_stats[horizon],
            "baseline": test_base[horizon],
            "edge_pp": _edge(test_stats, test_base)[horizon]["mean_pp"],
        },
        "note": None,
    }


def backtest_benchmark(symbol: str, label: str, closes: Sequence[float], *,
                       thresholds: Sequence[float] = DEFAULT_THRESHOLDS) -> dict:
    """
    Full dip study for one benchmark.

    Never raises on thin or dirty data: a series that cannot support the study
    comes back with ``status="insufficient_history"`` and every statistic None,
    which the dashboard renders as "not enough history" rather than as a
    strategy that happens to score zero.
    """
    series = _clean(closes)
    # Truncate at any split-like discontinuity BEFORE measuring anything. A
    # forward return spanning a unit split is not a return, and one such bar is
    # enough to dominate every average in the study.
    series, _dates, split_info = market_indices.trim_corporate_actions(series)
    if len(series) < MIN_POINTS_FOR_STUDY:
        out = _insufficient(label, symbol, len(series))
        out["history"] = split_info
        return out

    dd = drawdown_series(series)
    base = baseline_profile(series)
    studies = [study_threshold(series, dd, t, base) for t in thresholds]

    scored = [(s, _score_threshold(s)) for s in studies]
    usable = [(score, s) for s, score in scored if score is not None]
    best = max(usable, key=lambda r: r[0])[1] if usable else None

    return {
        "symbol": symbol,
        "label": label,
        "status": STATUS_OK,
        "points": len(series),
        "years": round(len(series) / 252.0, 1),
        "current_drawdown_pct": round(dd[-1], 2),
        "history": split_info,
        "baseline": base,
        "thresholds": studies,
        # The deepest threshold today's drawdown has actually reached, which is
        # the row the action panel should quote for a live decision.
        "active_threshold_pct": max((t for t in thresholds if dd[-1] >= t),
                                    default=None),
        "best_threshold_pct": best["threshold_pct"] if best else None,
        "walk_forward": walk_forward(series, dd, thresholds),
        "note": None,
    }
