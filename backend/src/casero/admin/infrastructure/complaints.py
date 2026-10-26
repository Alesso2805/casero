from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.admin.domain.complaints import Complaint

NEXT_SEQUENCE = text(
    "INSERT INTO complaint_counters (year, last_number) VALUES (:year, 1)"
    " ON CONFLICT (year) DO UPDATE SET last_number = complaint_counters.last_number + 1"
    " RETURNING last_number"
)

HOLIDAYS_AFTER = text("SELECT date FROM holidays WHERE date > :day")

INSERT = text(
    "INSERT INTO complaints (id, number, created_at, full_name, document_type, document_number,"
    " address, email, phone, guardian_name, guardian_address, guardian_phone, guardian_email,"
    " item_kind, claimed_amount_cents, item_description, kind, detail, request,"
    " response_channel, due_at)"
    " VALUES (:id, :number, :created_at, :full_name, :document_type, :document_number,"
    " :address, :email, :phone, :guardian_name, :guardian_address, :guardian_phone,"
    " :guardian_email, :item_kind, :claimed_amount_cents, :item_description, :kind, :detail,"
    " :request, :response_channel, :due_at)"
)


class SqlComplaintRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def next_sequence(self, year: int) -> int:
        result = await self._connection.execute(NEXT_SEQUENCE, {"year": year})
        return int(result.scalar_one())

    async def holidays_after(self, day: date) -> frozenset[date]:
        result = await self._connection.execute(HOLIDAYS_AFTER, {"day": day})
        return frozenset(result.scalars())

    async def add(self, complaint: Complaint) -> None:
        sheet = complaint.sheet
        guardian = sheet.guardian
        await self._connection.execute(
            INSERT,
            {
                "id": complaint.id,
                "number": complaint.number,
                "created_at": complaint.created_at,
                "full_name": sheet.full_name,
                "document_type": sheet.document_type,
                "document_number": sheet.document_number,
                "address": sheet.address,
                "email": sheet.email,
                "phone": sheet.phone,
                "guardian_name": guardian.full_name if guardian else None,
                "guardian_address": guardian.address if guardian else None,
                "guardian_phone": guardian.phone if guardian else None,
                "guardian_email": guardian.email if guardian else None,
                "item_kind": sheet.item_kind,
                "claimed_amount_cents": sheet.claimed_amount_cents,
                "item_description": sheet.item_description,
                "kind": sheet.kind,
                "detail": sheet.detail,
                "request": sheet.request,
                "response_channel": sheet.response_channel,
                "due_at": complaint.due_on,
            },
        )
