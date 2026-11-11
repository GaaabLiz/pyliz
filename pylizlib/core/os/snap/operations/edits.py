"""Plan and apply directory-association changes using stable folder IDs."""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pylizlib.core.os.snap.diff import get_edits_between_snapshots
from pylizlib.core.os.snap.domain import SnapDirAssociation, SnapEditAction, SnapEditType, Snapshot
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.publication import cleanup_after_commit


@dataclass(frozen=True)
class EditMove:
    """Move a stored association to a new name, or remove it when target is None."""

    source: Path
    target: Path | None


@dataclass(frozen=True)
class EditPlan:
    """Validated association operations and exact metadata to restore on failure.

    Association objects remain live: freezing this record does not freeze or
    copy the mutable snapshot model used by the existing public API.
    """

    old_json: bytes
    moves: list[EditMove]
    additions: list[SnapDirAssociation]


class SnapshotEditPlanner:
    """Resolve legacy actions against persisted identities before touching copies."""

    def __init__(self, storage: SnapshotStorage):
        """Use the live requested model and its protected metadata adapter."""
        self.storage = storage

    def build(self, edits: list[SnapEditAction]) -> EditPlan:
        """Validate actions and all paths, preserving the legacy preflight order."""
        self.storage.snapshot.validate()
        self.storage.root_path()
        for edit in edits:
            edit.validate()
        snapshot_json_path = self.storage.child_path(self.storage.settings.json_filename)
        old_json = self.storage.metadata.read_bytes(snapshot_json_path)
        old = self.storage.metadata.from_json(snapshot_json_path)
        expected_edits = get_edits_between_snapshots(old, self.storage.snapshot)
        old_by_id = {assoc.folder_id: assoc for assoc in old.directories}
        new_by_id = {assoc.folder_id: assoc for assoc in self.storage.snapshot.directories}
        for snapshot in (old, self.storage.snapshot):
            names = [assoc.directory_name for assoc in snapshot.directories]
            if len(set(names)) != len(names):
                raise ValueError("Snapshot associations must have unique directory names.")

        actions_by_id = self._resolve_legacy_actions(edits, old, self.storage.snapshot)
        if actions_by_id != {edit.folder_id: edit.action_type for edit in expected_edits}:
            raise ValueError("Edit actions do not match the stored and requested snapshot associations.")

        moves = []
        additions = []
        for edit in expected_edits:
            if edit.action_type == SnapEditType.ADD_DIR:
                additions.append(new_by_id[edit.folder_id])
            else:
                source = self.storage.child_path(old_by_id[edit.folder_id].directory_name)
                target = self.storage.child_path(new_by_id[edit.folder_id].directory_name) if edit.action_type == SnapEditType.RENAME_DIR else None
                moves.append(EditMove(source, target))

        self._validate_filesystem_plan(old, moves, additions)
        return EditPlan(old_json, moves, additions)

    @staticmethod
    def _resolve_legacy_actions(edits: list[SnapEditAction], old: Snapshot, requested: Snapshot) -> dict[str, SnapEditType]:
        """Resolve each action once against original names or requested additions."""
        # Resolve legacy name/path-based actions against the original metadata,
        # before any name is reused by another association.
        actions_by_id = {}
        for edit in edits:
            folder_id = edit.folder_id or edit.folder_id_to_remove
            if not folder_id:
                if edit.action_type == SnapEditType.ADD_DIR:
                    matches = [assoc for assoc in requested.directories if assoc.original_path == edit.new_path]
                else:
                    name = edit.old_directory_name or edit.directory_name_to_remove
                    matches = [assoc for assoc in old.directories if assoc.directory_name == name]
                if len(matches) != 1:
                    raise ValueError("Edit action does not identify a unique association.")
                folder_id = matches[0].folder_id
            if folder_id in actions_by_id:
                raise ValueError(f"Multiple edit actions for association '{folder_id}'.")
            actions_by_id[folder_id] = edit.action_type
        return actions_by_id

    def _validate_filesystem_plan(self, old: Snapshot, moves: list[EditMove], additions: list[SnapDirAssociation]) -> None:
        """Check every source and destination before the first stored rename."""
        # Validate the complete plan before touching any stored copy.
        sources = {move.source for move in moves}
        targets = [move.target for move in moves if move.target is not None] + [self.storage.child_path(assoc.directory_name) for assoc in additions]
        for assoc in old.directories:
            source = self.storage.child_path(assoc.directory_name)
            if not source.is_dir():
                raise FileNotFoundError(f"Snapshot directory '{source}' is missing.")
        for target in targets:
            if target.exists() and target not in sources:
                raise FileExistsError(f"Snapshot destination '{target}' is already occupied.")
        for assoc in additions:
            if not Path(assoc.original_path).is_dir():
                raise FileNotFoundError(f"Source directory '{assoc.original_path}' is missing.")


class SnapshotEditor:
    """Stage and publish association edits with the existing byte-level rollback."""

    def __init__(self, storage: SnapshotStorage):
        """Bind one invocation's model, paths, copy strategy and metadata adapter."""
        self.storage = storage

    def apply(self, edits: list[SnapEditAction], message_callback=None) -> None:
        """Build a complete plan before staging or publishing any association."""
        plan = SnapshotEditPlanner(self.storage).build(edits)
        self._apply_plan(plan, message_callback)

    def _apply_plan(self, plan: EditPlan, message_callback=None) -> None:
        """Keep originals until JSON save; restore moves and bytes on failure."""
        staging_path = Path(tempfile.mkdtemp(prefix="_staging_update_", dir=self.storage.path_snapshot))
        staged_originals = []
        publications = []
        published = []
        saving_json = False
        previous_manifests = {assoc.folder_id: assoc.integrity_manifest for assoc in self.storage.snapshot.directories}
        try:
            for i, move in enumerate(plan.moves):
                source, target = move.source, move.target
                staged = staging_path / f"original_{i}"
                source.rename(staged)
                staged_originals.append((staged, source))
                if target is not None:
                    publications.append((staged, target))
            for assoc in plan.additions:
                manifest = {}
                assoc.copy_install_to(
                    staging_path / "additions",
                    message_callback=message_callback,
                    copy_strategy=self.storage.settings.copy_strategy,
                    manifest=manifest,
                )
                assoc.integrity_manifest = manifest
                publications.append((staging_path / "additions" / assoc.directory_name, self.storage.child_path(assoc.directory_name)))

            for staged, target in publications:
                if target.exists():
                    raise FileExistsError(f"Snapshot destination '{target}' is already occupied.")
                staged.rename(target)
                published.append((staged, target))

            for assoc in self.storage.snapshot.directories:
                expected_path = self.storage.child_path(assoc.directory_name)
                if not expected_path.is_dir():
                    raise RuntimeError(f"Integrity check failed: Expected snapshot directory '{expected_path}' is missing.")
            saving_json = True
            self.storage.save_json()
        except Exception:
            for staged, target in reversed(published):
                target.rename(staged)
            for staged, source in reversed(staged_originals):
                staged.rename(source)
            if saving_json:
                self.storage.metadata.write_bytes(self.storage.child_path(self.storage.settings.json_filename), plan.old_json)
            for assoc in self.storage.snapshot.directories:
                assoc.integrity_manifest = previous_manifests[assoc.folder_id]
            shutil.rmtree(staging_path)
            raise

        # Deletions only affect staged originals after the new state is committed.
        cleanup_after_commit([staging_path], "Snapshot update")
