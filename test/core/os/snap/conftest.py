"""
Shared fixtures and helpers for the snap test package.

All test modules in this package import from here to keep setup/teardown
logic in a single place and avoid repetition.
"""

import shutil
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap import (
    SnapDirAssociation,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.testing.sample_downloader import SampleImageDownloader

# ---------------------------------------------------------------------------
# Root paths
# ---------------------------------------------------------------------------
TEST_ROOT = Path(__file__).parent.parent.parent.parent          # test/
TEST_LOCAL_ROOT = TEST_ROOT.parent / "test_local" / "snap_tests"
CATALOGUE_PATH = TEST_LOCAL_ROOT / "catalogue"
SOURCE_DATA_PATH = TEST_LOCAL_ROOT / "source_data"
INSTALL_DEST_PATH = TEST_LOCAL_ROOT / "install_dest"
BACKUP_PATH = TEST_LOCAL_ROOT / "backups"

# Shared image cache — downloaded once per session
_IMAGE_CACHE = TEST_ROOT.parent / "test_local" / "_img_cache"
downloader = SampleImageDownloader(cache_dir=_IMAGE_CACHE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def reset_index() -> None:
    """Resets the SnapDirAssociation class-level index counter to 0."""
    SnapDirAssociation._current_index = 0


def create_source_dirs(base: Path, names: list[str], with_images: bool = False) -> list[Path]:
    """
    Creates source directories under *base*, optionally populating them with
    downloaded sample images.  Returns the list of created paths.
    """
    dirs: list[Path] = []
    for name in names:
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        if with_images:
            downloader.download_images_to_folder(d, count=2, seeds=[f"{name}_a", f"{name}_b"])
        else:
            (d / f"{name}_file.txt").write_text(f"content of {name}", encoding="utf-8")
        dirs.append(d)
    return dirs


def make_snapshot(name: str, source_dirs: list[Path], n: int = 2) -> Snapshot:
    """
    Builds a Snapshot from the first *n* source directories.

    Args:
        name: The display name for the snapshot.
        source_dirs: A list of source directory paths.
        n: How many directories to include.

    Returns:
        A new Snapshot instance.
    """
    reset_index()
    dirs = []
    for d in source_dirs[:n]:
        dirs.append(
            SnapDirAssociation(
                index=SnapDirAssociation.next_index(),
                original_path=str(d),
                folder_id=gen_random_string(6),
            )
        )
    return Snapshot(
        id=gen_random_string(10),
        name=name,
        desc=f"Description for {name}",
        author="TestSuite",
        directories=dirs,
        tags=["test"],
    )


def setup_test_dirs() -> None:
    """Creates all standard test directories."""
    for d in (TEST_LOCAL_ROOT, CATALOGUE_PATH, SOURCE_DATA_PATH, INSTALL_DEST_PATH, BACKUP_PATH):
        d.mkdir(parents=True, exist_ok=True)


def teardown_test_dirs() -> None:
    """Removes the entire test local root."""
    shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)
