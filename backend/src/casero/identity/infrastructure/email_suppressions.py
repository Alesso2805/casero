import hashlib
import hmac
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from casero.identity.domain.email_suppressions import (
    ScheduledEmailKind,
    Suppression,
    normalize_email,
)

INSERT = text(
    "INSERT INTO email_suppressions (email_hash, email_kind, reason, created_at)"
    " VALUES (:email_hash, :email_kind, :reason, :created_at)"
    " ON CONFLICT DO NOTHING"
)

BLOCKS = text(
    "SELECT EXISTS (SELECT 1 FROM email_suppressions WHERE email_hash = :email_hash"
    " AND (email_kind IS NULL OR email_kind = :email_kind))"
)
UNSUBSCRIBED = text(
    "SELECT EXISTS (SELECT 1 FROM email_suppressions WHERE email_hash = :email_hash"
    " AND email_kind = :email_kind AND reason = 'unsubscribe')"
)
RESUBSCRIBE = text(
    "DELETE FROM email_suppressions WHERE email_hash = :email_hash"
    " AND email_kind = :email_kind AND reason = 'unsubscribe'"
)


def email_hash(key: bytes, email: str) -> bytes:
    # The key can't rotate: suppressions keep only this hash (ADR-0010).
    return hmac.new(key, normalize_email(email).encode(), hashlib.sha256).digest()


class SqlSuppressionStore:
    def __init__(self, connection: AsyncConnection, key: bytes) -> None:
        self._connection = connection
        self._key = key

    async def add(self, suppression: Suppression, now: datetime) -> None:
        await self._connection.execute(
            INSERT,
            {
                "email_hash": email_hash(self._key, suppression.email),
                "email_kind": suppression.kind,
                "reason": suppression.reason,
                "created_at": now,
            },
        )

    async def blocks(self, email: str, kind: ScheduledEmailKind | None) -> bool:
        result = await self._connection.execute(
            BLOCKS, {"email_hash": email_hash(self._key, email), "email_kind": kind}
        )
        return bool(result.scalar_one())

    async def unsubscribed(self, email: str, kind: ScheduledEmailKind) -> bool:
        result = await self._connection.execute(
            UNSUBSCRIBED, {"email_hash": email_hash(self._key, email), "email_kind": kind}
        )
        return bool(result.scalar_one())

    async def resubscribe(self, email: str, kind: ScheduledEmailKind) -> None:
        await self._connection.execute(
            RESUBSCRIBE, {"email_hash": email_hash(self._key, email), "email_kind": kind}
        )


class SuppressionLookup:
    def __init__(self, engine: AsyncEngine, key: bytes) -> None:
        self._engine = engine
        self._key = key

    async def blocks(self, email: str) -> bool:
        async with self._engine.connect() as connection:
            return await SqlSuppressionStore(connection, self._key).blocks(email, None)
