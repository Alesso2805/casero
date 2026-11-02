from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.application.entitlements import Subscription
from casero.admin.application.accounts import AccountRecord, SubscriptionPayment

ACCOUNT_COLUMNS = (
    "SELECT a.id, u.email, a.display_name, a.created_at, u.email_verified_at,"
    " a.deletion_requested_at, a.purged_at, s.plan_code, s.starts_at, s.trial_ends_at,"
    " s.ends_at, s.ended_at, s.founder"
    " FROM accounts a"
    " JOIN account_members m ON m.account_id = a.id"
    " JOIN users u ON u.id = m.user_id"
    " LEFT JOIN subscriptions s ON s.account_id = a.id AND s.ended_at IS NULL"
)
SEARCH = text(
    ACCOUNT_COLUMNS
    + " WHERE lower(u.email) LIKE :pattern ESCAPE '\\' ORDER BY u.email LIMIT :limit"
)
BY_ID = text(ACCOUNT_COLUMNS + " WHERE a.id = :account_id")
PAYMENT_COLUMNS = (
    "SELECT id, account_id, amount_cents, paid_on, method, boleta_number, months"
    " FROM subscription_payments"
)
PAYMENTS = text(PAYMENT_COLUMNS + " WHERE account_id = :account_id ORDER BY paid_on DESC, id DESC")
PAYMENT = text(PAYMENT_COLUMNS + " WHERE id = :id")
LOCK_OPEN = text(
    "SELECT id, plan_code, starts_at, trial_ends_at, ends_at, ended_at FROM subscriptions"
    " WHERE account_id = :account_id AND ended_at IS NULL FOR UPDATE"
)
INSERT_PAYMENT = text(
    "INSERT INTO subscription_payments"
    " (id, account_id, amount_cents, paid_on, method, boleta_number, months)"
    " VALUES (:id, :account_id, :amount_cents, :paid_on, :method, :boleta_number, :months)"
    " ON CONFLICT (id) DO NOTHING RETURNING id"
)
EXTEND = text("UPDATE subscriptions SET ends_at = :ends_at WHERE id = :id")


def contains_pattern(email_part: str) -> str:
    """A LIKE pattern that takes `_` and `%` as themselves: `_` is common in email addresses."""
    escaped = email_part.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def subscription_from_row(row: Any) -> Subscription:
    return Subscription(row.plan_code, row.starts_at, row.trial_ends_at, row.ends_at, row.ended_at)


def account_from_row(row: Any) -> AccountRecord:
    return AccountRecord(
        row.id,
        row.email,
        row.display_name,
        row.created_at,
        row.email_verified_at is not None,
        row.deletion_requested_at,
        row.purged_at,
        None if row.plan_code is None else subscription_from_row(row),
        bool(row.founder),
    )


def payment_from_row(row: Any) -> SubscriptionPayment:
    return SubscriptionPayment(
        row.id,
        row.account_id,
        row.amount_cents,
        row.paid_on,
        row.method,
        row.boleta_number,
        row.months,
    )


class SqlAccountDirectory:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def search(self, email_part: str, limit: int) -> list[AccountRecord]:
        rows = await self._connection.execute(
            SEARCH, {"pattern": contains_pattern(email_part), "limit": limit}
        )
        return [account_from_row(row) for row in rows]

    async def by_id(self, account_id: UUID) -> AccountRecord | None:
        row = (await self._connection.execute(BY_ID, {"account_id": account_id})).first()
        return None if row is None else account_from_row(row)

    async def payments(self, account_id: UUID) -> list[SubscriptionPayment]:
        rows = await self._connection.execute(PAYMENTS, {"account_id": account_id})
        return [payment_from_row(row) for row in rows]


class SqlSubscriptionLedger:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def lock_open(self, account_id: UUID) -> tuple[UUID, Subscription] | None:
        row = (await self._connection.execute(LOCK_OPEN, {"account_id": account_id})).first()
        if row is None:
            return None
        return row.id, subscription_from_row(row)

    async def add_payment(self, payment: SubscriptionPayment) -> bool:
        added = await self._connection.execute(
            INSERT_PAYMENT,
            {
                "id": payment.id,
                "account_id": payment.account_id,
                "amount_cents": payment.amount_cents,
                "paid_on": payment.paid_on,
                "method": payment.method,
                "boleta_number": payment.boleta_number,
                "months": payment.months,
            },
        )
        return added.first() is not None

    async def payment(self, payment_id: UUID) -> SubscriptionPayment | None:
        row = (await self._connection.execute(PAYMENT, {"id": payment_id})).first()
        return None if row is None else payment_from_row(row)

    async def extend(self, subscription_id: UUID, ends_at: date) -> None:
        await self._connection.execute(EXTEND, {"id": subscription_id, "ends_at": ends_at})
