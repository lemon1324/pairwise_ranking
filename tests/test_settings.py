"""Unit tests for the Settings model."""

import unittest
from src.models.settings import Settings


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


if __name__ == "__main__":
    unittest.main()
