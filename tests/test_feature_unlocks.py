import unittest

from feature_unlocks import FeatureUnlockDetector


class FeatureUnlockDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = FeatureUnlockDetector()

    def test_missing_optional_text_is_unknown(self):
        state = self.detector.detect("Gold 100000 Elixir 200000", "Upgrade")
        self.assertIsNone(state.dark_elixir)
        self.assertIsNone(state.builder_base)
        self.assertFalse(state.dark_elixir_unlocked)
        self.assertFalse(state.builder_base_unlocked)

    def test_dark_elixir_requires_explicit_evidence(self):
        state = self.detector.detect("Dark Elixir 1250", "")
        self.assertTrue(state.dark_elixir_unlocked)
        self.assertGreaterEqual(state.dark_elixir.confidence, 0.82)

    def test_builder_base_requires_explicit_evidence(self):
        state = self.detector.detect("", "Builder Hall level 3")
        self.assertTrue(state.builder_base_unlocked)
        self.assertEqual(state.builder_base.source, "accessibility")

    def test_independent_features_can_be_detected(self):
        state = self.detector.detect(
            "Gold 100K Dark Elixir Storage",
            "Builder Base"
        )
        self.assertTrue(state.dark_elixir_unlocked)
        self.assertTrue(state.builder_base_unlocked)


if __name__ == "__main__":
    unittest.main()
