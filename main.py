#!/usr/bin/env python3
"""
Pairwise Ranking Application

A PyQt6 GUI application for pairwise comparison ranking using a Bradley-Terry
model with regularization.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QDialog

from src.data.user_config import UserConfig
from src.data.migration import StorageMigration
from src.ui.project_picker import ProjectPickerDialog
from src.ui.main_window import MainWindow


def main():
    """
    Application entry point.

    Creates the QApplication instance, handles migration from old storage format,
    shows the project picker dialog, and starts the main window.

    Returns:
        int: Exit code from the application.
    """
    app = QApplication(sys.argv)
    app.setApplicationName("Pairwise Ranking")
    app.setApplicationVersion("0.1.0")

    # Load user configuration
    user_config = UserConfig()

    # Check for legacy data and migrate if present (relative to this file,
    # not the current working directory)
    data_dir = Path(__file__).resolve().parent / "data"
    if StorageMigration.needs_migration(data_dir):
        project = StorageMigration.migrate(data_dir)
        user_config.add_recent_project(
            project.name,
            project.file_path,
            project.modified,
        )

    # Show project picker dialog
    picker = ProjectPickerDialog(user_config)
    if picker.exec() != QDialog.DialogCode.Accepted:
        # User cancelled - exit application
        return 0

    project = picker.get_selected_project()
    if project is None:
        return 0

    # Create and show main window
    window = MainWindow(project, user_config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
