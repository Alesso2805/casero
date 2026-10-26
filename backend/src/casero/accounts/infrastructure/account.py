from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.domain.entitlements import FEATURES, Plan, Subscription
from casero.shared.infrastructure.database import set_account_context

MEMBERSHIP = text("SELECT account_id FROM account_members WHERE user_id = :user_id")
CURRENT_SUBSCRIPTION = text(
    "SELECT plan_code, starts_at, trial_ends_at, ends_at, ended_at FROM subscriptions"
    " WHERE ended_at IS NULL ORDER BY starts_at DESC LIMIT 1"
)
PLAN = text("SELECT code, max_active_leases, features FROM plans WHERE code = :code")
DISPLAY_NAME = text("SELECT display_name FROM accounts")


class SqlMemberships:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def account_of(self, user_id: UUID) -> UUID | None:
        result = await self._connection.execute(MEMBERSHIP, {"user_id": user_id})
        account_id: UUID | None = result.scalar_one_or_none()
        return account_id


class SqlAccountScope:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def enter(self, account_id: UUID) -> None:
        await set_account_context(self._connection, account_id)


class SqlSubscriptions:
    """Reads under RLS: only the subscription of the account in context is visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def current(self) -> Subscription | None:
        row = (await self._connection.execute(CURRENT_SUBSCRIPTION)).first()
        if row is None:
            return None
        return Subscription(
            row.plan_code, row.starts_at, row.trial_ends_at, row.ends_at, row.ended_at
        )


class SqlPlans:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def plan(self, code: str) -> Plan:
        row = (await self._connection.execute(PLAN, {"code": code})).one()
        features = frozenset(feature for feature in FEATURES if row.features.get(feature))
        return Plan(row.code, row.max_active_leases, features)


class SqlAccounts:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def display_name(self) -> str:
        name: str = (await self._connection.execute(DISPLAY_NAME)).scalar_one()
        return name
