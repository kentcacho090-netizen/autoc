import unittest

from resource_observer import DynamicResourceObserver


class ResourceObserverTests(unittest.TestCase):
    def test_parse_plain_integer(self):
        self.assertEqual(DynamicResourceObserver._parse_number("1,234,567"), 1234567)

    def test_parse_decimal_suffix(self):
        self.assertEqual(DynamicResourceObserver._parse_number("2.5M"), 2500000)

    def test_parse_common_ocr_confusions(self):
        self.assertEqual(DynamicResourceObserver._parse_number("IO K"), 10000)

    def test_rejects_negative_values(self):
        self.assertIsNone(DynamicResourceObserver._parse_number("-500"))

    def test_joins_adjacent_numeric_tokens(self):
        rows = [
            ("1,234", 900, 100, 60, 20, 0.92),
            ("567", 965, 101, 45, 19, 0.94),
        ]
        joined = DynamicResourceObserver._join_numeric_tokens(rows)
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0][0], "1,234567")

    def test_does_not_join_distant_numeric_tokens(self):
        rows = [
            ("123", 900, 100, 40, 20, 0.92),
            ("456", 1000, 101, 40, 19, 0.94),
        ]
        joined = DynamicResourceObserver._join_numeric_tokens(rows)
        self.assertEqual(len(joined), 2)


if __name__ == "__main__":
    unittest.main()
