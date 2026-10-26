from uuid import UUID

import asyncpg
import pytest

import seed
from architecture import catalog
from architecture.expected_grants import ACCOUNT_TABLES
from database import Database, rolled_back
from seed import SeededAccount

pytestmark = pytest.mark.anyio

ADMIN_TABLES = {"accounts", "subscriptions", "subscription_payments"}


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
async def seeded(database: Database) -> tuple[SeededAccount, SeededAccount]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        first = await seed.seed_account(owner, lease_count=2)
        second = await seed.seed_account(owner, lease_count=1)
    finally:
        await owner.close()
    return first, second


async def tenant_scope_leaks(
    connection: asyncpg.Connection, seeded: SeededAccount, lease_id: UUID
) -> list[str]:
    await seed.set_context(connection, seeded.account_id, "tenant", lease_id)
    return sorted(
        [
            table
            for table in ACCOUNT_TABLES
            if await seed.visible_keys(connection, table)
            != seed.expected_tenant_keys(seeded, lease_id, table)
        ]
    )


async def account_isolation_leaks(
    connection: asyncpg.Connection, seeded: SeededAccount
) -> list[str]:
    await seed.set_context(connection, seeded.account_id)
    return sorted(
        [
            table
            for table in ACCOUNT_TABLES
            if await seed.visible_keys(connection, table) != seeded.keys[table]
        ]
    )


async def tables_with_visible_rows(connection: asyncpg.Connection) -> set[str]:
    return {table for table in ACCOUNT_TABLES if await seed.visible_keys(connection, table)}


async def test_ar15_no_column_default_reads_the_clock(database: Database) -> None:
    async with rolled_back(database.dsn("casero_owner")) as owner:
        assert await catalog.clock_defaults(owner) == []


async def test_ar15_meta_detects_a_clock_default(database: Database) -> None:
    async with rolled_back(database.dsn("casero_owner")) as owner:
        await owner.execute("ALTER TABLE charges ALTER COLUMN created_at SET DEFAULT now()")

        assert await catalog.clock_defaults(owner) == ["charges.created_at DEFAULT now()"]


async def test_ar16_tenant_context_without_a_lease_sees_no_rows(
    database: Database, seeded: tuple[SeededAccount, SeededAccount]
) -> None:
    first, _ = seeded
    async with rolled_back(database.dsn("casero_app")) as app:
        await seed.set_context(app, first.account_id, "tenant")

        assert await tables_with_visible_rows(app) == set()


async def test_ar16_tenant_context_sees_only_its_lease(
    database: Database, seeded: tuple[SeededAccount, SeededAccount]
) -> None:
    first, _ = seeded
    for lease_id in first.lease_ids:
        async with rolled_back(database.dsn("casero_app")) as app:
            assert await tenant_scope_leaks(app, first, lease_id) == []


async def test_ar16_meta_detects_a_missing_tenant_policy(
    database: Database, seeded: tuple[SeededAccount, SeededAccount]
) -> None:
    first, _ = seeded
    async with rolled_back(database.superuser_dsn()) as superuser:
        await superuser.execute("DROP POLICY tenant_scope ON charges")
        await superuser.execute("SET LOCAL ROLE casero_app")

        assert await tenant_scope_leaks(superuser, first, first.lease_ids[0]) == ["charges"]


async def test_ar17_admin_sees_rows_only_where_it_has_a_policy(
    database: Database, seeded: tuple[SeededAccount, SeededAccount]
) -> None:
    async with rolled_back(database.superuser_dsn()) as superuser:
        await superuser.execute(f"GRANT SELECT ON {', '.join(ACCOUNT_TABLES)} TO casero_admin")
        await superuser.execute("SET LOCAL ROLE casero_admin")

        assert await tables_with_visible_rows(superuser) == ADMIN_TABLES


async def test_ar17_meta_detects_an_admin_policy_on_another_table(
    database: Database, seeded: tuple[SeededAccount, SeededAccount]
) -> None:
    async with rolled_back(database.superuser_dsn()) as superuser:
        await superuser.execute(f"GRANT SELECT ON {', '.join(ACCOUNT_TABLES)} TO casero_admin")
        await superuser.execute("CREATE POLICY leak ON leases TO casero_admin USING (true)")
        await superuser.execute("SET LOCAL ROLE casero_admin")

        assert await tables_with_visible_rows(superuser) == ADMIN_TABLES | {"leases"}


@pytest.mark.parametrize("role", ["casero_app", "casero_worker"])
async def test_ar18_each_account_sees_only_its_own_rows(
    database: Database, seeded: tuple[SeededAccount, SeededAccount], role: str
) -> None:
    for account in seeded:
        async with rolled_back(database.dsn(role)) as connection:
            assert await account_isolation_leaks(connection, account) == []


@pytest.mark.parametrize("role", ["casero_app", "casero_worker"])
async def test_ar18_without_an_account_no_row_is_visible(
    database: Database, seeded: tuple[SeededAccount, SeededAccount], role: str
) -> None:
    async with rolled_back(database.dsn(role)) as connection:
        await seed.set_context(connection, None)

        assert await tables_with_visible_rows(connection) == set()


async def test_ar18_meta_detects_a_table_without_rls(
    database: Database, seeded: tuple[SeededAccount, SeededAccount]
) -> None:
    _, second = seeded
    async with rolled_back(database.superuser_dsn()) as superuser:
        await superuser.execute("ALTER TABLE properties DISABLE ROW LEVEL SECURITY")
        await superuser.execute("SET LOCAL ROLE casero_app")

        assert await account_isolation_leaks(superuser, second) == ["properties"]
