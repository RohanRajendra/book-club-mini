"""Shared pytest configuration.

The `fake_only` marker sits on the shared abstract contract class, so it applies
to *every* subclass — including the in-memory one it is meant to let through.
Registering the marker skips nothing on its own; this hook is what makes it mean
something.

Skipping keys on a declared capability rather than a class name, so a future
adapter with real transactions runs those tests automatically. That is the
concrete meaning of the swappability goal.
"""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        marker = item.get_closest_marker("fake_only")
        if marker is None:
            continue

        cls = getattr(item, "cls", None)
        if cls is None or getattr(cls, "supports_transactions", True):
            continue

        reason = marker.kwargs.get("reason") or (
            marker.args[0] if marker.args else None
        )
        if not reason:
            raise pytest.UsageError(
                f"{item.nodeid}: @pytest.mark.fake_only requires a reason string"
            )
        item.add_marker(pytest.mark.skip(reason=f"fake_only: {reason}"))
