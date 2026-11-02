from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from api_client import TEST_FIELD_CIPHER
from casero.api import create_admin_app
from casero.shared.infrastructure.settings import AdminSettings
from casero.shared.kernel.clock import Clock
from database import Database


@contextmanager
def admin_client(database: Database, clock: Clock | None = None) -> Iterator[TestClient]:
    url = database.dsn("casero_admin").replace("postgresql://", "postgresql+asyncpg://", 1)
    app = create_admin_app(AdminSettings(url, TEST_FIELD_CIPHER), clock)
    with TestClient(app, base_url="https://localhost:8081") as client:
        yield client
