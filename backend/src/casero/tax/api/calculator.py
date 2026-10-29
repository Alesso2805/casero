from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from casero.shared.kernel.periods import PERIOD_PATTERN, Period
from casero.tax.application.calculator import CalculateTax
from casero.tax.domain.rules import RucGroup

MAX_LINES = 20
MAX_COLLECTED_CENTS = 10**11

PeriodText = Annotated[str, Field(pattern=f"^{PERIOD_PATTERN.pattern}$")]
Collected = Annotated[int, Field(ge=0, le=MAX_COLLECTED_CENTS)]


class CalculatorRequest(BaseModel):
    period: PeriodText
    collected_cents: Annotated[list[Collected], Field(min_length=1, max_length=MAX_LINES)]
    ruc_group: RucGroup | None = None


class CalculatorLine(BaseModel):
    collected_cents: int
    base_cents: int
    tax_cents: int


class CalculatorResponse(BaseModel):
    period: str
    rate_bp: int
    deduction_bp: int
    lines: list[CalculatorLine]
    total_tax_cents: int
    due_on: date | None


def create_router(provide_calculate: Callable[..., Awaitable[CalculateTax]]) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/public/tax-calculator",
        response_model=CalculatorResponse,
        responses={
            404: {"description": "The rules of that year are not loaded"},
            429: {"description": "Too many requests from this client"},
        },
    )
    async def calculate(
        body: CalculatorRequest,
        request: Request,
        calculate: Annotated[CalculateTax, Depends(provide_calculate)],
    ) -> CalculatorResponse | Response:
        """Estimate each renter's monthly SUNAT payment; amounts are not stored."""
        client = request.client.host if request.client else "unknown"
        outcome = await calculate(
            Period.parse(body.period), body.collected_cents, body.ruc_group, client
        )
        if outcome == "limited":
            return Response(status_code=429)
        if outcome == "unknown_year":
            return Response(status_code=404)
        return CalculatorResponse(
            period=str(outcome.period),
            rate_bp=outcome.rules.rate_bp,
            deduction_bp=outcome.rules.deduction_bp,
            lines=[
                CalculatorLine(
                    collected_cents=line.collected_cents,
                    base_cents=line.base_cents,
                    tax_cents=line.tax_cents,
                )
                for line in outcome.lines
            ],
            total_tax_cents=outcome.total_tax_cents,
            due_on=outcome.due_on,
        )

    return router
