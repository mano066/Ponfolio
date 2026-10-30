"""FEATURE IC REPLICATION — do the ATR% and distance-to-252d-high effects hold?

`research/V6_TRAINING_PLAN.md` §Phase 4 measured, on a survivorship-free
CA-adjusted panel, that the cross-sectional percentile rank of ATR% predicts
forward returns NEGATIVELY (IC -0.0824, top-5 edge -3.364%, negative in 6 of 6
purged folds) while distance-to-252-day-high predicts them POSITIVELY (IC
+0.0908, 6 of 6). Those are the two strongest, most fold-consistent findings in
the whole research corpus, and production v4 ignores the first and uses the
second only as a binary 85%-of-52w-high flag.

The rig that produced those numbers no longer exists on this machine. This
script re-derives the same statistics from the ONE dataset that is still
recoverable — `dataset/store/daily/` (750 symbols, restored from git) — so the
mechanism can be checked before any production ranking change is built.

WHAT THIS IS NOT: it is not a backtest, has no portfolio simulation, no costs,
no stops, and no `rand:N` comparison. It cannot produce a promotion number. It
answers exactly one question: does the feature-level effect replicate here?

TWO LIMITATIONS THAT BOUND EVERY NUMBER BELOW
  1. The 750 symbols are TODAY'S index members. On 2010-01-04, 1,223 EQ symbols
     traded and 939 (77%) are absent from today's list. High-ATR names are
     disproportionately the ones that later collapsed, so dropping them
     UNDERSTATES the benefit of penalising ATR. The bias runs against the effect
     being measured, which makes a positive result meaningful and a negative one
     inconclusive.
  2. The store is only PARTIALLY corporate-action adjusted (the NSE charting
     feed is pre-adjusted for recent events but not older ones). We infer
     split/bonus factors from near-rational one-day price ratios and mask what
     is left. A printed ratio would be authoritative; an inferred one is not.

Only TRAIN (2010-01-01 -> 2019-12-31) is read by default. VAL and TEST stay
untouched so an honest promotion test remains possible later.

Run:
    python research/scripts/feature_ic.py
    python research/scripts/feature_ic.py --shuffle-null
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DAILY_GLOB = os.path.join(REPO, "dataset", "store", "daily", "*.parquet")
OUT_CSV = os.path.join(REPO, "research", "data", "feature_ic_train.csv")

# Frozen windows from the original work (dataset/splits.py, now lost — the
# values are recorded in V6_TRAINING_PLAN.md §2 task 0.6). Never retype these
# per-script; they live here now.
WINDOWS = {
    "train": ("2010-01-01", "2019-12-31"),
    "val": ("2020-01-01", "2022-12-31"),
    "test": ("2023-01-01", "2026-07-31"),
}

# Published values to sit beside the measured ones, so divergence is visible
# rather than argued. Source: V6_TRAINING_PLAN.md §Phase 4 table.
PUBLISHED = {
    "f_atr_pct_xr": (-0.0824, -3.364, "0/6"),
    "f_dist_252h_xr": (+0.0908, +0.321, "6/6"),
    "f_ret63_xr": (+0.0319, +0.342, "5/6"),
    "f_ret20_xr": (+0.0044, -0.398, "4/6"),
}
FEATURES = list(PUBLISHED)

# Split/bonus ratios common in Indian equities. A one-day price step within
# RATIO_TOL of one of these is treated as a corporate action rather than a
# return. Ordered so the largest is tried first.
RATIOS = (10.0, 6.0, 5.0, 4.0, 3.0, 2.5, 2.0, 11 / 6, 5 / 3, 1.5, 1.4, 1.25, 1.2)
RATIO_TOL = 0.02          # +/-2% around the nominal ratio
CA_MIN_STEP = 0.15        # only inspect one-day moves beyond +/-15%
RESIDUAL_MAX = 0.25       # after adjusting, mask anything still beyond +/-25%


# ───────────────────────────── load ─────────────────────────────
def load_panels(start: str, end: str, warmup_days: int = 420) -> dict:
    """Wide date x symbol frames for open/high/low/close/volume.

    Loads `warmup_days` of calendar history before `start` so the 252-session
    features are computed from real bars rather than from a truncated window —
    a symbol whose history begins inside the test window simply carries NaN
    features until it has enough bars, which is the no-lookahead behaviour we
    want.
    """
    lo = (pd.Timestamp(start) - pd.Timedelta(days=warmup_days)).normalize()
    hi = pd.Timestamp(end).normalize()
    cols = ["open", "high", "low", "close", "volume"]
    acc: dict[str, dict[str, pd.Series]] = {c: {} for c in cols}

    paths = sorted(glob.glob(DAILY_GLOB))
    if not paths:
        sys.exit(f"No parquets at {DAILY_GLOB}. Run: git checkout -- dataset")

    for p in paths:
        sym = os.path.basename(p)[:-8]
        df = pd.read_parquet(p, columns=["ts"] + cols)
        if df.empty:
            continue
        df = df[(df["ts"] >= lo) & (df["ts"] <= hi)]
        if df.empty:
            continue
        df = df.drop_duplicates("ts").sort_values("ts").set_index("ts")
        for c in cols:
            acc[c][sym] = df[c].astype("float64")

    close = pd.DataFrame(acc["close"]).sort_index()
    out = {"close": close}
    for c in cols:
        if c != "close":
            out[c] = pd.DataFrame(acc[c]).reindex(index=close.index,
                                                  columns=close.columns)
    return out


# ───────────────────── corporate-action cleanup ─────────────────────
def _infer_factor(step: float) -> float | None:
    """A one-day price ratio that lands on a split/bonus ratio, else None.

    `step` is close[t] / close[t-1]. A 10:1 split gives ~0.1, so the factor is
    1/step ~ 10. A reverse split gives step ~ 10.
    """
    for r in RATIOS:
        if abs(step * r - 1.0) <= RATIO_TOL:      # price fell by 1/r  -> split
            return r
        if abs(step / r - 1.0) <= RATIO_TOL:      # price rose by r    -> reverse
            return 1.0 / r
    return None


def clean_corporate_actions(panels: dict) -> tuple[dict, dict]:
    """Undo inferable splits/bonuses; mask what stays unexplained.

    For each symbol independently: walk its one-day close ratios, and where a
    step beyond +/-CA_MIN_STEP matches a known ratio, divide ALL EARLIER bars by
    that factor (the modern price level is the anchor, so the adjustment is
    backwards). Steps that match nothing are masked — set to NaN — because a
    fabricated adjustment is worse than a hole, and any label window containing
    a hole becomes NaN automatically.
    """
    close = panels["close"]
    stats = {"adjusted": 0, "masked": 0, "symbols_adjusted": 0,
             "symbols_masked": 0}
    factors = pd.DataFrame(1.0, index=close.index, columns=close.columns)
    mask = pd.DataFrame(False, index=close.index, columns=close.columns)

    for sym in close.columns:
        s = close[sym]
        vals = s.to_numpy()
        ok = ~np.isnan(vals)
        if ok.sum() < 30:
            continue
        idx = np.flatnonzero(ok)
        step = np.full(len(vals), np.nan)
        step[idx[1:]] = vals[idx[1:]] / vals[idx[:-1]]

        cand = np.flatnonzero(np.abs(step - 1.0) > CA_MIN_STEP)
        if cand.size == 0:
            continue

        col_factor = np.ones(len(vals))
        col_mask = np.zeros(len(vals), dtype=bool)
        n_adj = n_msk = 0
        # Walk newest -> oldest and accumulate, so several actions on one
        # symbol compose instead of overwriting each other.
        cum = 1.0
        for i in sorted(cand, reverse=True):
            f = _infer_factor(float(step[i]))
            if f is not None:
                cum *= f
                col_factor[:i] = cum          # everything strictly before the step
                n_adj += 1
            else:
                col_mask[i] = True
                n_msk += 1

        if n_adj:
            factors[sym] = col_factor
            stats["adjusted"] += n_adj
            stats["symbols_adjusted"] += 1
        if n_msk:
            mask[sym] = col_mask
            stats["symbols_masked"] += 1

    adj = {k: v / factors if k != "volume" else v * factors
           for k, v in panels.items()}

    # Second pass: anything still moving beyond RESIDUAL_MAX after adjustment
    # is an unexplained step (suspension gap, penny-stock artefact, or a real
    # crash we cannot distinguish). Mask it rather than adjust it.
    r = adj["close"] / adj["close"].shift(1) - 1
    residual = r.abs() > RESIDUAL_MAX
    mask = mask | residual.fillna(False)
    stats["masked"] = int(mask.to_numpy().sum())
    stats["symbols_masked"] = int(mask.any(axis=0).sum())

    for k in adj:
        adj[k] = adj[k].mask(mask)
    return adj, stats


# ───────────────────── eligibility & features ─────────────────────
def eligibility(panels: dict, min_turnover: float, min_price: float) -> pd.DataFrame:
    """Point-in-time liquid universe: 20-day average turnover known on day t.

    `.shift(1)` is what makes it point-in-time — day t's decision may only use
    turnover through day t-1's close.
    """
    turn = (panels["close"] * panels["volume"]).rolling(20, min_periods=15).mean()
    return (turn.shift(1) > min_turnover) & (panels["close"] > min_price)


def _wilder_atr(high, low, close, n: int = 14) -> pd.DataFrame:
    prev = close.shift(1)
    tr = pd.concat([(high - low).stack(),
                    (high - prev).abs().stack(),
                    (low - prev).abs().stack()], axis=1).max(axis=1).unstack()
    tr = tr.reindex(index=close.index, columns=close.columns)
    return tr.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean()


def build_features(panels: dict) -> dict[str, pd.DataFrame]:
    """The four cross-sectional rank features, each using bars up to day t only.

    `.rank(axis=1, pct=True)` ranks ACROSS SYMBOLS within a date — that is what
    the `_xr` suffix means in the original work, and it is the only thing that
    matters when the production decision is "pick 5 of today's candidates".
    """
    c, h, l = panels["close"], panels["high"], panels["low"]
    raw = {
        "f_atr_pct_xr": _wilder_atr(h, l, c) / c,
        "f_dist_252h_xr": c / h.rolling(252, min_periods=200).max(),
        "f_ret63_xr": c / c.shift(63) - 1,
        "f_ret20_xr": c / c.shift(20) - 1,
    }
    return {k: v.rank(axis=1, pct=True) for k, v in raw.items()}


def build_label(panels: dict, fwd: int) -> pd.DataFrame:
    """Forward return entered at the NEXT open, exited `fwd` sessions later.

    Entry at open[t+1] (never close[t] — that would be a same-bar fill the live
    scanner cannot achieve), exit at close[t+fwd].
    """
    return panels["close"].shift(-fwd) / panels["open"].shift(-1) - 1


# ───────────────────────────── statistics ─────────────────────────────
def _winsorise(s: pd.Series, lo: float = 0.01, hi: float = 0.99) -> pd.Series:
    return s.clip(s.quantile(lo), s.quantile(hi))


def fold_stats(long: pd.DataFrame, feat: str, top_n: int = 5) -> tuple[float, float, int]:
    """Per-day rank IC and top-N edge for one feature over one fold.

    IC is the primary statistic BECAUSE it is rank-based: the store is only
    partially CA-adjusted, and a single fake -90% return would dominate any
    mean. `top_n` edge is a mean, so it runs on winsorised labels.
    """
    g = long.groupby("date", sort=False)
    fr = g[feat].rank(pct=True)
    lr = g["label"].rank(pct=True)
    d = pd.DataFrame({"date": long["date"], "fr": fr, "lr": lr})
    # Per-day Pearson of the two within-day ranks == per-day Spearman.
    ic = (d.groupby("date")[["fr", "lr"]]
           .corr().unstack().iloc[:, 1].dropna())

    w = long.assign(wl=_winsorise(long["label"]))
    top = (w.sort_values(feat, ascending=False)
            .groupby("date", sort=False)["wl"].head(top_n)
            .groupby(w["date"]).mean())
    base = w.groupby("date")["wl"].mean()
    edge = (top - base).dropna()
    return float(ic.mean()), float(edge.mean() * 100), int(len(ic))


def make_folds(dates: np.ndarray, n_folds: int, embargo: int) -> list[np.ndarray]:
    """Contiguous date blocks with an `embargo`-session gap trimmed off each
    side, so a fold's label windows cannot reach into its neighbours."""
    chunks = np.array_split(dates, n_folds)
    out = []
    for i, ch in enumerate(chunks):
        lo = embargo if i > 0 else 0
        hi = len(ch) - embargo if i < n_folds - 1 else len(ch)
        if hi - lo > embargo:
            out.append(ch[lo:hi])
    return out


