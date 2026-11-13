"""Post-commit metadata failures preserve installed contents and publication facts."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from pylizlib.core.os.snap.domain import Snapshot
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.operations.install import SnapshotInstaller, SnapshotInstallMetadataError


@pytest.mark.parametrize("published", [True, False, None, 1])
def test_completion_retains_strict_publication_flag_semantics(tmp_path, published):
    """Only a real True flag advances date_last_used after a failed metadata write."""
    previous = datetime(2025, 1, 1)
    current = datetime(2026, 1, 1)
    cause = OSError("metadata failed")
    cause.published = published
    cause.durability_confirmed = False

    def fail_write(path, contents):
        """Simulate the adapter's post-commit failure and publication report."""
        raise cause

    model = SimpleNamespace(date_last_used=previous)
    storage = SimpleNamespace(snapshot=model, path_snapshot_json=tmp_path / "snapshot.json", metadata=SimpleNamespace(read_bytes=lambda path: b"new", write_bytes=fail_write))
    journal = SimpleNamespace(workspace=tmp_path)

    with pytest.raises(SnapshotInstallMetadataError) as error:
        SnapshotInstaller(storage)._complete_install_metadata(journal, {"new": "staged.json"}, current, previous)

    expected = published if type(published) is bool else None
    assert error.value.metadata_published is expected
    assert error.value.installation_completed is True
    assert error.value.metadata_field == "date_last_used"
    assert error.value.durability_confirmed is False
    assert error.value.__cause__ is cause
    assert model.date_last_used == (current if published is True else previous)


def test_empty_install_reports_completion_after_metadata_commit(tmp_path, caplog):
    """Lifecycle INFO logs distinguish start from a successfully committed install."""
    manager = SnapshotManager(Snapshot("empty", "empty", ""), tmp_path / "catalogue")
    manager.create()
    with caplog.at_level("INFO", logger="PylizLib"):
        assert manager.install() is None
    assert "Installing snapshot id=empty associations=0" in caplog.text
    assert "Installed snapshot id=empty" in caplog.text
    assert manager.snapshot.date_last_used is not None
