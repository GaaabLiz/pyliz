from pathlib import Path

from pylizlib.core.os.path import random_subfolder
from pylizlib.core.os.snap import Snapshot, SnapshotCatalogue, SnapshotUtils, SnapEditAction, SnapEditType

path_catalogue = Path("/Users/gabliz/Documents/Test/Dev Tests")
path_temp = Path("/Users/gabliz/Documents/Test/eagleTest/test.library/images")

snap = SnapshotUtils.gen_random_snap(path_temp)
snap.add_data_item("ExtraField1", "ExtraValue1")
snap.add_data_item("ExtraField2", "ExtraValue2")


catalogue = SnapshotCatalogue(path_catalogue)
catalogue.add(snap)

list_snaps = catalogue.get_all()

snap_found = catalogue.get_by_id(snap.id)
snap_found.add_data_item("ExtraField3", "ExtraValue3")
snap_found.edit_data_item("ExtraField2", "ExtraValue2-Edited")
snap_found.desc = "Snapshot Edited"
snap_edit_new_dir = SnapEditAction(new_data=random_subfolder(path_temp).__str__(), action_type=SnapEditType.ADD_DIR)
catalogue.update_snapshot(snap_found, [snap_edit_new_dir])


print(list_snaps)