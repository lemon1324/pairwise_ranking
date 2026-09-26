"""Settings configuration widget."""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QGroupBox,
    QPlainTextEdit,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont

from src.app.slots import format_slot_list, parse_slot_list
from src.models.settings import Settings


SLOTS_HINT = (
    "one comma-separated line, e.g. A1, A2, B1; "
    "positions on a board, shelf labels, or bin numbers"
)

# The spin boxes' ranges. The model has no upper caps
# (src.models.settings.LIMITS), so these are only the editor's, and generous
# enough that no sane value meets them. The top-tier count's is the largest a
# QSpinBox holds.
WEIGHT_MAX = 1e6
DAYS_MAX = 1e6
COUNT_MAX = 2**31 - 1

# Places a spin box keeps. Enough for any value typed by hand (0.125, 7.25);
# the text drops the trailing zeros, so 1.0 is not drawn as 1.000000.
DECIMALS = 6


class TrimmedDoubleSpinBox(QDoubleSpinBox):
    """A QDoubleSpinBox that keeps many places but draws no trailing zeros."""

    def textFromValue(self, value: float) -> str:
        """
        Write a value without the zeros its places would pad it with.

        Args:
            value: The value.

        Returns:
            str: At least one place: ``1.0``, ``0.125``, ``7.25``.
        """
        text = super().textFromValue(value)
        point = self.locale().decimalPoint()
        if point in text:
            text = text.rstrip("0")
            if text.endswith(point):
                text += "0"
        return text


