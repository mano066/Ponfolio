"""Dev launcher: serve the REPO backend, not the installed one.

main.py ends with uvicorn.run("main:app"), which re-imports "main" by name.
Under the installed embedded Python, ._pth already lists the installed backend
folder, so that re-import resolves there and silently serves the old code.
Importing the module ourselves with the repo path first, then handing uvicorn
the app OBJECT, removes the name lookup entirely.
"""
import sys
from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_BACKEND))

import main  # noqa: E402
import market_indices  # noqa: E402
import uvicorn  # noqa: E402

print(f"[dev] main       -> {main.__file__}")
print(f"[dev] indices    -> {market_indices.__file__}")
print(f"[dev] universe   -> {len(market_indices.INDEX_UNIVERSE)} symbols")
print(f"[dev] data dir   -> {main.DATA_DIR}")

uvicorn.run(main.app, host="127.0.0.1", port=8182, log_level="info")
