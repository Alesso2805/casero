from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.application.profile import Profiles
from casero.reminders.domain.tax_reminders import (
    REMINDER_DAYS_BEFORE,
    DueMonth,
    OwedDeclaration,
    tax_reminder_email,
)
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.email import Email
from casero.shared.kernel.periods import Period
from casero.tax.application.calculator import TaxRuleBook
from casero.tax.application.declarations import GetDeclarations

TaxReminders = Literal["tax_reminders"]


@dataclass(frozen=True)
class Contact:
    user_id: UUID
    email: str


class AccountOwner(Protocol):
    async def owner(self, account_id: UUID) -> Contact | None:
        """The owner's address, only once verified: until then only verification emails go out."""
        ...


class Suppressions(Protocol):
    async def blocks(self, email: str, kind: TaxReminders) -> bool: ...


class UnsubscribeLinks(Protocol):
    def links(self, user_id: UUID, kind: TaxReminders) -> tuple[str, str]:
        """The /baja page for the body, and the one-click URL for the header (RFC 8058)."""
        ...


class TaxReminderLog(Protocol):
    async def add_tax_due(
        self,
        account_id: UUID,
        period: Period,
        renter_id: UUID,
        renter_doc_hmac: bytes | None,
        at: datetime,
    ) -> None: ...


class TaxReminderMailer(Protocol):
    async def send(self, email: Email) -> None: ...


@dataclass(frozen=True)
class SendTaxReminders:
    """Emails what is pending 5 days and 1 day before each 1683's due date (SPEC).

    The log rows are written in the account's transaction before sending: if the send
    fails, they roll back and the worker retries the account later that day (rule 12).
    """

    entitlements: GetEntitlements
    profiles: Profiles
    rule_book: TaxRuleBook
    declarations: GetDeclarations
    owner: AccountOwner
    suppressions: Suppressions
    unsubscribe: UnsubscribeLinks
    log: TaxReminderLog
    mailer: TaxReminderMailer
    app_url: str
    clock: Clock

    async def __call__(self, account_id: UUID, today: date) -> None:
        if not (await self.entitlements()).allows("tax_reminders"):
            return
        profile = await self.profiles.current()
        group = profile.ruc_group
        if group is None:
            return
        due: tuple[Period, date] | None = None
        for period in (Period.of(today).previous(), Period.of(today).previous().previous()):
            due_on = await self.rule_book.due_date(period, group)
            if due_on is not None and (due_on - today).days in REMINDER_DAYS_BEFORE:
                due = (period, due_on)
        if due is None:
            return
        due_period, due_on = due
        month = await self.declarations(due_period)
        if isinstance(month, str):
            return
        cards = [card for card in month.cards if card.pending_cents > 0]
        if not cards:
            return
        contact = await self.owner.owner(account_id)
        if contact is None or await self.suppressions.blocks(contact.email, "tax_reminders"):
            return
        now = self.clock.now()
        for card in cards:
            await self.log.add_tax_due(
                account_id,
                due_period,
                card.declaration.declarant.renter_id,
                card.declaration.declarant.doc_hmac,
                now,
            )
        page, one_click = self.unsubscribe.links(contact.user_id, "tax_reminders")
        owed = [
            OwedDeclaration(card.renter_name, card.pending_cents, card.declaration.incomplete)
            for card in cards
        ]
        await self.mailer.send(
            tax_reminder_email(
                contact.email,
                profile.display_name,
                DueMonth(due_period, due_on, owed),
                today,
                self.app_url,
                page,
                one_click,
            )
        )
