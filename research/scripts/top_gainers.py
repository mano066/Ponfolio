import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.joinpath("backend")))
import yfinance as yf
import swing_trading

syms = swing_trading.SWING_UNIVERSE
print(f"universe size: {len(syms)}", file=sys.stderr)

data = yf.download(syms, period="5d", group_by="ticker", progress=False, threads=True, auto_adjust=False)

rows = []
for s in syms:
    try:
        df = data[s].dropna()
        if len(df) < 2:
            continue
        prev = float(df["Close"].iloc[-2])
        last = float(df["Close"].iloc[-1])
        if prev <= 0:
            continue
        pct = (last - prev) / prev * 100.0
        rows.append((s, last, prev, pct))
    except Exception:
        continue

rows.sort(key=lambda r: r[3], reverse=True)
print(f"valid quotes: {len(rows)}", file=sys.stderr)
print("SYMBOL,LAST,PREV_CLOSE,CHG_PCT")
for s, last, prev, pct in rows[:10]:
    print(f"{s.replace('.NS','')},{last:.2f},{prev:.2f},{pct:+.2f}")
