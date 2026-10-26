import time
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import asyncpg
import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.core.container import DockerContainer

from api_client import TEST_EMAIL_HASH_KEY, FixedClock, address_for, api_client
from casero.admin.application.complaint_emails import COPY_JOB, NOTICE_JOB, SendComplaintEmails
from casero.admin.domain.complaint_emails import BusinessIdentity
from casero.admin.infrastructure.complaint_outbox import SqlComplaintOutbox
from casero.identity.infrastructure.email_suppressions import SuppressionLookup
from casero.shared.infrastructure.database import create_engine
from casero.shared.infrastructure.mail import SmtpMailer, SmtpSettings
from casero.worker import complaint_copy_text
from database import Database

pytestmark = pytest.mark.anyio

MAILPIT_IMAGE = "axllent/mailpit:v1.32.0"
READY_TIMEOUT_SECONDS = 30
NOW = datetime(2030, 3, 4, 15, 0, tzinfo=UTC)
BUSINESS = BusinessIdentity(
    name="Negocio de Prueba",
    ruc="10000000001",
    address="Av. Ficticia 100, Lima",
    complaints_inbox="reclamos@example.com",
)


def no_suppressions(engine: AsyncEngine) -> SuppressionLookup:
    return SuppressionLookup(engine, TEST_EMAIL_HASH_KEY)


class Mailpit:
    def __init__(self, host: str, smtp_port: int, api_port: int) -> None:
        self.smtp = SmtpSettings(
            host=host,
            port=smtp_port,
            security="none",
            username=None,
            password=None,
            sender="Casero <no-reply@example.com>",
        )
        self.api = f"http://{host}:{api_port}/api/v1"

    def messages_to(self, address: str) -> list[dict[str, Any]]:
        response = httpx2.get(f"{self.api}/search", params={"query": f"to:{address}"})
        response.raise_for_status()
        messages: list[dict[str, Any]] = response.json()["messages"]
        return messages

    def notice_text(self, number: str) -> str:
        [notice] = [
            message
            for message in self.messages_to(BUSINESS.complaints_inbox)
            if number in message["Subject"]
        ]
        response = httpx2.get(f"{self.api}/message/{notice['ID']}")
        response.raise_for_status()
        text: str = response.json()["Text"]
        return text


@pytest.fixture(scope="module")
def mailpit() -> Iterator[Mailpit]:
    with DockerContainer(MAILPIT_IMAGE).with_exposed_ports(1025, 8025) as container:
        server = Mailpit(
            container.get_container_host_ip(),
            int(container.get_exposed_port(1025)),
            int(container.get_exposed_port(8025)),
        )
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        while True:
            try:
                httpx2.get(f"{server.api}/messages").raise_for_status()
                break
            except httpx2.HTTPError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        yield server


@pytest.fixture
async def worker_engine(database: Database) -> AsyncIterator[AsyncEngine]:
    url = database.dsn("casero_worker").replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_engine(url)
    try:
        yield engine
    finally:
        await engine.dispose()


def file_complaint(database: Database, name: str, email: str | None) -> str:
    body = {
        "full_name": "Ana Quispe Mamani",
        "document_type": "dni",
        "document_number": "12345678",
        "email": email,
        "address": None if email else "Jr. Los Pinos 123, Arequipa",
        "item_kind": "service",
        "kind": "claim",
        "detail": "Me cobraron dos veces la suscripción.",
        "response_channel": "email" if email else "letter",
    }
    with api_client(database, address_for(name), FixedClock(NOW)) as client:
        response = client.post("/api/public/complaints", json=body)
    assert response.status_code == 201
    number: str = response.json()["number"]
    return number


async def job_runs(database: Database, number: str) -> dict[str, tuple[str, str | None]]:
    owner = await asyncpg.connect(database.dsn("casero_owner"))
    try:
        rows = await owner.fetch(
            "SELECT j.job, j.status, j.error_code FROM job_runs j"
            " JOIN complaints c ON j.run_key = c.id::text WHERE c.number = $1",
            number,
        )
        return {row["job"]: (row["status"], row["error_code"]) for row in rows}
    finally:
        await owner.close()


async def test_the_worker_sends_the_copy_and_the_notice_once(
    database: Database,
    mailpit: Mailpit,
    worker_engine: AsyncEngine,
    request: pytest.FixtureRequest,
) -> None:
    consumer = f"{uuid7()}@example.com"
    number = file_complaint(database, request.node.name, consumer)
    letter_only = file_complaint(database, request.node.name, None)
    clock = FixedClock(NOW)
    send = SendComplaintEmails(
        SqlComplaintOutbox(worker_engine),
        SmtpMailer(mailpit.smtp, clock),
        no_suppressions(worker_engine),
        clock,
        BUSINESS,
    )

    await send()
    await send()

    [copy] = mailpit.messages_to(consumer)
    assert copy["Subject"] == f"Copia de tu reclamo N.° {number}"
    assert copy["ReplyTo"][0]["Address"] == "reclamos@example.com"
    assert "Copia al consumidor: enviada." in mailpit.notice_text(number)
    assert "no dejó correo; responde por carta" in mailpit.notice_text(letter_only)
    assert await job_runs(database, number) == {
        COPY_JOB: ("done", None),
        NOTICE_JOB: ("done", None),
    }
    assert await job_runs(database, letter_only) == {NOTICE_JOB: ("done", None)}


async def test_the_owner_can_print_the_exact_copy_to_send_by_hand(
    database: Database, worker_engine: AsyncEngine, request: pytest.FixtureRequest
) -> None:
    consumer = f"{uuid7()}@example.com"
    number = file_complaint(database, request.node.name, consumer)

    text = await complaint_copy_text(worker_engine, number, BUSINESS)

    assert text is not None
    assert text.startswith(f"Para: {consumer}\nAsunto: Copia de tu reclamo N.° {number}")
    assert f"HOJA DE RECLAMACIÓN N.° {number}" in text
    assert await complaint_copy_text(worker_engine, "999999999-2030", BUSINESS) is None


async def test_an_unreachable_server_marks_the_emails_failed_without_retrying(
    database: Database,
    mailpit: Mailpit,
    worker_engine: AsyncEngine,
    request: pytest.FixtureRequest,
) -> None:
    consumer = f"{uuid7()}@example.com"
    number = file_complaint(database, request.node.name, consumer)
    clock = FixedClock(NOW)
    outbox = SqlComplaintOutbox(worker_engine)
    unreachable = SmtpSettings(
        host="127.0.0.1",
        port=9,
        security="none",
        username=None,
        password=None,
        sender="Casero <no-reply@example.com>",
    )

    await SendComplaintEmails(
        outbox, SmtpMailer(unreachable, clock), no_suppressions(worker_engine), clock, BUSINESS
    )()
    await SendComplaintEmails(
        outbox, SmtpMailer(mailpit.smtp, clock), no_suppressions(worker_engine), clock, BUSINESS
    )()

    runs = await job_runs(database, number)
    assert {status for status, _ in runs.values()} == {"failed"}
    assert all(code for _, code in runs.values())
    assert mailpit.messages_to(consumer) == []
