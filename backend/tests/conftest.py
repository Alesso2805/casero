from collections.abc import Iterator

import pytest

from database import Database, running_database


@pytest.fixture(scope="session")
def database() -> Iterator[Database]:
    with running_database() as running:
        yield running


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
