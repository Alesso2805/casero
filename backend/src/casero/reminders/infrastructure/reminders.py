from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.reminders.application.reminders import Recipient
from casero.shared.kernel.ids import new_id
from casero.shared.kernel.periods import Period

RECIPIENT = text(
    "SELECT l.renter_id, r.full_name, r.phone_e164, l.tools_enabled FROM leases l"
    " JOIN renters r ON r.account_id = l.account_id AND r.id = l.renter_id"
    " WHERE l.id = :lease_id"
)
ADD_RENT_REMINDER = text(
    "INSERT INTO reminder_logs (id, account_id, kind, charge_id, renter_id, channel, created_at)"
    " VALUES (:id, :account_id, 'rent', :charge_id, :renter_id, 'whatsapp_link', :created_at)"
)

ADD_TAX_REMINDER = text(
    "INSERT INTO reminder_logs (id, account_id, kind, period, renter_id, renter_doc_hmac,"
    " channel, created_at) VALUES (:id, :account_id, 'tax_due', :period, :renter_id,"
    " :renter_doc_hmac, 'email', :created_at)"
)
TAX_REMINDED_SINCE = text(
    "SELECT EXISTS (SELECT 1 FROM reminder_logs WHERE kind = 'tax_due' AND period = :period"
    " AND created_at >= :since)"
)
LAST_RENT_REMINDERS = text(
    "SELECT c.lease_id, max(g.created_at) AS sent_at FROM reminder_logs g"
    " JOIN charges c ON c.account_id = g.account_id AND c.id = g.charge_id"
    " WHERE g.kind = 'rent' GROUP BY c.lease_id"
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

    async def add_tax_due(
        self,
        account_id: UUID,
        period: Period,
        renter_id: UUID,
        renter_doc_hmac: bytes | None,
        at: datetime,
    ) -> None:
        await self._connection.execute(
            ADD_TAX_REMINDER,
            {
                "id": new_id(),
                "account_id": account_id,
                "period": str(period),
                "renter_id": renter_id,
                "renter_doc_hmac": renter_doc_hmac,
                "created_at": at,
            },
        )

    async def reminded_since(self, period: Period, since: datetime) -> bool:
        sent: bool = (
            await self._connection.execute(
                TAX_REMINDED_SINCE, {"period": str(period), "since": since}
            )
        ).scalar_one()
        return sent

    async def last_rent_reminders(self) -> dict[UUID, datetime]:
        rows = await self._connection.execute(LAST_RENT_REMINDERS)
        return {row.lease_id: row.sent_at for row in rows}
