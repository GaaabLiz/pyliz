"""Verify configuration rules independently of catalogue publication."""

from pathlib import Path

import pytest

from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot
from pylizlib.core.os.snap.operations import configuration


def test_association_ids_are_not_recycled_when_replacing_a_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    removed = SnapDirAssociation(index=0, original_path=str(tmp_path / "removed"), folder_id="abc")
    candidates = iter(("abc", "def", "def", "ghi"))

    def next_id(length: int) -> str:
        assert length == 3
        return next(candidates)

    monkeypatch.setattr(configuration, "gen_random_string", next_id)
    associations = configuration.build_associations([tmp_path / "first", tmp_path / "second"], 3, [removed])

    assert [association.folder_id for association in associations] == ["def", "ghi"]
    assert [association.index for association in associations] == [0, 1]


def test_unchanged_missing_path_keeps_legacy_storage_name(tmp_path: Path) -> None:
    path = tmp_path / "missing"
    association = SnapDirAssociation(index=3, original_path=str(path), folder_id="legacy", mb_size=2.5)
    association._set_storage_name("legacy-directory")
    snapshot = Snapshot(id="snap", name="Snapshot", desc="", directories=[association])

    updated = configuration.configure_snapshot(
        snapshot,
        folder_id_length=4,
        name=None,
        desc=None,
        tags=None,
        directory_paths=[path],
        data_updates=None,
        data_remove=(),
    )

    retained = updated.directories[0]
    assert retained is not association
    assert retained.directory_name == association.directory_name == "legacy-directory"
    assert retained.folder_id == association.folder_id
    assert retained.mb_size == 2.5
    assert retained.index == 0
    assert association.index == 3


def test_ambiguous_existing_associations_are_rejected(tmp_path: Path) -> None:
    associations = [SnapDirAssociation(index=i, original_path=str(tmp_path), folder_id=str(i)) for i in range(2)]

    with pytest.raises(ValueError, match="matches multiple existing associations"):
        configuration.build_associations([tmp_path], 4, associations)
