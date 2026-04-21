import unittest

from pylizlib.core.data.json import JsonUtils


class JsonUtilsTestCase(unittest.TestCase):
    def test_is_valid_json_true_for_object(self):
        self.assertTrue(JsonUtils.is_valid_json('{"a": 1, "b": 2}'))

    def test_is_valid_json_true_for_array(self):
        self.assertTrue(JsonUtils.is_valid_json("[1, 2, 3]"))

    def test_is_valid_json_false_for_invalid_string(self):
        self.assertFalse(JsonUtils.is_valid_json('{"a": 1'))

    def test_is_valid_json_false_for_non_string(self):
        self.assertFalse(JsonUtils.is_valid_json(None))

    def test_has_keys_true_when_all_keys_exist(self):
        raw = '{"name": "demo", "version": "1.0"}'

        self.assertTrue(JsonUtils.has_keys(raw, ["name", "version"]))

    def test_has_keys_false_when_missing_key(self):
        raw = '{"name": "demo"}'

        self.assertFalse(JsonUtils.has_keys(raw, ["name", "version"]))

    def test_has_keys_false_for_non_object_json(self):
        self.assertFalse(JsonUtils.has_keys('["name", "version"]', ["name"]))

    def test_has_keys_false_for_invalid_json(self):
        self.assertFalse(JsonUtils.has_keys('{"name":', ["name"]))

    def test_clean_json_apici_removes_json_fence(self):
        raw = '```json\n{"name":"demo"}\n```'

        self.assertEqual(JsonUtils.clean_json_apici(raw), '{"name":"demo"}')

    def test_clean_json_apici_removes_plain_fence(self):
        raw = '```\n{"name":"demo"}\n```'

        self.assertEqual(JsonUtils.clean_json_apici(raw), '{"name":"demo"}')

    def test_clean_json_apici_keeps_unfenced_json(self):
        raw = '  {"name":"demo"}  '

        self.assertEqual(JsonUtils.clean_json_apici(raw), '{"name":"demo"}')


if __name__ == "__main__":
    unittest.main()
