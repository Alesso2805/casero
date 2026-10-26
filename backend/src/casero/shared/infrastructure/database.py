from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

SET_ACCOUNT = text("SELECT set_config('app.account_id', :account_id, true)")


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_size=5, max_overflow=5, pool_pre_ping=True)


async def anonymous_transaction(request: Request) -> AsyncIterator[AsyncConnection]:
    engine: AsyncEngine = request.app.state.engine
    async with engine.begin() as connection:
        yield connection


async def set_account_context(connection: AsyncConnection, account_id: UUID) -> None:
    """Scope row-level security to one account until the transaction ends (AR-12)."""
    await connection.execute(SET_ACCOUNT, {"account_id": str(account_id)})
