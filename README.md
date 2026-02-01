# Pairwise Ranking

A PyQt6 GUI application for ranking items using pairwise comparisons with a Bradley-Terry model.

## Features

- Add items with names and descriptions
- Perform pairwise comparisons with a 7-point preference scale
- Intelligent pair selection balancing uncertainty, connectivity, freshness, and uncompared items
- Rankings displayed with ELO-converted scores
- Configurable algorithm parameters including vote decay and top-tier focus mode
- Data persistence via human-readable CSV and JSON files

## Installation

Requires Python 3.10+ and Poetry.

```bash
# Clone the repository
git clone <repo-url>
cd pairwise_ranking

# Install dependencies
poetry install

# Run the application
poetry run python main.py
```

## Usage

### Items Tab
Add items you want to rank. Each item has a name and optional description.

### Compare Tab
The app presents pairs of items. Click a button to indicate your preference:
- **A Much Better** (weight 3.0)
- **A Better** (weight 2.0)
- **A Slightly Better** (weight 1.0)
- **Equal** (skip - no vote recorded)
- **B Slightly Better** (weight 1.0)
- **B Better** (weight 2.0)
- **B Much Better** (weight 3.0)

Keyboard shortcuts: 1-7 for buttons, S to skip.

### Rankings Tab
View the current ranking with ELO scores. Expand items to see details like win/loss records.

### Settings Tab
Configure algorithm parameters:
- **Pair selection weights**: Control how pairs are chosen for comparison
- **Vote decay**: Old votes can decay over time
- **Top-tier mode**: Focus comparisons on top-ranked items

## Data Storage

Data is stored in the `data/` directory:
- `items.csv` - Item names and descriptions
- `votes.csv` - Comparison results with timestamps
- `settings.json` - Algorithm settings

## Running Tests

```bash
poetry run python -m unittest discover tests
```

## Algorithm

Uses a Bradley-Terry model with MM algorithm for parameter estimation:
- Each item has a latent strength parameter
- Regularization via pseudo-counts ensures connected comparisons
- Scores converted to ELO scale (centered at 1500, 200 points = 1 std dev)
