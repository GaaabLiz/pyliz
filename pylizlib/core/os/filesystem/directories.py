"""Directory creation, traversal, inspection and copy helpers."""

import os
import random
import shutil
import tempfile
from pathlib import Path
from typing import Callable, List, LiteralString, Optional

from pylizlib.core.data import gen
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.filesystem.file_types import is_image_file, is_video_file


def create_path(path):
    """Create a directory path if it does not exist.

    Args:
        path (str | Path): Directory path to create.

    Returns:
        None: The directory exists after the call.
    """
    if not os.path.exists(path):
        os.makedirs(path)


def check_path(path, create_if_not: bool = False) -> bool:
    """Check whether a path exists and is readable.

    Args:
        path (str | Path): Path to check.
        create_if_not (bool): Create a missing directory before returning False.

    Returns:
        bool: Whether the path exists and is readable.
    """
    if not os.path.exists(path):
        if create_if_not:
            os.makedirs(path)
            return False
        else:
            return False
    if not os.access(path, os.R_OK):
        return False
    return True


def check_path_dir(path):
    """Require an existing directory that is readable and writable.

    Args:
        path (str | Path): Directory path to validate.

    Returns:
        None: The directory satisfies the access checks.

    Raises:
        IOError: The path does not exist.
        PermissionError: The directory cannot be read or written.
        NotADirectoryError: The path is not a directory.
    """

    # Check if the path exists and is readable
    if not os.path.exists(path):
        raise IOError(f"Path {path} does not exist!")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"Path {path} is not readable!")
    if not os.access(path, os.W_OK):
        raise PermissionError(f"Path {path} is not writable!")

    # Check if the path is a directory
    if not os.path.isdir(path):
        raise NotADirectoryError(f"Path {path} is not a directory!")
    if not os.access(path, os.W_OK):
        raise PermissionError(f"Path {path} is not writable!")


