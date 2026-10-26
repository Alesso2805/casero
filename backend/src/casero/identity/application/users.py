from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.identity.application.sessions import PasswordHasher
from casero.identity.domain.email_suppressions import normalize_email
from casero.identity.domain.sessions import MIN_PASSWORD_LENGTH, is_acceptable_password
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id

__all__ = ["MIN_PASSWORD_LENGTH", "CreateUser", "UserStore"]


class UserStore(Protocol):
    async def add(self, user_id: UUID, email: str, password_hash: str, now: datetime) -> bool: ...


@dataclass(frozen=True)
class CreateUser:
    users: UserStore
    hasher: PasswordHasher
    clock: Clock

    async def __call__(
        self, email: str, password: str
    ) -> UUID | Literal["email_taken", "weak_password"]:
        if not is_acceptable_password(password):
            return "weak_password"
        user_id = new_id()
        password_hash = await self.hasher.hash(password)
        if not await self.users.add(
            user_id, normalize_email(email), password_hash, self.clock.now()
        ):
            return "email_taken"
        return user_id
