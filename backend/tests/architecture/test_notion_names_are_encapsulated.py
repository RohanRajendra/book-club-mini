"""No Notion property name may appear outside `app/adapters/notion/`.

Notion's property names are the most fragile knowledge in the codebase. Keeping
them in one module is what makes a rename in Notion a one-file change.

The scan covers `app/` only. `scripts/verify_notion.py` is deliberately outside
it: it is a standalone operator tool, not part of the application.

This file names the properties in order to look for them, so it exempts itself.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
ADAPTER = APP / "adapters" / "notion"

# The schema from 00-overview.md §Notion schema.
PROPERTY_NAMES = {
    "Title",
    "Author",
    "Status",
    "Total Chapters",
    "Name",
    "Book",
    "Member",
    "Type",
    "Body Preview",
    "Has Full Body",
    "Chapter",
    "Page",
    "Parent Post ID",
}


def string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_notion_property_names_appear_only_in_adapters_notion():
    offences = []
    for path in sorted(APP.rglob("*.py")):
        if ADAPTER in path.parents:
            continue
        leaked = string_literals(path) & PROPERTY_NAMES
        if leaked:
            offences.append(f"{path.relative_to(BACKEND)}: {sorted(leaked)}")

    assert not offences, (
        "Notion property names leaked outside app/adapters/notion/:\n"
        + "\n".join(offences)
    )


def test_the_scan_would_catch_a_leak():
    """Guard the guard.

    Every assertion above passes when `PROPERTY_NAMES` is empty or the walker is
    broken, so prove the mechanism detects a name in a file it is watching.
    """
    sample = ADAPTER.parent / "memory" / "__init__.py"
    assert not string_literals(sample) & PROPERTY_NAMES

    fake = ast.parse('X = "Body Preview"')
    leaked = {
        node.value
        for node in ast.walk(fake)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    } & PROPERTY_NAMES
    assert leaked == {"Body Preview"}
