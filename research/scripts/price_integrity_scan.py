"""Flag implausible single-day moves in the local daily store.

A large-cap close that moves more than the threshold in one session is almost
always an unadjusted corporate action or a bad bar, not a market move.
"""

import argparse
import pathlib

import pandas as pd

PRICE_DIR = pathlib.Path("dataset/store/daily")


def scan(symbols, start, threshold_pct):
    for s in symbols:
        p = PRICE_DIR / (s + ".parquet")
        df = pd.read_parquet(p, columns=["ts", "close"])
        df["ts"] = pd.to_datetime(df["ts"]).dt.normalize()
        df = df[df["ts"] >= start].sort_values("ts").reset_index(drop=True)
        df["chg"] = df["close"].pct_change() * 100.0
        bad = df[df["chg"].abs() >= threshold_pct]
        print(f"--- {s}: {len(bad)} moves >= {threshold_pct}% since {start}")
        for _, r in bad.iterrows():
            i = r.name
            prev = df.loc[i - 1] if i > 0 else None
            print(f"    {r['ts'].date()}  {prev['close']:.2f} -> {r['close']:.2f}"
                  f"  ({r['chg']:+.1f}%)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BHEL,COALINDIA,IOC,ITC,KTKBANK,"
                                         "ONGC,SCI,NTPC,TATASTEEL,SOUTHBANK")
    ap.add_argument("--start", default="2011-01-01")
    ap.add_argument("--threshold", type=float, default=25.0)
    a = ap.parse_args()
    scan([s.strip() for s in a.symbols.split(",")], a.start, a.threshold)
