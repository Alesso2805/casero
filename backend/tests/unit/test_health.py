from fastapi.testclient import TestClient

from casero.api import create_app
from casero.shared.infrastructure.settings import ApiSettings, BusinessSettings

UNUSED_SETTINGS = ApiSettings(
    database_url="postgresql+asyncpg://unused@localhost/unused",
    rate_limit_key=b"unused",
    business=BusinessSettings(
        name="Negocio de Prueba", ruc="10000000001", address="Av. Ficticia 100, Lima"
    ),
)


def test_health_reports_ok() -> None:
    response = TestClient(create_app(UNUSED_SETTINGS)).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_business_identity_comes_from_the_settings() -> None:
    response = TestClient(create_app(UNUSED_SETTINGS)).get("/api/public/business")

    assert response.json() == {
        "name": "Negocio de Prueba",
        "ruc": "10000000001",
        "address": "Av. Ficticia 100, Lima",
    }
