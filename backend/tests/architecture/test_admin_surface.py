from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from starlette.routing import Route

from routes import api_routes, offline_admin_app, offline_app

REPOSITORY = Path(__file__).resolve().parents[3]
COMPOSE_FILES = ("docker-compose.yml", "infra/deploy/docker-compose.yml")
ADMIN_PORT = "8081"
ADMIN_PREFIXES = ("/api/admin", "/admin")


def paths(app: FastAPI) -> set[str]:
    declared = {route.path for route in api_routes(app.routes)}
    declared |= {route.path for route in app.routes if isinstance(route, Route)}
    return declared


def published_ports(compose_file: str) -> list[str]:
    compose = yaml.safe_load((REPOSITORY / compose_file).read_text(encoding="utf-8"))
    return [
        str(port) for service in compose["services"].values() for port in service.get("ports", [])
    ]


def test_ar22_the_public_app_mounts_nothing_of_the_panel() -> None:
    assert not [path for path in paths(offline_app()) if path.startswith(ADMIN_PREFIXES)]


def test_ar22_the_panel_mounts_nothing_else() -> None:
    declared = paths(offline_admin_app())

    assert declared
    assert not [path for path in declared if not path.startswith(ADMIN_PREFIXES)]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_ar22_the_panel_port_is_published_only_on_loopback(compose_file: str) -> None:
    panel = [port for port in published_ports(compose_file) if ADMIN_PORT in port]

    assert panel == [f"127.0.0.1:{ADMIN_PORT}:{ADMIN_PORT}"]


def test_ar22_production_keeps_the_panel_off_by_default() -> None:
    compose = yaml.safe_load(
        (REPOSITORY / "infra/deploy/docker-compose.yml").read_text(encoding="utf-8")
    )

    assert compose["services"]["api"]["environment"]["ADMIN_ENABLED"] == "${ADMIN_ENABLED:-false}"
