from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.reminders.domain.messages import (
    DEFAULT_BODIES,
    TEMPLATE_KINDS,
    TemplateKind,
    unknown_variables,
)
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


class TemplateStore(Protocol):
    async def bodies(self) -> dict[TemplateKind, str]:
        """Only the templates the landlord edited; the rest use SPEC's defaults."""
        ...

    async def save(self, account_id: UUID, kind: TemplateKind, body: str) -> None: ...


@dataclass(frozen=True)
class Template:
    kind: TemplateKind
    body: str
    default_body: str


@dataclass(frozen=True)
class ListTemplates:
    store: TemplateStore

    async def __call__(self) -> list[Template]:
        edited = await self.store.bodies()
        return [
            Template(kind, edited.get(kind, DEFAULT_BODIES[kind]), DEFAULT_BODIES[kind])
            for kind in TEMPLATE_KINDS
        ]


@dataclass(frozen=True)
class SaveTemplate:
    store: TemplateStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, kind: TemplateKind, body: str
    ) -> Template | Literal["unknown_variable"]:
        if unknown_variables(body):
            return "unknown_variable"
        await self.store.save(context.account_id, kind, body)
        await self.audit.record(
            AuditEntry(
                new_id(),
                context.account_id,
                context.user_id,
                "message_template.updated",
                "message_templates",
                None,
                (kind,),
                self.clock.now(),
            )
        )
        return Template(kind, body, DEFAULT_BODIES[kind])
