from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.application.deletion import CancelledDeletion
from casero.shared.infrastructure.crypto import FieldCipher, field_context

SCHEDULE = text(
    "UPDATE accounts SET deletion_requested_at = :at, deletion_scheduled_for = :purge_on,"
    " deletion_contact_enc = :contact WHERE id = :id"
)
FORGET_INVITES = text("DELETE FROM registration_invites WHERE lower(email) = lower(:email)")
CANCEL = text(
    "SELECT account_id, user_id, deletion_contact_enc FROM app_cancel_deletion(:token_hash, :now)"
)


class SqlDeletionRecords:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def schedule(
        self, account_id: UUID, sealed_contact: str, at: datetime, purge_on: date
    ) -> None:
        await self._connection.execute(
            SCHEDULE,
            {"id": account_id, "at": at, "purge_on": purge_on, "contact": sealed_contact},
        )

    async def forget_invites(self, email: str) -> None:
        await self._connection.execute(FORGET_INVITES, {"email": email})

    async def cancel(self, token_hash: bytes, now: datetime) -> CancelledDeletion | None:
        row = (
            await self._connection.execute(CANCEL, {"token_hash": token_hash, "now": now})
        ).first()
        if row is None:
            return None
        return CancelledDeletion(row.account_id, row.user_id, row.deletion_contact_enc)


class CipherContactSeal:
    def __init__(self, cipher: FieldCipher) -> None:
        self._cipher = cipher

    def seal(self, account_id: UUID, email: str) -> str:
        return self._cipher.encrypt(
            email, field_context("accounts", "deletion_contact_enc", account_id, account_id)
        )

    def open(self, account_id: UUID, sealed: str) -> str:
        return self._cipher.decrypt(
            sealed, field_context("accounts", "deletion_contact_enc", account_id, account_id)
        )
