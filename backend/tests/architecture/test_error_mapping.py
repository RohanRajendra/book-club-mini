"""Every domain error must have an HTTP mapping.

An architecture test rather than a unit test: adding a domain error without a
mapping should fail the build, because the default would otherwise be a silent
500 in production.
"""

from __future__ import annotations

import pytest

from app.domain.errors import all_domain_errors
from app.interface.errors import NOTION_UNREACHABLE, STATUS_BY_CODE


def test_every_domain_error_subclass_appears_in_the_mapping():
    unmapped = sorted(
        error.__name__ for error in all_domain_errors() if error.code not in STATUS_BY_CODE
    )
    assert not unmapped, f"no HTTP status for: {unmapped}"


def test_the_mapping_has_no_entries_for_errors_that_no_longer_exist():
    live = {error.code for error in all_domain_errors()}
    stale = sorted(code for code in STATUS_BY_CODE if code not in live)
    assert not stale


@pytest.mark.parametrize("code,status", sorted(STATUS_BY_CODE.items()))
def test_every_mapped_status_is_a_client_error(code, status):
    """A domain error is something the caller did, never a server fault."""
    assert 400 <= status < 500


def test_the_notion_message_matches_the_ux_copy_exactly():
    """01-ux-spec.md §Empty and error copy. The frontend displays it verbatim
    rather than substituting its own."""
    assert NOTION_UNREACHABLE == "Can't reach Notion right now. Try refreshing."


def test_no_cors_middleware_anywhere_in_the_codebase():
    """phase-6 §6.6: the Vite dev proxy puts both servers on one origin. If a
    CORS error appears, the proxy is misconfigured — fix the proxy.

    Looks for the identifier in code, not the word in prose: main.py's
    docstring says why CORS is absent, and that comment is the point.
    """
    import ast
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[2] / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            named = (
                isinstance(node, ast.Name) and node.id == "CORSMiddleware"
            ) or (isinstance(node, ast.Attribute) and node.attr == "CORSMiddleware")
            imported = isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                alias.name.endswith("CORSMiddleware") for alias in node.names
            )
            if named or imported:
                offenders.append(path.name)
    assert not offenders
