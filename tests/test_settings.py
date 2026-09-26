"""Unit tests for the Settings model."""

import math
import unittest
from src.models.settings import LIMITS, Settings


class TestSettings(unittest.TestCase):
    """Test cases for the Settings dataclass."""

    def test_default_settings(self):
        """Test that default settings have expected values."""
        settings = Settings()
        self.assertEqual(settings.weight_uncertainty, 1.0)
        self.assertEqual(settings.weight_connectivity, 1.0)
        self.assertEqual(settings.weight_freshness, 0.5)
        self.assertEqual(settings.weight_uncompared, 2.0)
        self.assertEqual(settings.decay_timescale_days, 30.0)
        self.assertFalse(settings.top_tier_mode)
        self.assertEqual(settings.top_tier_count, 10)
        self.assertEqual(settings.top_tier_weight, 2.0)
        self.assertFalse(settings.blinded_comparison_mode)

    def test_custom_settings(self):
        """Test creating settings with custom values."""
        settings = Settings(
            weight_uncertainty=2.0,
            top_tier_mode=True,
            top_tier_count=5,
        )
        self.assertEqual(settings.weight_uncertainty, 2.0)
        self.assertTrue(settings.top_tier_mode)
        self.assertEqual(settings.top_tier_count, 5)

    def test_blinded_comparison_mode(self):
        """Test creating settings with blinded comparison mode enabled."""
        settings = Settings(blinded_comparison_mode=True)
        self.assertTrue(settings.blinded_comparison_mode)

    def test_to_dict(self):
        """Test converting settings to dictionary."""
        settings = Settings(weight_uncertainty=1.5, top_tier_mode=True, blinded_comparison_mode=True)
        result = settings.to_dict()

        self.assertEqual(result["weight_uncertainty"], 1.5)
        self.assertTrue(result["top_tier_mode"])
        self.assertTrue(result["blinded_comparison_mode"])
        self.assertIn("decay_timescale_days", result)

    def test_from_dict_full(self):
        """Test creating settings from complete dictionary."""
        data = {
            "weight_uncertainty": 2.0,
            "weight_connectivity": 1.5,
            "weight_freshness": 0.8,
            "weight_uncompared": 3.0,
            "decay_timescale_days": 60.0,
            "top_tier_mode": True,
            "top_tier_count": 15,
            "top_tier_weight": 2.5,
            "blinded_comparison_mode": True,
        }
        settings = Settings.from_dict(data)

        self.assertEqual(settings.weight_uncertainty, 2.0)
        self.assertEqual(settings.weight_connectivity, 1.5)
        self.assertEqual(settings.decay_timescale_days, 60.0)
        self.assertTrue(settings.top_tier_mode)
        self.assertEqual(settings.top_tier_count, 15)
        self.assertTrue(settings.blinded_comparison_mode)

    def test_from_dict_partial(self):
        """Test creating settings from partial dictionary uses defaults."""
        data = {"weight_uncertainty": 2.0}
        settings = Settings.from_dict(data)

        self.assertEqual(settings.weight_uncertainty, 2.0)
        self.assertEqual(settings.weight_connectivity, 1.0)  # default
        self.assertEqual(settings.decay_timescale_days, 30.0)  # default

    def test_from_dict_empty(self):
        """Test creating settings from empty dictionary uses all defaults."""
        settings = Settings.from_dict({})
        default = Settings()

        self.assertEqual(settings.weight_uncertainty, default.weight_uncertainty)
        self.assertEqual(settings.top_tier_mode, default.top_tier_mode)

    def test_roundtrip_dict_conversion(self):
        """Test that to_dict and from_dict are inverses."""
        original = Settings(
            weight_uncertainty=2.5,
            top_tier_mode=True,
            decay_timescale_days=45.0,
        )
        data = original.to_dict()
        restored = Settings.from_dict(data)

        self.assertEqual(original.weight_uncertainty, restored.weight_uncertainty)
        self.assertEqual(original.top_tier_mode, restored.top_tier_mode)
        self.assertEqual(original.decay_timescale_days, restored.decay_timescale_days)

    def test_cross_category_rate_default(self):
        """Test that cross_category_rate defaults to 0.1."""
        settings = Settings()
        self.assertEqual(settings.cross_category_rate, 0.1)

    def test_cross_category_rate_roundtrip(self):
        """Test that cross_category_rate survives to_dict/from_dict round-trip."""
        original = Settings(cross_category_rate=0.35)
        data = original.to_dict()
        self.assertEqual(data["cross_category_rate"], 0.35)

        restored = Settings.from_dict(data)
        self.assertEqual(restored.cross_category_rate, 0.35)

    def test_cross_category_rate_from_dict_partial(self):
        """Test that from_dict without cross_category_rate uses the default."""
        settings = Settings.from_dict({"weight_uncertainty": 2.0})
        self.assertEqual(settings.cross_category_rate, 0.1)

        settings = Settings.from_dict({"cross_category_rate": 0.75})
        self.assertEqual(settings.cross_category_rate, 0.75)


