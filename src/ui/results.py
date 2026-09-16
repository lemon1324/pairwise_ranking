"""Rankings display widget."""

import csv
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QComboBox,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from src.models.vote import Vote
from src.models.export import build_export_rows
from src.models.ranking import RankingResult


# Category filter entry meaning "do not filter"
ALL_CATEGORIES = "All"

# Colour used for retired rows and other de-emphasized text in this module
GREY = Qt.GlobalColor.gray


class ResultsWidget(QWidget):
    """
    Widget for displaying ranking results.

    Shows a ranked list with ELO scores and expandable details.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the results widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._rankings: list[RankingResult] = []
        self._votes: list[Vote] = []
        self._selected_category: str = ALL_CATEGORIES
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()

        self.title_label = QLabel("Rankings")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.title_label.setFont(font)
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        self.category_filter = QComboBox()
        self.category_filter.addItem(ALL_CATEGORIES)
        self.category_filter.setToolTip("Filter rankings by category")
        self.category_filter.currentTextChanged.connect(self._on_category_filter_changed)
        header_layout.addWidget(QLabel("Category:"))
        header_layout.addWidget(self.category_filter)

        self.show_retired_check = QCheckBox("Show retired")
        self.show_retired_check.setToolTip(
            "Include retired items. They keep their rating but are not ranked."
        )
        self.show_retired_check.toggled.connect(self._on_show_retired_toggled)
        header_layout.addWidget(self.show_retired_check)

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._on_export_clicked)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # Tree widget for rankings
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Rank", "Name", "Category", "ELO Rating", "Comparisons"])
        self.tree.setColumnCount(5)

        # Configure columns
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)  # Show expand arrows

        layout.addWidget(self.tree)

        # Summary label
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("color: gray;")
        layout.addWidget(self.summary_label)

    def set_rankings(self, rankings: list[RankingResult], votes: list[Vote]) -> None:
        """
        Set the rankings to display.

        Args:
            rankings: List of ranking results.
            votes: List of all votes (for detail view).
        """
        self._rankings = rankings
        self._votes = votes
        self._refresh_category_filter()
        self._refresh_tree()

    def _in_scope(self) -> list[RankingResult]:
        """
        Return the results the lifecycle filter lets through.

        Returns:
            list[RankingResult]: All results when retired items are shown,
            otherwise the active ones only.
        """
        if self.show_retired_check.isChecked():
            return list(self._rankings)
        return [r for r in self._rankings if r.item.is_active()]

    def _on_show_retired_toggled(self, checked: bool) -> None:
        """Handle the show-retired checkbox being toggled."""
        self._refresh_category_filter()
        self._refresh_tree()

    def _refresh_category_filter(self) -> None:
        """Rebuild the category filter dropdown from the visible results."""
        categories = sorted({r.item.category for r in self._in_scope()})
        current = self._selected_category

        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(ALL_CATEGORIES)
        for cat in categories:
            self.category_filter.addItem(cat)

        # Restore previous selection if still valid, otherwise fall back to All
        idx = self.category_filter.findText(current)
        self.category_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self._selected_category = self.category_filter.currentText()
        self.category_filter.blockSignals(False)

    def _on_category_filter_changed(self, category: str) -> None:
        """Handle category filter change."""
        self._selected_category = category
        self._refresh_tree()

    def set_no_rankings(self) -> None:
        """Display message when there are no rankings."""
        self._rankings = []
        self._votes = []
        self._selected_category = ALL_CATEGORIES
        self._refresh_category_filter()
        self.tree.clear()
        self.summary_label.setText("Add items and perform comparisons to see rankings.")

    def _refresh_tree(self) -> None:
        """Refresh the tree display."""
        self.tree.clear()

        in_scope = self._in_scope()

        # Apply category filter
        filtering_category = (
            bool(self._selected_category) and self._selected_category != ALL_CATEGORIES
        )
        if filtering_category:
            visible = [r for r in in_scope if r.item.category == self._selected_category]
        else:
            visible = in_scope

        for result in visible:
            is_active = result.item.is_active()
            name = result.item.name if is_active else f"{result.item.name} (retired)"

            # Main item; retired items are not numbered
            item = QTreeWidgetItem([
                "" if result.rank is None else str(result.rank),
                name,
                result.item.category,
                f"{result.elo_rating:.0f}",
                str(result.comparison_count),
            ])

            if not is_active:
                for col in range(5):
                    item.setForeground(col, GREY)

            # Add details as child items
            details = self._get_item_details(result)
            for detail_key, detail_value in details.items():
                detail_item = QTreeWidgetItem(["", detail_key, "", detail_value, ""])
                for col in range(5):
                    detail_item.setForeground(col, GREY)
                item.addChild(detail_item)

            self.tree.addTopLevelItem(item)

        self.summary_label.setText(self._summary_text(visible, filtering_category))

    def _summary_text(
        self,
        visible: list[RankingResult],
        filtering_category: bool,
    ) -> str:
        """
        Build the summary line under the rankings tree.

        Args:
            visible: The results currently shown.
            filtering_category: Whether a category filter is active.

        Returns:
            str: The summary text, empty when there is nothing to summarize.
        """
        if not self._rankings:
            return ""

        if filtering_category:
            scoped = [
                r for r in self._rankings
                if r.item.category == self._selected_category
            ]
            scope_suffix = f" (category: {self._selected_category})"
        else:
            scoped = self._rankings
            scope_suffix = ""

        active_shown = sum(1 for r in visible if r.item.is_active())
        retired_shown = len(visible) - active_shown
        retired_hidden = sum(1 for r in scoped if not r.item.is_active()) - retired_shown

        parts = [f"{active_shown} active items{scope_suffix}"]
        if retired_shown:
            parts.append(f"{retired_shown} retired shown")
        if retired_hidden:
            parts.append(f"{retired_hidden} retired hidden")

        return f"{', '.join(parts)} | {len(self._votes)} total votes"

    def _get_item_details(self, result: RankingResult) -> dict[str, str]:
        """
        Get detailed information for a ranking result.

        Args:
            result: The ranking result.

        Returns:
            dict: Detail key-value pairs.
        """
        details = {}

        # Description
        if result.item.description:
            details["Description"] = result.item.description

        # Strength (raw Bradley-Terry parameter)
        details["Strength"] = f"{result.strength:.4f}"

        # Log-strength
        details["Log-Strength"] = f"{result.log_strength:.4f}"

        # Standard error of log-strength (uncertainty)
        details["Uncertainty (SE)"] = f"{result.log_strength_se:.4f}"

        # Win/loss record against each opponent
        item_id = result.item.id
        wins = {}
        losses = {}

        for vote in self._votes:
            if vote.winner_id == item_id:
                loser_name = self._get_item_name(vote.loser_id)
                wins[loser_name] = wins.get(loser_name, 0) + vote.weight
            elif vote.loser_id == item_id:
                winner_name = self._get_item_name(vote.winner_id)
                losses[winner_name] = losses.get(winner_name, 0) + vote.weight

        if wins:
            win_str = ", ".join(f"{name}: {w:.1f}" for name, w in sorted(wins.items()))
            details["Wins (weighted)"] = win_str

        if losses:
            loss_str = ", ".join(f"{name}: {l:.1f}" for name, l in sorted(losses.items()))
            details["Losses (weighted)"] = loss_str

        return details

    def _get_item_name(self, item_id: str) -> str:
        """
        Get item name by ID.

        Args:
            item_id: The item ID.

        Returns:
            str: Item name or "Unknown" if not found.
        """
        for result in self._rankings:
            if result.item.id == item_id:
                return result.item.name
        return "Unknown"

    def _on_export_clicked(self) -> None:
        """Handle export button click."""
        if not self._rankings:
            QMessageBox.information(self, "Export", "No rankings to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Rankings",
            "rankings.csv",
            "CSV Files (*.csv);;All Files (*)",
        )

        if not file_path:
            return

        # The export mirrors what the Rankings tab currently shows.
        category = (
            self._selected_category
            if self._selected_category and self._selected_category != ALL_CATEGORIES
            else None
        )
        rows = build_export_rows(
            self._rankings,
            include_retired=self.show_retired_check.isChecked(),
            category=category,
        )

        try:
            with open(file_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)

            QMessageBox.information(
                self,
                "Export Successful",
                f"Rankings exported to:\n{file_path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export rankings:\n{str(e)}",
            )
