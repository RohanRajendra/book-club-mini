"""Architecture tests — enforce 02-architecture.md §Layers by walking the AST.

Written in Phase 1, before there is anything to violate. They pass trivially today
and start earning their keep in Phase 5, which is the point: the cost of adding
them later is a refactor, the cost of adding them now is nothing.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"


def modules_under(package: str) -> list[Path]:
    return sorted((APP / package).rglob("*.py"))


def imported_modules(path: Path) -> set[str]:
    """Every module named by an import in `path`, as dotted strings."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import, which cannot cross a top-level
            # package boundary from inside app/, so it is always in-layer.
            if node.level == 0 and node.module:
                found.add(node.module)
    return found


def offending_imports(package: str, forbidden: tuple[str, ...]) -> list[str]:
    offences = []
    for path in modules_under(package):
        for module in imported_modules(path):
            for banned in forbidden:
                if module == banned or module.startswith(banned + "."):
                    offences.append(f"{path.relative_to(APP.parent)} imports {module}")
    return offences


def test_domain_does_not_import_application_interface_or_adapters():
    assert not offending_imports(
        "domain", ("app.application", "app.interface", "app.adapters")
    )


def test_application_does_not_import_adapters_or_interface():
    assert not offending_imports("application", ("app.adapters", "app.interface"))


def test_domain_does_not_import_a_framework_or_http_client():
    """phase-2 acceptance: the domain is pure Python."""
    assert not offending_imports("domain", ("httpx", "fastapi", "pydantic", "respx"))


def test_ports_do_not_import_adapters():
    """The direction of this import is the whole point (02 §Dependency inversion)."""
    assert not offending_imports(
        "ports", ("app.adapters", "app.interface", "app.application")
    )


@pytest.mark.parametrize("package", ["domain", "application", "ports"])
def test_transport_details_stay_inside_the_adapters(package):
    """Only adapters talk HTTP. The interface layer is exempt: it may catch
    NotionApiError to map it to 502, but it still must not speak httpx."""
    assert not offending_imports(package, ("httpx",))
