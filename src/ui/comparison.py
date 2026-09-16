"""Pairwise comparison widget."""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont

from src.models.item import Item
from src.models.vote import Vote, VOTE_WEIGHTS


def _build_preference_buttons() -> list[tuple[str, float, Optional[bool]]]:
    """
    Build the preference button configuration from VOTE_WEIGHTS.

    Returns:
        list[tuple[str, float, Optional[bool]]]: (label, weight, is_for_a)
            tuples ordered strongest-for-A, ..., Equal, ..., strongest-for-B.
            is_for_a is True for A, False for B, and None for Equal.
    """
    strengths = [
        (key.replace("_", " ").title(), weight) for key, weight in VOTE_WEIGHTS.items()
    ]
    a_buttons = [(f"A {label}", weight, True) for label, weight in strengths]
    b_buttons = [(f"B {label}", weight, False) for label, weight in reversed(strengths)]
    return a_buttons + [("Equal", 0.0, None)] + b_buttons


class ItemCard(QFrame):
    """
    Card widget displaying an item's name and description.

    Used in the comparison view to show items side-by-side.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the item card.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the card UI."""
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Name label
        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.name_label.setFont(font)
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        # Description label
        self.description_label = QLabel()
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: gray;")
        layout.addWidget(self.description_label)

        # Identifier label (shown in non-blinded mode)
        self.identifier_label = QLabel()
        self.identifier_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.identifier_label.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(self.identifier_label)

        layout.addStretch()

    def set_item(self, item: Optional[Item], blinded: bool = False) -> None:
        """
        Set the item to display.

        Args:
            item: Item to display, or None to clear.
            blinded: If True, show only identifier and hide description.
        """
        if item:
            if blinded:
                # In blinded mode, show only the identifier
                self.name_label.setText(item.identifier or "(No identifier)")
                self.description_label.setVisible(False)
                self.identifier_label.setVisible(False)
            else:
                # Normal mode: show name, description, and identifier
                self.name_label.setText(item.name)
                self.description_label.setText(item.description or "")
                self.description_label.setVisible(bool(item.description))
                if item.has_identifier():
                    self.identifier_label.setText(f"[{item.identifier}]")
                    self.identifier_label.setVisible(True)
                else:
                    self.identifier_label.setVisible(False)
        else:
            self.name_label.setText("")
            self.description_label.setText("")
            self.description_label.setVisible(False)
            self.identifier_label.setVisible(False)


