"""Shared association decoding with explicit modern/legacy error vocabulary."""

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST, ArchivedAssociation


@dataclass(frozen=True)
class AssociationManifestPolicy:
    """Name format-specific validation messages without changing accepted values.

    Attributes:
        subject (str): Prefix for field/index/path errors.
        entry_error (str): Error for a non-object association entry.
        identity_error (str): Error for a missing/non-string association ID.
        directory_label (str): Field label passed to the component validator.
        reserved_error (str): Error for a reserved manifest name used as a directory.
        duplicate_error (str): Error for duplicate association IDs or storage names.
    """

    subject: str
    entry_error: str
    identity_error: str
    directory_label: str
    reserved_error: str
    duplicate_error: str


MODERN_ASSOCIATIONS = AssociationManifestPolicy(
    "Snapshot backup manifest",
    "Snapshot backup manifest association entries must be objects.",
    "Snapshot backup manifest contains an invalid association ID.",
    "backup association directory name",
    "Snapshot backup manifest name conflicts with an association directory.",
    "Snapshot backup manifest contains duplicate association IDs or names.",
)
LEGACY_ASSOCIATIONS = AssociationManifestPolicy(
    "Associated-directories manifest",
    "Associated-directories manifest entries must be objects.",
    "Associated-directories manifest contains an invalid folder ID.",
    "archive association directory name",
    "Associated-directories manifest name conflicts with an archived association.",
    "Associated-directories manifest contains duplicate association identities or names.",
)


def parse_associations(raw_associations: object, policy: AssociationManifestPolicy) -> list[ArchivedAssociation]:
    """Decode association entries using common rules and format-specific messages.

    Args:
        raw_associations (object): Decoded associations field; must be a list of objects.
        policy (AssociationManifestPolicy): Vocabulary belonging to the manifest format.

    Returns:
        list[ArchivedAssociation]: Associations in archive order, with original lexical
        path spellings and unique IDs/storage names. Inputs are not normalized.

    Raises:
        ValueError: If the list or an entry is invalid. Validation order remains ID,
            index, directory name, source path, then duplicate identity/name checks.
    """
    if not isinstance(raw_associations, list):
        raise ValueError(f"{policy.subject} has no association list.")
    associations = []
    seen_ids = set()
    seen_names = set()
    for raw in raw_associations:
        if not isinstance(raw, dict):
            raise ValueError(policy.entry_error)
        folder_id = raw.get("folder_id")
        index = raw.get("index")
        directory_name = raw.get("directory_name")
        original_path = raw.get("original_path")

        # Keep field checks ordered: callers rely on the first invalid field reported.
        if not isinstance(folder_id, str) or not folder_id:
            raise ValueError(policy.identity_error)
        if type(index) is not int or index < 0:
            raise ValueError(f"{policy.subject} contains an invalid index for '{folder_id}'.")
        validate_directory_component(directory_name, policy.directory_label)
        if directory_name in {BACKUP_MANIFEST_NAME, LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST}:
            raise ValueError(policy.reserved_error)
        if not isinstance(original_path, str) or not original_path or "\x00" in original_path:
            raise ValueError(f"{policy.subject} contains an invalid original path for '{folder_id}'.")
        if not Path(original_path).is_absolute() and not PureWindowsPath(original_path).is_absolute():
            raise ValueError(f"{policy.subject} path for '{folder_id}' must be absolute.")

        # Duplicate checks follow all field checks and preserve the input order.
        if folder_id in seen_ids or directory_name in seen_names:
            raise ValueError(policy.duplicate_error)
        seen_ids.add(folder_id)
        seen_names.add(directory_name)
        associations.append(ArchivedAssociation(folder_id, index, directory_name, original_path))
    return associations
