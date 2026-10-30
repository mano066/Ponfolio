"""Candidate swing engines, measured against v4 and a random-picker null.

Why this exists
---------------
`harness.py` settled two things and left a gap. It settled that v4.1 is refuted
and that hold length dominates any ranking change; `V5_BIASFREE_RESULT.md`
settled that v4-style momentum beats the v5 ensemble on the survivorship-free,
CA-adjusted universe. What neither did was ask whether a DIFFERENT ranking
inside the same momentum gate does better than v4's `ret63`. That is the one
question here.

Everything that could make the comparison unfair is held identical to
`harness.py` and is imported from it rather than re-implemented: the eligible
pool, the next-open entry, the 2.5-ATR stop filled at the following open, the
0.30% round trip, the 4% gap filter, the 260-bar warm-up, top-5 per day, and
the chronological TRAIN/VAL/TEST split. Only the RANKING changes between
engines, so any difference in the table is attributable to selection.

Prices are corporate-action back-adjusted before anything is computed, because
`V5_BIASFREE_RESULT.md` showed raw split noise moves the verdict — it cost the
v5 ensemble roughly 0.4%/trade. Adjustment is applied to the panel once, so
every engine and the null see the same series.

The candidates
--------------
Each is a stated hypothesis about WHY v4's ranking might be improvable, not a
parameter sweep. v4 gates on trend + near-52-week-high + relative strength and
then ranks the survivors by 63-day return.

  m1_riskadj    Rank by ret63 / realised vol instead of ret63.
                Hypothesis: raw ret63 rewards a name whose gain came from one
                explosive bar — often a news gap — and those revert. Dividing
                by realised volatility selects the DURABLE trends instead.

  m2_near_high  Rank by close / 250-day high; drop v4's 0.85 flag to a gate.
                Hypothesis (George-Hwang anchoring): proximity to the 52-week
                high, not trailing return, is what predicts continuation. v4
                already believes this enough to filter on it but then throws
                the magnitude away.

  m3_unextended Rank by LEAST extension above the 20 EMA, in ATR units.
                Hypothesis: v4 buys what has already run, and with a fixed
                2.5-ATR stop an extended entry is the one most likely to be
                stopped on ordinary noise. Same names, better entry point.

  m4_breakout   Gate on a NEW 250-day closing high, rank by turnover surge.
                Hypothesis: a breakout confirmed by participation holds; one on
                thin volume is a liquidity artefact.

  m5_persist    Rank by the fraction of the last 63 sessions closed above the
                20 EMA. Hypothesis: smooth trends persist and choppy ones do
                not, and that is invisible to a point-to-point return.

  *_bull        Any engine may be run with a market-regime overlay (Nifty above
                its 200 EMA) via --regime, which tests whether v4's known
                VAL instability is a market-state problem rather than a
                selection one.

Discipline
----------
TEST is reported but must not be used to choose. Pick on TRAIN and VAL, then
read TEST once. An engine has a selection edge only where it clears the random
p95 — beating v4 while sitting inside the null distribution means neither rule
selects anything.

Usage
-----
  python research/scripts/v5/strategy_lab.py --hold 20 --rand 20
  python research/scripts/v5/strategy_lab.py --hold 20,40 --rand 20 --regime

Out: research/data/strategy_lab_results.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bias_free_compare import ema, load_panel, nifty_series  # noqa: E402
from harness import (  # noqa: E402  reuse the VERIFIED mechanics unchanged
    GAP_MAX, MIN_PRICE, MIN_TURNOVER, TEST, TRAIN, VAL, TOP_N, WARMUP,
    pct_rank, score_trades, select_random, split_metrics,
)

D = Path(__file__).resolve().parents[2] / "data"
OUT = D / "strategy_lab_results.json"

# Split/bonus-sized close-to-close discontinuities, same thresholds as
# bias_free_ca_adjust.py so the two studies rest on the same adjusted series.
CA_DROP, CA_RISE = 0.60, 1.60


# ── corporate-action back-adjustment ────────────────────────────────────────
def adjust_ca(panel: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Back-adjust OHLC per ISIN so split/bonus-sized jumps vanish.

    Same ratio ("panama") back-adjust as `bias_free_ca_adjust.adjust_ca`, but
    computed as a reverse cumulative product rather than a Python loop over
    every bar — the loop version is ~7.5M iterations and dominates the run.

    Heuristic, not ground truth: a real NSE corporate-action feed would be
    better, and this may also flatten a genuine one-day collapse. It is applied
    identically to every engine and to the null, so it cannot favour one.
    """
    parts, n_ca = [], 0
    for _isin, g in panel.groupby("isin", observed=True):
        g = g.sort_values("date").copy()
        c = g["close"].to_numpy(float)
        n = len(c)
        if n < 2:
            parts.append(g)
            continue
        ratio = np.ones(n)
        prev = c[:-1]
        ratio[1:] = np.divide(c[1:], prev, out=np.ones(n - 1), where=prev > 0)
        is_ca = (ratio <= CA_DROP) | (ratio >= CA_RISE)
        is_ca[0] = False
        n_ca += int(is_ca.sum())

        # f[i] = product of the CA ratios at every bar AFTER i, so prices
        # before a split are scaled down onto the post-split basis.
        rca = np.where(is_ca, ratio, 1.0)
        suffix = np.cumprod(rca[::-1])[::-1]
        f = np.append(suffix[1:], 1.0)
        for col in ("open", "high", "low", "close"):
            g[col] = g[col].to_numpy(float) * f
        parts.append(g)
    return pd.concat(parts, ignore_index=True), n_ca


