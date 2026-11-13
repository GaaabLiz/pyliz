"""Characterize subtle contracts before extracting shared implementations."""

import ast
import importlib
import inspect
import json
from pathlib import Path

import pytest

from pylizlib.core.os import snap
from pylizlib.core.os.snap.searcher import SnapshotSearchResult, _ResultPage
from pylizlib.core.os.snap.storage import original_paths
from pylizlib.core.os.snap.storage.path_identity import same_filesystem_entry
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal


def _ast_dump(node):
    """Keep fixture comparison stable across Python AST dump versions."""
    try:
        return ast.dump(node, show_empty=True)
    except TypeError:
        return ast.dump(node)


def test_current_public_declarations_remain_compatible():
    """Protect APIs added after the first refactor, including class identities."""
    fixture = json.loads((Path(__file__).parent / "fixtures" / "public_api_v2.json").read_text())
    assert snap.__all__ == [*fixture["exports"], "SnapshotBusyError"]
    for name, expected in fixture["classes"].items():
        cls = getattr(snap, name)
        assert cls.__module__ == expected["module"]
        assert getattr(importlib.import_module(cls.__module__), name) is cls
        declaration = ast.parse(inspect.getsource(cls)).body[0]
        methods = {node.name: node for node in declaration.body if isinstance(node, ast.FunctionDef)}
        for method_name, signature in expected["methods"].items():
            method = methods[method_name]
            assert {
                "args": _ast_dump(method.args),
                "returns": _ast_dump(method.returns) if method.returns else None,
                "decorators": [_ast_dump(value) for value in method.decorator_list],
            } == signature, f"{name}.{method_name}"


@pytest.mark.parametrize("value", [None, 10, "", "relative", "bad\x00path", "Z:relative"])
def test_absolute_path_predicate_rejects_invalid_values_without_raising(value):
    """The predicate is tolerant even though the normalizer rejects invalid input."""
    assert original_paths.is_absolute_original_path(value) is False


def test_relative_path_keeps_parent_components(tmp_path, monkeypatch):
    """Anchoring must not collapse parent components through possible links."""
    monkeypatch.chdir(tmp_path)
    assert original_paths.normalize_original_path("alias/../source") == (tmp_path / "alias/../source").as_posix()


def test_missing_paths_use_lexical_identity(tmp_path):
    """Equal missing names compare equal; two different missing names do not."""
    assert same_filesystem_entry(tmp_path / "missing", tmp_path / "missing")
    assert not same_filesystem_entry(tmp_path / "missing", tmp_path / "other")


def test_identity_failure_retains_cause(tmp_path, monkeypatch):
    """An inaccessible filesystem identity is an error, not a negative match."""
    cause = PermissionError("cannot inspect entry")

    def fail_samefile(self, other):
        """Simulate a filesystem refusing the identity comparison."""
        raise cause

    monkeypatch.setattr(Path, "samefile", fail_samefile)
    with pytest.raises(ValueError, match="Cannot verify whether paths") as error:
        same_filesystem_entry(tmp_path / "first", tmp_path / "second")
    assert error.value.__cause__ is cause


def test_journal_state_names_do_not_impose_a_transition_graph(tmp_path, monkeypatch):
    """State validation accepts known names independently of the previous state."""
    data = {"state": "committed", "payload": {"future_field": [1, 2]}}
    journal = SnapshotTransactionJournal(tmp_path, data)
    writes = []
    monkeypatch.setattr(journal, "_write", lambda: writes.append(data["state"]))

    journal.set_state("prepared")
    journal.update_payload(extra=True)

    assert writes == ["prepared", "prepared"]
    assert journal.payload is data
    assert data["payload"] == {"future_field": [1, 2], "extra": True}
    with pytest.raises(ValueError, match="Unknown transaction state"):
        journal.set_state("invented")
    assert data["state"] == "prepared"


def test_file_page_retry_does_not_consume_parent_offset():
    """A failed decode attempt cannot retain matches or consume the global page."""
    parent = _ResultPage(offset_remaining=1, limit=2)
    result = SnapshotSearchResult(Path("file"), "query", "snapshot")
    failed_attempt = parent.fork()
    failed_attempt.add(result)
    failed_attempt.add(result)
    assert parent.offset_remaining == 1
    assert parent.results == []

    retry = parent.fork()
    retry.add(result)
    retry.add(result)
    parent.commit(retry)
    assert parent.offset_remaining == 0
    assert parent.results == [result]