def check_path_file(path: str):
    """Require an existing file that is readable and writable.

    Args:
        path (str | Path): File path to validate.

    Returns:
        None: The file satisfies the access checks.

    Raises:
        FileNotFoundError: The file does not exist.
        PermissionError: The file cannot be read or written.
        NotADirectoryError: The path is not a file.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File {path} does not exist!")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"File {path} is not readable!")
    if not os.access(path, os.W_OK):
        raise PermissionError(f"File {path} is not writable!")
    if not os.path.isfile(path):
        raise NotADirectoryError(f"Path {path} is not a file!")


def count_pathsub_files(path):
    """Count files beneath a path, including files in subdirectories.

    Args:
        path (str | Path): Root path to scan.

    Returns:
        int: Number of files found by the recursive walk.
    """
    count = 0
    for root, dirs, files in os.walk(path):
        count += len(files)
    return count


def count_pathsub_dirs(path):
    """Count subdirectories beneath a path.

    Args:
        path (str | Path): Root path to scan.

    Returns:
        int: Number of subdirectories found by the recursive walk.
    """
    count = 0
    for root, dirs, files in os.walk(path):
        count += len(dirs)
    return count


def count_pathsub_elements(path):
    """Count files and subdirectories beneath a path.

    Args:
        path (str | Path): Root path to scan.

    Returns:
        int: Combined number of files and subdirectories found recursively.
    """
    count = 0
    for root, dirs, files in os.walk(path):
        count += len(files) + len(dirs)
    return count


def scan_directory(path: str, on_file, on_folder):
    """Walk a directory and call callbacks with each discovered item path.

    Args:
        path (str | Path): Root directory to scan recursively.
        on_file (Callable[[str], object]): Callback for each file path.
        on_folder (Callable[[str], object]): Callback for each folder path.

    Returns:
        None: All callbacks have been invoked for the discovered entries.
    """
    for root, dirs, files in os.walk(path):
        for file in files:
            on_file(os.path.join(root, file))
        for dir in dirs:
            on_folder(os.path.join(root, dir))


def scan_directory_match_bool(path: str, to_be_add: Callable[[str], bool]) -> List[str]:
    """Return file paths accepted by a predicate during a recursive scan.

    Args:
        path (str | Path): Root directory to scan recursively.
        to_be_add (Callable[[str], bool]): Predicate deciding whether to keep a file path.

    Returns:
        list[str]: Paths accepted by the predicate in traversal order.
    """
    matching_files = []
    for root, dirs, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            if to_be_add(file_path):
                matching_files.append(file_path)
    return matching_files


def dir_contains_image(path: str):
    """Check whether a directory tree contains an image file.

    Args:
        path (str | Path): Directory to scan.

    Returns:
        bool: Whether any file has a supported image extension.
    """
    files = scan_directory_match_bool(path, is_image_file)
    return len(files) > 0


def dir_contains_video(path: str):
    """Check whether a directory tree contains a video file.

    Args:
        path (str | Path): Directory to scan.

    Returns:
        bool: Whether any file has a supported video extension.
    """
    files = scan_directory_match_bool(path, is_video_file)
    return len(files) > 0


def dir_contains(directory: str, names: list[str], at_least_one: bool = False) -> bool:
    """Check for named direct children in a directory.

    Args:
        directory (str | Path): Directory whose direct entries should be checked.
        names (list[str]): Entry names to look for.
        at_least_one (bool): Return True when any requested name exists instead of requiring all names.

    Returns:
        bool: Whether the requested presence rule is satisfied.
    """
    check_path_dir(directory)
    found = 0
    for folder_name in names:
        current = os.path.join(directory, folder_name)
        if os.path.exists(current):
            found += 1
    if at_least_one:
        return found > 0
    return found == len(names)


def get_folders_from(directory, recursive: bool = False) -> list[LiteralString | str | bytes]:
    """List folder paths directly below a directory or throughout its tree.

    Args:
        directory (str | Path): Directory to inspect.
        recursive (bool): Include folders nested at any depth when True.

    Returns:
        list[str | bytes]: Folder paths in the selected traversal scope.
    """
    if recursive:
        return [os.path.join(root, d) for root, dirs, files in os.walk(directory) for d in dirs]
    return [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]


def get_files_from(
    directory,
    recursive: bool = False,
    extension: Optional[str] = None,
) -> list[LiteralString | str | bytes]:
    """List file paths directly below a directory or throughout its tree.

    Args:
        directory (str | Path): Directory to inspect.
        recursive (bool): Include files nested at any depth when True.
        extension (str | None): Optional suffix required for returned file paths.

    Returns:
        list[str | bytes]: Matching file paths in traversal order.
    """
    db = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            for file in files:
                db.append(os.path.join(root, file))
    else:
        db = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    if extension is not None:
        return [f for f in db if f.endswith(extension)]
    return db


def get_path_items(path: Path, recursive: bool = False) -> list[Path]:
    """List entry paths below a directory, optionally including descendants.

    Args:
        path (Path): Directory whose entries should be listed.
        recursive (bool): Include descendants of child directories when True.

    Returns:
        list[Path]: Entry paths in scan order; entries blocked by permissions are skipped.
    """
    items = []

    with os.scandir(path) as entries:
        for entry in entries:
            try:
                entry_path = Path(entry.path)
                items.append(entry_path)

                if recursive and entry.is_dir(follow_symlinks=False):
                    items.extend(get_path_items(entry_path, recursive=True))
            except PermissionError:
                continue

    return items


def remove_directory_or_move_to_temp(path: Path, temp_path: Path | None = None, move_to_temp: bool = False, message_callback=None):
    """Remove a directory or move it to a temporary location.

    WARNING: By default, this permanently deletes the directory using shutil.rmtree.
    If you need to preserve data temporarily for rollback, set move_to_temp=True.

    Args:
        path (Path): Directory path to remove or move.
        temp_path (Path | None): Temporary subdirectory name used when moving the source.
        move_to_temp (bool): Move the directory to temporary storage instead of deleting it.
        message_callback (Callable[[str], object] | None): Optional progress callback receiving status messages.

    Returns:
        None: The requested removal or move has completed, or a missing source was ignored.

    Raises:
        OSError: The requested removal or move fails.
    """
    if not move_to_temp:
        try:
            path.lstat()
        except FileNotFoundError:
            return
        if message_callback:
            if not path.is_symlink():
                for root, dirs, files in os.walk(path, topdown=False, followlinks=False):
                    for name in files:
                        message_callback(f"Eliminazione: {name}")
                    for name in dirs:
                        message_callback(f"Eliminazione: {name}")
            message_callback(f"Eliminazione: {path.name}")

        # Unlink a root symlink itself, including a dangling link.
        if path.is_symlink():
            path.unlink(missing_ok=True)
        else:
            shutil.rmtree(path.__str__())
    else:
        if temp_path is None:
            logger.error("Temp path cannot be None")
            return
        temp_dir = tempfile.gettempdir()
        atom_temp_dir = os.path.join(temp_dir, temp_path.__str__())
        os.makedirs(atom_temp_dir, exist_ok=True)
        dest_name = os.path.basename(path.__str__() + "_" + gen.gen_random_string(10))
        dest_path = os.path.join(atom_temp_dir, dest_name)
        if message_callback:
            message_callback(f"Spostamento: {path.name}")
        shutil.move(path, dest_path)


def random_subfolder(path: Path) -> Path:
    """Choose a direct child directory at random.

    Args:
        path (Path): Parent directory whose child directories are candidates.

    Returns:
        Path | None: A randomly selected child directory, or None when no child directory exists.
    """
    subdirs = [p for p in path.iterdir() if p.is_dir()]
    if not subdirs:
        return None
    return random.choice(subdirs)


def clear_folder_contents(path: Path):
    """Remove the direct contents of a folder while preserving the folder itself.

    Args:
        path (Path): Directory whose contents should be removed.

    Returns:
        None: The folder remains in place after cleanup.

    Raises:
        NotADirectoryError: The path is not a directory.
    """
    if not path.is_dir():
        raise NotADirectoryError(f"The provided path {path} is not a directory.")
    for item in path.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            logger.error(f"Error deleting {item}: {e}")


def count_items(dir_path: Path) -> int:
    """Count direct entries in a directory.

    Args:
        dir_path (Path): Directory whose direct entries should be counted.

    Returns:
        int: Number of direct children.

    Raises:
        ValueError: The path is not an existing directory.
    """
    if not dir_path.is_dir():
        raise ValueError(f"{dir_path!r} non è una directory valida")
    return sum(1 for _ in dir_path.iterdir())


def duplicate_directory(src_dir: Path, dest_dir: Path | None = None, copy_suffix: str = "_copy", message_callback=None) -> Path:
    """Copy a directory tree and return the new destination path.

    If ``dest_dir`` is omitted, the copy is a sibling named by appending
    ``copy_suffix`` to the source directory name.

    Args:
        src_dir (Path): Existing directory tree to copy.
        dest_dir (Path | None): Optional destination path for the copy.
        copy_suffix (str): Suffix used for a default sibling destination.
        message_callback (Callable[[str], object] | None): Optional callback receiving each copied file name.

    Returns:
        Path: Path to the completed copy.

    Raises:
        ValueError: The source is not a directory or the destination is inside the source.
        FileExistsError: The destination already exists.
    """
    if not src_dir.is_dir():
        raise ValueError(f"{src_dir!r} non è una directory valida")

    # Se non specificato, costruisce dest_dir affiancata a src_dir
    if dest_dir is None:
        dest_dir = src_dir.with_name(src_dir.name + copy_suffix)

    resolved_src = src_dir.resolve(strict=True)
    resolved_dest = dest_dir.resolve(strict=False)
    if resolved_dest == resolved_src or resolved_src in resolved_dest.parents:
        raise ValueError("The destination directory cannot be the source or one of its descendants")

    # Assicura che la destinazione non esista già
    if dest_dir.exists():
        raise FileExistsError(f"{dest_dir!r} esiste già")

    def copy_with_cb(src, dst, *, follow_symlinks=True):
        """Copy one file entry and report it to the optional progress callback.

        Args:
            src (str | Path): Source file path.
            dst (str | Path): Destination file path.
            follow_symlinks (bool): Whether ``copy2`` follows a source symlink.

        Returns:
            None: The file metadata and contents have been copied.
        """
        if message_callback:
            message_callback(f"Copia in corso: {Path(src).name}")
        shutil.copy2(src, dst, follow_symlinks=follow_symlinks)

    # Copia ricorsivamente la directory
    shutil.copytree(src_dir, dest_dir, copy_function=copy_with_cb)
    return dest_dir


class PathMatcher:
    """Load directory-relative paths and compare them with saved path lists."""

    def __init__(self):
        """Initialize an empty path comparison state.

        Returns:
            None: No path has been loaded yet.
        """
        self.working_path_items_rel = None
        self.working_path_items = None
        self.working_path = None

    def load_path(self, path: Path, recursive: bool = False):
        """Load path entries and retain their names relative to the root.

        Args:
            path (Path): Directory to scan.
            recursive (bool): Include descendant entries when True.

        Returns:
            None: The matcher stores the paths and relative names.
        """
        self.working_path = path
        self.working_path_items = get_path_items(path, recursive)
        self.working_path_items_rel = [str(p.relative_to(self.working_path)) for p in self.working_path_items]

    def match_with_list(self, path_str_list: list[str]):
        """Compare the loaded relative paths with another path list.

        Args:
            path_str_list (list[str]): Relative path names to compare against.

        Returns:
            tuple[int, float]: Intersection count and intersection-over-union percentage.
        """
        set1, set2 = set(self.working_path_items_rel), set(path_str_list)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        perc = (intersection / union) * 100 if union > 0 else 100
        return intersection, perc

    def match_with_file_list(self, file_path: Path):
        """Compare loaded paths with newline-separated entries in a file.

        Args:
            file_path (Path): Text file containing one relative path per line.

        Returns:
            tuple[int, float]: Intersection count and intersection-over-union percentage.
        """
        with open(file_path, "r") as file:
            return self.match_with_list([line.strip() for line in file.readlines()])

    def export_file_list(self, save_file_path: Path, name: str = "output.txt"):
        """Write the loaded relative paths to a text file.

        Args:
            save_file_path (Path): Existing directory receiving the output file.
            name (str): Output file name.

        Returns:
            None: The relative paths have been written to the output file.
        """
        with open(save_file_path.joinpath(name), "w+") as file:
            for item in self.working_path_items_rel:
                file.write(f"{item}\n")

    def log_all(self):
        """Log the loaded root path and print each loaded relative path.

        Returns:
            None: All loaded relative paths have been reported.
        """
        logger.debug(f"Working path: {self.working_path}")
        for item in self.working_path_items_rel:
            print(item)
