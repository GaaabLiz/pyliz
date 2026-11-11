"""Random example snapshots retaining the public generators and index semantics."""

from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot


def gen_random_snap(source_folder_for_choices: Path, id_length: int = 10) -> Snapshot:
    """
    Generates a random Snapshot instance for testing or demonstration purposes.

    Args:
        source_folder_for_choices: The path to a directory from which to pick random subdirectories.
        id_length: The length of the random string to be used for the snapshot's ID and name.

    Returns:
        A new Snapshot object with randomly generated data.
    """
    dirs = SnapDirAssociation.gen_random_list(3, source_folder_for_choices)
    return Snapshot(
        id=gen_random_string(id_length),
        name="Snapshot " + gen_random_string(id_length),
        desc="Randomly generated snapshot",
        author="User",
        directories=dirs,
        tags=["example", "test"],
    )
