from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.kernel.data_sections import DataSection, plain_cell


async def read_section(
    connection: AsyncConnection, name: str, query: str, account_id: UUID
) -> DataSection:
    """Reads under RLS; `:account_id` is only for the tables without it (rule 3)."""
    result = await connection.execute(text(query), {"account_id": account_id})
    return DataSection(
        name,
        tuple(result.keys()),
        [tuple(plain_cell(value) for value in row) for row in result],
    )


async def read_sections(
    connection: AsyncConnection, queries: tuple[tuple[str, str], ...], account_id: UUID
) -> list[DataSection]:
    return [await read_section(connection, name, query, account_id) for name, query in queries]
