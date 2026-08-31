"""The shared contract suite, run against the Notion adapter.

The contract itself is not modified. If a contract test cannot pass, either the
adapter is wrong or the port is — a fourth fake_only marker means stopping to
reconsider the port design, not adding the marker.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.notion.http import BASE_URL, NotionHttpClient, TokenBucket
from app.adapters.notion.unit_of_work import NotionUnitOfWork
from tests.contract.test_unit_of_work_contract import UnitOfWorkContract
from tests.integration.notion_stub import BOOKS_DS, POSTS_DS, NotionStub


class NoWait:
    """The bucket's clock and sleep, so the contract suite does not spend
    seconds waiting on a token."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def build_uow(stub: NotionStub) -> NotionUnitOfWork:
    timing = NoWait()
    client = NotionHttpClient(
        token="ntn_test",
        client=httpx.AsyncClient(base_url=BASE_URL),
        bucket=TokenBucket(clock=timing, sleep=timing.sleep),
        sleep=timing.sleep,
    )
    return NotionUnitOfWork(client, BOOKS_DS, POSTS_DS)


class TestNotionUnitOfWork(UnitOfWorkContract):
    #: Rollback is compensating, not atomic, so the three transactional tests
    #: are skipped here and covered by the compensation tests instead.
    supports_transactions = False

    @pytest.fixture(autouse=True)
    def stub(self):
        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            stub = NotionStub()
            router.route().mock(side_effect=stub.handler)
            yield stub

    @pytest.fixture
    def uow(self, stub):
        return build_uow(stub)

    @pytest.fixture
    def tied_uow(self, stub):
        stub.hold_clock()
        return build_uow(stub)

    @pytest.fixture
    def uow_factory(self, stub):
        return lambda: build_uow(stub)
