import unittest

from pylizlib.core.data.unit import (
    convert_byte_to_mb,
    convert_months_number_to_str,
    get_min_from_msec,
    get_normalized_gb_mb_str,
    get_sec60_from_msec,
    get_total_sec_from_msec,
)


class UnitHelpersTestCase(unittest.TestCase):
    def test_convert_byte_to_mb(self):
        self.assertEqual(convert_byte_to_mb(1048576), 1.0)

    def test_get_total_sec_from_msec(self):
        self.assertEqual(get_total_sec_from_msec(3500), 3)

    def test_get_sec60_from_msec(self):
        self.assertEqual(get_sec60_from_msec(123000), 3)

    def test_get_min_from_msec(self):
        self.assertEqual(get_min_from_msec(180000), 3)

    def test_convert_months_number_to_str_valid(self):
        self.assertEqual(convert_months_number_to_str(12), "December")

    def test_convert_months_number_to_str_invalid(self):
        self.assertEqual(convert_months_number_to_str(99), "Invalid Month")

    def test_get_normalized_gb_mb_str_returns_mb_for_small_value(self):
        self.assertEqual(get_normalized_gb_mb_str(1048576), "1.00 MB")

    def test_get_normalized_gb_mb_str_returns_gb_for_large_value(self):
        self.assertEqual(get_normalized_gb_mb_str(1073741824), "1.00 GB")


if __name__ == "__main__":
    unittest.main()
