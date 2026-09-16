"""Project file storage for the pairwise ranking application."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from src.data.format_version import CURRENT_FORMAT_VERSION, upgrade
from src.models.project import Project
from src.models.settings import Settings


class ProjectStorage:
    """
    Handles reading and writing .pairrank project files.

    Project files are JSON files containing all project data: items, votes,
    settings, and metadata.

    Example:
        >>> project = ProjectStorage.load(Path("my_project.pairrank"))
        >>> project.name = "Updated Name"
        >>> ProjectStorage.save(project, project.file_path)
    """

    FILE_EXTENSION = ".pairrank"
    BACKUP_EXTENSION = ".pairrank.bak"
    MIGRATION_BACKUP_TEMPLATE = ".pairrank.v{version}.bak"

    @staticmethod
    def save(project: Project, file_path: Path) -> None:
        """
        Save a project to a .pairrank file.

        Updates the project's modified timestamp before saving. The write is
        atomic: data is serialized to a temporary file in the same directory,
        flushed to disk, and then moved over the target with ``os.replace``.
        If the target already exists it is first copied to a ``.pairrank.bak``
        backup, so a failed save never corrupts or truncates the existing file.

        Args:
            project: The Project to save.
            file_path: Path to save the file to.

        Raises:
            ValueError: If file_path doesn't have .pairrank extension.
            OSError: If file cannot be written.
        """
        if file_path.suffix != ProjectStorage.FILE_EXTENSION:
            raise ValueError(f"File must have {ProjectStorage.FILE_EXTENSION} extension")

        project.modified = datetime.now()
        project.file_path = file_path

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = file_path.with_name(file_path.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(project.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            if file_path.exists():
                backup_path = file_path.with_suffix(ProjectStorage.BACKUP_EXTENSION)
                shutil.copy2(file_path, backup_path)

            os.replace(tmp_path, file_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def load(file_path: Path) -> Project:
        """
        Load a project from a .pairrank file, upgrading it if necessary.

        Files written in an older format version are upgraded in memory. When
        that happens the original bytes are copied once to a
        ``.pairrank.v<old>.bak`` file beside the project (never overwriting an
        existing one) and the upgraded project is saved immediately, so the
        migration runs only the first time the file is opened. Loading a file
        that is already current writes nothing.

        Args:
            file_path: Path to the .pairrank file.

        Returns:
            Project: The loaded project with file_path set.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file_path doesn't have .pairrank extension, if the
                file is not valid JSON or is missing required data, or if the
                file was written by a newer version of the application.
        """
        if file_path.suffix != ProjectStorage.FILE_EXTENSION:
            raise ValueError(f"File must have {ProjectStorage.FILE_EXTENSION} extension")

        if not file_path.exists():
            raise FileNotFoundError(f"Project file not found: {file_path}")

        original_bytes = file_path.read_bytes()

        try:
            data = json.loads(original_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid project file: {e}") from e

        try:
            upgraded, started_version = upgrade(data)
            project = Project.from_dict(upgraded, file_path=file_path)
        except (KeyError, TypeError) as e:
            raise ValueError(f"Invalid project file: {e}") from e

        if started_version < CURRENT_FORMAT_VERSION:
            backup_path = file_path.with_suffix(
                ProjectStorage.MIGRATION_BACKUP_TEMPLATE.format(version=started_version)
            )
            if not backup_path.exists():
                backup_path.write_bytes(original_bytes)
            ProjectStorage.save(project, file_path)

        return project

    @staticmethod
    def create_new(name: str, file_path: Path) -> Project:
        """
        Create a new empty project and save it.

        Args:
            name: Name for the new project.
            file_path: Path where the project file will be saved.

        Returns:
            Project: The newly created and saved project.

        Raises:
            ValueError: If file_path doesn't have .pairrank extension.
            OSError: If file cannot be written.
        """
        project = Project(
            name=name,
            created=datetime.now(),
            modified=datetime.now(),
            items=[],
            votes=[],
            settings=Settings(),
            file_path=file_path,
        )

        ProjectStorage.save(project, file_path)
        return project


def safe_project_filename(name: str) -> str:
    """
    Build a filesystem-safe file stem from a project name.

    Alphanumeric characters, spaces, underscores and hyphens are kept; every
    other character becomes an underscore.

    Args:
        name: The project name.

    Returns:
        str: A file stem safe to use in a default save path.
    """
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name)


def ensure_pairrank_suffix(path: Path) -> Path:
    """
    Ensure a path carries the .pairrank extension.

    Args:
        path: The path chosen by the user.

    Returns:
        Path: The same path if it already has the extension, otherwise the
        path with its suffix replaced by .pairrank.
    """
    if path.suffix != ProjectStorage.FILE_EXTENSION:
        return path.with_suffix(ProjectStorage.FILE_EXTENSION)
    return path
