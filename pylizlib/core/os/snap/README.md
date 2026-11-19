# Snapshot subsystem maintenance

The public API remains available through `pylizlib.core.os.snap` and the
historical modules. The refactor separates internal responsibilities while
preserving formats, signatures, return values, and error behavior.

## Where to start

| Need | Module to read |
|---|---|
| API for one snapshot | `manager.py` |
| Catalogue API, statistics, and backup operations | `catalogue.py` |
| Public model, enum, action, and configuration declarations | `domain.py` |
| Association validation and operations | `association_model.py` |
| Snapshot validation, metadata, and cloning | `snapshot_model.py` |
| Creation, duplication, and deletion | `operations/lifecycle.py` |
| Installing and removing installed copies | `operations/install.py` |
| Updating internal copies from the source | `operations/sync.py` |
| Catalogue statistics | `operations/statistics.py` |
| Edit planning and execution | `operations/edits.py` |
| Compatible backup and restore facade | `operations/archives.py` |
| Archive creation and inspection | `operations/backup/creation.py`, `inspection.py` |
| Restore planning, staging, and publication | `operations/backup/planning.py`, `restore.py` |
| Codec and rules for archived associations | `operations/backup_manifest.py`, `backup/associations.py` |
| Backup name generation and parsing | `operations/backup_names.py` |
| Catalogue import/export | `operations/transfers.py` |
| Paths contained in storage | `storage/paths.py` |
| Strict scanning and symlink policies | `core/os/filesystem/tree.py`; delegates in `storage/tree.py` |
| Directory publication and cleanup | `storage/publication.py` |
| ZIP read and write primitives | `core/os/archives/zip/`; delegates in `storage/archives.py` |
| Default limits for ZIP import and restore | `storage/archive_limits.py` |
| Snapshot JSON conversion | `storage/metadata.py` |
| Protected file descriptors and atomic writes | `core/os/filesystem/atomic.py` |
| Catalogue entry scanning | `storage/catalogue.py` |
| Dependencies for a single operation | `storage/context.py` |
| Journal persistence and facade | `storage/transactions.py` |
| Operation coordination and recovery | `storage/coordination.py`; reusable native locks in `core/os/filesystem/locking.py` |
| Recovery codecs, dispatch, and handlers | `storage/recovery/` |
| Copying an association into its storage | `storage/association.py` |
| Public strategy contracts and classes | `copy_strategy.py` |
| Sequential and verified implementations | `copying/file_strategies.py` |
| Extended metadata copy implementation | `copying/metadata_strategy.py` |
| Provider, sessions, and metadata capabilities | `copying/provider.py`, `copying/session.py`, `copying/contracts.py` |
| Manifest validation and comparison | `integrity.py` |
| Public queries and path resolution | `searcher.py` |
| Live configuration adapters and results | `searching.py` |
| Text engine, encoding, windows, and previews | `core/data/text/` |
| Model restoration and capture state | `model_state.py` |
| Callback contracts | `callbacks.py` |
| Association comparison and sorting | `diff.py`, `sorting.py` |
| Randomized example generation | `factories.py` |

Paths beginning with `core/` are relative to `pylizlib/`. The other paths are
relative to this package. General-purpose primitives do not import `snap` and
can be used with other data and filesystems. In particular:

- `core/os/paths/` distinguishes lexical form, filesystem identity, and containment;
- `core/os/filesystem/` contains trees, metadata, fingerprints, capacity checks,
  entries, atomic writes, and rename durability;
- `core/os/windows/` isolates drives, security descriptors, and alternate data
  streams, loading native bindings only when called;
- `core/os/archives/zip/` validates, extracts, and publishes generic archives;
- `core/data/text/` reads text and collects matches through structural contracts.

Policies for IDs, reserved names, associations, legacy formats, and commit
states remain in `snap`. The old storage modules remain available as
compatibility adapters; shared code has a single implementation.

Metadata writes prepare a temporary file in the same directory, flush its
contents, preserve the previous bytes in a `.previous` sidecar, and publish it
with `os.replace`. If the final directory flush fails after the rename,
`MetadataDurabilityError.published` distinguishes JSON that is already visible
from a write that was not published. On SMB/NFS, a completed `fsync` is still
only confirmation from the system or server: the library cannot attest that the
server persisted the bytes to stable storage.

