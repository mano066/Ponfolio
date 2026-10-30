import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import yfinance as yf
import swing_trading as st

tickers = ["NUVOCO.NS","GABRIEL.NS","AEGISLOG.NS","ATHERENERG.NS","TIMETECHNO.NS",
           "LTTS.NS","GROWW.NS","INOXINDIA.NS","NEOGEN.NS"]

data = yf.download(tickers, period="1y", group_by="ticker", progress=False, threads=True, auto_adjust=False)

print(f"{'SYMBOL':<12}{'SCORE':>6}{'RSI':>7}{'STOCH':>7}{'BB_POS':>8}{'TREND':>9}  SETUP  | passes(>=55)?")
print("-"*95)
for t in tickers:
    df = data[t].dropna()
    r = st._analyze_arrays(t, df["Open"].values, df["High"].values, df["Low"].values,
                           df["Close"].values, df["Volume"].values)
    if not r:
        print(f"{t:<12}  <no result>")
        continue
    print(f"{r['name']:<12}{r['score']:>6}{r['rsi']:>7.1f}{r['stoch_rsi']:>7.1f}"
          f"{r['bb_position']:>8}{r['trend']:>9}  {r['setup'][:22]:<22} | {'YES' if r['score']>=55 else 'no'}")
