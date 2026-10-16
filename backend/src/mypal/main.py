"""Application factory.

Run with:  uv run uvicorn mypal.main:create_app --factory --reload
Using a factory (instead of a module-level `app`) means importing this module has no side effects,
and tests can create apps with their own Settings.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mypal.answering.llm import create_llm
from mypal.answering.service import AnswerDependencies
from mypal.api import chat, health
from mypal.auth.dev import DEV_USER_HEADER
from mypal.config import Settings, get_settings
from mypal.db.session import create_db_engine, create_session_factory
from mypal.errors import register_exception_handlers
from mypal.observability.logging import configure_logging
from mypal.observability.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from mypal.retrieval.embeddings import create_embedder
from mypal.retrieval.index import create_index

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # On shutdown, close pooled database connections cleanly.
    app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        docs_url="/api/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = create_db_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)
    # None of these connect or load a model yet; that happens on first use.
    app.state.answer_dependencies = AnswerDependencies(
        settings=settings,
        embedder=create_embedder(settings),
        index=create_index(settings),
        llm=create_llm(settings),
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER, DEV_USER_HEADER],
            expose_headers=[REQUEST_ID_HEADER],
        )
    # Added last so it is the outermost user middleware and wraps everything else.
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    return app
