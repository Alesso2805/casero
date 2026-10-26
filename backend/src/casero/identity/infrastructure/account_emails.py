import hashlib
import secrets
from datetime import datetime
from uuid import UUID

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.identity.application.account_emails import AccountUser
from casero.identity.domain.account_emails import TokenPurpose

TOKEN_BYTES = 32

USER_BY_ID = text(
    "SELECT id, email, email_verified_at FROM users WHERE id = :id AND deleted_at IS NULL"
)
USER_BY_EMAIL = text(
    "SELECT id, email, email_verified_at FROM users"
    " WHERE lower(email) = lower(:email) AND deleted_at IS NULL"
)
MARK_VERIFIED = text(
    "UPDATE users SET email_verified_at = :now WHERE id = :id AND email_verified_at IS NULL"
)
SET_PASSWORD = text("UPDATE users SET password_hash = :password_hash WHERE id = :id")
INSERT_TOKEN = text(
    "INSERT INTO email_tokens (id, user_id, purpose, token_hash, expires_at)"
    " VALUES (:id, :user_id, :purpose, :token_hash, :expires_at)"
)
CONSUME_TOKEN = text(
    "UPDATE email_tokens SET used_at = :now"
    " WHERE token_hash = :token_hash AND purpose = :purpose AND used_at IS NULL"
    " AND expires_at > :now RETURNING user_id"
)


class SecretEmailTokens:
    def new(self) -> tuple[str, bytes]:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        return token, self.hash(token)

    def hash(self, token: str) -> bytes:
        return hashlib.sha256(token.encode()).digest()


class SqlAccountUsers:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def _one(self, query: TextClause, params: dict[str, object]) -> AccountUser | None:
        row = (await self._connection.execute(query, params)).first()
        return AccountUser(row.id, row.email, row.email_verified_at is not None) if row else None

    async def by_id(self, user_id: UUID) -> AccountUser | None:
        return await self._one(USER_BY_ID, {"id": user_id})

    async def by_email(self, email: str) -> AccountUser | None:
        return await self._one(USER_BY_EMAIL, {"email": email})

    async def mark_verified(self, user_id: UUID, now: datetime) -> None:
        await self._connection.execute(MARK_VERIFIED, {"id": user_id, "now": now})

    async def set_password_hash(self, user_id: UUID, password_hash: str) -> None:
        await self._connection.execute(
            SET_PASSWORD, {"id": user_id, "password_hash": password_hash}
        )


class SqlEmailTokenStore:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def create(
        self,
        token_id: UUID,
        user_id: UUID,
        purpose: TokenPurpose,
        token_hash: bytes,
        expires_at: datetime,
    ) -> None:
        await self._connection.execute(
            INSERT_TOKEN,
            {
                "id": token_id,
                "user_id": user_id,
                "purpose": purpose,
                "token_hash": token_hash,
                "expires_at": expires_at,
            },
        )

    async def consume(self, token_hash: bytes, purpose: TokenPurpose, now: datetime) -> UUID | None:
        result = await self._connection.execute(
            CONSUME_TOKEN, {"token_hash": token_hash, "purpose": purpose, "now": now}
        )
        user_id: UUID | None = result.scalar_one_or_none()
        return user_id
