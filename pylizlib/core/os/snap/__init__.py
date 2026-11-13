"""Public snapshot API, retaining original exports and class identities.

operations contains lifecycle, edit, install, sync, backup and transfer flows.
storage contains snapshot layout, metadata adapters and versioned recovery.
General path, filesystem, Windows, ZIP and text mechanisms live in their dedicated
pylizlib.core packages. Model construction normalizes source paths without a
recursive size scan; Windows mapped-drive normalization can query the OS.
See README.md for architecture and operation-specific recovery boundaries."""

from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.copy_strategy import (
    CopyMetadataMode,
    DirectoryCopyStrategy,
    ExtendedMetadataCopyStrategy,
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
from pylizlib.core.os.snap.operations.archives import SnapshotIncompleteError
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
from pylizlib.core.os.snap.storage.coordination import SnapshotBusyError
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
    "SnapshotIncompleteError",
    "CopyMetadataMode",
    "ExtendedMetadataCopyStrategy",
    "SnapshotBusyError",
]
