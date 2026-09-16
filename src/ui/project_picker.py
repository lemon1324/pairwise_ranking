"""Project picker dialog for startup."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from src.data.user_config import UserConfig
from src.data.project_storage import ProjectStorage
from src.models.project import Project


class ProjectPickerDialog(QDialog):
    """
    Dialog shown at startup for selecting or creating a project.

    Users can:
    - Create a new project
    - Open an existing .pairrank file
    - Select from recent projects

    Attributes:
        user_config: UserConfig instance for recent projects.
        selected_project: The project that was selected, or None.
    """

    def __init__(self, user_config: UserConfig, parent=None):
        """
        Initialize the project picker dialog.

        Args:
            user_config: UserConfig instance for recent projects.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.user_config = user_config
        self.selected_project: Optional[Project] = None
        self._setup_ui()
        self._refresh_recent_list()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setWindowTitle("Pairwise Ranking")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Title
        title = QLabel("Pairwise Ranking")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.new_btn = QPushButton("New Project")
        self.new_btn.setMinimumHeight(36)
        self.new_btn.clicked.connect(self._on_new_clicked)
        btn_layout.addWidget(self.new_btn)

        self.open_btn = QPushButton("Open Project...")
        self.open_btn.setMinimumHeight(36)
        self.open_btn.clicked.connect(self._on_open_clicked)
        btn_layout.addWidget(self.open_btn)

        layout.addLayout(btn_layout)

        # Recent projects section
        recent_label = QLabel("Recent Projects:")
        recent_font = QFont()
        recent_font.setBold(True)
        recent_label.setFont(recent_font)
        layout.addWidget(recent_label)

        # Recent projects table
        self.recent_table = QTableWidget()
        self.recent_table.setColumnCount(2)
        self.recent_table.setHorizontalHeaderLabels(["Project Name", "Last Modified"])
        self.recent_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.recent_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.recent_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.recent_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.recent_table.itemDoubleClicked.connect(self._on_recent_double_clicked)
        self.recent_table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.recent_table)

        # Bottom buttons
        bottom_layout = QHBoxLayout()

        self.open_selected_btn = QPushButton("Open Selected")
        self.open_selected_btn.setEnabled(False)
        self.open_selected_btn.clicked.connect(self._on_open_selected_clicked)
        bottom_layout.addWidget(self.open_selected_btn)

        bottom_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(self.cancel_btn)

        layout.addLayout(bottom_layout)

    def _refresh_recent_list(self) -> None:
        """Refresh the recent projects list."""
        recent = self.user_config.get_recent_projects()
        self.recent_table.setRowCount(len(recent))

        for row, project in enumerate(recent):
            name_item = QTableWidgetItem(project.get("name", "Unknown"))
            name_item.setData(Qt.ItemDataRole.UserRole, project.get("path", ""))
            self.recent_table.setItem(row, 0, name_item)

            modified_str = project.get("modified", "")
            if modified_str:
                try:
                    modified = datetime.fromisoformat(modified_str)
                    display_date = modified.strftime("%b %d, %Y %H:%M")
                except ValueError:
                    display_date = modified_str
            else:
                display_date = ""

            date_item = QTableWidgetItem(display_date)
            self.recent_table.setItem(row, 1, date_item)

        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        """Handle selection change in recent projects."""
        has_selection = len(self.recent_table.selectedIndexes()) > 0
        self.open_selected_btn.setEnabled(has_selection)

    def _on_new_clicked(self) -> None:
        """Handle new project button click."""
        # Get project name
        name, ok = QInputDialog.getText(
            self,
            "New Project",
            "Project name:",
            text="My Rankings",
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        # Get save location
        default_dir = self.user_config.get_default_projects_dir()
        default_dir.mkdir(parents=True, exist_ok=True)

        # Create a safe filename from project name
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        default_path = default_dir / f"{safe_name}{ProjectStorage.FILE_EXTENSION}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save New Project",
            str(default_path),
            f"Pairrank Files (*{ProjectStorage.FILE_EXTENSION})",
        )

        if not file_path:
            return

        file_path = Path(file_path)

        # Ensure correct extension
        if file_path.suffix != ProjectStorage.FILE_EXTENSION:
            file_path = file_path.with_suffix(ProjectStorage.FILE_EXTENSION)

        try:
            self.selected_project = ProjectStorage.create_new(name, file_path)
            self.user_config.add_recent_project(
                name,
                file_path,
                self.selected_project.modified,
            )
            self.accept()
        except (OSError, ValueError) as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create project:\n{e}",
            )

    def _on_open_clicked(self) -> None:
        """Handle open project button click."""
        default_dir = self.user_config.get_default_projects_dir()
        if not default_dir.exists():
            default_dir = Path.home()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(default_dir),
            f"Pairrank Files (*{ProjectStorage.FILE_EXTENSION})",
        )

        if not file_path:
            return

        self._open_project(Path(file_path))

    def _on_recent_double_clicked(self) -> None:
        """Handle double-click on recent project."""
        self._on_open_selected_clicked()

    def _on_open_selected_clicked(self) -> None:
        """Handle open selected button click."""
        rows = self.recent_table.selectedIndexes()
        if not rows:
            return

        row = rows[0].row()
        path_str = self.recent_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if path_str:
            self._open_project(Path(path_str))

    def _open_project(self, file_path: Path) -> None:
        """Open a project file."""
        try:
            self.selected_project = ProjectStorage.load(file_path)
            self.user_config.add_recent_project(
                self.selected_project.name,
                file_path,
                self.selected_project.modified,
            )
            self.accept()
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "File Not Found",
                f"Project file not found:\n{file_path}",
            )
            self.user_config.remove_recent_project(file_path)
            self._refresh_recent_list()
        except (OSError, ValueError) as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open project:\n{e}",
            )

    def get_selected_project(self) -> Optional[Project]:
        """
        Get the selected project.

        Returns:
            Project: The selected project, or None if dialog was cancelled.
        """
        return self.selected_project
