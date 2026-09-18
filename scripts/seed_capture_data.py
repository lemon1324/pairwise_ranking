#!/usr/bin/env python
"""Fill a data directory with the projects the review captures are taken of.

``scripts/capture_web.py`` photographs the running application; this decides
what it is photographing. The register draws one row per ``.pairrank`` file and
tags the files it cannot open, so a capture directory is only as good as the
conditions it holds. This writes all of them:

* enough healthy projects to fold into columns at 1920 and to run onto
  continuation sheets at every review width,
* one project in format 1, which the register tags **Old format**,
* one stamped with a format version newer than this application knows, tagged
  **Newer format**,
* one that is not JSON at all, tagged **Unreadable**, with the reason on it,
* one whose top level is a perfectly good project but whose *item entries* are
  malformed - the register tags it **OK**, because the probe is deliberately
  shallow, and opening it lands on the damaged page,
* a name long enough to need its ellipsis, one carrying punctuation the file
  name has to sanitise, and one with no votes,
* a ``notes.txt``, to show that the listing is not simply the directory.

It also writes an empty sibling directory, because the picker's empty state is
a state of the screen like any other and cannot be photographed from a
directory with projects in it.

Usage (from WSL, with the Windows venv - the capture script explains why)::

    ./.venv/Scripts/python.exe scripts/seed_capture_data.py ../capture-data

The directory is emptied of ``.pairrank`` files first, so re-running it after a
capture pass has created, imported or duplicated something puts the register
back where it started. The empty directory is written as ``<path>-empty``.

Nothing here is imported by the application, and the files it writes are
invented: names, figures and timestamps are all made up.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_web import windows_path  # noqa: E402
from src.models.project import CURRENT_FORMAT_VERSION  # noqa: E402


PROGRAM = "seed_capture_data.py"

# Healthy projects: (name, file stem, items, votes, modified date/time).
# Thirty-odd, because two columns of a 1920 sheet hold about that many and the
# capture has to show a continuation sheet, not just a fold.
HEALTHY = (
    ("Linear switches, winter shortlist", "switches-2026", 64, 203, "2026-09-16T21:04:00"),
    ("Espresso, September roasts", "espresso-sept", 12, 88, "2026-09-14T08:12:00"),
    ("Tactile shortlist", "tactile", 22, 131, "2026-09-02T19:40:00"),
    ("Pour-over grinders", "grinders", 7, 21, "2026-08-19T10:02:00"),
    ("Whisky flight, November", "whisky-flight", 9, 36, "2025-11-23T22:31:00"),
    ("Keycap profiles", "keycaps", 18, 74, "2026-09-11T14:20:00"),
    ("Desk lamps", "desk-lamps", 11, 44, "2026-09-09T09:15:00"),
    ("Office chairs, second pass", "chairs-2", 15, 90, "2026-09-08T16:50:00"),
    ("Monitor arms", "monitor-arms", 8, 25, "2026-09-07T11:35:00"),
    ("Mechanical pencils", "pencils", 24, 158, "2026-09-06T08:05:00"),
    ("Notebook paper weights", "paper", 13, 52, "2026-09-05T18:22:00"),
    ("Travel mugs", "mugs", 10, 30, "2026-09-04T12:44:00"),
    ("Hiking boots", "boots", 16, 101, "2026-09-03T07:30:00"),
    ("Camping stoves", "stoves", 12, 61, "2026-09-01T20:10:00"),
    ("Rain shells", "shells", 9, 27, "2026-08-30T15:05:00"),
    ("Sleeping bags", "sleeping-bags", 14, 83, "2026-08-28T13:48:00"),
    ("Headphones, over-ear", "headphones", 21, 142, "2026-08-26T19:02:00"),
    ("Bookshelf speakers", "speakers", 17, 96, "2026-08-24T10:29:00"),
    ("Kitchen knives", "knives", 19, 118, "2026-08-22T09:41:00"),
    ("Cast iron pans", "pans", 6, 15, "2026-08-20T17:58:00"),
    ("Olive oils", "olive-oils", 11, 38, "2026-08-18T11:12:00"),
    ("Breakfast cereals, blind", "cereals", 20, 129, "2026-08-16T08:33:00"),
    ("Board games for four", "board-games", 26, 187, "2026-08-14T21:19:00"),
    ("Film cameras", "cameras", 13, 67, "2026-08-12T14:07:00"),
    ("Bicycle saddles", "saddles", 10, 41, "2026-08-10T18:26:00"),
    ("Running shoes, autumn", "running-shoes", 15, 88, "2026-08-08T06:55:00"),
    ("Tea, first flush", "tea-first-flush", 12, 55, "2026-08-06T16:14:00"),
    ("Houseplants for a north window", "houseplants", 23, 165, "2026-08-04T12:01:00"),
    ("Paint colours, hallway", "paint-hallway", 8, 22, "2026-08-02T10:37:00"),
    (
        "Standing desk frames, shortlisted after the showroom visit",
        "standing-desks",
        14,
        79,
        "2026-07-31T15:44:00",
    ),
    ("Cost #1, packaging", "Cost _1, packaging", 7, 19, "2026-07-29T09:08:00"),
    ("Backlog, not started", "backlog", 5, 0, "2026-07-27T08:00:00"),
)

# The project in format 1: no format_version key, no slots, no slot labels.
OLD_FORMAT = ("Migrated Project", "project", 18, 240, "2026-01-04T10:15:00")

# The project stamped with a version this application has never heard of.
NEWER_FORMAT = ("Keyboard cases", "cases", 9, 48, "2026-09-10T17:45:00")

# What the unreadable file holds: valid UTF-8, invalid JSON, and the truncation
# is far enough in that the parser's message names a line worth reading.
UNREADABLE_TEXT = (
    '{\n  "format_version": 3,\n  "name": "Half-written notes",\n'
    '  "items": [\n    {"id": "item-1", "name": "One"},\n'
    '    {"id": "item-2", "name": "Tw\n'
)

# A file the register tags OK and Open cannot open: the top level is right, so
# the shallow probe passes it, but an item entry has no name. This is the case
# the damaged page exists for.
DEEP_BROKEN = ("Shed inventory", "shed", "2026-07-25T19:30:00")

# Filler beyond the curated list, for the widths where the curated projects do
# not reach a second sheet. A 1920 sheet folds into three columns and holds
# something over fifty rows, so the continuation sheet - and with it the pager,
# the SHEET n OF N cell and the rightmost column sitting under the title
# block - is only visible with a directory that large. The names are dull on
# purpose: they are there to be counted, not read.
FILLER_SUBJECTS = (
    "Adhesives", "Bearings", "Bolts", "Brackets", "Cables", "Casters",
    "Clamps", "Connectors", "Dowels", "Fasteners", "Gaskets", "Grommets",
    "Hinges", "Latches", "Nozzles", "O-rings", "Pulleys", "Rivets",
    "Seals", "Shims", "Springs", "Studs", "Washers", "Bushings",
    "Couplings", "Ferrules", "Gears", "Inserts", "Keys", "Levers",
    "Magnets", "Pins",
)

NOT_A_PROJECT = "notes.txt"

NOT_A_PROJECT_TEXT = (
    "Files that are not .pairrank are not listed on the register.\n"
)


def items_for(count: int) -> list:
    """
    Build a list of item entries.

    Args:
        count: How many items to build.

    Returns:
        list: Item dictionaries in the current format.
    """
    return [
        {
            "id": f"item-{n}",
            "name": f"Candidate {n}",
            "description": "",
            "identifier": str(n),
            "category": "General",
            "status": "active",
        }
        for n in range(1, count + 1)
    ]


def votes_for(count: int) -> list:
    """
    Build a list of vote entries, all between the first two items.

    Args:
        count: How many votes to build.

    Returns:
        list: Vote dictionaries in the current format.
    """
    return [
        {
            "id": f"vote-{n}",
            "winner_id": "item-1",
            "loser_id": "item-2",
            "weight": 2.0,
            "timestamp": "2026-06-01T10:00:00",
        }
        for n in range(1, count + 1)
    ]


def project_data(name: str, items: int, votes: int, modified: str) -> dict:
    """
    Build a healthy project in the current format.

    Args:
        name: The project's name, as the register draws it.
        items: How many items it holds.
        votes: How many votes it holds.
        modified: The stored modification timestamp, ISO 8601. The register
            draws this rather than the file's mtime, by owner decision.

    Returns:
        dict: The project, ready to be written as JSON.
    """
    return {
        "format_version": CURRENT_FORMAT_VERSION,
        "name": name,
        "created": "2026-01-01T09:00:00",
        "modified": modified,
        "items": items_for(items),
        "votes": votes_for(votes),
        "settings": {},
        "slots": [],
        "slot_labels": {},
    }


def write(directory: Path, stem: str, data) -> Path:
    """
    Write one project file.

    Args:
        directory: Where to write it.
        stem: The file name without its extension.
        data: The project dictionary.

    Returns:
        Path: The file written.
    """
    path = directory / f"{stem}.pairrank"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def seed(directory: Path, filler: int = len(FILLER_SUBJECTS)) -> int:
    """
    Fill a directory with every condition the register can draw.

    Existing ``.pairrank`` files and backups are removed first, so a second run
    after a capture pass has created or imported something starts level.

    Args:
        directory: The data directory to fill.
        filler: How many dull extra projects to add after the curated ones, to
            push a 1920 sheet onto a continuation. Capped at the number of
            filler subjects there are names for.

    Returns:
        int: How many project files were written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if path.is_file() and (
            path.suffix == ".pairrank" or ".pairrank." in path.name
        ):
            path.unlink()

    written = 0
    for name, stem, items, votes, modified in HEALTHY:
        write(directory, stem, project_data(name, items, votes, modified))
        written += 1

    for n, subject in enumerate(FILLER_SUBJECTS[: max(0, filler)]):
        write(
            directory,
            f"parts-{subject.lower()}",
            project_data(
                f"{subject}, sourcing",
                6 + n % 17,
                3 * n + 7,
                f"2026-0{1 + n % 6}-{10 + n % 18:02d}T{8 + n % 9:02d}:{n % 60:02d}:00",
            ),
        )
        written += 1

    name, stem, items, votes, modified = OLD_FORMAT
    old = project_data(name, items, votes, modified)
    del old["format_version"]
    del old["slots"]
    del old["slot_labels"]
    for entry in old["items"]:
        del entry["status"]
    write(directory, stem, old)
    written += 1

    name, stem, items, votes, modified = NEWER_FORMAT
    newer = project_data(name, items, votes, modified)
    newer["format_version"] = CURRENT_FORMAT_VERSION + 1
    write(directory, stem, newer)
    written += 1

    (directory / "half-written.pairrank").write_text(
        UNREADABLE_TEXT, encoding="utf-8"
    )
    written += 1

    name, stem, modified = DEEP_BROKEN
    broken = project_data(name, 4, 6, modified)
    # Top level still right, so the register's probe passes it; the entry is
    # not, so building the project fails and Open lands on the damaged page.
    broken["items"][2] = {"id": "item-3", "identifier": "3"}
    write(directory, stem, broken)
    written += 1

    (directory / NOT_A_PROJECT).write_text(NOT_A_PROJECT_TEXT, encoding="utf-8")
    return written


