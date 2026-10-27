from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.kernel.audit import AuditEntry

INSERT_ENTRY = text(
    "INSERT INTO audit_log"
    " (id, account_id, actor_user_id, action, entity, entity_id, changed_fields, at)"
    " VALUES (:id, :account_id, :actor_user_id, :action, :entity, :entity_id,"
    " :changed_fields, :at)"
)


class SqlAuditLog:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def record(self, entry: AuditEntry) -> None:
        await self._connection.execute(
            INSERT_ENTRY,
            {
                "id": entry.id,
                "account_id": entry.account_id,
                "actor_user_id": entry.actor_user_id,
                "action": entry.action,
                "entity": entry.entity,
                "entity_id": entry.entity_id,
                "changed_fields": list(entry.changed_fields),
                "at": entry.at,
            },
        )
