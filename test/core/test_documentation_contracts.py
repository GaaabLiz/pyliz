"""Require complete typed Google sections for the refactored public-library code.

These checks enforce the chosen documentation convention. They do not prove
that descriptions or exception policies are semantically correct; behavioral
tests and review remain responsible for that part of the contract.
"""

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTED_PACKAGES = ["pylizlib/core/data/text", "pylizlib/core/os/filesystem", "pylizlib/core/os/paths", "pylizlib/core/os/windows", "pylizlib/core/os/archives", "pylizlib/core/os/snap"]


def section_entries(docstring: str, section: str) -> set[str]:
    """Read typed entry names from one canonical Google section used by this repo."""
    match = re.search(rf"(?ms)^{section}:\n(.*?)(?=^\w+:\n|\Z)", docstring)
    if match is None:
        return set()
    return set(re.findall(r"(?m)^    \*{0,2}(\w+) \([^\n]+\):", match.group(1)))


def documentation_errors(source: str) -> list[str]:
    """Report missing typed arguments, results and declared public model fields."""
    errors = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node)
        if not docstring:
            errors.append(f"{node.name}: missing docstring")
            continue
        if isinstance(node, ast.ClassDef):
            fields = {item.target.id for item in node.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and not item.target.id.startswith("_")}
            missing = fields - section_entries(docstring, "Attributes")
            if missing:
                errors.append(f"{node.name}: undocumented attributes {sorted(missing)}")
            continue
        parameters = {arg.arg for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs] if arg.arg not in {"self", "cls"}}
        parameters.update(arg.arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
        missing = parameters - section_entries(docstring, "Args")
        if missing:
            errors.append(f"{node.name}: undocumented parameters {sorted(missing)}")
        if not re.search(r"(?m)^(Returns|Yields):\n    [^\n:]+: \S", docstring):
            errors.append(f"{node.name}: missing typed return/yield description")
    return errors


@pytest.mark.parametrize("package", DOCUMENTED_PACKAGES)
def test_refactored_packages_have_complete_structured_documentation(package):
    """Every explicit callable and declared field has a typed documented contract."""
    errors = []
    for path in sorted((ROOT / package).rglob("*.py")):
        errors.extend(f"{path.relative_to(ROOT)}: {error}" for error in documentation_errors(path.read_text()))
    assert errors == []


def test_documentation_check_rejects_presence_only_docstrings():
    """A non-empty sentence alone cannot satisfy the parameter/result/field gate."""
    source = 'class Model:\n    """A model."""\n    size: int\n\ndef operation(path: str):\n    """Do the operation."""\n    return None\n'
    errors = documentation_errors(source)
    assert any("undocumented attributes ['size']" in error for error in errors)
    assert any("undocumented parameters ['path']" in error for error in errors)
    assert any("missing typed return/yield" in error for error in errors)


@pytest.mark.parametrize("package", DOCUMENTED_PACKAGES)
def test_function_comment_blocks_have_preceding_blank_lines(package):
    """Logical comment blocks follow the spacing requested for complex methods."""
    errors = []
    for path in sorted((ROOT / package).rglob("*.py")):
        source = path.read_text()
        lines = source.splitlines()
        functions = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)]
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            index = token.start[0] - 1
            in_function = any(node.lineno < index + 1 <= node.end_lineno for node in functions)
            if token.type != tokenize.COMMENT or not in_function or not index:
                continue
            if lines[index].lstrip().startswith("#") and lines[index - 1].strip() and not lines[index - 1].lstrip().startswith("#"):
                errors.append(f"{path.relative_to(ROOT)}:{index + 1}")
    assert errors == []
