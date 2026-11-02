from pathlib import Path

import pytest
import yaml
from fastapi import APIRouter, Depends, FastAPI
from starlette.routing import Route

from routes import (
    api_routes,
    dependency_names,
    documented_operations,
    offline_admin_app,
    offline_app,
    operations,
)

REPOSITORY = Path(__file__).resolve().parents[3]
COMPOSE_FILES = ("docker-compose.yml", "infra/deploy/docker-compose.yml")
ADMIN_PORT = "8081"
ADMIN_PREFIXES = ("/api/admin", "/admin")
PANEL_PREFIX = "/api/admin/"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# What a browser needs before it has a staff session (AR-23).
OPEN_ROUTES = frozenset(
    {
        ("GET", "/api/admin/health"),
        ("GET", "/api/admin/csrf"),
        ("POST", "/api/admin/session"),
    }
)


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


def routes_without_staff(app: FastAPI) -> list[str]:
    return sorted(
        f"{method} {path}"
        for (method, path), route in operations(app, PANEL_PREFIX).items()
        if (method, path) not in OPEN_ROUTES
        and "current_staff" not in dependency_names(route.dependant)
    )


def writes_without_csrf(app: FastAPI) -> list[str]:
    return sorted(
        f"{method} {path}"
        for (method, path), route in operations(app, PANEL_PREFIX).items()
        if method in UNSAFE_METHODS and "require_csrf" not in dependency_names(route.dependant)
    )


def test_ar23_every_panel_route_needs_a_staff_session() -> None:
    assert routes_without_staff(offline_admin_app()) == []


def test_ar23_every_panel_write_checks_the_csrf_token() -> None:
    assert writes_without_csrf(offline_admin_app()) == []


def test_ar23_the_open_routes_exist() -> None:
    assert set(operations(offline_admin_app(), PANEL_PREFIX)) >= OPEN_ROUTES


def test_ar23_the_checks_see_every_panel_route() -> None:
    app = offline_admin_app()

    assert documented_operations(app, PANEL_PREFIX) == set(operations(app, PANEL_PREFIX))


def test_ar23_meta_detects_an_open_route_and_an_unchecked_write_in_an_included_router() -> None:
    def require_csrf() -> None: ...

    def current_staff() -> None: ...

    router = APIRouter()

    @router.get("/api/admin/open")
    def open_route() -> None: ...

    @router.post("/api/admin/unchecked", dependencies=[Depends(current_staff)])
    def unchecked() -> None: ...

    @router.post("/api/admin/checked", dependencies=[Depends(current_staff), Depends(require_csrf)])
    def checked() -> None: ...

    app = FastAPI()
    app.include_router(router)

    assert routes_without_staff(app) == ["GET /api/admin/open"]
    assert writes_without_csrf(app) == ["POST /api/admin/unchecked"]
