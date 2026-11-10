import unittest

from pylizlib.ai.utils import unique_preserving_order


class UniquePreservingOrderTestCase(unittest.TestCase):
    def test_preserves_order_and_removes_duplicates(self):
        input_data = ["tag1", "tag2", "tag1", "tag3", "tag2"]
        result = unique_preserving_order(input_data)
        self.assertEqual(result, ["tag1", "tag2", "tag3"])

    def test_trims_whitespace_and_filters_empty_strings(self):
        input_data = ["  tag1  ", "", "   ", "tag2", "tag1\n", "\ttag3\t"]
        result = unique_preserving_order(input_data)
        self.assertEqual(result, ["tag1", "tag2", "tag3"])

    def test_empty_iterable(self):
        self.assertEqual(unique_preserving_order([]), [])
        self.assertEqual(unique_preserving_order(()), [])


if __name__ == "__main__":
    unittest.main()
