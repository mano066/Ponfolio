"""Selection harness with a RANDOM-PICKER NULL and a configurable hold.

Why this exists
---------------
Every prior number in this repo compared engines only to each other. That cannot
tell you whether an engine *selects* anything: a rule that trades liquid Indian
equities in a rising market makes money because the market rose, not because the
rule is smart. The only honest bar is a random picker drawing from the SAME
eligible pool, on the SAME dates, with the SAME entry, exit, cost and gap
filter. `rand:N` builds that distribution, and an engine has to beat it.

Two things it measures that the previous scripts could not:

  1. `rand:N`  — N independent uniform-random pickers. An engine's expectancy is
     reported as a percentile of that distribution. Below ~p50 means the
     selection rule is worthless; below p05 means it is actively harmful.
  2. `--hold`  — the exit horizon, swept. The one finding that replicated on
     RANDOM pickers (8 of 9 cells) was that a longer hold beats a shorter one,
     which if true is engine-independent and worth more than any ranking
     change. Production holds 14 trading days; the studies used 20; the finding
     pointed at 40.

Data
----
Consumes research/data/pit_universe_daily.parquet from
`universe_builder.py build` — the point-in-time, ISIN-keyed, survivorship-free
panel INCLUDING delisted and renamed names.

Usage
-----
  python research/scripts/v5/harness.py --hold 14,20,40 --rand 20
  python research/scripts/v5/harness.py --engines v4,v4.1 --hold 20 --rand 40

Out: research/data/harness_results.json

CAVEAT that limits every number below: bhavcopy OHLCV is RAW, not adjusted for
splits or bonuses. A split inside a hold window shows up as a ~-50% return. This
hits all engines AND the random null roughly equally, so the *comparison* is
usable while the absolute expectancies are biased downward. It is the reason the
corporate-action master (DATA_INVENTORY.md, "Not found yet") still matters.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bias_free_compare import (  # noqa: E402  reuse the verified loaders
    ema, load_panel, nifty_series,
)

D = Path(__file__).resolve().parents[2] / "data"
OUT = D / "harness_results.json"

COST = 0.30            # % round-trip, as in every prior study
TOP_N = 5              # picks per day, matching production
GAP_MAX = 4.0          # skip if it opens >4% above the signal close
STOP_ATR = 2.5         # v4's exit unit
MIN_TURNOVER, MIN_PRICE = 1e7, 5.0
TRAIN, VAL, TEST = (2011, 2019), (2020, 2022), (2023, 2026)
WARMUP = 260           # bars needed before a symbol is tradeable


def build_arrays_lean(panel: pd.DataFrame) -> dict:
    """Per-ISIN arrays, restricted to what THIS harness reads.

    bias_free_compare.build_arrays also computes v5-only indicators (rsi, macd,
    Bollinger width and its rolling quantile, volume ratio) and a per-ISIN
    {date: index} dict. Across 7.5M bars that dict alone is millions of entries
    and the extra series roughly double peak memory, for values nothing here
    uses. ISIN keying is preserved — that is what makes renames and delistings
    survive.
    """
    SYM = {}
    for isin, g in panel.groupby("isin", observed=True):
        if len(g) < WARMUP:
            continue
        c = g["close"].astype(float).reset_index(drop=True)
        h = g["high"].astype(float).reset_index(drop=True)
        lo = g["low"].astype(float).reset_index(drop=True)
        o = g["open"].astype(float).reset_index(drop=True)
        turn = g["turnover"].astype(float).reset_index(drop=True)
        v = g["volume"].astype(float).reset_index(drop=True)

        pc = c.shift(1)
        tr = pd.concat([h - lo, (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
        e50 = ema(c, 50)
        SYM[isin] = dict(
            sym=g["symbol"].iloc[-1],
            dates=g["date"].dt.date.to_numpy(),
            o=o.to_numpy(), c=c.to_numpy(),
            atr=tr.ewm(alpha=1 / 14, adjust=False).mean().to_numpy(),
            e20=ema(c, 20).to_numpy(), e50=e50.to_numpy(),
            e200=ema(c, 200).to_numpy(),
            hh250=c.rolling(250, min_periods=60).max().to_numpy(),
            # Turnover is present in both bhavcopy formats; fall back to
            # close*volume only where the column is entirely absent.
            turn=(turn if turn.notna().any() else c * v).rolling(20).mean().to_numpy(),
            ret63=(c / c.shift(63) - 1).to_numpy(),
        )
    return SYM


# ── per-bar eligibility + ranking features, long format ─────────────────────
def build_bar_table(SYM: dict, NIFR63: dict) -> tuple[pd.DataFrame, list]:
    """One row per (symbol, bar) that is liquid, warmed up and gap-clean.

    Long format on purpose: the random null has to sample from the *same* pool
    the engines rank, so the pool must exist independently of any engine. The
    forward price path is NOT stored — it is read from SYM at scoring time, or
    this table would be tens of GB.
    """
    keys = list(SYM.keys())
    frames = []
    for kid, isin in enumerate(keys):
        a = SYM[isin]
        c, o = a["c"], a["o"]
        n = len(c)
        if n <= WARMUP + 2:
            continue
        j = np.arange(WARMUP, n - 1)

        entry = o[j + 1]
        close_j = c[j]
        atr = a["atr"][j]
        with np.errstate(divide="ignore", invalid="ignore"):
            gap = (entry / close_j - 1.0) * 100.0
        ok = (entry > 0) & (atr > 0) & np.isfinite(gap) & (gap <= GAP_MAX)

        turn, price = a["turn"][j], c[j]
        ok &= np.isfinite(turn) & (turn >= MIN_TURNOVER) & (price >= MIN_PRICE)

        # v4's momentum tier, from raw OHLCV.
        e20, e50, e200 = a["e20"][j], a["e50"][j], a["e200"][j]
        hh250, ret63 = a["hh250"][j], a["ret63"][j]
        dates = a["dates"][j]
        nif = np.array([NIFR63.get(d, np.nan) for d in dates], dtype=float)
        trend_ok = (close_j > e20) & (e20 > e50)
        near_hi = (hh250 > 0) & (close_j >= 0.85 * hh250)
        rs = ret63 > nif
        sig_v4 = trend_ok & near_hi & rs & (ret63 > 0)

        # v4.1 keeps the relative-strength half of the tier and replaces the
        # 0.85 flag with a continuous near-high rank (built per date below).
        sig_v41 = trend_ok & rs & (ret63 > 0)

        with np.errstate(divide="ignore", invalid="ignore"):
            near_hi_frac = np.where(hh250 > 0, close_j / hh250, np.nan)
            atr_pct = np.where(close_j > 0, atr / close_j * 100.0, np.nan)

        if not ok.any():
            continue
        frames.append(pd.DataFrame({
            "date": dates[ok], "kid": kid, "j": j[ok],
            "ret63": ret63[ok], "near_hi_frac": near_hi_frac[ok],
            "atr_pct": atr_pct[ok],
            "sig_v4": sig_v4[ok], "sig_v41": sig_v41[ok],
        }))

    if not frames:
        return pd.DataFrame(), keys
    bars = pd.concat(frames, ignore_index=True)
    bars["year"] = pd.to_datetime(bars["date"]).dt.year

    # Cross-sectional percentile ranks, computed WITHIN each date — the same
    # per-day cross-section the live scanner ranks over, so no future dates leak
    # into a rank.
    g = bars.groupby("date")
    bars["xr_near_hi"] = g["near_hi_frac"].rank(pct=True)
    bars["xr_atr"] = g["atr_pct"].rank(pct=True)
    bars["v41_score"] = bars["xr_near_hi"] - bars["xr_atr"]
    return bars, keys


# ── exit: v4's stop-or-time rule, hold parameterised ────────────────────────
def score_trades(sel: pd.DataFrame, SYM: dict, keys: list, hold: int) -> np.ndarray:
    """Net % per trade: enter at next open, exit on a 2.5-ATR close stop (filled
    at the following open) or at the close of bar `hold`, minus round-trip cost."""
    nets = np.empty(len(sel), dtype=float)
    valid = np.zeros(len(sel), dtype=bool)
    kids = sel["kid"].to_numpy()
    js = sel["j"].to_numpy()

    for i, (kid, j) in enumerate(zip(kids, js)):
        a = SYM[keys[kid]]
        c, o = a["c"], a["o"]
        n = len(c)
        e = float(o[j + 1])
        m = min(hold, n - (j + 1))
        if m < 1 or e <= 0:
            continue
        stop = e - STOP_ATR * float(a["atr"][j])
        net = None
        for k in range(m):
            if float(c[j + 1 + k]) <= stop:
                nxt = j + 2 + k
                ex = float(o[nxt]) if nxt < n else float(c[j + 1 + k])
                net = (ex / e - 1.0) * 100.0 - COST
                break
        if net is None:
            net = (float(c[j + m]) / e - 1.0) * 100.0 - COST
        nets[i] = net
        valid[i] = True
    return nets[valid]


# ── selection policies ──────────────────────────────────────────────────────
def select_engine(bars: pd.DataFrame, engine: str) -> pd.DataFrame:
    if engine == "v4":
        d = bars[bars["sig_v4"]]
        return (d.sort_values(["date", "ret63"], ascending=[True, False])
                 .groupby("date").head(TOP_N))
    if engine == "v4.1":
        d = bars[bars["sig_v41"]]
        return (d.sort_values(["date", "v41_score"], ascending=[True, False])
                 .groupby("date").head(TOP_N))
    raise ValueError(f"unknown engine {engine!r}")


def select_random(bars: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Uniform draw of TOP_N from the FULL eligible pool for each date — no
    signal filter. This is the null the engines must beat."""
    rng = np.random.default_rng(seed)
    take = bars[["date", "kid", "j"]].copy()
    take["u"] = rng.random(len(take))
    return (take.sort_values(["date", "u"]).groupby("date").head(TOP_N))


