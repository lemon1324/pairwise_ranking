"""Rankings display widget."""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from src.models.vote import Vote
from src.models.ranking import RankingResult


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

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._on_export_clicked)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # Tree widget for rankings
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Rank", "Name", "ELO Rating", "Comparisons"])
        self.tree.setColumnCount(4)

        # Configure columns
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

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
        self._refresh_tree()

    def set_no_rankings(self) -> None:
        """Display message when there are no rankings."""
        self._rankings = []
        self._votes = []
        self.tree.clear()
        self.summary_label.setText("Add items and perform comparisons to see rankings.")

    def _refresh_tree(self) -> None:
        """Refresh the tree display."""
        self.tree.clear()

        for result in self._rankings:
            # Main item
            item = QTreeWidgetItem([
                str(result.rank),
                result.item.name,
                f"{result.elo_rating:.0f}",
                str(result.comparison_count),
            ])

            # Add details as child items
            details = self._get_item_details(result)
            for detail_key, detail_value in details.items():
                detail_item = QTreeWidgetItem(["", detail_key, detail_value, ""])
                detail_item.setForeground(0, Qt.GlobalColor.gray)
                detail_item.setForeground(1, Qt.GlobalColor.gray)
                detail_item.setForeground(2, Qt.GlobalColor.gray)
                item.addChild(detail_item)

            self.tree.addTopLevelItem(item)

        # Summary
        if self._rankings:
            total_items = len(self._rankings)
            total_votes = len(self._votes)
            self.summary_label.setText(f"{total_items} items | {total_votes} total votes")
        else:
            self.summary_label.setText("")

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

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("Rank,Name,ELO Rating,Comparisons,Description\n")
                for result in self._rankings:
                    # Escape description for CSV
                    desc = result.item.description.replace('"', '""')
                    f.write(f'{result.rank},"{result.item.name}",{result.elo_rating:.0f},'
                            f'{result.comparison_count},"{desc}"\n')

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
