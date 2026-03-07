"""User configuration management for the pairwise ranking application."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class UserConfig:
    """
    Manages user-level configuration including recent projects list.

    Configuration is stored in ~/.pairwise_ranking/config.json.

    Attributes:
        config_dir: Path to the configuration directory.
        config_file: Path to the configuration JSON file.

    Example:
        >>> config = UserConfig()
        >>> recent = config.get_recent_projects()
        >>> config.add_recent_project("My Project", Path("/path/to/project.pairrank"))
    """

    MAX_RECENT_PROJECTS = 10
    CONFIG_DIR_NAME = ".pairwise_ranking"
    CONFIG_FILENAME = "config.json"
    DEFAULT_PROJECTS_SUBDIR = "PairwiseRanking"

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize user configuration.

        Creates the configuration directory if it doesn't exist.

        Args:
            config_dir: Custom config directory. Defaults to ~/.pairwise_ranking
        """
        if config_dir is None:
            self.config_dir = Path.home() / self.CONFIG_DIR_NAME
        else:
            self.config_dir = config_dir

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / self.CONFIG_FILENAME

    def _load_config(self) -> dict:
        """Load configuration from file or return defaults."""
        if not self.config_file.exists():
            return {
                "recent_projects": [],
                "default_projects_dir": None,
            }

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {
                "recent_projects": [],
                "default_projects_dir": None,
            }

    def _save_config(self, config: dict) -> None:
        """Save configuration to file."""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def get_recent_projects(self) -> list[dict]:
        """
        Get list of recent projects.

        Returns:
            list[dict]: List of dicts with 'name', 'path', and 'modified' keys.
                       Ordered by most recent first.
        """
        config = self._load_config()
        recent = config.get("recent_projects", [])

        # Filter out projects whose files no longer exist
        valid_recent = []
        for project in recent:
            path = Path(project.get("path", ""))
            if path.exists():
                valid_recent.append(project)

        # Update config if we removed any invalid entries
        if len(valid_recent) != len(recent):
            config["recent_projects"] = valid_recent
            self._save_config(config)

        return valid_recent

    def add_recent_project(
        self,
        name: str,
        file_path: Path,
        modified: Optional[datetime] = None,
    ) -> None:
        """
        Add or update a project in the recent projects list.

        If the project already exists (by path), it's moved to the top.
        The list is limited to MAX_RECENT_PROJECTS entries.

        Args:
            name: Display name of the project.
            file_path: Path to the .pairrank file.
            modified: Last modified timestamp. Defaults to now.
        """
        if modified is None:
            modified = datetime.now()

        config = self._load_config()
        recent = config.get("recent_projects", [])

        path_str = str(file_path.resolve())

        # Remove existing entry with same path
        recent = [p for p in recent if p.get("path") != path_str]

        # Add new entry at the beginning
        recent.insert(0, {
            "name": name,
            "path": path_str,
            "modified": modified.isoformat(),
        })

        # Limit to max entries
        recent = recent[:self.MAX_RECENT_PROJECTS]

        config["recent_projects"] = recent
        self._save_config(config)

    def remove_recent_project(self, file_path: Path) -> bool:
        """
        Remove a project from the recent projects list.

        Args:
            file_path: Path to the .pairrank file to remove.

        Returns:
            bool: True if project was found and removed, False otherwise.
        """
        config = self._load_config()
        recent = config.get("recent_projects", [])

        path_str = str(file_path.resolve())
        original_count = len(recent)

        recent = [p for p in recent if p.get("path") != path_str]

        if len(recent) < original_count:
            config["recent_projects"] = recent
            self._save_config(config)
            return True

        return False

    def get_default_projects_dir(self) -> Path:
        """
        Get the default directory for new projects.

        Returns:
            Path: Default projects directory. Falls back to ~/Documents/PairwiseRanking
                  or ~/PairwiseRanking if Documents doesn't exist.
        """
        config = self._load_config()
        custom_dir = config.get("default_projects_dir")

        if custom_dir:
            return Path(custom_dir)

        # Try Documents folder first
        documents = Path.home() / "Documents"
        if documents.exists():
            return documents / self.DEFAULT_PROJECTS_SUBDIR

        # Fallback to home directory
        return Path.home() / self.DEFAULT_PROJECTS_SUBDIR

    def set_default_projects_dir(self, path: Path) -> None:
        """
        Set the default directory for new projects.

        Args:
            path: Directory path to use as default.
        """
        config = self._load_config()
        config["default_projects_dir"] = str(path.resolve())
        self._save_config(config)
