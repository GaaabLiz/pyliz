"""Persist the live destinations installed by snapshots in the local catalogue."""

import json
from dataclasses import dataclass
from pathlib import Path

from pylizlib.core.os.snap.serializer import SnapshotSerializer

INSTALL_REGISTRY_FILENAME = ".pyliz_installed_copies.json"
INSTALL_REGISTRY_FORMAT = "pyliz-installed-copies"
INSTALL_REGISTRY_VERSION = 1


@dataclass(frozen=True)
class InstalledCopy:
    """One destination published by a completed snapshot installation.

    Attributes:
        folder_id (str): Stable association identity recorded at install time.
        path (Path): Absolute lexical destination published by the installer.
        state (str): ``installed`` or ``removing``; pending removals are hidden from automatic retry.
    """

    folder_id: str
    path: Path
    state: str = "installed"


class InstalledCopyRegistry:
    """Read and atomically update catalogue-local installation records.

    A missing snapshot entry means the installation history is unknown (legacy
    metadata); an empty list means the history is known and no target is live.
    The registry is outside snapshot trees so its machine-specific paths are
    never copied into snapshot archives or catalogue exports.
    """

    def __init__(self, path_catalogue: Path):
        """Bind the registry to a catalogue directory.

        Args:
            path_catalogue (Path): Catalogue directory storing snapshot metadata and the local registry file.

        Returns:
            None: No return value.
        """
        self.path = Path(path_catalogue) / INSTALL_REGISTRY_FILENAME

    def get(self, snapshot_id: str) -> list[InstalledCopy] | None:
        """Read one snapshot's installed destinations, or None when untracked.

        Args:
            snapshot_id (str): Snapshot identity used as the registry key.

        Returns:
            list[InstalledCopy] | None: Known installed destinations, including an empty list, or None if untracked.

        Raises:
            ValueError: The persisted registry has an invalid format or destination entry.
        """
        data = self._read()
        raw_records = data["snapshots"].get(snapshot_id)
        if raw_records is None:
            return None
        return [InstalledCopy(record["folder_id"], Path(record["path"]), record.get("state", "installed")) for record in raw_records]

    def set(self, snapshot_id: str, records: list[InstalledCopy]) -> None:
        """Atomically replace one snapshot's installed destination list.

        Args:
            snapshot_id (str): Snapshot identity used as the registry key.
            records (list[InstalledCopy]): Complete new list of registered destinations.

        Returns:
            None: No return value.

        Raises:
            OSError: The registry cannot be atomically written.
            ValueError: The existing registry has an invalid format or destination entry.
        """
        data = self._read()
        data["snapshots"][snapshot_id] = [
            {"folder_id": record.folder_id, "path": record.path.as_posix(), "state": record.state} for record in records
        ]
        SnapshotSerializer.write_text(self.path, json.dumps(data, ensure_ascii=False, indent=2))

    def register(self, snapshot_id: str, records: list[InstalledCopy]) -> None:
        """Add successfully installed paths while preserving earlier live targets.

        Args:
            snapshot_id (str): Snapshot identity used as the registry key.
            records (list[InstalledCopy]): Destinations confirmed by the completed installation.

        Returns:
            None: No return value.

        Raises:
            OSError: The updated registry cannot be atomically written.
            ValueError: The persisted registry has an invalid format or destination entry.
        """
        current = self.get(snapshot_id) or []
        known = {(record.folder_id, record.path) for record in current}
        for record in records:
            key = (record.folder_id, record.path)
            if key not in known:
                current.append(record)
                known.add(key)
            else:
                current = [
                    InstalledCopy(existing.folder_id, existing.path, "installed")
                    if (existing.folder_id, existing.path) == key
                    else existing
                    for existing in current
                ]
        self.set(snapshot_id, current)

    def _read(self) -> dict:
        """Load and validate the complete registry; malformed state fails closed.

        Returns:
            dict: Registry document with format, version and snapshot destination records.

        Raises:
            OSError: The registry cannot be read.
            ValueError: The persisted registry has an invalid format or destination entry.
        """
        try:
            contents = SnapshotSerializer.read_text(self.path)
        except FileNotFoundError:
            return {"format": INSTALL_REGISTRY_FORMAT, "version": INSTALL_REGISTRY_VERSION, "snapshots": {}}

        data = json.loads(contents)
        if (
            not isinstance(data, dict)
            or data.get("format") != INSTALL_REGISTRY_FORMAT
            or type(data.get("version")) is not int
            or data["version"] != INSTALL_REGISTRY_VERSION
            or not isinstance(data.get("snapshots"), dict)
        ):
            raise ValueError(f"Installed-copy registry '{self.path}' has an invalid format.")

        for snapshot_id, records in data["snapshots"].items():
            if not isinstance(snapshot_id, str) or not isinstance(records, list):
                raise ValueError(f"Installed-copy registry '{self.path}' contains an invalid snapshot entry.")
            seen = set()
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError(f"Installed-copy registry '{self.path}' contains an invalid destination entry.")
                folder_id, raw_path = record.get("folder_id"), record.get("path")
                if not isinstance(folder_id, str) or not folder_id or not isinstance(raw_path, str) or not raw_path:
                    raise ValueError(f"Installed-copy registry '{self.path}' contains an invalid destination entry.")
                path = Path(raw_path)
                state = record.get("state", "installed")
                if not isinstance(state, str) or state not in {"installed", "removing"}:
                    raise ValueError(f"Installed-copy registry '{self.path}' contains an invalid destination state.")
                if not path.is_absolute() or "\x00" in raw_path:
                    raise ValueError(f"Installed-copy registry '{self.path}' contains an invalid destination path.")
                identity = (folder_id, path)
                if identity in seen:
                    raise ValueError(f"Installed-copy registry '{self.path}' contains duplicate destinations.")
                seen.add(identity)
        return data