def is_seeded(path: Path) -> bool:
    """
    Say whether a file is one this script wrote.

    Args:
        path: The file to judge.

    Returns:
        bool: True for a project file or a migration backup, which is
        everything :func:`seed` ever puts in a directory.
    """
    return path.is_file() and (
        path.suffix == ".pairrank"
        or ".pairrank." in path.name
        or path.name == NOT_A_PROJECT
    )


def refuse_to_empty(empty: Path, directory: Path) -> str:
    """
    Say why a directory must not be removed and rebuilt, if it must not be.

    ``--empty-dir`` names a directory this script deletes outright, so it is a
    path a mistyped command line turns into an ``rm -rf``: ``--empty-dir``
    pointed at a checkout removes the checkout. Nothing about the name says
    what it is for, so the directory itself has to.

    Args:
        empty: The directory that would be removed.
        directory: The data directory being seeded.

    Returns:
        str: The reason, or an empty string when it is safe to remove.
    """
    if empty == directory or empty in directory.parents:
        return f"{empty} holds the data directory being seeded"
    if empty.parent == empty:
        return f"{empty} is the root of a filesystem"
    if not empty.exists():
        return ""
    if not empty.is_dir():
        return f"{empty} is not a directory"
    strays = sorted(
        path.name for path in empty.iterdir() if not is_seeded(path)
    )
    if strays:
        return (
            f"{empty} holds {len(strays)} file(s) this script did not write, "
            f"starting with {strays[0]!r}"
        )
    return ""


