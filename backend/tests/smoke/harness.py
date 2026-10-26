from uuid import UUID

import asyncpg

ACCOUNT_SCOPED_TABLES = """
SELECT table_name FROM information_schema.columns
WHERE table_schema = 'public' AND column_name = 'account_id'
ORDER BY table_name
"""


async def rows_left(owner: asyncpg.Connection, account_id: UUID) -> dict[str, int]:
    counts = {}
    for row in await owner.fetch(ACCOUNT_SCOPED_TABLES):
        table = row["table_name"]
        count = await owner.fetchval(
            f"SELECT count(*) FROM {table} WHERE account_id = $1", account_id
        )
        if count:
            counts[table] = count
    accounts = await owner.fetchval("SELECT count(*) FROM accounts WHERE id = $1", account_id)
    if accounts:
        counts["accounts"] = accounts
    return counts
