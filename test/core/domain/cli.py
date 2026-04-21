import unittest

from pylizlib.core.domain.cli import AnsYesNo


class CliDomainTestCase(unittest.TestCase):
    def test_from_string_yes(self):
        self.assertEqual(AnsYesNo.from_string("yes"), AnsYesNo.YES)
        self.assertEqual(AnsYesNo.from_string(" YES "), AnsYesNo.YES)

    def test_from_string_no(self):
        self.assertEqual(AnsYesNo.from_string("no"), AnsYesNo.NO)
        self.assertEqual(AnsYesNo.from_string("No"), AnsYesNo.NO)

    def test_from_string_invalid(self):
        with self.assertRaises(ValueError):
            AnsYesNo.from_string("maybe")

    def test_str_returns_name(self):
        self.assertEqual(str(AnsYesNo.YES), "YES")


if __name__ == "__main__":
    unittest.main()
