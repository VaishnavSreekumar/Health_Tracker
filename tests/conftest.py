"""Pytest fixtures for HealthTrack test suite."""

from collections.abc import Generator
import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from pathlib import Path
import app.db.session as session_module
from app.db.base import Base
from app.db.session import configure_sqlite_pragmas, get_db
from app.main import create_app
from app.models import patient, appointment, reminder  # noqa: F401


@pytest.fixture(scope="session", autouse=True)
def isolate_test_database_environment() -> Generator[None, None]:
    """Ensure session module cached engines and factories do not hold handles or contaminate tests."""
    # Ensure cached engines in session module do not hold file handles
    session_module._default_engine = None
    session_module._default_session_factory = None

    try:
        yield
    finally:
        # Cleanup any database engine references
        session_module._default_engine = None
        session_module._default_session_factory = None


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    """Provide a session-scoped in-memory SQLite engine with foreign keys enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    configure_sqlite_pragmas(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Generator[Session, None, None]:
    """Provide a clean, isolated database session per test.

    Tables are created fresh before each test and dropped afterwards, ensuring
    total isolation without lingering side effects.
    """
    Base.metadata.create_all(bind=test_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(test_engine: Engine, db_session: Session) -> Generator[TestClient, None, None]:
    """Provide an HTTP test client connected to the isolated test database."""
    test_app = create_app(engine=test_engine, init_database=False)

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = _override_get_db

    with TestClient(test_app) as test_client:
        yield test_client

    test_app.dependency_overrides.clear()
