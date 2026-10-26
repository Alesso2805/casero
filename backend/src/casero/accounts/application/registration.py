from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.domain.registration import (
    REQUIRED_DOCUMENTS,
    TRIAL_DAYS,
    LegalVersion,
    RegistrationMode,
)
from casero.identity.application.sessions import LoggedIn, StartSession
from casero.identity.application.users import CreateUser
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


class Invites(Protocol):
    async def valid_for(self, token: str, email: str, now: datetime) -> UUID | None: ...

    async def consume(self, invite_id: UUID, now: datetime) -> None: ...


class LegalVersions(Protocol):
    async def current(self, today: date) -> list[LegalVersion]: ...


@dataclass(frozen=True)
class NewAccount:
    account_id: UUID
    user_id: UUID
    display_name: str
    accepted: list[LegalVersion]
    client: str
    now: datetime
    trial_starts_on: date
    trial_ends_on: date


class AccountRecords(Protocol):
    async def create(self, account: NewAccount) -> None: ...

    async def forget_waitlist_entry(self, email: str) -> None: ...


class RegistrationRateLimiter(Protocol):
    async def allow(self, client: str) -> bool: ...


@dataclass(frozen=True)
class Registration:
    email: str
    password: str
    display_name: str
    invite_token: str | None
    client: str
    previous_token: str | None


@dataclass(frozen=True)
class Registered:
    account_id: UUID
    login: LoggedIn


RegistrationOutcome = (
    Registered | Literal["closed", "limited", "invite_invalid", "email_taken", "weak_password"]
)


@dataclass(frozen=True)
class RegisterLandlord:
    mode: RegistrationMode
    limiter: RegistrationRateLimiter
    invites: Invites
    legal: LegalVersions
    create_user: CreateUser
    records: AccountRecords
    start_session: StartSession
    clock: Clock

    async def __call__(self, registration: Registration) -> RegistrationOutcome:
        if self.mode == "closed":
            return "closed"
        if not await self.limiter.allow(registration.client):
            return "limited"
        now = self.clock.now()
        invite_id = None
        if self.mode == "invite":
            token = registration.invite_token or ""
            invite_id = await self.invites.valid_for(token, registration.email, now)
            if invite_id is None:
                return "invite_invalid"
        today = self.clock.today_lima()
        accepted = await self.legal.current(today)
        if sorted(version.kind for version in accepted) != sorted(REQUIRED_DOCUMENTS):
            raise RuntimeError("The current legal documents are not loaded")
        user = await self.create_user(registration.email, registration.password)
        if not isinstance(user, UUID):
            return user
        account_id = new_id()
        await self.records.create(
            NewAccount(
                account_id=account_id,
                user_id=user,
                display_name=registration.display_name,
                accepted=accepted,
                client=registration.client,
                now=now,
                trial_starts_on=today,
                trial_ends_on=today + timedelta(days=TRIAL_DAYS),
            )
        )
        if invite_id is not None:
            await self.invites.consume(invite_id, now)
        await self.records.forget_waitlist_entry(registration.email)
        login = await self.start_session(user, registration.previous_token)
        return Registered(account_id, login)
