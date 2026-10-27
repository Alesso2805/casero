from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


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


class AuditLog(Protocol):
    async def record(self, entry: AuditEntry) -> None: ...
