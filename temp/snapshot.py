from pathlib import Path

from pylizlib.core.os.snap import SnapshotCatalogue, SnapshotUtils, SnapDirAssociation

path_catalogue = Path(r"C:\Users\Gabriele\devliz\Catalogue")
path_temp = Path(r"C:\Users\Gabriele\Pictures\LibTest.library\images")

snap = SnapshotUtils.gen_random_snap(path_temp)
snap.add_data_item("ExtraField1", "ExtraValue1")
snap.add_data_item("ExtraField2", "ExtraValue2")

dirs_new = SnapDirAssociation.gen_random_list(1, path_temp)

snap_edit = snap.clone()
snap_edit.desc = "edited description"
snap_edit.directories = dirs_new


catalogue = SnapshotCatalogue(path_catalogue)
catalogue.add(snap)

catalogue.update_snapshot_by_objs(snap, snap_edit)

# snap_found.add_data_item("ExtraField3", "ExtraValue3")
# snap_found.edit_data_item("ExtraField2", "ExtraValue2-Edited")
# snap_found.desc = "Snapshot Edited"
# snap_edit_new_dir = SnapEditAction(new_path=random_subfolder(path_temp).__str__(), action_type=SnapEditType.ADD_DIR)
# catalogue.update_snapshot(snap_found, [snap_edit_new_dir])


