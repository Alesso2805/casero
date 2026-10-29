from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Protocol

import sentry_sdk
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, StringConstraints

ErrorName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.$ -]+$"
    ),
]
# Paths and stack locations only: a query string or fragment could carry a token (rule 10).
RoutePath = Annotated[str, StringConstraints(max_length=200, pattern=r"^/[^?#\s]*$")]
CodeLocation = Annotated[str, StringConstraints(max_length=300, pattern=r"^[^?#\s]*$")]


class RateLimiter(Protocol):
    async def allow(self, client: str) -> bool: ...


@dataclass(frozen=True)
class ReportLimits:
    per_client: RateLimiter
    per_kind: RateLimiter
    overall: RateLimiter


class ClientError(BaseModel):
    name: ErrorName
    route: RoutePath
    where: CodeLocation | None = None


def create_router(provide_limits: Callable[..., Awaitable[ReportLimits]]) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/public/client-errors",
        status_code=204,
        responses={429: {"description": "Too many reports from this client"}},
    )
    async def report_client_error(
        body: ClientError,
        request: Request,
        limits: Annotated[ReportLimits, Depends(provide_limits)],
    ) -> Response:
        """Report a browser error by its type, route and code location (ADR-0011)."""
        client = request.client.host if request.client else "unknown"
        if not await limits.per_client.allow(client):
            return Response(status_code=429)
        # One visitor could use up Sentry's monthly quota: only the first report of each kind
        # in an hour, and a few per hour overall, are forwarded. The answer doesn't say which.
        forward = await limits.per_kind.allow(f"{body.name}|{body.route}")
        if forward and await limits.overall.allow("all") and sentry_sdk.is_initialized():
            sentry_sdk.capture_message(
                "web.unhandled_error",
                level="error",
                tags={"error": body.name, "route": body.route, "where": body.where or ""},
            )
        return Response(status_code=204)

    return router
