import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

SET_ACCOUNT = text("SELECT set_config('app.account_id', :account_id, true)")
HEALTH_TIMEOUT_SECONDS = 3


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url, pool_size=5, max_overflow=5, pool_pre_ping=True, hide_parameters=True
    )


async def anonymous_transaction(request: Request) -> AsyncIterator[AsyncConnection]:
    engine: AsyncEngine = request.app.state.engine
    async with engine.begin() as connection:
        yield connection


# FastAPI's default "request" scope commits after the response is sent; "function" commits
# before it, so a 2xx means the write is durable. Every use must share this one scope, or a
# request would open a second transaction without app.account_id.
Transaction = Annotated[AsyncConnection, Depends(anonymous_transaction, scope="function")]


async def set_account_context(connection: AsyncConnection, account_id: UUID) -> None:
    """Scope row-level security to one account until the transaction ends (AR-12)."""
    await connection.execute(SET_ACCOUNT, {"account_id": str(account_id)})


async def database_answers(engine: AsyncEngine) -> bool:
    try:
        async with asyncio.timeout(HEALTH_TIMEOUT_SECONDS), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except OSError, SQLAlchemyError, TimeoutError:
        return False
    return True


SET_TENANT = text(
    "SELECT set_config('app.account_id', :account_id, true),"
    " set_config('app.context', 'tenant', true), set_config('app.lease_id', :lease_id, true)"
)


async def set_tenant_context(connection: AsyncConnection, account_id: UUID, lease_id: UUID) -> None:
    """One statement scopes RLS to the tenant's lease until the transaction ends (rule 3)."""
    await connection.execute(SET_TENANT, {"account_id": str(account_id), "lease_id": str(lease_id)})
