"""Migration utilities for converting old storage format to new project format."""

from datetime import datetime
from pathlib import Path

from src.data.storage import Storage
from src.data.project_storage import ProjectStorage
from src.models.project import Project


class StorageMigration:
    """
    Handles migration from the old CSV/JSON storage format to .pairrank files.

    The old format stored data in separate files:
    - items.csv
    - votes.csv
    - settings.json

    The new format consolidates everything into a single .pairrank JSON file.

    Example:
        >>> if StorageMigration.needs_migration(Path("./data")):
        ...     project = StorageMigration.migrate(Path("./data"))
        ...     print(f"Migrated to {project.file_path}")
    """

    OLD_FILES = ["items.csv", "votes.csv", "settings.json"]
    DEFAULT_PROJECT_NAME = "Migrated Project"
    DEFAULT_OUTPUT_FILENAME = "project.pairrank"

    @staticmethod
    def needs_migration(data_dir: Path) -> bool:
        """
        Check if a directory contains old format data that needs migration.

        Migration is needed if the directory contains any of the old format files
        (items.csv, votes.csv, settings.json) but does not already contain a
        .pairrank file.

        Args:
            data_dir: Directory to check.

        Returns:
            bool: True if migration is needed, False otherwise.
        """
        if not data_dir.exists():
            return False

        # Check if any old format files exist
        has_old_files = any(
            (data_dir / filename).exists()
            for filename in StorageMigration.OLD_FILES
        )

        if not has_old_files:
            return False

        # Check if a .pairrank file already exists
        pairrank_files = list(data_dir.glob(f"*{ProjectStorage.FILE_EXTENSION}"))
        if pairrank_files:
            return False

        return True

    @staticmethod
    def migrate(
        data_dir: Path,
        project_name: str = DEFAULT_PROJECT_NAME,
        output_filename: str = DEFAULT_OUTPUT_FILENAME,
    ) -> Project:
        """
        Migrate old storage format to a new .pairrank project file.

        Reads items, votes, and settings from the old CSV/JSON files and
        creates a new .pairrank file in the same directory.

        Args:
            data_dir: Directory containing old format files.
            project_name: Name for the migrated project.
            output_filename: Filename for the output .pairrank file.

        Returns:
            Project: The migrated project with file_path set.

        Raises:
            FileNotFoundError: If data_dir doesn't exist.
            ValueError: If no old format data is found.
        """
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")

        # Load data using the old Storage class
        storage = Storage(data_dir)
        items = storage.load_items()
        votes = storage.load_votes()
        settings = storage.load_settings()

        # Determine creation time from oldest vote timestamp, or use now
        if votes:
            oldest_vote = min(votes, key=lambda v: v.timestamp)
            created = oldest_vote.timestamp
        else:
            created = datetime.now()

        # Create the project
        output_path = data_dir / output_filename
        project = Project(
            name=project_name,
            created=created,
            modified=datetime.now(),
            items=items,
            votes=votes,
            settings=settings,
            file_path=output_path,
        )

        # Save to the new format
        ProjectStorage.save(project, output_path)

        return project

    @staticmethod
    def cleanup_old_files(data_dir: Path) -> list[Path]:
        """
        Remove old format files after successful migration.

        Only removes files if a .pairrank file exists in the directory.

        Args:
            data_dir: Directory to clean up.

        Returns:
            list[Path]: List of files that were deleted.

        Raises:
            ValueError: If no .pairrank file exists in the directory.
        """
        pairrank_files = list(data_dir.glob(f"*{ProjectStorage.FILE_EXTENSION}"))
        if not pairrank_files:
            raise ValueError("No .pairrank file found - migration must complete first")

        deleted = []
        for filename in StorageMigration.OLD_FILES:
            file_path = data_dir / filename
            if file_path.exists():
                file_path.unlink()
                deleted.append(file_path)

        return deleted
