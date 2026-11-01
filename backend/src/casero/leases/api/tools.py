from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.leases.application.tools import ChooseLeaseTools, GetLeaseTools, ToolsStatus
from casero.shared.infrastructure.csrf import require_csrf

MAX_CHOSEN = 100

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, unverified email, or a legal step pending"},
}


class ChooseToolsRequest(BaseModel):
    lease_ids: Annotated[list[UUID], Field(max_length=MAX_CHOSEN)]


class LeaseToolsResponse(BaseModel):
    lease_id: UUID
    tools_enabled: bool


class ToolsStatusResponse(BaseModel):
    limit: int = Field(description="Active leases the plan covers with WhatsApp and the portal")
    over_limit: bool
    leases: list[LeaseToolsResponse] = Field(description="The active leases")


def status_response(status: ToolsStatus) -> ToolsStatusResponse:
    return ToolsStatusResponse(
        limit=status.limit,
        over_limit=status.over_limit,
        leases=[
            LeaseToolsResponse(lease_id=lease.lease_id, tools_enabled=lease.enabled)
            for lease in status.leases
        ],
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_get: Callable[..., Awaitable[GetLeaseTools]],
    provide_choose: Callable[..., Awaitable[ChooseLeaseTools]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/app/lease-tools", responses=ERRORS)
    async def lease_tools(
        _: Annotated[AccountContext, Depends(current_account)],
        get_tools: Annotated[GetLeaseTools, Depends(provide_get)],
    ) -> ToolsStatusResponse:
        """Which active leases keep WhatsApp and the tenant portal."""
        return status_response(await get_tools())

    @router.put(
        "/api/app/lease-tools",
        dependencies=[Depends(require_csrf)],
        responses={
            **ERRORS,
            404: {"description": "`lease_not_found`: not an active lease of this account"},
            422: {"description": "Invalid data, or `too_many_leases` for the plan"},
        },
    )
    async def choose_lease_tools(
        body: ChooseToolsRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        choose: Annotated[ChooseLeaseTools, Depends(provide_choose)],
    ) -> ToolsStatusResponse:
        """Choose who keeps the tools while the account is over its plan's limit."""
        result = await choose(context, body.lease_ids)
        if result == "lease_not_found":
            raise HTTPException(status_code=404, detail=result)
        if result == "too_many_leases":
            raise HTTPException(status_code=422, detail=result)
        return status_response(result)

    return router
