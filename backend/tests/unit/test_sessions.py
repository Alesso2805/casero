from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid7

import pytest

from casero.identity.application.sessions import (
    AuthenticateSession,
    CheckLogin,
    CompleteLogin,
    LoggedIn,
    LogIn,
    LogOut,
    StartSession,
    UserCredentials,
)
from casero.identity.domain.sessions import (
    SESSION_LIFETIME,
    Session,
    email_delay_seconds,
    is_acceptable_password,
)
from casero.identity.infrastructure.passwords import Argon2PasswordHasher

pytestmark = pytest.mark.anyio

START = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
USER = UUID("01a175b4-8f38-727d-a7dc-40a7a7b30002")


class Clock:
    def __init__(self) -> None:
        self.current = START

    def now(self) -> datetime:
        return self.current

    def today_lima(self) -> date:
        return self.current.date()


class Credentials:
    async def by_email(self, email: str) -> UserCredentials | None:
        return UserCredentials(USER, "hash-of-correct") if email == "ana@example.com" else None


class Hasher:
    def __init__(self) -> None:
        self.dummy_checks = 0

    async def hash(self, password: str) -> str:
        return f"hash-of-{password}"

    async def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hash-of-{password}"

    async def verify_nothing(self, password: str) -> None:
        self.dummy_checks += 1


class Tokens:
    def __init__(self) -> None:
        self.issued = 0

    def new(self) -> tuple[str, bytes]:
        self.issued += 1
        token = f"token-{self.issued}"
        return token, self.hash(token)

    def hash(self, token: str) -> bytes:
        return token.encode()


class Store:
    def __init__(self) -> None:
        self.sessions: dict[bytes, Session] = {}

    async def create(self, session: Session, token_hash: bytes) -> None:
        self.sessions[token_hash] = session

    async def by_token_hash(self, token_hash: bytes) -> Session | None:
        return self.sessions.get(token_hash)

    def _key(self, session_id: UUID) -> bytes:
        return next(key for key, session in self.sessions.items() if session.id == session_id)

    async def touch(self, session_id: UUID, now: datetime, expires_at: datetime) -> None:
        key = self._key(session_id)
        self.sessions[key] = replace(self.sessions[key], last_seen_at=now, expires_at=expires_at)

    async def revoke(self, session_id: UUID, now: datetime) -> None:
        key = self._key(session_id)
        self.sessions[key] = replace(self.sessions[key], revoked_at=now)

    async def revoke_all(self, user_id: UUID, now: datetime) -> None:
        for session in list(self.sessions.values()):
            if session.user_id == user_id:
                await self.revoke(session.id, now)


class Throttle:
    def __init__(self, allow: bool = True, failures: int = 0) -> None:
        self.allow = allow
        self.failures = failures
        self.recorded: list[str] = []

    async def allow_ip(self, client: str) -> bool:
        return self.allow

    async def recent_failures(self, email: str) -> int:
        return self.failures

    async def record_failure(self, email: str) -> None:
        self.recorded.append(email)


class Sleeper:
    def __init__(self) -> None:
        self.slept: list[int] = []

    async def sleep(self, seconds: int) -> None:
        self.slept.append(seconds)


class Steps:
    """Both login steps in memory; the API runs each in its own transaction."""

    def __init__(self, check: CheckLogin, complete: CompleteLogin) -> None:
        self._check = check
        self._complete = complete

    async def check(self, email: str, client: str) -> int | Literal["limited"]:
        return await self._check(email, client)

    async def complete(
        self, email: str, password: str, previous_token: str | None
    ) -> LoggedIn | Literal["invalid"]:
        return await self._complete(email, password, previous_token)


def login(
    store: Store | None = None,
    throttle: Throttle | None = None,
    hasher: Hasher | None = None,
    sleeper: Sleeper | None = None,
    clock: Clock | None = None,
) -> LogIn:
    start = StartSession(Tokens(), store or Store(), clock or Clock())
    throttle = throttle or Throttle()
    complete = CompleteLogin(Credentials(), hasher or Hasher(), start, throttle)
    return LogIn(Steps(CheckLogin(throttle), complete), sleeper or Sleeper())


