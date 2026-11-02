from pathlib import Path

import pytest
import yaml

from casero.api import admin_listener, listeners, public_listener
from casero.shared.infrastructure.settings import DEFAULT_ADMIN_PORT, AdminSettings
from routes import offline_admin_app, offline_app

REPOSITORY = Path(__file__).resolve().parents[3]
URL = "postgresql+asyncpg://casero_admin@localhost/casero"
PANEL_ENV = {
    "ADMIN_ENABLED": "true",
    "CASERO_ADMIN_DATABASE_URL": URL,
    "CASERO_ENCRYPTION_KEYS": "k1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "CASERO_ENCRYPTION_ACTIVE_KEY": "k1",
}


@pytest.mark.parametrize("env", [{}, {"ADMIN_ENABLED": "false"}, {"ADMIN_ENABLED": "TRUE"}])
def test_the_panel_is_off_unless_asked_for_exactly(env: dict[str, str]) -> None:
    assert AdminSettings.from_environment(env) is None


def test_the_panel_needs_its_own_database_role_when_on() -> None:
    with pytest.raises(KeyError, match="CASERO_ADMIN_DATABASE_URL"):
        AdminSettings.from_environment({"ADMIN_ENABLED": "true"})


def test_the_panel_needs_the_keys_to_open_the_totp_secrets() -> None:
    env = {"ADMIN_ENABLED": "true", "CASERO_ADMIN_DATABASE_URL": URL}

    with pytest.raises(KeyError, match="CASERO_ENCRYPTION_KEYS"):
        AdminSettings.from_environment(env)


def test_the_panel_uses_the_published_port_unless_told_otherwise() -> None:
    default = AdminSettings.from_environment(PANEL_ENV)
    moved = AdminSettings.from_environment({**PANEL_ENV, "CASERO_ADMIN_PORT": "9000"})

    assert default is not None
    assert moved is not None
    assert (default.database_url, default.port) == (URL, DEFAULT_ADMIN_PORT)
    assert moved.port == 9000


def test_with_the_panel_off_only_the_public_server_starts() -> None:
    assert [listener.config.port for listener in listeners(offline_app(), {})] == [8000]


def test_with_the_panel_on_both_servers_start() -> None:
    assert [listener.config.port for listener in listeners(offline_app(), PANEL_ENV)] == [
        8000,
        DEFAULT_ADMIN_PORT,
    ]


@pytest.mark.parametrize("compose", ["docker-compose.yml", "infra/deploy/docker-compose.yml"])
def test_the_api_starts_through_these_listeners(compose: str) -> None:
    services = yaml.safe_load((REPOSITORY / compose).read_text(encoding="utf-8"))["services"]

    assert services["api"]["command"] == ["python", "-m", "casero.api"]


def test_neither_server_logs_requests_so_no_ip_or_token_is_kept() -> None:
    public = public_listener(offline_app()).config
    admin = admin_listener(offline_admin_app(), DEFAULT_ADMIN_PORT).config

    assert (public.access_log, admin.access_log) == (False, False)


def test_only_the_public_server_trusts_forwarded_addresses() -> None:
    public = public_listener(offline_app()).config
    admin = admin_listener(offline_admin_app(), DEFAULT_ADMIN_PORT).config

    assert (public.proxy_headers, admin.proxy_headers) == (True, False)


def test_the_panel_does_not_announce_its_server() -> None:
    admin = admin_listener(offline_admin_app(), DEFAULT_ADMIN_PORT).config

    assert admin.server_header is False
