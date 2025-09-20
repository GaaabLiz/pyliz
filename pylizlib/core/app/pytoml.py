from pathlib import Path
import tomllib


class PyProjectToml:
    """
    A class to handle reading and extracting information from a pyproject.toml file.
    """

    def __init__(self, toml_path: Path):
        """
        Initialize with the path to the pyproject.toml file.
        """
        self.toml_path = toml_path
        if not self.toml_path.exists():
            raise FileNotFoundError(f"File {self.toml_path} does not exist.")

    def extract_info(self) -> dict:
        """
        Extract project information from the pyproject.toml file.
        Returns a dictionary with keys: name, version, description, requires_python.
        """
        with open(self.toml_path.__str__(), "rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})
        return {
            "name": project.get("name"),
            "version": project.get("version"),
            "description": project.get("description"),
            "requires_python": project.get("requires-python")
        }

    def gen_project_py(self, path_py: Path):
        """
        Generate a Python file with project information extracted from pyproject.toml.
        """
        info = self.extract_info()
        lines = [
            f'name = {repr(info["name"])}',
            f'version = {repr(info["version"])}',
            f'description = {repr(info["description"])}',
            f'requires_python = {repr(info["requires_python"])}',
        ]
        with open(path_py.__str__(), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")