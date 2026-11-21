"""Generate the runtime module for Python package metadata."""

import sys
import tomllib
from pathlib import Path
from typing import Any


def read_project_table(path: Path) -> dict[str, Any]:
    with path.open("rb") as file_handle:
        return tomllib.load(file_handle).get("project", {})


def generate_project_module(pyproject_path: Path, py_file: Path) -> int:
    try:
        if not pyproject_path.exists():
            raise FileNotFoundError(f"File {pyproject_path} does not exist.")

        project = read_project_table(pyproject_path)
        raw_authors = project.get("authors", [])
        authors: list[tuple[str | None, str | None]] = []
        for entry in raw_authors:
            name = entry.get("name")
            email = entry.get("email")
            if name or email:
                authors.append((name, email))

        info = {
            "name": project.get("name"),
            "version": project.get("version"),
            "description": project.get("description"),
            "requires_python": project.get("requires-python"),
            "authors": authors,
        }

        authors_repr = "[" + ", ".join(f"({repr(name)}, {repr(email)})" for name, email in info["authors"]) + "]"

        lines = [
            "# fmt: off",
            "name = " + repr(info["name"]),
            "version = " + repr(info["version"]),
            "description = " + repr(info["description"]),
            "requires_python = " + repr(info["requires_python"]),
            "authors = " + authors_repr,
            "# fmt: on",
        ]

        py_file.parent.mkdir(parents=True, exist_ok=True)
        with py_file.open("w", encoding="utf-8") as file_handle:
            file_handle.write("\n".join(lines) + "\n")

        print(f"Generated: {py_file}")
        return 0
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
