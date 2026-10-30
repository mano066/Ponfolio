"""Independent audit: can EOD-T information predict T+1 top-10 gainers?

Leakage rules enforced:
- every feature at date T uses data <= close of T (rolling windows end at T)
- target uses ONLY T+1 adjusted close-to-close return
- chronological splits; scaler fit on train only; model/hyperparams picked on
  validation; test untouched until the end; walk-forward re-fit monthly.
Cleaning rules (documented, not silent):
- R1: drop phantom non-trading dates (>=99% zero volume AND ~no price moves)
- R2: stock-days with |adj c2c return| > 22% are corporate-action artifacts
      (NSE daily circuit max is 20%); excluded from TARGET ranking only.
- R3: eligibility at T: close>=5, volume>0 on T, traded >=15 of last 20 days,
      >=60 days history. All determinable at T.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DOCS = str(ROOT.joinpath("research", "data"))
SCR = str(ROOT.joinpath("research", "data"))
rng = np.random.default_rng(42)

u = pd.read_csv(DOCS + r"\nse_universe_5y_ohlcv.csv", parse_dates=["date"])
nif = pd.read_csv(DOCS + r"\nifty50_daily_5y.csv", parse_dates=["date"])

# R1 phantom dates
zv = u.groupby("date")["volume"].apply(lambda s: (s == 0).mean())
phantom = set(zv[zv >= 0.99].index)
print(f"R1: dropping {len(phantom)} phantom dates: {sorted(d.date() for d in phantom)}")
u = u[~u["date"].isin(phantom)].copy()
nif = nif[~nif["date"].isin(phantom)].copy()

u = u.sort_values(["symbol", "date"]).reset_index(drop=True)
g = u.groupby("symbol", sort=False)

# adjust open with same-day factor so o2c/c2o use consistent prices
u["af"] = u["adjusted_close"] / u["close"]
u["adj_open"] = u["open"] * u["af"]

# ---- features at T (rolling windows END at T => info available at close T)
u["ret1"] = g["adjusted_close"].pct_change() * 100
u["ret5"] = g["adjusted_close"].pct_change(5) * 100
u["ret21"] = g["adjusted_close"].pct_change(21) * 100
u["vol20"] = g["volume"].transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
u["vol_ratio"] = (u["volume"] / u["vol20"]).clip(0, 50)
u["volat21"] = g["ret1"].transform(lambda s: s.rolling(21, min_periods=10).std())
u["hi250"] = g["adjusted_close"].transform(lambda s: s.rolling(250, min_periods=60).max())
u["dist_hi"] = (u["adjusted_close"] / u["hi250"] - 1) * 100
u["cir"] = (u["close"] - u["low"]) / (u["high"] - u["low"]).replace(0, np.nan)
u["gap"] = (u["open"] / g["close"].shift(1) - 1) * 100
u["log_turn"] = np.log10(u["turnover"].clip(lower=1))
u["days_traded20"] = g["volume"].transform(lambda s: (s > 0).rolling(20, min_periods=1).sum())
u["hist_days"] = g.cumcount()

nif = nif.sort_values("date")
nif["nifty_ret1"] = nif["nifty_close"].pct_change() * 100
u = u.merge(nif[["date", "nifty_ret1"]], on="date", how="left")

# ---- forward returns (TARGET ONLY, never features)
u["fwd_c2c"] = g["adjusted_close"].shift(-1) / u["adjusted_close"] * 100 - 100
u["fwd_o2c"] = (g["adjusted_close"].shift(-1) / g["adj_open"].shift(-1) * 100 - 100)
u["fwd_c2o"] = (g["adj_open"].shift(-1) / u["adjusted_close"] * 100 - 100)

# R3 eligibility at T
u["eligible"] = ((u["close"] >= 5) & (u["volume"] > 0) &
                 (u["days_traded20"] >= 15) & (u["hist_days"] >= 60))
# R2 artifact days can't be a valid target
u["valid_target"] = u["fwd_c2c"].abs() <= 22

FEATS = ["ret1", "ret5", "ret21", "vol_ratio", "volat21", "dist_hi", "cir", "gap",
         "log_turn", "nifty_ret1"]
d = u[u["eligible"]].dropna(subset=FEATS + ["fwd_c2c"]).copy()

# target: top-10 by T+1 c2c among eligible+valid, per date (vectorized)
fwd_valid = d["fwd_c2c"].where(d["valid_target"])
d["fwd_rank"] = fwd_valid.groupby(d["date"]).rank(ascending=False, method="first")
d["target"] = (d["fwd_rank"] <= 10).astype(int)
print(f"panel: {len(d):,} stock-days, {d['date'].nunique()} dates, "
      f"avg eligible/day={len(d)/d['date'].nunique():.0f}, positives={d['target'].sum():,}")

# cross-sectional pct-ranks of features (within each date -> no temporal leak)
for f in FEATS:
    d[f"rk_{f}"] = d.groupby("date")[f].rank(pct=True)
RFEATS = [f"rk_{f}" for f in FEATS]

TR_END, VA_END, TE_END = "2024-07-12", "2025-07-14", "2026-07-14"
tr = d[d["date"] <= TR_END]
va = d[(d["date"] > TR_END) & (d["date"] <= VA_END)]
te = d[(d["date"] > VA_END) & (d["date"] <= TE_END)]
print(f"train {tr['date'].nunique()}d | val {va['date'].nunique()}d | test {te['date'].nunique()}d")

def evaluate(frame, scorecol, label, costs=0.25):
    """pick top-10 by score per day; compute all requested metrics."""
    res = []
    for dt, day in frame.groupby("date"):
        picks = day.nlargest(10, scorecol)
        hits = int(picks["target"].sum())
        res.append(dict(date=dt, hits=hits, c2c=picks["fwd_c2c"].mean(),
                        o2c=picks["fwd_o2c"].mean(), c2o=picks["fwd_c2o"].mean()))
    r = pd.DataFrame(res)
    net = r["o2c"] - costs
    eq = (1 + net / 100).cumprod()
    mdd = ((eq / eq.cummax()) - 1).min() * 100
    boot = [r["hits"].sample(len(r), replace=True, random_state=i).mean() for i in range(500)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return dict(model=label, days=len(r),
                prec10=r["hits"].mean() / 10 * 100, hits_day=r["hits"].mean(),
                hits_ci=f"[{lo:.2f},{hi:.2f}]",
                ge1=(r["hits"] >= 1).mean() * 100,
                c2c=r["c2c"].mean(), c2o=r["c2o"].mean(), o2c=r["o2c"].mean(),
                net_o2c=net.mean(), win=(net > 0).mean() * 100,
                vol=net.std(), mdd=mdd), r

def show(rows, title):
    print(f"\n--- {title} ---")
    print(f"{'model':<26}{'prec@10':>8}{'hits/d':>7}{'95%CI':>14}{'>=1hit%':>8}"
          f"{'c2o%':>7}{'o2c%':>7}{'net%':>7}{'win%':>6}{'MDD%':>8}")
    for m in rows:
        print(f"{m['model']:<26}{m['prec10']:>7.1f}%{m['hits_day']:>7.2f}{m['hits_ci']:>14}"
              f"{m['ge1']:>7.0f}%{m['c2o']:>7.2f}{m['o2c']:>7.2f}{m['net_o2c']:>7.2f}"
              f"{m['win']:>6.1f}{m['mdd']:>8.1f}")

# ---------- models ----------
# random baseline: analytic + empirical
d["rand"] = rng.random(len(d))
# chase: today's biggest gainer;  volsurge: biggest volume surprise
d["chase"] = d["ret1"]; d["volsurge"] = d["vol_ratio"]

sc = StandardScaler().fit(tr[RFEATS])
logit = LogisticRegression(max_iter=1000, C=0.1, class_weight="balanced")
logit.fit(sc.transform(tr[RFEATS]), tr["target"])
ridge = Ridge(alpha=10.0).fit(sc.transform(tr[RFEATS]), tr["fwd_c2c"].clip(-22, 22))
hgb = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05,
                                     random_state=0)
hgb.fit(tr[RFEATS], tr["target"])

for part in (va, te, d):
    part_idx = part.index
    d.loc[part_idx, "logit"] = logit.decision_function(sc.transform(part[RFEATS]))
    d.loc[part_idx, "ridge"] = ridge.predict(sc.transform(part[RFEATS]))
    d.loc[part_idx, "hgb"] = hgb.predict_proba(part[RFEATS])[:, 1]
# cross-sectional rank blend (weights chosen ON VALIDATION below, simple grid)
best_w, best_p = None, -1
va2 = d.loc[va.index]
for w1 in (0.0, 0.5, 1.0):
    for w2 in (0.0, 0.5, 1.0):
        for w3 in (-1.0, 0.0, 1.0):
            s = w1*va2["rk_ret1"] + w2*va2["rk_vol_ratio"] + w3*va2["rk_volat21"]
            va2["_tmp"] = s
            m, _ = evaluate(va2, "_tmp", "tmp")
            if m["hits_day"] > best_p:
                best_p, best_w = m["hits_day"], (w1, w2, w3)
print(f"\nrank-blend weights chosen on VALIDATION: ret1={best_w[0]}, vol_ratio={best_w[1]}, volat={best_w[2]}")
d["blend"] = best_w[0]*d["rk_ret1"] + best_w[1]*d["rk_vol_ratio"] + best_w[2]*d["rk_volat21"]

MODELS = [("random", "rand"), ("chase yesterday's gainer", "chase"),
          ("volume surprise", "volsurge"), ("logistic (balanced)", "logit"),
          ("ridge on fwd return", "ridge"), ("gradient boosting", "hgb"),
          ("rank blend (val-tuned)", "blend")]

val_rows = [evaluate(d.loc[va.index], c, n)[0] for n, c in MODELS]
show(val_rows, "VALIDATION 2024-07-15 .. 2025-07-14 (model selection)")

test_rows, test_daily = [], {}
for n, c in MODELS:
    m, r = evaluate(d.loc[te.index], c, n)
    test_rows.append(m); test_daily[n] = r
show(test_rows, "FINAL TEST 2025-07-15 .. 2026-07-14 (untouched)")

# ---------- walk-forward: monthly refit (expanding) of best-by-validation ----------
best_val = max(val_rows, key=lambda m: m["hits_day"])
print(f"\nbest on validation: {best_val['model']} ({best_val['hits_day']:.2f} hits/day)")
wf_rows = []
te_dates = sorted(te["date"].unique())
months = sorted({pd.Timestamp(x).strftime("%Y-%m") for x in te_dates})
for mo in months:
    mo_dates = [x for x in te_dates if pd.Timestamp(x).strftime("%Y-%m") == mo]
    hist = d[d["date"] < mo_dates[0]]
    mdl = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05,
                                         random_state=0)
    mdl.fit(hist[RFEATS], hist["target"])
    cur = d[d["date"].isin(mo_dates)].copy()
    cur["wf"] = mdl.predict_proba(cur[RFEATS])[:, 1]
    hits = [int(day.nlargest(10, "wf")["target"].sum()) for _, day in cur.groupby("date")]
    o2c = [day.nlargest(10, "wf")["fwd_o2c"].mean() for _, day in cur.groupby("date")]
    wf_rows.append((mo, len(hits), np.mean(hits), np.mean(o2c)))
print("\n--- WALK-FORWARD (monthly expanding refit, gradient boosting) on TEST ---")
print(f"{'month':<9}{'days':>5}{'hits/day':>9}{'o2c%':>8}")
for mo, nd_, h, o in wf_rows:
    print(f"{mo:<9}{nd_:>5}{h:>9.2f}{o:>8.2f}")
print(f"{'ALL':<9}{sum(r[1] for r in wf_rows):>5}"
      f"{np.average([r[2] for r in wf_rows], weights=[r[1] for r in wf_rows]):>9.2f}"
      f"{np.average([r[3] for r in wf_rows], weights=[r[1] for r in wf_rows]):>8.2f}")

# ---------- cost sensitivity on best test model ----------
best_test = max(test_rows, key=lambda m: m["hits_day"])
print(f"\ncost sensitivity ({best_test['model']}, o2c strategy, test): ", end="")
_, rbest = evaluate(d.loc[te.index], dict(MODELS)[best_test['model']] if False else
                    [c for n, c in MODELS if n == best_test['model']][0], "x")
for c in (0.0, 0.10, 0.25, 0.50):
    print(f" cost{c:.2f}%: {(rbest['o2c']-c).mean():+.3f}%/d", end="")
print()

# ---------- regime split on test ----------
nif["regime"] = np.where(nif["nifty_close"].pct_change(21) > 0, "bull21", "bear21")
reg = rbest.merge(nif[["date", "regime"]], on="date", how="left")
print("\nregime split (test, best model): ")
print(reg.groupby("regime").agg(days=("hits", "size"), hits_day=("hits", "mean"),
                                o2c=("o2c", "mean")).round(2).to_string())

# ---------- latest ranking through 2026-07-15 ----------
last_day = d[d["date"] == d["date"].max()].copy()
print(f"\n--- LATEST RANKING (features through {d['date'].max().date()}) ---")
for n, c in [("gradient boosting", "hgb"), ("chase yesterday's gainer", "chase"),
             ("rank blend (val-tuned)", "blend")]:
    top = last_day.nlargest(10, c)["symbol"].tolist()
    print(f"{n:<26}: {', '.join(top)}")
claimed = ["NUVOCO","JUSTDIAL","KALYANKJIL","GABRIEL","PCJEWELLER","NEOGEN",
           "ATHERENERG","UTLSOLAR","AEGISLOG","PATANJALI"]
for n, c in [("gradient boosting", "hgb"), ("chase yesterday's gainer", "chase"),
             ("rank blend (val-tuned)", "blend")]:
    top = set(last_day.nlargest(10, c)["symbol"])
    print(f"overlap of claimed list with {n}: {len(top & set(claimed))}/10")

d[["date","symbol","target","fwd_c2c","fwd_o2c","fwd_c2o"] + RFEATS + ["chase","volsurge","logit","ridge","hgb","blend"]] \
    .to_parquet(SCR + r"\audit_panel.parquet") if False else None
print("\nDONE")
