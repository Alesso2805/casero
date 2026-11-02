from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.admin.application.oversight import ComplaintDeadline, ScheduleEntry

SCHEDULE = text(
    "SELECT period, ruc_group, due_date, source_url FROM sunat_due_dates ORDER BY period, ruc_group"
)
COMPLAINT_DEADLINES = text(
    "SELECT number, kind, created_at, due_at, responded_at, response_channel FROM complaints"
    " ORDER BY responded_at IS NOT NULL, CASE WHEN responded_at IS NULL THEN due_at END,"
    " responded_at DESC, number LIMIT :limit"
)


class SqlOversightRecords:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def schedule(self) -> list[ScheduleEntry]:
        rows = await self._connection.execute(SCHEDULE)
        return [
            ScheduleEntry(row.period, row.ruc_group, row.due_date, row.source_url) for row in rows
        ]

    async def complaint_deadlines(self, limit: int) -> list[ComplaintDeadline]:
        rows = await self._connection.execute(COMPLAINT_DEADLINES, {"limit": limit})
        return [
            ComplaintDeadline(
                row.number,
                row.kind,
                row.created_at,
                row.due_at,
                row.responded_at,
                row.response_channel,
            )
            for row in rows
        ]
