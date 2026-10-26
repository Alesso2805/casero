import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

BACKEND = Path(__file__).resolve().parents[1]
INIT_SCRIPTS = BACKEND.parent / "infra" / "postgres" / "init"
IMAGE = "postgres:17-trixie"
DATABASE_NAME = "casero"
ROLES = ("casero_owner", "casero_backup", "casero_app", "casero_worker", "casero_admin")


def password_env_name(role: str) -> str:
    return f"{role.upper()}_PASSWORD"


@dataclass(frozen=True)
class Database:
    host: str
    port: int

    def dsn(self, role: str) -> str:
        return f"postgresql://{role}:{role}_test@{self.host}:{self.port}/{DATABASE_NAME}"

    def superuser_dsn(self) -> str:
        return f"postgresql://postgres:postgres_test@{self.host}:{self.port}/{DATABASE_NAME}"


def migrate(database: Database) -> None:
    url = database.dsn("casero_owner").replace("postgresql://", "postgresql+asyncpg://", 1)
    previous = os.environ.get("CASERO_MIGRATION_DATABASE_URL")
    os.environ["CASERO_MIGRATION_DATABASE_URL"] = url
    try:
        command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    finally:
        if previous is None:
            del os.environ["CASERO_MIGRATION_DATABASE_URL"]
        else:
            os.environ["CASERO_MIGRATION_DATABASE_URL"] = previous


@contextmanager
def running_database() -> Iterator[Database]:
    container = PostgresContainer(
        IMAGE, username="postgres", password="postgres_test", dbname=DATABASE_NAME, driver=None
    )
    container.with_volume_mapping(str(INIT_SCRIPTS), "/docker-entrypoint-initdb.d", "ro")
    for role in ROLES:
        container.with_env(password_env_name(role), f"{role}_test")
    with container:
        database = Database(
            container.get_container_host_ip(), int(container.get_exposed_port(5432))
        )
        migrate(database)
        yield database


@asynccontextmanager
async def rolled_back(dsn: str, role: str | None = None) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(dsn)
    transaction = connection.transaction()
    await transaction.start()
    try:
        if role is not None:
            await connection.execute(f"SET LOCAL ROLE {role}")
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()
