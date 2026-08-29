"""The DI container.

Hand-written, not `dependency-injector`. Sixty explicit lines read better than
string-keyed provider wiring, and the wiring is the part a newcomer most needs
to be able to read.

Its real job is that the object graph is constructible from HTTP handlers, from
tests, and from scripts. `Depends` covers only the first.
"""

from __future__ import annotations

from typing import Callable

from app.adapters.notion.http import NotionHttpClient
from app.adapters.notion.ids import DataSourceResolver
from app.adapters.notion.unit_of_work import NotionUnitOfWork
from app.application.caching import CachingFeedQuery
from app.application.feed import FeedAssembler
from app.application.use_cases.books import AddBook, ListBooks, UpdateBook
from app.application.use_cases.create_post import CreatePost
from app.application.use_cases.delete_post import DeletePost
from app.application.use_cases.edit_post import EditPost
from app.application.use_cases.get_feed import GetFeed
from app.application.use_cases.get_post_body import GetPostBody
from app.config import Settings
from app.domain.policies import ChapterFirstSpoilerPolicy
from app.domain.services import BodySplitter, PositionResolver, ScaleCalculator
from app.domain.values import MemberName
from app.ports.unit_of_work import UnitOfWork


class Container:
    def __init__(
        self,
        settings: Settings,
        uow_factory: Callable[[], UnitOfWork] | None = None,
    ) -> None:
        """`uow_factory` is the seam that lets tests and scripts build the whole
        graph with in-memory adapters and no HTTP at all."""
        self.settings = settings
        self._uow_override = uow_factory

        self._client: NotionHttpClient | None = None
        self.books_data_source_id: str | None = None
        self.posts_data_source_id: str | None = None

        self.roster = [MemberName(name) for name in settings.members]
        self.member = MemberName(settings.member_name)

        # Singletons: stateless policies and the one cache.
        self._spoiler_policy = ChapterFirstSpoilerPolicy()
        self._splitter = BodySplitter()
        self._assembler = FeedAssembler(
            spoiler_policy=self._spoiler_policy,
            position_resolver=PositionResolver(),
            scale_calculator=ScaleCalculator(),
            roster=self.roster,
        )
        self._cache = CachingFeedQuery(GetFeed(self.uow_factory(), self._assembler))

    async def startup(self) -> None:
        """Resolve data source IDs once. Failing here fails at boot rather than
        on the first request."""
        if self._uow_override is not None:
            return

        self._client = NotionHttpClient(self.settings.notion_token)
        resolver = DataSourceResolver(self._client)
        self.books_data_source_id = await resolver.resolve(
            self.settings.notion_books_db_id
        )
        self.posts_data_source_id = await resolver.resolve(
            self.settings.notion_posts_db_id
        )

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------ the graph

    def uow_factory(self) -> Callable[[], UnitOfWork]:
        def build() -> UnitOfWork:
            uow = self._build_uow()
            # The single invalidation hook. Nothing else has to remember.
            uow.on_commit.append(self._cache.invalidate)
            return uow

        return build

    def _build_uow(self) -> UnitOfWork:
        if self._uow_override is not None:
            return self._uow_override()
        if self._client is None:
            raise RuntimeError("Container.startup() has not run")
        return NotionUnitOfWork(
            self._client, self.books_data_source_id, self.posts_data_source_id
        )

    # One accessor per use case. Built per call: they are cheap and stateless.

    def list_books(self) -> ListBooks:
        return ListBooks(self.uow_factory())

    def add_book(self) -> AddBook:
        return AddBook(self.uow_factory())

    def update_book(self) -> UpdateBook:
        return UpdateBook(self.uow_factory())

    def get_feed(self) -> CachingFeedQuery:
        return self._cache

    def create_post(self) -> CreatePost:
        return CreatePost(self.uow_factory(), self.roster, self._splitter)

    def edit_post(self) -> EditPost:
        return EditPost(self.uow_factory(), self._splitter)

    def delete_post(self) -> DeletePost:
        return DeletePost(self.uow_factory())

    def get_post_body(self) -> GetPostBody:
        return GetPostBody(self.uow_factory())
