from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from admin_client import admin_client
from casero.admin.api.protection import CONTENT_SECURITY_POLICY
from database import Database

pytestmark = pytest.mark.anyio

PAGE = "<!doctype html><title>Panel</title>"
SCRIPT = "console.log('panel');"


@pytest.fixture
def bundled(database: Database, tmp_path: Path) -> Iterator[TestClient]:
    bundle = tmp_path / "bundle"
    (bundle / "assets").mkdir(parents=True)
    (bundle / "admin.html").write_text(PAGE, encoding="utf-8")
    (bundle / "assets" / "main-abc123.js").write_text(SCRIPT, encoding="utf-8")
    (tmp_path / "outside.txt").write_text("private", encoding="utf-8")
    with admin_client(database, bundle_dir=bundle) as client:
        yield client


@pytest.mark.parametrize("path", ["/admin", "/admin/", "/admin/ingresar", "/admin/cuentas/123"])
async def test_every_page_of_the_panel_is_the_same_file(bundled: TestClient, path: str) -> None:
    answer = bundled.get(path)

    assert (answer.status_code, answer.text) == (200, PAGE)
    assert answer.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


async def test_the_assets_of_the_bundle_are_served(bundled: TestClient) -> None:
    answer = bundled.get("/admin/assets/main-abc123.js")

    assert (answer.status_code, answer.text) == (200, SCRIPT)
    assert answer.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


async def test_an_asset_that_does_not_exist_is_a_404_and_not_the_page(bundled: TestClient) -> None:
    assert bundled.get("/admin/assets/missing.js").status_code == 404


@pytest.mark.parametrize(
    "path", ["/admin/assets/../../outside.txt", "/admin/assets/%2e%2e/%2e%2e/outside.txt"]
)
async def test_nothing_outside_the_bundle_can_be_reached(bundled: TestClient, path: str) -> None:
    assert "private" not in bundled.get(path).text


async def test_an_unknown_api_route_stays_a_404(bundled: TestClient) -> None:
    assert bundled.get("/api/admin/nothing-here").status_code == 404


async def test_without_a_bundle_the_panel_is_only_its_api(database: Database) -> None:
    with admin_client(database) as client:
        assert client.get("/admin").status_code == 404
