"""Compare the real Backblaze B2 buckets with docs/ops/storage-buckets.md.

Run with `make check-bucket-policy`. Needs the `audit` key (listBuckets, readBucketEncryption,
readBucketRetentions) in B2_AUDIT_KEY_ID and B2_AUDIT_APPLICATION_KEY, and CASERO_BUCKET_PREFIX.
"""

import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx2

B2_AUTHORIZE_URL = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"
HTTP_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class BucketPolicy:
    suffix: str
    days_to_hide: int | None
    days_to_delete: int
    lock_days: int | None


POLICIES = (
    BucketPolicy("vouchers", days_to_hide=None, days_to_delete=30, lock_days=None),
    BucketPolicy("backups", days_to_hide=30, days_to_delete=1, lock_days=30),
)


def _readable(setting: Any) -> dict[str, Any] | None:
    if not isinstance(setting, dict) or not setting.get("isClientAuthorizedToRead"):
        return None
    value = setting.get("value")
    return value if isinstance(value, dict) else {}


def violations(bucket: dict[str, Any], policy: BucketPolicy) -> list[str]:
    found = []
    if bucket.get("bucketType") != "allPrivate":
        found.append(f"no es privado (bucketType = {bucket.get('bucketType')})")
    if bucket.get("corsRules"):
        found.append("tiene reglas CORS")

    encryption = _readable(bucket.get("defaultServerSideEncryption"))
    if encryption is None:
        found.append("la clave no puede leer el cifrado (falta readBucketEncryption)")
    elif encryption.get("mode") != "SSE-B2":
        found.append(f"no tiene SSE-B2 (mode = {encryption.get('mode')})")

    rules = [
        (
            rule.get("fileNamePrefix"),
            rule.get("daysFromUploadingToHiding"),
            rule.get("daysFromHidingToDeleting"),
        )
        for rule in bucket.get("lifecycleRules") or []
    ]
    expected = [("", policy.days_to_hide, policy.days_to_delete)]
    if rules != expected:
        found.append(f"ciclo de vida {rules}, se esperaba {expected}")

    lock = _readable(bucket.get("fileLockConfiguration"))
    if lock is None:
        found.append("la clave no puede leer el bloqueo (falta readBucketRetentions)")
    elif policy.lock_days is None and lock.get("isFileLockEnabled"):
        found.append("tiene bloqueo de objetos y no debe tenerlo")
    elif policy.lock_days is not None:
        retention = lock.get("defaultRetention") or {}
        expected_retention = {
            "mode": "compliance",
            "period": {"duration": policy.lock_days, "unit": "days"},
        }
        if not lock.get("isFileLockEnabled"):
            found.append("no tiene bloqueo de objetos")
        elif retention != expected_retention:
            found.append(f"retención por defecto {retention}, se esperaba {expected_retention}")
    return found


def list_buckets(key_id: str, key: str, client: httpx2.Client) -> list[dict[str, Any]]:
    authorization = client.get(B2_AUTHORIZE_URL, auth=(key_id, key))
    authorization.raise_for_status()
    account = authorization.json()
    response = client.post(
        f"{account['apiUrl']}/b2api/v2/b2_list_buckets",
        headers={"Authorization": account["authorizationToken"]},
        json={"accountId": account["accountId"]},
    )
    response.raise_for_status()
    buckets: list[dict[str, Any]] = response.json()["buckets"]
    return buckets


def check(prefix: str, buckets: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_name = {bucket.get("bucketName"): bucket for bucket in buckets}
    report = {}
    for policy in POLICIES:
        name = f"{prefix}-{policy.suffix}"
        bucket = by_name.get(name)
        report[name] = violations(bucket, policy) if bucket else ["no existe"]
    return report


def main() -> int:
    env = os.environ
    with httpx2.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        buckets = list_buckets(env["B2_AUDIT_KEY_ID"], env["B2_AUDIT_APPLICATION_KEY"], client)
    report = check(env["CASERO_BUCKET_PREFIX"], buckets)
    for name, found in report.items():
        print(f"{name}: {'bien' if not found else 'NO cumple'}")
        for problem in found:
            print(f"  - {problem}")
    return 1 if any(report.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
