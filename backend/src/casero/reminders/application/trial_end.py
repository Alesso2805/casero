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
from casero.tax.application.upcoming import GetPendingDues


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
    pending_dues: GetPendingDues
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
        pending = [
            PendingDue(due.period, due.due_on, due.pending_cents)
            for due in await self.pending_dues()
        ]
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
