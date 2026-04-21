import os
import re
import shutil
import tempfile
import unittest

from pylizlib.core.log.loggiz import Loggiz, config, rootConsoleLogger, rootFileLogger


class LoggizTestCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: Loggiz._reset_handlers(rootFileLogger))
        self.addCleanup(lambda: Loggiz._reset_handlers(rootConsoleLogger))

    def test_create_timestamp_log_file_name(self):
        result = Loggiz.create_timestamp_log_file_name("app")
        self.assertRegex(result, r"^app_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log$")

    def test_create_timestamp_log_file_path(self):
        result = Loggiz.create_timestamp_log_file_path("app", "logs")
        self.assertTrue(result.startswith("logs" + os.sep))
        self.assertTrue(result.endswith(".log"))

    def test_setup_console_replaces_handlers(self):
        Loggiz.setup_console()
        first_count = len(rootConsoleLogger.handlers)
        Loggiz.setup_console()
        second_count = len(rootConsoleLogger.handlers)

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)

    def test_setup_file_replaces_handlers_and_writes(self):
        temp_dir = tempfile.mkdtemp()
        try:
            path = os.path.join(temp_dir, "app.log")
            Loggiz.setup_file(file_path=path)
            rootFileLogger.info("hello")

            self.assertEqual(len(rootFileLogger.handlers), 1)
            self.assertTrue(os.path.exists(path))
        finally:
            Loggiz._reset_handlers(rootFileLogger)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_setup_updates_config_flags(self):
        temp_dir = tempfile.mkdtemp()
        try:
            Loggiz.setup(
                app_name="demo",
                setup_console=True,
                setup_file=True,
                file_log_base_path=temp_dir,
                file_log_folder_name="logs",
                use_app_timestamp_template=False,
                file_log_name="latest.log",
            )

            self.assertTrue(config.logger_console_enabled)
            self.assertTrue(config.logger_file_enabled)
            self.assertTrue(config.file_log_path.endswith("latest.log"))
            self.assertTrue(re.search(r"logs[\\/]latest\.log$", config.file_log_path) is not None)
        finally:
            Loggiz._reset_handlers(rootFileLogger)
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
