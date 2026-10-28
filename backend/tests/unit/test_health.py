from fastapi.testclient import TestClient

from casero.api import create_app
from casero.shared.infrastructure.crypto import DocumentHasher, FieldCipher
from casero.shared.infrastructure.mail import SmtpSettings
from casero.shared.infrastructure.settings import ApiSettings

UNREACHABLE_DATABASE = ApiSettings(
    database_url="postgresql+asyncpg://unused@127.0.0.1:9/unused",
    rate_limit_key=b"unused",
    email_hash_key=b"unused",
    ses_events_topic_arn="arn:aws:sns:us-east-1:000000000000:unused",
    unsubscribe_key=b"unused",
    acceptance_ip_key=b"unused",
    registration_mode="closed",
    smtp=SmtpSettings("localhost", 25, "none", None, None, "Casero <no-reply@example.com>"),
    public_url="https://casero.example",
    field_cipher=FieldCipher({"test": bytes(32)}, "test"),
    document_hasher=DocumentHasher(bytes(range(32))),
)


def test_health_fails_when_the_database_does_not_answer() -> None:
    with TestClient(create_app(UNREACHABLE_DATABASE)) as client:
        response = client.get("/api/health")

    assert (response.status_code, response.json()) == (503, {"detail": "database_unavailable"})
