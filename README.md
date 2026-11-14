# pylizlib

`pylizlib` is a Python utility library for application configuration, data and
text handling, network requests, filesystem operations, and directory
snapshots. Optional packages add media processing, AI-assisted media scanning,
and Qt desktop components.

- **Python:** 3.12 or later
- **Package:** [`pylizlib` on PyPI](https://pypi.org/project/pylizlib/)
- **License:** [The Unlicense](UNLICENSE) (`Unlicense` SPDX identifier)

The core utilities install with the base package. Media, AI, and Qt dependencies
are optional so applications only need to install the features they use.

## Install

### From PyPI

```bash
python -m pip install pylizlib
```

This installs the core package and its required dependencies. Install an extra
to add an optional feature:

| Extra | Provides | Install command |
| --- | --- | --- |
| `media` | Image, video, and audio helpers, metadata parsing, and frame sampling | `python -m pip install "pylizlib[media]"` |
| `qt` | Desktop components based on PySide6 | `python -m pip install "pylizlib[qt]"` |
| `qtfw` | PySide6 and PySide6-Fluent-Widgets components | `python -m pip install "pylizlib[qtfw]"` |
| `ai` | JoyTag, NudeNet, and EasyOCR scanning providers | `python -m pip install "pylizlib[ai]"` |
| `ai-macos` | Compatibility alias for the `ai` extra | `python -m pip install "pylizlib[ai-macos]"` |
| `ai-linux-nvidia` | AI dependencies with the NVIDIA ONNX Runtime package on Linux | `python -m pip install "pylizlib[ai-linux-nvidia]"` |

Extras can be combined, for example:

```bash
python -m pip install "pylizlib[media,qt]"
```

The AI extras include large machine-learning dependencies. AI providers may
also need model files, network access, and substantial local compute resources.
The Linux NVIDIA option requires compatible NVIDIA drivers on the host.

### From a source checkout

To install the checkout into the active Python environment:

```bash
python -m pip install .
```

For an editable install with media support, for example:

```bash
python -m pip install -e ".[media]"
```

For development, use the repository's `uv` environment as described below.

## What is included

The library is organized into importable subpackages. Import APIs from the
feature package you use; for example, snapshot types live under
`pylizlib.core.os.snap`, and the optional scanner lives under `pylizlib.ai`.

| Package | Capabilities | Dependencies |
| --- | --- | --- |
| [`pylizlib.core`](pylizlib/core/README.md) | Application paths and INI/TOML configuration; JSON, regular-expression, and data helpers; shared domain models, operation progress, and logging; HTTP, SSL, and download helpers; OS and filesystem utilities | Installed with the base package |
| `pylizlib.core.data.text` | Streaming text search, text encoding detection, literal and timed regular-expression matching, previews, and bounded result pages | Base package |
| `pylizlib.core.os.paths` and `pylizlib.core.os.filesystem` | Path normalization, identity and containment checks; tree scans, metadata, file types, capacity checks, locking, atomic writes, and durability primitives | Base package |
| `pylizlib.core.os.archives.zip` | ZIP validation, extraction, and staged publication helpers | Base package |
| `pylizlib.core.os.windows` | Windows-specific drive, process, command, security descriptor, and alternate data stream helpers | Base package; native integrations are platform-specific |
| [`pylizlib.core.os.snap`](pylizlib/core/os/snap/README.md) | Snapshot catalogues and models, directory capture and installation, synchronization and edits, ZIP backup/restore and import/export, integrity checking, recovery, and bounded content search | Base package |
| [`pylizlib.media`](pylizlib/media/README.md) | `LizMedia` models, media metadata and sidecars, image/video/audio helpers, frame selection, and video sampling | `media` extra |
| [`pylizlib.ai`](pylizlib/ai/README.md) | AI media scanning with JoyTag (`TAGS`), NudeNet (`NSFW`), and EasyOCR (`OCR`) providers; accepts file paths or base64 content | `ai`, `ai-macos`, or `ai-linux-nvidia` extra |
| [`pylizlib.qt`](pylizlib/qt/README.md) | PySide6 configuration and preferences, menus and toolbars, themes and resources, reusable widgets, and background operation handling | `qt` extra |
| [`pylizlib.qtfw`](pylizlib/qtfw/README.md) | Settings models and widgets built with PySide6-Fluent-Widgets | `qtfw` extra |

The compatibility modules `pylizlib.core.os.path`, `file`, and `utils` remain
available for existing imports. New code should prefer the focused
`pylizlib.core.os.paths` and `pylizlib.core.os.filesystem` packages.

## Snapshot example

The following searches the contents of snapshots already present in a catalogue.
It searches text files by default; pass `query_type=QueryType.REGEX` to use a
regular expression, or `search_target=SearchTarget.FILE_NAME` to search names.

```python
from pathlib import Path

from pylizlib.core.os.snap import (
    QueryType,
    SearchTarget,
    SnapshotCatalogue,
    SnapshotSearchParams,
    SnapshotSearcher,
)

catalogue = SnapshotCatalogue(Path("./snapshot-catalogue"))
snapshots = catalogue.get_all()
searcher = SnapshotSearcher(catalogue)

matches = searcher.search_list(
    snapshots,
    SnapshotSearchParams(
        query="needle",
        search_target=SearchTarget.FILE_CONTENT,
        query_type=QueryType.TEXT,
        extensions=[".txt", ".md"],
    ),
)

for match in matches:
    print(match.file_path)
```

`SnapshotCatalogue` handles catalogue-level operations such as lookup, import
and export, backups, and restore. `SnapshotManager` provides operations for one
snapshot, including capture, installation, edits, and synchronization. The
catalogue path in this example must point to a catalogue containing snapshots
for the search to return results.

## Snapshot behavior and limits

Snapshot operations validate source and destination paths before destructive
work. Symlinks and Windows junctions are rejected in snapshot tree operations.
Captured directory copies can include integrity manifests; workflows that
replace or publish data use staging and transaction journals where specified by
the operation. ZIP imports and restores validate archive contents and apply
configurable entry-count and expanded-size limits before extraction.

The default `SnapshotSettings` copy mode preserves file contents and standard
file/subdirectory metadata. Its `EXTENDED` mode can also copy owner and group
when permitted, extended attributes and ACLs exposed by the operating system,
Windows alternate data streams, and hard links within an individual copied
tree. Extended metadata depends on source and destination filesystem support
and permissions; a requested attribute that cannot be copied causes the copy
to fail before publication. ZIP backups do not preserve owner, ACLs, extended
attributes, alternate data streams, or hard-link topology.

Filesystem durability depends on the operating system and filesystem. In
particular, a successful flush on SMB or NFS cannot prove that a remote server
has persisted data to stable storage. See the [snapshot guide](pylizlib/core/os/snap/README.md)
for operation-specific recovery behavior, compatibility details, and limits.

## Optional feature examples

### AI media scan

After installing an AI extra, `AiMediaScanner` returns a `LizMedia` object with
the requested scan results attached:

```python
from pylizlib.ai import AiMediaScanner

scanner = AiMediaScanner()
media = scanner.scan(
    media_path="/path/to/image.jpg",
    tools=["TAGS", "OCR", "NSFW"],
)

print(media.ai_tags)
print(media.ai_has_ocr_text)
print(media.ai_nsfw)
```

The [AI guide](pylizlib/ai/README.md) documents accepted tool names, base64
inputs, platform extras, and integration requirements.

## License

This project is released under [The Unlicense](UNLICENSE), with the aim of
dedicating its copyright to the public domain. It allows anyone to use, copy,
modify, publish, distribute, compile, and sell the project for any purpose,
without requiring permission, attribution, or preservation of copyright
notices. The license text also disclaims warranties and liability.

The legal effect of a public-domain dedication can vary by jurisdiction. This
license applies to material the project authors are entitled to release;
third-party dependencies and separately identified third-party materials keep
their own licenses.

## Development

The repository uses [`uv`](https://docs.astral.sh/uv/) with `pyproject.toml`
and the committed `uv.lock` file. Install the standard development tools with:

```bash
uv sync --group dev
```

Development dependencies are separated into groups:

| Group | Tools |
| --- | --- |
| `dev` | pytest, pytest-cov, Ruff, and git-cliff |
| `build` | PyInstaller |
| `typing` | `ty` |
| `docs` | pdoc |
| `graphics` | SVG/vector and raster image tooling used by graphics scripts |

Add a group when needed, for example `uv sync --group dev --group docs`.
These are repository development groups, separate from the installable package
extras in the previous section. `uv sync --all-groups --all-extras` installs all
groups and features, including the large AI and Qt dependency sets.

Common repository commands:

```bash
make lint
make format-check
make type-check
make test
make docs-snap
make docs
```

`make test` runs the configured suite with the `media`, `qt`, and `qtfw` extras.
AI integration tests can require network access and model files. Unit tests are
under `test/unit/`; end-to-end feature workflows are under
`test/integration/<feature>/`. Generated API documentation is written to
`docs/api`, while the focused snapshot preview is written to
`temp_local/docs_snap_preview`.

See [AI_CONTEXT.md](AI_CONTEXT.md) for the repository architecture and
[AGENTS.md](AGENTS.md) for contribution and testing conventions. Release
history is in [CHANGELOG.md](CHANGELOG.md).
