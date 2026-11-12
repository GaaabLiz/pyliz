"""Random example snapshots retaining the public generators and index semantics."""

from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.filesystem.directories import random_subfolder
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot


def gen_random_snap(source_folder_for_choices: Path, id_length: int = 10) -> Snapshot:
    """Generates a random Snapshot instance for testing or demonstration purposes.

    Args:
        source_folder_for_choices (Path): The path to a directory from which to pick random subdirectories.
        id_length (int): The length of the random string to be used for the snapshot's ID and name.

    Returns:
        Snapshot: A new Snapshot object with randomly generated data.
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


def gen_random_association(
    source_folder_for_choices: Path,
    folder_id_length: int = 4,
) -> "SnapDirAssociation":
    """Generates a single, random SnapDirAssociation for testing purposes.

    Args:
        source_folder_for_choices (Path): A directory from which a random subfolder will be chosen.
        folder_id_length (int): The length of the random `folder_id`.

    Returns:
        SnapDirAssociation: A new `SnapDirAssociation` instance with random data.
    """
    return SnapDirAssociation(
        index=SnapDirAssociation.next_index(),
        original_path=random_subfolder(source_folder_for_choices).__str__(),
        folder_id=gen_random_string(folder_id_length),
    )


def gen_random_association_list(count: int, source_folder_for_choices: Path) -> list["SnapDirAssociation"]:
    """Generates a list of random SnapDirAssociation objects for testing.

    Args:
        count (int): The number of associations to generate.
        source_folder_for_choices (Path): The directory from which random subfolders will be chosen.

    Returns:
        list['SnapDirAssociation']: A list of new `SnapDirAssociation` instances.
    """
    return [SnapDirAssociation.gen_random(source_folder_for_choices) for _ in range(count)]
