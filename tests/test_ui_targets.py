import unittest

from ui_targets import UITargetDetector


class UITargetDetectorTests(unittest.TestCase):
    def test_multiword_alias_is_detectable_in_grouped_text(self):
        detector = UITargetDetector()
        words = [
            ("Town", 100, 200, 60, 30, 0.95),
            ("Hall", 165, 200, 60, 30, 0.96),
        ]
        grouped = detector._group_ocr_words(words)
        self.assertTrue(any(row[0] == "Town Hall" for row in grouped))

    def test_grouped_text_keeps_combined_bounds(self):
        detector = UITargetDetector()
        words = [
            ("Return", 100, 200, 70, 30, 0.90),
            ("Home", 175, 202, 65, 28, 0.92),
        ]
        grouped = detector._group_ocr_words(words)
        self.assertEqual(grouped, [("Return Home", 100, 200, 140, 30, 0.90)])

    def test_single_word_ocr_remains_usable(self):
        detector = UITargetDetector()
        words = [("Upgrade", 300, 400, 90, 32, 0.91)]
        grouped = detector._group_ocr_words(words)
        self.assertEqual(grouped, words)


if __name__ == "__main__":
    unittest.main()
