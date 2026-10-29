from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.leases.application.renters import DocType
from casero.shared.kernel.periods import PERIOD_PATTERN, Period
from casero.tax.application.declarations import ChangeKind, DueStatus, GetDeclarations
from casero.tax.application.upcoming import GetUpcomingDue


class DeclaredPaymentResponse(BaseModel):
    id: UUID
    amount_cents: int
    paid_on: date
    order_number: str


class AfterDeclaringResponse(BaseModel):
    kind: ChangeKind = Field(
        description="`up`/`down`: the base changed after paying; `document_changed`: paid with"
        " another tenant document; `overdue_unpaid`: past due with no payment recorded"
    )
    base_difference_cents: int
    tax_difference_cents: int


class DeclarationResponse(BaseModel):
    renter_id: UUID
    renter_name: str
    doc_type: DocType | None
    doc_number: str | None = Field(description="In clear only here, to copy into the 1683")
    incomplete: bool = Field(description="Without the tenant's document it cannot be filed")
    company_tenant: bool
    lease_ids: list[UUID]
    collected_cents: int
    old_debt_cents: int = Field(description="Debt from 2025 or before: outside the base")
    base_cents: int
    tax_cents: int
    payments: list[DeclaredPaymentResponse]
    paid_cents: int
    pending_cents: int
    after_declaring: AfterDeclaringResponse | None


class UntaxedResponse(BaseModel):
    lease_id: UUID
    renter_name: str
    collected_cents: int


class MinimumRentResponse(BaseModel):
    property_id: UUID
    property_name: str


class MonthDeclarationsResponse(BaseModel):
    period: str
    ruc: str | None
    due_on: date | None
    due_status: DueStatus = Field(
        description="`no_ruc` without a RUC; `unknown_schedule` until the year is loaded"
    )
    total_tax_cents: int
    declarations: list[DeclarationResponse]
    untaxed: list[UntaxedResponse]
    minimum_rent: list[MinimumRentResponse] = Field(
        description="Properties whose rent this year is under the autovalúo's minimum"
    )


class UpcomingDueResponse(BaseModel):
    period: str
    due_on: date
    days_left: int
    pending_cents: int
    declarations: int


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_declarations: Callable[..., Awaitable[GetDeclarations]],
    provide_upcoming: Callable[..., Awaitable[GetUpcomingDue]],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/app/tax/upcoming",
        responses={
            401: {"description": "No valid session"},
            403: {"description": "No account, or `tax_module_unavailable` in the plan"},
        },
    )
    async def upcoming_due(
        _: Annotated[AccountContext, Depends(current_account)],
        get: Annotated[GetUpcomingDue, Depends(provide_upcoming)],
    ) -> UpcomingDueResponse | None:
        """What is still owed to SUNAT when a due date is 5 days away or less; null otherwise."""
        result = await get()
        if result == "tax_module_unavailable":
            raise HTTPException(status_code=403, detail=result)
        if result is None:
            return None
        return UpcomingDueResponse(
            period=str(result.period),
            due_on=result.due_on,
            days_left=result.days_left,
            pending_cents=result.pending_cents,
            declarations=result.declarations,
        )

    @router.get(
        "/api/app/tax/declarations",
        responses={
            401: {"description": "No valid session"},
            403: {"description": "No account, or `tax_module_unavailable` in the plan"},
            422: {"description": "Invalid period, or `unknown_year` without its tax rules"},
        },
    )
    async def month_declarations(
        period: Annotated[str, Query(pattern=f"^{PERIOD_PATTERN.pattern}$")],
        _: Annotated[AccountContext, Depends(current_account)],
        get: Annotated[GetDeclarations, Depends(provide_declarations)],
    ) -> MonthDeclarationsResponse:
        """The month's Formulario 1683 declarations: one per tenant document."""
        result = await get(Period.parse(period))
        if result == "tax_module_unavailable":
            raise HTTPException(status_code=403, detail=result)
        if result == "unknown_year":
            raise HTTPException(status_code=422, detail=result)
        return MonthDeclarationsResponse(
            period=str(result.period),
            ruc=result.ruc,
            due_on=result.due_on,
            due_status=result.due_status,
            total_tax_cents=result.total_tax_cents,
            declarations=[
                DeclarationResponse(
                    renter_id=c.declaration.declarant.renter_id,
                    renter_name=c.renter_name,
                    doc_type=c.doc_type,
                    doc_number=c.doc_number,
                    incomplete=c.declaration.incomplete,
                    company_tenant=c.company_tenant,
                    lease_ids=list(c.declaration.lease_ids),
                    collected_cents=c.declaration.collected_cents,
                    old_debt_cents=c.declaration.old_debt_cents,
                    base_cents=c.declaration.base_cents,
                    tax_cents=c.declaration.tax_cents,
                    payments=[
                        DeclaredPaymentResponse(
                            id=p.id,
                            amount_cents=p.amount_cents,
                            paid_on=p.paid_on,
                            order_number=p.order_number,
                        )
                        for p in c.payments
                    ],
                    paid_cents=c.paid_cents,
                    pending_cents=c.pending_cents,
                    after_declaring=None
                    if c.after is None
                    else AfterDeclaringResponse(
                        kind=c.after.kind,
                        base_difference_cents=c.after.base_difference_cents,
                        tax_difference_cents=c.after.tax_difference_cents,
                    ),
                )
                for c in result.cards
            ],
            untaxed=[
                UntaxedResponse(
                    lease_id=u.lease_id,
                    renter_name=u.renter_name,
                    collected_cents=u.collected_cents,
                )
                for u in result.untaxed
            ],
            minimum_rent=[
                MinimumRentResponse(property_id=m.property_id, property_name=m.property_name)
                for m in result.minimum_rent
            ],
        )

    return router
