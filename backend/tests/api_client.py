import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime

from fastapi.testclient import TestClient

from casero.api import create_app
from casero.shared.infrastructure.settings import ApiSettings
from casero.shared.kernel.clock import LIMA, Clock
from database import Database


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def today_lima(self) -> date:
        return self._now.astimezone(LIMA).date()


def address_for(name: str) -> str:
    return f"198.51.100.{zlib.crc32(name.encode()) % 250 + 1}"


@contextmanager
def api_client(
    database: Database, address: str, clock: Clock | None = None
) -> Iterator[TestClient]:
    url = database.dsn("casero_app").replace("postgresql://", "postgresql+asyncpg://", 1)
    app = create_app(ApiSettings(database_url=url, rate_limit_key=b"test-key"), clock)
    with TestClient(app, client=(address, 50000)) as client:
        yield client
