"""Regression coverage for association copies published by snapshot edits."""

from pathlib import Path

from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot


def test_added_association_is_published_at_the_declared_storage_root(tmp_path: Path) -> None:
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    source_a.mkdir()
    source_b.mkdir()
    (source_a / "data.txt").write_text("existing association", encoding="utf-8")
    (source_b / "data.txt").write_text("added association", encoding="utf-8")

    catalogue = SnapshotCatalogue(tmp_path / "catalogue")
    original = Snapshot(
        id="edit-addition",
        name="Before edit",
        desc="",
        directories=[SnapDirAssociation(index=1, original_path=str(source_a), folder_id="association-a")],
    )
    catalogue.add(original)

    updated = original.clone()
    updated.directories.append(SnapDirAssociation(index=2, original_path=str(source_b), folder_id="association-b"))
    catalogue.update_snapshot_by_objs(original, updated)

    loaded = catalogue.get_by_id(original.id)
    assert loaded is not None
    added = next(association for association in loaded.directories if association.folder_id == "association-b")
    snapshot_root = catalogue.get_snap_directory_path(loaded)
    assert snapshot_root is not None
    stored_copy = snapshot_root / added.directory_name
    assert (stored_copy / "data.txt").read_text(encoding="utf-8") == "added association"
    assert not (stored_copy / added.directory_name).exists()
    assert added.integrity_manifest is not None
