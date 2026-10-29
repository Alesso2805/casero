from collections.abc import Iterable, Iterator

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from casero.api import create_app
from casero.shared.infrastructure.crypto import DocumentHasher, FieldCipher, HmacKeyring
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
    tenant_link_keys=HmacKeyring({"test": bytes(range(32))}, "test"),
)

HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def offline_app() -> FastAPI:
    """The real app, built without a database or mail server to inspect its routes."""
    return create_app(SETTINGS)


def api_routes(routes: Iterable[BaseRoute]) -> Iterator[APIRoute]:
    """Every APIRoute, including those of included routers.

    FastAPI 0.162 keeps each included router wrapped in `app.routes` (`original_router`), so
    looking only at `app.routes` misses all of them.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from api_routes(included.routes)


def dependencies(dependant: Dependant) -> Iterator[Dependant]:
    for dependency in dependant.dependencies:
        yield dependency
        yield from dependencies(dependency)


def dependency_names(dependant: Dependant) -> set[str]:
    return {getattr(d.call, "__name__", "") for d in dependencies(dependant) if d.call is not None}


def operations(app: FastAPI, prefix: str) -> dict[tuple[str, str], APIRoute]:
    return {
        (method, route.path): route
        for route in api_routes(app.routes)
        if route.path.startswith(prefix)
        for method in route.methods or ()
    }


def documented_operations(app: FastAPI, prefix: str) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        if path.startswith(prefix)
        for method in item
        if method.upper() in HTTP_METHODS
    }
