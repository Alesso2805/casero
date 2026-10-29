from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.reminders.application.tax_reminders import Contact

OWNER = text(
    "SELECT u.id, u.email FROM account_members m JOIN users u ON u.id = m.user_id"
    " WHERE m.account_id = :account_id AND m.role = 'owner'"
    " AND u.email_verified_at IS NOT NULL AND u.deleted_at IS NULL"
)


class SqlAccountOwner:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def owner(self, account_id: UUID) -> Contact | None:
        row = (await self._connection.execute(OWNER, {"account_id": account_id})).first()
        return None if row is None else Contact(row.id, row.email)
