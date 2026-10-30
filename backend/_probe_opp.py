import sys, os, warnings, json
warnings.filterwarnings("ignore")
from pathlib import Path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE)); os.chdir(_HERE)
import main
b = main.get_opportunities(with_news=False)
m = b["market"]
print("MARKET: %s %s" % (m["label"].upper(), m["summary"]))
print("status=%s  buys=%d  risks=%d" % (b["status"], b["buy_count"], b["risk_count"]))
if b["headline"]: print("  >> %s — %s" % (b["headline"], b["detail"]))
print()
for r in b["rows"]:
    print("  %-6s %-34s score=%-5s %-18s %s" % (
        r["label"], (r["name"] or "")[:32], r["score"],
        r["metric"] or "", (r["why"] or "")[:60]))
print()
print("=== fund scores ===")
for f in main.get_fund_dips()["funds"]:
    print("  %-42s %-14s score=%-5s %-22s %s" % (
        f["scheme_name"][:40], f["category"], f["score"],
        f["action_label"], (f["reasons"] or [""])[0][:44]))
