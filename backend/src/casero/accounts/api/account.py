from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from casero.accounts.application.account import GetAccountSummary
from casero.accounts.application.context import AccountContext
from casero.accounts.domain.entitlements import FEATURES, Feature, SubscriptionStatus


class AccountResponse(BaseModel):
    display_name: str
    plan_code: str
    status: SubscriptionStatus
    trial_ends_at: date | None
    ends_at: date | None
    max_active_leases: int
    features: dict[Feature, bool]


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_summary: Callable[..., Awaitable[GetAccountSummary]],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/app/account",
        responses={
            401: {"description": "No valid session"},
            403: {"description": "No account, or the email is unverified past its deadline"},
        },
    )
    async def account(
        _: Annotated[AccountContext, Depends(current_account)],
        summary: Annotated[GetAccountSummary, Depends(provide_summary)],
    ) -> AccountResponse:
        """The account in context with its plan, subscription status and features."""
        result = await summary()
        entitlements = result.entitlements
        subscription = entitlements.subscription
        return AccountResponse(
            display_name=result.display_name,
            plan_code=entitlements.plan.code,
            status=entitlements.status,
            trial_ends_at=subscription.trial_ends_at if subscription else None,
            ends_at=subscription.ends_at if subscription else None,
            max_active_leases=entitlements.plan.max_active_leases,
            features={feature: entitlements.allows(feature) for feature in FEATURES},
        )

    return router
