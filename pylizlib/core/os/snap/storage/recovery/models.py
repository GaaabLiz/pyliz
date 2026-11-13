"""Describe legacy v1 journals and v2 edits with durable rollback progress."""

import json
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

TRANSACTION_DIRECTORY = ".pyliz_transactions"
JOURNAL_FILENAME = "journal.json"
VALID_STATES = {"prepared", "rollback_decided", "commit_decided", "committed"}
JournalState = Literal["prepared", "rollback_decided", "commit_decided", "committed"]


class MetadataPaths(TypedDict):
    """Name exact previous/proposed JSON versions inside one journal workspace.

    Attributes:
        old (str): Workspace-relative filename containing previous metadata bytes.
        new (str): Workspace-relative filename containing proposed metadata bytes.
        target (str): Active metadata basename below the snapshot directory.
    """

    old: str
    new: str
    target: str


class ReplacementEntry(TypedDict):
    """Describe one directory swap; validators retain operation-specific policies.

    Attributes:
        folder_id (str): Non-empty stable association identity; physical storage uses its digest, so it need not
            be a path component.
        stage (str): Staged tree path, with interpretation defined by the operation.
        destination (str): Publication target path.
        backup (str): Generated path retaining the original destination.
        had_original (bool): Whether the target existed before publication.
        stage_root (NotRequired[str]): Optional shared staging root, used for install merge.
        merge_child (NotRequired[bool]): Optional flag identifying a top-level merge child.
    """

    folder_id: str
    stage: str
    destination: str
    backup: str
    had_original: bool
    stage_root: NotRequired[str]
    merge_child: NotRequired[bool]


class EditEntry(TypedDict):
    """Persist relative names for a staged rename, removal or addition.

    Attributes:
        source (NotRequired[str]): Original basename, omitted for additions.
        target (str | None): Final basename, or None for a removal.
        staged (str): Unique workspace-relative staging basename.
    """

    source: NotRequired[str]
    target: str | None
    staged: str


class JournalEnvelope(TypedDict):
    """Describe persisted journal envelopes without discarding unknown fields.

    Attributes:
        version (int): Format version: 1 for legacy/general operations, 2 for durable edit rollback progress.
        scope_root (str): Resolved scope path serialized with forward slashes.
        operation (str): Operation discriminator used by the recovery coordinator.
        state (JournalState): Durable decision; allowed names do not impose an FSM.
        payload (dict): Operation-specific fields, validated by its handler.
    """

    version: int
    scope_root: str
    operation: str
    state: JournalState
    payload: dict


class JournalCodec:
    """Encode and validate versioned envelopes without normalizing their values."""

    @staticmethod
    def encode(payload: dict) -> str:
        """Encode journal data using the existing two-space JSON representation.

        Args:
            payload (dict): Envelope and operation data, including unknown fields.

        Returns:
            str: JSON with two-space indentation and no added terminal newline.

        Raises:
            TypeError: If a value is not JSON serializable.
        """
        return json.dumps(payload, indent=2)

    @staticmethod
    def validate(payload: dict, scope_root: Path) -> None:
        """Validate legacy envelopes and the v2 envelope reserved for resumable edits.

        Args:
            payload (dict): Decoded journal, checked without copying or coercion.
            scope_root (Path): Resolved path expected to own this journal.

        Returns:
            None: If the envelope is valid; operation data is validated separately.

        Raises:
            TransactionRecoveryError: If version, scope, operation, state or payload shape is invalid. Existing
                equality semantics for v1 are retained; v2 requires an integer version and an edit operation.
        """
        from pylizlib.core.os.snap.storage.transactions import TransactionRecoveryError

        if not isinstance(payload, dict):
            raise TransactionRecoveryError("Unsupported snapshot transaction journal version.")
        version = payload.get("version")
        if version != 1 and not (type(version) is int and version == 2 and payload.get("operation") == "edit"):
            raise TransactionRecoveryError("Unsupported snapshot transaction journal version.")
        if payload.get("scope_root") != scope_root.as_posix():
            raise TransactionRecoveryError("Transaction journal belongs to another storage scope.")
        if not isinstance(payload.get("operation"), str):
            raise TransactionRecoveryError("Transaction journal operation must be a string.")
        if payload.get("state") not in VALID_STATES:
            raise TransactionRecoveryError("Transaction journal has an invalid state.")
        if not isinstance(payload.get("payload"), dict):
            raise TransactionRecoveryError("Transaction journal payload must be an object.")
