"""Reserve operational names at snapshot storage boundaries, preserving user data."""

import pytest

from pylizlib.core.os.snap import SequentialFileCopyStrategy
from pylizlib.core.os.snap.storage.paths import assert_no_transaction_storage, get_snapshot_path
from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree


@pytest.mark.parametrize("identity", [".pyliz_transactions", ".PYLIZ_TRANSACTIONS", ".pyliz_transactions. "])
def test_snapshot_ids_cannot_alias_the_transaction_directory(tmp_path, identity):
    """A published snapshot can never occupy the catalogue journal directory."""
    with pytest.raises(ValueError, match="[Tt]ransaction"):
        get_snapshot_path(identity, tmp_path)


def test_reserved_storage_policy_does_not_interpret_nested_user_data(tmp_path):
    """Only direct operational children belong to the trusted snapshot namespace."""
    nested = tmp_path / "association" / ".pyliz_transactions"
    nested.mkdir(parents=True)
    (nested / "journal.json").write_text("ordinary captured data")
    assert assert_no_transaction_storage(tmp_path) is None
    with pytest.raises(ValueError, match="transaction"):
        assert_no_transaction_storage(tmp_path / "association")


def test_publication_checks_the_actual_copy_before_replacing_a_target(tmp_path):
    """A strategy introducing a journal cannot bypass the input-tree check."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload").write_bytes(b"new")
    catalogue = tmp_path / "catalogue"
    destination = catalogue / "identity"
    destination.mkdir(parents=True)
    (destination / "payload").write_bytes(b"original")

    class InjectingStrategy(SequentialFileCopyStrategy):
        """Simulate a delegate changing the copied operational structure."""

        def copy_directory(self, source, destination, *args, **kwargs):
            """Create an otherwise valid copy containing unexpected journal storage."""
            copied = super().copy_directory(source, destination, *args, **kwargs)
            (copied / ".pyliz_transactions").mkdir()
            return copied

    with pytest.raises(ValueError, match="transaction"):
        publish_snapshot_tree(source, "identity", catalogue, replace_existing=True, copy_strategy=InjectingStrategy())
    assert (destination / "payload").read_bytes() == b"original"
    assert not list(catalogue.rglob("journal.json"))
