"""Data storage and persistence for the pairwise ranking application."""

import csv
import json
from datetime import datetime
from pathlib import Path

from src.models.item import Item
from src.models.vote import Vote
from src.models.settings import Settings


class Storage:
    """
    Handles persistence of items, votes, and settings to disk.

    Items and votes are stored as CSV files for human readability.
    Settings are stored as JSON.

    Attributes:
        data_dir: Path to the directory where data files are stored.
        items_file: Path to the items CSV file.
        votes_file: Path to the votes CSV file.
        settings_file: Path to the settings JSON file.

    Example:
        >>> storage = Storage("./data")
        >>> items = storage.load_items()
        >>> storage.save_item(Item(name="New Item"))
    """

    ITEMS_FILENAME = "items.csv"
    VOTES_FILENAME = "votes.csv"
    SETTINGS_FILENAME = "settings.json"

    ITEMS_FIELDNAMES = ["id", "name", "identifier", "description"]
    VOTES_FIELDNAMES = ["id", "winner_id", "loser_id", "timestamp", "weight"]

    def __init__(self, data_dir: str | Path):
        """
        Initialize storage with a data directory.

        Creates the directory if it doesn't exist.

        Args:
            data_dir: Path to the directory where data files will be stored.
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.items_file = self.data_dir / self.ITEMS_FILENAME
        self.votes_file = self.data_dir / self.VOTES_FILENAME
        self.settings_file = self.data_dir / self.SETTINGS_FILENAME

    def _ensure_items_file(self) -> None:
        """Create items file with header if it doesn't exist."""
        if not self.items_file.exists():
            with open(self.items_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.ITEMS_FIELDNAMES)
                writer.writeheader()

    def _ensure_votes_file(self) -> None:
        """Create votes file with header if it doesn't exist."""
        if not self.votes_file.exists():
            with open(self.votes_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.VOTES_FIELDNAMES)
                writer.writeheader()

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

    def save_items(self, items: list[Item]) -> None:
        """
        Save all items to the CSV file, replacing existing content.

        Args:
            items: List of Item objects to save.
        """
        with open(self.items_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.ITEMS_FIELDNAMES)
            writer.writeheader()
            for item in items:
                writer.writerow({
                    "id": item.id,
                    "name": item.name,
                    "identifier": item.identifier,
                    "description": item.description,
                })

    def save_item(self, item: Item) -> None:
        """
        Append a single item to the CSV file.

        Args:
            item: The Item to append.
        """
        self._ensure_items_file()
        with open(self.items_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.ITEMS_FIELDNAMES)
            writer.writerow({
                "id": item.id,
                "name": item.name,
                "identifier": item.identifier,
                "description": item.description,
            })

    def update_item(self, item: Item) -> bool:
        """
        Update an existing item in the CSV file.

        Args:
            item: The Item with updated values. Matched by ID.

        Returns:
            bool: True if item was found and updated, False otherwise.
        """
        items = self.load_items()
        updated = False
        for i, existing in enumerate(items):
            if existing.id == item.id:
                items[i] = item
                updated = True
                break

        if updated:
            self.save_items(items)
        return updated

    def delete_item(self, item_id: str) -> bool:
        """
        Delete an item from the CSV file by ID.

        Args:
            item_id: The ID of the item to delete.

        Returns:
            bool: True if item was found and deleted, False otherwise.
        """
        items = self.load_items()
        original_count = len(items)
        items = [item for item in items if item.id != item_id]

        if len(items) < original_count:
            self.save_items(items)
            return True
        return False

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

    def save_votes(self, votes: list[Vote]) -> None:
        """
        Save all votes to the CSV file, replacing existing content.

        Args:
            votes: List of Vote objects to save.
        """
        with open(self.votes_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.VOTES_FIELDNAMES)
            writer.writeheader()
            for vote in votes:
                writer.writerow({
                    "id": vote.id,
                    "winner_id": vote.winner_id,
                    "loser_id": vote.loser_id,
                    "timestamp": vote.timestamp.isoformat(),
                    "weight": vote.weight,
                })

    def save_vote(self, vote: Vote) -> None:
        """
        Append a single vote to the CSV file.

        Args:
            vote: The Vote to append.
        """
        self._ensure_votes_file()
        with open(self.votes_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.VOTES_FIELDNAMES)
            writer.writerow({
                "id": vote.id,
                "winner_id": vote.winner_id,
                "loser_id": vote.loser_id,
                "timestamp": vote.timestamp.isoformat(),
                "weight": vote.weight,
            })

    def delete_vote(self, vote_id: str) -> bool:
        """
        Delete a vote from the CSV file by ID.

        Args:
            vote_id: The ID of the vote to delete.

        Returns:
            bool: True if vote was found and deleted, False otherwise.
        """
        votes = self.load_votes()
        original_count = len(votes)
        votes = [vote for vote in votes if vote.id != vote_id]

        if len(votes) < original_count:
            self.save_votes(votes)
            return True
        return False

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

    def save_settings(self, settings: Settings) -> None:
        """
        Save settings to the JSON file.

        Args:
            settings: The Settings object to save.
        """
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, indent=2)

    def clear_all(self) -> None:
        """
        Delete all data files.

        Use with caution - this permanently deletes all items, votes, and settings.
        """
        for file_path in [self.items_file, self.votes_file, self.settings_file]:
            if file_path.exists():
                file_path.unlink()
