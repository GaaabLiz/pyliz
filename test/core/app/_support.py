"""Shared fixtures for application configuration tests."""

import os
import tempfile
import unittest
from unittest.mock import patch


def isolate_pylizapp_home(test_case: unittest.TestCase):
    """Redirect PylizApp's home-directory lookup into a per-test temporary root."""
    temp_dir = tempfile.TemporaryDirectory()
    test_case.addCleanup(temp_dir.cleanup)

    def fake_home_dir(app_name, create_if_not=True):
        target = os.path.join(temp_dir.name, app_name)
        if create_if_not:
            os.makedirs(target, exist_ok=True)
        return target

    path_patcher = patch(
        "pylizlib.core.app.pylizapp.get_app_home_dir",
        side_effect=fake_home_dir,
    )
    path_patcher.start()
    test_case.addCleanup(path_patcher.stop)
    return temp_dir
