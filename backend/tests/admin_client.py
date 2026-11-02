from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import uuid7

import pyotp
from fastapi.testclient import TestClient

from api_client import TEST_FIELD_CIPHER
from casero.admin.application.staff import StaffEnrollment
from casero.api import create_admin_app
from casero.shared.infrastructure.csrf import CSRF_COOKIE, CSRF_HEADER
from casero.shared.infrastructure.settings import AdminSettings
from casero.shared.kernel.clock import Clock
from casero.worker import create_staff
from database import Database

STAFF_PASSWORD = "una-clave-larga-de-personal"


@contextmanager
def admin_client(database: Database, clock: Clock | None = None) -> Iterator[TestClient]:
    url = database.dsn("casero_admin").replace("postgresql://", "postgresql+asyncpg://", 1)
    app = create_admin_app(AdminSettings(url, TEST_FIELD_CIPHER), clock)
    with TestClient(app, base_url="https://localhost:8081") as client:
        yield client


async def a_staff_user(database: Database, clock: Clock) -> tuple[str, StaffEnrollment]:
    email = f"{uuid7()}@example.com"
    url = database.dsn("casero_owner").replace("postgresql://", "postgresql+asyncpg://", 1)
    enrollment = await create_staff(url, TEST_FIELD_CIPHER, clock, email, STAFF_PASSWORD)
    assert isinstance(enrollment, StaffEnrollment)
    return email, enrollment


def csrf_headers(client: TestClient) -> dict[str, str]:
    client.get("/api/admin/csrf")
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def code_at(enrollment: StaffEnrollment, moment: datetime) -> str:
    totp = pyotp.parse_uri(enrollment.totp_uri)
    assert isinstance(totp, pyotp.TOTP)
    return totp.at(moment)


def log_in(client: TestClient, email: str, code: str, password: str = STAFF_PASSWORD) -> int:
    answer = client.post(
        "/api/admin/session",
        json={"email": email, "password": password, "code": code},
        headers=csrf_headers(client),
    )
    return answer.status_code
