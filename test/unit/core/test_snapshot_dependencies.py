"""Keep reusable text/filesystem mechanisms independent from snapshot policy."""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERAL_PACKAGES = ["core/data/text", "core/os/paths", "core/os/filesystem", "core/os/windows", "core/os/archives"]


def test_general_packages_never_import_snapshot_policy():
    """Reject reverse imports, including imports guarded by TYPE_CHECKING."""
    violations = []
    for package in GENERAL_PACKAGES:
        for path in (ROOT / "pylizlib" / package).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                imports = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                if any(name == "pylizlib.core.os.snap" or name.startswith("pylizlib.core.os.snap.") for name in imports):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert violations == []


def test_every_shared_module_imports_without_loading_snapshot_or_native_bindings():
    """Exercise all extracted modules in a clean interpreter on each CI platform."""
    modules = []
    for package in GENERAL_PACKAGES:
        for path in sorted((ROOT / "pylizlib" / package).rglob("*.py")):
            parts = path.relative_to(ROOT).with_suffix("").parts
            modules.append(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    code = "\n".join(
        [
            "import importlib, sys",
            f"for name in {json.dumps(modules)}: importlib.import_module(name)",
            "assert not any(name.startswith('pylizlib.core.os.snap') for name in sys.modules)",
            "assert not {'win32security', 'win32file', 'win32wnet'} & sys.modules.keys()",
        ]
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
