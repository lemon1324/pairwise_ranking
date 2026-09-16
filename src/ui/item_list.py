"""Item list management widget."""

from dataclasses import replace
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QDialogButtonBox,
    QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor, QBrush

from src.models.item import Item, DEFAULT_CATEGORY
from src.models.project import active_identifiers, free_slots


# Colour used for retired rows and other de-emphasized text. The stylesheet
# form is derived from it so the module defines one grey, not two.
GREY = QColor(128, 128, 128)
GREY_TEXT = f"color: {GREY.name()};"

# Highlight for an active item that still needs an identifier
NO_IDENTIFIER_BG = QColor(255, 243, 224)  # Light orange
NO_IDENTIFIER_FG = QColor(0, 0, 0)


class ItemDialog(QDialog):
    """
    Dialog for adding, editing, replacing or reactivating an item.

    Attributes:
        name_edit: Text input for item name.
        category_edit: Editable dropdown for the item's category.
        identifier_edit: Input for the item identifier. A plain text field when
            the project defines no slots, otherwise an editable dropdown of the
            slots that are still free.
        description_edit: Text input for item description.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        item: Optional[Item] = None,
        existing_categories: Optional[list[str]] = None,
        taken_identifiers: Optional[set[str]] = None,
        free_slots: Optional[list[str]] = None,
        reactivate: bool = False,
        prefill_identifier: str = "",
        prefill_category: str = "",
        title: Optional[str] = None,
    ):
        """
        Initialize the dialog.

        Args:
            parent: Parent widget.
            item: Existing item to edit, or None for a new item.
            existing_categories: List of existing category names for the dropdown.
            taken_identifiers: Identifiers already held by other active items.
                The dialog refuses to accept one of these.
            free_slots: Slots the project still has free, or None when the
                project defines no slot list (identifiers are then free text).
            reactivate: True when a retired item is being returned to the
                active pool.
            prefill_identifier: Identifier to pre-fill for a new item, used by
                the Replace flow to hand the old item's slot to its successor.
            prefill_category: Category to pre-fill for a new item.
            title: Window title override.
        """
        super().__init__(parent)
        self.item = item
        # The one place the category list is built: the categories already in
        # use plus the default, deduped and sorted.
        self._categories = sorted(
            dict.fromkeys(list(existing_categories or []) + [DEFAULT_CATEGORY])
        )
        self._taken_identifiers = set(taken_identifiers or set())
        self._free_slots = free_slots
        self._reactivate = reactivate
        self._setup_ui()

        if item:
            self.setWindowTitle("Reactivate Item" if reactivate else "Edit Item")
            self.name_edit.setText(item.name)
            self.description_edit.setPlainText(item.description)
            self.category_edit.setCurrentText(item.category)
            if reactivate:
                self._set_identifier("")
            else:
                self._set_identifier(item.identifier)
                if not item.is_active():
                    # A retired item holds no identifier; Reactivate assigns one.
                    self.identifier_edit.setEnabled(False)
                    self.identifier_edit.setToolTip(
                        "Retired items hold no identifier. Use Reactivate to "
                        "return this item to a slot."
                    )
        else:
            self.setWindowTitle("Add Item")
            if prefill_category:
                self.category_edit.setCurrentText(prefill_category)
            if prefill_identifier:
                self._set_identifier(prefill_identifier)

        if title:
            self.setWindowTitle(title)

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Form layout for inputs
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter item name...")
        form.addRow("Name:", self.name_edit)

        self.category_edit = QComboBox()
        self.category_edit.setEditable(True)
        self.category_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.category_edit.setPlaceholderText("Type a new category or pick one")
        self.category_edit.setToolTip(
            "Category for this item. Items are compared within their own category by default.\n"
            "The list is only a suggestion: any text you type is accepted."
        )
        self.category_edit.addItems(self._categories)
        self.category_edit.setCurrentText(DEFAULT_CATEGORY)
        form.addRow("Category (type or pick):", self.category_edit)

        self.identifier_edit = self._create_identifier_widget()
        # The label depends on which widget was built: only the dropdown form
        # needs to tell the user that typing is allowed too.
        identifier_label = (
            "Identifier (type or pick):"
            if isinstance(self.identifier_edit, QComboBox)
            else "Identifier:"
        )
        form.addRow(identifier_label, self.identifier_edit)

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

    def _create_identifier_widget(self) -> QWidget:
        """
        Build the identifier input.

        Returns:
            QWidget: An editable dropdown of the free slots when the project
            defines a slot list, otherwise a plain text field.
        """
        tooltip = (
            "Short label for where this item is kept.\n"
            "Items without an identifier cannot be compared in blinded mode."
        )

        if self._free_slots is None:
            widget = QLineEdit()
            widget.setPlaceholderText(
                "Identifier (e.g. a slot or position label; optional)"
            )
            widget.setToolTip(tooltip)
            return widget

        widget = QComboBox()
        widget.setEditable(True)
        # Enter must never turn the typed text into a row of its own.
        widget.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        widget.setPlaceholderText("Type or pick a slot (optional)")
        widget.setToolTip(
            tooltip
            + "\nThe list shows the slots that are free; it is only a "
            "suggestion, and any text you type is accepted."
        )

        options = list(self._free_slots)
        # When editing, the item keeps its own slot at the top of the list.
        if self.item is not None and self.item.identifier:
            options = [self.item.identifier] + [
                slot for slot in options if slot != self.item.identifier
            ]
        # Only real slots become rows. No row is selected to start with, so an
        # empty edit text means "no identifier" and the placeholder shows.
        widget.addItems(options)
        widget.setCurrentIndex(-1)
        widget.setCurrentText("")
        return widget

    def _identifier_text(self) -> str:
        """
        Return the identifier currently entered.

        Returns:
            str: The stripped identifier text.
        """
        if isinstance(self.identifier_edit, QComboBox):
            return self.identifier_edit.currentText().strip()
        return self.identifier_edit.text().strip()

    def _set_identifier(self, value: str) -> None:
        """
        Write a value into the identifier input.

        Args:
            value: The identifier to display.
        """
        if isinstance(self.identifier_edit, QComboBox):
            self.identifier_edit.setCurrentText(value)
        else:
            self.identifier_edit.setText(value)

    def _validate_and_accept(self) -> None:
        """Validate input and accept dialog if valid."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Item name cannot be empty.")
            self.name_edit.setFocus()
            return

        identifier = self._identifier_text()
        if identifier and identifier in self._taken_identifiers:
            QMessageBox.warning(
                self,
                "Identifier In Use",
                f"The identifier '{identifier}' is already assigned to another "
                "active item.\n\nChoose a different identifier, or retire the "
                "other item first to free it.",
            )
            self.identifier_edit.setFocus()
            return

        self.accept()

    def get_item(self) -> Item:
        """
        Get the item from dialog input.

        Returns:
            Item: New or updated Item instance. Reactivating returns an active
            item with its retirement data cleared.
        """
        name = self.name_edit.text().strip()
        category = self.category_edit.currentText().strip() or DEFAULT_CATEGORY
        identifier = self._identifier_text()
        description = self.description_edit.toPlainText().strip()

        if not self.item:
            # Create new item
            return Item(name=name, identifier=identifier, description=description,
                        category=category)

        # Copy the original, retirement data included, then apply the edits.
        updated = replace(
            self.item, name=name, category=category, description=description
        )

        if self._reactivate:
            updated.reactivate(identifier)
        elif updated.is_active():
            updated.identifier = identifier
        # A retired item that is merely edited keeps its empty identifier.

        return updated


