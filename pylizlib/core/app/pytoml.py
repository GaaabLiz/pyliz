"""Helpers for reading project information from a ``pyproject.toml`` file."""

import tomllib
from pathlib import Path


class PyProjectToml:
    """Read project metadata from a ``pyproject.toml`` file."""

    def __init__(self, toml_path: Path):
        """Store and validate the path to the TOML file."""

        self.toml_path = toml_path
        if not self.toml_path.exists():
            raise FileNotFoundError(f"File {self.toml_path} does not exist.")

    def extract_info(self) -> dict[str, object]:
        """Extract basic project metadata, including authors."""

        with self.toml_path.open("rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})

        raw_authors = project.get("authors", [])
        authors: list[tuple[str | None, str | None]] = []
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

    def gen_project_py(self, path_py: Path) -> None:
        """Generate a Python module containing the extracted project metadata."""

        info = self.extract_info()

        authors_repr = "[" + ", ".join(f"({repr(name)}, {repr(email)})" for name, email in info["authors"]) + "]"

        lines = [
            f"name = {repr(info['name'])}",
            f"version = {repr(info['version'])}",
            f"description = {repr(info['description'])}",
            f"requires_python = {repr(info['requires_python'])}",
            f"authors = {authors_repr}",
        ]

        path_py.parent.mkdir(parents=True, exist_ok=True)
        with path_py.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
