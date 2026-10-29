from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.shared.infrastructure.csrf import require_csrf
from casero.tenant_portal.application.links import GetLink, IssueLink, LinkView, RevokeLink

ERRORS: dict[int | str, dict[str, str]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, unverified email past its deadline, or `csrf`"},
    404: {"description": "`lease_not_found`"},
}


class TenantLinkResponse(BaseModel):
    url: str = Field(description="Holds the token in its fragment: share it only with the tenant")
    created_at: datetime
    last_used_at: datetime | None


class TenantLinkStatus(BaseModel):
    link: TenantLinkResponse | None


def link_response(view: LinkView) -> TenantLinkResponse:
    return TenantLinkResponse(
        url=view.url, created_at=view.created_at, last_used_at=view.last_used_at
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_get: Callable[..., Awaitable[GetLink]],
    provide_issue: Callable[..., Awaitable[IssueLink]],
    provide_revoke: Callable[..., Awaitable[RevokeLink]],
) -> APIRouter:
    router = APIRouter()
    path = "/api/app/leases/{lease_id}/tenant-link"

    @router.get(path, responses=ERRORS)
    async def get_link(
        lease_id: UUID,
        _: Annotated[AccountContext, Depends(current_account)],
        get: Annotated[GetLink, Depends(provide_get)],
    ) -> TenantLinkStatus:
        """The tenant's link in use for this lease, if any."""
        result = await get(lease_id)
        if result == "lease_not_found":
            raise HTTPException(status_code=404, detail=result)
        return TenantLinkStatus(link=link_response(result) if result else None)

    @router.post(
        path,
        status_code=201,
        dependencies=[Depends(require_csrf)],
        responses={
            **ERRORS,
            403: {"description": "No account, `csrf`, or `portal_unavailable` for this lease"},
        },
    )
    async def issue_link(
        lease_id: UUID,
        context: Annotated[AccountContext, Depends(current_account)],
        issue: Annotated[IssueLink, Depends(provide_issue)],
    ) -> TenantLinkResponse:
        """Create the tenant's link, or replace it so the previous one stops working."""
        result = await issue(context, lease_id)
        if result == "lease_not_found":
            raise HTTPException(status_code=404, detail=result)
        if result == "portal_unavailable":
            raise HTTPException(status_code=403, detail=result)
        return link_response(result)

    @router.post(f"{path}/revoke", dependencies=[Depends(require_csrf)], responses=ERRORS)
    async def revoke_link(
        lease_id: UUID,
        context: Annotated[AccountContext, Depends(current_account)],
        revoke: Annotated[RevokeLink, Depends(provide_revoke)],
    ) -> TenantLinkStatus:
        """Stop the tenant's link from working; doing it again changes nothing."""
        if await revoke(context, lease_id) == "lease_not_found":
            raise HTTPException(status_code=404, detail="lease_not_found")
        return TenantLinkStatus(link=None)

    return router