class TestSettingsValidation(unittest.TestCase):
    """Test cases for the sanity ranges: nothing negative, a rate, a count."""

    def test_defaults_are_valid(self):
        """Test that the defaults pass their own validation."""
        self.assertEqual(Settings().invalid_fields(), [])
        Settings().validate()

    def test_limits_cover_every_numeric_setting(self):
        """Test that every setting but the two switches has a range."""
        numeric = {
            name for name, value in Settings().to_dict().items() if not isinstance(value, bool)
        }
        self.assertEqual(set(LIMITS), numeric)

    def test_negative_values_are_refused(self):
        """Test that no weight, half-life or rate may be negative."""
        for name in LIMITS:
            with self.subTest(name=name):
                settings = Settings(**{name: -1})
                self.assertEqual(settings.invalid_fields(), [name])
                with self.assertRaises(ValueError) as caught:
                    settings.validate()
                self.assertIn(name, str(caught.exception))

    def test_zero_is_allowed_for_weights_and_half_life(self):
        """Test that 0 is the floor, and a half-life of 0 (no decay) is valid."""
        settings = Settings(
            weight_uncertainty=0.0,
            weight_connectivity=0,
            weight_freshness=0.0,
            weight_uncompared=0.0,
            decay_timescale_days=0.0,
            top_tier_weight=0.0,
            cross_category_rate=0.0,
        )
        self.assertEqual(settings.invalid_fields(), [])

    def test_no_upper_caps_except_the_rate(self):
        """Test that large weights, half-lives and counts are allowed."""
        settings = Settings(
            weight_uncertainty=500.0, decay_timescale_days=10000.0, top_tier_count=5000
        )
        self.assertEqual(settings.invalid_fields(), [])

    def test_cross_category_rate_is_between_zero_and_one(self):
        """Test the rate's two bounds, inclusive."""
        self.assertEqual(Settings(cross_category_rate=1.0).invalid_fields(), [])
        self.assertEqual(
            Settings(cross_category_rate=1.01).invalid_fields(), ["cross_category_rate"]
        )

    def test_top_tier_count_is_a_whole_number_of_at_least_one(self):
        """Test that the count refuses 0 and fractions but takes a whole float."""
        self.assertEqual(Settings(top_tier_count=0).invalid_fields(), ["top_tier_count"])
        self.assertEqual(Settings(top_tier_count=2.5).invalid_fields(), ["top_tier_count"])
        self.assertEqual(Settings(top_tier_count=1).invalid_fields(), [])
        self.assertEqual(Settings(top_tier_count=3.0).invalid_fields(), [])

    def test_values_that_are_not_numbers_are_refused(self):
        """Test that NaN, infinities, booleans and text fail the range check."""
        for value in (math.nan, math.inf, -math.inf, True, "1"):
            with self.subTest(value=value):
                self.assertEqual(
                    Settings(weight_freshness=value).invalid_fields(), ["weight_freshness"]
                )

    def test_every_bad_field_is_named(self):
        """Test that validation reports all the fields, in order."""
        settings = Settings(weight_uncertainty=-1.0, cross_category_rate=2.0)
        self.assertEqual(
            settings.invalid_fields(), ["weight_uncertainty", "cross_category_rate"]
        )


class TestSettingsLoadedOutOfRange(unittest.TestCase):
    """Test cases for a file that holds an out-of-range value: clamped, not refused."""

    def load(self, data: dict) -> Settings:
        """
        Load settings, capturing the warning the clamp logs.

        Args:
            data: The settings dictionary.

        Returns:
            Settings: The loaded settings.
        """
        with self.assertLogs("src.models.settings", level="WARNING"):
            return Settings.from_dict(data)

    def test_negative_values_become_zero(self):
        """Test that a negative weight or half-life is raised to 0."""
        settings = self.load({"weight_freshness": -2.0, "decay_timescale_days": -5})
        self.assertEqual(settings.weight_freshness, 0.0)
        self.assertEqual(settings.decay_timescale_days, 0.0)

    def test_the_rate_is_clamped_to_its_bounds(self):
        """Test that a rate above 1 or below 0 is brought to the bound."""
        self.assertEqual(self.load({"cross_category_rate": 1.5}).cross_category_rate, 1.0)
        self.assertEqual(self.load({"cross_category_rate": -0.5}).cross_category_rate, 0.0)

    def test_the_top_tier_count_becomes_a_whole_number_of_at_least_one(self):
        """Test that 0 becomes 1 and a fraction is cut to a whole number."""
        self.assertEqual(self.load({"top_tier_count": 0}).top_tier_count, 1)
        count = self.load({"top_tier_count": 4.5}).top_tier_count
        self.assertEqual(count, 4)
        self.assertIsInstance(count, int)

    def test_values_that_are_no_number_become_the_default(self):
        """Test that NaN and infinities read as the default."""
        settings = self.load(
            {"weight_uncertainty": math.nan, "top_tier_count": math.inf, "top_tier_weight": -math.inf}
        )
        self.assertEqual(settings.weight_uncertainty, 1.0)
        self.assertEqual(settings.top_tier_count, 10)
        self.assertEqual(settings.top_tier_weight, 2.0)

    def test_clamped_settings_are_valid(self):
        """Test that whatever the clamp returns passes validation."""
        settings = self.load(
            {name: -3.5 for name in LIMITS} | {"cross_category_rate": 7.0}
        )
        self.assertEqual(settings.invalid_fields(), [])

    def test_valid_values_load_unchanged_and_quietly(self):
        """Test that a sane file is read as written, with no warning."""
        with self.assertNoLogs("src.models.settings", level="WARNING"):
            settings = Settings.from_dict({"top_tier_count": 12, "weight_uncompared": 50.0})
        self.assertEqual(settings.top_tier_count, 12)
        self.assertIsInstance(settings.top_tier_count, int)
        self.assertEqual(settings.weight_uncompared, 50.0)

    def test_text_that_is_no_number_is_still_an_error(self):
        """Test that the clamp does not hide a malformed file."""
        with self.assertRaises(ValueError):
            Settings.from_dict({"weight_freshness": "lots"})


if __name__ == "__main__":
    unittest.main()
