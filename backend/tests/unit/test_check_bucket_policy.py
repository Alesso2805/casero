import copy
import json
from typing import Any

import httpx2
import pytest

from check_bucket_policy import POLICIES, check, list_buckets, violations

VOUCHERS, BACKUPS = POLICIES


def bucket(name: str, lifecycle: dict[str, Any], lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "bucketName": name,
        "bucketType": "allPrivate",
        "corsRules": [],
        "defaultServerSideEncryption": {
            "isClientAuthorizedToRead": True,
            "value": {"algorithm": "AES256", "mode": "SSE-B2"},
        },
        "lifecycleRules": [{"fileNamePrefix": "", **lifecycle}],
        "fileLockConfiguration": {"isClientAuthorizedToRead": True, "value": lock},
    }


GOOD_VOUCHERS = bucket(
    "casero-vouchers",
    {"daysFromUploadingToHiding": None, "daysFromHidingToDeleting": 30},
    {"isFileLockEnabled": False, "defaultRetention": {"mode": None}},
)
GOOD_BACKUPS = bucket(
    "casero-backups",
    {"daysFromUploadingToHiding": 30, "daysFromHidingToDeleting": 1},
    {
        "isFileLockEnabled": True,
        "defaultRetention": {"mode": "compliance", "period": {"duration": 30, "unit": "days"}},
    },
)


def test_buckets_set_up_as_documented_pass() -> None:
    assert check("casero", [GOOD_VOUCHERS, GOOD_BACKUPS]) == {
        "casero-vouchers": [],
        "casero-backups": [],
    }


def test_a_missing_bucket_is_reported() -> None:
    assert check("casero", [GOOD_VOUCHERS])["casero-backups"] == ["no existe"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"bucketType": "allPublic"}, "no es privado"),
        ({"corsRules": [{"corsRuleName": "x"}]}, "CORS"),
        (
            {
                "defaultServerSideEncryption": {
                    "isClientAuthorizedToRead": True,
                    "value": {"mode": None},
                }
            },
            "SSE-B2",
        ),
        (
            {"defaultServerSideEncryption": {"isClientAuthorizedToRead": False}},
            "readBucketEncryption",
        ),
        ({"lifecycleRules": []}, "ciclo de vida"),
        (
            {
                "fileLockConfiguration": {
                    "isClientAuthorizedToRead": True,
                    "value": {"isFileLockEnabled": True},
                }
            },
            "no debe tenerlo",
        ),
    ],
)
def test_vouchers_deviations_are_reported(change: dict[str, Any], problem: str) -> None:
    [found] = violations({**GOOD_VOUCHERS, **change}, VOUCHERS)

    assert problem in found


@pytest.mark.parametrize(
    ("retention", "problem"),
    [
        ({"mode": "governance", "period": {"duration": 30, "unit": "days"}}, "retención"),
        ({"mode": "compliance", "period": {"duration": 1, "unit": "days"}}, "retención"),
    ],
)
def test_backups_need_thirty_days_in_compliance(retention: dict[str, Any], problem: str) -> None:
    changed = copy.deepcopy(GOOD_BACKUPS)
    changed["fileLockConfiguration"]["value"]["defaultRetention"] = retention

    [found] = violations(changed, BACKUPS)

    assert problem in found


def test_backups_without_lock_are_reported() -> None:
    changed = copy.deepcopy(GOOD_BACKUPS)
    changed["fileLockConfiguration"]["value"] = {"isFileLockEnabled": False}

    assert violations(changed, BACKUPS) == ["no tiene bloqueo de objetos"]


def test_buckets_are_listed_with_the_authorized_account() -> None:
    seen: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path.endswith("b2_authorize_account"):
            return httpx2.Response(
                200,
                json={
                    "accountId": "acc",
                    "authorizationToken": "token",
                    "apiUrl": "https://api005.backblazeb2.com",
                },
            )
        return httpx2.Response(200, json={"buckets": [GOOD_VOUCHERS]})

    with httpx2.Client(transport=httpx2.MockTransport(handle)) as client:
        assert list_buckets("key-id", "key", client) == [GOOD_VOUCHERS]

    listing = seen[1]
    assert str(listing.url) == "https://api005.backblazeb2.com/b2api/v2/b2_list_buckets"
    assert listing.headers["authorization"] == "token"
    assert json.loads(listing.content) == {"accountId": "acc"}
