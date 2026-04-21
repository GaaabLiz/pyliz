import unittest

from pylizlib.core.domain.operation import Operation


class OperationDomainTestCase(unittest.TestCase):
    def test_default_state(self):
        op = Operation()

        self.assertIsNone(op.payload)
        self.assertFalse(op.status)
        self.assertIsNone(op.error)
        self.assertFalse(op.is_op_ok())

    def test_custom_state(self):
        op = Operation(payload={"x": 1}, status=True, error=None)

        self.assertEqual(op.payload, {"x": 1})
        self.assertTrue(op.is_op_ok())

    def test_str_contains_fields(self):
        op = Operation(payload="done", status=True, error="none")
        output = str(op)

        self.assertIn("status=True", output)
        self.assertIn("payload=done", output)
        self.assertIn("error=none", output)


if __name__ == "__main__":
    unittest.main()
