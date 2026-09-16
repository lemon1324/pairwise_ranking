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
    def save(
        project: Project,
        file_path: Path,
        *,
        touch_modified: bool = True,
        backup: bool = True,
    ) -> None:
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
            touch_modified: Whether to stamp the project as modified now. The
                format migration in :meth:`load` passes False so that reading
                an old file does not look like an edit.
            backup: Whether to copy an existing target to ``.pairrank.bak``
                first. The format migration passes False because it writes its
                own ``.pairrank.v<old>.bak`` instead.

        Raises:
            ValueError: If file_path doesn't have .pairrank extension.
            OSError: If file cannot be written.
        """
        if file_path.suffix != ProjectStorage.FILE_EXTENSION:
            raise ValueError(f"File must have {ProjectStorage.FILE_EXTENSION} extension")

        if touch_modified:
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

            if backup and file_path.exists():
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
        migration runs only the first time the file is opened. That re-save
        keeps the file's original modified timestamp and writes no
        ``.pairrank.bak``, so reading a file never looks like an edit. If the
        backup or the re-save cannot be written the upgraded project is still
        returned and a warning is printed. Loading a file that is already
        current writes nothing.

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
        except ValueError:
            # Already a clear message about what is wrong with the file.
            raise
        except Exception as e:
            raise ValueError(f"Invalid project file: {e}") from e

        if started_version < CURRENT_FORMAT_VERSION:
            ProjectStorage._migrate_in_place(
                project, file_path, original_bytes, started_version
            )

        return project

    @staticmethod
    def _migrate_in_place(
        project: Project,
        file_path: Path,
        original_bytes: bytes,
        started_version: int,
    ) -> None:
        """
        Back up the original file and write the upgraded project over it.

        A failure here is not fatal: the caller already holds a usable,
        upgraded project in memory, so the migration is simply skipped (and
        retried the next time the file is opened).

        Args:
            project: The upgraded project.
            file_path: The project file that was read.
            original_bytes: The exact bytes read from that file.
            started_version: The format version the file was written in.
        """
        backup_path = file_path.with_suffix(
            ProjectStorage.MIGRATION_BACKUP_TEMPLATE.format(version=started_version)
        )
        try:
            if not backup_path.exists():
                backup_path.write_bytes(original_bytes)
            # The migration is not a user edit: keep the recorded modified
            # timestamp and leave the regular .pairrank.bak alone.
            ProjectStorage.save(
                project, file_path, touch_modified=False, backup=False
            )
        except OSError as e:
            print(
                f"Warning: could not migrate {file_path} to format version "
                f"{CURRENT_FORMAT_VERSION}: {e}"
            )

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

    @staticmethod
    def create_copy(source: Project, name: str, file_path: Path) -> Project:
        """
        Create a copy of a project without its votes and save it.

        The copy carries the source project's items, settings and slots, with
        item ids preserved, but starts with no votes. The source project and
        its file are left untouched.

        Args:
            source: The project to copy.
            name: Name for the new project.
            file_path: Path where the new project file will be saved.

        Returns:
            Project: The newly created and saved project.

        Raises:
            ValueError: If name is empty or only whitespace, or if file_path
                doesn't have .pairrank extension.
            OSError: If file cannot be written.
        """
        project = source.copy_without_votes(name)
        project.file_path = file_path

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
