from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid7

import pytest

from casero.admin.application.complaint_emails import (
    COPY_JOB,
    NOTICE_JOB,
    PendingNotice,
    SendComplaintEmails,
)
from casero.admin.domain.complaint_emails import (
    NOTICES,
    BusinessIdentity,
    CopyStatus,
    consumer_copy,
    inbox_notice,
)
from casero.admin.domain.complaints import Complaint, ComplaintSheet, Guardian
from casero.shared.kernel.email import Email, MailDeliveryError
from casero.shared.kernel.money import format_soles

NOW = datetime(2026, 10, 23, 15, 5, tzinfo=UTC)
BUSINESS = BusinessIdentity(
    name="Negocio de Prueba",
    ruc="10000000001",
    address="Av. Ficticia 100, Lima",
    complaints_inbox="reclamos@example.com",
)
SHEET = ComplaintSheet(
    full_name="Ana Quispe Mamani",
    document_type="dni",
    document_number="12345678",
    address="Jr. Los Pinos 123, Arequipa",
    email="ana@example.com",
    phone=None,
    guardian=Guardian("Rosa Mamani", None, "+51 999 111 222", None),
    item_kind="service",
    claimed_amount_cents=1900,
    item_description="Plan Casero mensual",
    kind="claim",
    detail="Me cobraron dos veces la suscripción.",
    request="Que me devuelvan el cobro repetido.",
    response_channel="email",
)
COMPLAINT = Complaint(uuid7(), "000000007-2026", NOW, date(2026, 11, 13), SHEET)


@pytest.mark.parametrize(
    ("cents", "text"),
    [(0, "S/ 0.00"), (1900, "S/ 19.00"), (275_000, "S/ 2,750.00"), (-5, "-S/ 0.05")],
)
def test_soles_are_formatted_for_peru(cents: int, text: str) -> None:
    assert format_soles(cents) == text


def test_the_copy_reproduces_the_sheet_for_the_consumer() -> None:
    email = consumer_copy(COMPLAINT, BUSINESS)

    assert email.to == "ana@example.com"
    assert email.reply_to == "reclamos@example.com"
    assert email.subject == "Copia de tu reclamo N.° 000000007-2026"
    for expected in (
        "HOJA DE RECLAMACIÓN N.° 000000007-2026",
        "Fecha y hora de presentación: 23/10/2026 10:05 (hora de Lima)",
        "Proveedor: Negocio de Prueba, RUC 10000000001",
        "DNI: 12345678",
        "Padre, madre o representante: Rosa Mamani",
        "Su teléfono: +51 999 111 222",
        "Monto reclamado: S/ 19.00",
        "Tipo: Reclamo",
        "Pedido: Que me devuelvan el cobro repetido.",
        "a más tardar el 13/11/2026",
        *NOTICES,
    ):
        assert expected in email.text


def test_the_copy_shows_empty_optional_fields() -> None:
    sheet = replace(SHEET, guardian=None, claimed_amount_cents=None, request=None)

    text = consumer_copy(replace(COMPLAINT, sheet=sheet), BUSINESS).text

    assert "Padre, madre o representante" not in text
    assert "Monto reclamado: —" in text
    assert "Pedido: —" in text


def test_a_letter_only_complaint_has_no_copy() -> None:
    sheet = replace(SHEET, email=None, response_channel="letter")

    with pytest.raises(ValueError, match="email"):
        consumer_copy(replace(COMPLAINT, sheet=sheet), BUSINESS)


def test_the_inbox_notice_carries_no_personal_data() -> None:
    email = inbox_notice(COMPLAINT, BUSINESS, CopyStatus("sent"))

    assert email.to == "reclamos@example.com"
    assert email.subject == "Reclamo N.° 000000007-2026: responder antes del 13/11/2026"
    for personal in ("Ana", "12345678", "ana@example.com", "Arequipa", "Rosa", "cobraron"):
        assert personal not in email.subject + email.text


