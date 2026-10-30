# Ponfolio

*Pon* (பொன், Tamil for gold) + port*folio*.

A local-first desktop terminal for Indian markets: portfolio analytics with
Zerodha Kite sync, swing-trade signals, mutual fund analysis, SIP and
rebalancing tools, and a research library. A Flutter (Windows) front end talks
to a Python (FastAPI) backend that runs on the same machine; your data stays on
your computer.

> Source available, all rights reserved. See [LICENSE](LICENSE).

## Repository layout

| Path | What it is |
|---|---|
| [`lib/`](lib), [`test/`](test), [`windows/`](windows), [`assets/`](assets) | Flutter desktop app |
| [`backend/`](backend) | Python API server (`main.py`) and its tests (`test_*.py`) |
| [`dataset/`](dataset) | NSE daily/intraday data pipeline (downloaded data is not committed) |
| [`research/`](research) | Market studies: write-ups, `scripts/`, small result files |
| [`docs/`](docs) | Documentation and finished research reports (`docs/reports/`) |
| [`site/`](site) | Public product page, deployed by Netlify |
| [`tools/`](tools) | Developer helpers and git hooks |
| `installer.iss` | Inno Setup script for the Windows installer |

## Getting started

Requirements: Windows 10/11, Flutter SDK (Dart ^3.11), Python 3.12.

```powershell
# 1. Backend
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # add your own Kite Connect API key and secret
python main.py                  # serves http://127.0.0.1:8182

# 2. App (new terminal, repo root)
flutter pub get
flutter run -d windows
```

Optional: Google sign-in and Drive backup need your own OAuth client. Put it in
`backend/google_oauth.json` as `{"client_id": "...", "client_secret": "..."}`
(git-ignored) or set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.

## Tests

```powershell
flutter test                                   # app
cd backend; python -m unittest discover -p "test_*.py"   # backend
```

## Building the installer

`flutter build windows --release`, then compile `installer.iss` with Inno Setup
(it expects an embedded Python in `installer/python-embed/`). Build outputs are
not committed.

## Contributing and privacy

This repository is public. Before your first commit:

```powershell
git config core.hooksPath tools/git-hooks
```

The hook blocks credentials, broker exports and personal data. Read
[SECURITY.md](SECURITY.md) for what must never be committed.

## Disclaimer

Research results and signals in this project are backtests on past data. They
are not investment advice, and past returns do not predict future returns.
