from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from casero.accounts.application.context import AccountContext
from casero.ledger.application.payments import (
    GetStatement,
    NewPayment,
    PaymentRecord,
    Recorded,
    RecordPayment,
    VoidPayment,
)
from casero.ledger.domain.allocation import ChargeKind, ChargeStatus
from casero.ledger.domain.payments import PaymentMethod
from casero.shared.infrastructure.csrf import require_csrf

MAX_CENTS = 10**11
UUID_V7 = 7

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, or the email is unverified past its deadline"},
}
WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **READ_ERRORS,
    403: {"description": "No account, unverified email past its deadline, or `csrf`"},
}


def client_generated(value: UUID) -> UUID:
    if value.version != UUID_V7:
        raise ValueError("the id must be a uuid v7 generated when the form opens")
    return value


class PaymentRequest(BaseModel):
    id: Annotated[UUID, AfterValidator(client_generated)]
    amount_cents: Annotated[int, Field(gt=0, le=MAX_CENTS)]
    received_on: date
    method: PaymentMethod
    note: Note | None = None


class VoidRequest(BaseModel):
    reason: Note


class PaymentResponse(BaseModel):
    id: UUID
    lease_id: UUID
    amount_cents: int
    received_on: date
    method: str
    note: str | None
    voided: bool


class RecordedResponse(PaymentResponse):
    bank_threshold_cents: int | None = Field(
        description="Set when a cash payment's rent reaches the year's bancarization threshold"
    )
    before_control: bool = Field(
        description="Collected before the lease's control month, for example at signing"
    )


class ChargeLineResponse(BaseModel):
    id: UUID
    kind: ChargeKind
    period: str | None
    pre_2026: bool | None = Field(description="Set on prior debt: from 2025 or before, or not")
    corrects_charge_id: UUID | None = Field(description="The voided rent this one replaces")
    amount_cents: int
    due_date: date
    outstanding_cents: int
    status: ChargeStatus | None = Field(description="None for voided charges and credits")
    partial: bool
    voided: bool


class StatementResponse(BaseModel):
    lease_id: UUID
    balance_cents: int
    credit_cents: int = Field(description="Money received beyond what is owed, in favor")
    up_to_date: bool
    charges: list[ChargeLineResponse]
    payments: list[PaymentResponse]


def payment_response(record: PaymentRecord) -> PaymentResponse:
    payment = record.payment
    return PaymentResponse(
        id=payment.id,
        lease_id=record.lease_id,
        amount_cents=payment.amount_cents,
        received_on=payment.received_on,
        method=record.method,
        note=record.note,
        voided=payment.voided,
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_record: Callable[..., Awaitable[RecordPayment]],
    provide_void: Callable[..., Awaitable[VoidPayment]],
    provide_statement: Callable[..., Awaitable[GetStatement]],
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/app/leases/{lease_id}/payments",
        status_code=201,
        dependencies=[Depends(require_csrf)],
        responses={
            **WRITE_ERRORS,
            200: {"description": "The same id was already recorded with the same content"},
            404: {"description": "`lease_not_found`"},
            409: {"description": "The id exists with other content or in another account"},
            422: {"description": "Invalid data, `received_in_future` or `received_before_2026`"},
        },
    )
    async def record_payment(
        lease_id: UUID,
        body: PaymentRequest,
        response: Response,
        context: Annotated[AccountContext, Depends(current_account)],
        record: Annotated[RecordPayment, Depends(provide_record)],
    ) -> RecordedResponse:
        """Record money the landlord received; the id comes from the client (rule 5)."""
        new = NewPayment(
            body.id, lease_id, body.amount_cents, body.received_on, body.method, body.note
        )
        result = await record(context, new)
        if not isinstance(result, Recorded):
            if result == "conflict":
                raise HTTPException(status_code=409)
            status = 404 if result == "lease_not_found" else 422
            raise HTTPException(status_code=status, detail=result)
        if result.replayed:
            response.status_code = 200
        return RecordedResponse(
            **payment_response(result.record).model_dump(),
            bank_threshold_cents=result.bank_threshold_cents,
            before_control=result.before_control,
        )

    @router.post(
        "/api/app/payments/{payment_id}/void",
        dependencies=[Depends(require_csrf)],
        responses={**WRITE_ERRORS, 404: {"description": "`payment_not_found`"}},
    )
    async def void_payment(
        payment_id: UUID,
        body: VoidRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        void: Annotated[VoidPayment, Depends(provide_void)],
    ) -> PaymentResponse:
        """Void a payment with a reason; voiding it again returns it unchanged."""
        result = await void(context, payment_id, body.reason)
        if result == "payment_not_found":
            raise HTTPException(status_code=404, detail=result)
        return payment_response(result)

    @router.get(
        "/api/app/leases/{lease_id}/statement",
        responses={**READ_ERRORS, 404: {"description": "`lease_not_found`"}},
    )
    async def statement(
        lease_id: UUID,
        _: Annotated[AccountContext, Depends(current_account)],
        get_statement: Annotated[GetStatement, Depends(provide_statement)],
    ) -> StatementResponse:
        """The lease's charges with their status, its payments and its balance."""
        result = await get_statement(lease_id)
        if result is None:
            raise HTTPException(status_code=404, detail="lease_not_found")
        return StatementResponse(
            lease_id=result.lease_id,
            balance_cents=result.balance_cents,
            credit_cents=result.credit_cents,
            up_to_date=result.up_to_date,
            charges=[
                ChargeLineResponse(
                    id=line.charge.id,
                    kind=line.charge.kind,
                    period=str(line.charge.period) if line.charge.period else None,
                    pre_2026=line.charge.pre_2026,
                    corrects_charge_id=line.charge.corrects_charge_id,
                    amount_cents=line.charge.amount_cents,
                    due_date=line.charge.due_date,
                    outstanding_cents=line.outstanding_cents,
                    status=line.status,
                    partial=line.partial,
                    voided=line.charge.voided,
                )
                for line in result.charges
            ],
            payments=[payment_response(record) for record in result.payments],
        )

    return router
