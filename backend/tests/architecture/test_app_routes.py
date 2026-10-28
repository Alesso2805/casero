from collections.abc import Callable, Iterable
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from casero.api import create_app
from casero.shared.infrastructure.crypto import DocumentHasher, FieldCipher
from casero.shared.infrastructure.mail import SmtpSettings
from casero.shared.infrastructure.settings import ApiSettings

SETTINGS = ApiSettings(
    database_url="postgresql+asyncpg://unused@localhost/unused",
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

# Session-level routes that must keep working before an account is usable (AR-20).
SESSION_ONLY_ROUTES = frozenset(
    {
        ("GET", "/api/app/me"),
        ("DELETE", "/api/app/session"),
        ("DELETE", "/api/app/sessions"),
        ("POST", "/api/app/email-verification"),
    }
)


def dependency_names(dependant: Dependant) -> set[str]:
    names = set()
    for dependency in dependant.dependencies:
        if dependency.call is not None:
            names.add(getattr(dependency.call, "__name__", ""))
        names |= dependency_names(dependency)
    return names


def routes_without_account(app: FastAPI, allowed: Iterable[tuple[str, str]]) -> list[str]:
    allowed = set(allowed)
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/app/"):
            continue
        for method in sorted(route.methods or ()):
            if (method, route.path) in allowed:
                continue
            if "current_account" not in dependency_names(route.dependant):
                missing.append(f"{method} {route.path}")
    return missing


def test_ar20_every_account_route_runs_in_the_account_context() -> None:
    assert routes_without_account(create_app(SETTINGS), SESSION_ONLY_ROUTES) == []


def test_ar20_meta_detects_a_route_without_the_account_context() -> None:
    app = FastAPI()

    async def current_account() -> str:
        return "account"

    async def scoped(_: Annotated[str, Depends(current_account)]) -> None:
        return None

    async def unscoped() -> None:
        return None

    route: Callable[..., Any]
    for path, route in (("/api/app/scoped", scoped), ("/api/app/leaky", unscoped)):
        app.get(path)(route)

    assert routes_without_account(app, set()) == ["GET /api/app/leaky"]
