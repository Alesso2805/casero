from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.domain.waitlist import WaitlistEntry

INSERT = text(
    "INSERT INTO waitlist_entries (id, email, source, consented_at, created_at)"
    " VALUES (:id, :email, :source, :consented_at, :created_at)"
    " ON CONFLICT DO NOTHING"
)


class SqlWaitlistRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, entry: WaitlistEntry) -> None:
        await self._connection.execute(
            INSERT,
            {
                "id": entry.id,
                "email": entry.email,
                "source": entry.source,
                "consented_at": entry.consented_at,
                "created_at": entry.created_at,
            },
        )
