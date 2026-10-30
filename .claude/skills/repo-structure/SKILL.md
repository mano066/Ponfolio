---
name: repo-structure
description: Use when adding, moving, renaming or deleting files or folders, deciding where a new script, report, dataset, test, asset or tool goes, or when the repo root starts collecting stray files in this repository.
---

# Repository structure

| Path | Holds | Committed? |
|---|---|---|
| `lib/`, `test/`, `windows/`, `assets/`, `pubspec.yaml` | Flutter desktop app (root layout required by Flutter) | yes |
| `assets/private/` | Personal pages the owner's build bundles (portfolio, expenses) | only its `README.md` |
| `backend/` | Python API server (`main.py` + modules), tests `backend/test_*.py` | yes |
| `backend/data/` | Runtime user data, sessions, settings | **never** |
| `dataset/` | NSE data pipeline code | yes, except `dataset/store/` |
| `research/` | Studies: `*.md` write-ups, `scripts/`, notebooks | yes |
| `research/data/` | Small derived results (json/csv); raw downloads ignored | small results only |
| `docs/` | Project docs; `docs/reports/<study>/` finished PDFs + CSVs | public studies only |
| `site/` | Public marketing page, deployed by Netlify | yes |
| `tools/dev/` | Developer helper scripts (run from anywhere, paths from repo root) | yes |
| `tools/git-hooks/` | Repo hooks; enable with `git config core.hooksPath tools/git-hooks` | yes |
| `private/` | Owner's personal files, snapshots, denylist, private reports | **never** |
| `installer.iss`, `installer/`, `build/`, `dist/` | Windows packaging; outputs ignored | script only |

## Rules

- **Nothing new at the repo root** except project-wide config (README, LICENSE,
  SECURITY.md, CLAUDE.md, pubspec, netlify, installer.iss). Scratch output goes
  to `private/scratch/`; helper scripts to `tools/dev/`.
- **No absolute paths.** Build paths from the file's location
  (`Path(__file__).resolve().parents[n]`, `$PSScriptRoot`) or env vars.
- **Names:** Python `snake_case.py`; Dart `snake_case.dart`; PowerShell
  `verb_noun.ps1`; reports `Title_Case_With_Years.pdf`; folders `kebab-case`
  under `docs/reports/`, `snake_case` elsewhere to match existing code.
- **Tests sit next to their code**: `backend/test_<module>.py`, `test/<feature>_test.dart`,
  with synthetic fixtures only (see `privacy-guard`).
- **Generated outputs** (PDF, CSV, PNG, XLSX) are rebuilt by a script whose docstring
  names its `Out:` path. Commit the script; commit outputs only for public studies.
- Moving a file: `git mv`, then grep for its old path (`git grep -n "<old name>"`)
  and fix every reference, including `installer.iss`, `pubspec.yaml`, docstrings.

## Adding a new study

`research/scripts/<study>_*.py` → results in `research/data/<study>/` →
report in `docs/reports/<study>/` (see `research-report`) → one line in
`docs/README.md`.
