import hashlib
import hmac
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from casero.shared.kernel.clock import Clock

# Windows are hourly, so dropping those that began 23 hours ago means no hashed IP lives
# 24 hours, as the privacy policy promises.
RETENTION = timedelta(hours=23)
PURGE = text("DELETE FROM rate_limit_buckets WHERE window_start < :cutoff")

HIT = text(
    "INSERT INTO rate_limit_buckets (key_hash, window_start, count)"
    " VALUES (:key_hash, :window_start, 1)"
    " ON CONFLICT (key_hash, window_start)"
    " DO UPDATE SET count = rate_limit_buckets.count + 1"
    " RETURNING count"
)
COUNT = text(
    "SELECT count FROM rate_limit_buckets WHERE key_hash = :key_hash"
    " AND window_start = :window_start"
)


def _bucket(secret: bytes, now: datetime, scope: str, subject: str) -> dict[str, object]:
    # The date in the message rotates the key every day, so a hash can't be linked across days.
    message = f"{now.date().isoformat()}|{scope}|{subject}".encode()
    return {
        "key_hash": hmac.new(secret, message, hashlib.sha256).digest(),
        "window_start": now.replace(minute=0, second=0, microsecond=0),
    }


class PostgresCounter:
    def __init__(
        self, connection: AsyncConnection, secret: bytes, clock: Clock, scope: str
    ) -> None:
        self._connection = connection
        self._secret = secret
        self._clock = clock
        self._scope = scope

    async def hit(self, subject: str) -> int:
        bucket = _bucket(self._secret, self._clock.now(), self._scope, subject)
        result = await self._connection.execute(HIT, bucket)
        return int(result.scalar_one())

    async def count(self, subject: str) -> int:
        bucket = _bucket(self._secret, self._clock.now(), self._scope, subject)
        result = await self._connection.execute(COUNT, bucket)
        return int(result.scalar_one_or_none() or 0)


class PostgresRateLimiter:
    def __init__(
        self, connection: AsyncConnection, secret: bytes, clock: Clock, scope: str, per_hour: int
    ) -> None:
        self._counter = PostgresCounter(connection, secret, clock, scope)
        self._per_hour = per_hour

    async def allow(self, client: str) -> bool:
        return await self._counter.hit(client) <= self._per_hour


async def purge_expired_buckets(engine: AsyncEngine, clock: Clock) -> int:
    async with engine.begin() as connection:
        result = await connection.execute(PURGE, {"cutoff": clock.now() - RETENTION})
        return result.rowcount
