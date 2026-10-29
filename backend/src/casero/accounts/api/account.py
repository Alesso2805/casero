from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from casero.accounts.api.registration import DisplayName
from casero.accounts.application.account import GetAccountSummary
from casero.accounts.application.context import AccountContext
from casero.accounts.application.profile import (
    GetProfile,
    ProfileChange,
    ProfileView,
    UpdateProfile,
)
from casero.accounts.domain.entitlements import FEATURES, Feature, SubscriptionStatus
from casero.accounts.domain.profile import RucGroup, TaxpayerKind
from casero.shared.infrastructure.csrf import require_csrf

Ruc = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{11}$")]


ACCOUNT_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, or the email is unverified past its deadline"},
}


class AccountResponse(BaseModel):
    display_name: str
    plan_code: str
    status: SubscriptionStatus
    trial_ends_at: date | None
    ends_at: date | None
    max_active_leases: int
    features: dict[Feature, bool]


class ProfileRequest(BaseModel):
    display_name: DisplayName
    taxpayer_kind: TaxpayerKind
    ruc: Ruc | None
    good_taxpayer: bool = False
    daily_digest: bool
    tax_reminders_email: bool | None = Field(
        default=None,
        description="The user gets the SUNAT due-date reminders; true undoes an unsubscribe,"
        " and leaving it out keeps the current choice",
    )


class ProfileResponse(BaseModel):
    display_name: str
    taxpayer_kind: TaxpayerKind
    ruc: str | None
    ruc_group: RucGroup | None
    daily_digest: bool
    declarant_locked: bool
    tax_reminders_email: bool


def profile_response(view: ProfileView) -> ProfileResponse:
    profile = view.profile
    return ProfileResponse(
        display_name=profile.display_name,
        taxpayer_kind=profile.taxpayer_kind,
        ruc=profile.ruc,
        ruc_group=profile.ruc_group,
        daily_digest=profile.daily_digest,
        declarant_locked=view.declarant_locked,
        tax_reminders_email=view.tax_reminders_email,
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_summary: Callable[..., Awaitable[GetAccountSummary]],
    provide_get_profile: Callable[..., Awaitable[GetProfile]],
    provide_update_profile: Callable[..., Awaitable[UpdateProfile]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/app/account", responses=ACCOUNT_ERRORS)
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

    @router.get("/api/app/account/profile", responses=ACCOUNT_ERRORS)
    async def profile(
        context: Annotated[AccountContext, Depends(current_account)],
        get_profile: Annotated[GetProfile, Depends(provide_get_profile)],
    ) -> ProfileResponse:
        """The landlord's name, declarant type, RUC with its schedule group and email choices.

        `declarant_locked` is true once the account has properties, archived ones included.
        """
        return profile_response(await get_profile(context))

    @router.put(
        "/api/app/account/profile",
        dependencies=[Depends(require_csrf)],
        responses={
            **ACCOUNT_ERRORS,
            403: {"description": "No account, unverified email past its deadline, or `csrf`"},
            409: {"description": "`declarant_locked`: the account has properties"},
            422: {"description": "Invalid data, or `invalid_ruc` when the check digit fails"},
        },
    )
    async def update_profile(
        body: ProfileRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        update: Annotated[UpdateProfile, Depends(provide_update_profile)],
    ) -> ProfileResponse:
        """Replace the profile; the schedule group comes from the RUC's last digit."""
        result = await update(
            context,
            ProfileChange(
                display_name=body.display_name,
                taxpayer_kind=body.taxpayer_kind,
                ruc=body.ruc,
                good_taxpayer=body.good_taxpayer,
                daily_digest=body.daily_digest,
                tax_reminders_email=body.tax_reminders_email,
            ),
        )
        if result == "invalid_ruc":
            raise HTTPException(status_code=422, detail=result)
        if result == "declarant_locked":
            raise HTTPException(status_code=409, detail=result)
        return profile_response(result)

    return router
