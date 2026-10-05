# Pairwise Ranking Project

## Environment

- **Package manager**: Poetry 2.x (local venv via `poetry.toml`)
- **Python version**: 3.10+ (developed on 3.11)

## Commands

```bash
# Install dependencies (all groups: desktop, web, dev)
poetry sync

# Run application
poetry run python main.py

# Run tests (Poetry)
poetry run python -m unittest discover tests/ -v

# Run tests (from WSL, using the Windows venv directly)
./.venv/Scripts/python.exe -m unittest discover tests/
```

## Testing

- **Framework**: unittest (standard library)
- **Test location**: `tests/`
- **Run all tests**: `poetry run python -m unittest discover tests/ -v`
  (or from WSL: `./.venv/Scripts/python.exe -m unittest discover tests/`)

## Docker, CI and publishing

- WSL has no `docker`; run Docker commands through Windows, e.g. `cmd.exe /c docker compose up --build`.
- CI (`.github/workflows/ci.yml`) runs the tests and builds and smoke-tests the image on every push
  and pull request, with a read-only token. A separate `publish` job, the only one with
  `packages: write`, rebuilds the image from the `image` job's cache and pushes it to GHCR, and it
  runs only on a push to `main` when the `PUBLISH_IMAGE` repo variable is `true`.
  `tests/test_deploy_files.py` checks those guards.
- `origin` is HTTPS and WSL has no credential helper, so push over SSH:
  `git push git@github.com:lemon1324/pairwise_ranking.git <branch>`.
- Bump `[project].version` in `pyproject.toml` when merging to `main`: CI pushes `:<version>` only
  when that tag doesn't exist yet (otherwise it warns and skips it), so an unbumped merge publishes
  no new version tag. `:latest` only moves when the commit is still `main`'s head.

## Subagents

Choose an agent in this order: a specialised agent when one fits (the `impeccable-*` agents for
Impeccable design builds and finish reviews), then a built-in agent (`Explore`, `Plan`), then the
project agents in `.claude/agents/`:

- `implementer` (Opus, medium effort): implements one plan phase on its feature branch and commits.
- `reviewer` (Opus, xhigh effort, read-only): correctness review of a branch or diff against its spec.

When launching built-in agents, set their model explicitly: `sonnet` for `Explore` and other
search or investigation work, `opus` for everything else. Project agents set their own model and
effort level; don't override them.

## Scratch files

Agents never create, modify or delete anything outside this repository directory. WSL-only scratch
goes in the Claude Code scratchpad directory. Anything the Windows venv or Windows Chrome must read,
such as seeded capture data, throwaway CDP scripts or browser profiles, goes in `.scratch/` at the
repo root. That folder is excluded through `.git/info/exclude`, and Windows programs cannot see
WSL's `/tmp`.

## Architecture

- `src/models/` - Data models (Item, Vote, Settings, RankingResult, BradleyTerryModel, PairSelector)
- `src/data/` - Persistence (project storage, user config, legacy CSV loader, format migrations)
- `src/ui/` - PyQt6 UI components
- `main.py` - Application entry point
