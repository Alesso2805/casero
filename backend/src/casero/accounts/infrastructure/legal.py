from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.domain.legal import LegalEvent
from casero.accounts.infrastructure.registration import INSERT_ACCEPTANCE, acceptance_ip_hash
from casero.shared.kernel.ids import new_id

EVENTS = text(
    "SELECT a.document_id, d.kind, a.accepted_at AS happened_at, false AS withdrawn"
    " FROM legal_acceptances a JOIN legal_documents d ON d.id = a.document_id"
    " WHERE a.user_id = :user_id"
    " UNION ALL"
    " SELECT w.document_id, d.kind, w.withdrawn_at, true"
    " FROM legal_withdrawals w JOIN legal_documents d ON d.id = w.document_id"
    " WHERE w.user_id = :user_id"
)
INSERT_WITHDRAWAL = text(
    "INSERT INTO legal_withdrawals (id, account_id, user_id, document_id, withdrawn_at)"
    " VALUES (:id, :account_id, :user_id, :document_id, :withdrawn_at)"
)


class SqlLegalRecords:
    def __init__(self, connection: AsyncConnection, ip_key: bytes) -> None:
        self._connection = connection
        self._ip_key = ip_key

    async def events(self, user_id: UUID) -> list[LegalEvent]:
        rows = await self._connection.execute(EVENTS, {"user_id": user_id})
        return [
            LegalEvent(row.document_id, row.kind, row.happened_at, row.withdrawn) for row in rows
        ]

    async def accept(
        self,
        account_id: UUID,
        user_id: UUID,
        document_ids: Sequence[UUID],
        client: str,
        at: datetime,
    ) -> None:
        ip_hash = acceptance_ip_hash(self._ip_key, client)
        await self._connection.execute(
            INSERT_ACCEPTANCE,
            [
                {
                    "id": new_id(),
                    "account_id": account_id,
                    "user_id": user_id,
                    "document_id": document_id,
                    "accepted_at": at,
                    "ip_hash": ip_hash,
                }
                for document_id in document_ids
            ],
        )

    async def withdraw(
        self, account_id: UUID, user_id: UUID, document_id: UUID, at: datetime
    ) -> None:
        await self._connection.execute(
            INSERT_WITHDRAWAL,
            {
                "id": new_id(),
                "account_id": account_id,
                "user_id": user_id,
                "document_id": document_id,
                "withdrawn_at": at,
            },
        )
