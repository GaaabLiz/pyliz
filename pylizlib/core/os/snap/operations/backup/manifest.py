"""Compatibility codecs for associated-directory manifests predating unified backups."""

from pathlib import Path, PureWindowsPath

from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST_FORMAT, ArchivedAssociation
from pylizlib.core.os.snap.operations.backup_manifest import LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST as ASSOCIATED_DIRECTORIES_MANIFEST


def parse_legacy_associations_manifest(data: object) -> tuple[str, str | None, list[ArchivedAssociation]]:
    """Read a version 1 or 2 AD manifest written before the unified backup format."""
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
    raw_associations = data.get("associations")
    if not isinstance(raw_associations, list):
        raise ValueError("Associated-directories manifest has no association list.")

    associations = []
    seen_ids = set()
    seen_names = set()
    for raw in raw_associations:
        if not isinstance(raw, dict):
            raise ValueError("Associated-directories manifest entries must be objects.")
        folder_id = raw.get("folder_id")
        index = raw.get("index")
        directory_name = raw.get("directory_name")
        original_path = raw.get("original_path")
        if not isinstance(folder_id, str) or not folder_id:
            raise ValueError("Associated-directories manifest contains an invalid folder ID.")
        if type(index) is not int or index < 0:
            raise ValueError(f"Associated-directories manifest contains an invalid index for '{folder_id}'.")
        validate_directory_component(directory_name, "archive association directory name")
        if directory_name in {BACKUP_MANIFEST_NAME, ASSOCIATED_DIRECTORIES_MANIFEST}:
            raise ValueError("Associated-directories manifest name conflicts with an archived association.")
        if not isinstance(original_path, str) or not original_path or "\x00" in original_path:
            raise ValueError(f"Associated-directories manifest contains an invalid original path for '{folder_id}'.")
        if not Path(original_path).is_absolute() and not PureWindowsPath(original_path).is_absolute():
            raise ValueError(f"Associated-directories manifest path for '{folder_id}' must be absolute.")
        if folder_id in seen_ids or directory_name in seen_names:
            raise ValueError("Associated-directories manifest contains duplicate association identities or names.")
        seen_ids.add(folder_id)
        seen_names.add(directory_name)
        associations.append(ArchivedAssociation(folder_id, index, directory_name, original_path))
    return snapshot_id, origin_os, associations
