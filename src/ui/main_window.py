"""Main application window for the pairwise ranking application."""

from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QMessageBox,
    QInputDialog,
)
from PyQt6.QtGui import QAction

from src.app.session import NoPairReason, PairOffer, ProjectSession
from src.data.project_storage import ProjectStorage
from src.data.user_config import UserConfig
from src.models.project import Project
from src.models.settings import Settings
from src.models.item import Item
from src.models.vote import Vote
from src.ui.item_list import ItemListWidget
from src.ui.comparison import ComparisonWidget
from src.ui.results import ResultsWidget
from src.ui.settings import SettingsWidget
from src.ui.project_dialogs import (
    ask_duplicate_project,
    ask_new_project,
    ask_open_project_path,
    ask_save_as_path,
)


class MainWindow(QMainWindow):
    """
    Main application window with tabbed interface.

    Provides access to four main views:
    - Items: Manage the list of items to rank
    - Compare: Perform pairwise comparisons
    - Rankings: View current rankings
    - Settings: Configure algorithm parameters

    The window owns no application logic: it renders what
    :class:`~src.app.session.ProjectSession` computes and hands user actions
    back to it. File dialogs, message boxes and the wording of every message
    stay here.

    Attributes:
        session: The session over the project being edited.
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

        self.session = ProjectSession(project, on_saved=self._on_project_saved)
        self.user_config = user_config

        # Set up UI
        self._setup_menu()
        self._setup_ui()
        self._connect_signals()

        # Initial data refresh
        self._refresh_all()
        self._update_window_title()

    @property
    def project(self) -> Project:
        """
        Return the project currently on screen.

        Returns:
            Project: The project the session is editing.
        """
        return self.session.project

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

        rename_action = QAction("&Rename Project...", self)
        rename_action.triggered.connect(self._on_rename_project)
        file_menu.addAction(rename_action)

        duplicate_action = QAction("&Duplicate Without Votes...", self)
        duplicate_action.triggered.connect(self._on_duplicate_project)
        file_menu.addAction(duplicate_action)

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

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self.undo_action = QAction("&Undo Last Vote", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self._on_undo_last_vote)
        edit_menu.addAction(self.undo_action)

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
        self.item_list_widget = ItemListWidget(self.session)
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
        self.item_list_widget.item_retired.connect(self._on_item_retired)
        self.item_list_widget.item_replaced.connect(self._on_item_replaced)

        # Comparison signals
        self.comparison_widget.vote_submitted.connect(self._on_vote_submitted)
        self.comparison_widget.skip_requested.connect(self._on_skip_requested)
        self.comparison_widget.undo_requested.connect(self._on_undo_last_vote)

        # Settings signals
        self.settings_widget.settings_changed.connect(self._on_settings_changed)

        # Tab change
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_project_saved(self, project: Project) -> None:
        """
        Record a project the session has just saved.

        The recent projects list is desktop business, so the session reports
        its saves here instead of knowing about user configuration.

        Args:
            project: The project that was saved.
        """
        self.user_config.add_recent_project(
            project.name,
            project.file_path,
            project.modified,
        )

    def _refresh_all(self) -> None:
        """Refresh all widgets with current data."""
        self._refresh_item_list()
        self._refresh_comparison()
        self._refresh_results()
        self._refresh_settings()
        self._refresh_undo_state()

    def _refresh_item_list(self) -> None:
        """Refresh the items list widget."""
        self.item_list_widget.set_items(self.project.items)

    def _refresh_comparison(self) -> None:
        """Refresh the comparison widget with next pair."""
        self._show_offer(self.session.next_pair())

    def _show_offer(self, offer: PairOffer) -> None:
        """
        Render a pair offer, or the message that goes with its refusal.

        Args:
            offer: The offer to show. The session reports why it has no pair;
                the wording of that is this window's business.
        """
        if offer.has_pair():
            self.comparison_widget.set_pair(
                offer.pair[0],
                offer.pair[1],
                offer.stats,
                blinded_mode=offer.blinded,
            )
        elif offer.reason == NoPairReason.BLINDED_NO_IDENTIFIERS:
            # Have items but they lack identifiers
            self.comparison_widget.set_no_items(
                "Assign identifiers to at least 2 items to compare in blinded mode"
            )
        else:
            self.comparison_widget.set_no_items()

    def _refresh_results(self) -> None:
        """Refresh the results widget."""
        rankings = self.session.rankings()
        if rankings:
            self.results_widget.set_rankings(rankings, self.project.votes)
        else:
            self.results_widget.set_no_rankings()

    def _refresh_settings(self) -> None:
        """Refresh the settings widget."""
        self.settings_widget.set_settings(self.project.settings)
        self.settings_widget.set_slots(self.project.slots)

    def _refresh_undo_state(self) -> None:
        """Enable the undo action and button only when there is a vote to undo."""
        can_undo = bool(self.project.votes)
        self.undo_action.setEnabled(can_undo)
        self.comparison_widget.set_undo_enabled(can_undo)

    def _on_data_changed(self) -> None:
        """
        Refresh everything that depends on the data.

        The session has already saved by the time this runs. The Settings tab
        is deliberately left alone: it holds edits the user may not have saved
        yet.
        """
        self._refresh_item_list()
        self._refresh_comparison()
        self._refresh_results()
        self._refresh_undo_state()

    def _on_item_added(self, item: Item) -> None:
        """Handle item added event."""
        self.session.add_item(item)
        self._on_data_changed()

    def _on_item_updated(self, item: Item) -> None:
        """Handle item updated event."""
        self.session.update_item(item)
        self._on_data_changed()

    def _on_item_deleted(self, item_id: str) -> None:
        """Handle item deleted event."""
        self.session.delete_item(item_id)
        self._on_data_changed()

    def _on_item_retired(self, item_id: str) -> None:
        """Handle item retired event."""
        self.session.retire(item_id)
        self._on_data_changed()

    def _on_item_replaced(self, old_item_id: str, new_item: Item) -> None:
        """Handle item replaced event: retire the old item, add its successor."""
        self.session.replace(old_item_id, new_item)
        self._on_data_changed()

    def _on_vote_submitted(self, vote: Vote) -> None:
        """Handle vote submitted event."""
        self.session.vote(vote.winner_id, vote.loser_id, vote.weight)
        self._on_data_changed()

    def _on_skip_requested(self) -> None:
        """Handle skip requested event - just get next pair."""
        self._show_offer(self.session.skip())

    def _on_undo_last_vote(self) -> None:
        """Remove the most recent vote and offer its pair again if possible."""
        result = self.session.undo()
        if result is None:
            return

        self._refresh_item_list()
        self._show_offer(result.offer)
        if result.pair is not None:
            # The undone pair goes back up over whatever the session just
            # chose, carrying that selection's statistics rather than new ones.
            self.comparison_widget.set_pair(
                result.pair[0],
                result.pair[1],
                result.offer.stats,
                blinded_mode=result.offer.blinded,
            )
        self._refresh_results()
        self._refresh_undo_state()

    def _on_settings_changed(self, settings: Settings) -> None:
        """
        Apply the settings and slot list from a single Save Settings click.

        The slot list is read back from the widget rather than arriving on a
        second signal, so one click means exactly one save.

        Args:
            settings: The settings as entered.
        """
        slots = self.session.apply_settings(settings, self.settings_widget.get_slots())
        self._on_data_changed()
        # Show the slot list as it was normalized.
        self.settings_widget.set_slots(slots)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change event."""
        # Refresh the new tab's content. The Settings tab is deliberately not
        # refreshed here: it holds edits the user has not saved yet, and is
        # pushed only on startup, on a project switch and after a save.
        if index == 0:  # Items
            self._refresh_item_list()
        elif index == 1:  # Compare
            self._refresh_comparison()
        elif index == 2:  # Rankings
            self._refresh_results()

    def _on_new_project(self) -> None:
        """Handle File > New Project."""
        new_project = ask_new_project(self, self.user_config)
        if new_project is None:
            return

        self._switch_to_project(new_project)

    def _on_open_project(self) -> None:
        """Handle File > Open Project."""
        file_path = ask_open_project_path(self, self.user_config)
        if file_path is not None:
            self._open_project_file(file_path)

    def _on_duplicate_project(self) -> None:
        """Handle File > Duplicate Without Votes."""
        new_project = ask_duplicate_project(self, self.user_config, self.session)
        if new_project is None:
            return

        self._switch_to_project(new_project)

    def _on_rename_project(self) -> None:
        """Handle File > Rename Project."""
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Project",
            "Project name:",
            text=self.project.name,
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name or new_name == self.project.name:
            return

        # Only the name inside the project changes; the file keeps its path.
        self.session.rename(new_name)
        self._on_data_changed()
        self._update_window_title()

        if self.project.file_path:
            self.user_config.add_recent_project(
                self.project.name,
                self.project.file_path,
                self.project.modified,
            )
        self._refresh_recent_menu()

    def _on_save_as(self) -> None:
        """Handle File > Save As."""
        file_path = ask_save_as_path(self, self.user_config, self.project.name)
        if file_path is None:
            return

        try:
            self.project.file_path = file_path
            self.session.save()
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
        self.session = ProjectSession(project, on_saved=self._on_project_saved)
        self.item_list_widget.set_session(self.session)

        self.user_config.add_recent_project(
            project.name,
            project.file_path,
            project.modified,
        )

        self._update_window_title()
        self._refresh_recent_menu()
        self._refresh_all()
