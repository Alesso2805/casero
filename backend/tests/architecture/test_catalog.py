from collections.abc import AsyncIterator

import asyncpg
import pytest

from architecture import catalog
from architecture.expected_grants import COLUMN_PRIVILEGES, TABLE_PRIVILEGES, TABLES_WITHOUT_RLS
from database import Database

pytestmark = pytest.mark.anyio


@pytest.fixture
async def owner(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.dsn(catalog.OWNER))
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.fixture
async def superuser(database: Database) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database.superuser_dsn())
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


async def privilege_differences(connection: asyncpg.Connection) -> list[str]:
    return catalog.privilege_differences(
        await catalog.table_privileges(connection),
        await catalog.column_privileges(connection),
        [table.name for table in await catalog.tables(connection)],
        TABLE_PRIVILEGES,
        COLUMN_PRIVILEGES,
    )


async def test_ar13_only_the_closed_list_skips_forced_rls(owner: asyncpg.Connection) -> None:
    tables = await catalog.tables(owner)

    assert catalog.tables_without_forced_rls(tables, TABLES_WITHOUT_RLS) == []


async def test_ar13_meta_detects_a_table_without_forced_rls(owner: asyncpg.Connection) -> None:
    await owner.execute("CREATE TABLE stray (id uuid PRIMARY KEY)")

    tables = await catalog.tables(owner)

    assert catalog.tables_without_forced_rls(tables, TABLES_WITHOUT_RLS) == ["stray"]


async def test_ar14_roles_have_exactly_the_listed_privileges(owner: asyncpg.Connection) -> None:
    assert await privilege_differences(owner) == []


async def test_ar14_meta_detects_unlisted_privileges(owner: asyncpg.Connection) -> None:
    await owner.execute("GRANT UPDATE ON plans TO casero_app")
    await owner.execute("GRANT SELECT (password_hash) ON users TO casero_admin")

    assert await privilege_differences(owner) == [
        "casero_app: unexpected UPDATE on plans",
        "casero_admin: unexpected SELECT(password_hash) on users",
    ]


async def test_ar14_meta_detects_missing_privileges(owner: asyncpg.Connection) -> None:
    await owner.execute("REVOKE SELECT ON plans FROM casero_app")
    await owner.execute("REVOKE SELECT ON plans FROM casero_backup")

    assert await privilege_differences(owner) == [
        "casero_app: missing SELECT on plans",
        "casero_backup: has [] on plans, expected SELECT only",
    ]


async def test_ar14_roles_and_ownership_follow_the_roles_table(
    owner: asyncpg.Connection,
) -> None:
    problems = catalog.ownership_and_role_problems(
        await catalog.tables(owner), await catalog.roles(owner)
    )

    assert problems == []


async def test_ar14_meta_detects_an_application_role_bypassing_rls(
    superuser: asyncpg.Connection,
) -> None:
    await superuser.execute("ALTER ROLE casero_app BYPASSRLS")
    await superuser.execute("ALTER TABLE plans OWNER TO casero_admin")

    problems = catalog.ownership_and_role_problems(
        await catalog.tables(superuser), await catalog.roles(superuser)
    )

    assert problems == ["casero_app has BYPASSRLS=True", "plans is owned by casero_admin"]
