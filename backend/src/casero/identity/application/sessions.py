from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.identity.domain.email_suppressions import normalize_email
from casero.identity.domain.sessions import SESSION_LIFETIME, Session, email_delay_seconds
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


@dataclass(frozen=True)
class UserCredentials:
    user_id: UUID
    password_hash: str


class Credentials(Protocol):
    async def by_email(self, email: str) -> UserCredentials | None: ...


class PasswordHasher(Protocol):
    async def verify(self, password_hash: str, password: str) -> bool: ...

    async def verify_nothing(self, password: str) -> None: ...


class SessionTokens(Protocol):
    def new(self) -> tuple[str, bytes]: ...

    def hash(self, token: str) -> bytes: ...


class SessionStore(Protocol):
    async def create(self, session: Session, token_hash: bytes) -> None: ...

    async def by_token_hash(self, token_hash: bytes) -> Session | None: ...

    async def touch(self, session_id: UUID, now: datetime, expires_at: datetime) -> None: ...

    async def revoke(self, session_id: UUID, now: datetime) -> None: ...

    async def revoke_all(self, user_id: UUID, now: datetime) -> None: ...


class LoginThrottle(Protocol):
    async def allow_ip(self, client: str) -> bool: ...

    async def recent_failures(self, email: str) -> int: ...

    async def record_failure(self, email: str) -> None: ...


class Sleeper(Protocol):
    async def sleep(self, seconds: int) -> None: ...


@dataclass(frozen=True)
class LoggedIn:
    token: str
    session: Session


LoginOutcome = LoggedIn | Literal["invalid", "limited"]


@dataclass(frozen=True)
class LogIn:
    credentials: Credentials
    hasher: PasswordHasher
    tokens: SessionTokens
    store: SessionStore
    throttle: LoginThrottle
    sleeper: Sleeper
    clock: Clock

    async def __call__(
        self, email: str, password: str, client: str, previous_token: str | None
    ) -> LoginOutcome:
        if not await self.throttle.allow_ip(client):
            return "limited"
        email = normalize_email(email)
        delay = email_delay_seconds(await self.throttle.recent_failures(email))
        if delay:
            await self.sleeper.sleep(delay)
        user = await self.credentials.by_email(email)
        if user is None:
            await self.hasher.verify_nothing(password)
            await self.throttle.record_failure(email)
            return "invalid"
        if not await self.hasher.verify(user.password_hash, password):
            await self.throttle.record_failure(email)
            return "invalid"
        now = self.clock.now()
        if previous_token:
            await self._revoke(previous_token, now)
        token, token_hash = self.tokens.new()
        session = Session(new_id(), user.user_id, now, now, now + SESSION_LIFETIME, None)
        await self.store.create(session, token_hash)
        return LoggedIn(token, session)

    async def _revoke(self, token: str, now: datetime) -> None:
        session = await self.store.by_token_hash(self.tokens.hash(token))
        if session is not None:
            await self.store.revoke(session.id, now)


@dataclass(frozen=True)
class AuthenticateSession:
    tokens: SessionTokens
    store: SessionStore
    clock: Clock

    async def __call__(self, token: str) -> Session | None:
        session = await self.store.by_token_hash(self.tokens.hash(token))
        now = self.clock.now()
        if session is None or not session.active(now):
            return None
        if session.needs_refresh(now):
            await self.store.touch(session.id, now, now + SESSION_LIFETIME)
        return session


@dataclass(frozen=True)
class LogOut:
    store: SessionStore
    clock: Clock

    async def __call__(self, session: Session, everywhere: bool) -> None:
        now = self.clock.now()
        if everywhere:
            await self.store.revoke_all(session.user_id, now)
        else:
            await self.store.revoke(session.id, now)
