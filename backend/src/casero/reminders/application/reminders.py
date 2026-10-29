from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.entitlements import GetEntitlements
from casero.ledger.application.payments import ChargeLine, GetStatement
from casero.reminders.application.templates import TemplateStore
from casero.reminders.domain.messages import (
    DEFAULT_BODIES,
    TemplateKind,
    day_label,
    period_label,
    render,
    uses_link,
    whatsapp_url,
)
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.money import format_soles

UNPAID = ("overdue", "due_today", "due_soon", "pending")


@dataclass(frozen=True)
class Recipient:
    renter_id: UUID
    full_name: str
    phone_e164: str | None
    tools_enabled: bool


class RecipientStore(Protocol):
    async def recipient(self, lease_id: UUID) -> Recipient | None: ...


class TenantLinkUrls(Protocol):
    """Implemented by `tenant_portal`, which comes after `reminders` (AR-03)."""

    async def url_for(self, context: AccountContext, lease_id: UUID) -> str | None:
        """The lease's link in use, issued now if it has none; None without the portal."""
        ...


class ReminderLog(Protocol):
    async def add_rent(
        self, account_id: UUID, charge_id: UUID, renter_id: UUID, at: datetime
    ) -> None: ...


@dataclass(frozen=True)
class PreparedReminder:
    kind: TemplateKind
    charge_id: UUID
    message: str
    url: str


ReminderRefusal = Literal["lease_not_found", "whatsapp_unavailable", "nothing_due"]


def template_kind(line: ChargeLine) -> TemplateKind:
    match line.status:
        case "overdue":
            return "overdue"
        case "due_today":
            return "due_today"
        case _:
            return "friendly"


@dataclass(frozen=True)
class PrepareReminder:
    """The WhatsApp message for the lease's most urgent unpaid rent, logged as sent."""

    entitlements: GetEntitlements
    recipients: RecipientStore
    statements: GetStatement
    templates: TemplateStore
    links: TenantLinkUrls
    log: ReminderLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, lease_id: UUID
    ) -> PreparedReminder | ReminderRefusal:
        recipient = await self.recipients.recipient(lease_id)
        statement = await self.statements(lease_id)
        if recipient is None or statement is None:
            return "lease_not_found"
        if not recipient.tools_enabled or not (await self.entitlements()).allows("whatsapp_links"):
            return "whatsapp_unavailable"
        line = next(
            (
                line
                for line in statement.charges
                if line.charge.kind in ("rent", "rent_correction") and line.status in UNPAID
            ),
            None,
        )
        if line is None or line.charge.period is None:
            return "nothing_due"
        kind = template_kind(line)
        body = (await self.templates.bodies()).get(kind, DEFAULT_BODIES[kind])
        link = await self.links.url_for(context, lease_id) if uses_link(body) else None
        message = render(
            body,
            {
                "inquilino": recipient.full_name,
                "monto": format_soles(line.outstanding_cents),
                "periodo": period_label(line.charge.period),
                "fecha": day_label(line.charge.due_date),
                "enlace": link or "",
            },
        )
        await self.log.add_rent(
            context.account_id, line.charge.id, recipient.renter_id, self.clock.now()
        )
        return PreparedReminder(
            kind, line.charge.id, message, whatsapp_url(recipient.phone_e164, message)
        )
