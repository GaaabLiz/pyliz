import os
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pylizlib.core.log.loggiz import (
    Loggiz,
    LoggizLogger,
    config,
    rootConsoleLogger,
    rootFileLogger,
)


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

    def test_setup_with_timestamp_template(self):
        temp_dir = tempfile.mkdtemp()
        try:
            Loggiz.setup(
                app_name="demo_ts",
                setup_console=False,
                setup_file=True,
                file_log_base_path=temp_dir,
                use_app_timestamp_template=True,
            )
            self.assertTrue(config.logger_file_enabled)
            self.assertTrue(os.path.exists(config.file_log_path))
        finally:
            Loggiz._reset_handlers(rootFileLogger)
            shutil.rmtree(temp_dir, ignore_errors=True)


class LoggizLoggerTestCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: Loggiz._reset_handlers(rootFileLogger))
        self.addCleanup(lambda: Loggiz._reset_handlers(rootConsoleLogger))
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "test.log")
        Loggiz.setup(
            app_name="test",
            setup_console=True,
            setup_file=True,
            file_log_base_path=self.temp_dir,
            file_log_folder_name="",
            file_log_name="test.log",
            use_app_timestamp_template=False,
        )

    def tearDown(self):
        Loggiz._reset_handlers(rootFileLogger)
        Loggiz._reset_handlers(rootConsoleLogger)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tag_string_formatting(self):
        raw = LoggizLogger.get_tag_string("CORE", ansify=False)
        self.assertIn("CORE", raw)
        ansi = LoggizLogger.get_tag_string("CORE", ansify=True)
        self.assertIn("CORE", ansi)

    def test_print_separator(self):
        config.set_console_ansi(False)
        LoggizLogger.print_separator("-", 5)
        config.set_console_ansi(True)
        LoggizLogger.print_separator("-", 5)

    def test_log_console_methods(self):
        for ansi in (False, True):
            config.set_console_ansi(ansi)
            LoggizLogger.log_console_debug("TAG", "debug msg")
            LoggizLogger.log_console_info("TAG", "info msg")
            LoggizLogger.log_console_warning("TAG", "warn msg")
            LoggizLogger.log_console_error("TAG", "err msg")

    def test_log_file_methods(self):
        LoggizLogger.log_file_debug("FILE_TAG", "file debug")
        LoggizLogger.log_file_info("FILE_TAG", "file info")
        LoggizLogger.log_file_warning("FILE_TAG", "file warn")
        LoggizLogger.log_file_error("FILE_TAG", "file err")

        with open(self.log_file, "r") as f:
            content = f.read()
        self.assertIn("file debug", content)
        self.assertIn("file info", content)
        self.assertIn("file warn", content)
        self.assertIn("file err", content)

    def test_combined_tag_logging(self):
        config.set_logger_console_enabled(True)
        config.set_logger_file_enabled(True)

        LoggizLogger.debug_tag("ALL", "debug combined")
        LoggizLogger.info_tag("ALL", "info combined")
        LoggizLogger.warning_tag("ALL", "warning combined")
        LoggizLogger.error_tag("ALL", "error combined")

        with open(self.log_file, "r") as f:
            content = f.read()
        self.assertIn("debug combined", content)
        self.assertIn("info combined", content)
        self.assertIn("warning combined", content)
        self.assertIn("error combined", content)

        # Test with outputs disabled
        config.set_logger_console_enabled(False)
        config.set_logger_file_enabled(False)
        LoggizLogger.debug_tag("NONE", "should not appear")
        LoggizLogger.info_tag("NONE", "should not appear")
        LoggizLogger.warning_tag("NONE", "should not appear")
        LoggizLogger.error_tag("NONE", "should not appear")


