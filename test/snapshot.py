from pathlib import Path

from pylizlib.core.os.snap import Snapshot, SnapshotCatalogue, SnapshotUtils

path_catalogue = Path("/Users/gabliz/Documents/Test/Dev Tests")
path_temp = Path("/Users/gabliz/Documents/Test/eagleTest/test.library/images")

snap = SnapshotUtils.gen_random(path_temp)
snap.add_data_item("ExtraField1", "ExtraValue1")
snap.add_data_item("ExtraField2", "ExtraValue2")


catalogue = SnapshotCatalogue(path_catalogue)
catalogue.add(snap)

list_snaps = catalogue.get_all()

print(list_snaps)