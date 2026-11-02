import hashlib
import secrets
from uuid import UUID

import pyotp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.admin.domain.staff import NewStaff
from casero.shared.infrastructure.crypto import FieldCipher

TOTP_ISSUER = "Casero"
RECOVERY_CODE_BYTES = 10
RECOVERY_CODE_GROUP = 5

INSERT_STAFF = text(
    "INSERT INTO staff_users"
    " (id, email, password_hash, totp_secret_enc, recovery_codes_hash, created_at)"
    " VALUES (:id, :email, :password_hash, :totp_secret_enc, :recovery_codes_hash, :created_at)"
    " ON CONFLICT (lower(email)) DO NOTHING RETURNING id"
)


def totp_secret_context(staff_id: UUID) -> str:
    """Staff belong to no account, so the secret is tied to its row alone (ADR-0007)."""
    return f"staff_users.totp_secret_enc:{staff_id}"


class SqlStaffDirectory:
    def __init__(self, connection: AsyncConnection, cipher: FieldCipher) -> None:
        self._connection = connection
        self._cipher = cipher

    async def add(self, staff: NewStaff) -> bool:
        created = await self._connection.execute(
            INSERT_STAFF,
            {
                "id": staff.id,
                "email": staff.email,
                "password_hash": staff.password_hash,
                "totp_secret_enc": self._cipher.encrypt(
                    staff.totp_secret, totp_secret_context(staff.id)
                ),
                "recovery_codes_hash": staff.recovery_code_hashes,
                "created_at": staff.created_at,
            },
        )
        return created.first() is not None


class PyotpSecondFactor:
    def new_secret(self) -> str:
        return pyotp.random_base32()

    def enrollment_uri(self, secret: str, email: str) -> str:
        return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=TOTP_ISSUER)


class HashedRecoveryCodes:
    """80 random bits per code, so a plain hash holds up where a password would need Argon2."""

    def new(self) -> tuple[str, str]:
        digits = secrets.token_hex(RECOVERY_CODE_BYTES)
        groups = range(0, len(digits), RECOVERY_CODE_GROUP)
        code = "-".join(digits[start : start + RECOVERY_CODE_GROUP] for start in groups)
        return code, self.hash(code)

    def hash(self, code: str) -> str:
        normalized = code.strip().lower().replace("-", "").replace(" ", "")
        return hashlib.sha256(normalized.encode()).hexdigest()
