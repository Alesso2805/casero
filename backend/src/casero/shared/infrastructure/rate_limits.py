import hashlib
import hmac

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.kernel.clock import Clock

HIT = text(
    "INSERT INTO rate_limit_buckets (key_hash, window_start, count)"
    " VALUES (:key_hash, :window_start, 1)"
    " ON CONFLICT (key_hash, window_start)"
    " DO UPDATE SET count = rate_limit_buckets.count + 1"
    " RETURNING count"
)


class PostgresRateLimiter:
    def __init__(
        self, connection: AsyncConnection, secret: bytes, clock: Clock, scope: str, per_hour: int
    ) -> None:
        self._connection = connection
        self._secret = secret
        self._clock = clock
        self._scope = scope
        self._per_hour = per_hour

    async def allow(self, client: str) -> bool:
        now = self._clock.now()
        message = f"{now.date().isoformat()}|{self._scope}|{client}".encode()
        key_hash = hmac.new(self._secret, message, hashlib.sha256).digest()
        window_start = now.replace(minute=0, second=0, microsecond=0)
        result = await self._connection.execute(
            HIT, {"key_hash": key_hash, "window_start": window_start}
        )
        return int(result.scalar_one()) <= self._per_hour
