from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.ledger.api.payments import MAX_CENTS, WRITE_ERRORS, VoidRequest, client_generated
from casero.ledger.application.manual_charges import (
    ChargeRecord,
    Corrected,
    CorrectRent,
    NewCorrection,
    VoidCharge,
)
from casero.ledger.domain.allocation import ChargeKind
from casero.shared.infrastructure.csrf import require_csrf


class CorrectionRequest(BaseModel):
    id: Annotated[UUID, AfterValidator(client_generated)]
    corrects_charge_id: UUID
    amount_cents: Annotated[int, Field(gt=0, le=MAX_CENTS)]


class ChargeResponse(BaseModel):
    id: UUID
    lease_id: UUID
    kind: ChargeKind
    period: str | None
    amount_cents: int
    due_date: date
    corrects_charge_id: UUID | None
    voided: bool


def charge_response(record: ChargeRecord) -> ChargeResponse:
    charge = record.charge
    return ChargeResponse(
        id=charge.id,
        lease_id=record.lease_id,
        kind=charge.kind,
        period=str(charge.period) if charge.period else None,
        amount_cents=charge.amount_cents,
        due_date=charge.due_date,
        corrects_charge_id=record.corrects_charge_id,
        voided=charge.voided,
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_correct: Callable[..., Awaitable[CorrectRent]],
    provide_void: Callable[..., Awaitable[VoidCharge]],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/app/leases/{lease_id}/charges/corrections",
        status_code=201,
        dependencies=[Depends(require_csrf)],
        responses={
            **WRITE_ERRORS,
            200: {"description": "The same id was already recorded with the same content"},
            404: {"description": "`lease_not_found`"},
            409: {"description": "The id exists with other content or in another account"},
            422: {"description": "Invalid data, `not_a_voided_rent` or `already_corrected`"},
        },
    )
    async def correct_rent(
        lease_id: UUID,
        body: CorrectionRequest,
        response: Response,
        context: Annotated[AccountContext, Depends(current_account)],
        correct: Annotated[CorrectRent, Depends(provide_correct)],
    ) -> ChargeResponse:
        """Replace a voided rent with its corrected amount; the id comes from the client."""
        result = await correct(
            context,
            NewCorrection(body.id, lease_id, body.corrects_charge_id, body.amount_cents),
        )
        if not isinstance(result, Corrected):
            if result == "conflict":
                raise HTTPException(status_code=409)
            status = 404 if result == "lease_not_found" else 422
            raise HTTPException(status_code=status, detail=result)
        if result.replayed:
            response.status_code = 200
        return charge_response(result.record)

    @router.post(
        "/api/app/charges/{charge_id}/void",
        dependencies=[Depends(require_csrf)],
        responses={
            **WRITE_ERRORS,
            404: {"description": "`charge_not_found`"},
            422: {"description": "Invalid data or `charge_not_voidable` (a prior debt)"},
        },
    )
    async def void_charge(
        charge_id: UUID,
        body: VoidRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        void: Annotated[VoidCharge, Depends(provide_void)],
    ) -> ChargeResponse:
        """Void a charge with a reason; voiding it again returns it unchanged."""
        result = await void(context, charge_id, body.reason)
        if result == "charge_not_found":
            raise HTTPException(status_code=404, detail=result)
        if result == "charge_not_voidable":
            raise HTTPException(status_code=422, detail=result)
        return charge_response(result)

    return router
