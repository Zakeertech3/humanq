from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Connection

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import ConnectionPoolEntry

from board.models import Base


def make_engine(db_path: str) -> Engine:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(
        dbapi_connection: Connection,
        connection_record: ConnectionPoolEntry,
    ) -> None:
        previous = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        dbapi_connection.autocommit = previous

    return engine


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    raise NotImplementedError


def get_session(engine: Engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
