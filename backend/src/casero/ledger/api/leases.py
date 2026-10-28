from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from casero.accounts.application.context import AccountContext
from casero.leases.application.leases import (
    LeaseTerms,
    LeaseView,
    ListLeases,
    OpeningBalances,
    TaxTreatment,
)
from casero.ledger.application.leases import Created, CreateLease, NewLease
from casero.shared.infrastructure.csrf import require_csrf
from casero.shared.kernel.periods import Period

MAX_CENTS = 10**11
UUID_V7 = 7

PeriodText = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]
Cents = Annotated[int, Field(gt=0, le=MAX_CENTS)]

STATUS = {
    "conflict": 409,
    "plan_limit": 409,
    "unit_archived": 409,
    "unit_occupied": 409,
    "unit_not_found": 404,
    "renter_not_found": 404,
}
READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, or the email is unverified past its deadline"},
}


def client_generated(value: UUID) -> UUID:
    if value.version != UUID_V7:
        raise ValueError("the id must be a uuid v7 generated when the form opens")
    return value


class LeaseRequest(BaseModel):
    id: Annotated[UUID, AfterValidator(client_generated)]
    unit_id: UUID
    renter_id: UUID
    monthly_rent_cents: Cents
    due_day: Annotated[int, Field(ge=1, le=31)]
    start_date: date
    end_date: date | None = None
    control_from_period: PeriodText
    tax_treatment: TaxTreatment
    opening_balance_pre_2026_cents: Cents | None = None
    opening_balance_2026_cents: Cents | None = None

    def new_lease(self) -> NewLease:
        terms = LeaseTerms(
            unit_id=self.unit_id,
            renter_id=self.renter_id,
            monthly_rent_cents=self.monthly_rent_cents,
            due_day=self.due_day,
            start_date=self.start_date,
            end_date=self.end_date,
            control_from=Period.parse(self.control_from_period),
            tax_treatment=self.tax_treatment,
        )
        opening = OpeningBalances(
            self.opening_balance_pre_2026_cents, self.opening_balance_2026_cents
        )
        return NewLease(self.id, terms, opening)


class LeaseResponse(BaseModel):
    id: UUID
    unit_id: UUID
    renter_id: UUID
    monthly_rent_cents: int = Field(description="The rent of the current period")
    due_day: int
    start_date: date
    end_date: date | None
    ended_at: date | None
    control_from_period: str
    tax_treatment: TaxTreatment
    days_to_end: int | None
    ending_soon: bool = Field(description="The planned end is 15 days away or less")


def lease_response(item: LeaseView) -> LeaseResponse:
    lease, terms = item.lease, item.lease.terms
    return LeaseResponse(
        id=lease.id,
        unit_id=terms.unit_id,
        renter_id=terms.renter_id,
        monthly_rent_cents=lease.current_rent_cents,
        due_day=terms.due_day,
        start_date=terms.start_date,
        end_date=terms.end_date,
        ended_at=lease.ended_at,
        control_from_period=str(terms.control_from),
        tax_treatment=terms.tax_treatment,
        days_to_end=item.days_to_end,
        ending_soon=item.ending_soon,
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_list: Callable[..., Awaitable[ListLeases]],
    provide_create: Callable[..., Awaitable[CreateLease]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/app/leases", responses=READ_ERRORS)
    async def list_leases(
        _: Annotated[AccountContext, Depends(current_account)],
        list_all: Annotated[ListLeases, Depends(provide_list)],
    ) -> list[LeaseResponse]:
        """Every lease of the account, ended ones included."""
        return [lease_response(item) for item in await list_all()]

    @router.post(
        "/api/app/leases",
        status_code=201,
        dependencies=[Depends(require_csrf)],
        responses={
            **READ_ERRORS,
            200: {"description": "The same id was already created with the same content"},
            403: {"description": "No account, unverified email past its deadline, or `csrf`"},
            404: {"description": "`unit_not_found` or `renter_not_found`"},
            409: {
                "description": "The id exists with other content or in another account (no"
                " detail), `plan_limit`, `unit_archived` or `unit_occupied`"
            },
            422: {
                "description": "Invalid data, `end_before_start`, `control_period_out_of_range`"
                " or `balance_2026_without_months`"
            },
        },
    )
    async def create_lease(
        body: LeaseRequest,
        response: Response,
        context: Annotated[AccountContext, Depends(current_account)],
        create: Annotated[CreateLease, Depends(provide_create)],
    ) -> LeaseResponse:
        """Start a lease with its first rent and up to two prior balances.

        The id comes from the client, so sending the same request again creates nothing
        (rule 5). A `conjugal_split` property forces the `unsupported` tax treatment.
        """
        result = await create(context, body.new_lease())
        if not isinstance(result, Created):
            if result == "conflict":
                raise HTTPException(status_code=409)
            raise HTTPException(status_code=STATUS.get(result, 422), detail=result)
        if result.replayed:
            response.status_code = 200
        return lease_response(result.view)

    return router