`SnapshotManager.install()` reports a `date_last_used` error after the data has
been committed by raising `SnapshotInstallMetadataError`. The exception
indicates that the directories have already been installed and exposes
`metadata_published` (True, False, or None if the adapter cannot determine it).
In replacement mode, the previous copies are left temporarily available for
recovery. Merge mode instead records top-level entry replacements and their
rollback copies; it does not create a recursive backup of the entire
destination. An alternative adapter should expose `published` and
`durability_confirmed` on post-publication write exceptions.

Backing up and restoring associated directories requires every association to
be present. If a source or an archive folder is missing,
`SnapshotIncompleteError` is raised; `missing_folders` contains the missing
original paths and `unexpected_entries` contains archive entries with no
matching association. Restore checks the complete set before changing any
destinations.

## Content search

`SnapshotSearchParams` reads in chunks and limits candidates to `max_files`
(default 10,000), results to `max_results` (default 1,000), and displayed text
per line to `max_line_preview_chars` (default 4,096). Pagination uses
`result_offset`; in `search_list()`, the page is shared across all snapshots.
Extensions are compared case-insensitively and can be compound, such as
`.TAR.GZ`.

If `encoding` is not specified, search detects BOMs and UTF-16 without a BOM
when the text is ASCII, tries UTF-8, and uses Windows-1252 if the text is not
valid UTF-8. If decoding fails later in the file, the file is read again using
Windows-1252. Files identified as binary by the initial sample are skipped; a
text decoding error is not reported as a binary file. Set `encoding` explicitly
to use another encoding.

Text and regex queries can span lines. Content is read in chunks of
`chunk_size` (default 65,536 **decoded characters**); the initial encoding
sample is 8,192 bytes. Regexes have a timeout for each match operation
(`regex_timeout_seconds`, default 0.1 seconds), not a global search deadline.
`max_context_chars` (default 1,048,576 characters) is the context budget held
between chunks. It does not impose a strict maximum length on each match: a
longer span may be found when it fits in the current window, but matches across
chunks and the EOF tail are not guaranteed. Only `False` stops the current
snapshot search; the callback is also called while reading, so it can stop a
very large file.

## Catalogue statistics

```python
from pathlib import Path

from pylizlib.core.os.snap import SnapshotCatalogue, SnapshotSettings

catalogue = SnapshotCatalogue(Path("catalogue"), SnapshotSettings(backup_path=Path("backups")))
stats = catalogue.get_statistics()
print(stats.snapshot_count, stats.total_size_bytes, stats.average_snapshot_size_bytes)
print(stats.file_count, stats.directory_count, stats.largest_file)
print(stats.oldest_snapshot_date, stats.newest_snapshot_date, stats.backup_count, stats.catalogue_path)
```

`get_statistics()` loads snapshots using the same rules as `get_all()` and
aggregates their manifests in one pass. Totals cover captured association
contents. Sizes are logical bytes per path, and directory counts include each
association root and empty directories. `largest_file` reports the size,
snapshot ID, association ID, and relative path. Dates preserve the
`date_created` value and are ordered by interpreting timestamps without a time
zone as local times. For an empty catalogue, counts and sizes are zero, while
dates and the largest file are `None`.

For legacy associations without manifests, the operation reads only filesystem
metadata for copies in the catalogue. Contained paths and strict scanning use
the existing symlink rules. Errors from legacy scans are propagated.
`strict=True` also propagates I/O errors when loading snapshot metadata, as
`get_all()` does.

`get_snapshot_count()` reads only snapshot metadata. `get_backup_count()` counts
the ZIP files recognized by `list_backups()` in
`SnapshotSettings.backup_path` without inspecting their members. If that
directory is missing or not configured, the count is zero.
`get_statistics(include_backups=False)` skips the backup count and returns
`backup_count=None`.

## Sizes and capture times

`SnapDirAssociation` does not measure the source when constructed or when JSON
is loaded. If `mb_size` is missing, it remains `None`, so a lookup does not
start potentially slow scans on network paths. After a successful copy,
create, add, edit, and sync calculate `mb_size` from the manifest of the copy
that was actually captured. A captured empty directory has size zero; an
unknown legacy value remains distinct from zero until the next capture.

Copy callbacks never exceed 100% and receive a final update even for empty
trees or when the source changes size during copying. Without a callback,
create does not perform a preliminary byte scan to estimate progress.

`date_created` retains its historical meaning as the creation time of the
metadata object. `capture_started_at` and `capture_completed_at` instead record
the start and end of the latest complete capture performed by create or sync,
as UTC timestamps with an explicit offset (`+00:00`). Both fields remain `None`
for legacy snapshots until they are captured again.

