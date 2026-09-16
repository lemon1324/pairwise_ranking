"""Shared file dialogs for creating, opening and saving project files.

Both the startup project picker and the main window need the same new/open/
save-as flows, so they live here rather than being duplicated in each widget.
The two pure helpers are defined in :mod:`src.data.project_storage` (so they
can be tested without Qt) and re-exported for convenience.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QWidget

from src.data.project_storage import (
    ProjectStorage,
    ensure_pairrank_suffix,
    safe_project_filename,
)
from src.data.user_config import UserConfig
from src.models.project import Project

__all__ = [
    "safe_project_filename",
    "ensure_pairrank_suffix",
    "ask_new_project",
    "ask_open_project_path",
    "ask_save_as_path",
]

FILE_FILTER = f"Pairrank Files (*{ProjectStorage.FILE_EXTENSION})"


def ask_save_as_path(
    parent: Optional[QWidget],
    user_config: UserConfig,
    project_name: str,
    title: str = "Save Project As",
) -> Optional[Path]:
    """
    Ask the user where to save a project file.

    Args:
        parent: Parent widget for the dialog.
        user_config: User configuration, used for the default directory.
        project_name: Project name used to build the default filename.
        title: Dialog title.

    Returns:
        Optional[Path]: The chosen path with a .pairrank extension, or None if
        the user cancelled.
    """
    default_dir = user_config.get_default_projects_dir()
    default_dir.mkdir(parents=True, exist_ok=True)

    default_path = default_dir / (
        f"{safe_project_filename(project_name)}{ProjectStorage.FILE_EXTENSION}"
    )

    file_path, _ = QFileDialog.getSaveFileName(
        parent,
        title,
        str(default_path),
        FILE_FILTER,
    )

    if not file_path:
        return None

    return ensure_pairrank_suffix(Path(file_path))


def ask_open_project_path(
    parent: Optional[QWidget],
    user_config: UserConfig,
) -> Optional[Path]:
    """
    Ask the user which project file to open.

    Args:
        parent: Parent widget for the dialog.
        user_config: User configuration, used for the default directory.

    Returns:
        Optional[Path]: The chosen path, or None if the user cancelled.
    """
    default_dir = user_config.get_default_projects_dir()
    if not default_dir.exists():
        default_dir = Path.home()

    file_path, _ = QFileDialog.getOpenFileName(
        parent,
        "Open Project",
        str(default_dir),
        FILE_FILTER,
    )

    if not file_path:
        return None

    return Path(file_path)


def ask_new_project(
    parent: Optional[QWidget],
    user_config: UserConfig,
) -> Optional[Project]:
    """
    Prompt for a project name and location, then create the project file.

    Shows an error message box if the project cannot be created. The caller is
    responsible for recording the project in the recent projects list.

    Args:
        parent: Parent widget for the dialogs.
        user_config: User configuration, used for the default directory.

    Returns:
        Optional[Project]: The newly created project, or None if the user
        cancelled or creation failed.
    """
    name, ok = QInputDialog.getText(
        parent,
        "New Project",
        "Project name:",
        text="My Rankings",
    )

    if not ok or not name.strip():
        return None

    name = name.strip()

    file_path = ask_save_as_path(parent, user_config, name, title="Save New Project")
    if file_path is None:
        return None

    try:
        return ProjectStorage.create_new(name, file_path)
    except (OSError, ValueError) as e:
        QMessageBox.critical(parent, "Error", f"Failed to create project:\n{e}")
        return None
