from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, StringConstraints

from casero.admin.application.accounts import (
    AccountDetail,
    AccountSummary,
    RecordSubscriptionPayment,
    SearchAccounts,
    SubscriptionPayment,
    ViewAccount,
)
from casero.admin.domain.staff import StaffSession
from casero.shared.infrastructure.csrf import require_csrf

MIN_SEARCH_LENGTH = 3
MAX_SEARCH_LENGTH = 254
MAX_CENTS = 100_000_00
MAX_MONTHS = 24
MAX_BOLETA_LENGTH = 40

BoletaNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_BOLETA_LENGTH)
]


class AccountResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    created_at: datetime
    email_verified: bool
    deletion_requested_at: datetime | None
    purged_at: date | None
    status: str
    plan_code: str | None
    trial_ends_at: date | None
    ends_at: date | None
    founder: bool


class PaymentResponse(BaseModel):
    id: UUID
    amount_cents: int
    paid_on: date
    method: str
    boleta_number: str
    months: int


class AccountDetailResponse(AccountResponse):
    payments: list[PaymentResponse]


class RecordPaymentRequest(BaseModel):
    id: UUID
    amount_cents: Annotated[int, Field(gt=0, le=MAX_CENTS)]
    paid_on: date
    method: Literal["yape", "transfer"]
    boleta_number: BoletaNumber
    months: Annotated[int, Field(ge=1, le=MAX_MONTHS)]


def account_fields(summary: AccountSummary) -> dict[str, object]:
    account = summary.account
    subscription = account.subscription
    return {
        "id": account.id,
        "email": account.email,
        "display_name": account.display_name,
        "created_at": account.created_at,
        "email_verified": account.email_verified,
        "deletion_requested_at": account.deletion_requested_at,
        "purged_at": account.purged_at,
        "status": summary.status,
        "plan_code": subscription.plan_code if subscription else None,
        "trial_ends_at": subscription.trial_ends_at if subscription else None,
        "ends_at": subscription.ends_at if subscription else None,
        "founder": account.founder,
    }


def detail_response(detail: AccountDetail) -> AccountDetailResponse:
    return AccountDetailResponse(
        **account_fields(detail.summary),
        payments=[
            PaymentResponse(
                id=payment.id,
                amount_cents=payment.amount_cents,
                paid_on=payment.paid_on,
                method=payment.method,
                boleta_number=payment.boleta_number,
                months=payment.months,
            )
            for payment in detail.payments
        ],
    )


def create_router(
    current_staff: Callable[..., Awaitable[StaffSession]],
    provide_search: Callable[..., Awaitable[SearchAccounts]],
    provide_view: Callable[..., Awaitable[ViewAccount]],
    provide_record: Callable[..., Awaitable[RecordSubscriptionPayment]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/accounts", responses={401: {"description": "No valid staff session"}})
    async def search(
        email: Annotated[str, Query(min_length=MIN_SEARCH_LENGTH, max_length=MAX_SEARCH_LENGTH)],
        session: Annotated[StaffSession, Depends(current_staff)],
        search: Annotated[SearchAccounts, Depends(provide_search)],
    ) -> list[AccountResponse]:
        """Accounts whose email contains the text, without distinguishing case."""
        summaries = await search(email.strip(), session.staff_id)
        return [AccountResponse(**account_fields(summary)) for summary in summaries]

    @router.get(
        "/api/admin/accounts/{account_id}",
        responses={
            401: {"description": "No valid staff session"},
            404: {"description": "No such account"},
        },
    )
    async def view(
        account_id: UUID,
        session: Annotated[StaffSession, Depends(current_staff)],
        view: Annotated[ViewAccount, Depends(provide_view)],
    ) -> AccountDetailResponse:
        """One account with its subscription and the payments recorded for it."""
        detail = await view(account_id, session.staff_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="not_found")
        return detail_response(detail)

    @router.post(
        "/api/admin/accounts/{account_id}/payments",
        status_code=204,
        dependencies=[Depends(require_csrf)],
        responses={
            401: {"description": "No valid staff session"},
            404: {"description": "No such account"},
            409: {"description": "`account_closing`, `no_subscription`, or an id already used"},
            422: {"description": "`future_date`, or an invalid body"},
        },
    )
    async def record_payment(
        account_id: UUID,
        body: RecordPaymentRequest,
        session: Annotated[StaffSession, Depends(current_staff)],
        record: Annotated[RecordSubscriptionPayment, Depends(provide_record)],
    ) -> Response:
        """Record a payment and extend the subscription; sending it again changes nothing."""
        payment = SubscriptionPayment(
            body.id,
            account_id,
            body.amount_cents,
            body.paid_on,
            body.method,
            body.boleta_number,
            body.months,
        )
        outcome = await record(payment, session.staff_id)
        if outcome == "not_found":
            raise HTTPException(status_code=404, detail="not_found")
        if outcome == "future_date":
            raise HTTPException(status_code=422, detail="future_date")
        if outcome == "closing":
            raise HTTPException(status_code=409, detail="account_closing")
        if outcome == "no_subscription":
            raise HTTPException(status_code=409, detail="no_subscription")
        if outcome == "id_conflict":
            raise HTTPException(status_code=409)
        return Response(status_code=204)

    return router