class ComparisonWidget(QWidget):
    """
    Widget for performing pairwise comparisons.

    Displays two items side-by-side with preference buttons below.

    Signals:
        vote_submitted: Emitted when a vote is submitted (passes Vote object).
        skip_requested: Emitted when skip/equal is clicked.
        undo_requested: Emitted when the undo button is clicked.
    """

    vote_submitted = pyqtSignal(Vote)
    skip_requested = pyqtSignal()
    undo_requested = pyqtSignal()

    # Button configurations: (label, weight, is_for_a), derived from VOTE_WEIGHTS
    # so the model stays the single source of truth for preference strengths.
    # Laid out strongest-for-A ... Equal ... strongest-for-B.
    BUTTONS = _build_preference_buttons()

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the comparison widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._item_a: Optional[Item] = None
        self._item_b: Optional[Item] = None
        self._setup_ui()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        # Status/progress bar
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Items area
        items_layout = QHBoxLayout()

        # Item A
        self.card_a = ItemCard()
        items_layout.addWidget(self.card_a, 1)

        # VS label
        vs_label = QLabel("VS")
        vs_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        vs_label.setFont(font)
        items_layout.addWidget(vs_label)

        # Item B
        self.card_b = ItemCard()
        items_layout.addWidget(self.card_b, 1)

        layout.addLayout(items_layout, 1)

        # Preference buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(5)

        self.preference_buttons: list[QPushButton] = []
        for label, weight, is_for_a in self.BUTTONS:
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumHeight(40)

            btn.clicked.connect(lambda checked, w=weight, a=is_for_a: self._on_button_clicked(w, a))
            buttons_layout.addWidget(btn)
            self.preference_buttons.append(btn)

        layout.addLayout(buttons_layout)

        # Undo row, below the preference buttons
        undo_layout = QHBoxLayout()
        undo_layout.addStretch()
        self.undo_btn = QPushButton("Undo last vote")
        self.undo_btn.setToolTip("Remove the most recent vote and show that pair again")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo_requested.emit)
        undo_layout.addWidget(self.undo_btn)
        undo_layout.addStretch()
        layout.addLayout(undo_layout)

        # Keyboard shortcuts hint
        hint_label = QLabel("Keyboard: 1-7 for buttons, S to skip, Ctrl+Z to undo last vote")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint_label)

    def set_undo_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the undo button.

        Args:
            enabled: True when there is a vote that can be undone.
        """
        self.undo_btn.setEnabled(enabled)

    def set_pair(
        self,
        item_a: Item,
        item_b: Item,
        stats: Optional[dict] = None,
        blinded_mode: bool = False,
    ) -> None:
        """
        Set the pair of items to compare.

        Args:
            item_a: First item.
            item_b: Second item.
            stats: Optional comparison statistics dict.
            blinded_mode: If True, show only identifiers (not names/descriptions).
        """
        self._item_a = item_a
        self._item_b = item_b

        self.card_a.set_item(item_a, blinded=blinded_mode)
        self.card_b.set_item(item_b, blinded=blinded_mode)

        # Update status
        if stats:
            compared = stats.get("compared_pairs", 0)
            total = stats.get("total_possible_pairs", 0)
            votes = stats.get("total_votes", 0)
            self.status_label.setText(
                f"Pairs compared: {compared}/{total} | Total votes: {votes}"
            )
        else:
            self.status_label.setText("")

        # Enable buttons
        for btn in self.preference_buttons:
            btn.setEnabled(True)

        # Grab focus for keyboard shortcuts
        self.setFocus()

    def set_no_items(self, message: str = "Add at least 2 items to start comparing") -> None:
        """
        Display message when there are not enough items to compare.

        Args:
            message: Custom message to display.
        """
        self._item_a = None
        self._item_b = None

        self.card_a.set_item(None)
        self.card_b.set_item(None)

        self.card_a.name_label.setText(message)
        self.status_label.setText("")

        # Disable buttons
        for btn in self.preference_buttons:
            btn.setEnabled(False)

    def _on_button_clicked(self, weight: float, is_for_a: Optional[bool]) -> None:
        """
        Handle preference button click.

        Args:
            weight: Vote weight.
            is_for_a: True if A wins, False if B wins, None for equal/skip.
        """
        if self._item_a is None or self._item_b is None:
            return

        if is_for_a is None:
            # Equal/skip - no vote recorded
            self.skip_requested.emit()
        elif is_for_a:
            # A wins
            vote = Vote(
                winner_id=self._item_a.id,
                loser_id=self._item_b.id,
                weight=weight,
            )
            self.vote_submitted.emit(vote)
        else:
            # B wins
            vote = Vote(
                winner_id=self._item_b.id,
                loser_id=self._item_a.id,
                weight=weight,
            )
            self.vote_submitted.emit(vote)

    def keyPressEvent(self, event) -> None:
        """Handle keyboard shortcuts."""
        key = event.key()

        # Number keys 1-7 for buttons
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_7:
            index = key - Qt.Key.Key_1
            if index < len(self.preference_buttons) and self.preference_buttons[index].isEnabled():
                self.preference_buttons[index].click()
                return

        # S for skip
        if key == Qt.Key.Key_S:
            # Click the "Equal" button (index 3)
            if len(self.preference_buttons) > 3 and self.preference_buttons[3].isEnabled():
                self.preference_buttons[3].click()
                return

        super().keyPressEvent(event)
