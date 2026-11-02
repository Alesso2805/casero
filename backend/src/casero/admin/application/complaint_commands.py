from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal, Protocol
from uuid import UUID

from casero.admin.application.complaints import ComplaintRepository, new_complaint
from casero.admin.domain.complaint_emails import response_email
from casero.admin.domain.complaints import Complaint, ComplaintSheet
from casero.shared.kernel.clock import LIMA, Clock
from casero.shared.kernel.email import Email, MailDeliveryError

LETTER_SENT_AT = time(12)

ResponseOutcome = Literal[
    "responded", "not_found", "already_responded", "needs_sent_on", "email_failed"
]


class ComplaintResponses(Protocol):
    async def by_number(self, number: str) -> Complaint | None: ...

    async def record_response(self, complaint_id: UUID, response: str, at: datetime) -> bool:
        """False when the complaint already has a response."""
        ...


class ResponseMailer(Protocol):
    async def send(self, email: Email) -> None: ...


class StaffActions(Protocol):
    async def record(
        self,
        action: str,
        entity: str,
        entity_id: UUID,
        at: datetime,
        staff_id: UUID | None = None,
    ) -> None:
        """Without `staff_id`, the action came from a command rather than from the panel."""
        ...


@dataclass(frozen=True)
class RespondToComplaint:
    """Answers by the channel the consumer chose. A letter goes out by hand, so only its date
    is recorded; a failed email leaves the complaint unanswered, for the caller to roll back."""

    responses: ComplaintResponses
    mailer: ResponseMailer
    actions: StaffActions
    complaints_inbox: str
    clock: Clock

    async def __call__(self, number: str, text: str, sent_on: date | None) -> ResponseOutcome:
        complaint = await self.responses.by_number(number)
        if complaint is None:
            return "not_found"
        letter = complaint.sheet.response_channel == "letter"
        if letter and sent_on is None:
            return "needs_sent_on"
        now = self.clock.now()
        at = datetime.combine(sent_on, LETTER_SENT_AT, LIMA) if letter and sent_on else now
        if not await self.responses.record_response(complaint.id, text, at):
            return "already_responded"
        await self.actions.record("complaint.respond", "complaints", complaint.id, now)
        if not letter:
            try:
                await self.mailer.send(response_email(complaint, text, self.complaints_inbox))
            except MailDeliveryError:
                return "email_failed"
        return "responded"


@dataclass(frozen=True)
class RegisterComplaint:
    """A complaint that reached the inbox while the virtual book was down (docs/ops/complaints.md).

    Its number and deadline come from when it arrived, and the worker sends the copy as usual.
    """

    repository: ComplaintRepository
    actions: StaffActions
    clock: Clock

    async def __call__(self, sheet: ComplaintSheet, filed_at: datetime) -> Complaint:
        complaint = await new_complaint(self.repository, sheet, filed_at)
        await self.actions.record(
            "complaint.register", "complaints", complaint.id, self.clock.now()
        )
        return complaint
