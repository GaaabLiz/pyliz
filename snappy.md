# Snappy migration to the pylizlib snapshot APIs

Update Snappy's `pylizlib` dependency to a revision that provides
`SnapshotCatalogue.create_snapshot()`, `SnapshotCatalogue.update_snapshot_with_result()`,
and `SnapshotCatalogue.get_statistics()`.
Use the catalogue already available as `self.dash_model.snap_catalogue`; its
live settings control association ID length and the existing backup policy.

## Controller changes

In `snappy/controller/catalogue.py`, update the worker actions in
`__open_config_dialog()`. Keep the dialog payload, worker setup, translated
messages, action logging, and dashboard refresh.

For creation, replace the builder and `catalogue.add()` with:

```python
from pylizlib.core.os.system import get_system_username

# Inside the create action:
new = self.dash_model.snap_catalogue.create_snapshot(
    snap_id=raw_data["id"],
    name=raw_data["name"],
    desc=raw_data["desc"],
    author=get_system_username(),
    tags=raw_data["tags"],
    directory_paths=raw_data["directories"],
    data=raw_data["custom_data"],
    progress_callback=task.update_task_progress,
    message_callback=task.update_task_message,
)
```

For editing, replace the builder and `catalogue.update_snapshot_by_objs()`
with:

```python
# Inside the edit action:
result = self.dash_model.snap_catalogue.update_snapshot_with_result(
    snap.id,
    name=raw_data["name"],
    desc=raw_data["desc"],
    tags=raw_data["tags"],
    directory_paths=raw_data["directories"],
    data_updates=raw_data["custom_data"],
    message_callback=task.update_task_message,
)
new = result.snapshot
self.__log_automatic_backup(snap, result.backup_path, "edit")
```

Both methods save the snapshot. Creation returns the `Snapshot` directly;
the edit result exposes it as `result.snapshot`. Use `new.name` for the
existing success log. The edit target is `snap.id`; the ID displayed in the
form is used only when creating a snapshot.

## Remove the old builder

Delete `build_snapshot_from_raw()` from `snappy/model/catalogue.py` once
its callers use the new methods. Remove the imports used only by that helper.
Keep the form's snapshot ID generation, field validation, authorship lookup
and custom field selection in Snappy.

## Editing rules

- Omit an argument or pass `None` to keep its stored value. Use `desc=""` or
  `tags=[]` to clear those fields.
- `directory_paths` is the complete ordered list whenever provided. If the
  form can tell that the directory list was untouched, omit the argument for
  that edit. An explicit empty list removes all stored associations. Updating
  associations edits the catalogue; it does not remove the original folders.
- Pass paths as `str` or `Path`. Pylizlib matches by filesystem identity.
  Retained entries keep their stored path, ID, copy and integrity metadata.
  New entries receive new IDs and their contents are captured. A duplicate
  path or a path that matches multiple legacy associations raises `ValueError`.
- Pass only custom values the form supplies in `data_updates`. Hidden keys
  are preserved. An empty string is a value. Pass `data_remove=["key"]` only
  for an explicit deletion. If both arguments contain a key, its new value wins.
- In `snappy/view/catalogue_imp_tab_directories.py`, use
  `pylizlib.core.os.paths.identity.same_filesystem_entry()` for the folder
  picker's duplicate check on absolute native paths. If the view compares
  the current selection with the initial selection to detect edits, compare
  lengths and then corresponding paths with the same helper. Using sets
  loses changes in order.

## Automatic backups in action history

In `snappy/controller/catalogue.py`, use the operation result instead of
reading the backup settings to decide whether to log a backup. Keep the
existing worker callbacks and other success events.

| Controller action | Catalogue method |
|---|---|
| Install snapshot | `install_with_result(snap, ...)` |
| Edit configuration | `update_snapshot_with_result(snap.id, ...)` |
| Delete snapshot | `delete_with_result(snap, ...)` |
| Update stored copies with local contents | `sync_with_result(snap.id, ...)` |
| Remove installed copies | `remove_installed_copies_with_result(snap.id, ...)` |

