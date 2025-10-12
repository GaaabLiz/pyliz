from pathlib import Path
import tomllib


class PyProjectToml:
    """
    A class to handle reading and extracting information from a pyproject.toml file,
    including authors.
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
        Returns a dictionary with keys: name, version, description, requires_python, authors.
        """
        with self.toml_path.open("rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})

        # Estrai gli autori come lista di tuple (name, email)
        raw_authors = project.get("authors", [])
        authors = []
        for entry in raw_authors:
            name = entry.get("name")
            email = entry.get("email")
            if name or email:
                authors.append((name, email))

        return {
            "name": project.get("name"),
            "version": project.get("version"),
            "description": project.get("description"),
            "requires_python": project.get("requires-python"),
            "authors": authors,
        }

    def gen_project_py(self, path_py: Path):
        """
        Generate a Python file with project information extracted from pyproject.toml.
        """
        info = self.extract_info()

        # Prepara la rappresentazione di authors
        authors_repr = "[" + ", ".join(
            f"({repr(name)}, {repr(email)})" for name, email in info["authors"]
        ) + "]"

        lines = [
            f"name = {repr(info['name'])}",
            f"version = {repr(info['version'])}",
            f"description = {repr(info['description'])}",
            f"requires_python = {repr(info['requires_python'])}",
            f"authors = {authors_repr}",
        ]

        with path_py.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")