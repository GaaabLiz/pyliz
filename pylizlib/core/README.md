# Core utilities

`pylizlib.core` provides services and models reusable across the rest of the
library: configuration, data, networking, filesystem, and operating-system
operations. Modules can be imported from their respective subpackages, such as
`pylizlib.core.os.paths` or `pylizlib.core.network`.

## Main areas

| Package | Contents |
| --- | --- |
| `app/` | INI and TOML configuration and application paths |
| `data/` | JSON, regular expressions, conversions, utilities, and streaming text search |
| `domain/`, `handler/`, `log/` | Shared models, progress support, and logging |
| `network/` | HTTP requests, downloads, and SSL helpers |
| `os/paths/` | Path normalization, identity, containment, and safety |
| `os/filesystem/` | Files, directories, trees, metadata, locks, and atomic writes |
| `os/archives/zip/` | ZIP validation, extraction, and publication |
| `os/windows/` | Adapters for Windows-specific features |
| `os/snap/` | Snapshots, catalogues, backups, restore, search, and recovery |

The public snapshot APIs are exposed by `pylizlib.core.os.snap`, including
`Snapshot`, `SnapshotManager`, and `SnapshotCatalogue`. For workflows and safety
guarantees, see the [snapshot guide](os/snap/README.md).

The `os/path.py`, `os/file.py`, and `os/utils.py` modules retain legacy imports;
new code should prefer `os/paths/` and `os/filesystem/`.

## Tests

Unit tests mirror the package structure under `test/unit/core/`. Complete
snapshot workflows are grouped under `test/integration/snap/`.