# ── per-ISIN arrays: harness's set plus what the candidates need ────────────
def build_arrays(panel: pd.DataFrame) -> dict:
    """Everything `harness.build_arrays_lean` computes, plus the candidate
    features. Kept in one pass so no engine pays for a second groupby."""
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
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
        e20, e50 = ema(c, 20), ema(c, 50)
        ret1 = c.pct_change()
        turn_s = turn if turn.notna().any() else c * v

        SYM[isin] = dict(
            sym=g["symbol"].iloc[-1],
            dates=g["date"].dt.date.to_numpy(),
            o=o.to_numpy(), c=c.to_numpy(),
            atr=atr.to_numpy(),
            e20=e20.to_numpy(), e50=e50.to_numpy(),
            e200=ema(c, 200).to_numpy(),
            hh250=c.rolling(250, min_periods=60).max().to_numpy(),
            turn=turn_s.rolling(20).mean().to_numpy(),
            ret63=(c / c.shift(63) - 1).to_numpy(),
            # m1: realised volatility of daily returns over the same 63-day
            # window the momentum is measured on, so the ratio is coherent.
            vol63=ret1.rolling(63).std().to_numpy(),
            # m3: how far above its own 20 EMA the close sits, in ATR units —
            # scale-free, so a ₹50 stock and a ₹5,000 one compare.
            ext_atr=((c - e20) / atr.replace(0, np.nan)).to_numpy(),
            # m5: share of the last 63 sessions closed above the 20 EMA.
            persist63=(c > e20).rolling(63).mean().to_numpy(),
            # m4: 5-day turnover against its own 60-day base.
            turn_ratio=(turn_s.rolling(5).mean()
                        / turn_s.rolling(60).mean().replace(0, np.nan)).to_numpy(),
            # ── inputs the S-family (MULTITIMEFRAME_STRATEGY_RESEARCH) needs ──
            o_arr=o.to_numpy(), lo=lo.to_numpy(),
            c_prev=c.shift(1).to_numpy(),
            rsi14=_rsi_wilder(c).to_numpy(),
            e12=ema(c, 12).to_numpy(), e26=ema(c, 26).to_numpy(),
            e50_rise=(e50 > e50.shift(5)).to_numpy(),
            ret20=(c / c.shift(20) - 1).to_numpy(),
            ret120=(c / c.shift(120) - 1).to_numpy(),
            # 20-day high as of the PREVIOUS bar — "close > 20d-high[t-1]" must
            # not include today's own close or the breakout is circular.
            hh20_prev=c.rolling(20).max().shift(1).to_numpy(),
            bbw=_bb_width(c).to_numpy(),
            bbw_q25=_bb_width(c).rolling(100).quantile(0.25).to_numpy(),
        )
    return SYM


