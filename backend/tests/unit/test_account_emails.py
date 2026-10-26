from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from casero.identity.application.account_emails import (
    AccountEmailSender,
    AccountLinks,
    AccountUser,
    ConfirmEmail,
    RequestPasswordReset,
    ResetPassword,
    SendVerification,
)
from casero.identity.domain.account_emails import (
    RESET_LIFETIME,
    VERIFICATION_LIFETIME,
    TokenPurpose,
    access_blocked,
    verify_by,
)
from casero.identity.domain.email_suppressions import ScheduledEmailKind, Suppression
from casero.identity.domain.sessions import Session
from casero.shared.kernel.email import Email, MailDeliveryError

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
USER = AccountUser(UUID("01a175b4-8f38-727d-a7dc-40a7a7b30003"), "ana@example.com", False)


class Clock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> date:
        return NOW.date()


class Users:
    def __init__(self, *users: AccountUser) -> None:
        self.users = {user.user_id: user for user in users}
        self.verified: list[UUID] = []
        self.hashes: dict[UUID, str] = {}

    async def by_id(self, user_id: UUID) -> AccountUser | None:
        return self.users.get(user_id)

    async def by_email(self, email: str) -> AccountUser | None:
        return next((user for user in self.users.values() if user.email == email), None)

    async def mark_verified(self, user_id: UUID, now: datetime) -> None:
        self.verified.append(user_id)

    async def set_password_hash(self, user_id: UUID, password_hash: str) -> None:
        self.hashes[user_id] = password_hash


class Tokens:
    def new(self) -> tuple[str, bytes]:
        return "token-1", b"hash-1"

    def hash(self, token: str) -> bytes:
        return f"hash-{token.removeprefix('token-')}".encode()


class Store:
    def __init__(self) -> None:
        self.created: list[tuple[UUID, TokenPurpose, bytes, datetime]] = []
        self.valid: dict[tuple[bytes, TokenPurpose], UUID] = {}

    async def create(
        self,
        token_id: UUID,
        user_id: UUID,
        purpose: TokenPurpose,
        token_hash: bytes,
        expires_at: datetime,
    ) -> None:
        self.created.append((user_id, purpose, token_hash, expires_at))
        self.valid[token_hash, purpose] = user_id

    async def consume(self, token_hash: bytes, purpose: TokenPurpose, now: datetime) -> UUID | None:
        return self.valid.pop((token_hash, purpose), None)


class Suppressions:
    def __init__(self, blocked: bool = False) -> None:
        self.blocked = blocked

    async def add(self, suppression: Suppression, now: datetime) -> None:
        raise AssertionError("not used")

    async def blocks(self, email: str, kind: ScheduledEmailKind | None) -> bool:
        return self.blocked


class Mailer:
    def __init__(self, failing: bool = False) -> None:
        self.failing = failing
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        if self.failing:
            raise MailDeliveryError("SMTPServerDisconnected")
        self.sent.append(email)


class Limiter:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    async def allow(self, subject: str) -> bool:
        return self.allowed


class Hasher:
    async def hash(self, password: str) -> str:
        return f"hash-of-{password}"

    async def verify(self, password_hash: str, password: str) -> bool:
        return False

    async def verify_nothing(self, password: str) -> None:
        return None


class Sessions:
    def __init__(self) -> None:
        self.revoked_users: list[UUID] = []

    async def create(self, session: Session, token_hash: bytes) -> None:
        raise AssertionError("not used")

    async def by_token_hash(self, token_hash: bytes) -> Session | None:
        return None

    async def touch(self, session_id: UUID, now: datetime, expires_at: datetime) -> None:
        raise AssertionError("not used")

    async def revoke(self, session_id: UUID, now: datetime) -> None:
        raise AssertionError("not used")

    async def revoke_all(self, user_id: UUID, now: datetime) -> None:
        self.revoked_users.append(user_id)


def sender(
    store: Store, mailer: Mailer, suppressions: Suppressions | None = None
) -> AccountEmailSender:
    links = AccountLinks("https://casero.example/")
    return AccountEmailSender(
        Tokens(), store, suppressions or Suppressions(), mailer, links, Clock()
    )


