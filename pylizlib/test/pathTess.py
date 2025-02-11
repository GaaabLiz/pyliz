import unittest
from pathlib import Path

from pylizlib.os import pathutils
from pylizlib.os.pathMatcher import PathMatcher


class PathTests(unittest.TestCase):

    def test_list_files(self):
        home_dir = Path(pathutils.get_home_dir())
        elenco = pathutils.get_path_items(home_dir, True)
        for item in elenco:
            print(item)

    def test_dir_matcher(self):
        home_dir = Path(pathutils.get_home_dir())
        dir_1 = "A:\Models"
        matcher = PathMatcher()
        matcher.load_path(Path(dir_1), True)
        matcher.log_all()
        matcher.export_file_list(Path(r"C:\Users\Gabriele\Downloads"))

if __name__ == '__main__':
    unittest.main()