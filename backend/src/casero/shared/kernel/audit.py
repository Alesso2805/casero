from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from casero.shared.kernel.ids import new_id


@dataclass(frozen=True)
class AuditEntry:
    """Field names only: audit_log never holds personal values (SPEC)."""

    id: UUID
    account_id: UUID
    actor_user_id: UUID | None
    action: str
    entity: str
    entity_id: UUID | None
    changed_fields: tuple[str, ...]
    at: datetime

    @classmethod
    def of(
        cls,
        account_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity: str,
        entity_id: UUID,
        changed_fields: Iterable[str],
        at: datetime,
    ) -> AuditEntry:
        return cls(
            new_id(),
            account_id,
            actor_user_id,
            action,
            entity,
            entity_id,
            tuple(changed_fields),
            at,
        )


class AuditLog(Protocol):
    async def record(self, entry: AuditEntry) -> None: ...
