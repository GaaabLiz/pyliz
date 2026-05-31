"""
Snapshot management package.

Re-exports all public symbols so that existing code using::

    from pylizlib.core.os.snap import SnapshotCatalogue, Snapshot, ...

continues to work unchanged regardless of which sub-module each class lives in.

Sub-modules:
    domain      – Pure data models (dataclasses, enums).
    serializer  – JSON serialization / deserialization.
    utils       – Stateless helper functions.
    manager     – Single-snapshot lifecycle manager.
    catalogue   – Multi-snapshot catalogue manager.
    searcher    – Full-text / filename search across snapshots.
"""

from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    SnapEditAction,
    SnapEditType,
    Snapshot,
    SnapshotBackupInfo,
    SnapshotSettings,
    SnapshotSortKey,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.utils import SnapshotUtils
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.searcher import (
    QueryType,
    SearchTarget,
    SnapshotProgressCallback,
    SnapshotSearcher,
    SnapshotSearchParams,
    SnapshotSearchResult,
)

__all__ = [
    # domain
    "BackupType",
    "SnapDirAssociation",
    "SnapEditAction",
    "SnapEditType",
    "Snapshot",
    "SnapshotBackupInfo",
    "SnapshotSettings",
    "SnapshotSortKey",
    # serializer
    "SnapshotSerializer",
    # utils
    "SnapshotUtils",
    # manager
    "SnapshotManager",
    # catalogue
    "SnapshotCatalogue",
    # searcher
    "QueryType",
    "SearchTarget",
    "SnapshotProgressCallback",
    "SnapshotSearcher",
    "SnapshotSearchParams",
    "SnapshotSearchResult",
]
