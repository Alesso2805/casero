from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from casero.accounts.application.context import AccountContext
from casero.shared.infrastructure.csrf import require_csrf
from casero.shared.kernel.ids import client_generated
from casero.shared.kernel.periods import PERIOD_PATTERN, Period
from casero.tax.application.payments import (
    NewTaxPayment,
    RecordTaxPayment,
    TaxPaymentRecord,
    VoidTaxPayment,
)

MAX_CENTS = 10**11

PeriodText = Annotated[str, Field(pattern=f"^{PERIOD_PATTERN.pattern}$")]
OrderNumber = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{1,20}$")]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {
        "description": "No account, unverified email past its deadline, `csrf`,"
        " or `tax_module_unavailable` in the plan"
    },
}


class TaxPaymentRequest(BaseModel):
    id: Annotated[UUID, AfterValidator(client_generated)]
    period: PeriodText
    renter_id: UUID
    amount_cents: Annotated[int, Field(gt=0, le=MAX_CENTS)]
    paid_on: date
    order_number: OrderNumber = Field(description="SUNAT's número de orden, digits only")


class VoidTaxPaymentRequest(BaseModel):
    reason: Reason


class TaxPaymentResponse(BaseModel):
    id: UUID
    period: str
    renter_id: UUID
    amount_cents: int
    paid_on: date
    order_number: str
    base_cents: int = Field(description="The declaration's base when the payment was recorded")
    voided: bool


def tax_payment_response(record: TaxPaymentRecord) -> TaxPaymentResponse:
    return TaxPaymentResponse(
        id=record.id,
        period=str(record.period),
        renter_id=record.renter_id,
        amount_cents=record.amount_cents,
        paid_on=record.paid_on,
        order_number=record.order_number,
        base_cents=record.base_cents,
        voided=record.voided,
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_record: Callable[..., Awaitable[RecordTaxPayment]],
    provide_void: Callable[..., Awaitable[VoidTaxPayment]],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/app/tax/payments",
        status_code=201,
        dependencies=[Depends(require_csrf)],
        responses={
            **WRITE_ERRORS,
            200: {"description": "The same id was already recorded with the same content"},
            404: {"description": "`declaration_not_found`: nothing collected from them that month"},
            409: {"description": "The id exists with other content or in another account"},
            422: {
                "description": "Invalid data, `unknown_year`, `declaration_incomplete` (no"
                " tenant document), `paid_before_period` or `paid_in_future`"
            },
        },
    )
    async def record_tax_payment(
        body: TaxPaymentRequest,
        response: Response,
        context: Annotated[AccountContext, Depends(current_account)],
        record: Annotated[RecordTaxPayment, Depends(provide_record)],
    ) -> TaxPaymentResponse:
        """Record what the landlord paid SUNAT for one declaration; the id comes from the client."""
        new = NewTaxPayment(
            body.id,
            Period.parse(body.period),
            body.renter_id,
            body.amount_cents,
            body.paid_on,
            body.order_number,
        )
        result = await record(context, new)
        if isinstance(result, str):
            if result == "conflict":
                raise HTTPException(status_code=409)
            status = {"tax_module_unavailable": 403, "declaration_not_found": 404}.get(result, 422)
            raise HTTPException(status_code=status, detail=result)
        if result.replayed:
            response.status_code = 200
        return tax_payment_response(result.record)

    @router.post(
        "/api/app/tax/payments/{payment_id}/void",
        dependencies=[Depends(require_csrf)],
        responses={**WRITE_ERRORS, 404: {"description": "`tax_payment_not_found`"}},
    )
    async def void_tax_payment(
        payment_id: UUID,
        body: VoidTaxPaymentRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        void: Annotated[VoidTaxPayment, Depends(provide_void)],
    ) -> TaxPaymentResponse:
        """Void a SUNAT payment with a reason; voiding it again returns it unchanged."""
        result = await void(context, payment_id, body.reason)
        if result == "tax_module_unavailable":
            raise HTTPException(status_code=403, detail=result)
        if result == "tax_payment_not_found":
            raise HTTPException(status_code=404, detail=result)
        return tax_payment_response(result)

    return router
