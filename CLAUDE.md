# Pairwise Ranking Project

## Environment

- **Package manager**: Poetry (local venv via `poetry.toml`)
- **Python version**: 3.10+ (developed on 3.11)

## Commands

```bash
# Install dependencies
poetry install

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

## Architecture

- `src/models/` - Data models (Item, Vote, Settings, RankingResult, BradleyTerryModel, PairSelector)
- `src/data/` - Persistence (project storage, user config, legacy CSV loader, format migrations)
- `src/ui/` - PyQt6 UI components
- `main.py` - Application entry point
