"""Regression tests for persistent association source paths."""

from pathlib import Path

import pytest

from pylizlib.core.os.snap.domain import BackupType, SnapDirAssociation, SnapEditAction, SnapEditType, Snapshot
from pylizlib.core.os.snap.operations.backup_manifest import build_backup_manifest
from pylizlib.core.os.snap.storage import original_paths


def test_relative_association_keeps_its_creation_directory_after_chdir(tmp_path, monkeypatch):
    """Copying an association later must still read from the source chosen at creation."""
    first_cwd = tmp_path / "first-cwd"
    second_cwd = tmp_path / "second-cwd"
    source_a = first_cwd / "data"
    source_b = second_cwd / "data"
    source_a.mkdir(parents=True)
    source_b.mkdir(parents=True)
    (source_a / "value.txt").write_text("from A", encoding="utf-8")
    (source_b / "value.txt").write_text("from B", encoding="utf-8")

    monkeypatch.chdir(first_cwd)
    association = SnapDirAssociation(1, "data", "association", mb_size=0)
    assert association.original_path == source_a.as_posix()

    monkeypatch.chdir(second_cwd)
    association.validate()
    target = tmp_path / "catalogue-copy"
    association.copy_install_to(target)

    assert (target / association.directory_name / "value.txt").read_text(encoding="utf-8") == "from A"
    assert (source_b / "value.txt").read_text(encoding="utf-8") == "from B"


def test_mutated_association_cannot_be_rebound_to_a_relative_path(tmp_path):
    association = SnapDirAssociation(1, str(tmp_path / "source"), "association", mb_size=0)
    association.original_path = "source"

    with pytest.raises(ValueError, match="must be absolute"):
        association.validate()


def test_absolute_normalization_keeps_symlink_components_for_existing_safety_checks(tmp_path):
    real_source = tmp_path / "real-source"
    real_source.mkdir()
    link = tmp_path / "source-link"
    try:
        link.symlink_to(real_source, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    association = SnapDirAssociation(1, str(link), "linked-association", mb_size=0)

    assert association.original_path == link.as_posix()
    assert Path(association.original_path).is_symlink()


def test_relative_add_action_is_anchored_when_created(tmp_path, monkeypatch):
    first_cwd = tmp_path / "first-cwd"
    second_cwd = tmp_path / "second-cwd"
    first_cwd.mkdir()
    second_cwd.mkdir()

    monkeypatch.chdir(first_cwd)
    action = SnapEditAction(action_type=SnapEditType.ADD_DIR, new_path="data")
    assert action.new_path == (first_cwd / "data").as_posix()

    monkeypatch.chdir(second_cwd)
    action.validate()
    assert action.new_path == (first_cwd / "data").as_posix()


def test_windows_mapped_drive_is_stored_as_a_unc_path(monkeypatch):
    """A Windows network drive letter is converted while its mapping is visible."""
    monkeypatch.setattr(original_paths.os, "name", "nt")
    monkeypatch.setattr(original_paths, "_windows_drive_type", lambda drive: 4)
    monkeypatch.setattr(original_paths, "_mapped_drive_unc_root", lambda drive: r"\\server\share")

    normalized = original_paths.normalize_original_path(r"Z:\project\data")

    assert normalized == "//server/share/project/data"


def test_windows_mapped_drive_without_resolvable_unc_is_rejected(monkeypatch):
    monkeypatch.setattr(original_paths.os, "name", "nt")
    monkeypatch.setattr(original_paths, "_windows_drive_type", lambda drive: 4)

    def fail_to_resolve(_drive):
        raise OSError("drive mapping unavailable")

    monkeypatch.setattr(original_paths, "_mapped_drive_unc_root", fail_to_resolve)

    with pytest.raises(ValueError, match="Use the UNC path directly"):
        original_paths.normalize_original_path(r"Z:\project\data")


def test_relative_and_drive_relative_strings_are_not_persisted_absolute_paths():
    assert not original_paths.is_absolute_original_path("data")
    assert not original_paths.is_absolute_original_path(r"Z:project\data")
    assert original_paths.is_absolute_original_path(Path("/data").as_posix())
    assert original_paths.is_absolute_original_path(r"Z:\project\data")


def test_backup_manifest_preserves_foreign_absolute_paths_without_rebinding_them():
    association = SnapDirAssociation(1, r"Z:\project\data", "windows-source", mb_size=0)
    snapshot = Snapshot(
        id="windows-source",
        name="Windows source",
        desc="",
        directories=[association],
        os_created="Windows",
    )

    manifest = build_backup_manifest(
        snapshot,
        BackupType.ASSOCIATED_DIRECTORIES,
        "backup",
        False,
        "20260101_000000",
    )

    assert manifest["associations"][0]["original_path"] == "Z:/project/data"
