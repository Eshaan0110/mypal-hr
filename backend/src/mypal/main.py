"""Application factory.

Run with:  uv run uvicorn mypal.main:create_app --factory --reload
Using a factory (instead of a module-level `app`) means importing this module has no side effects,
and tests can create apps with their own Settings.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anyio import to_thread
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mypal.answering.llm import create_llm
from mypal.answering.service import AnswerDependencies
from mypal.api import admin, chat, feedback, health, info, me
from mypal.auth.dev import DEV_USER_HEADER, DEV_USERS, load_dev_users
from mypal.config import Settings, get_settings
from mypal.db.session import create_db_engine, create_session_factory
from mypal.errors import register_exception_handlers
from mypal.observability.logging import configure_logging
from mypal.observability.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from mypal.retrieval.retriever import create_retriever

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # `def` routes run in AnyIO's worker threads (40 by default). Never run more of them than
    # there are database connections, so a route never blocks waiting for one.
    settings: Settings = app.state.settings
    to_thread.current_default_thread_limiter().total_tokens = (
        settings.database_pool_size + settings.database_max_overflow
    )
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
    # The users the development login offers: the built-in fictional ones, or those of a
    # separately loaded data set.
    app.state.dev_users = (
        load_dev_users(settings.dev_users_file) if settings.dev_users_file else DEV_USERS
    )
    app.state.engine = create_db_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)
    # None of these connect or load a model yet; that happens on first use.
    app.state.answer_dependencies = AnswerDependencies(
        settings=settings,
        retriever=create_retriever(settings),
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
    app.include_router(info.router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    app.include_router(feedback.router, prefix=API_PREFIX)
    app.include_router(me.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    return app
