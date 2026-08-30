"""The fake_only marker does nothing on its own; this is the machinery.

Registering a marker only satisfies --strict-markers. The marker sits on the
shared contract class, so it applies to every subclass — including the in-memory
one it is meant to let through. This hook is what makes it selective.
"""

from __future__ import annotations

import pytest

from tests.conftest import pytest_collection_modifyitems


class FakeItem:
    def __init__(self, marker, cls):
        self._marker = marker
        self.cls = cls
        self.nodeid = "test_x"
        self.added: list = []

    def get_closest_marker(self, name):
        return self._marker if name == "fake_only" else None

    def add_marker(self, marker):
        self.added.append(marker)


class Transactional:
    supports_transactions = True


class Compensating:
    supports_transactions = False


def fake_only(**kwargs):
    return pytest.mark.fake_only(**kwargs).mark


def test_a_fake_only_test_is_skipped_for_a_compensating_implementation():
    item = FakeItem(fake_only(reason="no transactions"), Compensating)
    pytest_collection_modifyitems([item])
    assert [mark.name for mark in item.added] == ["skip"]
    assert "no transactions" in item.added[0].kwargs["reason"]


def test_a_fake_only_test_still_runs_for_a_transactional_implementation():
    item = FakeItem(fake_only(reason="no transactions"), Transactional)
    pytest_collection_modifyitems([item])
    assert item.added == []


def test_an_unmarked_test_is_untouched():
    item = FakeItem(None, Compensating)
    pytest_collection_modifyitems([item])
    assert item.added == []


def test_a_fake_only_marker_without_a_reason_is_an_error():
    """Every such marker needs a reason string."""
    item = FakeItem(fake_only(), Compensating)
    with pytest.raises(pytest.UsageError, match="reason"):
        pytest_collection_modifyitems([item])


def test_a_module_level_fake_only_test_outside_a_class_is_left_alone():
    item = FakeItem(fake_only(reason="r"), None)
    pytest_collection_modifyitems([item])
    assert item.added == []
