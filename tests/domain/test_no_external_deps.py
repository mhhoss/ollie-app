"""
Mechanically enforces the architectural rule stated in
ollie/domain/__init__.py and ollie/fmt/__init__.py: both packages
import only the standard library and their own modules — never
aiogram, sqlite3, ollie.bot, ollie.db, or each other. This is a test,
not a convention, precisely so a future handler can't quietly import
domain logic that has grown a database dependency without anyone
noticing until it's load-bearing.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_PACKAGES = ("ollie.domain", "ollie.fmt")

_STDLIB_NAMES = sys.stdlib_module_names | {"__future__"}


def _python_files(package: str) -> list[Path]:
    package_dir = _SRC_ROOT.joinpath(*package.split("."))
    assert package_dir.is_dir(), f"expected {package_dir} to exist"
    return sorted(package_dir.rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    """Full dotted module names this file imports. Relative imports
    (`from .errors import X`, level > 0) are omitted deliberately —
    they always resolve within the importing file's own package, so
    they can never reach outside ollie.domain / ollie.fmt and don't
    need to be checked."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                modules.add(node.module)
    return modules


def _is_allowed(module: str) -> bool:
    top = module.split(".")[0]
    if top in _STDLIB_NAMES:
        return True
    # Only ollie.domain / ollie.fmt themselves — never ollie.bot,
    # ollie.db, or anything else under the ollie namespace.
    if module == "ollie":
        return True
    return any(module == pkg or module.startswith(pkg + ".") for pkg in _PACKAGES)


def test_domain_and_fmt_import_only_stdlib_and_themselves() -> None:
    violations: list[str] = []
    for package in _PACKAGES:
        for path in _python_files(package):
            for module in sorted(_imported_modules(path)):
                if not _is_allowed(module):
                    rel = path.relative_to(_SRC_ROOT)
                    violations.append(f"{rel}: disallowed import {module!r}")

    assert not violations, "Domain/fmt isolation violated:\n" + "\n".join(violations)


def test_domain_never_imports_fmt_and_vice_versa() -> None:
    """The two packages are independent siblings by design — only the
    bot layer is meant to compose them together."""
    violations: list[str] = []
    for path in _python_files("ollie.domain"):
        for module in _imported_modules(path):
            if module == "ollie.fmt" or module.startswith("ollie.fmt."):
                violations.append(f"{path.relative_to(_SRC_ROOT)}: domain imports fmt ({module!r})")
    for path in _python_files("ollie.fmt"):
        for module in _imported_modules(path):
            if module == "ollie.domain" or module.startswith("ollie.domain."):
                violations.append(f"{path.relative_to(_SRC_ROOT)}: fmt imports domain ({module!r})")

    assert not violations, "\n".join(violations)


def test_both_packages_have_python_files_to_check() -> None:
    """A guard against this test silently passing because a package
    directory doesn't exist yet or is empty."""
    for package in _PACKAGES:
        files = _python_files(package)
        assert files, f"{package} has no .py files — isolation check would be vacuous"
