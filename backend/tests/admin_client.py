from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from casero.api import create_admin_app
from casero.shared.infrastructure.settings import AdminSettings
from database import Database


@contextmanager
def admin_client(database: Database) -> Iterator[TestClient]:
    url = database.dsn("casero_admin").replace("postgresql://", "postgresql+asyncpg://", 1)
    with TestClient(
        create_admin_app(AdminSettings(url)), base_url="http://localhost:8081"
    ) as client:
        yield client
