"""Compatibility codecs for associated-directory manifests predating unified backups."""

from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.operations.backup_manifest import LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST_FORMAT, ArchivedAssociation


def parse_legacy_associations_manifest(data: object) -> tuple[str, str | None, list[ArchivedAssociation]]:
    """Read a version 1 or 2 AD manifest written before the unified backup format.

    Args:
        data (object): Decoded JSON value or metadata mapping; fields are validated without implicit schema
            coercion.

    Returns:
        tuple[str, str | None, list[ArchivedAssociation]]: Legacy snapshot ID, optional origin OS and ordered
            association records, retaining v1/v2 acceptance rules.

    Raises:
        ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
    """
    if not isinstance(data, dict) or data.get("format") != LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST_FORMAT or type(data.get("version")) is not int or data["version"] not in {1, 2}:
        raise ValueError("Unsupported or invalid associated-directories manifest format.")
    origin_os = data.get("os_created")
    if origin_os is not None and (not isinstance(origin_os, str) or not origin_os):
        raise ValueError("Associated-directories manifest contains an invalid originating OS.")
    if data["version"] == 2 and origin_os is None:
        raise ValueError("Associated-directories manifest does not record its originating OS.")
    snapshot_id = data.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("Associated-directories manifest has no snapshot ID.")
    validate_directory_component(snapshot_id, "backup snapshot ID")
    from pylizlib.core.os.snap.operations.backup.associations import LEGACY_ASSOCIATIONS, parse_associations

    associations = parse_associations(data.get("associations"), LEGACY_ASSOCIATIONS)
    return snapshot_id, origin_os, associations