# ── metrics ─────────────────────────────────────────────────────────────────
def split_metrics(sel: pd.DataFrame, SYM, keys, hold: int, split) -> dict | None:
    lo, hi = split
    years = pd.to_datetime(sel["date"]).dt.year
    d = sel[(years >= lo) & (years <= hi)]
    if len(d) < 50:
        return None
    nets = score_trades(d, SYM, keys, hold)
    if len(nets) < 50:
        return None
    w = nets > 0
    return {
        "n": int(len(nets)),
        "exp": round(float(nets.mean()), 4),
        "win": round(float(w.mean() * 100), 2),
        "pf": round(float(nets[w].sum() / max(1e-9, -nets[~w].sum())), 3),
        "med": round(float(np.median(nets)), 4),
    }


def pct_rank(value: float, dist: list[float]) -> float | None:
    """Percentile of `value` within the random-null distribution."""
    d = [x for x in dist if x is not None]
    if not d or value is None:
        return None
    return round(float(np.mean([value > x for x in d]) * 100), 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hold", default="14,20,40",
                    help="comma-separated hold lengths in trading days")
    ap.add_argument("--rand", type=int, default=20,
                    help="number of random pickers in the null distribution")
    ap.add_argument("--engines", default="v4,v4.1")
    a = ap.parse_args()
    holds = [int(x) for x in a.hold.split(",") if x.strip()]
    engines = [x.strip() for x in a.engines.split(",") if x.strip()]

    print("loading survivorship-free panel...", flush=True)
    panel = load_panel()
    print(f"  rows={len(panel):,}  ISINs={panel['isin'].nunique():,}  "
          f"{panel['date'].min().date()}..{panel['date'].max().date()}", flush=True)
    _REG, NIFR63 = nifty_series()
    nif_dates = sorted(NIFR63)
    print(f"  nifty benchmark covers {nif_dates[0]}..{nif_dates[-1]} — bars after "
          f"that have no relative-strength reference and cannot signal", flush=True)
    SYM = build_arrays_lean(panel)
    del panel
    print(f"  usable ISINs (>={WARMUP}d): {len(SYM):,}", flush=True)

    print("building per-bar eligibility table...", flush=True)
    bars, keys = build_bar_table(SYM, NIFR63)
    if bars.empty:
        raise SystemExit("no eligible bars — check the panel")
    print(f"  eligible bars={len(bars):,}  dates={bars['date'].nunique():,}  "
          f"v4 signals={int(bars['sig_v4'].sum()):,}  "
          f"v4.1 signals={int(bars['sig_v41'].sum()):,}", flush=True)

    res = {
        "meta": {
            "universe": "survivorship-free point-in-time (ISIN-keyed, incl. delisted)",
            "prices": "RAW bhavcopy OHLCV — NOT split/bonus adjusted",
            "cost_pct_round_trip": COST, "top_n": TOP_N, "stop_atr": STOP_ATR,
            "gap_max_pct": GAP_MAX, "warmup_bars": WARMUP,
            "splits": {"train": TRAIN, "val": VAL, "test": TEST},
            "eligible_bars": int(len(bars)), "dates": int(bars["date"].nunique()),
            "n_random_pickers": a.rand,
        },
        "by_hold": {},
    }

    selections = {e: select_engine(bars, e) for e in engines}
    for e, sel in selections.items():
        print(f"  {e}: {len(sel):,} selected trades", flush=True)

    for hold in holds:
        print(f"\n=== hold={hold} sessions ===", flush=True)
        block = {"engines": {}, "random": {}}

        for e, sel in selections.items():
            block["engines"][e] = {
                s: split_metrics(sel, SYM, keys, hold, sp)
                for s, sp in (("train", TRAIN), ("val", VAL), ("test", TEST))
            }
            t = block["engines"][e]["test"]
            print(f"  {e:<6} TEST exp={t['exp'] if t else 'n/a'} "
                  f"win={t['win'] if t else 'n/a'}% n={t['n'] if t else 0}", flush=True)

        # The null: N random pickers over the identical pool.
        dist = {"train": [], "val": [], "test": []}
        for seed in range(a.rand):
            rsel = select_random(bars, seed)
            for s, sp in (("train", TRAIN), ("val", VAL), ("test", TEST)):
                m = split_metrics(rsel, SYM, keys, hold, sp)
                dist[s].append(m["exp"] if m else None)
            if (seed + 1) % 5 == 0:
                print(f"    rand {seed+1}/{a.rand}", flush=True)

        for s in ("train", "val", "test"):
            d = [x for x in dist[s] if x is not None]
            block["random"][s] = {
                "n_seeds": len(d),
                "mean": round(float(np.mean(d)), 4) if d else None,
                "p05": round(float(np.percentile(d, 5)), 4) if d else None,
                "p50": round(float(np.percentile(d, 50)), 4) if d else None,
                "p95": round(float(np.percentile(d, 95)), 4) if d else None,
                "min": round(float(np.min(d)), 4) if d else None,
                "max": round(float(np.max(d)), 4) if d else None,
            }
        for e in engines:
            for s in ("train", "val", "test"):
                m = block["engines"][e][s]
                if m:
                    m["pctile_vs_random"] = pct_rank(m["exp"], dist[s])
        res["by_hold"][str(hold)] = block

        r = block["random"]["test"]
        print(f"  rand:{a.rand} TEST mean={r['mean']} "
              f"p05={r['p05']} p50={r['p50']} p95={r['p95']}", flush=True)

    OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    # ── report ──
    print("\n" + "=" * 74)
    print("EXPECTANCY %/TRADE vs RANDOM-PICKER NULL  (survivorship-free panel)")
    print("=" * 74)
    hdr = f"{'hold':>5} {'engine':<9}{'TRAIN':>9}{'VAL':>9}{'TEST':>9}{'TEST pct':>10}"
    print(hdr)
    print("-" * 74)
    for hold in holds:
        b = res["by_hold"][str(hold)]
        for e in engines:
            m = b["engines"][e]
            def g(s):
                return f"{m[s]['exp']:.3f}" if m[s] else "n/a"
            pc = m["test"].get("pctile_vs_random") if m["test"] else None
            print(f"{hold:>5} {e:<9}{g('train'):>9}{g('val'):>9}{g('test'):>9}"
                  f"{(f'p{pc:.0f}' if pc is not None else 'n/a'):>10}")
        rr = b["random"]
        def gr(s):
            return f"{rr[s]['mean']:.3f}" if rr[s]["mean"] is not None else "n/a"
        print(f"{hold:>5} {'rand:mean':<9}{gr('train'):>9}{gr('val'):>9}{gr('test'):>9}"
              f"{'—':>10}")
        print("-" * 74)
    print("\nAn engine only has a selection edge where TEST pct is high AND its "
          "expectancy exceeds the random p95.")
    print("Prices are RAW (unadjusted) — splits depress every row, engines and "
          "null alike. Compare columns, not absolute levels.")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
