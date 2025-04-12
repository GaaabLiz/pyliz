from pathlib import Path

from pylizlib.log.pylizLogger import logger

from pylizlib.os import pathutils


class PathMatcher:

    def __init__(self):
        self.working_path_items_rel = None
        self.working_path_items = None
        self.working_path = None

    def load_path(self, path: Path, recursive: bool = False):
        self.working_path = path
        self.working_path_items = pathutils.get_path_items(path, recursive)
        self.working_path_items_rel = [str(p.relative_to(self.working_path)) for p in self.working_path_items]

    def match_with_list(self, path_str_list: list[str]):
        set1, set2 = set(self.working_path_items_rel), set(path_str_list)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        perc = (intersection / union) * 100 if union > 0 else 100
        return intersection, perc

    def match_with_file_list(self, file_path: Path):
        with open(file_path, "r") as file:
            return self.match_with_list([line.strip() for line in file.readlines()])

    def export_file_list(self, save_file_path: Path, name: str = "output.txt"):
        with open(save_file_path.joinpath(name), "w+") as file:
            for item in self.working_path_items_rel:
                file.write(f"{item}\n")

    def log_all(self):
        logger.trace(f"Working path: {self.working_path}")
        for item in self.working_path_items_rel:
            print(item)
