"""Main application window for the pairwise ranking application."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QMessageBox,
    QMenu,
    QFileDialog,
    QInputDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from src.data.project_storage import ProjectStorage
from src.data.user_config import UserConfig
from src.models.project import Project
from src.models.settings import Settings
from src.models.item import Item
from src.models.vote import Vote
from src.models.ranking import BradleyTerryModel, PairSelector, RankingResult
from src.ui.item_list import ItemListWidget
from src.ui.comparison import ComparisonWidget
from src.ui.results import ResultsWidget
from src.ui.settings import SettingsWidget


class MainWindow(QMainWindow):
    """
    Main application window with tabbed interface.

    Provides access to four main views:
    - Items: Manage the list of items to rank
    - Compare: Perform pairwise comparisons
    - Rankings: View current rankings
    - Settings: Configure algorithm parameters

    Attributes:
        project: The current project being edited.
        user_config: User configuration for recent projects.
    """

    def __init__(self, project: Project, user_config: UserConfig):
        """
        Initialize the main window.

        Args:
            project: The project to work with.
            user_config: User configuration instance.
        """
        super().__init__()

        self.project = project
        self.user_config = user_config

        # Convenience references
        self.items = self.project.items
        self.votes = self.project.votes
        self.settings = self.project.settings

        # Current rankings (computed on demand)
        self._rankings: Optional[list[RankingResult]] = None

        # Set up UI
        self._setup_menu()
        self._setup_ui()
        self._connect_signals()

        # Initial data refresh
        self._refresh_all()
        self._update_window_title()

    def _setup_menu(self) -> None:
        """Set up the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New Project...", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Project...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_action)

        # Recent projects submenu
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._refresh_recent_menu()

        file_menu.addSeparator()

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _refresh_recent_menu(self) -> None:
        """Refresh the recent projects submenu."""
        self.recent_menu.clear()

        recent = self.user_config.get_recent_projects()

        if not recent:
            no_recent = QAction("(No recent projects)", self)
            no_recent.setEnabled(False)
            self.recent_menu.addAction(no_recent)
            return

        for project_info in recent:
            name = project_info.get("name", "Unknown")
            path = project_info.get("path", "")

            action = QAction(name, self)
            action.setData(path)
            action.triggered.connect(lambda checked, p=path: self._open_project_file(Path(p)))
            self.recent_menu.addAction(action)

    def _update_window_title(self) -> None:
        """Update the window title to show project name."""
        self.setWindowTitle(f"{self.project.name} - Pairwise Ranking")

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setMinimumSize(800, 600)

        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self.item_list_widget = ItemListWidget()
        self.comparison_widget = ComparisonWidget()
        self.results_widget = ResultsWidget()
        self.settings_widget = SettingsWidget()

        self.tabs.addTab(self.item_list_widget, "Items")
        self.tabs.addTab(self.comparison_widget, "Compare")
        self.tabs.addTab(self.results_widget, "Rankings")
        self.tabs.addTab(self.settings_widget, "Settings")

    def _connect_signals(self) -> None:
        """Connect signals between widgets."""
        # Item list signals
        self.item_list_widget.item_added.connect(self._on_item_added)
        self.item_list_widget.item_updated.connect(self._on_item_updated)
        self.item_list_widget.item_deleted.connect(self._on_item_deleted)

        # Comparison signals
        self.comparison_widget.vote_submitted.connect(self._on_vote_submitted)
        self.comparison_widget.skip_requested.connect(self._on_skip_requested)

        # Settings signals
        self.settings_widget.settings_changed.connect(self._on_settings_changed)

        # Tab change
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _save_project(self) -> None:
        """Save the current project to disk."""
        if self.project.file_path:
            ProjectStorage.save(self.project, self.project.file_path)
            self.user_config.add_recent_project(
                self.project.name,
                self.project.file_path,
                self.project.modified,
            )

    def _refresh_all(self) -> None:
        """Refresh all widgets with current data."""
        self._compute_rankings()
        self._refresh_item_list()
        self._refresh_comparison()
        self._refresh_results()
        self._refresh_settings()

    def _compute_rankings(self) -> None:
        """Compute rankings from current items and votes."""
        # Rankings are always computed for all items (not filtered by blinded mode)
        # This ensures the Rankings tab shows all items regardless of mode
        if len(self.items) < 2:
            self._rankings = None
            return

        model = BradleyTerryModel(self.items)
        model.add_votes(
            self.votes,
            decay_timescale_days=self.settings.decay_timescale_days,
        )
        self._rankings = model.compute_rankings()

    def _refresh_item_list(self) -> None:
        """Refresh the items list widget."""
        self.item_list_widget.set_items(self.items)

    def _refresh_comparison(self) -> None:
        """Refresh the comparison widget with next pair."""
        blinded_mode = self.settings.blinded_comparison_mode

        # In blinded mode, only include items with identifiers
        if blinded_mode:
            eligible_items = [item for item in self.items if item.has_identifier()]
        else:
            eligible_items = self.items

        if len(eligible_items) < 2:
            if blinded_mode and len(self.items) >= 2:
                # Have items but they lack identifiers
                self.comparison_widget.set_no_items(
                    "Assign location identifiers to at least 2 items to compare in blinded mode"
                )
            else:
                self.comparison_widget.set_no_items()
            return

        selector = PairSelector(eligible_items, self.votes, self.settings)
        pair = selector.select_pair(self._rankings)

        if pair is None:
            self.comparison_widget.set_no_items()
            return

        stats = selector.get_comparison_stats()
        self.comparison_widget.set_pair(pair[0], pair[1], stats, blinded_mode=blinded_mode)

    def _refresh_results(self) -> None:
        """Refresh the results widget."""
        if self._rankings:
            self.results_widget.set_rankings(self._rankings, self.votes)
        else:
            self.results_widget.set_no_rankings()

    def _refresh_settings(self) -> None:
        """Refresh the settings widget."""
        self.settings_widget.set_settings(self.settings)

    def _on_item_added(self, item: Item) -> None:
        """Handle item added event."""
        self.items.append(item)
        self._save_project()
        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_item_updated(self, item: Item) -> None:
        """Handle item updated event."""
        for i, existing in enumerate(self.items):
            if existing.id == item.id:
                self.items[i] = item
                break
        self._save_project()
        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_item_deleted(self, item_id: str) -> None:
        """Handle item deleted event."""
        self.project.items[:] = [item for item in self.items if item.id != item_id]
        self.items = self.project.items

        # Also delete votes involving this item
        self.project.votes[:] = [v for v in self.votes if not v.involves_item(item_id)]
        self.votes = self.project.votes

        self._save_project()
        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_vote_submitted(self, vote: Vote) -> None:
        """Handle vote submitted event."""
        self.votes.append(vote)
        self._save_project()
        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_skip_requested(self) -> None:
        """Handle skip requested event - just get next pair."""
        self._refresh_comparison()

    def _on_settings_changed(self, settings: Settings) -> None:
        """Handle settings changed event."""
        self.project.settings = settings
        self.settings = settings
        self._save_project()
        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change event."""
        # Refresh the new tab's content
        if index == 0:  # Items
            self._refresh_item_list()
        elif index == 1:  # Compare
            self._refresh_comparison()
        elif index == 2:  # Rankings
            self._refresh_results()
        elif index == 3:  # Settings
            self._refresh_settings()

    def _on_new_project(self) -> None:
        """Handle File > New Project."""
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
        if file_path.suffix != ProjectStorage.FILE_EXTENSION:
            file_path = file_path.with_suffix(ProjectStorage.FILE_EXTENSION)

        try:
            new_project = ProjectStorage.create_new(name, file_path)
            self._switch_to_project(new_project)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Failed to create project:\n{e}")

    def _on_open_project(self) -> None:
        """Handle File > Open Project."""
        default_dir = self.user_config.get_default_projects_dir()
        if not default_dir.exists():
            default_dir = Path.home()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(default_dir),
            f"Pairrank Files (*{ProjectStorage.FILE_EXTENSION})",
        )

        if file_path:
            self._open_project_file(Path(file_path))

    def _on_save_as(self) -> None:
        """Handle File > Save As."""
        default_dir = self.user_config.get_default_projects_dir()
        default_dir.mkdir(parents=True, exist_ok=True)

        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in self.project.name)
        default_path = default_dir / f"{safe_name}{ProjectStorage.FILE_EXTENSION}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            str(default_path),
            f"Pairrank Files (*{ProjectStorage.FILE_EXTENSION})",
        )

        if not file_path:
            return

        file_path = Path(file_path)
        if file_path.suffix != ProjectStorage.FILE_EXTENSION:
            file_path = file_path.with_suffix(ProjectStorage.FILE_EXTENSION)

        try:
            self.project.file_path = file_path
            self._save_project()
            self._update_window_title()
            self._refresh_recent_menu()
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Failed to save project:\n{e}")

    def _open_project_file(self, file_path: Path) -> None:
        """Open a project file."""
        try:
            project = ProjectStorage.load(file_path)
            self._switch_to_project(project)
        except FileNotFoundError:
            QMessageBox.warning(self, "File Not Found", f"Project file not found:\n{file_path}")
            self.user_config.remove_recent_project(file_path)
            self._refresh_recent_menu()
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    def _switch_to_project(self, project: Project) -> None:
        """Switch to a different project."""
        self.project = project
        self.items = self.project.items
        self.votes = self.project.votes
        self.settings = self.project.settings

        self.user_config.add_recent_project(
            project.name,
            project.file_path,
            project.modified,
        )

        self._update_window_title()
        self._refresh_recent_menu()
        self._refresh_all()

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        # Data is saved incrementally via auto-save, so just accept the close
        event.accept()
