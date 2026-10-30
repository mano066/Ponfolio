"""Dev launcher: force the repo backend ahead of anything the embedded
Python's ._pth already put on sys.path."""
import os
import runpy
import sys

REPO_BACKEND = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))

sys.path.insert(0, REPO_BACKEND)
os.chdir(REPO_BACKEND)

import market_indices  # noqa: E402

print(f"[dev] market_indices from : {market_indices.__file__}")
print(f"[dev] universe size       : {len(market_indices.INDEX_UNIVERSE)}")

runpy.run_path(os.path.join(REPO_BACKEND, "main.py"), run_name="__main__")