class ItemListWidget(QWidget):
    """
    Widget for managing the list of items.

    The widget owns no data: every action emits a signal and the main window
    applies it to the project and pushes the result back through
    :meth:`set_items`. The table keeps the selected item selected across those
    refreshes.

    Signals:
        item_added: Emitted when a new item is added.
        item_updated: Emitted when an item is updated.
        item_deleted: Emitted when an item is deleted (passes item ID).
        item_retired: Emitted when an item is retired (passes item ID).
        item_replaced: Emitted when an item is replaced (passes the old item's
            ID and the new Item that takes its place).
    """

    item_added = pyqtSignal(Item)
    item_updated = pyqtSignal(Item)
    item_deleted = pyqtSignal(str)
    item_retired = pyqtSignal(str)
    item_replaced = pyqtSignal(str, Item)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the item list widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._items: list[Item] = []
        self._slots: list[str] = []
        self._visible: list[Item] = []
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

        self.retire_btn = QPushButton("Retire")
        self.retire_btn.setToolTip(
            "Retire the selected item: it keeps its votes and history but is "
            "no longer offered for comparison, and its identifier is freed."
        )
        self.retire_btn.clicked.connect(self._on_retire_clicked)
        self.retire_btn.setEnabled(False)
        toolbar.addWidget(self.retire_btn)

        self.replace_btn = QPushButton("Replace...")
        self.replace_btn.setToolTip(
            "Retire the selected item and add a new item in its place, taking "
            "over its identifier."
        )
        self.replace_btn.clicked.connect(self._on_replace_clicked)
        self.replace_btn.setEnabled(False)
        toolbar.addWidget(self.replace_btn)

        self.reactivate_btn = QPushButton("Reactivate")
        self.reactivate_btn.setToolTip(
            "Return the selected retired item to the active pool."
        )
        self.reactivate_btn.clicked.connect(self._on_reactivate_clicked)
        self.reactivate_btn.setEnabled(False)
        toolbar.addWidget(self.reactivate_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        toolbar.addWidget(self.delete_btn)

        toolbar.addStretch()

        self.show_retired_check = QCheckBox("Show retired")
        self.show_retired_check.setToolTip("Include retired items in the table")
        self.show_retired_check.toggled.connect(self._on_show_retired_toggled)
        toolbar.addWidget(self.show_retired_check)

        layout.addLayout(toolbar)

        # Slot usage summary, only shown when the project defines slots
        self.slots_label = QLabel()
        self.slots_label.setStyleSheet(GREY_TEXT)
        self.slots_label.setVisible(False)
        layout.addWidget(self.slots_label)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Category", "Identifier", "Status", "Description"]
        )
        for column in range(4):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_edit_clicked)

        layout.addWidget(self.table)

    def set_items(self, items: list[Item], slots: Optional[list[str]] = None) -> None:
        """
        Set the list of items to display.

        Args:
            items: List of items to display, active and retired.
            slots: The project's slot list, or None/empty when it defines none.
        """
        self._items = list(items)
        self._slots = list(slots or [])
        self._refresh_table()

    def _visible_items(self) -> list[Item]:
        """
        Return the items the table should show.

        Returns:
            list[Item]: All items when retired ones are shown, otherwise the
            active items only.
        """
        if self.show_retired_check.isChecked():
            return list(self._items)
        return [item for item in self._items if item.is_active()]

    def _on_show_retired_toggled(self, checked: bool) -> None:
        """Handle the show-retired checkbox being toggled."""
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table display, keeping the selected item selected."""
        selected = self._get_selected_item()
        selected_id = selected.id if selected else None

        self._visible = self._visible_items()

        # Rebuilding the rows churns the selection; announce it once at the end.
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._visible))

        no_identifier_brush = QBrush(NO_IDENTIFIER_BG)
        no_identifier_text_brush = QBrush(NO_IDENTIFIER_FG)
        grey_brush = QBrush(GREY)

        for row, item in enumerate(self._visible):
            name_item = QTableWidgetItem(item.name)
            name_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.table.setItem(row, 0, name_item)

            category_item = QTableWidgetItem(item.category)
            self.table.setItem(row, 1, category_item)

            # Identifier column
            if item.has_identifier():
                identifier_item = QTableWidgetItem(item.identifier)
            elif item.is_active():
                identifier_item = QTableWidgetItem("(Not assigned)")
                identifier_item.setForeground(grey_brush)
            else:
                identifier_item = QTableWidgetItem("")
            self.table.setItem(row, 2, identifier_item)

            status_item = QTableWidgetItem("Active" if item.is_active() else "Retired")
            self.table.setItem(row, 3, status_item)

            desc_item = QTableWidgetItem(item.description or "")
            self.table.setItem(row, 4, desc_item)

            row_items = [name_item, category_item, identifier_item, status_item, desc_item]

            if not item.is_active():
                # Retired rows are greyed out and never flagged for a missing
                # identifier: retiring an item frees it on purpose.
                for cell in row_items:
                    cell.setForeground(grey_brush)
                if item.retired_at:
                    name_item.setToolTip(
                        f"Retired {item.retired_at.strftime('%Y-%m-%d')}"
                    )
            elif not item.has_identifier():
                for cell in row_items:
                    cell.setBackground(no_identifier_brush)
                    cell.setForeground(no_identifier_text_brush)
                name_item.setToolTip(
                    "This item needs an identifier before it can be compared"
                )

        self._restore_selection(selected_id)
        self.table.blockSignals(False)

        self._refresh_slots_label()
        self._on_selection_changed()

    def _restore_selection(self, item_id: Optional[str]) -> None:
        """
        Re-select a row after the table was rebuilt.

        Args:
            item_id: Id of the item that was selected, or None. Nothing is
                selected when the item is no longer visible.
        """
        if item_id is None:
            return

        for row, item in enumerate(self._visible):
            if item.id == item_id:
                self.table.selectRow(row)
                return

    def _refresh_slots_label(self) -> None:
        """Update the slot usage summary, hiding it when there are no slots."""
        if not self._slots:
            self.slots_label.setVisible(False)
            self.slots_label.setText("")
            return

        free = free_slots(self._slots, self._items)
        used = len(self._slots) - len(free)
        free_text = ", ".join(free) if free else "none free"
        if free:
            free_text = f"free: {free_text}"
        self.slots_label.setText(
            f"Slots: {used} of {len(self._slots)} in use — {free_text}"
        )
        self.slots_label.setVisible(True)

    def _other_items(self, exclude_item_id: Optional[str] = None) -> list[Item]:
        """
        Return the items other than the one being edited or replaced.

        Excluding an item is how its own slot is made to count as free.

        Args:
            exclude_item_id: Id of an item to leave out, or None for all.

        Returns:
            list[Item]: The remaining items.
        """
        if exclude_item_id is None:
            return self._items
        return [item for item in self._items if item.id != exclude_item_id]

    def _dialog_slots(self, exclude_item_id: Optional[str] = None) -> Optional[list[str]]:
        """
        Return the free slot list to hand an ItemDialog.

        Args:
            exclude_item_id: Id of an item whose slot should count as free.

        Returns:
            Optional[list[str]]: The free slots, or None when the project
            defines no slot list and identifiers are free text.
        """
        if not self._slots:
            return None
        return free_slots(self._slots, self._other_items(exclude_item_id))

    def _get_existing_categories(self) -> list[str]:
        """Return sorted list of unique categories currently in use."""
        seen = set()
        result = []
        for item in self._items:
            cat = item.category
            if cat not in seen:
                seen.add(cat)
                result.append(cat)
        return sorted(result)

    def _get_selected_item(self) -> Optional[Item]:
        """Get the currently selected item."""
        rows = self.table.selectedIndexes()
        if not rows:
            return None

        row = rows[0].row()
        if 0 <= row < len(self._visible):
            return self._visible[row]
        return None

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        selected = self._get_selected_item()
        has_selection = selected is not None
        is_active = has_selection and selected.is_active()

        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.retire_btn.setEnabled(is_active)
        self.replace_btn.setEnabled(is_active)
        self.reactivate_btn.setEnabled(has_selection and not is_active)

    def _on_add_clicked(self) -> None:
        """Handle add button click."""
        dialog = ItemDialog(
            self,
            existing_categories=self._get_existing_categories(),
            taken_identifiers=active_identifiers(self._items),
            free_slots=self._dialog_slots(),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # The window owns the project; it pushes the new list back.
            self.item_added.emit(dialog.get_item())

    def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        item = self._get_selected_item()
        if not item:
            return

        dialog = ItemDialog(
            self,
            item,
            existing_categories=self._get_existing_categories(),
            taken_identifiers=active_identifiers(self._other_items(item.id)),
            free_slots=self._dialog_slots(item.id),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_update(dialog.get_item())

    def _on_reactivate_clicked(self) -> None:
        """Handle reactivate button click."""
        item = self._get_selected_item()
        if not item or item.is_active():
            return

        dialog = ItemDialog(
            self,
            item,
            existing_categories=self._get_existing_categories(),
            taken_identifiers=active_identifiers(self._other_items(item.id)),
            free_slots=self._dialog_slots(item.id),
            reactivate=True,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_update(dialog.get_item())

    def _apply_update(self, updated_item: Item) -> None:
        """
        Announce an edited item. The window applies it and pushes the result back.

        Args:
            updated_item: The item as returned by the dialog.
        """
        self.item_updated.emit(updated_item)

    def _on_retire_clicked(self) -> None:
        """Handle retire button click."""
        item = self._get_selected_item()
        if not item or not item.is_active():
            return

        reply = QMessageBox.question(
            self,
            "Confirm Retire",
            f"Retire '{item.name}'?\n\n"
            "Its comparison votes and ranking history are kept, but it will no "
            "longer be offered for comparison.\n"
            "Its identifier is freed so another item can take the slot.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.item_retired.emit(item.id)

    def _on_replace_clicked(self) -> None:
        """Handle replace button click."""
        item = self._get_selected_item()
        if not item or not item.is_active():
            return

        dialog = ItemDialog(
            self,
            existing_categories=self._get_existing_categories(),
            # The item being replaced hands its identifier to its successor,
            # so its own identifier must not count as taken.
            taken_identifiers=active_identifiers(self._other_items(item.id)),
            free_slots=self._dialog_slots(item.id),
            prefill_identifier=item.identifier,
            prefill_category=item.category,
            title=f"Replace {item.name}",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.item_replaced.emit(item.id, dialog.get_item())

    def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        item = self._get_selected_item()
        if not item:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete '{item.name}'?\n\n"
            "This will also delete all comparison votes involving this item.\n"
            "To keep its history instead, retire it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.item_deleted.emit(item.id)
