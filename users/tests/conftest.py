"""
conftest.py — users-service test configuration.

Environment variables MUST be set before any app module is imported,
so this file is the single place where all test config lives.
SQLite is used as a drop-in replacement for PostgreSQL during tests.
"""
import os
import sys

# ---------------------------------------------------------------------------
# Patch environment BEFORE any app module is imported
# ---------------------------------------------------------------------------
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DB_FILE = os.path.join(_TESTS_DIR, "test_users.db")

os.environ.setdefault("DB_URL", f"sqlite:///{_DB_FILE}")
os.environ.setdefault("KEYCLOAK_URL", "http://localhost:8080")
os.environ.setdefault("KEYCLOAK_REALM", "cc2526")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test-client")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test-secret")

# Add users/ directory to path so imports work
sys.path.insert(0, os.path.dirname(_TESTS_DIR))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from config import Base, get_db
from users import app  # noqa: E402 — must be after env vars

_engine = create_engine(
    f"sqlite:///{_DB_FILE}",
    connect_args={"check_same_thread": False},
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Create all tables once for the test session."""
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)
    if os.path.exists(_DB_FILE):
        os.remove(_DB_FILE)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate all tables before each test for isolation."""
    yield
    with _engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db():
    """Yield a database session."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    """Yield a FastAPI TestClient backed by the SQLite test database."""
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