# ───────────────────────────── main ─────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="train", choices=list(WINDOWS))
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--embargo", type=int, default=20)
    ap.add_argument("--fwd", type=int, default=20, help="forward sessions held")
    ap.add_argument("--min-turnover", type=float, default=5e7, help="rupees, 20d avg")
    ap.add_argument("--min-price", type=float, default=5.0)
    ap.add_argument("--shuffle-null", action="store_true",
                    help="permute labels WITHIN each day; every IC must collapse to ~0")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    start, end = WINDOWS[a.window]
    print(f"window {a.window}: {start} -> {end} | fwd={a.fwd} "
          f"folds={a.folds} embargo={a.embargo}"
          f"{'  [SHUFFLED NULL]' if a.shuffle_null else ''}", flush=True)

    print("loading store...", flush=True)
    panels = load_panels(start, end)
    print(f"  panel {panels['close'].shape[0]} sessions x "
          f"{panels['close'].shape[1]} symbols", flush=True)

    print("cleaning corporate actions...", flush=True)
    panels, ca = clean_corporate_actions(panels)
    print(f"  inferred {ca['adjusted']} split/bonus factors over "
          f"{ca['symbols_adjusted']} symbols; masked {ca['masked']} "
          f"unexplained bars over {ca['symbols_masked']} symbols", flush=True)

    elig = eligibility(panels, a.min_turnover, a.min_price)
    feats = build_features(panels)
    label = build_label(panels, a.fwd)

    keep = elig & label.notna()
    for f in FEATURES:
        keep &= feats[f].notna()
    keep = keep.loc[start:end]

    long = pd.DataFrame({"date": np.repeat(keep.index.values, keep.shape[1]),
                         "sym": np.tile(keep.columns.values, keep.shape[0])})
    long["label"] = label.loc[keep.index].to_numpy().ravel()
    for f in FEATURES:
        long[f] = feats[f].loc[keep.index].to_numpy().ravel()
    long = long[keep.to_numpy().ravel()].reset_index(drop=True)

    per_day = long.groupby("date").size()
    print(f"  {len(long):,} eligible stock-days over {len(per_day):,} sessions "
          f"| median {int(per_day.median())} names/day", flush=True)
    if per_day.median() < 50:
        print("  REFUSING: fewer than 50 names/day — cross-section too thin.")
        return 2

    if a.shuffle_null:
        rng = np.random.default_rng(a.seed)
        long["label"] = (long.groupby("date")["label"]
                             .transform(lambda s: rng.permutation(s.to_numpy())))

    # G1 — label sanity. Published grade means: -11.92 / -4.49 / -0.22 / +4.58 / +16.33
    q = long.groupby("date")["label"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False, duplicates="drop"))
    grades = long.groupby(q)["label"].mean() * 100
    print("\nG1 label sanity — within-day quintile means (%):")
    print("   measured : " + "  ".join(f"{v:+7.2f}" for v in grades))
    print("   published:   -11.92    -4.49    -0.22    +4.58   +16.33")

    dates = np.sort(long["date"].unique())
    folds = make_folds(dates, a.folds, a.embargo)
    print(f"\n{len(folds)} purged folds, {a.embargo}-session embargo each side")

    rows = []
    for f in FEATURES:
        ics, edges = [], []
        for k, fd in enumerate(folds):
            sub = long[long["date"].isin(fd)]
            ic, edge, n = fold_stats(sub, f)
            ics.append(ic)
            edges.append(edge)
        ics_a, edges_a = np.array(ics), np.array(edges)
        pos = int((ics_a > 0).sum())
        rows.append({
            "feature": f, "ic": ics_a.mean(), "ic_sd": ics_a.std(ddof=1),
            "top5_edge": edges_a.mean(), "edge_sd": edges_a.std(ddof=1),
            "folds_pos": pos, "n_folds": len(folds),
            "pub_ic": PUBLISHED[f][0], "pub_edge": PUBLISHED[f][1],
            "pub_folds": PUBLISHED[f][2],
            **{f"ic_fold{i}": v for i, v in enumerate(ics)},
        })

    res = pd.DataFrame(rows)
    tag = "NULL" if a.shuffle_null else "REAL"
    print(f"\n{tag} — measured vs published (V6_TRAINING_PLAN.md Phase 4)")
    print(f"{'feature':18s} {'IC':>9s} {'+/-sd':>7s} {'folds+':>7s} "
          f"{'top5%':>8s} | {'pub IC':>8s} {'pub top5%':>10s} {'pub':>5s}")
    for _, r in res.iterrows():
        print(f"{r['feature']:18s} {r['ic']:+9.4f} {r['ic_sd']:7.4f} "
              f"{int(r['folds_pos'])}/{int(r['n_folds']):<5d} "
              f"{r['top5_edge']:+8.3f} | {r['pub_ic']:+8.4f} "
              f"{r['pub_edge']:+10.3f} {r['pub_folds']:>5s}")

    # ── pre-registered gates (research/FEATURE_IC_REPLICATION.md) ──
    print("\ngates:")
    if a.shuffle_null:
        worst = res["ic"].abs().max()
        print(f"  G0 shuffled null |IC| < 0.01 : "
              f"{'PASS' if worst < 0.01 else 'FAIL'}  (worst |IC| {worst:.4f})")
    else:
        ordered = bool(np.all(np.diff(grades.to_numpy()) > 0))
        print(f"  G1 grade means increasing    : {'PASS' if ordered else 'FAIL'}")
        for gate, feat, want in (("G2", "f_atr_pct_xr", "neg"),
                                 ("G3", "f_dist_252h_xr", "pos")):
            r = res[res["feature"] == feat].iloc[0]
            n = int(r["n_folds"])
            consistent = (n - int(r["folds_pos"])) if want == "neg" else int(r["folds_pos"])
            sign_ok = (r["ic"] < 0) if want == "neg" else (r["ic"] > 0)
            ok = sign_ok and consistent >= n - 1
            print(f"  {gate} {feat:16s} {want}, >={n-1}/{n} folds : "
                  f"{'PASS' if ok else 'FAIL'}  "
                  f"(IC {r['ic']:+.4f}, {consistent}/{n} folds {want})")

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    out = OUT_CSV.replace(".csv", "_null.csv") if a.shuffle_null else OUT_CSV
    res.assign(window=a.window, fwd=a.fwd, min_turnover=a.min_turnover,
               names_per_day=int(per_day.median()),
               ca_adjusted=ca["adjusted"], ca_masked=ca["masked"]).to_csv(out, index=False)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
