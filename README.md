# Pairwise Ranking

[![CI](https://github.com/lemon1324/pairwise_ranking/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/lemon1324/pairwise_ranking/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/lemon1324/pairwise_ranking/badges/tests.json)](https://github.com/lemon1324/pairwise_ranking/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A desktop application (PyQt6) for putting a set of items in order when comparing two of them side
by side is easy but assigning each one an absolute score is hard. You answer a stream of "which of
these two is better?" questions; the app fits a Bradley-Terry model to your answers and turns the
result into a ranked list with ELO-style ratings and an uncertainty estimate for each item. It is
domain-neutral: typical uses are ranking keyswitches mounted on a tester board, ordering the
samples in a tasting flight, or working a shortlist of candidates down to a decision.

A web version of the same app works on the same `.pairrank` files, and runs either locally or as
a container on a home server (see [Running the web app](#running-the-web-app) and
[Deploying to Unraid](#deploying-to-unraid)).

## Features

- Projects saved as a single human-readable `.pairrank` JSON file, with a recent-projects list.
- Items with a name, description, free-text category, and an identifier for the physical slot or
  storage location the item occupies.
- Optional per-project **slot list**: when defined, identifiers are picked from the slots that are
  still free, and the Items tab shows slot usage.
- **Item lifecycle**: retire an item (its votes and rating are kept, its slot is freed, it is never
  offered for comparison again), replace it with a successor that inherits its slot, or reactivate
  it later.
- Seven-point preference scale with keyboard shortcuts, a skip option, and undo of the last vote.
- Pair selection that balances estimation uncertainty, graph connectivity, vote freshness and
  uncompared items, with an optional top-tier focus mode.
- Categories with a configurable cross-category comparison rate, so ratings stay comparable across
  categories.
- Blinded comparison mode that hides names and descriptions and shows only identifiers.
- Rankings with ELO ratings, per-item standard errors, weighted win/loss detail, category filter,
  and CSV export.
- Atomic saves with automatic backups and a versioned, one-time file-format migration.

## Installation

Requires Python 3.10+ and [Poetry](https://python-poetry.org/) 2.x.

```bash
git clone <repo-url>
cd pairwise_ranking
poetry sync
```

## Running

```bash
poetry run python main.py
```

On startup a project picker appears: create a **New Project**, **Open Project...** an existing
`.pairrank` file, or pick one from the recent projects table (double-click, or select and press
**Open Selected**). Cancelling exits the application.

There is no Save command. Every change — a vote, an item edit, a settings change — is written to
the project file immediately.

## Usage

### Items tab

The table lists Name, Category, Identifier, Status and Description. Active items with no identifier
are highlighted; retired items are greyed out and hidden unless **Show retired** is ticked.

Toolbar actions, all operating on the selected row:

| Button | Effect |
| --- | --- |
| **Add Item** | Create an item. Name is required; category, identifier and description optional. |
| **Edit** | Change the selected item. |
| **Retire** | Keep the item's votes and rating but stop comparing it, and free its identifier. |
| **Replace...** | Retire the selected item and add a new one prefilled with its identifier and category. Titled "Replace \<name\>"; cancelling changes nothing. |
| **Reactivate** | Return a retired item to the active pool, assigning it a new identifier. |
| **Delete** | Remove the item *and every vote involving it*. Use Retire to keep history. |

Identifiers must be unique among active items; the dialog refuses a duplicate. If the project
defines slots, the identifier field is an editable dropdown of the free slots and a line under the
toolbar reads `Slots: 40 of 42 in use — free: X, Y` (or `none free`).

### Compare tab

Two items are shown side by side with seven preference buttons:

| Key | Button | Weight |
| --- | --- | --- |
| 1 | A Much Better | 3.0 |
| 2 | A Better | 2.0 |
| 3 | A Slightly Better | 1.0 |
| 4 | Equal | no vote recorded — skips to the next pair |
| 5 | B Slightly Better | 1.0 |
| 6 | B Better | 2.0 |
| 7 | B Much Better | 3.0 |

Keyboard: `1`-`7` for the buttons, `S` to skip (same as Equal), `Ctrl+Z` to undo. The **Undo last
vote** button below the buttons does the same; undo removes the most recent vote and, if both its
items are still eligible, offers that pair again so you can re-answer. Repeated undo keeps popping
votes. A status line shows how many pairs have been compared and the total vote count.

In blinded comparison mode the cards show only each item's identifier, and items without an
identifier are excluded from comparison.

### Rankings tab

A tree of Rank, Name, Category, ELO Rating and Comparisons. Expanding a row shows Description,
Strength, Log-Strength, Uncertainty (SE), and the weighted wins and losses against each opponent.

- **Category** filter restricts the list to one category; the dropdown is built from what is
  currently visible.
- **Show retired** includes retired items. They keep their rating but have a blank rank and are
  suffixed " (retired)"; ranks number the active items 1..N.
- The summary line counts the active items shown and how many retired ones are shown or hidden.
- **Export** writes a CSV of exactly what the filters currently show, with the columns:
  `Rank, Name, Category, Identifier, Status, ELO Rating, Uncertainty (SE), Comparisons,
  Description`. Rank is blank for retired items.

### Settings tab

Grouped as:

- **Pair Selection Weights** — Uncertainty, Connectivity, Freshness, Uncompared.
- **Vote Decay** — decay half-life in days; `0` disables decay.
- **Top-Tier Focus Mode** — enable, top-tier count, top-tier weight.
- **Category Comparisons** — cross-category rate, the fraction of comparisons allowed to cross
  category boundaries (`0.0` = never, `1.0` = ignore categories).
- **Comparison Mode** — the blinded comparison mode checkbox.
- **Slots** — the project's slot list, one slot per line or comma separated.

**Save Settings** applies both the algorithm settings and the slot list. **Reset to Defaults**
restores the algorithm settings only and deliberately leaves the slot list alone.

### Menus

**File**: New Project... (`Ctrl+N`), Open Project... (`Ctrl+O`), Recent Projects submenu, Save
As... (`Ctrl+Shift+S`), Exit (`Ctrl+Q`).

**Edit**: Undo Last Vote (`Ctrl+Z`), enabled only when the project has at least one vote.

## Projects and files

A project is one `.pairrank` file — JSON, indented, safe to read and diff. Format version 2 looks
like this (settings abbreviated):

```json
{
  "format_version": 2,
  "name": "My Rankings",
  "created": "2026-01-04T10:15:00",
  "modified": "2026-02-11T21:03:12",
  "items": [
    {"id": "…", "name": "Sample A", "description": "", "identifier": "6",
     "category": "Default", "status": "active", "retired_at": null, "replaced_by": null}
  ],
  "votes": [
    {"id": "…", "winner_id": "…", "loser_id": "…", "weight": 2.0,
     "timestamp": "2026-02-11T20:58:41"}
  ],
  "settings": {"weight_uncertainty": 1.0, "decay_timescale_days": 30.0,
               "cross_category_rate": 0.1},
  "slots": ["1", "2", "3"]
}
```

A retired item has `"identifier": ""`, `"status": "retired"`, an ISO `retired_at`, and
`replaced_by` set to its successor's id when it was retired through Replace.

**Backups.** Saves are atomic: the new contents go to a `.tmp` file in the same directory, are
flushed to disk, and are then moved over the target. Before the move, any existing project file is
copied to `<name>.pairrank.bak`, so the previous version is always one file away. A failed save
leaves the original untouched.

**Format migration.** Files written before versioning (no `format_version` key) are version 1. The
first time one is opened it is upgraded in memory, the original bytes are copied once to
`<name>.pairrank.v1.bak`, and the upgraded project is written back — so the migration happens once
and the original is preserved. Opening a file that is already current writes nothing. A file from a
newer format version is refused with an explanatory error rather than being loaded.

**Legacy CSV migration.** If a `data/` folder next to `main.py` contains the old `items.csv`,
`votes.csv` or `settings.json` and no `.pairrank` file, it is converted to
`data/project.pairrank` at startup (as "Migrated Project") and added to the recent projects list.
The legacy format is read-only; nothing is ever written back to it.

**User configuration** lives in `~/.pairwise_ranking/config.json` and holds the recent projects
list (most recent first, up to ten, with missing files pruned) and an optional default projects
directory. Without one, new projects default to `~/Documents/PairwiseRanking`, or
`~/PairwiseRanking` if there is no `Documents` folder.

## Running the web app

The web app serves every `.pairrank` file in one data folder. It addresses projects by file name
within that folder, never by path.

```bash
PAIRRANK_DATA_DIR=~/Documents/PairwiseRanking poetry run python web_main.py
```

Then open http://localhost:8080. Set `PAIRRANK_DATA_DIR` when running outside a container: the
default, `/data`, is the container's mount point.

The web process is configured entirely through environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `PAIRRANK_DATA_DIR` | `/data` | The folder holding the `.pairrank` projects. |
| `PAIRRANK_PORT` | `8080` | The port the server listens on (all interfaces). Must be 1–65535. |
| `PAIRRANK_ROOT_PATH` | empty | The subpath a reverse proxy serves the app under, e.g. `/pairrank`. Leading and trailing slashes are optional. Leave unset when served at the root. |
| `PAIRRANK_SECRET_KEY` | random per start | The key signing the session cookie. Unset, a key is generated at each start and a warning is logged; sessions then don't survive a restart. |
| `PAIRRANK_AUTH_MODE` | `none` | How users are identified. `none` is the only mode implemented; any other value stops the server at startup. |
| `PAIRRANK_LOG_LEVEL` | `INFO` | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG` or `TRACE`, in any case (`WARN` and `FATAL` are accepted too). An unknown level logs a warning and falls back to `INFO`. |

A value that can't be used (a bad port, an unsupported auth mode) makes the server print
`Cannot start: ...` and exit with status 2.

The server runs as a single process on purpose: projects are locked in memory, so two processes on
one data folder would write the same files without them. Never add uvicorn workers.

### Local Docker stack

`docker-compose.yml` at the repo root builds the image from the checkout, for testing on Docker
Desktop:

```bash
docker compose up --build
```

The app is at http://localhost:8080 and its data folder is `./.scratch/docker-data`. The container
runs in `America/Denver` unless `TZ` is set in the shell; vote timestamps are stored as local time,
so match the zone the desktop app runs in.

## Deploying to Unraid

> **Warning: the web app has no authentication.** Anyone who can reach it can read and change every
> project in its data folder. Run it on your LAN only, and do not expose it to the internet without
> an authenticating proxy in front of it.

GitHub Actions publishes the image to `ghcr.io/lemon1324/pairwise_ranking` from `main`, tagged
`:latest`, `:<version>` (from `pyproject.toml`) and `:sha-<commit>`. The image is public, so the
Unraid host needs no registry token. `deploy/docker-compose.yml` is the deployment stack: it pulls
the image rather than building, so the host never needs the source tree.

### 1. Share folder

Create a folder on a share for the projects, for example `/mnt/user/documents/pairwise-ranking`,
and export the share over SMB (*Shares → documents → SMB Security Settings*) so the desktop app
can reach it. The desktop app then opens the same files over SMB, e.g.
`\\tower\documents\pairwise-ranking\<name>.pairrank`.

The web app checks each project file before every change and reloads it if the desktop app saved
it in the meantime. The desktop app does not watch the file, so don't keep a project open in it
while voting on the web.

### 2. Bring the stack up

With the Compose Manager plugin (Community Applications): add a stack, paste
`deploy/docker-compose.yml`, and edit the values marked `# EDIT`: the share path on the left of
`:/data` and the host port. Then compose up, or from the console:

```bash
docker compose pull
docker compose up -d
docker compose logs -f
```

Open `http://<unraid-ip>:8080` (or the host port you chose).

The stack's other settings:

| Variable | Stack value | Meaning |
| --- | --- | --- |
| `PUID` / `PGID` | `99` / `100` | The user and group the app runs as: Unraid's `nobody:users`. With neither set the container stays root and saves root-owned files. |
| `UMASK` | `000` | Files the app writes stay writable by everyone, so SMB users can save over them from the desktop app. |
| `TZ` | `America/Denver` | Votes and modified times are stored as local time and shared with the desktop app; set the zone the desktop runs in. |

The entrypoint never changes ownership of the share. If the folder isn't writable by `PUID:PGID`,
it refuses to start and logs `Cannot start: the data folder /data is not writable by uid:gid ...`;
fix the folder's permissions (or set `PUID` and `PGID` to its owner) and start it again.

`PAIRRANK_SECRET_KEY` and `PAIRRANK_ROOT_PATH` are in the stack, commented out; see
[Running the web app](#running-the-web-app) for what they do.

**Run exactly one container per project folder.** Project locks live in the app's one process, so
a second container (or extra uvicorn workers) on the same folder would write the same files
without them.

### 3. Update and roll back

To update: `docker compose pull && docker compose up -d` (or *Update Stack* in Compose Manager).

To roll back, change the stack's image from `:latest` to an earlier tag and bring it up again:
`ghcr.io/lemon1324/pairwise_ranking:sha-<full commit hash>` for a specific build, or `:<version>` for a
release. Every push to `main` gets a `sha-` tag; a version tag is new only when the version in
`pyproject.toml` was bumped.

### 4. Optional: Nginx Proxy Manager

To reach the app through Nginx Proxy Manager under a subpath, e.g.
`https://example.com/pairrank`, set `PAIRRANK_ROOT_PATH: /pairrank` in the stack, and have the
proxy forward that location to `http://<unraid-ip>:8080` with the prefix stripped. The app puts
the prefix back on every link it generates. Served at its own hostname instead, leave
`PAIRRANK_ROOT_PATH` unset.

A proxy does not add authentication by itself. If the proxy is reachable from the internet, put
an authenticating layer in front of the app as well.

## Algorithm

Each item *i* has a latent strength π<sub>i</sub>, and `P(i beats j) = π_i / (π_i + π_j)`. The
strengths are fitted with the MM (minorization-maximization) algorithm, iterating a simultaneous
update until the largest log-strength change falls below 1e-10. Vote weights (1.0 / 2.0 / 3.0) are
the observation counts, optionally reduced by exponential decay with the configured half-life.

- **Regularization.** A pseudo-count of 0.01 is added to every off-diagonal pair, so a sparse or
  disconnected comparison graph still yields a finite, unique fit.
- **ELO ratings.** Log-strengths are converted to a z-score and mapped to `1500 + 200·z`. This is a
  *relative* scale computed over the items currently in the model, so adding, retiring or deleting
  items shifts everyone's rating even when no new votes were cast. Compare ratings within one
  snapshot, not across snapshots.
- **Uncertainty.** The Fisher information matrix for the log-strengths weights each pair by
  `p_ij·(1 - p_ij)`; its pseudo-inverse (the matrix is rank *n*-1 because of the normalization
  constraint) gives the per-item standard error shown as "Uncertainty (SE)".
- **Pair selection.** Every candidate pair is scored and the best one is offered:
  *uncertainty* (sum of the two standard errors), *connectivity* (a large bonus for a pair that
  would join two disconnected components of the comparison graph), *freshness* (age of the pair's
  last vote, relative to the decay timescale), *uncompared* (a decaying bonus for items with few
  comparisons, plus a bonus for a pair never compared directly), and *top-tier* (when enabled, a
  bonus for pairs involving top-ranked items or plausible risers).
- **Categories.** Before scoring, a draw against the cross-category rate decides whether this
  comparison should cross category boundaries; candidates are filtered accordingly, falling back to
  all pairs when the filter would leave nothing (for example when only one category exists).
  Cross-category votes are what keeps ratings comparable between categories.
- **Retired items** stay in the fit — their votes still inform everyone else's strength — but are
  never offered for comparison and carry no rank.

## Running tests

```bash
poetry run python -m unittest discover tests/ -v
```

From WSL against a Windows virtualenv, where Poetry is not on the path:

```bash
./.venv/Scripts/python.exe -m unittest discover tests/
```
