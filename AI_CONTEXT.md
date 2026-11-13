# Project context for AI assistants

## What this repository contains

`pylizlib` is a Python utility library for application configuration, data and text handling, filesystem and archive operations, directory snapshots, media processing, and optional AI and Qt features. It requires Python 3.12 or later and uses `uv` with `pyproject.toml` and `uv.lock` to manage dependencies.

The project is both an importable library and a source for optional application and UI components. Optional dependency groups are defined in `pyproject.toml`; do not assume AI, media, or Qt dependencies are installed in the base environment.

## Package map

| Path | Responsibility |
| --- | --- |
| `pylizlib/core/app/` | Application configuration and INI/TOML helpers |
| `pylizlib/core/data/` | General data helpers and text search, encoding, matching, and previews |
| `pylizlib/core/domain/`, `handler/`, `log/`, `network/` | Shared domain models, operation handlers, logging, and network helpers |
| `pylizlib/core/os/paths/` | Lexical path spelling and normalization, locations, identity, containment, and safety checks |
| `pylizlib/core/os/filesystem/` | Directory and file operations, file-type checks, capacity, tree scans, metadata, atomic writes, and durability primitives |
| `pylizlib/core/os/archives/zip/` | ZIP validation, extraction, and publication primitives |
| `pylizlib/core/os/windows/` | Windows drives, process/service inspection, commands, security descriptors, and alternate data streams |
| `pylizlib/core/network/` | HTTP requests, response wrappers, SSL helpers, and downloads |
| `pylizlib/core/os/path.py`, `file.py`, `utils.py` | Compatibility facades; new code should import from the focused modules above |
| `pylizlib/core/os/snap/` | Snapshot public API, models, operations, storage, recovery, copying strategies, and search |
| `pylizlib/media/` | Media models and processing utilities |
| `pylizlib/ai/` | Optional AI media scanning providers and orchestration |
| `pylizlib/qt/`, `pylizlib/qtfw/` | Optional Qt and Qt widget support |
| `test/unit/` | Unit tests mirroring the relative package and module paths under `pylizlib/` |
| `test/integration/<feature>/` | Public workflows grouped by feature, such as snapshots, Qt operations, or AI media scanning |
| `test/support/` | Shared test helpers and fixtures used across unit and integration suites |

## Snapshot design

The main public entry points are `SnapshotCatalogue`, `SnapshotManager`, `Snapshot`, and `SnapshotSettings`, exported from `pylizlib.core.os.snap`. The catalogue and manager are orchestration facades. Their workflows are implemented in `operations/`; on-disk layout, metadata access, and transaction recovery live in `storage/` and `storage/recovery/`.

`domain.py` and `copy_strategy.py` retain the historical public class locations and imports. The model declarations and strategy contracts stay in those modules; association and snapshot validation, cloning, and copy algorithms are delegated to `association_model.py`, `snapshot_model.py`, and `copying/`.

Copy behavior is selected through `SnapshotSettings.copy_strategy` and `copy_metadata_mode`. Captured association contents have integrity manifests. Snapshot creation, edits, synchronization, installation, and restore use staged publication and persistent transaction records where defined by the operation. Backups and exports use versioned ZIP metadata. Search reuses the shared text-search components.

The detailed snapshot guide is [pylizlib/core/os/snap/README.md](pylizlib/core/os/snap/README.md). Read it before changing snapshot contracts, recovery, archive handling, or copy guarantees. Shared primitives are documented in their own modules; keep snapshot policy in `snap` and reusable filesystem behavior in `core/os/`.

## Testing and quality

Unit tests live under `test/unit/` and mirror source paths: for example, `pylizlib/core/network/req.py` is tested from `test/unit/core/network/req.py`. Multi-module public workflows belong under `test/integration/<feature>/`; snapshot, Qt, qtfw, and AI workflows are grouped by feature there.

For snapshot changes, start with:

```sh
uv run pytest test/unit/core/os/snap test/integration/snap -q
```

The integration fixture creates a unique workspace under `test_local/snapshot_integration`, because snapshot destructive-path validation can classify OS-managed temporary directories as critical. A passing test removes only its own workspace; a failed test retains it for diagnosis. The executable runner accepts `--root` to run the same workflows on another local directory or a mounted share.

Common project checks are `make lint`, `make format-check`, and `make test`. The full test target enables the `media` extra; optional AI integration tests may require additional extras, model files, or network access. CI also runs snapshot contracts across Linux, macOS, and Windows, so avoid relying on one platform's filesystem behavior.

## Compatibility and change guidance

- Prefer focused changes over broad refactors. Preserve public re-exports and compatibility facades unless a task explicitly changes them.
- Keep new filesystem/path helpers in `core/os/paths/` or `core/os/filesystem/`; keep HTTP transfer code in `core/network/`. The root `core/os/path.py`, `file.py`, and `utils.py` modules preserve legacy imports and should not accumulate new implementation.
- Treat snapshot JSON fields, legacy metadata, backup manifests, ZIP layouts, and transaction states as persisted contracts.
- For filesystem changes, test both success and relevant failure paths. Verify that a failed preflight leaves targets untouched and that cleanup after a committed operation cannot trigger rollback.
- Keep tests deterministic and offline by default. Use synthetic files instead of downloaded media for filesystem and snapshot scenarios.
- Update the subsystem guide when behavior or operational guarantees change.
