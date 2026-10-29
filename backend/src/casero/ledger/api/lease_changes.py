from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.ledger.api.leases import LeaseResponse, lease_response
from casero.ledger.api.payments import MAX_CENTS, WRITE_ERRORS, client_generated
from casero.ledger.application.lease_changes import (
    ChangeRent,
    EndingCredit,
    EndLease,
    NewRent,
    RentChanged,
    SetEndDate,
)
from casero.shared.infrastructure.csrf import require_csrf


class RentChangeRequest(BaseModel):
    id: Annotated[UUID, AfterValidator(client_generated)]
    monthly_rent_cents: Annotated[int, Field(gt=0, le=MAX_CENTS)]


class RentChangeResponse(BaseModel):
    id: UUID
    lease_id: UUID
    monthly_rent_cents: int
    effective_period: str = Field(description="The first period not yet charged")


class EndDateRequest(BaseModel):
    end_date: date | None = Field(description="The new planned end; null leaves it open")


class CreditRequest(BaseModel):
    id: Annotated[UUID, AfterValidator(client_generated)]
    amount_cents: Annotated[
        int, Field(gt=0, le=MAX_CENTS, description="Recorded as a credit (negative adjustment)")
    ]


class TerminationRequest(BaseModel):
    ended_on: date
    credit: CreditRequest | None = None


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_change_rent: Callable[..., Awaitable[ChangeRent]],
    provide_set_end_date: Callable[..., Awaitable[SetEndDate]],
    provide_end_lease: Callable[..., Awaitable[EndLease]],
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

    @router.post(
        "/api/app/leases/{lease_id}/end-date",
        dependencies=[Depends(require_csrf)],
        responses={
            **WRITE_ERRORS,
            404: {"description": "`lease_not_found`"},
            422: {
                "description": "Invalid data, `lease_ended`, `end_in_past` or `end_before_start`"
            },
        },
    )
    async def set_end_date(
        lease_id: UUID,
        body: EndDateRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        set_end: Annotated[SetEndDate, Depends(provide_set_end_date)],
    ) -> LeaseResponse:
        """Renew: extend, move or remove the planned end of an active lease."""
        result = await set_end(context, lease_id, body.end_date)
        if isinstance(result, str):
            status = 404 if result == "lease_not_found" else 422
            raise HTTPException(status_code=status, detail=result)
        return lease_response(result)

    @router.post(
        "/api/app/leases/{lease_id}/termination",
        dependencies=[Depends(require_csrf)],
        responses={
            **WRITE_ERRORS,
            404: {"description": "`lease_not_found`"},
            409: {"description": "The credit's id exists with other content or elsewhere"},
            422: {
                "description": "Invalid data, `lease_ended`, `end_in_future`, `end_before_start`"
                " or `end_before_control`"
            },
        },
    )
    async def end_lease(
        lease_id: UUID,
        body: TerminationRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        end: Annotated[EndLease, Depends(provide_end_lease)],
    ) -> LeaseResponse:
        """End a lease on a date up to today, voiding the rents of later periods."""
        credit = EndingCredit(body.credit.id, body.credit.amount_cents) if body.credit else None
        result = await end(context, lease_id, body.ended_on, credit)
        if isinstance(result, str):
            if result == "conflict":
                raise HTTPException(status_code=409)
            status = 404 if result == "lease_not_found" else 422
            raise HTTPException(status_code=status, detail=result)
        return lease_response(result)

    return router
