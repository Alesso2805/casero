from collections.abc import Callable, Iterable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI

from routes import dependency_names, documented_operations, offline_app, operations

# Session-level routes that must keep working before an account is usable (AR-20).
SESSION_ONLY_ROUTES = frozenset(
    {
        ("GET", "/api/app/me"),
        ("DELETE", "/api/app/session"),
        ("DELETE", "/api/app/sessions"),
        ("POST", "/api/app/email-verification"),
    }
)


UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ACCOUNT_PREFIX = "/api/app/"


def routes_without_account(app: FastAPI, allowed: Iterable[tuple[str, str]]) -> list[str]:
    allowed = set(allowed)
    return sorted(
        f"{method} {path}"
        for (method, path), route in operations(app, ACCOUNT_PREFIX).items()
        if (method, path) not in allowed
        and "current_account" not in dependency_names(route.dependant)
    )


def writes_without_csrf(app: FastAPI) -> list[str]:
    return sorted(
        f"{method} {path}"
        for (method, path), route in operations(app, ACCOUNT_PREFIX).items()
        if method in UNSAFE_METHODS and "require_csrf" not in dependency_names(route.dependant)
    )


def test_ar20_every_account_route_runs_in_the_account_context() -> None:
    assert routes_without_account(offline_app(), SESSION_ONLY_ROUTES) == []


def test_ar20_every_account_write_checks_the_csrf_token() -> None:
    assert writes_without_csrf(offline_app()) == []


def test_ar20_the_checks_see_every_documented_account_route() -> None:
    app = offline_app()
    documented = documented_operations(app, ACCOUNT_PREFIX)

    assert documented
    assert documented <= set(operations(app, ACCOUNT_PREFIX))


def test_ar20_meta_detects_unscoped_routes_and_unchecked_writes_in_included_routers() -> None:
    app = FastAPI()
    router = APIRouter()

    async def current_account() -> str:
        return "account"

    async def require_csrf() -> None:
        return None

    async def scoped(_: Annotated[str, Depends(current_account)]) -> None:
        return None

    async def unscoped() -> None:
        return None

    route: Callable[..., Any]
    for path, route in (("/api/app/scoped", scoped), ("/api/app/leaky", unscoped)):
        router.get(path)(route)
    router.post("/api/app/unchecked")(scoped)
    router.post("/api/app/checked", dependencies=[Depends(require_csrf)])(scoped)
    app.include_router(router)

    assert routes_without_account(app, set()) == ["GET /api/app/leaky"]
    assert writes_without_csrf(app) == ["POST /api/app/unchecked"]
