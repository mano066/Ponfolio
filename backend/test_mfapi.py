import requests
try:
    r = requests.get("https://api.mfapi.in/mf/search", params={"q": "nifty 50 index direct growth"}, timeout=10)
    print(f"Status: {r.status_code}, Count: {len(r.json())}")
    for x in r.json()[:5]:
        print(f"  {x['schemeCode']}: {x['schemeName'][:70]}")
except Exception as e:
    print(f"ERROR: {e}")
