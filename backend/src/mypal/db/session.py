"""Database engine and session handling.

We use synchronous SQLAlchemy: FastAPI runs plain `def` routes in a thread pool, so a blocking
database call does not block other requests. One engine (with its connection pool) is created
per app; each request gets its own short-lived Session.
"""

from collections.abc import Iterator
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
        connect_args={"connect_timeout": settings.database_connect_timeout},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False lets code read attributes of saved objects after commit.
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db_session(request: Request) -> Iterator[Session]:
    """One Session per request. Services decide when to commit; anything uncommitted is
    rolled back when the session closes."""
    with request.app.state.session_factory() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db_session)]