@pytest.mark.parametrize(
    ("status", "line"),
    [
        (CopyStatus("sent"), "Copia al consumidor: enviada."),
        (
            CopyStatus("failed", "SMTPRecipientsRefused"),
            "Copia al consumidor: no se pudo enviar (SMTPRecipientsRefused)."
            " Envíala tú desde este correo.",
        ),
        (CopyStatus("no_email"), "Copia al consumidor: no dejó correo; responde por carta."),
        (CopyStatus("unfinished"), "Copia al consumidor: el envío no terminó."),
    ],
)
def test_the_inbox_notice_reports_the_copy(status: CopyStatus, line: str) -> None:
    assert line in inbox_notice(COMPLAINT, BUSINESS, status).text


class FixedClock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> date:
        return date(2026, 10, 23)


class MemoryOutbox:
    def __init__(self, complaints: list[Complaint]) -> None:
        self.complaints = complaints
        self.runs: dict[tuple[str, UUID], str | None] = {}
        self.events: list[str] = []

    async def without_copy(self, limit: int) -> list[Complaint]:
        return [c for c in self.complaints if c.sheet.email and (COPY_JOB, c.id) not in self.runs]

    async def without_notice(self, limit: int) -> list[PendingNotice]:
        return [
            PendingNotice(c, self.copy_status(c))
            for c in self.complaints
            if (NOTICE_JOB, c.id) not in self.runs
        ]

    def copy_status(self, complaint: Complaint) -> CopyStatus:
        run = self.runs.get((COPY_JOB, complaint.id))
        if run is None:
            return CopyStatus("no_email" if complaint.sheet.email is None else "unfinished")
        if run == "done":
            return CopyStatus("sent")
        if run == "running":
            return CopyStatus("unfinished")
        return CopyStatus("failed", run)

    async def claim(self, job: str, complaint_id: UUID, now: datetime) -> bool:
        if (job, complaint_id) in self.runs:
            return False
        self.runs[job, complaint_id] = "running"
        self.events.append(f"claim {job}")
        return True

    async def finish(
        self, job: str, complaint_id: UUID, now: datetime, error_code: str | None
    ) -> None:
        self.runs[job, complaint_id] = error_code or "done"


class Mailer:
    def __init__(self, outbox: MemoryOutbox, failing: frozenset[str] = frozenset()) -> None:
        self.outbox = outbox
        self.failing = failing
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.outbox.events.append(f"send {email.to}")
        if email.to in self.failing:
            raise MailDeliveryError("SMTPRecipientsRefused")
        self.sent.append(email)


@pytest.mark.anyio
async def test_each_email_is_claimed_before_it_is_sent_and_sent_once() -> None:
    outbox = MemoryOutbox([COMPLAINT])
    mailer = Mailer(outbox)
    send = SendComplaintEmails(outbox, mailer, FixedClock(), BUSINESS)

    await send()
    await send()

    assert [email.to for email in mailer.sent] == ["ana@example.com", "reclamos@example.com"]
    assert outbox.events == [
        f"claim {COPY_JOB}",
        "send ana@example.com",
        f"claim {NOTICE_JOB}",
        "send reclamos@example.com",
    ]
    assert set(outbox.runs.values()) == {"done"}
    assert "Copia al consumidor: enviada." in mailer.sent[1].text


@pytest.mark.anyio
async def test_a_failed_copy_is_recorded_reported_and_not_retried() -> None:
    outbox = MemoryOutbox([COMPLAINT])
    mailer = Mailer(outbox, failing=frozenset({"ana@example.com"}))
    send = SendComplaintEmails(outbox, mailer, FixedClock(), BUSINESS)

    await send()
    mailer.failing = frozenset()
    await send()

    [notice] = mailer.sent
    assert notice.to == "reclamos@example.com"
    assert "no se pudo enviar (SMTPRecipientsRefused)" in notice.text
    assert outbox.runs[COPY_JOB, COMPLAINT.id] == "SMTPRecipientsRefused"
