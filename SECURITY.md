# Security and privacy

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting
(**Security → Report a vulnerability**) on this repository.

## What must never be committed

This repository is public. The pre-commit hook in `tools/git-hooks/` enforces
these rules; enable it with `git config core.hooksPath tools/git-hooks`.

- **Credentials:** API keys and secrets (Kite Connect, Google OAuth), tokens,
  cookies, `.env` files, certificates and private keys. Use `backend/.env`
  (from `.env.example`) and `backend/google_oauth.json`, both git-ignored.
- **Personal data:** holdings, quantities, prices paid, P&L, expenses, bank or
  broker statements and exports, account/client/folio numbers, names, emails,
  phone numbers, addresses, personal file paths.
- **Runtime data:** everything under `backend/data/` (sessions, settings, user
  folders) and anything captured from a running app.
- **Third-party raw data:** NSE or vendor downloads and scraped pages. Commit
  the download script and small derived results instead.

Test fixtures must be synthetic. Personal files belong in the git-ignored
`private/` folder; personal app pages in `assets/private/`.

## If something private was committed

Do not push. Rotate any exposed credential first, then remove the data from
history (`git filter-repo`). A follow-up commit that deletes the file is not
enough, because the old commit still contains it.
