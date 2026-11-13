"""Stable-identity comparison of snapshot directory associations."""

from pylizlib.core.os.snap.domain import SnapEditAction, SnapEditType, Snapshot


def get_edits_between_snapshots(old: Snapshot, new: Snapshot) -> list[SnapEditAction]:
    """Compares associations by stable folder_id and generates add/remove/rename actions
    required to transform the old snapshot into the new one.

    Args:
        old (Snapshot): The original Snapshot object.
        new (Snapshot): The updated Snapshot object.

    Returns:
        list[SnapEditAction]: A list of SnapEditAction objects representing the changes.

    Raises:
        ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
    """
    edits: list[SnapEditAction] = []

    # Paths are not identities: distinct associations may share a source, and
    # one source may have multiple spellings on case-insensitive or aliased filesystems.
    old_by_id = {assoc.folder_id: assoc for assoc in old.directories}
    new_by_id = {assoc.folder_id: assoc for assoc in new.directories}
    if len(old_by_id) != len(old.directories) or len(new_by_id) != len(new.directories):
        raise ValueError("Snapshot associations must have unique folder IDs.")

    for assoc in new.directories:
        if assoc.folder_id not in old_by_id:
            edits.append(SnapEditAction(action_type=SnapEditType.ADD_DIR, new_path=assoc.original_path, folder_id=assoc.folder_id))

    for assoc in old.directories:
        if assoc.folder_id in new_by_id:
            continue
        edits.append(
            SnapEditAction(
                action_type=SnapEditType.REMOVE_DIR,
                folder_id_to_remove=assoc.folder_id,
                directory_name_to_remove=assoc.directory_name,
                folder_id=assoc.folder_id,
            )
        )

    for old_assoc in old.directories:
        new_assoc = new_by_id.get(old_assoc.folder_id)
        if new_assoc is None:
            continue
        if old_assoc.directory_name != new_assoc.directory_name:
            edits.append(
                SnapEditAction(
                    action_type=SnapEditType.RENAME_DIR,
                    old_directory_name=old_assoc.directory_name,
                    new_directory_name=new_assoc.directory_name,
                    folder_id=old_assoc.folder_id,
                )
            )

    return edits
