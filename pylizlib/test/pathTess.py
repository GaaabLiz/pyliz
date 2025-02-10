import unittest
from pathlib import Path

from pylizlib.os import pathutils


class PathTests(unittest.TestCase):

    def test_list_files(self):
        home_dir = Path(pathutils.get_home_dir())
        elenco = pathutils.get_path_items(home_dir, True)
        for item in elenco:
            print(item)

    def test_dir_matcher(self):
        home_dir = Path(pathutils.get_home_dir())
        elenco = [
            str(".android\cache\sdkbin-1_75698f08-sys-img2-3_xml")
        ]
        num, perc = pathutils.path_match_items(home_dir, elenco)
        print(f"Num: {num}, Perc: {perc}")

if __name__ == '__main__':
    unittest.main()