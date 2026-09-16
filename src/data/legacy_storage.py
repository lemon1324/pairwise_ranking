"""Read-only loader for the legacy CSV/JSON storage format.

The application now stores everything in a single ``.pairrank`` project file.
This module exists only so :mod:`src.data.migration` can read data written by
older versions; it deliberately provides no write operations.
"""

import csv
import json
from pathlib import Path

from src.models.item import Item
from src.models.vote import Vote
from src.models.settings import Settings


class LegacyCsvStorage:
    """
    Reads items, votes, and settings from the legacy on-disk format.

    Items and votes were stored as CSV files, settings as JSON. This loader is
    read-only and has no side effects: it never creates the data directory or
    any of the files.

    Attributes:
        data_dir: Path to the directory holding the legacy data files.
        items_file: Path to the items CSV file.
        votes_file: Path to the votes CSV file.
        settings_file: Path to the settings JSON file.

    Example:
        >>> storage = LegacyCsvStorage("./data")
        >>> items = storage.load_items()
    """

    ITEMS_FILENAME = "items.csv"
    VOTES_FILENAME = "votes.csv"
    SETTINGS_FILENAME = "settings.json"

    ITEMS_FIELDNAMES = ["id", "name", "identifier", "description"]
    VOTES_FIELDNAMES = ["id", "winner_id", "loser_id", "timestamp", "weight"]

    def __init__(self, data_dir: str | Path):
        """
        Initialize the loader with a data directory.

        The directory is not created and is not required to exist; missing
        files simply yield empty results or defaults.

        Args:
            data_dir: Path to the directory holding the legacy data files.
        """
        self.data_dir = Path(data_dir)

        self.items_file = self.data_dir / self.ITEMS_FILENAME
        self.votes_file = self.data_dir / self.VOTES_FILENAME
        self.settings_file = self.data_dir / self.SETTINGS_FILENAME

    def load_items(self) -> list[Item]:
        """
        Load all items from the CSV file.

        Returns:
            list[Item]: List of Item objects. Empty list if file doesn't exist.
        """
        if not self.items_file.exists():
            return []

        items = []
        with open(self.items_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    items.append(Item.from_dict(row))
                except (KeyError, ValueError) as e:
                    # Skip invalid rows but continue loading
                    print(f"Warning: Skipping invalid item row: {e}")
        return items

    def load_votes(self) -> list[Vote]:
        """
        Load all votes from the CSV file.

        Returns:
            list[Vote]: List of Vote objects. Empty list if file doesn't exist.
        """
        if not self.votes_file.exists():
            return []

        votes = []
        with open(self.votes_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    vote_data = {
                        "id": row["id"],
                        "winner_id": row["winner_id"],
                        "loser_id": row["loser_id"],
                        "weight": row["weight"],
                        "timestamp": row["timestamp"],
                    }
                    votes.append(Vote.from_dict(vote_data))
                except (KeyError, ValueError) as e:
                    # Skip invalid rows but continue loading
                    print(f"Warning: Skipping invalid vote row: {e}")
        return votes

    def load_settings(self) -> Settings:
        """
        Load settings from the JSON file.

        Returns:
            Settings: Settings object. Returns default settings if file doesn't exist.
        """
        if not self.settings_file.exists():
            return Settings()

        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Settings.from_dict(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Error loading settings, using defaults: {e}")
            return Settings()