Change the existing helper to take the path:

```python
from pathlib import Path

@staticmethod
def __log_automatic_backup(snap: Snapshot, backup_path: Path | None, operation: str):
    if backup_path is not None:
        log_action(
            ActionCategory.BACKUPS,
            ActionType.BACKUP_CREATED,
            f"snapshot={snap.name}; before={operation}; archive={backup_path.name}",
        )
```

After each successful call, pass `result.backup_path` to the helper. A
successful install that recreated all its destinations has no backup to
log. A partial backup of existing destinations does have a path. If an
operation raises, keep the normal error flow. A backup that finished before
a later failure may still be on disk and the failed call has no result.

## Home and catalogue statistics

In `snappy/model/snappy_update.py`, use the existing `TaskGetSnapshots`
worker to load both the snapshot list and the catalogue statistics:

```python
snapshots = self.catalogue.get_all()
self.home_statistics = self.catalogue.get_statistics(include_backups=False)
return snapshots
```

`get_all()` supplies the list used by the catalogue and search. The second
call returns a `SnapshotCatalogueStatistics` summary and reads catalogue
metadata itself. Forward the result through the existing dashboard refresh
payload. Remove `SnappySnapshotData.compute_home_statistics()` and its callers'
filesystem scans. Keep formatting and unavailable states in the Home model
or view. If the statistics query fails, log it in the worker and publish the
snapshot list with `home_statistics=None` for that refresh. Reset this field
on each run so a failed refresh cannot display stale values.

| Snappy display | Library value |
|---|---|
| Snapshot count | `stats.snapshot_count` |
| Total size | `stats.total_size_bytes` |
| Average snapshot size | `stats.average_snapshot_size_bytes` (float in bytes) |
| Total files and directories | `stats.file_count` and `stats.directory_count` |
| Largest file | `stats.largest_file.size_bytes` and `PurePosixPath(stats.largest_file.relative_path).name` when present |
| Oldest and latest snapshot | `stats.oldest_snapshot_date` and `stats.newest_snapshot_date` (optional datetimes) |
| Catalogue path | `str(stats.catalogue_path)` |

Sizes are logical bytes of captured files. Directory totals include
association roots and empty folders. The largest file is identified by
`snapshot_id`, `folder_id` and a POSIX path relative to the stored association.
Render `None` dates or largest file as empty values. Reuse the same summary
for the catalogue footer's count and size when it displays the whole
catalogue. If only the total snapshot count is needed on a separate refresh,
`catalogue.get_snapshot_count()` reads snapshot metadata without counting
files or backups.

The Home card currently counts managed AD and SD backups. To keep that
meaning, use `include_backups=False` as shown above and move the existing
`catalogue.list_backups(backup_path)` filter from `snappy/model/home.py` into
the worker. Keep entries of type `BackupType.ASSOCIATED_DIRECTORIES` or
`BackupType.SNAPSHOT_DIRECTORY` with a creation date and snapshot ID, and
exclude exports. Pass the count through the refresh payload and preserve the
unavailable state on errors. An unset or missing backup directory has a count
of zero. For a card that counts every recognized ZIP in
`SnapshotSettings.backup_path`, use `catalogue.get_statistics().backup_count`
or `catalogue.get_backup_count()` when only that count is needed. These counts
can include exports and unrelated ZIPs. With `include_backups=False` the
summary's `backup_count` is `None`.

## Snappy tests

Test the controller's mapping from form values to catalogue arguments,
including the correct ID and callbacks. Verify that success logging happens
after the catalogue call returns. Association IDs, path matching, custom
data merges, and capture metadata are covered by pylizlib tests.
For the Home refresh, test the field mapping, empty and unavailable states,
and the managed backup filter if that count remains in the UI.
For the action history, verify that `backup_path=None` emits no backup
event and that a returned archive path emits one.
