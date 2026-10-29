from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from casero.ledger.application.payments import ChargeKind, ChargeStatus
from casero.tenant_portal.application.portal import (
    GetTenantStatement,
    PortalRefusal,
    TenantLease,
)

TenantAccess = TenantLease | PortalRefusal | Literal["too_many_requests"]
REFUSAL_STATUS = {"link_not_found": 404, "portal_unavailable": 403, "too_many_requests": 429}


class TenantChargeResponse(BaseModel):
    kind: ChargeKind
    period: str | None
    pre_2026: bool | None
    amount_cents: int
    due_date: date
    outstanding_cents: int
    status: ChargeStatus | None
    partial: bool
    voided: bool


class TenantPaymentResponse(BaseModel):
    amount_cents: int
    received_on: date
    method: str
    voided: bool


class TenantStatementResponse(BaseModel):
    """An explicit DTO: never the landlord's RUC, email or notes (CS-18)."""

    landlord_name: str
    renter_name: str
    unit: str
    balance_cents: int
    credit_cents: int
    up_to_date: bool
    charges: list[TenantChargeResponse]
    payments: list[TenantPaymentResponse]


def create_router(
    provide_access: Callable[..., Awaitable[TenantAccess]],
    provide_statement: Callable[..., Awaitable[GetTenantStatement]],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/tenant/statement",
        response_model=TenantStatementResponse,
        responses={
            403: {"description": "`portal_unavailable`: the plan or the lease lost the portal"},
            404: {"description": "`link_not_found`: unknown, revoked or expired link"},
            429: {"description": "`too_many_requests` from this client"},
        },
    )
    async def statement(
        access: Annotated[TenantAccess, Depends(provide_access)],
        get_statement: Annotated[GetTenantStatement, Depends(provide_statement)],
    ) -> TenantStatementResponse | JSONResponse:
        """The tenant's balance and history, with the token in the X-Tenant-Token header."""
        # Refusals are returned, not raised, so the transaction commits the rate-limit hit.
        if isinstance(access, str):
            return JSONResponse(status_code=REFUSAL_STATUS[access], content={"detail": access})
        result = await get_statement(access)
        if result is None:
            return JSONResponse(status_code=404, content={"detail": "link_not_found"})
        statement = result.statement
        return TenantStatementResponse(
            landlord_name=result.header.landlord_name,
            renter_name=result.header.renter_name,
            unit=result.header.unit,
            balance_cents=statement.balance_cents,
            credit_cents=statement.credit_cents,
            up_to_date=statement.up_to_date,
            charges=[
                TenantChargeResponse(
                    kind=line.charge.kind,
                    period=str(line.charge.period) if line.charge.period else None,
                    pre_2026=line.charge.pre_2026,
                    amount_cents=line.charge.amount_cents,
                    due_date=line.charge.due_date,
                    outstanding_cents=line.outstanding_cents,
                    status=line.status,
                    partial=line.partial,
                    voided=line.charge.voided,
                )
                for line in statement.charges
            ],
            payments=[
                TenantPaymentResponse(
                    amount_cents=record.payment.amount_cents,
                    received_on=record.payment.received_on,
                    method=record.method,
                    voided=record.payment.voided,
                )
                for record in statement.payments
            ],
        )

    return router
