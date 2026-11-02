from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.entitlements import (
    Subscription,
    SubscriptionStatus,
    extended_until,
    subscription_status,
)
from casero.admin.application.complaint_commands import StaffActions
from casero.shared.kernel.clock import Clock

SEARCH_LIMIT = 20


@dataclass(frozen=True)
class AccountRecord:
    id: UUID
    email: str
    display_name: str | None
    created_at: datetime
    email_verified: bool
    deletion_requested_at: datetime | None
    purged_at: date | None
    subscription: Subscription | None
    founder: bool


@dataclass(frozen=True)
class SubscriptionPayment:
    id: UUID
    account_id: UUID
    amount_cents: int
    paid_on: date
    method: str
    boleta_number: str
    months: int


@dataclass(frozen=True)
class AccountSummary:
    account: AccountRecord
    status: SubscriptionStatus


@dataclass(frozen=True)
class AccountDetail:
    summary: AccountSummary
    payments: list[SubscriptionPayment]


class AccountDirectory(Protocol):
    async def search(self, email_part: str, limit: int) -> list[AccountRecord]: ...

    async def by_id(self, account_id: UUID) -> AccountRecord | None: ...

    async def payments(self, account_id: UUID) -> list[SubscriptionPayment]: ...


class SubscriptionLedger(Protocol):
    async def lock_open(self, account_id: UUID) -> tuple[UUID, Subscription] | None:
        """The open subscription, locked so two payments can't both extend from the same date."""
        ...

    async def add_payment(self, payment: SubscriptionPayment) -> bool:
        """False, with nothing written, when the id already exists."""
        ...

    async def payment(self, payment_id: UUID) -> SubscriptionPayment | None: ...

    async def extend(self, subscription_id: UUID, ends_at: date) -> None: ...


@dataclass(frozen=True)
class SearchAccounts:
    directory: AccountDirectory
    actions: StaffActions
    clock: Clock

    async def __call__(self, email_part: str, staff_id: UUID) -> list[AccountSummary]:
        """The audit row leaves out what was searched: it would be part of someone's email."""
        await self.actions.record("account.search", "accounts", None, self.clock.now(), staff_id)
        today = self.clock.today_lima()
        return [
            AccountSummary(account, subscription_status(account.subscription, today))
            for account in await self.directory.search(email_part, SEARCH_LIMIT)
        ]


@dataclass(frozen=True)
class ViewAccount:
    directory: AccountDirectory
    actions: StaffActions
    clock: Clock

    async def __call__(self, account_id: UUID, staff_id: UUID) -> AccountDetail | None:
        account = await self.directory.by_id(account_id)
        if account is None:
            return None
        await self.actions.record(
            "account.view", "accounts", account_id, self.clock.now(), staff_id
        )
        status = subscription_status(account.subscription, self.clock.today_lima())
        return AccountDetail(
            AccountSummary(account, status), await self.directory.payments(account_id)
        )


PaymentOutcome = Literal[
    "recorded", "not_found", "closing", "no_subscription", "id_conflict", "future_date"
]


@dataclass(frozen=True)
class RecordSubscriptionPayment:
    directory: AccountDirectory
    ledger: SubscriptionLedger
    actions: StaffActions
    clock: Clock

    async def __call__(self, payment: SubscriptionPayment, staff_id: UUID) -> PaymentOutcome:
        if payment.paid_on > self.clock.today_lima():
            return "future_date"
        account = await self.directory.by_id(payment.account_id)
        if account is None:
            return "not_found"
        if account.deletion_requested_at is not None or account.purged_at is not None:
            return "closing"
        opened = await self.ledger.lock_open(payment.account_id)
        if opened is None:
            return "no_subscription"
        subscription_id, subscription = opened
        if not await self.ledger.add_payment(payment):
            stored = await self.ledger.payment(payment.id)
            return "recorded" if stored == payment else "id_conflict"
        await self.ledger.extend(
            subscription_id, extended_until(subscription, payment.months, payment.paid_on)
        )
        await self.actions.record(
            "subscription.payment",
            "subscription_payments",
            payment.id,
            self.clock.now(),
            staff_id,
        )
        return "recorded"
