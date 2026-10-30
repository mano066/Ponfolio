"""Multi-timeframe swing-strategy backtest engine (DAILY resolution).

Backtests seven swing-strategy families (2-20 session holds) on the daily NSE
lake, with NIFTY-daily market-regime context, walk-forward train/val/test,
realistic costs, regime splits, cost/slippage sensitivity, ablations, and a
portfolio simulation for the shortlist.

MEASURED vs UNVERIFIED (read this):
  * MEASURED here = daily-resolution results on the survivorship-biased current
    ~750-name universe (today's members pulled back to 2010). Raw OHLC prices;
    ~13 known unadjusted corporate-action rows (documented, not repaired). This
    is an apples-to-apples comparison vs v4, NOT a bias-free absolute.
  * UNVERIFIED / DESIGN-ONLY = every lower-timeframe (60m..1m) entry-timing rule.
    There is NO per-stock intraday history to backtest it (only NIFTY/BANKNIFTY
    indices, ending 2020, + a 7-day HDFCBANK sample). Those rules are specified
    in the strategy configs and deferred to forward paper shadow mode. This
    engine therefore uses a DAILY proxy for "lower-timeframe confirmation" and
    labels it as such; it never claims an intraday backtest.

Run:
  backend/.venv/Scripts/python.exe research/scripts/multitimeframe/mtf_backtest.py
Outputs (machine-readable):
  research/data/mtf_backtest_results.json
  research/data/mtf_strategy_configs.json
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

D = Path(__file__).resolve().parents[2] / "data"
RESULTS = D / "mtf_backtest_results.json"
CONFIGS = D / "mtf_strategy_configs.json"

# ── frozen protocol ───────────────────────────────────────────────────────
COST_BASE = 0.30          # % round trip (brokerage+STT+charges+GST proxy)
SLIP_SCENARIOS = [0.0, 0.05, 0.10, 0.20]   # extra one-way % slippage
TOP_N = 5                 # picks/day/strategy
GAP_MAX = 4.0             # skip T+1 open gap-ups > this %
MIN_TURNOVER = 1e7        # ₹1cr 20d avg traded value (liquidity)
MIN_PRICE = 5.0
MIN_UPSIDE = 2.0          # % min remaining upside to target
MIN_RR = 1.5              # min reward:risk for an actionable target
TRAIN = ("2011-01-01", "2019-12-31")
VAL = ("2020-01-01", "2022-12-31")
TEST = ("2023-01-01", "2026-12-31")   # untouched: evaluated once, not tuned on

print("loading daily lake...", flush=True)
px = pd.read_csv(
    D / "nse_universe_2010_ohlcv.csv.gz",
    usecols=["date", "symbol", "open", "high", "low", "close", "volume"],
    dtype={"symbol": "category", "open": "f4", "high": "f4", "low": "f4",
           "close": "f4", "volume": "f8"},
)
nif = pd.read_csv(D / "nifty50_daily_2010.csv").sort_values("date")
nser = nif.set_index("date")["nifty_close"]


def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


# ── NIFTY market-regime series (daily) ──────────────────────────────────────
print("building NIFTY regime...", flush=True)
nfc = nser.astype(float)
n_e50, n_e200 = ema(nfc, 50), ema(nfc, 200)
n_vol = nfc.pct_change().rolling(20).std() * np.sqrt(252)
n_vol_hi = n_vol.rolling(252, min_periods=120).quantile(0.80)
n_r63 = (nfc / nfc.shift(63) - 1)
regime = {}
for dt in nfc.index:
    c, e50, e200 = nfc[dt], n_e50[dt], n_e200[dt]
    vol, volhi = n_vol[dt], n_vol_hi[dt]
    if pd.isna(e200):
        regime[dt] = "UNKNOWN"; continue
    if pd.notna(volhi) and vol > volhi and c < e50:
        regime[dt] = "HIGHVOL_CORRECTION"
    elif c > e200 and e50 > e200:
        regime[dt] = "BULL"
    elif c < e200 and e50 < e200:
        regime[dt] = "BEAR"
    else:
        regime[dt] = "SIDEWAYS"
nifty_r63 = n_r63.to_dict()
nifty_r20 = (nfc / nfc.shift(20) - 1).to_dict()
nifty_r120 = (nfc / nfc.shift(120) - 1).to_dict()

# ── per-symbol indicator arrays ─────────────────────────────────────────────
print("building per-symbol indicators (751 symbols)...", flush=True)
SYM = {}
for sym, g in px.groupby("symbol", sort=False, observed=True):
    g = g.sort_values("date")
    c = g["close"].astype(float).reset_index(drop=True)
    o = g["open"].astype(float).reset_index(drop=True)
    h = g["high"].astype(float).reset_index(drop=True)
    lo = g["low"].astype(float).reset_index(drop=True)
    v = g["volume"].astype(float).reset_index(drop=True)
    n = len(c)
    if n < 260:
        continue
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    r = rsi(c)
    pc = c.shift(1)
    tr = pd.concat([h - lo, (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    ma20 = c.rolling(20).mean()
    sd20 = c.rolling(20).std()
    bbw = (4 * sd20) / ma20.replace(0, np.nan)            # band width / price
    bbw_q25 = bbw.rolling(100, min_periods=60).quantile(0.25)
    hh20 = h.rolling(20).max()
    hh55 = h.rolling(55).max()
    ll20 = lo.rolling(20).min()
    turn20 = (c * v).rolling(20).mean()
    ret5 = c / c.shift(5) - 1
    ret10 = c / c.shift(10) - 1
    ret20 = c / c.shift(20) - 1
    ret60 = c / c.shift(63) - 1
    ret120 = c / c.shift(120) - 1
    vma20 = v.rolling(20).mean()
    vratio = v / vma20.replace(0, np.nan)
    ema50_rising = e50 > e50.shift(5)
    macd_up = ema(c, 12) > ema(c, 26)
    SYM[str(sym)] = dict(
        dates=g["date"].to_numpy(), o=o.to_numpy(), h=h.to_numpy(),
        l=lo.to_numpy(), c=c.to_numpy(), atr=atr.to_numpy(),
        e20=e20.to_numpy(), e50=e50.to_numpy(), e200=e200.to_numpy(),
        rsi=r.to_numpy(), bbw=bbw.to_numpy(), bbwq=bbw_q25.to_numpy(),
        hh20=hh20.to_numpy(), hh55=hh55.to_numpy(), ll20=ll20.to_numpy(),
        turn=turn20.to_numpy(), vratio=vratio.to_numpy(),
        ret5=ret5.to_numpy(), ret10=ret10.to_numpy(), ret20=ret20.to_numpy(),
        ret60=ret60.to_numpy(), ret120=ret120.to_numpy(),
        e50rise=ema50_rising.to_numpy(), macdup=macd_up.to_numpy(),
        idx={d: i for i, d in enumerate(g["date"].to_numpy())},
    )
del px
print(f"usable symbols: {len(SYM)}", flush=True)


# ── strategy signal generators ──────────────────────────────────────────────
# Each returns True if symbol `s` at integer bar `j` (a COMPLETED daily candle)
# is a valid signal. Entry is the NEXT session open (j+1). `flags` toggles
# ablation components. All fields are as-of bar j (no lookahead).
def liquid(a, j):
    return a["turn"][j] >= MIN_TURNOVER and a["c"][j] >= MIN_PRICE


def s1_trend_pullback(a, j, reg, flags):
    if flags.get("regime", True) and reg != "BULL":
        return False
    c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
    if flags.get("trend", True) and not (c > e50 > e200 and a["e50rise"][j]):
        return False
    near_e20 = a["l"][j] <= e20 * 1.02 or abs(c / e20 - 1) <= 0.02
    reclaim = c > e20
    cooled = 40 <= a["rsi"][j] <= 62
    strength = a["c"][j] > a["o"][j]
    return bool(near_e20 and reclaim and cooled and strength)


def s2_vol_contraction(a, j, reg, flags):
    if flags.get("regime", True) and reg not in ("BULL", "SIDEWAYS"):
        return False
    c, e20, e50, e200 = a["c"][j], a["e20"][j], a["e50"][j], a["e200"][j]
    if flags.get("trend", True) and not (c > e50 > e200):
        return False
    contracted = np.isfinite(a["bbwq"][j]) and a["bbw"][j] <= a["bbwq"][j]
    breakout = j >= 1 and c > a["hh20"][j - 1]
    not_extended = c <= e20 * 1.15
    volok = (not flags.get("volume", True)) or (np.isfinite(a["vratio"][j]) and a["vratio"][j] >= 1.2)
    return bool(contracted and breakout and not_extended and volok)


def s3_rs_continuation(a, j, reg, flags):
    if flags.get("regime", True) and reg != "BULL":
        return False
    c, e50, e200 = a["c"][j], a["e50"][j], a["e200"][j]
    if flags.get("trend", True) and not (c > e50 > e200):
        return False
    dt = a["dates"][j]
    if flags.get("rs", True):
        rs20 = a["ret20"][j] > nifty_r20.get(dt, np.nan)
        rs60 = a["ret60"][j] > nifty_r63.get(dt, np.nan)
        rs120 = a["ret120"][j] > nifty_r120.get(dt, np.nan)
        if not (rs20 and rs60 and rs120):
            return False
    shallow = j >= 1 and c >= a["hh20"][j - 1] * 0.92
    renewed = c > a["c"][j - 1] and c > a["e20"][j]
    return bool(shallow and renewed)


def s4_failed_breakdown(a, j, reg, flags):
    if flags.get("regime", True) and reg not in ("SIDEWAYS", "BULL"):
        return False
    c, e200, e50 = a["c"][j], a["e200"][j], a["e50"][j]
    if flags.get("trend", True) and not (c > e200 and e50 > e200):
        return False
    if j < 1:
        return False
    undercut = a["l"][j] < a["ll20"][j - 1]
    reclaim = c > a["ll20"][j - 1]
    return bool(undercut and reclaim)


def s5_gap_and_hold(a, j, reg, flags):
    if flags.get("regime", True) and reg not in ("BULL", "SIDEWAYS"):
        return False
    if j < 1:
        return False
    pcl = a["c"][j - 1]
    gap = a["o"][j] / pcl - 1 if pcl > 0 else 0
    if not (0.03 <= gap <= 0.15):
        return False
    holds = a["c"][j] >= pcl * (1 + gap / 2) and a["c"][j] >= a["o"][j] * 0.99
    ctx = a["c"][j] > a["e50"][j]
    return bool(holds and ctx)


def s6_mtf_momentum(a, j, reg, flags):
    # DAILY PROXY for multi-timeframe alignment (intraday unverified — see header)
    if flags.get("regime", True) and reg != "BULL":
        return False
    c, e50, e200 = a["c"][j], a["e50"][j], a["e200"][j]
    if flags.get("trend", True) and not (c > e50 > e200):
        return False
    # "5h/2h/60m bullish" daily proxy: multi-horizon positive momentum + macd up.
    align = a["ret5"][j] > 0 and a["ret10"][j] > 0 and a["ret20"][j] > 0
    recovering = a["macdup"][j] and 45 <= a["rsi"][j] < 70   # not overbought
    if flags.get("lower_tf", True) and not align:
        return False
    return bool(recovering)


STRATS = {
    "S1_trend_pullback": (s1_trend_pullback, "ret60", 20),
    "S2_vol_contraction_breakout": (s2_vol_contraction, "ret60", 20),
    "S3_rs_continuation": (s3_rs_continuation, "ret60", 20),
    "S4_failed_breakdown_meanrev": (s4_failed_breakdown, "ret20", 10),
    "S5_gap_and_hold": (s5_gap_and_hold, "ret20", 10),
    "S6_mtf_momentum_alignment": (s6_mtf_momentum, "ret20", 20),
    # S7 is the regime overlay applied to S1 (see run_strategy sizing).
}


def build_trades(sig_fn, rank_key, hold, flags, size_by_regime=False):
    """Materialize every trade for a strategy across all history (no period
    filter yet). Entry = next-session open, skip gap>GAP_MAX. Target = entry +
    3*ATR (research target), stop = entry - 2.5*ATR (v4 unit)."""
    rows = []
    for s, a in SYM.items():
        c = a["c"]
        n = len(c)
        for j in range(260, n - 1):
            dt = a["dates"][j]
            reg = regime.get(dt, "UNKNOWN")
            if not liquid(a, j):
                continue
            if not sig_fn(a, j, reg, flags):
                continue
            e = float(a["o"][j + 1])
            cT = float(c[j])
            atr = float(a["atr"][j])
            if not (e > 0 and atr > 0):
                continue
            gap = (e / cT - 1) * 100 if cT > 0 else np.nan
            m = min(hold, n - (j + 1))
            if m < 1:
                continue
            rows.append(dict(
                date=dt, sym=s, reg=reg, e=e, cT=cT, atr=atr, gap=gap,
                rank=float(a[rank_key][j]) if np.isfinite(a[rank_key][j]) else -9,
                op=a["o"][j + 1:j + 2 + m].astype(float),
                hi=a["h"][j + 1:j + 1 + m].astype(float),
                lo=a["l"][j + 1:j + 1 + m].astype(float),
                cl=a["c"][j + 1:j + 1 + m].astype(float),
                m=m, size=_regime_size(reg) if size_by_regime else 1.0,
            ))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # top-N/day by rank
    df = df.sort_values(["date", "rank"], ascending=[True, False]).groupby("date").head(TOP_N)
    return df.reset_index(drop=True)


def _regime_size(reg):
    return {"BULL": 1.0, "SIDEWAYS": 0.5, "HIGHVOL_CORRECTION": 0.25,
            "BEAR": 0.0, "UNKNOWN": 0.0}.get(reg, 0.0)


def exit_v4(t, cost, slip):
    """No-TP, stop 2.5xATR on close, exit next open if breached; time exit."""
    e = t["e"] * (1 + slip / 100)
    sl = t["e"] - 2.5 * t["atr"]
    for k in range(t["m"]):
        if t["cl"][k] <= sl:
            ex = t["op"][k + 1] if k + 1 < len(t["op"]) else t["cl"][k]
            return (ex * (1 - slip / 100) / e - 1) * 100 - cost
    ex = t["cl"][t["m"] - 1]
    return (ex * (1 - slip / 100) / e - 1) * 100 - cost


def exit_target(t, cost, slip):
    """Target=+3xATR, stop=-1.5xATR, stop-first if both touched in a candle."""
    e = t["e"] * (1 + slip / 100)
    sl = t["e"] - 1.5 * t["atr"]
    tp = t["e"] + 3.0 * t["atr"]
    for k in range(t["m"]):
        if t["lo"][k] <= sl:                       # conservative: stop first
            ex = min(sl, t["op"][k]) if k < len(t["op"]) else sl
            return (ex * (1 - slip / 100) / e - 1) * 100 - cost
        if t["hi"][k] >= tp:
            return (tp * (1 - slip / 100) / e - 1) * 100 - cost
    ex = t["cl"][t["m"] - 1]
    return (ex * (1 - slip / 100) / e - 1) * 100 - cost


def in_period(dates, period):
    lo, hi = period
    return (dates >= lo) & (dates <= hi)


def trade_metrics(nets):
    if len(nets) < 50:
        return None
    nets = np.asarray(nets, dtype=float)
    w = nets > 0
    wins, losses = nets[w], nets[~w]
    total_win = wins.sum()
    # Profit concentration: share of total gross profit from the best 5 trades
    # (a small share means the edge is broad, not a few lucky outliers).
    top5 = np.sort(wins)[-5:].sum() if len(wins) else 0.0
    conc = round(float(top5 / total_win), 3) if total_win > 0 and len(wins) >= 5 else None
    return dict(
        n=int(len(nets)), win=round(float(w.mean() * 100), 2),
        avg_win=round(float(wins.mean()), 3) if len(wins) else 0.0,
        avg_loss=round(float(losses.mean()), 3) if len(losses) else 0.0,
        exp=round(float(nets.mean()), 4), med=round(float(np.median(nets)), 4),
        pf=round(float(total_win / max(1e-9, -losses.sum())), 3),
        best=round(float(nets.max()), 2), worst=round(float(nets.min()), 2),
        top5_profit_share=conc,
    )


def _f(x):
    return f"{x:.3f}" if isinstance(x, (int, float)) else "n/a"


def gap_filtered(df):
    return df[df["gap"] <= GAP_MAX]


# ── run all strategies ──────────────────────────────────────────────────────
def run_strategy(name, sig_fn, rank_key, hold, size_by_regime=False):
    df = gap_filtered(build_trades(sig_fn, rank_key, hold, {}, size_by_regime))
    out = {"total_trades_all_periods": int(len(df))}
    dates = df["date"].to_numpy() if len(df) else np.array([])
    for exname, exfn in (("v4_notp", exit_v4), ("target_3atr", exit_target)):
        nets_all = np.array([exfn(r, COST_BASE, 0.0) for _, r in df.iterrows()]) if len(df) else np.array([])
        per = {}
        for pname, period in (("train", TRAIN), ("val", VAL), ("test", TEST)):
            mask = in_period(dates, period)
            per[pname] = trade_metrics(nets_all[mask]) if len(nets_all) else None
        out[exname] = per
    # regime split (v4 exit, all periods)
    reg_split = {}
    if len(df):
        nets_all = np.array([exit_v4(r, COST_BASE, 0.0) for _, r in df.iterrows()])
        for rg in ("BULL", "SIDEWAYS", "HIGHVOL_CORRECTION", "BEAR"):
            m = df["reg"].to_numpy() == rg
            reg_split[rg] = trade_metrics(nets_all[m])
    out["regime_split_v4"] = reg_split
    return out, df


print("\n=== running strategies (measured, daily) ===", flush=True)
results = {"meta": {
    "measured_scope": "daily, survivorship-biased current ~750 universe, raw OHLC",
    "unverified_scope": "all lower-timeframe (60m-1m) entry timing — no per-stock intraday data",
    "cost_base_pct": COST_BASE, "top_n": TOP_N, "gap_max_pct": GAP_MAX,
    "train": TRAIN, "val": VAL, "test": TEST,
    "min_upside_pct": MIN_UPSIDE, "min_rr": MIN_RR,
}, "strategies": {}}
trade_frames = {}
for name, (fn, rk, hold) in STRATS.items():
    print(f"  {name}...", flush=True)
    res, df = run_strategy(name, fn, rk, hold)
    results["strategies"][name] = res
    trade_frames[name] = df

# S7 = regime-sized overlay on S1
print("  S7_regime_defensive (overlay on S1)...", flush=True)
res7, df7 = run_strategy("S7", s1_trend_pullback, "ret60", 20, size_by_regime=True)
results["strategies"]["S7_regime_defensive"] = res7
trade_frames["S7_regime_defensive"] = df7

# ── cost/slippage sensitivity (VAL, v4 exit) ────────────────────────────────
print("\n=== cost/slippage sensitivity (VAL) ===", flush=True)
cost_sens = {}
for name, df in trade_frames.items():
    if not len(df):
        continue
    d = df[in_period(df["date"].to_numpy(), VAL)]
    row = {}
    for slip in SLIP_SCENARIOS:
        nets = np.array([exit_v4(r, COST_BASE, slip) for _, r in d.iterrows()]) if len(d) else np.array([])
        m = trade_metrics(nets)
        row[f"slip_{slip}"] = m["exp"] if m else None
    cost_sens[name] = row
results["cost_slippage_sensitivity_val_exp"] = cost_sens

# ── ablations (VAL expectancy delta, v4 exit) ───────────────────────────────
print("=== ablations (VAL) ===", flush=True)
ABLATE = ["regime", "trend", "volume", "rs", "lower_tf"]
abl = {}
for name, (fn, rk, hold) in STRATS.items():
    base_df = gap_filtered(build_trades(fn, rk, hold, {}))
    bd = base_df[in_period(base_df["date"].to_numpy(), VAL)]
    base_exp = trade_metrics(np.array([exit_v4(r, COST_BASE, 0) for _, r in bd.iterrows()])) if len(bd) else None
    entry = {"base_exp": base_exp["exp"] if base_exp else None,
             "base_n": base_exp["n"] if base_exp else 0}
    for comp in ABLATE:
        flags = {comp: False}
        adf = gap_filtered(build_trades(fn, rk, hold, flags))
        ad = adf[in_period(adf["date"].to_numpy(), VAL)]
        m = trade_metrics(np.array([exit_v4(r, COST_BASE, 0) for _, r in ad.iterrows()])) if len(ad) else None
        entry[f"no_{comp}"] = {"exp": m["exp"] if m else None, "n": m["n"] if m else 0}
    abl[name] = entry
results["ablations_val"] = abl

# ── portfolio simulation (all strategies, full 2011-2026, v4 exit) ──────────
print("=== portfolio sim ===", flush=True)


def portfolio_sim(df, capital=1_000_000, max_pos=8, cost=COST_BASE):
    """Equal-weight, <=max_pos concurrent, cap/max_pos per position, T+1 open
    entry, v4 exit. Builds a daily equity curve for CAGR/DD/Sharpe/Sortino."""
    if not len(df):
        return None
    df = df.sort_values("date").reset_index(drop=True)
    # exit date index = entry bar + holding used; approximate exit day offset by m
    # We only have per-trade net%; sequence by entry date, cap concurrency.
    slot_free_at = []            # list of exit-date strings for open slots
    trades = []
    for _, r in df.iterrows():
        d0 = r["date"]
        slot_free_at = [x for x in slot_free_at if x > d0]
        if len(slot_free_at) >= max_pos:
            continue
        net = exit_v4(r, cost, 0.0) / 100.0
        # exit date = last dates covered; approx via m sessions ahead
        a = SYM[r["sym"]]
        j = a["idx"][d0]
        ex_j = min(j + r["m"], len(a["dates"]) - 1)
        d1 = a["dates"][ex_j]
        slot_free_at.append(d1)
        trades.append((d0, d1, net))
    if not trades:
        return None
    tdf = pd.DataFrame(trades, columns=["entry", "exit", "net"])
    # daily equity: allocate cap/max_pos, compound realized P&L at exit dates
    per_trade_cap = capital / max_pos
    tdf = tdf.sort_values("exit")
    equity = capital
    curve = []
    all_days = sorted(set(tdf["exit"]))
    realized = tdf.groupby("exit")["net"].apply(list).to_dict()
    for day in all_days:
        for net in realized[day]:
            equity += per_trade_cap * net
        curve.append((day, equity))
    eq = pd.Series([c[1] for c in curve], index=pd.to_datetime([c[0] for c in curve]))
    if len(eq) < 5:
        return None
    rets = eq.pct_change().dropna()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / capital) ** (1 / max(years, 0.5)) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0
    downside = rets[rets < 0].std()
    sortino = (rets.mean() / downside * np.sqrt(252)) if downside and downside > 0 else 0
    calmar = (cagr / abs(dd)) if dd < 0 else 0
    return dict(
        final_equity=round(float(eq.iloc[-1]), 0),
        cagr_pct=round(float(cagr * 100), 2), max_dd_pct=round(float(dd * 100), 2),
        sharpe=round(float(sharpe), 2), sortino=round(float(sortino), 2),
        calmar=round(float(calmar), 2), n_trades_taken=int(len(tdf)),
    )


port = {}
for name, df in trade_frames.items():
    port[name] = portfolio_sim(df)
results["portfolio_sim_full_v4"] = port

RESULTS.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
print(f"\nwrote {RESULTS}")

# ── print concise summary ───────────────────────────────────────────────────
print("\n=== SUMMARY: expectancy %/trade (v4 exit) ===")
print(f"{'strategy':<32}{'nAll':>7}{'TRAIN':>8}{'VAL':>8}{'TEST':>8}{'PF_val':>8}")
for name, res in results["strategies"].items():
    v4 = res["v4_notp"]
    tr = v4["train"]["exp"] if v4["train"] else None
    va = v4["val"]["exp"] if v4["val"] else None
    te = v4["test"]["exp"] if v4["test"] else None
    pf = v4["val"]["pf"] if v4["val"] else None
    print(f"{name:<32}{res['total_trades_all_periods']:>7}"
          f"{_f(tr):>8}{_f(va):>8}{_f(te):>8}{_f(pf):>8}")