A backup destination must resolve outside the trees that will be archived.
This prevents previous ZIP files from being included and is checked even when
the destination uses an alias or symlink.

New AD and SD backups include `.pyliz_backup_manifest.json` with the version,
type, snapshot ID and name, date, source OS, and associations (ID, index,
internal name, and original path). Restore and `list_backups()` read this data
from the archive; renaming the ZIP does not change its type or identity. Before
installing, restoring, or removing copies, the library checks that destinations
are not critical, do not overlap the catalogue, and do not coincide with or
contain one another. The operation is rejected if a path cannot be resolved.
Destructive destinations with symlink or junction components are rejected,
even when the link appears before `..`: the model preserves the lexical form,
while install/restore/remove require a path that can be used without traversing
links. A `..` component without a link keeps its meaning; it is not collapsed
with `abspath()`. Install and restore recheck planned targets after staging. If
a recovery parent has become a link, recovery stops and preserves the journal
and available copies.

Backups can also be restored after the snapshot has been deleted from the
catalogue. Older AD manifests and earlier archives without a manifest retain
the compatibility path that uses catalogue metadata or the legacy name. To
change the destination,
`SnapshotCatalogue.restore_backup_with_mapping(zip_path, {folder_id: path})`
accepts a mapping from persistent association IDs to new paths; associations
not listed keep the path saved in the archive.

SD import and restore reject trees containing the operational storage
`.pyliz_transactions` at the snapshot root. Catalogue import checks every
entry before publishing the first one. The reserved name includes case
variants and trailing dots or spaces that can become aliases on Windows.
Snapshot IDs cannot use this namespace either. Journals are created locally by
operations; archives carry data without introducing instructions to execute on
the next lookup. A directory with that name inside association data remains
ordinary user content.

Before replacing a snapshot through SD restore, the actual staged copy is
verified: every association must exist, and available manifests must match
paths, types, sizes, and file SHA-256 values. An incomplete or inconsistent
archive leaves the previous snapshot intact. The same check protects single
imports and duplication. Legacy metadata without a manifest remains explicitly
unverified; `allow_unverified_legacy_snapshots` continues to control its
installation and does not imply integrity guarantees.

ZIP writing also accepts source timestamps earlier than 1980 and clamps them to
the range representable by the format. Before extraction, import and restore
check the entry count, total uncompressed bytes, and available space, including
the second staging area needed for publication. Defaults are 100 GiB and
1,000,000 entries; they can be changed or disabled with
`SnapshotSettings.max_archive_uncompressed_bytes` and
`max_archive_entries`. SD import and restore use the catalogue filesystem for
staging; AD restore chooses the volume of an associated destination. Set
`SnapshotSettings.archive_temp_directory` to choose another volume. The check
also accounts for the final copy, but does not reserve capacity against
concurrent writes.

`utils.py` and `serializer.py` retain the old APIs as facades. New internal
implementations use the responsible modules directly instead of going through
the aggregated exports in `snap.__init__`.

## Composition and interfaces

The manager and catalogue coordinate operations; they no longer contain the
large copy, publication, or restore algorithms. Services receive explicit
dependencies and do not inherit from a general-purpose manager.

`SnapshotStorage` is constructed on each manager invocation using its current
public attributes. It retains references to the model and settings without
copying them. Destinations captured by the manager continue to be compared
against the requested paths to detect changes to an ID or JSON filename.

The contracts are limited to the capabilities in use:

- `DirectoryCopyStrategy` and `SourceSnapshotProvider` retain their existing
  public ABCs and runtime type checks.
- `SnapshotMetadata` describes saving, reading, partial updates, and access to
  the bytes needed for recovery. The default adapter is the serializer.
- `SnapshotPathLookup` describes the only catalogue capability required by
  search; the historical constructor signature remains available.
- `SnapshotLookup` provides the lookup used by association restore.
- `CatalogueQuery` exposes the reads needed for ZIP transfers.
- `MetadataCopyCapability` lets the extended strategy keep the source stable
  while copying attributes, without depending on the concrete provider class.
- `TextSearchConfiguration`, `MatchPage`, and `TimedPattern` expose only live
  configuration, pages isolated for retries, and matching with a timeout to
  the text engine. The engine does not know snapshot names or models.

