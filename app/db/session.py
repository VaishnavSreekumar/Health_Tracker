"""Database session management, engine lifecycle, and initialization."""

from collections.abc import Generator
from typing import Any, Optional
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base


def configure_sqlite_pragmas(engine: Engine) -> None:
    """Attach listener to enable SQLite foreign key constraints on connection."""
    @event.listens_for(engine, "connect")
    def _set_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


def create_db_engine(database_url: Optional[str] = None, **kwargs: Any) -> Engine:
    """Create a configured SQLAlchemy Engine.

    Enforces SQLite foreign keys if using SQLite and configures appropriate thread settings.
    """
    url = database_url or get_settings().database_url
    connect_args = kwargs.pop("connect_args", {})

    if url.startswith("sqlite"):
        # SQLite needs check_same_thread=False for multithreaded web server usage
        connect_args.setdefault("check_same_thread", False)

    engine = create_engine(url, connect_args=connect_args, **kwargs)

    if url.startswith("sqlite"):
        configure_sqlite_pragmas(engine)

    return engine


# Default application engine instance (lazy creation or initialized on demand)
_default_engine: Optional[Engine] = None
_default_session_factory: Optional[sessionmaker[Session]] = None


def get_engine() -> Engine:
    """Get or lazily instantiate default database engine."""
    global _default_engine
    if _default_engine is None:
        _default_engine = create_db_engine()
    return _default_engine


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker[Session]:
    """Get sessionmaker factory bound to the provided or default engine."""
    global _default_session_factory
    target_engine = engine or get_engine()
    if engine is not None:
        return sessionmaker(autocommit=False, autoflush=False, bind=target_engine)
    if _default_session_factory is None:
        _default_session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=target_engine
        )
    return _default_session_factory


def init_db(engine: Optional[Engine] = None) -> None:
    """Explicitly create database tables.

    Never run on module import to prevent unexpected side-effects.
    """
    target_engine = engine or get_engine()
    # Import all models to ensure they are registered with Base.metadata
    from app.models import patient, appointment, reminder  # noqa: F401

    Base.metadata.create_all(bind=target_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a managed database session."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()
