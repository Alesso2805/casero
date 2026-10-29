from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.ledger.api.payments import MAX_CENTS, WRITE_ERRORS, client_generated
from casero.ledger.application.lease_changes import ChangeRent, NewRent, RentChanged
from casero.shared.infrastructure.csrf import require_csrf


class RentChangeRequest(BaseModel):
    id: Annotated[UUID, AfterValidator(client_generated)]
    monthly_rent_cents: Annotated[int, Field(gt=0, le=MAX_CENTS)]


class RentChangeResponse(BaseModel):
    id: UUID
    lease_id: UUID
    monthly_rent_cents: int
    effective_period: str = Field(description="The first period not yet charged")


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_change_rent: Callable[..., Awaitable[ChangeRent]],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/app/leases/{lease_id}/rent-changes",
        status_code=201,
        dependencies=[Depends(require_csrf)],
        responses={
            **WRITE_ERRORS,
            200: {"description": "The same id was already recorded with the same content"},
            404: {"description": "`lease_not_found`"},
            409: {"description": "The id exists with other content or in another account"},
            422: {"description": "Invalid data or `lease_ended`"},
        },
    )
    async def change_rent(
        lease_id: UUID,
        body: RentChangeRequest,
        response: Response,
        context: Annotated[AccountContext, Depends(current_account)],
        change: Annotated[ChangeRent, Depends(provide_change_rent)],
    ) -> RentChangeResponse:
        """Change the rent from the next period not yet charged; the id comes from the client."""
        result = await change(context, NewRent(body.id, lease_id, body.monthly_rent_cents))
        if not isinstance(result, RentChanged):
            if result == "conflict":
                raise HTTPException(status_code=409)
            status = 404 if result == "lease_not_found" else 422
            raise HTTPException(status_code=status, detail=result)
        if result.replayed:
            response.status_code = 200
        record = result.change
        return RentChangeResponse(
            id=record.id,
            lease_id=record.lease_id,
            monthly_rent_cents=record.monthly_rent_cents,
            effective_period=str(record.effective_period),
        )

    return router
