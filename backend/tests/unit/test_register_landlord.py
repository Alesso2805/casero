from datetime import UTC, date, datetime
from uuid import UUID, uuid7

import pytest

from casero.accounts.application.registration import (
    NewAccount,
    Registered,
    RegisterLandlord,
    Registration,
)
from casero.accounts.domain.registration import LegalVersion, RegistrationMode
from casero.identity.application.sessions import LoggedIn
from casero.identity.domain.sessions import Session

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
TODAY = date(2026, 10, 26)
DOCUMENTS = [
    LegalVersion("terms", uuid7()),
    LegalVersion("privacy", uuid7()),
    LegalVersion("sensitive_consent", uuid7()),
]
REGISTRATION = Registration(
    email="ana@example.com",
    password="una clave bien larga",
    display_name="Ana",
    invite_token="token",
    client="203.0.113.7",
    previous_token=None,
)


class Clock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> date:
        return TODAY


class Limiter:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    async def allow(self, client: str) -> bool:
        return self.allowed


class Invites:
    def __init__(self, valid: bool = True) -> None:
        self.invite_id = uuid7() if valid else None
        self.consumed: list[UUID] = []

    async def valid_for(self, token: str, email: str, now: datetime) -> UUID | None:
        return self.invite_id

    async def consume(self, invite_id: UUID, now: datetime) -> None:
        self.consumed.append(invite_id)


class Legal:
    def __init__(self, documents: list[LegalVersion]) -> None:
        self.documents = documents

    async def current(self, today: date) -> list[LegalVersion]:
        return self.documents


class CreateUser:
    def __init__(self, outcome: UUID | str) -> None:
        self.outcome = outcome

    async def __call__(self, email: str, password: str) -> UUID | str:
        return self.outcome


class Records:
    def __init__(self) -> None:
        self.created: list[NewAccount] = []
        self.forgotten: list[str] = []

    async def create(self, account: NewAccount) -> None:
        self.created.append(account)

    async def forget_waitlist_entry(self, email: str) -> None:
        self.forgotten.append(email)


class StartSession:
    async def __call__(self, user_id: UUID, previous_token: str | None) -> LoggedIn:
        return LoggedIn("token", Session(uuid7(), user_id, NOW, NOW, NOW, None))


def register(
    mode: RegistrationMode = "invite",
    limiter: Limiter | None = None,
    invites: Invites | None = None,
    legal: Legal | None = None,
    user: UUID | str | None = None,
    records: Records | None = None,
) -> RegisterLandlord:
    return RegisterLandlord(
        mode,
        limiter or Limiter(),
        invites or Invites(),
        legal or Legal(DOCUMENTS),
        CreateUser(user or uuid7()),  # type: ignore[arg-type]
        records or Records(),
        StartSession(),  # type: ignore[arg-type]
        Clock(),
    )


async def test_an_invited_landlord_gets_an_account_with_a_trial_and_a_session() -> None:
    invites, records = Invites(), Records()

    outcome = await register(invites=invites, records=records)(REGISTRATION)

    assert isinstance(outcome, Registered)
    [account] = records.created
    assert account.display_name == "Ana"
    assert account.accepted == DOCUMENTS
    assert (account.trial_starts_on, account.trial_ends_on) == (TODAY, date(2026, 11, 25))
    assert invites.consumed == [invites.invite_id]
    assert records.forgotten == ["ana@example.com"]


@pytest.mark.parametrize(
    ("mode", "limiter", "invites", "expected"),
    [
        ("closed", Limiter(), Invites(), "closed"),
        ("invite", Limiter(False), Invites(), "limited"),
        ("invite", Limiter(), Invites(valid=False), "invite_invalid"),
    ],
)
async def test_closed_limited_or_uninvited_registrations_create_nothing(
    mode: RegistrationMode, limiter: Limiter, invites: Invites, expected: str
) -> None:
    records = Records()

    assert await register(mode, limiter, invites, records=records)(REGISTRATION) == expected
    assert records.created == []


async def test_open_registration_needs_no_invite() -> None:
    invites = Invites(valid=False)

    outcome = await register("open", invites=invites)(REGISTRATION)

    assert isinstance(outcome, Registered)
    assert invites.consumed == []


async def test_a_taken_email_keeps_the_invite_unused() -> None:
    invites, records = Invites(), Records()

    outcome = await register(invites=invites, user="email_taken", records=records)(REGISTRATION)

    assert outcome == "email_taken"
    assert invites.consumed == []
    assert records.created == []


async def test_registration_refuses_to_run_without_the_three_legal_documents() -> None:
    with pytest.raises(RuntimeError, match="legal documents"):
        await register(legal=Legal(DOCUMENTS[:2]))(REGISTRATION)
