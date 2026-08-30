"""The FastAPI application.

No CORSMiddleware: the Vite dev proxy puts both servers on one origin. If a
CORS error appears, the proxy is misconfigured — fix the proxy.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from app.adapters.notion.http import NotionApiError
from app.composition import Container
from app.config import Settings
from app.interface.errors import NOTION_UNREACHABLE, UNEXPECTED, error_response
from app.interface.routers.api import router

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = Container(Settings())
    # Failing to resolve data source IDs must fail at boot, not on the first
    # request.
    await container.startup()
    app.state.container = container
    try:
        yield
    finally:
        await container.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="Book Club", lifespan=lifespan)
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(422, _first_message(exc))

    @app.exception_handler(NotionApiError)
    async def notion_error(request: Request, exc: NotionApiError):
        # A raw Notion error body must never reach the browser.
        logger.error("notion %s %s: %s", exc.status, exc.code, exc.notion_message)
        return error_response(502, NOTION_UNREACHABLE)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("unhandled error on %s", request.url.path)
        return error_response(500, UNEXPECTED)

    return app


def _first_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:  # pragma: no cover - pydantic always reports at least one
        return "That request wasn't valid."
    first = errors[0]
    field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    return f"{field}: {first.get('msg', 'invalid')}" if field else first.get("msg", "invalid")


app = create_app()
