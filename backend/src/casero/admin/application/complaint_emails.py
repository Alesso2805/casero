from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

import structlog

from casero.admin.domain.complaint_emails import (
    BusinessIdentity,
    CopyStatus,
    consumer_copy,
    inbox_notice,
)
from casero.admin.domain.complaints import Complaint
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.email import Email, MailDeliveryError

COPY_JOB = "complaint_copy"
NOTICE_JOB = "complaint_notice"
BATCH_SIZE = 20

log = structlog.get_logger()


@dataclass(frozen=True)
class PendingNotice:
    complaint: Complaint
    copy: CopyStatus


class ComplaintOutbox(Protocol):
    async def without_copy(self, limit: int) -> list[Complaint]: ...

    async def without_notice(self, limit: int) -> list[PendingNotice]: ...

    async def claim(self, job: str, complaint_id: UUID, now: datetime) -> bool: ...

    async def finish(
        self, job: str, complaint_id: UUID, now: datetime, error_code: str | None
    ) -> None: ...


class ComplaintMailer(Protocol):
    async def send(self, email: Email) -> None: ...


@dataclass(frozen=True)
class SendComplaintEmails:
    outbox: ComplaintOutbox
    mailer: ComplaintMailer
    clock: Clock
    business: BusinessIdentity

    async def __call__(self) -> None:
        for complaint in await self.outbox.without_copy(BATCH_SIZE):
            await self._send_once(COPY_JOB, complaint, consumer_copy(complaint, self.business))
        for pending in await self.outbox.without_notice(BATCH_SIZE):
            notice = inbox_notice(pending.complaint, self.business, pending.copy)
            await self._send_once(NOTICE_JOB, pending.complaint, notice)

    async def _send_once(self, job: str, complaint: Complaint, email: Email) -> None:
        if not await self.outbox.claim(job, complaint.id, self.clock.now()):
            return
        try:
            await self.mailer.send(email)
        except MailDeliveryError as error:
            log.warning("complaint_email.failed", job=job, complaint_id=str(complaint.id))
            await self.outbox.finish(job, complaint.id, self.clock.now(), error.code)
            return
        await self.outbox.finish(job, complaint.id, self.clock.now(), None)
