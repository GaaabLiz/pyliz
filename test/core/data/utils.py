import unittest

from pylizlib.core.data.utils import all_not_none, contains_item


class UtilsHelpersTestCase(unittest.TestCase):

    def test_contains_item_true(self):
        self.assertTrue(contains_item(2, [1, 2, 3]))

    def test_contains_item_false(self):
        self.assertFalse(contains_item("x", ["a", "b", "c"]))

    def test_all_not_none_true(self):
        self.assertTrue(all_not_none(1, "a", True))

    def test_all_not_none_false_when_any_none(self):
        self.assertFalse(all_not_none(1, None, "a"))

    def test_all_not_none_true_for_empty_input(self):
        self.assertTrue(all_not_none())


if __name__ == "__main__":
    unittest.main()