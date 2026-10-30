"""Final clean re-run: survivorship-free universe with corporate-action (split/
bonus) back-adjustment. Answers whether v5's collapse on the bias-free universe
(V5_BIASFREE_RESULT.md) was caused by split noise in RAW prices, or is real.

Method (transparent, heuristic, applied EQUALLY to both engines so the
comparison stays fair): for each ISIN, a close-to-close move beyond a
split/bonus-sized threshold (default ≤ -40% or ≥ +60%) is treated as a corporate
action; prior prices are back-adjusted by the cumulative ratio so the series is
continuous (the standard ratio/"panama" back-adjust). This removes fake ~50%
"returns" a 2:1 split otherwise injects into a holding window or a pullback
signal. It is NOT ground-truth CA data (NSE historical CA feed would be) — it is
a robustness check, and it may also neutralize genuine extreme gaps.

Run AFTER the universe build:
  backend/.venv/Scripts/python.exe research/scripts/v5/bias_free_ca_adjust.py
Out: research/data/v5_biasfree_ca_comparison.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.scripts.v5.bias_free_compare import (
    D, TRAIN, VAL, TEST, build_arrays, load_panel, make_signals, metrics,
    nifty_series, run,
)

OUT = D / "v5_biasfree_ca_comparison.json"
DROP_THRESH = 0.60      # close_t/close_{t-1} <= 0.60  -> split/bonus-sized drop
RISE_THRESH = 1.60      # >= 1.60 -> reverse-split/consolidation-sized rise


def adjust_ca(panel: pd.DataFrame) -> pd.DataFrame:
    """Back-adjust OHLC per ISIN so split/bonus-sized discontinuities vanish.
    Prior prices are scaled by the cumulative ratio at each detected CA day."""
    parts = []
    n_ca = 0
    for isin, g in panel.groupby("isin", observed=True):
        g = g.sort_values("date").copy()
        c = g["close"].to_numpy(float)
        f = np.ones(len(c))
        cum = 1.0
        for t in range(len(c) - 1, 0, -1):
            if c[t - 1] > 0:
                ratio = c[t] / c[t - 1]
                if ratio <= DROP_THRESH or ratio >= RISE_THRESH:
                    cum *= ratio
                    n_ca += 1
            f[t - 1] = cum
        for col in ("open", "high", "low", "close"):
            g[col] = g[col].to_numpy(float) * f
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    out.attrs["n_ca_events"] = n_ca
    return out


def run_all(panel, label, REG, NIFR63):
    SYM = build_arrays(panel)
    liquid, v4_proxy, v5 = make_signals(SYM, REG, NIFR63)
    res = {}
    for name, fn in (("v4_style_momentum", v4_proxy), ("v5_ensemble", v5)):
        df = run(SYM, liquid, fn)
        res[name] = {"n_all": int(len(df)),
                     "train": metrics(df, TRAIN), "val": metrics(df, VAL), "test": metrics(df, TEST)}
    return res


def main():
    print("loading survivorship-free panel...", flush=True)
    panel = load_panel()
    REG, NIFR63 = nifty_series()
    print(f"  rows={len(panel):,}  ISINs={panel['isin'].nunique():,}", flush=True)

    print("RAW (no CA adjustment)...", flush=True)
    raw = run_all(panel, "raw", REG, NIFR63)

    print("CA-adjusted (split/bonus back-adjust)...", flush=True)
    adj_panel = adjust_ca(panel)
    print(f"  CA-sized events back-adjusted: {adj_panel.attrs.get('n_ca_events', 0):,}", flush=True)
    adj = run_all(adj_panel, "adjusted", REG, NIFR63)

    result = {"meta": {"universe": "survivorship-free, ISIN-keyed",
                       "ca_method": f"price back-adjust (drop<={DROP_THRESH}, rise>={RISE_THRESH}) — heuristic, not NSE CA feed",
                       "n_ca_events": int(adj_panel.attrs.get("n_ca_events", 0))},
              "raw": raw, "ca_adjusted": adj}
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    print("\n=== v4-style vs v5 — RAW vs CA-ADJUSTED (expectancy %/trade) ===")
    hdr = f"{'engine':<20}{'':>6}{'TRAIN':>8}{'VAL':>8}{'TEST':>8}"
    print(hdr)
    for eng in ("v4_style_momentum", "v5_ensemble"):
        for lab, block in (("raw", raw), ("adj", adj)):
            e = block[eng]
            def g(p): return f"{e[p]['exp']:.3f}" if e[p] else "n/a"
            print(f"{eng:<20}{lab:>6}{g('train'):>8}{g('val'):>8}{g('test'):>8}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
