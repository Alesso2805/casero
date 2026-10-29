from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.shared.kernel.periods import PERIOD_PATTERN, Period
from casero.tax.application.declarations import DueStatus, GetDeclarations


class DeclarationResponse(BaseModel):
    renter_id: UUID
    renter_name: str
    doc_type: str | None
    doc_number: str | None = Field(description="In clear only here, to copy into the 1683")
    incomplete: bool = Field(description="Without the tenant's document it cannot be filed")
    company_tenant: bool
    lease_ids: list[UUID]
    collected_cents: int
    old_debt_cents: int = Field(description="Debt from 2025 or before: outside the base")
    base_cents: int
    tax_cents: int


class UntaxedResponse(BaseModel):
    lease_id: UUID
    renter_name: str
    collected_cents: int


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


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_declarations: Callable[..., Awaitable[GetDeclarations]],
) -> APIRouter:
    router = APIRouter()

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
        )

    return router