async def test_a_verification_link_is_valid_for_seven_days() -> None:
    store, mailer = Store(), Mailer()

    outcome = await SendVerification(Users(USER), Limiter(), sender(store, mailer))(USER.user_id)

    assert outcome == "sent"
    assert store.created == [(USER.user_id, "verify_email", b"hash-1", NOW + VERIFICATION_LIFETIME)]
    [email] = mailer.sent
    assert email.to == "ana@example.com"
    assert email.subject == "Confirma tu correo en Casero"
    assert "https://casero.example/verificar#token=token-1" in email.text


@pytest.mark.parametrize(
    ("user", "limiter", "expected"),
    [
        (AccountUser(USER.user_id, USER.email, True), Limiter(), "verified"),
        (USER, Limiter(False), "limited"),
    ],
)
async def test_no_verification_is_sent_when_verified_or_limited(
    user: AccountUser, limiter: Limiter, expected: str
) -> None:
    mailer = Mailer()

    assert (
        await SendVerification(Users(user), limiter, sender(Store(), mailer))(USER.user_id)
        == expected
    )
    assert mailer.sent == []


async def test_a_bounced_address_gets_no_email_and_a_failed_send_is_reported() -> None:
    store = Store()

    assert (
        await sender(store, Mailer(), Suppressions(blocked=True)).send(USER, "verify_email")
        == "suppressed"
    )
    assert store.created == []
    assert await sender(store, Mailer(failing=True)).send(USER, "verify_email") == "failed"


async def test_a_verification_token_confirms_the_email_once() -> None:
    store, users = Store(), Users(USER)
    await sender(store, Mailer()).send(USER, "verify_email")
    confirm = ConfirmEmail(users, store, Tokens(), Clock())

    assert await confirm("token-1")
    assert not await confirm("token-1")
    assert users.verified == [USER.user_id]


async def test_a_reset_is_only_sent_to_existing_accounts_but_always_accepted() -> None:
    store, mailer = Store(), Mailer()
    request = RequestPasswordReset(Users(USER), Limiter(), Limiter(), sender(store, mailer))

    assert await request(" ANA@example.com ", "203.0.113.7") == "accepted"
    assert await request("nadie@example.com", "203.0.113.7") == "accepted"
    [email] = mailer.sent
    assert "https://casero.example/nueva-clave#token=token-1" in email.text
    assert store.created[0][3] == NOW + RESET_LIFETIME
    blocked = RequestPasswordReset(Users(USER), Limiter(False), Limiter(), sender(store, mailer))
    assert await blocked("ana@example.com", "203.0.113.7") == "limited"


async def test_a_reset_sets_the_password_verifies_the_email_and_closes_sessions() -> None:
    store, users, sessions = Store(), Users(USER), Sessions()
    await sender(store, Mailer()).send(USER, "reset_password")
    reset = ResetPassword(users, store, Tokens(), Hasher(), sessions, Clock())

    assert await reset("token-1", "corta") == "weak"
    assert await reset("token-1", "una clave nueva y larga") == "done"
    assert await reset("token-1", "una clave nueva y larga") == "invalid"
    assert users.hashes == {USER.user_id: "hash-of-una clave nueva y larga"}
    assert users.verified == [USER.user_id]
    assert sessions.revoked_users == [USER.user_id]


def test_links_never_double_the_slash() -> None:
    links = AccountLinks("https://casero.example/")

    assert links.verification("t") == "https://casero.example/verificar#token=t"
    assert links.password_reset("t") == "https://casero.example/nueva-clave#token=t"
    assert timedelta(days=7) == VERIFICATION_LIFETIME


def test_an_unverified_account_is_blocked_after_seven_days() -> None:
    assert verify_by(NOW, email_verified=False) == NOW + timedelta(days=7)
    assert verify_by(NOW, email_verified=True) is None
    assert not access_blocked(NOW, False, NOW + timedelta(days=6, hours=23))
    assert access_blocked(NOW, False, NOW + timedelta(days=7))
    assert not access_blocked(NOW, True, NOW + timedelta(days=300))
