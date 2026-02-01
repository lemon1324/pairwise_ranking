# Pairwise Ranking Project

## Environment

- **Package manager**: Poetry (local venv via `poetry.toml`)
- **Python version**: 3.12+

## Commands

```bash
# Install dependencies
poetry install

# Run application
poetry run python main.py

# Run tests
poetry run python -m unittest discover tests/ -v
```

## Testing

- **Framework**: unittest (standard library)
- **Test location**: `tests/`
- **Run all tests**: `poetry run python -m unittest discover tests/ -v`

## Architecture

- `src/models/` - Data models (Item, Vote, Settings, RankingResult, BradleyTerryModel, PairSelector)
- `src/ui/` - PyQt6 UI components
- `main.py` - Application entry point
