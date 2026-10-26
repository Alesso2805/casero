import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.identity.application.sessions import UserCredentials
from casero.identity.domain.sessions import Session
from casero.shared.infrastructure.rate_limits import PostgresCounter, PostgresRateLimiter
from casero.shared.kernel.clock import Clock

TOKEN_BYTES = 32

CREDENTIALS = text(
    "SELECT id, password_hash FROM users WHERE lower(email) = lower(:email) AND deleted_at IS NULL"
)
PROFILE = text(
    "SELECT email, email_verified_at, created_at FROM users WHERE id = :id AND deleted_at IS NULL"
)
SESSION = text(
    "SELECT id, user_id, created_at, last_seen_at, expires_at, revoked_at FROM sessions"
    " WHERE token_hash = :token_hash"
)
INSERT_SESSION = text(
    "INSERT INTO sessions (id, user_id, token_hash, created_at, last_seen_at, expires_at)"
    " VALUES (:id, :user_id, :token_hash, :created_at, :last_seen_at, :expires_at)"
)
TOUCH = text(
    "UPDATE sessions SET last_seen_at = :now, expires_at = :expires_at"
    " WHERE id = :id AND revoked_at IS NULL"
)
REVOKE = text("UPDATE sessions SET revoked_at = :now WHERE id = :id AND revoked_at IS NULL")
REVOKE_ALL = text(
    "UPDATE sessions SET revoked_at = :now WHERE user_id = :user_id AND revoked_at IS NULL"
)


@dataclass(frozen=True)
class UserProfile:
    email: str
    email_verified: bool
    created_at: datetime


class SecretSessionTokens:
    def new(self) -> tuple[str, bytes]:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        return token, self.hash(token)

    def hash(self, token: str) -> bytes:
        return hashlib.sha256(token.encode()).digest()


class SqlCredentials:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def by_email(self, email: str) -> UserCredentials | None:
        row = (await self._connection.execute(CREDENTIALS, {"email": email})).first()
        return UserCredentials(row.id, row.password_hash) if row else None

    async def profile(self, user_id: UUID) -> UserProfile | None:
        row = (await self._connection.execute(PROFILE, {"id": user_id})).first()
        if row is None:
            return None
        return UserProfile(row.email, row.email_verified_at is not None, row.created_at)


class SqlSessionStore:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def create(self, session: Session, token_hash: bytes) -> None:
        await self._connection.execute(
            INSERT_SESSION,
            {
                "id": session.id,
                "user_id": session.user_id,
                "token_hash": token_hash,
                "created_at": session.created_at,
                "last_seen_at": session.last_seen_at,
                "expires_at": session.expires_at,
            },
        )

    async def by_token_hash(self, token_hash: bytes) -> Session | None:
        row = (await self._connection.execute(SESSION, {"token_hash": token_hash})).first()
        if row is None:
            return None
        return Session(
            row.id, row.user_id, row.created_at, row.last_seen_at, row.expires_at, row.revoked_at
        )

    async def touch(self, session_id: UUID, now: datetime, expires_at: datetime) -> None:
        await self._connection.execute(
            TOUCH, {"id": session_id, "now": now, "expires_at": expires_at}
        )

    async def revoke(self, session_id: UUID, now: datetime) -> None:
        await self._connection.execute(REVOKE, {"id": session_id, "now": now})

    async def revoke_all(self, user_id: UUID, now: datetime) -> None:
        await self._connection.execute(REVOKE_ALL, {"user_id": user_id, "now": now})


class PostgresLoginThrottle:
    def __init__(
        self, connection: AsyncConnection, secret: bytes, clock: Clock, attempts_per_ip: int
    ) -> None:
        self._ip = PostgresRateLimiter(connection, secret, clock, "login-ip", attempts_per_ip)
        self._email = PostgresCounter(connection, secret, clock, "login-email")

    async def allow_ip(self, client: str) -> bool:
        return await self._ip.allow(client)

    async def recent_failures(self, email: str) -> int:
        return await self._email.count(email)

    async def record_failure(self, email: str) -> None:
        await self._email.hit(email)


class AsyncioSleeper:
    async def sleep(self, seconds: int) -> None:
        await asyncio.sleep(seconds)


INSERT_USER = text(
    "INSERT INTO users (id, email, password_hash, created_at)"
    " VALUES (:id, :email, :password_hash, :created_at)"
    " ON CONFLICT ((lower(email))) DO NOTHING RETURNING id"
)


class SqlUserStore:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, user_id: UUID, email: str, password_hash: str, now: datetime) -> bool:
        result = await self._connection.execute(
            INSERT_USER,
            {"id": user_id, "email": email, "password_hash": password_hash, "created_at": now},
        )
        return result.first() is not None