@pytest.mark.parametrize(
    ("failures", "delay"), [(0, 0), (2, 0), (3, 1), (4, 2), (7, 16), (8, 30), (50, 30)]
)
def test_the_delay_grows_with_failures_but_never_locks_the_account(
    failures: int, delay: int
) -> None:
    assert email_delay_seconds(failures) == delay


def test_passwords_need_ten_characters() -> None:
    assert not is_acceptable_password("123456789")
    assert is_acceptable_password("1234567890")


async def test_argon2id_hashes_verify_and_reject() -> None:
    hasher = Argon2PasswordHasher()
    hashed = await hasher.hash("una clave larga")

    assert hashed.startswith("$argon2id$")
    assert await hasher.verify(hashed, "una clave larga")
    assert not await hasher.verify(hashed, "otra clave")
    assert not await hasher.verify("not a hash", "una clave larga")


async def test_a_right_password_opens_a_thirty_day_session() -> None:
    store = Store()

    outcome = await login(store=store)(" Ana@Example.com ", "correct", "203.0.113.7", None)

    assert isinstance(outcome, LoggedIn)
    assert outcome.session.user_id == USER
    assert outcome.session.expires_at == START + SESSION_LIFETIME
    assert store.sessions[outcome.token.encode()] == outcome.session


@pytest.mark.parametrize(
    ("email", "password"), [("ana@example.com", "wrong"), ("x@example.com", "correct")]
)
async def test_wrong_credentials_count_as_failures(email: str, password: str) -> None:
    throttle = Throttle()
    hasher = Hasher()

    assert await login(throttle=throttle, hasher=hasher)(email, password, "x", None) == "invalid"
    assert throttle.recorded == [email]
    assert hasher.dummy_checks == (email != "ana@example.com")


async def test_a_blocked_ip_is_refused_and_a_failing_email_waits() -> None:
    sleeper = Sleeper()

    assert (
        await login(throttle=Throttle(allow=False))("ana@example.com", "correct", "x", None)
        == "limited"
    )
    outcome = await login(throttle=Throttle(failures=4), sleeper=sleeper)(
        "ana@example.com", "correct", "x", None
    )
    assert isinstance(outcome, LoggedIn)
    assert sleeper.slept == [2]


async def test_logging_in_again_replaces_the_previous_session() -> None:
    store = Store()
    log_in = login(store=store)
    first = await log_in("ana@example.com", "correct", "x", None)
    assert isinstance(first, LoggedIn)

    second = await log_in("ana@example.com", "correct", "x", first.token)

    assert isinstance(second, LoggedIn)
    assert second.token != first.token
    assert store.sessions[first.token.encode()].revoked_at == START


async def test_sessions_slide_while_used_and_end_when_idle_or_revoked() -> None:
    store, clock, tokens = Store(), Clock(), Tokens()
    token, token_hash = tokens.new()
    await store.create(
        Session(uuid7(), USER, START, START, START + SESSION_LIFETIME, None), token_hash
    )
    authenticate = AuthenticateSession(tokens, store, clock)

    clock.current = START + timedelta(minutes=30)
    assert (await authenticate(token)) is not None
    assert store.sessions[token_hash].last_seen_at == START

    clock.current = START + timedelta(days=20)
    assert (await authenticate(token)) is not None
    assert store.sessions[token_hash].expires_at == clock.current + SESSION_LIFETIME

    clock.current += SESSION_LIFETIME
    assert await authenticate(token) is None


async def test_logging_out_everywhere_ends_every_session_of_the_user() -> None:
    store, clock = Store(), Clock()
    sessions = [
        Session(uuid7(), USER, START, START, START + SESSION_LIFETIME, None) for _ in range(2)
    ]
    for index, session in enumerate(sessions):
        await store.create(session, bytes([index]))

    await LogOut(store, clock)(sessions[0], everywhere=True)

    assert all(session.revoked_at == START for session in store.sessions.values())
