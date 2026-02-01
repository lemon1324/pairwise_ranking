"""Item list management widget."""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QDialogButtonBox,
    QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor, QBrush

from src.models.item import Item


class ItemDialog(QDialog):
    """
    Dialog for adding or editing an item.

    Attributes:
        name_edit: Text input for item name.
        identifier_edit: Text input for item identifier (storage location).
        description_edit: Text input for item description.
    """

    def __init__(self, parent: Optional[QWidget] = None, item: Optional[Item] = None):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            item: Existing item to edit, or None for new item.
        """
        super().__init__(parent)
        self.item = item
        self._setup_ui()

        if item:
            self.setWindowTitle("Edit Item")
            self.name_edit.setText(item.name)
            self.identifier_edit.setText(item.identifier)
            self.description_edit.setPlainText(item.description)
        else:
            self.setWindowTitle("Add Item")

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Form layout for inputs
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter item name...")
        form.addRow("Name:", self.name_edit)

        self.identifier_edit = QLineEdit()
        self.identifier_edit.setPlaceholderText("Enter storage location (optional)...")
        self.identifier_edit.setToolTip(
            "Physical storage location identifier.\n"
            "Items without an identifier cannot be compared in blinded mode."
        )
        form.addRow("Identifier:", self.identifier_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Enter description (optional)...")
        self.description_edit.setMaximumHeight(100)
        form.addRow("Description:", self.description_edit)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        """Validate input and accept dialog if valid."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Item name cannot be empty.")
            self.name_edit.setFocus()
            return
        self.accept()

    def get_item(self) -> Item:
        """
        Get the item from dialog input.

        Returns:
            Item: New or updated Item instance.
        """
        name = self.name_edit.text().strip()
        identifier = self.identifier_edit.text().strip()
        description = self.description_edit.toPlainText().strip()

        if self.item:
            # Update existing item
            return Item(name=name, identifier=identifier, description=description, id=self.item.id)
        else:
            # Create new item
            return Item(name=name, identifier=identifier, description=description)


class ItemListWidget(QWidget):
    """
    Widget for managing the list of items.

    Signals:
        item_added: Emitted when a new item is added.
        item_updated: Emitted when an item is updated.
        item_deleted: Emitted when an item is deleted (passes item ID).
    """

    item_added = pyqtSignal(Item)
    item_updated = pyqtSignal(Item)
    item_deleted = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the item list widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._items: list[Item] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()

        self.add_btn = QPushButton("Add Item")
        self.add_btn.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        self.edit_btn.setEnabled(False)
        toolbar.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        toolbar.addWidget(self.delete_btn)

        toolbar.addStretch()

        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Identifier", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_edit_clicked)

        layout.addWidget(self.table)

    def set_items(self, items: list[Item]) -> None:
        """
        Set the list of items to display.

        Args:
            items: List of items to display.
        """
        self._items = list(items)
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table display."""
        self.table.setRowCount(len(self._items))

        # Highlight color for items without identifier
        no_identifier_brush = QBrush(QColor(255, 243, 224))  # Light orange

        for row, item in enumerate(self._items):
            name_item = QTableWidgetItem(item.name)
            name_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.table.setItem(row, 0, name_item)

            # Identifier column
            if item.has_identifier():
                identifier_item = QTableWidgetItem(item.identifier)
            else:
                identifier_item = QTableWidgetItem("(Not assigned)")
                identifier_item.setForeground(QBrush(QColor(128, 128, 128)))
            self.table.setItem(row, 1, identifier_item)

            desc_item = QTableWidgetItem(item.description or "")
            self.table.setItem(row, 2, desc_item)

            # Highlight row if no identifier
            if not item.has_identifier():
                dark_text_brush = QBrush(QColor(0, 0, 0))
                name_item.setBackground(no_identifier_brush)
                name_item.setForeground(dark_text_brush)
                identifier_item.setBackground(no_identifier_brush)
                identifier_item.setForeground(dark_text_brush)
                desc_item.setBackground(no_identifier_brush)
                desc_item.setForeground(dark_text_brush)
                name_item.setToolTip("This item needs a location identifier before it can be compared")

        self._on_selection_changed()

    def _get_selected_item(self) -> Optional[Item]:
        """Get the currently selected item."""
        rows = self.table.selectedIndexes()
        if not rows:
            return None

        row = rows[0].row()
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        has_selection = self._get_selected_item() is not None
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _on_add_clicked(self) -> None:
        """Handle add button click."""
        dialog = ItemDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            item = dialog.get_item()
            self._items.append(item)
            self._refresh_table()
            self.item_added.emit(item)

    def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        item = self._get_selected_item()
        if not item:
            return

        dialog = ItemDialog(self, item)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_item = dialog.get_item()

            # Update local list
            for i, existing in enumerate(self._items):
                if existing.id == updated_item.id:
                    self._items[i] = updated_item
                    break

            self._refresh_table()
            self.item_updated.emit(updated_item)

    def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        item = self._get_selected_item()
        if not item:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete '{item.name}'?\n\n"
            "This will also delete all comparison votes involving this item.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._items = [i for i in self._items if i.id != item.id]
            self._refresh_table()
            self.item_deleted.emit(item.id)
