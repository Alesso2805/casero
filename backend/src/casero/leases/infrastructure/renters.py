from typing import Any
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.leases.domain.renters import Document, Renter, RenterDetails
from casero.shared.infrastructure.crypto import DocumentHasher, FieldCipher, field_context

SELECT_RENTERS = "SELECT id, full_name, phone_e164, doc_type, doc_last4 FROM renters"
ALL_RENTERS = text(SELECT_RENTERS + " ORDER BY id")
LOCK_RENTER = text(SELECT_RENTERS + " WHERE id = :id FOR UPDATE")
HOLDER = text("SELECT id FROM renters WHERE doc_hmac = :doc_hmac")
ADD_RENTER = text(
    "INSERT INTO renters (id, account_id, full_name, phone_e164, doc_type, doc_enc, doc_hmac,"
    " doc_last4) VALUES (:id, :account_id, :full_name, :phone_e164, :doc_type, :doc_enc,"
    " :doc_hmac, :doc_last4)"
)
UPDATE_RENTER = text(
    "UPDATE renters SET full_name = :full_name, phone_e164 = :phone_e164 WHERE id = :id"
)
SET_DOCUMENT = text(
    "UPDATE renters SET doc_type = :doc_type, doc_enc = :doc_enc, doc_hmac = :doc_hmac,"
    " doc_last4 = :doc_last4 WHERE id = :id"
)


def renter(row: Row[Any]) -> Renter:
    return Renter(row.id, RenterDetails(row.full_name, row.phone_e164), row.doc_type, row.doc_last4)


class SqlRenterStore:
    """Reads under RLS: only the renters of the account in context are visible."""

    def __init__(
        self, connection: AsyncConnection, cipher: FieldCipher, hasher: DocumentHasher
    ) -> None:
        self._connection = connection
        self._cipher = cipher
        self._hasher = hasher

    def _sealed(
        self, account_id: UUID, renter_id: UUID, document: Document | None
    ) -> dict[str, object]:
        if document is None:
            return {"doc_type": None, "doc_enc": None, "doc_hmac": None, "doc_last4": None}
        context = field_context("renters", "doc_enc", account_id, renter_id)
        return {
            "doc_type": document.doc_type,
            "doc_enc": self._cipher.encrypt(document.number, context),
            "doc_hmac": self._hasher.digest(document.doc_type, document.number),
            "doc_last4": document.last4,
        }

    async def all(self) -> list[Renter]:
        return [renter(row) for row in await self._connection.execute(ALL_RENTERS)]

    async def holder_of(self, document: Document) -> UUID | None:
        digest = self._hasher.digest(document.doc_type, document.number)
        holder: UUID | None = (
            await self._connection.execute(HOLDER, {"doc_hmac": digest})
        ).scalar_one_or_none()
        return holder

    async def lock(self, renter_id: UUID) -> Renter | None:
        row = (await self._connection.execute(LOCK_RENTER, {"id": renter_id})).first()
        return None if row is None else renter(row)

    async def add(
        self, account_id: UUID, renter_id: UUID, details: RenterDetails, document: Document | None
    ) -> None:
        await self._connection.execute(
            ADD_RENTER,
            {
                "id": renter_id,
                "account_id": account_id,
                "full_name": details.full_name,
                "phone_e164": details.phone_e164,
                **self._sealed(account_id, renter_id, document),
            },
        )

    async def update(self, renter_id: UUID, details: RenterDetails) -> None:
        await self._connection.execute(
            UPDATE_RENTER,
            {"id": renter_id, "full_name": details.full_name, "phone_e164": details.phone_e164},
        )

    async def set_document(self, account_id: UUID, renter_id: UUID, document: Document) -> None:
        await self._connection.execute(
            SET_DOCUMENT, {"id": renter_id, **self._sealed(account_id, renter_id, document)}
        )
