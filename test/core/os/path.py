import os
import tempfile
import unittest
from pathlib import Path

from pylizlib.core.os.path import (
    PathMatcher,
    check_path,
    check_path_dir,
    check_path_file,
    clear_folder_contents,
    clear_or_move_to_temp,
    count_items,
    count_pathsub_dirs,
    count_pathsub_elements,
    count_pathsub_files,
    create_path,
    dir_contains,
    duplicate_directory,
    get_app_home_dir,
    get_filename,
    get_filename_no_ext,
    get_files_from,
    get_folders_from,
    get_home_dir,
    get_path_items,
    get_second_to_last_directory,
    random_subfolder,
    scan_directory_match_bool,
)


# ---------------------------------------------------------------------------
# Helper: build a small reproducible directory tree inside a temp dir
# ---------------------------------------------------------------------------
def _build_tree(root: str):
    """
    Creates the following tree under *root*:
        root/
            a.txt
            b.png
            sub1/
                c.txt
                d.mp4
            sub2/
                e.jpg
    """
    os.makedirs(os.path.join(root, "sub1"))
    os.makedirs(os.path.join(root, "sub2"))
    for name in ("a.txt", "b.png"):
        open(os.path.join(root, name), "w").close()
    for name in ("c.txt", "d.mp4"):
        open(os.path.join(root, "sub1", name), "w").close()
    open(os.path.join(root, "sub2", "e.jpg"), "w").close()


class GetHomeDirTestCase(unittest.TestCase):

    def test_returns_existing_directory(self):
        home = get_home_dir()
        self.assertTrue(os.path.isdir(home))


class GetAppHomeDirTestCase(unittest.TestCase):

    def test_creates_app_dir(self):
        with tempfile.TemporaryDirectory() as td:
            app_name = os.path.join(td, ".test_pyliz_app")
            result = get_app_home_dir(app_name, create_if_not=True)
            self.assertTrue(os.path.isdir(result))

    def test_no_create_flag(self):
        result = get_app_home_dir(".unlikely_test_app_xyz_999", create_if_not=False)
        # should just return the path string without creating it
        self.assertIsInstance(result, str)


class CreatePathTestCase(unittest.TestCase):

    def test_creates_nested_path(self):
        with tempfile.TemporaryDirectory() as td:
            nested = os.path.join(td, "a", "b", "c")
            create_path(nested)
            self.assertTrue(os.path.isdir(nested))

    def test_existing_path_no_error(self):
        with tempfile.TemporaryDirectory() as td:
            create_path(td)  # should not raise


