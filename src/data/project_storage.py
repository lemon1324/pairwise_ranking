"""Project file storage for the pairwise ranking application."""

import json
from datetime import datetime
from pathlib import Path

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

    @staticmethod
    def save(project: Project, file_path: Path) -> None:
        """
        Save a project to a .pairrank file.

        Updates the project's modified timestamp before saving.

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

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(project.to_dict(), f, indent=2)

    @staticmethod
    def load(file_path: Path) -> Project:
        """
        Load a project from a .pairrank file.

        Args:
            file_path: Path to the .pairrank file.

        Returns:
            Project: The loaded project with file_path set.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file_path doesn't have .pairrank extension.
            json.JSONDecodeError: If file contains invalid JSON.
        """
        if file_path.suffix != ProjectStorage.FILE_EXTENSION:
            raise ValueError(f"File must have {ProjectStorage.FILE_EXTENSION} extension")

        if not file_path.exists():
            raise FileNotFoundError(f"Project file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return Project.from_dict(data, file_path=file_path)

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
