"""Public snapshot API, retaining original exports and class identities.

operations contains lifecycle, edit, install, sync, backup and transfer flows.
storage contains path, tree, publication, ZIP and metadata primitives.
Models retain their legacy construction side effects; see README.md for the
architecture and the operation-specific recovery boundaries."""

from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.copy_strategy import (
    DirectoryCopyStrategy,
    ProviderSnapshotCopyStrategy,
    SequentialFileCopyStrategy,
    SourceChangedError,
    SourceSnapshotProvider,
    VerifiedFileCopyStrategy,
)
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
from pylizlib.core.os.snap.integrity import IntegrityManifest, SnapshotIntegrityError
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.operations.install import SnapshotInstallMetadataError
from pylizlib.core.os.snap.searcher import (
    QueryType,
    SearchTarget,
    SnapshotProgressCallback,
    SnapshotSearcher,
    SnapshotSearchParams,
    SnapshotSearchResult,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.utils import SnapshotUtils

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
    # copy strategies
    "DirectoryCopyStrategy",
    "SequentialFileCopyStrategy",
    "VerifiedFileCopyStrategy",
    "SourceSnapshotProvider",
    "ProviderSnapshotCopyStrategy",
    "SourceChangedError",
    # integrity
    "IntegrityManifest",
    "SnapshotIntegrityError",
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
    "SnapshotInstallMetadataError",
]
