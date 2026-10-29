from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.reminders.domain.messages import TemplateKind

BODIES = text("SELECT kind, body FROM message_templates")
SAVE = text(
    "INSERT INTO message_templates (account_id, kind, body) VALUES (:account_id, :kind, :body)"
    " ON CONFLICT (account_id, kind) DO UPDATE SET body = EXCLUDED.body"
)


class SqlTemplateStore:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def bodies(self) -> dict[TemplateKind, str]:
        rows = await self._connection.execute(BODIES)
        return {cast(TemplateKind, row.kind): row.body for row in rows}

    async def save(self, account_id: UUID, kind: TemplateKind, body: str) -> None:
        await self._connection.execute(SAVE, {"account_id": account_id, "kind": kind, "body": body})
