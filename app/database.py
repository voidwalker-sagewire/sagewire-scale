mport os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:////data/scale.db",
)


def prepare_sqlite_directory(database_url: str) -> None:
    """
    Create the parent directory for the SQLite database when necessary.

    Production default:
        /data/scale.db
    """

    sqlite_prefix = "sqlite:///"

    if not database_url.startswith(sqlite_prefix):
        return

    database_path = database_url.removeprefix(sqlite_prefix)

    if database_path == ":memory:":
        return

    Path(database_path).parent.mkdir(
        parents=True,
        exist_ok=True,
    )


prepare_sqlite_directory(DATABASE_URL)


connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """
    Parent class for all SageWire Scale Service database tables.
    """

    pass


def get_db() -> Generator[Session, None, None]:
    """
    Give an API request a database session and close it afterward.
    """

    database = SessionLocal()

    try:
        yield database
    finally:
        database.close()
