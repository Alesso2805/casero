from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from casero.accounts.application.entitlements import (
    GRACE_PERIOD,
    GetEntitlements,
    is_trial_lapsing,
)
from casero.accounts.application.profile import Profiles
from casero.reminders.application.tax_reminders import AccountOwner, TaxReminderMailer
from casero.reminders.domain.trial_end import PendingDue, trial_ended_email
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.periods import Period
from casero.tax.application.calculator import TaxRuleBook
from casero.tax.application.declarations import GetDeclarations


class BouncedAddresses(Protocol):
    async def blocks(self, email: str) -> bool: ...


class TrialEmailLog(Protocol):
    async def claim(self, account_id: UUID, now: datetime) -> bool:
        """True only the first time, recorded before sending: it goes out once (rule 12)."""
        ...


@dataclass(frozen=True)
class SendTrialEnded:
    """The single email when a trial ends unpaid, while the grace days still show the tax."""

    entitlements: GetEntitlements
    profiles: Profiles
    rule_book: TaxRuleBook
    declarations: GetDeclarations
    owner: AccountOwner
    bounced: BouncedAddresses
    log: TrialEmailLog
    mailer: TaxReminderMailer
    app_url: str
    clock: Clock

    async def __call__(self, account_id: UUID, today: date) -> None:
        subscription = (await self.entitlements()).subscription
        if subscription is None or subscription.trial_ends_at is None:
            return
        if not is_trial_lapsing(subscription, today):
            return
        contact = await self.owner.owner(account_id)
        if contact is None or await self.bounced.blocks(contact.email):
            return
        profile = await self.profiles.current()
        last_month = Period.of(today).previous()
        group = profile.ruc_group
        dues = (
            [
                (period, await self.rule_book.due_date(period, group))
                for period in (last_month.previous(), last_month)
            ]
            if group
            else []
        )
        pending = await self._pending(dues, today)
        if not await self.log.claim(account_id, self.clock.now()):
            return
        await self.mailer.send(
            trial_ended_email(
                contact.email,
                profile.display_name,
                subscription.trial_ends_at,
                subscription.trial_ends_at + GRACE_PERIOD,
                pending,
                self.app_url,
            )
        )

    async def _pending(
        self, dues: list[tuple[Period, date | None]], today: date
    ) -> list[PendingDue]:
        pending = []
        for period, due_on in dues:
            if due_on is None or due_on < today:
                continue
            month = await self.declarations(period)
            if isinstance(month, str):
                continue
            owed = sum(card.pending_cents for card in month.cards)
            if owed:
                pending.append(PendingDue(period, due_on, owed))
        return pending