class CheckPathTestCase(unittest.TestCase):

    def test_existing_readable_dir(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(check_path(td))

    def test_non_existing_dir(self):
        self.assertFalse(check_path("/non/existing/path/xyz"))

    def test_create_if_not(self):
        with tempfile.TemporaryDirectory() as td:
            new = os.path.join(td, "new_dir")
            result = check_path(new, create_if_not=True)
            self.assertFalse(result)  # returns False but creates it
            self.assertTrue(os.path.isdir(new))


class CheckPathDirTestCase(unittest.TestCase):

    def test_valid_directory(self):
        with tempfile.TemporaryDirectory() as td:
            check_path_dir(td)  # should not raise

    def test_non_existing_raises_ioerror(self):
        with self.assertRaises(IOError):
            check_path_dir("/non/existing/xyz")

    def test_file_raises_not_a_directory(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with self.assertRaises(Exception):
                check_path_dir(tmp.name)


class CheckPathFileTestCase(unittest.TestCase):

    def test_valid_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_name = tmp.name
        try:
            check_path_file(tmp_name)  # should not raise
        finally:
            os.unlink(tmp_name)

    def test_non_existing_raises(self):
        with self.assertRaises(FileNotFoundError):
            check_path_file("/non/existing/file.txt")

    def test_directory_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(Exception):
                check_path_file(td)


class GetSecondToLastDirectoryTestCase(unittest.TestCase):

    def test_normal_path(self):
        self.assertEqual(get_second_to_last_directory("/a/b/c"), "b")

    def test_short_path(self):
        self.assertIsNone(get_second_to_last_directory("single"))

    def test_two_components(self):
        result = get_second_to_last_directory("/root/child")
        self.assertEqual(result, "root")


class CountPathSubTestCase(unittest.TestCase):

    def test_count_files(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            self.assertEqual(count_pathsub_files(td), 5)

    def test_count_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            self.assertEqual(count_pathsub_dirs(td), 2)

    def test_count_elements(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            self.assertEqual(count_pathsub_elements(td), 7)


class GetFilenameTestCase(unittest.TestCase):

    def test_get_filename(self):
        self.assertEqual(get_filename("/a/b/photo.jpg"), "photo.jpg")

    def test_get_filename_no_ext(self):
        self.assertEqual(get_filename_no_ext("/a/b/photo.jpg"), "photo")

    def test_get_filename_no_ext_no_extension(self):
        self.assertEqual(get_filename_no_ext("/a/b/README"), "README")


class ScanDirectoryMatchBoolTestCase(unittest.TestCase):

    def test_returns_matching_files(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            result = scan_directory_match_bool(td, lambda p: p.endswith(".txt"))
            self.assertEqual(len(result), 2)

    def test_no_match(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            result = scan_directory_match_bool(td, lambda p: p.endswith(".zip"))
            self.assertEqual(len(result), 0)


class DirContainsTestCase(unittest.TestCase):

    def test_contains_all(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            self.assertTrue(dir_contains(td, ["sub1", "sub2"]))

    def test_contains_all_false(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            self.assertFalse(dir_contains(td, ["sub1", "missing"]))

    def test_at_least_one_true(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            self.assertTrue(dir_contains(td, ["sub1", "missing"], at_least_one=True))

    def test_at_least_one_false(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            self.assertFalse(dir_contains(td, ["x", "y"], at_least_one=True))


class GetFoldersFromTestCase(unittest.TestCase):

    def test_non_recursive(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            folders = get_folders_from(td)
            names = [os.path.basename(f) for f in folders]
            self.assertIn("sub1", names)
            self.assertIn("sub2", names)

    def test_recursive(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            folders = get_folders_from(td, recursive=True)
            self.assertEqual(len(folders), 2)


class GetFilesFromTestCase(unittest.TestCase):

    def test_non_recursive(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            files = get_files_from(td)
            self.assertEqual(len(files), 2)  # a.txt, b.png

    def test_recursive(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            files = get_files_from(td, recursive=True)
            self.assertEqual(len(files), 5)

    def test_extension_filter(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            files = get_files_from(td, recursive=True, extension=".txt")
            self.assertEqual(len(files), 2)


class GetPathItemsTestCase(unittest.TestCase):

    def test_non_recursive(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            items = get_path_items(Path(td))
            # top level: a.txt, b.png, sub1, sub2
            self.assertEqual(len(items), 4)

    def test_recursive(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            items = get_path_items(Path(td), recursive=True)
            # 2 dirs + 5 files = 7
            self.assertEqual(len(items), 7)


class ClearFolderContentsTestCase(unittest.TestCase):

    def test_clears_all(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            clear_folder_contents(Path(td))
            self.assertEqual(len(os.listdir(td)), 0)

    def test_not_a_dir_raises(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with self.assertRaises(NotADirectoryError):
                clear_folder_contents(Path(tmp.name))


class CountItemsTestCase(unittest.TestCase):

    def test_count(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            # top-level: a.txt, b.png, sub1, sub2 = 4
            self.assertEqual(count_items(Path(td)), 4)

    def test_not_a_dir_raises(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with self.assertRaises(ValueError):
                count_items(Path(tmp.name))


class DuplicateDirectoryTestCase(unittest.TestCase):

    def test_duplicate_default_suffix(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "origin"
            src.mkdir()
            (src / "file.txt").write_text("hello")

            dup = duplicate_directory(src)
            self.assertTrue(dup.exists())
            self.assertEqual((dup / "file.txt").read_text(), "hello")
            self.assertEqual(dup.name, "origin_copy")

    def test_duplicate_custom_dest(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "origin"
            src.mkdir()
            (src / "file.txt").write_text("data")

            dest = Path(td) / "my_copy"
            dup = duplicate_directory(src, dest_dir=dest)
            self.assertTrue(dup.exists())

    def test_duplicate_existing_dest_raises(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "origin"
            src.mkdir()
            dest = Path(td) / "existing"
            dest.mkdir()
            with self.assertRaises(FileExistsError):
                duplicate_directory(src, dest_dir=dest)


class RandomSubfolderTestCase(unittest.TestCase):

    def test_returns_subfolder(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            result = random_subfolder(Path(td))
            self.assertIn(result.name, ("sub1", "sub2"))

    def test_no_subfolder_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            result = random_subfolder(Path(td))
            self.assertIsNone(result)


class ClearOrMoveToTempTestCase(unittest.TestCase):

    def test_clear_deletes_directory(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "to_delete"
            target.mkdir()
            (target / "x.txt").write_text("bye")
            clear_or_move_to_temp(target)
            self.assertFalse(target.exists())

    def test_move_to_temp(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "to_move"
            target.mkdir()
            (target / "x.txt").write_text("data")
            clear_or_move_to_temp(target, temp_path=Path("pyliz_test_tmp"), move_to_temp=True)
            self.assertFalse(target.exists())


class PathMatcherTestCase(unittest.TestCase):

    def test_load_and_match(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            pm = PathMatcher()
            pm.load_path(Path(td), recursive=False)
            intersection, perc = pm.match_with_list(["a.txt", "b.png", "sub1", "sub2"])
            self.assertEqual(intersection, 4)
            self.assertEqual(perc, 100.0)

    def test_partial_match(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            pm = PathMatcher()
            pm.load_path(Path(td), recursive=False)
            intersection, perc = pm.match_with_list(["a.txt", "unknown"])
            self.assertEqual(intersection, 1)
            self.assertGreater(perc, 0)
            self.assertLess(perc, 100)

    def test_export_file_list(self):
        with tempfile.TemporaryDirectory() as td:
            _build_tree(td)
            pm = PathMatcher()
            pm.load_path(Path(td), recursive=False)
            pm.export_file_list(Path(td), name="list.txt")
            out_file = Path(td) / "list.txt"
            self.assertTrue(out_file.exists())
            lines = out_file.read_text().strip().splitlines()
            self.assertEqual(len(lines), 4)


if __name__ == "__main__":
    unittest.main()




