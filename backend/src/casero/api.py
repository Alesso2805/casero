from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.api import waitlist as waitlist_api
from casero.accounts.application.waitlist import (
    JoinWaitlist,
    WaitlistRateLimiter,
    WaitlistRepository,
)
from casero.accounts.infrastructure.waitlist import SqlWaitlistRepository
from casero.shared.infrastructure.database import anonymous_transaction, create_engine
from casero.shared.infrastructure.rate_limits import PostgresRateLimiter
from casero.shared.infrastructure.settings import ApiSettings
from casero.shared.kernel.clock import Clock, SystemClock

WAITLIST_JOINS_PER_HOUR = 5


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app(settings: ApiSettings | None = None, clock: Clock | None = None) -> FastAPI:
    config = settings or ApiSettings.from_environment()
    app_clock: Clock = clock or SystemClock()
    engine = create_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(
        title="Casero API",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.engine = engine

    async def provide_join_waitlist(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> JoinWaitlist:
        repository: WaitlistRepository = SqlWaitlistRepository(connection)
        limiter: WaitlistRateLimiter = PostgresRateLimiter(
            connection, config.rate_limit_key, app_clock, "waitlist", WAITLIST_JOINS_PER_HOUR
        )
        return JoinWaitlist(repository, limiter, app_clock)

    app.include_router(waitlist_api.create_router(provide_join_waitlist))

    @app.get("/api/health")
    def health() -> HealthResponse:
        """Report that the API process is up."""
        return HealthResponse(status="ok")

    return app
