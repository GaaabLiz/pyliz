# Snappy migration to the pylizlib configuration API

Update Snappy's `pylizlib` dependency to a revision that provides
`SnapshotCatalogue.create_snapshot()` and `SnapshotCatalogue.update_snapshot()`.
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
new = self.dash_model.snap_catalogue.update_snapshot(
    snap.id,
    name=raw_data["name"],
    desc=raw_data["desc"],
    tags=raw_data["tags"],
    directory_paths=raw_data["directories"],
    data_updates=raw_data["custom_data"],
    message_callback=task.update_task_message,
)
```

Both methods save the snapshot and return the resulting `Snapshot`. Use
`new.name` for the existing success log. Keep the existing automatic backup
log after the edit succeeds. The edit target is `snap.id`; the ID displayed
in the form is used only when creating a snapshot.

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

## Snappy tests

Test the controller's mapping from form values to catalogue arguments,
including the correct ID and callbacks. Verify that success logging happens
after the catalogue call returns. Association IDs, path matching, custom
data merges, and capture metadata are covered by pylizlib tests.