Copying uses `SnapshotSettings.copy_metadata_mode`. The `BASIC` default
preserves current behavior: content is copied with `copy2`, along with standard
file and subdirectory metadata, but not metadata for the associated root
directory. Select the extended level with
`SnapshotSettings(copy_metadata_mode=CopyMetadataMode.EXTENDED)`. `EXTENDED`
wraps the configured strategy and also preserves root attributes, owner and
group when the process has the required permissions, extended attributes
(including ACLs exposed as attributes), DACLs and alternate data streams
on Windows, and hard links within each copied tree. If required metadata cannot
be copied, copying fails before publication. Features not exposed by the
operating system or not supported by the destination filesystem cannot be
guaranteed; hard links between different associations are not preserved
because associations are copied separately. Symlinks and junctions remain
rejected in both modes. This mode applies to directory copies: ZIP backups and
exports do not carry owners, ACLs, extended attributes, ADS, or hard-link
topology.

The `EditMove`, `EditPlan`, `InstallReplacement`, `SyncReplacement`, and
`RestoreReplacement` records give explicit names to data previously stored in
tuples or dictionaries. Their contained models remain mutable: a frozen record
does not freeze the snapshot or introduce a copy of it.

`SnapDirAssociation.copy_install_to()` first copies into private staging and
publishes only the complete result. If the destination already exists, even if
it appears during copying, the operation fails and cleanup does not remove it.
Cleanup handles only staging owned by the call; the outgoing manifest and
association metadata are updated after publication.

## Journals and crash recovery

Snapshot replacements, association edits, synchronization, installation, and
association restore record their phases in `.pyliz_transactions` on the same
storage as the affected data. The journal is published atomically through
`SnapshotSerializer`; its state updates precede actions that recovery must
complete or undo. Renames sync the affected directories when the filesystem
supports it. On SMB, NFS, and platforms that do not provide this confirmation,
the library can detect and recover states left by a process crash, but cannot
attest that the server physically persisted the data.

Recovery runs when the catalogue loads snapshots and before later operations
that modify or copy their trees. `prepared` is rolled back;
`commit_decided` is completed; `committed` repeats cleanup only. If a journal
cannot be read or an expected copy is missing, recovery stops and preserves
the journal and available copies rather than proceeding with ambiguous data.
Previous copies are deleted only after the journal records the commit.

Edit journals use format v2: rollback records parking the new names, restoring
the originals, and completion as separate phases before cleanup. A second crash
resumes from the recorded phase without mistaking already-restored originals
for new directories to remove. Other journals remain v1. Edit v1 journals are
recovered when their state can be determined; if old and new names overlap and
an original copy is no longer in staging, recovery stops and preserves every
available copy. Do not use an older library version while v2 journals are
pending: the older reader rejects them because it does not know the new
rollback phases.

Each operation holds exclusive access to the catalogue from initial recovery
through cleanup. Coordination uses a thread gate and a native lock on the
stable `.pyliz_snapshot.lock` file in the catalogue root. The file remains
after an operation finishes: do not remove or replace it while the library is
in use, because processes must refer to the same file. Archives cannot
introduce this operational name, including its Windows variants; a file with
the same name inside an association remains ordinary user content.

Progress and message callbacks can call `get_all()`, `get_by_id()`, and
`exists()` on the current catalogue. Implicit recovery skips journals created
by the active operation. Callbacks cannot start edits, backups, or exports;
these attempts, as well as access from other threads or processes during an
operation, raise `SnapshotBusyError` (exported from `pylizlib.core.os.snap`)
before changing data. The caller can retry after the operation finishes. An
exception or process crash releases the lock; the next call can recover
pending journals. Workers created with `fork` discard inherited leases and
descriptors and must acquire the lock themselves.

Locks coordinate library callers that share the same catalogue. Applications
must also serialize operations on different catalogues that install into the
same destinations. On remote filesystems, the server must support native locks:
an acquisition error is propagated and the operation does not continue without
protection. This coordination does not attest to cross-machine lock support or
physical durability on a particular SMB/NFS share.

