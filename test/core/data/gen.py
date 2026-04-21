import hashlib
import os
import tempfile
import unittest

from pylizlib.core.data.gen import gen_file_hash, gen_random_string, gen_timestamp_log_name


class GenHelpersTestCase(unittest.TestCase):
    def test_gen_random_string_has_requested_length(self):
        value = gen_random_string(24)

        self.assertEqual(len(value), 24)

    def test_gen_random_string_uses_alnum_characters_only(self):
        value = gen_random_string(200)

        self.assertTrue(value.isalnum())

    def test_gen_random_string_zero_length(self):
        self.assertEqual(gen_random_string(0), "")

    def test_gen_timestamp_log_name_contains_prefix_and_extension(self):
        result = gen_timestamp_log_name("app_", ".log")

        self.assertTrue(result.startswith("app_"))
        self.assertTrue(result.endswith(".log"))

    def test_gen_timestamp_log_name_has_expected_timestamp_shape(self):
        result = gen_timestamp_log_name("p_", ".txt")
        timestamp = result[len("p_") : -len(".txt")]

        self.assertRegex(timestamp, r"^\d{8}_\d{6}$")

    def test_gen_file_hash_matches_known_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "sample.bin")
            payload = b"pyliz-core-data"
            with open(file_path, "wb") as f:
                f.write(payload)

            expected = hashlib.sha256(payload).hexdigest()
            result = gen_file_hash(file_path)

            self.assertEqual(result, expected)

    def test_gen_file_hash_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = os.path.join(temp_dir, "missing.bin")
            with self.assertRaises(FileNotFoundError):
                gen_file_hash(missing)


if __name__ == "__main__":
    unittest.main()
