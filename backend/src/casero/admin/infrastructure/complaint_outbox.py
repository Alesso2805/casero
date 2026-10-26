from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from casero.admin.application.complaint_emails import COPY_JOB, NOTICE_JOB, PendingNotice
from casero.admin.domain.complaint_emails import CopyStatus
from casero.admin.domain.complaints import Complaint, ComplaintSheet, Guardian

WITHOUT_COPY = text(
    "SELECT c.* FROM complaints c"
    " WHERE c.email IS NOT NULL AND NOT EXISTS (SELECT 1 FROM job_runs j"
    " WHERE j.job = :job AND j.run_key = c.id::text AND j.account_id IS NULL)"
    " ORDER BY c.created_at, c.id LIMIT :limit"
)

WITHOUT_NOTICE = text(
    "SELECT c.*, cj.status AS copy_status, cj.error_code AS copy_error FROM complaints c"
    " LEFT JOIN job_runs cj ON cj.job = :copy_job AND cj.run_key = c.id::text"
    " AND cj.account_id IS NULL"
    " WHERE NOT EXISTS (SELECT 1 FROM job_runs j"
    " WHERE j.job = :job AND j.run_key = c.id::text AND j.account_id IS NULL)"
    " ORDER BY c.created_at, c.id LIMIT :limit"
)

BY_NUMBER = text("SELECT c.* FROM complaints c WHERE c.number = :number")

CLAIM = text(
    "INSERT INTO job_runs (job, run_key, account_id, status, attempts, started_at)"
    " VALUES (:job, :run_key, NULL, 'running', 1, :now)"
    " ON CONFLICT DO NOTHING"
)

FINISH = text(
    "UPDATE job_runs SET status = :status, finished_at = :now, error_code = :error_code"
    " WHERE job = :job AND run_key = :run_key AND account_id IS NULL"
)


def copy_status_from_row(row: Any) -> CopyStatus:
    if row.copy_status == "done":
        return CopyStatus("sent")
    if row.copy_status == "failed":
        return CopyStatus("failed", row.copy_error)
    if row.copy_status is None and row.email is None:
        return CopyStatus("no_email")
    return CopyStatus("unfinished")


def complaint_from_row(row: Any) -> Complaint:
    guardian = (
        Guardian(
            full_name=row.guardian_name,
            address=row.guardian_address,
            phone=row.guardian_phone,
            email=row.guardian_email,
        )
        if row.guardian_name
        else None
    )
    return Complaint(
        id=row.id,
        number=row.number,
        created_at=row.created_at,
        due_on=row.due_at,
        sheet=ComplaintSheet(
            full_name=row.full_name,
            document_type=row.document_type,
            document_number=row.document_number,
            address=row.address,
            email=row.email,
            phone=row.phone,
            guardian=guardian,
            item_kind=row.item_kind,
            claimed_amount_cents=row.claimed_amount_cents,
            item_description=row.item_description,
            kind=row.kind,
            detail=row.detail,
            request=row.request,
            response_channel=row.response_channel,
        ),
    )


class SqlComplaintOutbox:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def without_copy(self, limit: int) -> list[Complaint]:
        async with self._engine.connect() as connection:
            result = await connection.execute(WITHOUT_COPY, {"job": COPY_JOB, "limit": limit})
            return [complaint_from_row(row) for row in result]

    async def without_notice(self, limit: int) -> list[PendingNotice]:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                WITHOUT_NOTICE, {"job": NOTICE_JOB, "copy_job": COPY_JOB, "limit": limit}
            )
            return [
                PendingNotice(complaint_from_row(row), copy_status_from_row(row)) for row in result
            ]

    async def by_number(self, number: str) -> Complaint | None:
        async with self._engine.connect() as connection:
            row = (await connection.execute(BY_NUMBER, {"number": number})).first()
            return complaint_from_row(row) if row else None

    async def claim(self, job: str, complaint_id: UUID, now: datetime) -> bool:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                CLAIM, {"job": job, "run_key": str(complaint_id), "now": now}
            )
            return result.rowcount == 1

    async def finish(
        self, job: str, complaint_id: UUID, now: datetime, error_code: str | None
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                FINISH,
                {
                    "job": job,
                    "run_key": str(complaint_id),
                    "now": now,
                    "status": "failed" if error_code else "done",
                    "error_code": error_code,
                },
            )
