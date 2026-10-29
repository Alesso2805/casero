from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.ledger.api.payments import READ_ERRORS
from casero.ledger.application.collections import GetCollections
from casero.ledger.domain.collections import Standing


class LeaseCollectionResponse(BaseModel):
    lease_id: UUID
    ended: bool = Field(description="Ended leases are listed only while they still owe")
    status: Standing
    overdue_days: int = Field(description="Days since the oldest overdue charge was due")
    overdue_cents: int
    next_due_on: date | None = Field(description="The next charge not yet overdue, if any")
    next_due_cents: int
    balance_cents: int
    rent_to_remind: bool = Field(
        description="An unpaid rent the WhatsApp message can remind (prior debts are not)"
    )


class CollectionsResponse(BaseModel):
    due_by_month_end_cents: int = Field(
        description="Still owed on charges due by the last day of this month in Lima,"
        " overdue ones included"
    )
    overdue_cents: int
    leases: list[LeaseCollectionResponse] = Field(description="Most urgent first")


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_collections: Callable[..., Awaitable[GetCollections]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/app/collections", responses=READ_ERRORS)
    async def collections(
        _: Annotated[AccountContext, Depends(current_account)],
        get_collections: Annotated[GetCollections, Depends(provide_collections)],
    ) -> CollectionsResponse:
        """Who owes what today, for the collections panel."""
        result = await get_collections()
        return CollectionsResponse(
            due_by_month_end_cents=result.due_by_month_end_cents,
            overdue_cents=result.overdue_cents,
            leases=[
                LeaseCollectionResponse(
                    lease_id=line.lease_id,
                    ended=line.ended,
                    status=line.collection.status,
                    overdue_days=line.collection.overdue_days,
                    overdue_cents=line.collection.overdue_cents,
                    next_due_on=line.collection.next_due_on,
                    next_due_cents=line.collection.next_due_cents,
                    balance_cents=line.collection.balance_cents,
                    rent_to_remind=line.collection.rent_to_remind,
                )
                for line in result.leases
            ],
        )

    return router
