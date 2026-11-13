"""Destructive snapshot flows must validate the same path semantics that they use."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pylizlib.core.os.snap import BackupType, SnapDirAssociation, Snapshot, SnapshotCatalogue, SnapshotManager, SnapshotSettings


@pytest.mark.parametrize("operation", ["install-replace", "install-merge", "restore-ad", "remove"])
def test_link_followed_by_parent_component_never_selects_another_target(snapshot_workspace: Path, operation: str) -> None:
    """Ambiguous linked parents are refused before either live directory changes."""
    root = snapshot_workspace
    (root / "real/anchor").mkdir(parents=True)
    actual = root / "real/data"
    actual.mkdir()
    (actual / "payload").write_bytes(b"captured")
    (root / "route").mkdir()
    try:
        (root / "route/link").symlink_to(root / "real/anchor", target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    unrelated = root / "route/data"
    unrelated.mkdir()
    (unrelated / "important").write_bytes(b"unrelated data")
    original = root / "route/link/../data"
    settings = SnapshotSettings()
    snapshot = Snapshot("linked-parent", "linked parent", "", directories=[SnapDirAssociation(0, str(original), "folder")])
    catalogue = SnapshotCatalogue(root / "catalogue", settings)
    catalogue.add(snapshot)
    manager = SnapshotManager(snapshot, catalogue.path_catalogue, settings)
    archive = manager.create_backup(root / "exports", "source", BackupType.ASSOCIATED_DIRECTORIES)
    (actual / "payload").write_bytes(b"live source")

    with pytest.raises(ValueError, match="[Ll]ink|[Jj]unction"):
        if operation.startswith("install"):
            catalogue.install(snapshot, clear_destination=operation == "install-replace")
        elif operation == "restore-ad":
            catalogue.restore_backup(archive)
        else:
            catalogue.remove_installed_copies(snapshot.id)
    assert (actual / "payload").read_bytes() == b"live source"
    assert (unrelated / "important").read_bytes() == b"unrelated data"
    assert not (unrelated / "payload").exists()
    assert not list(catalogue.path_catalogue.rglob("journal.json"))


@pytest.mark.parametrize("clear_destination", [True, False])
def test_parent_components_without_links_remain_usable(snapshot_workspace: Path, clear_destination: bool) -> None:
    """Safe lexical parent components retain their meaning through planning and publication."""
    (snapshot_workspace / "prefix/anchor").mkdir(parents=True)
    source = snapshot_workspace / "prefix/data"
    source.mkdir()
    (source / "payload").write_bytes(b"captured")
    lexical = snapshot_workspace / "prefix/anchor/../data"
    settings = SnapshotSettings()
    snapshot = Snapshot("lexical-parent", "lexical parent", "", directories=[SnapDirAssociation(0, str(lexical), "folder")])
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", settings)
    catalogue.add(snapshot)
    (source / "payload").write_bytes(b"live source")
    catalogue.install(snapshot, clear_destination=clear_destination)
    assert (source / "payload").read_bytes() == b"captured"
    assert ".." in snapshot.directories[0].original_path


@pytest.mark.parametrize("legacy_normalized", [False, True])
def test_recovery_retains_lexical_parent_paths_without_links(snapshot_workspace: Path, legacy_normalized: bool) -> None:
    """A paused installation rolls back using the same safe lexical paths as its journal."""
    from pylizlib.core.os.snap.operations import install

    (snapshot_workspace / "prefix/anchor").mkdir(parents=True)
    source = snapshot_workspace / "prefix/data"
    source.mkdir()
    (source / "payload").write_bytes(b"captured")
    lexical = snapshot_workspace / "prefix/anchor/../data"
    settings = SnapshotSettings()
    snapshot = Snapshot("lexical-recovery", "lexical recovery", "", directories=[SnapDirAssociation(0, str(lexical), "folder")])
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", settings)
    catalogue.add(snapshot)
    (source / "payload").write_bytes(b"live source")
    rename = install.rename_and_sync

    def stop_after_backup(original, destination):
        """Stop after the live directory has moved into its recoverable sibling."""
        rename(original, destination)
        if destination.name.startswith("data_bck_"):
            raise SystemExit("simulated process termination")

    with patch.object(install, "rename_and_sync", side_effect=stop_after_backup):
        with pytest.raises(SystemExit):
            catalogue.install(snapshot)
    journal_path = next(catalogue.path_catalogue.rglob("journal.json"))
    journal = json.loads(journal_path.read_text())
    assert ".." in journal["payload"]["entries"][0]["destination"]
    if legacy_normalized:
        for entry in journal["payload"]["entries"]:
            for name in ("stage", "stage_root", "destination", "backup"):
                entry[name] = str(Path(entry[name]).resolve(strict=False))
        journal["payload"]["staging_roots"] = [str(Path(path).resolve(strict=False)) for path in journal["payload"]["staging_roots"]]
        journal_path.write_text(json.dumps(journal))
    assert catalogue.get_by_id(snapshot.id) is not None
    assert (source / "payload").read_bytes() == b"live source"
    assert not list(catalogue.path_catalogue.rglob("journal.json"))
