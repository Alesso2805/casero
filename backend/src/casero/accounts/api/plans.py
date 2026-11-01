from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from casero.accounts.application.context import AccountContext
from casero.accounts.application.plans import PlanOffers


class PlanResponse(BaseModel):
    code: str
    name: str
    price_month_cents: int
    price_year_cents: int
    max_active_leases: int


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_offers: Callable[..., Awaitable[PlanOffers]],
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/app/plans",
        responses={
            401: {"description": "No valid session"},
            403: {"description": "No account, unverified email, or a legal step pending"},
        },
    )
    async def plans(
        _: Annotated[AccountContext, Depends(current_account)],
        offers: Annotated[PlanOffers, Depends(provide_offers)],
    ) -> list[PlanResponse]:
        """The plans with their prices, from the cheapest."""
        return [
            PlanResponse(
                code=offer.code,
                name=offer.name,
                price_month_cents=offer.price_month_cents,
                price_year_cents=offer.price_year_cents,
                max_active_leases=offer.max_active_leases,
            )
            for offer in await offers.offers()
        ]

    return router
