from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext, AccountScope
from casero.accounts.domain.deletion import DELETION_GRACE, anonymized_email
from casero.identity.application.account_emails import (
    AccountEmailSender,
    AccountUsers,
    EmailTokens,
)
from casero.identity.application.sessions import SessionStore
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock


@dataclass(frozen=True)
class CancelledDeletion:
    account_id: UUID
    user_id: UUID
    sealed_contact: str


class DeletionRecords(Protocol):
    async def schedule(
        self, account_id: UUID, sealed_contact: str, at: datetime, purge_on: date
    ) -> None: ...

    async def forget_invites(self, email: str) -> None: ...

    async def cancel(self, token_hash: bytes, now: datetime) -> CancelledDeletion | None: ...


class ContactSeal(Protocol):
    def seal(self, account_id: UUID, email: str) -> str: ...

    def open(self, account_id: UUID, sealed: str) -> str: ...


@dataclass(frozen=True)
class RequestDeletion:
    """Takes the account out of use now; the worker purges it DELETION_GRACE later (SPEC).

    The email goes last and a failure undoes everything, because that link is the only way back.
    An address that bounced gets no link, but its owner can still delete the account.
    """

    users: AccountUsers
    records: DeletionRecords
    seal: ContactSeal
    sender: AccountEmailSender
    sessions: SessionStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext
    ) -> date | Literal["already_requested", "email_failed"]:
        user = await self.users.by_id(context.user_id)
        if user is None:
            return "already_requested"
        now = self.clock.now()
        purge_on = self.clock.today_lima() + DELETION_GRACE
        sealed = self.seal.seal(context.account_id, user.email)
        await self.records.schedule(context.account_id, sealed, now, purge_on)
        await self.records.forget_invites(user.email)
        await self.users.set_email(user.user_id, anonymized_email(user.user_id), now)
        await self.sessions.revoke_all(user.user_id, now)
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "account.deletion_requested",
                "accounts",
                context.account_id,
                ["deletion_scheduled_for"],
                now,
            )
        )
        outcome = await self.sender.send_cancel_deletion(user, purge_on, now + DELETION_GRACE)
        return "email_failed" if outcome == "failed" else purge_on


@dataclass(frozen=True)
class CancelDeletion:
    """Restores the account from the emailed link, in the transaction that consumes the token.

    Someone may have registered that email meanwhile; the token then stays unused.
    """

    tokens: EmailTokens
    records: DeletionRecords
    seal: ContactSeal
    users: AccountUsers
    scope: AccountScope
    audit: AuditLog
    clock: Clock

    async def __call__(self, token: str) -> Literal["cancelled", "invalid", "email_taken"]:
        now = self.clock.now()
        cancelled = await self.records.cancel(self.tokens.hash(token), now)
        if cancelled is None:
            return "invalid"
        email = self.seal.open(cancelled.account_id, cancelled.sealed_contact)
        if await self.users.by_email(email) is not None:
            return "email_taken"
        await self.users.set_email(cancelled.user_id, email, None)
        await self.scope.enter(cancelled.account_id)
        await self.audit.record(
            AuditEntry.of(
                cancelled.account_id,
                cancelled.user_id,
                "account.deletion_cancelled",
                "accounts",
                cancelled.account_id,
                ["deletion_scheduled_for"],
                now,
            )
        )
        return "cancelled"
