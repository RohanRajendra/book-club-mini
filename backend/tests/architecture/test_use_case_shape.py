"""Architecture tests for the application layer."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.domain.errors import all_domain_errors

APP = Path(__file__).resolve().parents[2] / "app"
USE_CASES = APP / "application" / "use_cases"


def use_case_classes() -> list[tuple[str, ast.ClassDef]]:
    found = []
    for path in sorted(USE_CASES.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and any(
                isinstance(item, ast.AsyncFunctionDef) and item.name == "execute"
                for item in node.body
            ):
                found.append((path.name, node))
    return found


def test_there_are_use_cases_to_check():
    """Guard the guard: every assertion below passes vacuously on an empty
    list, and this phase's whole point is that the list is not empty."""
    assert len(use_case_classes()) >= 8


@pytest.mark.parametrize(
    "module,cls", use_case_classes(), ids=lambda arg: getattr(arg, "name", arg)
)
def test_every_use_case_returns_result(module, cls):
    execute = next(
        item
        for item in cls.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == "execute"
    )
    assert execute.returns is not None, f"{module}:{cls.name}.execute has no return type"
    assert "Result" in ast.unparse(execute.returns), (
        f"{module}:{cls.name}.execute returns {ast.unparse(execute.returns)}"
    )


@pytest.mark.parametrize(
    "module,cls", use_case_classes(), ids=lambda arg: getattr(arg, "name", arg)
)
def test_every_use_case_has_exactly_one_execute_method(module, cls):
    """A use case is one class with a single `execute`. A second public entry
    point means two use cases wearing one name."""
    public = [
        item.name
        for item in cls.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not item.name.startswith("_")
    ]
    assert public == ["execute"], f"{module}:{cls.name} exposes {public}"


def _names_used_in(package: Path) -> set[str]:
    used = set()
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Name):
                used.add(node.id)
    return used


def test_every_domain_error_is_returned_by_at_least_one_use_case():
    """Every declared error is returned by a use case, or it is deleted.

    An error nothing can produce is a mapping the HTTP layer maintains for a
    response that never happens.
    """
    used = _names_used_in(APP / "application")
    unused = sorted(
        error.__name__ for error in all_domain_errors() if error.__name__ not in used
    )
    assert not unused, f"defined but never returned: {unused}"
