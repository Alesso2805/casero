from fastapi.testclient import TestClient

from casero.api import create_app
from casero.shared.infrastructure.settings import ApiSettings

UNUSED_SETTINGS = ApiSettings(
    database_url="postgresql+asyncpg://unused@localhost/unused",
    rate_limit_key=b"unused",
    email_hash_key=b"unused",
    ses_events_topic_arn="arn:aws:sns:us-east-1:000000000000:unused",
    unsubscribe_key=b"unused",
)


def test_health_reports_ok() -> None:
    response = TestClient(create_app(UNUSED_SETTINGS)).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
