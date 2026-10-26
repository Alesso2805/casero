import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

TIMING_DUMMY = "casero-timing-dummy"


class Argon2PasswordHasher:
    """Argon2id with argon2-cffi's defaults (RFC 9106 low-memory profile: t=3, m=64 MiB, p=4).

    Hashing runs in a worker thread so the single API process keeps serving requests.
    """

    def __init__(self) -> None:
        self._argon2 = PasswordHasher()
        self._dummy_hash: str | None = None

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._argon2.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        try:
            return await asyncio.to_thread(self._argon2.verify, password_hash, password)
        except VerifyMismatchError, VerificationError, InvalidHashError:
            return False

    async def verify_nothing(self, password: str) -> None:
        # Spends the same time as a real check so a login doesn't reveal which emails exist.
        if self._dummy_hash is None:
            self._dummy_hash = await self.hash(TIMING_DUMMY)
        await self.verify(self._dummy_hash, password)
