import os
import re

import httpx2
import pytest

EDGE_URL = os.environ.get("CASERO_EDGE_URL", "")
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
SIX_MEGABYTES = 6 * 1024 * 1024

pytestmark = pytest.mark.skipif(not EDGE_URL, reason="needs CASERO_EDGE_URL of a running edge")


def get(path: str) -> httpx2.Response:
    return httpx2.get(f"{EDGE_URL}{path}", verify=False, follow_redirects=False)


def assert_security_headers(response: httpx2.Response) -> None:
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["strict-transport-security"] == "max-age=31536000"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "server" not in response.headers


def test_the_app_installs_and_its_worker_is_revalidated_and_caches_nothing() -> None:
    manifest = get("/manifest.webmanifest")
    worker = get("/sw.js")

    register = get("/registerSW.js")

    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.json()["start_url"] == "/app"
    # A missing file falls back to index.html with 200, so the type and body are what count.
    assert worker.headers["content-type"].startswith("text/javascript")
    assert "skipWaiting" in worker.text
    assert worker.headers["cache-control"] == "no-cache"
    assert "fetch" not in worker.text
    assert register.headers["content-type"].startswith("text/javascript")
    assert "serviceWorker" in register.text


def test_pages_send_the_security_headers() -> None:
    response = get("/")

    assert response.status_code == 200
    assert_security_headers(response)


def test_api_responses_send_the_security_headers() -> None:
    response = get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert_security_headers(response)


def test_index_is_revalidated_and_hashed_assets_are_cached_for_a_year() -> None:
    index = get("/")
    asset = re.search(r'src="(/assets/[^"]+\.js)"', index.text)

    assert index.headers["cache-control"] == "no-cache"
    assert asset is not None
    assert get(asset.group(1)).headers["cache-control"] == "public, max-age=31536000, immutable"


def test_app_routes_fall_back_to_the_index() -> None:
    response = get("/app/cobros")

    assert response.status_code == 200
    assert "<title>Casero</title>" in response.text


@pytest.mark.parametrize("path", ["/admin", "/admin/cuentas", "/api/admin/accounts"])
def test_admin_paths_are_not_served_publicly(path: str) -> None:
    assert get(path).status_code == 404


def test_plain_http_redirects_to_https() -> None:
    response = httpx2.get(EDGE_URL.replace("https://", "http://", 1), follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"].startswith("https://")


def test_request_bodies_over_5_mb_are_rejected() -> None:
    response = httpx2.post(f"{EDGE_URL}/api/health", content=b"x" * SIX_MEGABYTES, verify=False)

    assert response.status_code == 413


def test_the_edge_serves_the_business_identity_from_its_environment() -> None:
    response = get("/api/public/business")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "name": os.environ["CASERO_BUSINESS_NAME"],
        "ruc": os.environ["CASERO_BUSINESS_RUC"],
        "address": os.environ["CASERO_BUSINESS_ADDRESS"],
        "complaints_inbox": os.environ["CASERO_COMPLAINTS_INBOX"],
        "privacy_inbox": os.environ["CASERO_PRIVACY_INBOX"],
    }


@pytest.mark.parametrize(
    ("path", "indexed"),
    [
        ("/", True),
        ("/privacidad", False),
        ("/baja", False),
        ("/legal/terminos", False),
        ("/libro-de-reclamaciones", False),
        ("/api/health", False),
        ("/api/public/business", False),
    ],
)
def test_pages_with_the_business_address_are_kept_out_of_search_engines(
    path: str, indexed: bool
) -> None:
    assert ("x-robots-tag" not in get(path).headers) is indexed
    if not indexed:
        assert get(path).headers["x-robots-tag"] == "noindex"


def test_www_redirects_to_the_main_domain() -> None:
    host = EDGE_URL.removeprefix("https://")
    response = httpx2.get(
        f"{EDGE_URL}/privacidad",
        headers={"Host": f"www.{host}"},
        verify=False,
        follow_redirects=False,
    )

    assert response.status_code == 301
    assert response.headers["location"] == f"https://{host}/privacidad"
