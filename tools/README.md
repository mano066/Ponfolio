# Tools

## git-hooks/

`pre-commit` blocks credentials, broker exports, personal paths and the
identifiers listed in the git-ignored `private/denylist.txt`. Enable once per
clone:

```powershell
git config core.hooksPath tools/git-hooks
```

## dev/

Developer helpers. Each builds its paths from its own location, so run it from
anywhere. Anything they capture from the running app is written to `private/`.

| Script | Purpose |
|---|---|
| `run_backend_dev.py` | Start the repo's backend ahead of an installed copy |
| `verify_index_tape.py` | Rebuild the market index tape and audit each index |
| `check_index_tape.ps1`, `index_tape_coverage.ps1` | Inspect `/api/market/indices` from the running backend |
| `snapshot_live_board.ps1` | Save live deploy-board and tape responses to `private/snapshots/` |
| `stage_installed_data.ps1` | Copy the installed app's data into `backend/data/` (backed up first) |
| `import_kite_exports.py` | Import your Kite tradebook, P&L and ledger exports into the running app |
| `capture_dashboard.ps1` | Screenshot the app window (keep screenshots out of git) |
