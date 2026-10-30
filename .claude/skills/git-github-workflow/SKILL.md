---
name: git-github-workflow
description: Use when creating a branch, committing, writing a commit message, bumping the app version, merging, tagging a release, opening or reviewing a pull request, using gh, or when unsure whether to push in this repository.
---

# Git and GitHub workflow

Public repo `mano066/ponfolio`, default branch `main`. Run the
`privacy-guard` checks before anything below that commits or publishes.

## Rules

| Action | Rule |
|---|---|
| Push / force-push | Only when the owner asks in this conversation. Never force-push `main` unless they explicitly ask for that exact operation. |
| Commit | Only when asked. Never on `main` directly: branch first. Never `--no-verify`. |
| Identity | `user.email` = `mano066@users.noreply.github.com` (check `git config user.email`). |
| History | Never rewrite pushed history except a deliberate privacy cleanup the owner approved. |

## Branches

`<type>/<short-kebab-topic>`, types: `feat`, `fix`, `chore`, `docs`, `research`,
`refactor`, `test`. Examples: `feat/mf-sip-planner`, `research/smart-sip`,
`fix/kite-session-refresh`. One topic per branch.

## Commit messages

```
<Imperative summary, max ~70 chars> (vX.Y.Z when the app version changes)

Why the change was needed, then what changed, wrapped at ~72 columns.
Mention verification run (tests, rebuilds) when relevant.

Co-Authored-By: <assistant attribution line, if the session supplies one>
```

Match the existing log style (`git log --oneline -10`): sentence-case imperative,
version in parentheses for app releases, e.g. `Stop a broken yfinance cache from
freezing login (v1.7.0)`.

## App version

The version lives in `pubspec.yaml` (`version:`) and `installer.iss`
(`MyAppVersion`). Bump both together, semver: patch = fix, minor = feature,
major = breaking data change. Research-only or docs-only commits do not bump it.

## Pull requests

- Title = the commit summary style. Body: Summary (what and why), How verified,
  Screenshots only if they contain no personal data, then the PR attribution
  line if the session supplies one.
- `gh pr create --base main --head <branch>`; check `gh pr checks` before merge.
- Prefer squash-merge for single-topic branches.

## Before you finish

- `git status` clean or intentionally dirty, and say which.
- Report the branch, commits made, and that nothing was pushed (or what was).
