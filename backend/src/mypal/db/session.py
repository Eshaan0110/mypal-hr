"""Database engine and session handling.

We use synchronous SQLAlchemy: FastAPI runs plain `def` routes in a thread pool, so a blocking
database call does not block other requests. One engine (with its connection pool) is created
per app; each request gets its own short-lived Session.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from mypal.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    # Creating an engine does not connect yet; the first query does.
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,  # replace connections the database has silently closed
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        connect_args={"connect_timeout": settings.database_connect_timeout},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False lets code read attributes of saved objects after commit.
    return sessionmaker(bind=engine, expire_on_commit=False)


async def get_db_session(request: Request) -> AsyncIterator[Session]:
    """One Session per request. Services decide when to commit; anything uncommitted is
    rolled back when the session closes.

    Deliberately `async`: FastAPI runs the clean-up of a plain generator dependency in its worker
    thread pool, so under load every thread could be busy waiting for a connection while the
    requests holding connections waited for a thread to release them - a deadlock. Closing on
    the event loop needs no thread, so connections always come back. (The Session itself is
    still used synchronously by the `def` routes.)"""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db_session)]