class LoggizLoggerTestCase(unittest.TestCase):
    def test_get_tag_string(self):
        tag_no_ansi = LoggizLogger.get_tag_string("TEST", ansify=False)
        self.assertEqual(tag_no_ansi, f"{config.tag_char_start}TEST{config.tag_char_end}")

        tag_ansi = LoggizLogger.get_tag_string("TEST", ansify=True)
        self.assertIn("TEST", tag_ansi)

    @patch("builtins.print")
    def test_print_separator(self, mock_print):
        config.enable_console_ansi = False
        LoggizLogger.print_separator("-", 5)
        mock_print.assert_called_with("-----")

        config.enable_console_ansi = True
        LoggizLogger.print_separator("-", 5)
        self.assertIn("-----", mock_print.call_args[0][0])

    @patch.object(rootConsoleLogger, "debug")
    @patch.object(rootConsoleLogger, "info")
    @patch.object(rootConsoleLogger, "warning")
    @patch.object(rootConsoleLogger, "error")
    def test_log_console_methods(self, mock_err, mock_warn, mock_info, mock_dbg):
        config.enable_console_ansi = False
        LoggizLogger.log_console_debug("TAG", "dbg msg")
        mock_dbg.assert_called_with(f"{config.tag_char_start}TAG{config.tag_char_end}dbg msg")

        LoggizLogger.log_console_info("TAG", "info msg")
        mock_info.assert_called_with(f"{config.tag_char_start}TAG{config.tag_char_end}info msg")

        LoggizLogger.log_console_warning("TAG", "warn msg")
        mock_warn.assert_called_with(f"{config.tag_char_start}TAG{config.tag_char_end}warn msg")

        LoggizLogger.log_console_error("TAG", "err msg")
        mock_err.assert_called_with(f"{config.tag_char_start}TAG{config.tag_char_end}err msg")

        config.enable_console_ansi = True
        LoggizLogger.log_console_debug("TAG", "dbg msg")
        self.assertIn("dbg msg", mock_dbg.call_args[0][0])

    @patch.object(rootFileLogger, "debug")
    @patch.object(rootFileLogger, "info")
    @patch.object(rootFileLogger, "warning")
    @patch.object(rootFileLogger, "error")
    def test_log_file_methods(self, mock_err, mock_warn, mock_info, mock_dbg):
        LoggizLogger.log_file_debug("TAG", "dbg msg")
        mock_dbg.assert_called_with(f"{config.tag_char_start}TAG{config.tag_char_end}dbg msg")

        LoggizLogger.log_file_info("TAG", "info msg")
        mock_info.assert_called_with(f"{config.tag_char_start}TAG{config.tag_char_end}info msg")

        LoggizLogger.log_file_warning("TAG", "warn msg")
        mock_warn.assert_called_with(f"{config.tag_char_start}TAG{config.tag_char_end}warn msg")

        LoggizLogger.log_file_error("TAG", "err msg")
        mock_err.assert_called_with(f"{config.tag_char_start}TAG{config.tag_char_end}err msg")

    @patch.object(LoggizLogger, "log_console_debug")
    @patch.object(LoggizLogger, "log_file_debug")
    @patch.object(LoggizLogger, "log_console_info")
    @patch.object(LoggizLogger, "log_file_info")
    @patch.object(LoggizLogger, "log_console_warning")
    @patch.object(LoggizLogger, "log_file_warning")
    @patch.object(LoggizLogger, "log_console_error")
    @patch.object(LoggizLogger, "log_file_error")
    def test_tag_dispatch_methods(
        self,
        mock_file_err,
        mock_cons_err,
        mock_file_warn,
        mock_cons_warn,
        mock_file_info,
        mock_cons_info,
        mock_file_dbg,
        mock_cons_dbg,
    ):
        config.logger_console_enabled = True
        config.logger_file_enabled = True

        LoggizLogger.debug_tag("T", "msg")
        mock_cons_dbg.assert_called_once_with("T", "msg")
        mock_file_dbg.assert_called_once_with("T", "msg")

        LoggizLogger.info_tag("T", "msg")
        mock_cons_info.assert_called_once_with("T", "msg")
        mock_file_info.assert_called_once_with("T", "msg")

        LoggizLogger.warning_tag("T", "msg")
        mock_cons_warn.assert_called_once_with("T", "msg")
        mock_file_warn.assert_called_once_with("T", "msg")

        LoggizLogger.error_tag("T", "msg")
        mock_cons_err.assert_called_once_with("T", "msg")
        mock_file_err.assert_called_once_with("T", "msg")


if __name__ == "__main__":
    unittest.main()
