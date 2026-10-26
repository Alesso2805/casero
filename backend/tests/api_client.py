import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from casero.api import create_app
from casero.identity.application.account_emails import AccountMailer
from casero.identity.application.email_suppressions import SnsMessageVerifier
from casero.identity.application.sessions import Sleeper
from casero.shared.infrastructure.mail import SmtpSettings
from casero.shared.infrastructure.settings import ApiSettings, RegistrationMode
from casero.shared.kernel.clock import LIMA, Clock
from casero.shared.kernel.email import Email
from database import Database

TEST_EMAIL_HASH_KEY = b"test-email-hash-key"
TEST_TOPIC_ARN = "arn:aws:sns:us-east-1:000000000000:casero-test"
TEST_UNSUBSCRIBE_KEY = b"test-unsubscribe-key"
TEST_ACCEPTANCE_IP_KEY = b"test-acceptance-ip-key"


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def today_lima(self) -> date:
        return self._now.astimezone(LIMA).date()

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class RecordingMailer:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)


def address_for(name: str) -> str:
    return f"198.51.100.{zlib.crc32(name.encode()) % 250 + 1}"


@contextmanager
def api_client(
    database: Database,
    address: str,
    clock: Clock | None = None,
    sns_verifier: SnsMessageVerifier | None = None,
    sleeper: Sleeper | None = None,
    registration_mode: RegistrationMode = "closed",
    mailer: AccountMailer | None = None,
) -> Iterator[TestClient]:
    url = database.dsn("casero_app").replace("postgresql://", "postgresql+asyncpg://", 1)
    settings = ApiSettings(
        database_url=url,
        rate_limit_key=b"test-key",
        email_hash_key=TEST_EMAIL_HASH_KEY,
        ses_events_topic_arn=TEST_TOPIC_ARN,
        unsubscribe_key=TEST_UNSUBSCRIBE_KEY,
        acceptance_ip_key=TEST_ACCEPTANCE_IP_KEY,
        registration_mode=registration_mode,
        smtp=SmtpSettings("localhost", 25, "none", None, None, "Casero <no-reply@example.com>"),
        public_url="https://casero.example",
    )
    app = create_app(settings, clock, sns_verifier, sleeper, mailer or RecordingMailer())
    # https, because __Host- cookies are Secure and the client only sends them over https.
    with TestClient(app, base_url="https://testserver", client=(address, 50000)) as client:
        yield client
