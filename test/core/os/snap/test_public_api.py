"""Guard the pre-refactor snapshot API and the requested documentation contract.

The fixture records declarations from revision 8f45eac, before any extraction.
New private collaborators are unrestricted; legacy parameters, dataclass fields,
enum values, class locations and package exports remain compatible.
"""

import ast
import importlib
import inspect
import json
from pathlib import Path

from pylizlib.core.os import snap

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "public_api.json").read_text())


def test_original_exports_and_class_locations_are_preserved():
    """Old exports remain stable while new documented errors can be added."""
    assert snap.__all__ == [*FIXTURE["exports"], "SnapshotInstallMetadataError"]
    for qualified_name in FIXTURE["classes"]:
        module_name, class_name = qualified_name.split(".")
        module = importlib.import_module(f"pylizlib.core.os.snap.{module_name}")
        cls = getattr(module, class_name)
        assert cls.__module__ == module.__name__
        if class_name in snap.__all__:
            assert getattr(snap, class_name) is cls


def test_original_method_signatures_fields_and_enum_values_are_preserved():
    """The refactor changes method bodies, not callers' declared API contracts."""
    for qualified_name, expected in FIXTURE["classes"].items():
        module_name, class_name = qualified_name.split(".")
        module = importlib.import_module(f"pylizlib.core.os.snap.{module_name}")
        tree = ast.parse(inspect.getsource(module))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        for name, declaration in expected["methods"].items():
            method = methods[name]
            actual = {
                "args": ast.dump(method.args),
                "returns": ast.dump(method.returns) if method.returns else None,
                "decorators": [ast.dump(d) for d in method.decorator_list],
            }
            assert actual == declaration, f"{qualified_name}.{name}"
        fields = {n.target.id: ast.dump(n) for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
        for name, declaration in expected["fields"].items():
            assert fields[name] == declaration, f"{qualified_name}.{name}"
        runtime_class = getattr(module, class_name)
        for name, value in expected["enum_values"].items():
            assert getattr(runtime_class, name).value == value


def test_all_snapshot_classes_and_functions_have_documentation():
    """Require docstrings for use cases, helpers and nested callbacks alike."""
    root = Path(snap.__file__).parent
    undocumented = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and not ast.get_docstring(node):
                undocumented.append(f"{path.relative_to(root)}:{node.lineno} {node.name}")
    assert undocumented == []
