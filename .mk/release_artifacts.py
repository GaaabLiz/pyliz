"""Select and stage native release files using the configured path patterns."""

import os
import shlex
import shutil
import tempfile
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path


def _absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(Path(path).expanduser()))


def parse_patterns(value: str) -> list[tuple[Path, bool]]:
    patterns = []
    for token in shlex.split(value):
        pattern = token.lstrip("!")
        if pattern and not pattern.startswith("#"):
            include = (len(token) - len(pattern)) % 2 == 0
            patterns.append((_absolute(pattern), include))
    return patterns


def _matches(parts: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    if not pattern:
        return True  # A selected directory includes its descendants.
    head, tail = pattern[0], pattern[1:]
    if head == "**":
        return any(_matches(parts[index:], tail) for index in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], head) and _matches(parts[1:], tail)


def _upload_path(path: Path) -> Path:
    if path.is_relative_to(Path.cwd()):
        return path.relative_to(Path.cwd())
    return Path(path.name)


def is_selected(path: str | Path, patterns: list[tuple[Path, bool]], *, ignore_case: bool = os.name == "nt") -> bool:
    path = _absolute(path)
    if any(part.startswith(".") for part in _upload_path(path).parts):
        return False
    parts = tuple(part.lower() for part in path.parts) if ignore_case else path.parts
    selected = False
    for pattern, include in patterns:
        pattern_parts = tuple(part.lower() for part in pattern.parts) if ignore_case else pattern.parts
        if _matches(parts, pattern_parts):
            selected = include
    return selected


def _candidate_files(pattern: Path) -> Iterator[Path]:
    fixed_parts = []
    for part in pattern.parts:
        if any(character in part for character in "*?["):
            break
        fixed_parts.append(part)
    yield from _files_under(Path(*fixed_parts), frozenset())


def _files_under(path: Path, ancestors: frozenset[Path]) -> Iterator[Path]:
    if path.is_file():
        yield path
    elif path.is_dir():
        resolved = path.resolve()
        if resolved in ancestors:
            return
        ancestors = ancestors | {resolved}
        for child in path.iterdir():
            if not child.name.startswith("."):
                yield from _files_under(child, ancestors)


def verify(value: str, expected_paths: list[Path]) -> list[Path]:
    patterns = parse_patterns(value)
    print(f"[ci-verify-release-artifacts] Checking RELEASE_ARTIFACTS={value}")
    files = {path for pattern, include in patterns if include for path in _candidate_files(pattern) if is_selected(path, patterns)}
    for expected in expected_paths:
        if not expected.is_file():
            raise ValueError(f"expected release artifact {expected.as_posix()} was not built.")
        if _absolute(expected) not in files:
            raise ValueError(f"{expected.as_posix()} is not included in RELEASE_ARTIFACTS.")

    if not files:
        raise ValueError("no platform assets matched RELEASE_ARTIFACTS.")
    ordered_files = sorted(files)
    for path in ordered_files:
        print(f"[ci-verify-release-artifacts]   matched: {_upload_path(path).as_posix()}")
    return ordered_files


def stage(files: list[Path], output: str) -> None:
    if not output:
        raise ValueError("GITHUB_OUTPUT is not set.")
    directory = Path(tempfile.mkdtemp(prefix="release-assets-", dir=os.getenv("RUNNER_TEMP")))
    try:
        for path in files:
            destination = directory / _upload_path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ValueError(f"multiple release files have upload path {_upload_path(path)}.")
            try:
                os.link(path.resolve(strict=True), destination)
            except OSError:
                shutil.copy2(path, destination)
        with Path(output).open("a", encoding="utf-8", newline="\n") as file_handle:
            file_handle.write(f"directory={directory.as_posix()}\n")
    except (OSError, ValueError):
        shutil.rmtree(directory, ignore_errors=True)
        raise
