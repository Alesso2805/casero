import hashlib
import secrets
from datetime import datetime
from uuid import UUID

import pyotp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.admin.application.staff_sessions import StaffCredentials
from casero.admin.domain.staff import NewStaff, StaffSession
from casero.shared.infrastructure.crypto import FieldCipher

TOTP_ISSUER = "Casero"
RECOVERY_CODE_BYTES = 10
RECOVERY_CODE_GROUP = 5
# RFC 6238 step before and after, so a clock slightly off doesn't lock the owner out (ADR-0008).
TOTP_TOLERANCE_STEPS = 1

INSERT_STAFF = text(
    "INSERT INTO staff_users"
    " (id, email, password_hash, totp_secret_enc, recovery_codes_hash, created_at)"
    " VALUES (:id, :email, :password_hash, :totp_secret_enc, :recovery_codes_hash, :created_at)"
    " ON CONFLICT (lower(email)) DO NOTHING RETURNING id"
)
CREDENTIALS = text(
    "SELECT id, password_hash, totp_secret_enc FROM staff_users"
    " WHERE lower(email) = lower(:email) AND disabled_at IS NULL"
)
SPEND_RECOVERY_CODE = text(
    "UPDATE staff_users"
    " SET recovery_codes_hash = array_remove(recovery_codes_hash, CAST(:code_hash AS text))"
    " WHERE id = :id AND CAST(:code_hash AS text) = ANY(recovery_codes_hash) RETURNING id"
)
INSERT_SESSION = text(
    "INSERT INTO staff_sessions"
    " (id, staff_user_id, token_hash, created_at, last_seen_at, expires_at)"
    " VALUES (:id, :staff_id, :token_hash, :now, :now, :expires_at)"
)
SESSION = text(
    "SELECT s.id, s.staff_user_id, u.email, s.last_seen_at, s.expires_at, s.revoked_at"
    " FROM staff_sessions s JOIN staff_users u ON u.id = s.staff_user_id"
    " WHERE s.token_hash = :token_hash AND u.disabled_at IS NULL"
)
TOUCH = text("UPDATE staff_sessions SET last_seen_at = :now WHERE id = :id AND revoked_at IS NULL")
REVOKE = text("UPDATE staff_sessions SET revoked_at = :now WHERE id = :id AND revoked_at IS NULL")
REVOKE_ALL = text(
    "UPDATE staff_sessions SET revoked_at = :now"
    " WHERE staff_user_id = :staff_id AND revoked_at IS NULL"
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


class SqlStaffLogins:
    def __init__(self, connection: AsyncConnection, cipher: FieldCipher) -> None:
        self._connection = connection
        self._cipher = cipher

    async def by_email(self, email: str) -> StaffCredentials | None:
        row = (await self._connection.execute(CREDENTIALS, {"email": email})).first()
        if row is None:
            return None
        secret = self._cipher.decrypt(row.totp_secret_enc, totp_secret_context(row.id))
        return StaffCredentials(row.id, row.password_hash, secret)

    async def spend_recovery_code(self, staff_id: UUID, code_hash: str) -> bool:
        spent = await self._connection.execute(
            SPEND_RECOVERY_CODE, {"id": staff_id, "code_hash": code_hash}
        )
        return spent.first() is not None


class SqlStaffSessions:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def create(
        self,
        session_id: UUID,
        staff_id: UUID,
        token_hash: bytes,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        await self._connection.execute(
            INSERT_SESSION,
            {
                "id": session_id,
                "staff_id": staff_id,
                "token_hash": token_hash,
                "now": now,
                "expires_at": expires_at,
            },
        )

    async def by_token_hash(self, token_hash: bytes) -> StaffSession | None:
        row = (await self._connection.execute(SESSION, {"token_hash": token_hash})).first()
        if row is None:
            return None
        return StaffSession(
            row.id, row.staff_user_id, row.email, row.last_seen_at, row.expires_at, row.revoked_at
        )

    async def touch(self, session_id: UUID, now: datetime) -> None:
        await self._connection.execute(TOUCH, {"id": session_id, "now": now})

    async def revoke(self, session_id: UUID, now: datetime) -> None:
        await self._connection.execute(REVOKE, {"id": session_id, "now": now})

    async def revoke_all(self, staff_id: UUID, now: datetime) -> None:
        await self._connection.execute(REVOKE_ALL, {"staff_id": staff_id, "now": now})


class PyotpSecondFactor:
    def new_secret(self) -> str:
        return pyotp.random_base32()

    def enrollment_uri(self, secret: str, email: str) -> str:
        return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=TOTP_ISSUER)

    def verify(self, secret: str, code: str, at: datetime) -> bool:
        return pyotp.TOTP(secret).verify(code, for_time=at, valid_window=TOTP_TOLERANCE_STEPS)


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
