"""Item 10: recompute latest ranking with features through 2026-07-15.
Model trained only on data < 2026-07-15 (walk-forward, no leakage)."""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DOCS = str(ROOT.joinpath("research", "data"))
u = pd.read_csv(DOCS + r"\nse_universe_5y_ohlcv.csv", parse_dates=["date"])
nif = pd.read_csv(DOCS + r"\nifty50_daily_5y.csv", parse_dates=["date"])

zv = u.groupby("date")["volume"].apply(lambda s: (s == 0).mean())
u = u[~u["date"].isin(set(zv[zv >= 0.99].index))].copy()
u = u.sort_values(["symbol", "date"]).reset_index(drop=True)
g = u.groupby("symbol", sort=False)

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
u["fwd_c2c"] = g["adjusted_close"].shift(-1) / u["adjusted_close"] * 100 - 100
u["eligible"] = ((u["close"] >= 5) & (u["volume"] > 0) &
                 (u["days_traded20"] >= 15) & (u["hist_days"] >= 60))
u["valid_target"] = u["fwd_c2c"].abs() <= 22

FEATS = ["ret1", "ret5", "ret21", "vol_ratio", "volat21", "dist_hi", "cir", "gap",
         "log_turn", "nifty_ret1"]
d = u[u["eligible"]].dropna(subset=FEATS).copy()
for f in FEATS:
    d[f"rk_{f}"] = d.groupby("date")[f].rank(pct=True)
RFEATS = [f"rk_{f}" for f in FEATS]

LAST = d["date"].max()
train = d[(d["date"] < LAST) & d["fwd_c2c"].notna()].copy()
fwd_valid = train["fwd_c2c"].where(train["valid_target"])
train["fwd_rank"] = fwd_valid.groupby(train["date"]).rank(ascending=False, method="first")
train["target"] = (train["fwd_rank"] <= 10).astype(int)

mdl = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05, random_state=0)
mdl.fit(train[RFEATS], train["target"])
last = d[d["date"] == LAST].copy()
last["score"] = mdl.predict_proba(last[RFEATS])[:, 1]
print(f"latest signal date: {LAST.date()}  (predicting for next session)")
top = last.nlargest(15, "score")[["symbol", "score", "ret1", "vol_ratio"]]
print(top.to_string(index=False))
claimed = ["NUVOCO","JUSTDIAL","KALYANKJIL","GABRIEL","PCJEWELLER","NEOGEN",
           "ATHERENERG","UTLSOLAR","AEGISLOG","PATANJALI"]
mine = set(last.nlargest(10, "score")["symbol"])
print(f"\noverlap with claimed candidate list: {len(mine & set(claimed))}/10 -> {sorted(mine & set(claimed))}")
chase = set(last.nlargest(10, "ret1")["symbol"])
print(f"overlap of claimed list with pure chase(ret1) on 07-15: {len(chase & set(claimed))}/10 -> {sorted(chase & set(claimed))}")
