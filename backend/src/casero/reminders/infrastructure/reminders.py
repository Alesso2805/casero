from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.reminders.application.reminders import Recipient
from casero.shared.kernel.ids import new_id

RECIPIENT = text(
    "SELECT l.renter_id, r.full_name, r.phone_e164, l.tools_enabled FROM leases l"
    " JOIN renters r ON r.account_id = l.account_id AND r.id = l.renter_id"
    " WHERE l.id = :lease_id"
)
ADD_RENT_REMINDER = text(
    "INSERT INTO reminder_logs (id, account_id, kind, charge_id, renter_id, channel, created_at)"
    " VALUES (:id, :account_id, 'rent', :charge_id, :renter_id, 'whatsapp_link', :created_at)"
)


class SqlRecipientStore:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def recipient(self, lease_id: UUID) -> Recipient | None:
        row = (await self._connection.execute(RECIPIENT, {"lease_id": lease_id})).first()
        if row is None:
            return None
        return Recipient(row.renter_id, row.full_name, row.phone_e164, row.tools_enabled)


class SqlReminderLog:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add_rent(
        self, account_id: UUID, charge_id: UUID, renter_id: UUID, at: datetime
    ) -> None:
        await self._connection.execute(
            ADD_RENT_REMINDER,
            {
                "id": new_id(),
                "account_id": account_id,
                "charge_id": charge_id,
                "renter_id": renter_id,
                "created_at": at,
            },
        )
