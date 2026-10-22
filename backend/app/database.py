"""Database engine and session helpers.

Member 2 owns engine/session/transaction (database/README.md v0.2 section 3);
Member 3 owns schema + Alembic migrations in `database/`.

`create_all` here is only for tests / throwaway demo databases. The demo runs
`alembic upgrade head` from `database/` instead.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (register tables on SQLModel.metadata)
from app.config import settings

logger = logging.getLogger(__name__)


def _build_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        # paho/WS workers run in other threads -> allow cross-thread sessions.
        connect_args["check_same_thread"] = False

    engine = create_engine(database_url, echo=False, connect_args=connect_args)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            # WAL keeps Dashboard reads from blocking MQTT writes.
            cursor.execute("PRAGMA journal_mode=WAL")
            # Foreign keys are off by default in SQLite.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _build_engine(settings.database_url)


def createTablesForTest() -> None:
    """Create tables directly - tests and disposable demo databases only.

    The real workflow is `alembic upgrade head` from `database/` (Member 3).
    """
    SQLModel.metadata.create_all(engine)


def ensureTablesIfAllowed() -> None:
    """Dev/demo convenience: AUTO_CREATE_TABLES=1 creates missing tables.

    Never used for the shared database, where migrations own the schema.
    """
    if not settings.auto_create_tables:
        return
    before = set(inspect(engine).get_table_names())
    SQLModel.metadata.create_all(engine)
    created = sorted(set(SQLModel.metadata.tables) - before)
    if created:
        logger.info("AUTO_CREATE_TABLES created: %s", ", ".join(created))


@contextmanager
def sessionScope() -> Iterator[Session]:
    """Short-lived transaction; never held open across MQTT or WS work."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def getSession() -> Iterator[Session]:
    """FastAPI dependency."""
    with sessionScope() as session:
        yield session


def checkDatabase() -> bool:
    """Health probe used by GET /api/health."""
    try:
        with Session(engine) as session:
            session.exec(models.DeviceState.__table__.select().limit(1))
        return True
    except Exception:
        return False
