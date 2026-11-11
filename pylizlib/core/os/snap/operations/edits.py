"""Plan and apply directory-association changes using stable folder IDs."""

from copy import deepcopy
from dataclasses import dataclass, fields
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.diff import get_edits_between_snapshots
from pylizlib.core.os.snap.domain import SnapDirAssociation, SnapEditAction, SnapEditType, Snapshot
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.path_identity import same_filesystem_entry
from pylizlib.core.os.snap.storage.transactions import (
    SnapshotTransactionJournal,
    TransactionRecoveryError,
    prepare_snapshot_metadata,
    recover_storage_transactions,
    rename_and_sync,
)


@dataclass(frozen=True)
class EditMove:
    """Move a stored association to a new name, or remove it when target is None."""

    source: Path
    target: Path | None


@dataclass(frozen=True)
class EditPlan:
    """Validated association operations and exact metadata to restore on failure.

    Association objects remain live: freezing this record does not freeze or
    copy the mutable snapshot model used by the existing public API. The
    persisted model is retained separately so a failed edit can restore the
    caller's live model along with the stored bytes and directory names.
    """

    old_json: bytes
    old_snapshot: Snapshot
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
        return EditPlan(old_json, old, moves, additions)

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
                    matches = [assoc for assoc in requested.directories if same_filesystem_entry(assoc.original_path, edit.new_path)]
                else:
                    name = edit.old_directory_name or edit.directory_name_to_remove
                    matches = [assoc for assoc in old.directories if assoc.directory_name == name]
                if len(matches) != 1:
                    raise ValueError("Edit action does not identify a unique association; pass its folder_id.")
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
    """Stage and publish association edits with persistent crash recovery."""

    def __init__(self, storage: SnapshotStorage):
        """Bind one invocation's model, paths, copy strategy and metadata adapter."""
        self.storage = storage

    def apply(self, edits: list[SnapEditAction], message_callback=None) -> None:
        """Build a complete plan before staging or publishing any association."""
        recover_storage_transactions(self.storage)
        plan = SnapshotEditPlanner(self.storage).build(edits)
        self._apply_plan(plan, message_callback)

    def _apply_plan(self, plan: EditPlan, message_callback=None) -> None:
        """Journal staged moves and the proposed JSON before final publication."""
        moves = [
            {"source": move.source.name, "target": move.target.name if move.target is not None else None, "staged": f"original_{index}"}
            for index, move in enumerate(plan.moves)
        ]
        additions = [{"target": association.directory_name, "staged": f"addition_{index}"} for index, association in enumerate(plan.additions)]
        journal = SnapshotTransactionJournal.begin(
            self.storage.path_snapshot,
            "edit",
            {"phase": "staging", "moves": moves, "additions": additions},
        )
        staging_path = journal.workspace
        try:
            for index, assoc in enumerate(plan.additions):
                manifest = {}
                assoc.copy_install_to(
                    staging_path / additions[index]["staged"],
                    message_callback=message_callback,
                    copy_strategy=self.storage.settings.copy_strategy,
                    manifest=manifest,
                )
            metadata = prepare_snapshot_metadata(self.storage, staging_path)
            journal.update_payload(metadata=metadata)

            for index, move in enumerate(plan.moves):
                rename_and_sync(move.source, staging_path / f"original_{index}")

            journal.update_payload(phase="publishing")
            publications = [
                (staging_path / move["staged"], self.storage.child_path(move["target"]))
                for move in moves
                if move["target"] is not None
            ]
            publications.extend(
                (staging_path / addition["staged"], self.storage.child_path(addition["target"]))
                for addition in additions
            )
            for staged, target in publications:
                if target.exists() or target.is_symlink():
                    raise FileExistsError(f"Snapshot destination '{target}' is already occupied.")
                rename_and_sync(staged, target)

            for assoc in self.storage.snapshot.directories:
                expected_path = self.storage.child_path(assoc.directory_name)
                if not expected_path.is_dir():
                    raise RuntimeError(f"Integrity check failed: Expected snapshot directory '{expected_path}' is missing.")
            journal.set_state("commit_decided")
        except Exception as error:
            try:
                journal.decide_rollback(self.storage)
                self._restore_snapshot_model(self.storage.snapshot, plan.old_snapshot)
            except Exception as rollback_error:
                logger.error(f"Snapshot edit rollback is incomplete; journal retained at '{journal.path}': {rollback_error}")
                raise TransactionRecoveryError(f"Snapshot edit rollback is incomplete; journal retained at '{journal.path}'.") from error
            raise

        try:
            new_metadata = self.storage.metadata.read_bytes(staging_path / metadata["new"])
            self.storage.metadata.write_bytes(self.storage.path_snapshot_json, new_metadata)
        except Exception as error:
            if getattr(error, "published", False) is True:
                raise
            try:
                journal.decide_rollback(self.storage)
                self._restore_snapshot_model(self.storage.snapshot, plan.old_snapshot)
            except Exception as rollback_error:
                logger.error(f"Snapshot edit rollback is incomplete; journal retained at '{journal.path}': {rollback_error}")
                raise TransactionRecoveryError(f"Snapshot edit rollback is incomplete; journal retained at '{journal.path}'.") from error
            raise

        journal.set_state("committed")
        journal.finalize(operation="Snapshot update")

    @staticmethod
    def _restore_snapshot_model(snapshot: Snapshot, previous: Snapshot) -> None:
        """Restore a failed edit's model while preserving existing association objects."""
        live_by_id = {association.folder_id: association for association in snapshot.directories}
        restored_directories = []
        association_fields = ("index", "original_path", "folder_id", "mb_size", "integrity_manifest")
        for old_association in previous.directories:
            association = live_by_id.get(old_association.folder_id)
            if association is None:
                association = deepcopy(old_association)
            else:
                for name in association_fields:
                    setattr(association, name, deepcopy(getattr(old_association, name)))
                association._set_storage_name(old_association.directory_name)
            restored_directories.append(association)

        for model_field in fields(Snapshot):
            if model_field.name != "directories":
                setattr(snapshot, model_field.name, deepcopy(getattr(previous, model_field.name)))
        snapshot.directories[:] = restored_directories
