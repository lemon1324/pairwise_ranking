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

from src.models.settings import Settings


SLOTS_HINT = (
    "one slot per line or comma separated; "
    "e.g. positions on a board, shelf labels, or bin numbers"
)


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

        self.decay_timescale_spin = QDoubleSpinBox()
        self.decay_timescale_spin.setRange(0.0, 365.0)
        self.decay_timescale_spin.setSingleStep(1.0)
        self.decay_timescale_spin.setDecimals(1)
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
        self.top_tier_count_spin.setRange(1, 100)
        self.top_tier_count_spin.setToolTip("Number of items considered 'top tier'")
        top_tier_layout.addRow("Top-tier count:", self.top_tier_count_spin)

        self.top_tier_weight_spin = self._create_weight_spin()
        self.top_tier_weight_spin.setToolTip("Additional weight for top-tier comparisons")
        top_tier_layout.addRow("Top-tier weight:", self.top_tier_weight_spin)

        layout.addWidget(top_tier_group)

        # Category Comparison group
        category_group = QGroupBox("Category Comparisons")
        category_layout = QFormLayout(category_group)

        self.cross_category_rate_spin = QDoubleSpinBox()
        self.cross_category_rate_spin.setRange(0.0, 1.0)
        self.cross_category_rate_spin.setSingleStep(0.05)
        self.cross_category_rate_spin.setDecimals(2)
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
        self.slots_edit.setMaximumHeight(120)
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
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 20.0)
        spin.setSingleStep(0.5)
        spin.setDecimals(1)
        return spin

    def set_slots(self, slots: list[str]) -> None:
        """
        Display a project's slot list.

        Args:
            slots: The slot labels, shown one per line.
        """
        self.slots_edit.setPlainText("\n".join(slots))

    def get_slots(self) -> list[str]:
        """
        Read the slot list from the editor.

        Entries may be separated by newlines or commas. Stripping, dropping
        blanks and removing duplicates is left to
        :func:`src.models.project.normalize_slots`, which
        :meth:`src.models.project.Project.set_slots` applies.

        Returns:
            list[str]: The slot labels exactly as entered, split up.
        """
        return [
            part
            for line in self.slots_edit.toPlainText().splitlines()
            for part in line.split(",")
        ]

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
        self.weight_uncertainty_spin.setValue(self._settings.weight_uncertainty)
        self.weight_connectivity_spin.setValue(self._settings.weight_connectivity)
        self.weight_freshness_spin.setValue(self._settings.weight_freshness)
        self.weight_uncompared_spin.setValue(self._settings.weight_uncompared)
        self.decay_timescale_spin.setValue(self._settings.decay_timescale_days)
        self.top_tier_mode_check.setChecked(self._settings.top_tier_mode)
        self.top_tier_count_spin.setValue(self._settings.top_tier_count)
        self.top_tier_weight_spin.setValue(self._settings.top_tier_weight)
        self.blinded_mode_check.setChecked(self._settings.blinded_comparison_mode)
        self.cross_category_rate_spin.setValue(self._settings.cross_category_rate)

        self._on_top_tier_toggled(self._settings.top_tier_mode)

    def _on_top_tier_toggled(self, checked: bool) -> None:
        """Handle top-tier mode checkbox toggle."""
        self.top_tier_count_spin.setEnabled(checked)
        self.top_tier_weight_spin.setEnabled(checked)

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        new_settings = Settings(
            weight_uncertainty=self.weight_uncertainty_spin.value(),
            weight_connectivity=self.weight_connectivity_spin.value(),
            weight_freshness=self.weight_freshness_spin.value(),
            weight_uncompared=self.weight_uncompared_spin.value(),
            decay_timescale_days=self.decay_timescale_spin.value(),
            top_tier_mode=self.top_tier_mode_check.isChecked(),
            top_tier_count=self.top_tier_count_spin.value(),
            top_tier_weight=self.top_tier_weight_spin.value(),
            blinded_comparison_mode=self.blinded_mode_check.isChecked(),
            cross_category_rate=self.cross_category_rate_spin.value(),
        )

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
