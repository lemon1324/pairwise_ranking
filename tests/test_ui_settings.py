"""Unit tests for the desktop's settings widget.

The web accepts any value the model's ranges allow (owner answer 3), so the
desktop's spin boxes must show such a value without raising and must write it
back unchanged (R8 ruling 1). Driven offscreen.
"""

import os
import unittest

from src.models.settings import Settings


class SettingsWidgetTestCase(unittest.TestCase):
    """Starts an offscreen Qt application and builds a widget per test."""

    @classmethod
    def setUpClass(cls):
        """Start an offscreen Qt application, or skip without one."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError as error:  # pragma: no cover - the desktop is a dependency
            raise unittest.SkipTest(f"PyQt6 is not available: {error}")
        cls.qt_app = QApplication.instance() or QApplication([])

    def widget(self):
        """
        Build a settings widget, deleted after the test.

        Returns:
            SettingsWidget: The widget.
        """
        from src.ui.settings import SettingsWidget

        widget = SettingsWidget()
        self.addCleanup(widget.deleteLater)
        return widget


class TestLargeValues(SettingsWidgetTestCase):
    """Values beyond what a spin box holds."""

    def test_a_top_tier_count_of_two_to_the_31_does_not_raise(self):
        """Test that QSpinBox's OverflowError is kept out of set_settings."""
        widget = self.widget()
        widget.set_settings(Settings(top_tier_count=2**31))
        self.assertEqual(widget.top_tier_count_spin.value(), 2**31 - 1)

    def test_a_count_the_web_saved_is_written_back_unchanged(self):
        """Test that a count beyond the box survives a desktop Save untouched."""
        widget = self.widget()
        widget.set_settings(Settings(top_tier_count=3_000_000_000))
        self.assertEqual(widget.get_settings().top_tier_count, 3_000_000_000)

    def test_a_weight_beyond_the_box_is_written_back_unchanged(self):
        """Test that the box's cap does not cut a stored weight."""
        widget = self.widget()
        widget.set_settings(Settings(weight_uncompared=5e7, decay_timescale_days=2e6))
        settings = widget.get_settings()
        self.assertEqual(settings.weight_uncompared, 5e7)
        self.assertEqual(settings.decay_timescale_days, 2e6)

    def test_a_value_finer_than_the_box_is_written_back_unchanged(self):
        """Test that the box's places do not round a stored value."""
        widget = self.widget()
        widget.set_settings(Settings(weight_freshness=0.123456789))
        self.assertEqual(widget.get_settings().weight_freshness, 0.123456789)

    def test_an_edited_box_gives_its_own_value(self):
        """Test that remembering the stored value does not hide an edit."""
        widget = self.widget()
        widget.set_settings(Settings(top_tier_count=3_000_000_000))
        widget.top_tier_count_spin.setValue(12)
        self.assertEqual(widget.get_settings().top_tier_count, 12)


class TestRoundTrip(SettingsWidgetTestCase):
    """Values a person types, held by the boxes themselves."""

    VALUES = Settings(
        weight_uncertainty=0.75,
        weight_connectivity=0.125,
        weight_freshness=7.25,
        weight_uncompared=50.0,
        decay_timescale_days=45.5,
        top_tier_mode=True,
        top_tier_count=5000,
        top_tier_weight=0.125,
        blinded_comparison_mode=True,
        cross_category_rate=0.125,
    )

    def test_set_then_get_round_trips_exactly(self):
        """Test that set_settings then get_settings changes nothing."""
        widget = self.widget()
        widget.set_settings(self.VALUES)
        self.assertEqual(widget.get_settings(), self.VALUES)

    def test_the_boxes_hold_the_values_exactly(self):
        """Test that no box caps or rounds a value the web accepts."""
        widget = self.widget()
        widget.set_settings(self.VALUES)
        self.assertEqual(widget.weight_uncertainty_spin.value(), 0.75)
        self.assertEqual(widget.weight_connectivity_spin.value(), 0.125)
        self.assertEqual(widget.weight_freshness_spin.value(), 7.25)
        self.assertEqual(widget.weight_uncompared_spin.value(), 50.0)
        self.assertEqual(widget.decay_timescale_spin.value(), 45.5)
        self.assertEqual(widget.top_tier_count_spin.value(), 5000)
        self.assertEqual(widget.cross_category_rate_spin.value(), 0.125)

    def test_values_typed_into_the_boxes_are_read_exactly(self):
        """Test that a value set on the box itself is read back unrounded."""
        widget = self.widget()
        widget.set_settings(Settings())
        widget.weight_uncertainty_spin.setValue(0.75)
        widget.weight_connectivity_spin.setValue(0.125)
        widget.weight_freshness_spin.setValue(7.25)
        widget.weight_uncompared_spin.setValue(50.0)
        widget.top_tier_count_spin.setValue(5000)
        widget.cross_category_rate_spin.setValue(0.125)
        settings = widget.get_settings()
        self.assertEqual(settings.weight_uncertainty, 0.75)
        self.assertEqual(settings.weight_connectivity, 0.125)
        self.assertEqual(settings.weight_freshness, 7.25)
        self.assertEqual(settings.weight_uncompared, 50.0)
        self.assertEqual(settings.top_tier_count, 5000)
        self.assertEqual(settings.cross_category_rate, 0.125)

    def test_the_boxes_draw_no_trailing_zeros(self):
        """Test that six places are not drawn as 1.000000."""
        widget = self.widget()
        widget.set_settings(Settings(weight_uncertainty=1.0, weight_connectivity=0.125))
        self.assertEqual(widget.weight_uncertainty_spin.text(), "1.0")
        self.assertEqual(widget.weight_connectivity_spin.text(), "0.125")
        self.assertEqual(widget.decay_timescale_spin.text(), "30.0 days")


if __name__ == "__main__":
    unittest.main()
