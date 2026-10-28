from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from casero.shared.infrastructure.database import create_engine
from casero.shared.infrastructure.logs import ErrorShield, drop_personal_fields

REPO = Path(__file__).resolve().parents[3]
PERSONAL_VALUE = "ana.quispe@example.com"


def failing_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ErrorShield)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(f"Key (email)=({PERSONAL_VALUE}) already exists.")

    @app.get("/fine")
    def fine() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_unhandled_errors_answer_500_and_log_only_their_type() -> None:
    with capture_logs() as logs, TestClient(failing_app()) as client:
        response = client.get("/boom")

    assert (response.status_code, response.json()) == (500, {"detail": "internal_error"})
    assert logs == [{"event": "api.unhandled_error", "error": "RuntimeError", "log_level": "error"}]
    assert PERSONAL_VALUE not in repr(logs)


def test_the_shield_leaves_normal_responses_alone() -> None:
    with TestClient(failing_app()) as client:
        assert client.get("/fine").json() == {"status": "ok"}


def test_personal_fields_are_dropped_from_log_events() -> None:
    event: dict[str, Any] = {"event": "x", "email": PERSONAL_VALUE, "token": "t", "job": "j"}

    assert drop_personal_fields(None, "info", event) == {"event": "x", "job": "j"}


def test_database_errors_do_not_quote_bound_parameters() -> None:
    engine = create_engine("postgresql+asyncpg://user:secret@localhost/casero")

    assert engine.sync_engine.hide_parameters


@pytest.mark.parametrize("compose", ["docker-compose.yml", "infra/deploy/docker-compose.yml"])
def test_postgres_logs_errors_without_their_details(compose: str) -> None:
    services = yaml.safe_load((REPO / compose).read_text(encoding="utf-8"))["services"]
    command = services["postgres"]["command"]

    assert "log_error_verbosity=terse" in command
    assert "log_min_error_statement=panic" in command