class SettingsWidget(QWidget):
    """
    Widget for configuring application settings.

    Allows adjustment of pair selection algorithm weights and other parameters.

    The slot list is not a signal of its own: Save Settings emits
    settings_changed and the main window reads the slots back with
    :meth:`get_slots`, so one click means one save.

    Signals:
        settings_changed: Emitted when settings are saved (passes Settings object).
    """

    settings_changed = pyqtSignal(Settings)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the settings widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._settings: Settings = Settings()
        # Per spin box, the value it was given and the value it then showed,
        # so an untouched box writes back exactly what the file holds.
        self._given: dict = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Algorithm Settings")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        title_label.setFont(font)
        layout.addWidget(title_label)

        # Pair Selection Weights group
        weights_group = QGroupBox("Pair Selection Weights")
        weights_layout = QFormLayout(weights_group)

        self.weight_uncertainty_spin = self._create_weight_spin()
        weights_layout.addRow("Uncertainty (close ratings):", self.weight_uncertainty_spin)

        self.weight_connectivity_spin = self._create_weight_spin()
        weights_layout.addRow("Connectivity (join components):", self.weight_connectivity_spin)

        self.weight_freshness_spin = self._create_weight_spin()
        weights_layout.addRow("Freshness (refresh old votes):", self.weight_freshness_spin)

        self.weight_uncompared_spin = self._create_weight_spin()
        weights_layout.addRow("Uncompared (new items/pairs):", self.weight_uncompared_spin)

        layout.addWidget(weights_group)

        # Vote Decay group
        decay_group = QGroupBox("Vote Decay")
        decay_layout = QFormLayout(decay_group)

        self.decay_timescale_spin = TrimmedDoubleSpinBox()
        self.decay_timescale_spin.setDecimals(DECIMALS)
        self.decay_timescale_spin.setRange(0.0, DAYS_MAX)
        self.decay_timescale_spin.setSingleStep(1.0)
        self.decay_timescale_spin.setSuffix(" days")
        self.decay_timescale_spin.setToolTip(
            "Half-life for vote decay. After this many days, a vote's weight is halved.\n"
            "Set to 0 to disable decay."
        )
        decay_layout.addRow("Decay half-life:", self.decay_timescale_spin)

        layout.addWidget(decay_group)

        # Top-Tier Mode group
        top_tier_group = QGroupBox("Top-Tier Focus Mode")
        top_tier_layout = QFormLayout(top_tier_group)

        self.top_tier_mode_check = QCheckBox("Enable top-tier mode")
        self.top_tier_mode_check.setToolTip(
            "When enabled, prioritizes comparisons involving top-ranked items\n"
            "or items that could potentially rise to the top tier."
        )
        self.top_tier_mode_check.toggled.connect(self._on_top_tier_toggled)
        top_tier_layout.addRow(self.top_tier_mode_check)

        self.top_tier_count_spin = QSpinBox()
        self.top_tier_count_spin.setRange(1, COUNT_MAX)
        self.top_tier_count_spin.setToolTip("Number of items considered 'top tier'")
        top_tier_layout.addRow("Top-tier count:", self.top_tier_count_spin)

        self.top_tier_weight_spin = self._create_weight_spin()
        self.top_tier_weight_spin.setToolTip("Additional weight for top-tier comparisons")
        top_tier_layout.addRow("Top-tier weight:", self.top_tier_weight_spin)

        layout.addWidget(top_tier_group)

        # Category Comparison group
        category_group = QGroupBox("Category Comparisons")
        category_layout = QFormLayout(category_group)

        self.cross_category_rate_spin = TrimmedDoubleSpinBox()
        self.cross_category_rate_spin.setDecimals(DECIMALS)
        self.cross_category_rate_spin.setRange(0.0, 1.0)
        self.cross_category_rate_spin.setSingleStep(0.05)
        self.cross_category_rate_spin.setToolTip(
            "Fraction of comparisons that cross category boundaries.\n"
            "Cross-category votes calibrate ELO so ratings are comparable across categories\n"
            "(e.g. a 1700 in one category means about the same as a 1700 in another).\n"
            "0.0 = always compare within the same category.\n"
            "1.0 = ignore categories entirely."
        )
        category_layout.addRow("Cross-category rate:", self.cross_category_rate_spin)

        layout.addWidget(category_group)

        # Blinded Comparison Mode group
        blinded_group = QGroupBox("Comparison Mode")
        blinded_layout = QFormLayout(blinded_group)

        self.blinded_mode_check = QCheckBox("Blinded comparison mode")
        self.blinded_mode_check.setToolTip(
            "When enabled, the comparison panel shows only the item's\n"
            "identifier instead of its name and description.\n"
            "This helps reduce bias during comparisons.\n\n"
            "Note: Items without an identifier cannot be compared\n"
            "when blinded mode is enabled."
        )
        blinded_layout.addRow(self.blinded_mode_check)

        layout.addWidget(blinded_group)

        # Slots group
        slots_group = QGroupBox("Slots")
        slots_layout = QVBoxLayout(slots_group)

        slots_help = QLabel(
            "Optional list of the positions this project has room for. When "
            "set, an item's identifier is chosen from the free slots."
        )
        slots_help.setWordWrap(True)
        slots_help.setStyleSheet("color: gray;")
        slots_layout.addWidget(slots_help)

        self.slots_edit = QPlainTextEdit()
        self.slots_edit.setPlaceholderText(SLOTS_HINT)
        self.slots_edit.setToolTip(SLOTS_HINT)
        # One comma-separated line, so the box only has to hold a couple of
        # wrapped lines rather than a column of names.
        self.slots_edit.setMaximumHeight(72)
        slots_layout.addWidget(self.slots_edit)

        layout.addWidget(slots_group)

        layout.addStretch()

        # Buttons
        buttons_layout = QHBoxLayout()

        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        buttons_layout.addWidget(self.reset_btn)

        buttons_layout.addStretch()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.clicked.connect(self._on_save_clicked)
        buttons_layout.addWidget(self.save_btn)

        layout.addLayout(buttons_layout)

    def _create_weight_spin(self) -> QDoubleSpinBox:
        """
        Create a spin box for weight values.

        Returns:
            QDoubleSpinBox: Configured spin box.
        """
        spin = TrimmedDoubleSpinBox()
        spin.setDecimals(DECIMALS)
        spin.setRange(0.0, WEIGHT_MAX)
        spin.setSingleStep(0.5)
        return spin

    def _spins(self) -> dict:
        """
        Pair each numeric setting with the spin box that edits it.

        Returns:
            dict: Setting name to its spin box.
        """
        return {
            "weight_uncertainty": self.weight_uncertainty_spin,
            "weight_connectivity": self.weight_connectivity_spin,
            "weight_freshness": self.weight_freshness_spin,
            "weight_uncompared": self.weight_uncompared_spin,
            "decay_timescale_days": self.decay_timescale_spin,
            "top_tier_count": self.top_tier_count_spin,
            "top_tier_weight": self.top_tier_weight_spin,
            "cross_category_rate": self.cross_category_rate_spin,
        }

    def _show_value(self, name: str, spin, value) -> None:
        """
        Put a stored value in its spin box, clamped into the box's range.

        A QSpinBox raises OverflowError for a value of 2**31 or more, and any
        box silently cuts a value to its range and places; the clamp keeps the
        first from happening, and remembering the value lets
        :meth:`get_settings` undo the second for a box nobody edited.

        Args:
            name: The setting's name.
            spin: Its spin box.
            value: The stored value.
        """
        shown = min(max(value, spin.minimum()), spin.maximum())
        if isinstance(spin, QSpinBox):
            shown = int(shown)
        spin.setValue(shown)
        self._given[name] = (value, spin.value())

    def _read_value(self, name: str, spin):
        """
        Read a spin box back as the setting it edits.

        Args:
            name: The setting's name.
            spin: Its spin box.

        Returns:
            The box's value, or the stored value exactly when the box still
            shows what it was given.
        """
        value = spin.value()
        given = self._given.get(name)
        if given is not None and value == given[1]:
            return given[0]
        return value

    def set_slots(self, slots: list[str]) -> None:
        """
        Display a project's slot list.

        Args:
            slots: The slot labels, shown as one comma-separated line.
        """
        self.slots_edit.setPlainText(format_slot_list(slots))

    def get_slots(self) -> list[str]:
        """
        Read the slot list from the editor.

        Entries are separated by commas; newlines are accepted too, so a
        pasted column of names still works. Stripping, dropping blanks and
        removing duplicates is left to
        :func:`src.models.project.normalize_slots`, which
        :meth:`src.models.project.Project.set_slots` applies.

        Returns:
            list[str]: The slot labels exactly as entered, split up.
        """
        return parse_slot_list(self.slots_edit.toPlainText())

    def set_settings(self, settings: Settings) -> None:
        """
        Set the settings to display/edit.

        Args:
            settings: Settings to display.
        """
        self._settings = settings
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        """Refresh UI from current settings."""
        for name, spin in self._spins().items():
            self._show_value(name, spin, getattr(self._settings, name))
        self.top_tier_mode_check.setChecked(self._settings.top_tier_mode)
        self.blinded_mode_check.setChecked(self._settings.blinded_comparison_mode)

        self._on_top_tier_toggled(self._settings.top_tier_mode)

    def get_settings(self) -> Settings:
        """
        Read the settings as the widget holds them.

        Returns:
            Settings: The edited values. A spin box nobody changed gives back
            the value it was set with, exactly, even one beyond its range or
            places.
        """
        values = {name: self._read_value(name, spin) for name, spin in self._spins().items()}
        return Settings(
            top_tier_mode=self.top_tier_mode_check.isChecked(),
            blinded_comparison_mode=self.blinded_mode_check.isChecked(),
            **values,
        )

    def _on_top_tier_toggled(self, checked: bool) -> None:
        """Handle top-tier mode checkbox toggle."""
        self.top_tier_count_spin.setEnabled(checked)
        self.top_tier_weight_spin.setEnabled(checked)

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        new_settings = self.get_settings()

        self._settings = new_settings
        self.settings_changed.emit(new_settings)

        QMessageBox.information(self, "Settings Saved", "Settings have been saved.")

    def _on_reset_clicked(self) -> None:
        """Handle reset button click."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Reset all settings to default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # The slot list describes the project, not the algorithm, so a
            # reset to defaults deliberately leaves it alone.
            self._settings = Settings()
            self._refresh_ui()
