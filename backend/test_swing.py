"""Test ONLY Kite MCP - no Yahoo Finance."""
from kite_client import kite

# 1. Check connection
print("mcp_available:", kite._mcp_available)
ok = kite.check_connection()
print("check_connection:", ok)
print("connected:", kite.connected)
print("user:", kite._user_name, kite._user_id)

if not ok:
    print("\n*** NOT LOGGED IN - cannot test MCP ***")
    exit(1)

# 2. Search instruments
print("\n=== SEARCH ===")
results = kite.search_instruments("RELIANCE", "NSE")
if results and isinstance(results, list):
    eq = [r for r in results if r.get("instrument_type") == "EQ"]
    print(f"Found {len(results)} total, {len(eq)} EQ")
    if eq:
        token = eq[0]["instrument_token"]
        print(f"RELIANCE EQ token: {token}")
    else:
        token = 738561
        print(f"No EQ found, using hardcoded token: {token}")
else:
    token = 738561
    print(f"Search failed: {results}, using hardcoded token: {token}")

# 3. Historical data
print("\n=== HISTORICAL (90 days) ===")
r = kite.get_historical_data(
    instrument_token=token,
    from_date="2026-03-16 00:00:00",
    to_date="2026-06-16 23:59:59",
    interval="day"
)
if isinstance(r, list) and len(r) > 0:
    print(f"SUCCESS: {len(r)} candles")
    print(f"First: {r[0]}")
    print(f"Last:  {r[-1]}")
elif isinstance(r, str):
    print(f"ERROR (string): {r}")
elif isinstance(r, dict):
    candles = r.get("candles", [])
    print(f"Dict with {len(candles)} candles")
    if candles:
        print(f"First: {candles[0]}")
        print(f"Last:  {candles[-1]}")
else:
    print(f"Unexpected: type={type(r).__name__}, val={r}")

# 4. LTP
print("\n=== LTP ===")
ltp = kite.get_ltp(["NSE:RELIANCE"])
print(f"LTP: {ltp}")

# 5. OHLC  
print("\n=== OHLC ===")
ohlc = kite.get_ohlc(["NSE:RELIANCE"])
print(f"OHLC: {ohlc}")
