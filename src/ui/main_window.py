"""Main application window for the pairwise ranking application."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from src.data.storage import Storage
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
        storage: Storage instance for data persistence.
        items: List of items being ranked.
        votes: List of comparison votes.
        settings: Application settings.
    """

    def __init__(self, data_dir: Optional[str | Path] = None):
        """
        Initialize the main window.

        Args:
            data_dir: Directory for data storage. Defaults to ./data.
        """
        super().__init__()

        # Set up storage
        if data_dir is None:
            data_dir = Path("./data")
        self.storage = Storage(data_dir)

        # Load data
        self.items: list[Item] = self.storage.load_items()
        self.votes: list[Vote] = self.storage.load_votes()
        self.settings: Settings = self.storage.load_settings()

        # Current rankings (computed on demand)
        self._rankings: Optional[list[RankingResult]] = None

        # Set up UI
        self._setup_ui()
        self._connect_signals()

        # Initial data refresh
        self._refresh_all()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("Pairwise Ranking")
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
        self.storage.save_item(item)
        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_item_updated(self, item: Item) -> None:
        """Handle item updated event."""
        for i, existing in enumerate(self.items):
            if existing.id == item.id:
                self.items[i] = item
                break
        self.storage.update_item(item)
        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_item_deleted(self, item_id: str) -> None:
        """Handle item deleted event."""
        self.items = [item for item in self.items if item.id != item_id]
        self.storage.delete_item(item_id)

        # Also delete votes involving this item
        self.votes = [v for v in self.votes if not v.involves_item(item_id)]
        self.storage.save_votes(self.votes)

        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_vote_submitted(self, vote: Vote) -> None:
        """Handle vote submitted event."""
        self.votes.append(vote)
        self.storage.save_vote(vote)
        self._compute_rankings()
        self._refresh_comparison()
        self._refresh_results()

    def _on_skip_requested(self) -> None:
        """Handle skip requested event - just get next pair."""
        self._refresh_comparison()

    def _on_settings_changed(self, settings: Settings) -> None:
        """Handle settings changed event."""
        self.settings = settings
        self.storage.save_settings(settings)
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

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        # Data is saved incrementally, so just accept the close
        event.accept()
