---
name: privacy-guard
description: Use when about to commit, push, publish, share, open a PR, create a release, deploy the site, attach a file, or add any file, fixture, screenshot, report or sample data to this public repository - especially anything derived from the running app, backend/data, broker or bank exports, or the owner's portfolio.
---

# Privacy guard

This repository is **public**. The owner's personal and financial data, and any
credential, must never enter git: not in a file, a test fixture, a comment, a
commit message, a branch, or history. A rewrite after the fact does not undo a push.

## What counts as private

| Private (never commit) | Fine to commit |
|---|---|
| Real holdings, quantities, average prices, P&L, dividends, MF units/folios | Synthetic fixtures with made-up symbols and round numbers |
| Expenses, salary, income, bank/card/loan/insurance details | Generic code that reads such data at runtime from `backend/data/` |
| Broker exports: tradebook, P&L, ledger, holdings, contract notes | Parsers for those formats, tested with synthetic sheets |
| Client IDs, account/demat/folio numbers, PAN, phone, email, home address | `mano066` GitHub handle and `users.noreply.github.com` email |
| Personal paths (`C:\Users\<name>\...`), machine names | Paths built from the repo root or env vars |
| API keys, OAuth client secrets, tokens, cookies, certificates, `.env` | `.env.example` with placeholders |
| Studies whose basket mirrors the owner's holdings (e.g. rebalancing S1-S10) | Studies on public indices or broad universes (e.g. Nifty 50 SIP) |
| Raw third-party data (NSE downloads, vendor files, scraped pages) | Download scripts and small derived results |

Personal identifiers to block are listed in `private/denylist.txt` (git-ignored).
Read it before reviewing a diff; never copy its contents anywhere tracked.

## Before every commit

1. `git config core.hooksPath` must print `tools/git-hooks`. If not:
   `git config core.hooksPath tools/git-hooks`.
2. `git status --short` and read every staged path. Anything under `private/`,
   `backend/data/`, `assets/private/`, `dataset/store/`, `test/_real_*`, or any
   spreadsheet/export: unstage it.
3. `git diff --cached` and read the added lines for values from the private column.
4. Let the hook run. **Never use `--no-verify`** to get past it; fix the file instead.
5. New test fixture? It must be synthetic. Do not snapshot the live app
   (`/api/portfolio/*`, deploy-board) into `test/`; `tools/dev/snapshot_live_board.ps1`
   writes to `private/snapshots/` for that reason.

## Before every push, PR, release or site deploy

Push only when the owner asks in this conversation. Then also:
- Scan the whole range being pushed: `git log -p origin/main..HEAD` for private values.
- `site/` is deployed by Netlify; only the marketing page belongs there.
- Release artifacts (installer, `dist/`) are built locally and never committed.

## If private data was already committed

Stop and tell the owner. Do not push. Fixing it needs a history rewrite
(`git filter-repo`) and, if it was ever pushed, rotating any credential. Removing
it in a new commit is not enough.

## Red flags - stop and re-check

- "It's only a test fixture" / "it's only my own data" / "the repo is private for now"
- Copying a JSON response from the running app into `test/` or `docs/`
- A report, chart or screenshot built from the live portfolio
- A hard-coded symbol list that matches the owner's holdings
- Pasting a key "temporarily" into source, or committing to "fix later"
