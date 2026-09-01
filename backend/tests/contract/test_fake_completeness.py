"""Guards that are not part of the contract itself."""

from __future__ import annotations

import inspect

import pytest

from app.adapters.memory import (
    InMemoryBookRepository,
    InMemoryPostRepository,
    InMemoryUnitOfWork,
)
from app.ports.repositories import BookRepository, PostRepository
from app.ports.unit_of_work import UnitOfWork

from tests.contract.test_unit_of_work_contract import UnitOfWorkContract

PAIRS = [
    (BookRepository, InMemoryBookRepository),
    (PostRepository, InMemoryPostRepository),
    (UnitOfWork, InMemoryUnitOfWork),
]


@pytest.mark.parametrize("port,fake", PAIRS, ids=lambda arg: arg.__name__)
def test_in_memory_repositories_implement_every_abstract_method(port, fake):
    """A port method added later and never implemented on the fake would
    otherwise surface as a confusing failure inside an unrelated test."""
    unimplemented = [
        name
        for name in getattr(port, "__abstractmethods__", ())
        if getattr(fake, name, None) is getattr(port, name, None)
    ]
    assert not unimplemented, f"{fake.__name__} does not implement {unimplemented}"


@pytest.mark.parametrize("port,fake", PAIRS, ids=lambda arg: arg.__name__)
def test_the_fake_matches_each_port_signature(port, fake):
    """Same names is not enough — a fake with a different signature passes the
    contract suite and then breaks the first real caller."""
    mismatches = []
    for name in getattr(port, "__abstractmethods__", ()):
        expected = inspect.signature(getattr(port, name))
        actual = inspect.signature(getattr(fake, name))
        if list(expected.parameters) != list(actual.parameters):
            mismatches.append(f"{name}: {expected} != {actual}")
    assert not mismatches


def test_the_fake_is_instantiable():
    """ABCs refuse instantiation while an abstract method is outstanding, so
    this is the cheapest possible completeness check."""
    assert isinstance(InMemoryUnitOfWork(), UnitOfWork)


def fake_only_tests() -> list[str]:
    return [
        name
        for name, member in vars(UnitOfWorkContract).items()
        if name.startswith("test_")
        and any(
            mark.name == "fake_only" for mark in getattr(member, "pytestmark", [])
        )
    ]


def test_the_contract_carries_exactly_three_fake_only_markers():
    """All three share one root cause: a store without transactions cannot
    provide real rollback. A fourth marker should prompt a review of the port
    design rather than another marker."""
    assert sorted(fake_only_tests()) == [
        "test_rollback_discards_an_added_post",
        "test_rollback_discards_an_update",
        "test_rollback_restores_an_archived_post",
    ]


def test_every_fake_only_marker_carries_a_reason():
    for name in fake_only_tests():
        member = vars(UnitOfWorkContract)[name]
        for mark in member.pytestmark:
            if mark.name == "fake_only":
                assert mark.kwargs.get("reason"), name


def test_the_in_memory_adapter_does_not_depend_on_notion_or_httpx():
    """Checks imports, not prose — the docstrings legitimately discuss Notion,
    since the fake's whole job is to mirror its observable behaviour."""
    import ast

    import app.adapters.memory.store as store

    tree = ast.parse(inspect.getsource(store))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = {
        name
        for name in imported
        if name.split(".")[0] == "httpx" or "notion" in name.lower()
    }
    assert not forbidden


class _Recording(UnitOfWork):
    """A minimal implementation, to test the port's own behaviour.

    Both real adapters make `rollback` a no-op after a commit — the fake clears
    its snapshot, the Notion one clears its compensation stack — so neither can
    show whether the port actually stops calling it. A backend whose rollback is
    not idempotent would find out in production.
    """

    def __init__(self) -> None:
        self.books = None
        self.posts = None
        self.on_commit = []
        self.commits = 0
        self.rollbacks = 0

    async def _commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class TestUnitOfWorkScope:
    async def test_a_committed_scope_does_not_roll_back(self):
        uow = _Recording()
        async with uow:
            await uow.commit()
        assert (uow.commits, uow.rollbacks) == (1, 0)

    async def test_an_uncommitted_scope_rolls_back(self):
        uow = _Recording()
        async with uow:
            pass
        assert (uow.commits, uow.rollbacks) == (0, 1)

    async def test_an_exception_rolls_back_and_propagates(self):
        uow = _Recording()
        with pytest.raises(RuntimeError):
            async with uow:
                raise RuntimeError("boom")
        assert uow.rollbacks == 1

    async def test_an_exception_after_a_commit_does_not_roll_back(self):
        """Commit is a durability boundary, and both adapters discard their
        undo record when they cross it — the fake drops its snapshot, the
        Notion one clears its compensation stack. There is nothing left to
        undo, so the exception propagates without a rollback that could only
        pretend to work.

        The corollary, worth knowing: writes made *after* a commit inside the
        same scope are not covered by anything."""
        uow = _Recording()
        with pytest.raises(RuntimeError):
            async with uow:
                await uow.commit()
                raise RuntimeError("boom")
        assert uow.rollbacks == 0

    async def test_a_reused_unit_of_work_starts_each_scope_uncommitted(self):
        uow = _Recording()
        async with uow:
            await uow.commit()
        async with uow:
            pass
        assert uow.rollbacks == 1