def _rsi_wilder(c: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI — the smoothing the MTF configs specify (RSI14 Wilder)."""
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _bb_width(c: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    """Bollinger width (20,2) as (upper-lower)/middle, i.e. 2k*sigma/mean."""
    m = c.rolling(n).mean()
    s = c.rolling(n).std()
    return (2 * k * s) / m.replace(0, np.nan)


# ── eligibility + features, long format (one row per tradeable bar) ─────────
def build_bar_table(SYM: dict, NIFR63: dict, NIFBULL: dict,
                    NIFR20: dict, NIFR120: dict, NIFSIDE: dict
                    ) -> tuple[pd.DataFrame, list]:
    """The pool every engine ranks and the null samples.

    Identical eligibility to `harness.build_bar_table` — liquidity, price,
    warm-up, gap — so a candidate cannot win by quietly trading a different
    universe. Only the feature columns are new.
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
        turn = a["turn"][j]
        ok &= np.isfinite(turn) & (turn >= MIN_TURNOVER) & (close_j >= MIN_PRICE)
        if not ok.any():
            continue

        e20, e50 = a["e20"][j], a["e50"][j]
        hh250, ret63 = a["hh250"][j], a["ret63"][j]
        dates = a["dates"][j]
        nif = np.array([NIFR63.get(d, np.nan) for d in dates], dtype=float)
        bull = np.array([NIFBULL.get(d, False) for d in dates], dtype=bool)

        trend_ok = (close_j > e20) & (e20 > e50)
        near_hi = (hh250 > 0) & (close_j >= 0.85 * hh250)
        rs = ret63 > nif
        with np.errstate(divide="ignore", invalid="ignore"):
            near_hi_frac = np.where(hh250 > 0, close_j / hh250, np.nan)
            vol63 = a["vol63"][j]
            sharpe63 = np.where(vol63 > 0, ret63 / vol63, np.nan)

        # ── S-family gates, transcribed from mtf_strategy_configs.json ──
        e200 = a["e200"][j]
        rsi = a["rsi14"][j]
        e20v = e20
        c_prev = a["c_prev"][j]
        hh20p = a["hh20_prev"][j]
        s_trend = (close_j > e50) & (e50 > e200)          # common to S1/S2/S3/S6
        nif20 = np.array([NIFR20.get(d, np.nan) for d in dates], dtype=float)
        nif120 = np.array([NIFR120.get(d, np.nan) for d in dates], dtype=float)
        side = np.array([NIFSIDE.get(d, False) for d in dates], dtype=bool)

        with np.errstate(divide="ignore", invalid="ignore"):
            near_e20 = np.abs(close_j / e20v - 1.0) <= 0.02
        s1 = (bull & s_trend & a["e50_rise"][j]
              & ((a["lo"][j] <= e20v * 1.02) | near_e20) & (close_j > e20v)
              & (rsi >= 40) & (rsi <= 62) & (close_j > a["o_arr"][j]))
        s2 = ((bull | side) & s_trend
              & (a["bbw"][j] <= a["bbw_q25"][j]) & (close_j > hh20p)
              & (close_j <= e20v * 1.15))
        s3 = (bull & s_trend
              & (a["ret20"][j] > nif20) & (ret63 > nif) & (a["ret120"][j] > nif120)
              & (close_j >= hh20p * 0.92)
              & (close_j > c_prev) & (close_j > e20v))
        # S3 with the triple relative-strength filter relaxed to ret63 only —
        # the config's own ablation note says the triple version "slightly
        # LOWERS expectancy, mainly cuts trades".
        s3r = (bull & s_trend & (ret63 > nif)
               & (close_j >= hh20p * 0.92)
               & (close_j > c_prev) & (close_j > e20v))
        s6 = (bull & s_trend & (a["e12"][j] > a["e26"][j])
              & (rsi >= 45) & (rsi < 70))

        frames.append(pd.DataFrame({
            "date": dates[ok], "kid": np.int32(kid), "j": j[ok].astype(np.int32),
            "ret63": ret63[ok].astype(np.float32),
            "near_hi_frac": near_hi_frac[ok].astype(np.float32),
            "sharpe63": sharpe63[ok].astype(np.float32),
            "ext_atr": a["ext_atr"][j][ok].astype(np.float32),
            "persist63": a["persist63"][j][ok].astype(np.float32),
            "turn_ratio": a["turn_ratio"][j][ok].astype(np.float32),
            "new_high": (near_hi_frac[ok] >= 0.995),
            "trend_ok": trend_ok[ok], "near_hi": near_hi[ok], "rs": rs[ok],
            "pos_ret": (ret63[ok] > 0), "bull": bull[ok],
            "sig_s1": np.nan_to_num(s1[ok], nan=0).astype(bool),
            "sig_s2": np.nan_to_num(s2[ok], nan=0).astype(bool),
            "sig_s3": np.nan_to_num(s3[ok], nan=0).astype(bool),
            "sig_s3r": np.nan_to_num(s3r[ok], nan=0).astype(bool),
            "sig_s6": np.nan_to_num(s6[ok], nan=0).astype(bool),
        }))

    if not frames:
        return pd.DataFrame(), keys
    bars = pd.concat(frames, ignore_index=True)
    # v4's own signal, reconstructed from the same parts the candidates use.
    bars["sig_v4"] = bars["trend_ok"] & bars["near_hi"] & bars["rs"] & bars["pos_ret"]
    return bars, keys


# ── candidate selection policies ────────────────────────────────────────────
#
# (gate, rank column, ascending) per engine. A gate is a boolean over the pool;
# the rank orders the survivors and the top TOP_N per date are taken. Stated as
# data rather than as branches so every candidate provably shares one code path
# — a candidate cannot accidentally get a different tie-break or a different
# top-N than the baseline it is being compared against.
ENGINES: dict[str, tuple] = {
    # incumbent: trend + near-52w-high + RS, ranked by 63-day return
    "v4":            (("trend_ok", "near_hi", "rs", "pos_ret"), "ret63", False),
    "m1_riskadj":    (("trend_ok", "near_hi", "rs", "pos_ret"), "sharpe63", False),
    "m2_near_high":  (("trend_ok", "rs", "pos_ret"), "near_hi_frac", False),
    "m3_unextended": (("trend_ok", "near_hi", "rs", "pos_ret"), "ext_atr", True),
    "m4_breakout":   (("trend_ok", "rs", "new_high"), "turn_ratio", False),
    "m5_persist":    (("trend_ok", "near_hi", "rs", "pos_ret"), "persist63", False),

    # ── the S-family from MULTITIMEFRAME_STRATEGY_RESEARCH_2026-07-25.md ──
    # Published on the survivorship-BIASED ~708-name universe with no null, so
    # those numbers (S1 test 2.06, S3 test 1.73, S6 test 2.13) cannot be
    # compared to anything on this rig until the strategies are re-run on it.
    # That is what these entries are for.
    #
    # Every one is ranked by ret63 — the configs record each strategy's gate
    # but NOT its "strategy-specific rank", so a common momentum rank is used
    # throughout. That keeps the comparison about the gate, which is the part
    # that is actually documented. It is a real limitation, stated in the
    # write-up: a better rank might lift any of them.
    "S1_pullback":   (("sig_s1",), "ret63", False),
    "S2_volcontr":   (("sig_s2",), "ret63", False),
    "S3_rs_cont":    (("sig_s3",), "ret63", False),
    "S3r_rs_relaxed": (("sig_s3r",), "ret63", False),
    "S6_momentum":   (("sig_s6",), "ret63", False),
}


def select_engine(bars: pd.DataFrame, engine: str, regime: bool = False) -> pd.DataFrame:
    gates, rank_col, asc = ENGINES[engine]
    mask = np.ones(len(bars), dtype=bool)
    for gcol in gates:
        mask &= bars[gcol].to_numpy()
    if regime:
        # Market-state overlay: only trade with the Nifty above its 200 EMA.
        mask &= bars["bull"].to_numpy()
    d = bars[mask]
    d = d[np.isfinite(d[rank_col].to_numpy())]
    if d.empty:
        return d
    return (d.sort_values(["date", rank_col], ascending=[True, asc])
             .groupby("date").head(TOP_N))


def nifty_context() -> tuple[dict, dict, dict, dict]:
    """(bull, sideways, ret20, ret120) by date.

    BULL is the MTF configs' definition — close>EMA200 AND EMA50>EMA200 — not
    merely "above the 200", because S1/S3/S6 all gate on that exact phrase and
    a looser reading would let them trade states they were never measured in.
    """
    nf = pd.read_csv(D / "nifty50_daily_2010.csv").sort_values("date")
    nf["date"] = pd.to_datetime(nf["date"])
    c = nf.set_index("date")["nifty_close"].astype(float)
    e50, e200 = ema(c, 50), ema(c, 200)
    r20, r120 = c / c.shift(20) - 1, c / c.shift(120) - 1
    bull, side, ret20, ret120 = {}, {}, {}, {}
    for d in c.index:
        k = d.date()
        known = pd.notna(e200[d])
        bull[k] = bool(known and c[d] > e200[d] and e50[d] > e200[d])
        side[k] = bool(known and not bull[k]
                       and not (c[d] < e200[d] and e50[d] < e200[d]))
        ret20[k], ret120[k] = float(r20[d]), float(r120[d])
    return bull, side, ret20, ret120


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hold", default="20", help="comma-separated hold lengths")
    ap.add_argument("--rand", type=int, default=20, help="random pickers in the null")
    ap.add_argument("--engines", default=",".join(ENGINES))
    ap.add_argument("--regime", action="store_true",
                    help="also run every engine with the Nifty>200EMA overlay")
    ap.add_argument("--no-ca", action="store_true",
                    help="skip corporate-action adjustment (for comparison only)")
    a = ap.parse_args()
    holds = [int(x) for x in a.hold.split(",") if x.strip()]
    engines = [x.strip() for x in a.engines.split(",") if x.strip()]
    t0 = time.time()

    print("loading survivorship-free panel...", flush=True)
    panel = load_panel()
    print(f"  rows={len(panel):,}  ISINs={panel['isin'].nunique():,}  "
          f"{panel['date'].min().date()}..{panel['date'].max().date()}", flush=True)

    n_ca = 0
    if not a.no_ca:
        print("back-adjusting corporate actions...", flush=True)
        panel, n_ca = adjust_ca(panel)
        print(f"  {n_ca:,} split/bonus-sized discontinuities corrected", flush=True)

    _REG, NIFR63 = nifty_series()
    NIFBULL, NIFSIDE, NIFR20, NIFR120 = nifty_context()
    SYM = build_arrays(panel)
    del panel
    print(f"  usable ISINs (>={WARMUP}d): {len(SYM):,}", flush=True)

    print("building per-bar eligibility table...", flush=True)
    bars, keys = build_bar_table(SYM, NIFR63, NIFBULL, NIFR20, NIFR120, NIFSIDE)
    if bars.empty:
        raise SystemExit("no eligible bars — check the panel")
    print(f"  eligible bars={len(bars):,}  dates={bars['date'].nunique():,}  "
          f"v4 signals={int(bars['sig_v4'].sum()):,}  "
          f"({time.time()-t0:.0f}s)", flush=True)

    res = {
        "meta": {
            "universe": "survivorship-free point-in-time (ISIN-keyed, incl. delisted)",
            "prices": ("RAW bhavcopy OHLCV" if a.no_ca else
                       f"corporate-action back-adjusted ({n_ca:,} events)"),
            "entry": "open of the bar after the signal",
            "exit": "2.5-ATR close stop filled at the next open, else close of bar `hold`",
            "cost_pct_round_trip": 0.30,
            "picks_per_day": TOP_N,
            "splits": {"train": TRAIN, "val": VAL, "test": TEST},
            "random_pickers": a.rand,
            "eligible_bars": int(len(bars)),
            "note": ("TEST is reported, not used for selection. An engine has a "
                     "selection edge only above the random p95."),
        },
        "holds": {},
    }

    variants = [(e, False) for e in engines]
    if a.regime:
        variants += [(e, True) for e in engines]

    for hold in holds:
        print(f"\n=== hold {hold} ===", flush=True)
        # The null first: every engine is scored as a percentile of it.
        null = {"train": [], "val": [], "test": []}
        for s in range(a.rand):
            sel = select_random(bars, seed=1000 + s)
            for name, split in (("train", TRAIN), ("val", VAL), ("test", TEST)):
                m = split_metrics(sel, SYM, keys, hold, split)
                null[name].append(m["exp"] if m else None)
        rand_mean = {k: round(float(np.mean([x for x in v if x is not None])), 4)
                     for k, v in null.items()}
        rand_p95 = {k: round(float(np.percentile([x for x in v if x is not None], 95)), 4)
                    for k, v in null.items()}
        print(f"  random null  mean {rand_mean}  p95 {rand_p95}", flush=True)

        rows = {}
        for engine, regime in variants:
            label = f"{engine}_bull" if regime else engine
            sel = select_engine(bars, engine, regime=regime)
            if sel.empty:
                print(f"  {label:18s} no signals", flush=True)
                continue
            row = {"trades_total": int(len(sel))}
            for name, split in (("train", TRAIN), ("val", VAL), ("test", TEST)):
                m = split_metrics(sel, SYM, keys, hold, split)
                if m:
                    m["pct_of_random"] = pct_rank(m["exp"], null[name])
                    m["beats_random_p95"] = bool(m["exp"] > rand_p95[name])
                row[name] = m
            rows[label] = row
            fmt = lambda k: (f"{row[k]['exp']:6.2f} (p{row[k]['pct_of_random']:<5.1f})"
                             if row.get(k) else "   n/a       ")
            print(f"  {label:18s} TRAIN {fmt('train')}  VAL {fmt('val')}  "
                  f"TEST {fmt('test')}", flush=True)

        res["holds"][str(hold)] = {
            "random": {"mean": rand_mean, "p95": rand_p95, "raw": null},
            "engines": rows,
        }

    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}  ({time.time()-t0:.0f}s total)", flush=True)


if __name__ == "__main__":
    main()
