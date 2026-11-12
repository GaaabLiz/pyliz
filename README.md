# pylizlib

General-purpose Python utilities for application configuration, data handling,
filesystem operations and directory snapshots. Python 3.12 or later is required.

The snapshot API supports catalogue management, directory capture and
installation, ZIP backup/restore and bounded text search. See the
[snapshot guide](pylizlib/core/os/snap/README.md) for the package map,
copying guarantees, recovery behavior and compatibility constraints.

Install the development environment with `uv sync --group dev`. Run
`make docs-snap` to generate a focused API preview under
`temp_local/docs_snap_preview`, or `make docs` for the full API under `docs/api`.
Both commands render the typed Google-style docstrings with pdoc.

Run the snapshot and shared-primitive checks from the repository root:

```sh
uv run pytest test/core/test_documentation_contracts.py test/core/os/snap \
    test/core/os/filesystem test/core/os/paths test/core/data/text -q
```

Optional features outside this scope have separate extras in `pyproject.toml`.

Contributor and AI-agent guidance is in [AGENTS.md](AGENTS.md), with the
repository architecture and subsystem map in [AI_CONTEXT.md](AI_CONTEXT.md).
