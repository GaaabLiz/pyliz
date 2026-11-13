"""Cumulative space checks on a shared filesystem."""

import errno
from types import SimpleNamespace

import pytest

from pylizlib.core.os.filesystem import capacity


def test_same_device_requirements_are_added_and_logged(tmp_path, monkeypatch, caplog):
    """Two targets on one device cannot each consume the same free-space budget."""
    monkeypatch.setattr(capacity.shutil, "disk_usage", lambda path: SimpleNamespace(free=15))
    with caplog.at_level("DEBUG", logger="PylizLib"):
        with pytest.raises(OSError) as error:
            capacity.ensure_required_space(tmp_path, 5, [(tmp_path, 6), (tmp_path, 5)])
    assert error.value.errno == errno.ENOSPC
    assert "required_bytes=16 available_bytes=15" in caplog.text
    assert capacity.ensure_required_space(tmp_path, 5, [(tmp_path, 10)]) is None
