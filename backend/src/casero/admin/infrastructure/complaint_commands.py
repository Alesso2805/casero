from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.admin.domain.complaints import Complaint
from casero.admin.infrastructure.complaint_outbox import BY_NUMBER, complaint_from_row
from casero.shared.kernel.ids import new_id

RECORD_RESPONSE = text(
    "UPDATE complaints SET response = :response, responded_at = :at"
    " WHERE id = :id AND responded_at IS NULL RETURNING id"
)
RECORD_ACTION = text(
    "INSERT INTO staff_audit_log (id, staff_user_id, actor, action, entity, entity_id, at)"
    " VALUES (:id, NULL, 'cli', :action, :entity, :entity_id, :at)"
)


class SqlComplaintResponses:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def by_number(self, number: str) -> Complaint | None:
        row = (await self._connection.execute(BY_NUMBER, {"number": number})).first()
        return None if row is None else complaint_from_row(row)

    async def record_response(self, complaint_id: UUID, response: str, at: datetime) -> bool:
        recorded = await self._connection.execute(
            RECORD_RESPONSE, {"id": complaint_id, "response": response, "at": at}
        )
        return recorded.first() is not None


class SqlStaffActions:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def record(self, action: str, entity: str, entity_id: UUID, at: datetime) -> None:
        await self._connection.execute(
            RECORD_ACTION,
            {
                "id": new_id(),
                "action": action,
                "entity": entity,
                "entity_id": entity_id,
                "at": at,
            },
        )
