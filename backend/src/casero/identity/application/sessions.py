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
    async def hash(self, password: str) -> str: ...

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
class StartSession:
    tokens: SessionTokens
    store: SessionStore
    clock: Clock

    async def __call__(self, user_id: UUID, previous_token: str | None) -> LoggedIn:
        now = self.clock.now()
        if previous_token:
            previous = await self.store.by_token_hash(self.tokens.hash(previous_token))
            if previous is not None:
                await self.store.revoke(previous.id, now)
        token, token_hash = self.tokens.new()
        session = Session(new_id(), user_id, now, now, now + SESSION_LIFETIME, None)
        await self.store.create(session, token_hash)
        return LoggedIn(token, session)


class LoginSteps(Protocol):
    """Each step runs in its own short transaction, so the delay between them holds no
    database connection or rate-limit lock (critical reviews of Sprints 4-6 and 7-9, I1)."""

    async def check(self, email: str, client: str) -> int | Literal["limited"]: ...

    async def complete(
        self, email: str, password: str, previous_token: str | None
    ) -> LoggedIn | Literal["invalid"]: ...


@dataclass(frozen=True)
class CheckLogin:
    throttle: LoginThrottle

    async def __call__(self, email: str, client: str) -> int | Literal["limited"]:
        """The seconds to wait before checking the password, or "limited" for this client."""
        if not await self.throttle.allow_ip(client):
            return "limited"
        return email_delay_seconds(await self.throttle.recent_failures(email))


@dataclass(frozen=True)
class CompleteLogin:
    credentials: Credentials
    hasher: PasswordHasher
    start_session: StartSession
    throttle: LoginThrottle

    async def __call__(
        self, email: str, password: str, previous_token: str | None
    ) -> LoggedIn | Literal["invalid"]:
        user = await self.credentials.by_email(email)
        if user is None:
            await self.hasher.verify_nothing(password)
            await self.throttle.record_failure(email)
            return "invalid"
        if not await self.hasher.verify(user.password_hash, password):
            await self.throttle.record_failure(email)
            return "invalid"
        return await self.start_session(user.user_id, previous_token)


@dataclass(frozen=True)
class LogIn:
    steps: LoginSteps
    sleeper: Sleeper

    async def __call__(
        self, email: str, password: str, client: str, previous_token: str | None
    ) -> LoginOutcome:
        email = normalize_email(email)
        delay = await self.steps.check(email, client)
        if delay == "limited":
            return "limited"
        if delay:
            await self.sleeper.sleep(delay)
        return await self.steps.complete(email, password, previous_token)


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