| Workflow | Ordering and limit to preserve |
|---|---|
| Creation | Prepare associations and JSON in staging, then publish the root. Recovery completes publication if the commit was already decided. |
| Edit | Plan using persisted identities, move the originals, publish, and save; if JSON publication does not happen, restore directories, bytes, and model. If publication happens but flush fails, keep the new state and retain removed directories still in staging. |
| Synchronization | Prepare all copies, replace them, update sizes/manifests, and save; restore copies and in-memory metadata according to the existing protocol. |
| Installation | Reject coincident or nested destinations before staging; verify and prepare all copies before changing targets; save `date_last_used` after the content commit. |
| Installation merge | Replace top-level collisions; do not introduce a recursive merge. |
| `_ad` restore | Restore recognized associations using staging and a journal; recovery completes or rolls back the swap after a crash. |
| Post-commit cleanup | Record errors and continue without reactivating rollback of data already published. |

A fix that changes these boundaries requires a product decision and its own
tests; it should not be bundled into a code move.

## Other compatibility constraints

- Associations keep `mb_size=None` until content is captured; saved sizes come
  from the copy manifests. `validate()` normalizes `original_path` to an
  absolute path anchored at the current working directory at construction time
  and is called by the properties that already called it. Normalization is
  lexical and does not follow symlinks. JSON rejects relative paths; on Windows,
  mapped network drives are converted to UNC paths when the mapping is
  available.
- The `SnapshotSettings()` defaults of the two public constructors retain their
  historical sharing behavior. Do not add implicit copies or reconstructions.
- Diff uses `folder_id` as a stable identity and preserves the order of adds,
  removals, and renames. Legacy actions are resolved before edits.
- JSON retains UTF-8, indentation, ISO dates, and legacy fallback. Partial
  updates preserve extra fields without constructing a model; all default
  writes are published atomically and retain the previous version in the
  `.previous` sidecar.
- The serializer resolves its hooks in the historical order: read/validate,
  prepare data, select the converter, encode, then resolve the writer.
- Symlink checks before and after I/O are not redundant and should not be
  removed. Backup, storage, and search traversal retain distinct policies.
- The persisted manifest and the internal fingerprint of the verified copy
  remain different representations. Verification by retry does not mean the
  filesystem/provider source was frozen.
- A callback enables byte estimation and receives completion for empty paths.
  Create passes `None` when there is no observer, avoiding the preliminary
  scan; install does the same.
- In search, only `False` stops the current snapshot; the callback is called
  before each file and during chunked reads.
- Catalogue import handles errors per entry and initially reads only the ID;
  single import instead validates the entire model.

## Checks before making changes

From the repository root:

```sh
.venv/bin/python -m pytest test/unit/core/test_documentation_contracts.py \
    test/unit/core/os/snap test/unit/core/os/filesystem test/unit/core/os/paths \
    test/unit/core/data/text -q --disable-warnings
.venv/bin/ruff check pylizlib/core/os/snap pylizlib/core/os/filesystem \
    pylizlib/core/os/paths pylizlib/core/os/windows pylizlib/core/os/archives \
    pylizlib/core/data/text
make docs-snap
```

Characterization tests are in `test_refactor_contracts.py`; tests for the
extracted modules and strategies are in `test_refactor_modules.py`.
`test_public_api.py` and `test_second_refactor_contracts.py` compare signatures,
defaults, identity, and public fields against fixtures from before the two
refactors. `test/unit/core/test_documentation_contracts.py` requires typed
Google-style sections for parameters, returns/yields, and declared fields, as
well as a blank line before comment blocks. These structural checks supplement
semantic review and behavioral tests; they do not by themselves prove that the
text is correct.

The HTML preview is at `temp_local/docs_snap_preview/index.html` and is
generated with the `dev` group already declared in the project. The historical
HTML under `docs/` must be regenerated explicitly before publishing the updated
documentation.

For filesystem workflow changes, check both success and copy, rename, save, and
cleanup errors. Compare contents, JSON, and in-memory state. Use isolated local
copies: many older tests share a fixture root and are not designed for parallel
execution. Native Windows tests require a Windows runner and declare skips for
unavailable capabilities; drive, ACL, and ADS mocks separately verify errors
and call order. A local suite on another OS does not prove equivalence with
Win32 calls. The drive/ADS backends therefore retain the existing bindings
behind the new boundary; replacing them first requires native conformance
tests. SMB/NFS also require a real environment to claim additional persistence
guarantees.

## Logging in applications

The shared `PylizLib` logger retains its `NullHandler`: the library does not
install handlers or change the global level. The application configures
logging as needed. INFO events describe operations and actual recovery; DEBUG
exposes phases, persisted journal decisions, backup formats, and search counts.
Queries, file contents, previews, and complete JSON documents are not added to
logs. Some messages contain IDs and paths needed to identify a phase; the
application controls their visibility.