def main(argv: list) -> int:
    """
    Seed a capture data directory and an empty one beside it.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        int: The process exit status.
    """
    parser = argparse.ArgumentParser(
        prog=PROGRAM, description="Fill a data directory for the review captures."
    )
    parser.add_argument("directory", help="the data directory to fill")
    parser.add_argument(
        "--filler",
        type=int,
        default=len(FILLER_SUBJECTS),
        help=(
            "how many dull extra projects to add, for the continuation sheet "
            f"at 1920 (default: {len(FILLER_SUBJECTS)}, 0 for none)"
        ),
    )
    parser.add_argument(
        "--empty-dir",
        default=None,
        help="where to put the empty directory (default: <directory>-empty)",
    )
    args = parser.parse_args(argv)

    # The arguments arrive in WSL's form and this runs as a Windows process,
    # which is the same crossing capture_web.py makes; the translation is
    # borrowed from it rather than written twice.
    directory = Path(windows_path(args.directory)).resolve()

    empty = (
        Path(windows_path(args.empty_dir)).resolve()
        if args.empty_dir
        else directory.parent / f"{directory.name}-empty"
    )
    # Checked before anything is written, so a refusal costs nothing and leaves
    # nothing half-seeded behind it.
    refusal = refuse_to_empty(empty, directory)
    if refusal:
        print(f"{PROGRAM}: refusing to remove {empty}: {refusal}", file=sys.stderr)
        return 1

    written = seed(directory, args.filler)
    if empty.exists():
        shutil.rmtree(empty)
    empty.mkdir(parents=True)

    print(f"{written} project files in {directory}")
    print(f"empty directory at {empty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
