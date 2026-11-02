from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from casero.admin.application.complaint_commands import StaffActions
from casero.admin.application.staff import RecoveryCodes, SecondFactor
from casero.admin.domain.staff import STAFF_SESSION_LIFETIME, StaffSession
from casero.identity.application.sessions import PasswordHasher, SessionTokens
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


@dataclass(frozen=True)
class StaffCredentials:
    staff_id: UUID
    password_hash: str
    totp_secret: str


class StaffLogins(Protocol):
    async def by_email(self, email: str) -> StaffCredentials | None: ...

    async def spend_recovery_code(self, staff_id: UUID, code_hash: str) -> bool:
        """True only for the one call that removes the code, so it works once."""
        ...


class StaffSessions(Protocol):
    async def create(
        self,
        session_id: UUID,
        staff_id: UUID,
        token_hash: bytes,
        now: datetime,
        expires_at: datetime,
    ) -> None: ...

    async def by_token_hash(self, token_hash: bytes) -> StaffSession | None: ...

    async def touch(self, session_id: UUID, now: datetime) -> None: ...

    async def revoke(self, session_id: UUID, now: datetime) -> None: ...

    async def revoke_all(self, staff_id: UUID, now: datetime) -> None: ...


@dataclass(frozen=True)
class LogStaffIn:
    logins: StaffLogins
    sessions: StaffSessions
    passwords: PasswordHasher
    second_factor: SecondFactor
    recovery_codes: RecoveryCodes
    tokens: SessionTokens
    actions: StaffActions
    clock: Clock

    async def __call__(self, email: str, password: str, code: str) -> str | None:
        """The session token, or None without saying which factor failed."""
        credentials = await self.logins.by_email(email)
        if credentials is None:
            await self.passwords.verify_nothing(password)
            return None
        staff_id = credentials.staff_id
        now = self.clock.now()
        login = await self._second_step(credentials, password, code, now)
        if login is None:
            await self.actions.record("staff.login_failed", "staff_users", staff_id, now, staff_id)
            return None
        await self.sessions.revoke_all(staff_id, now)
        token, token_hash = self.tokens.new()
        session_id = new_id()
        await self.sessions.create(
            session_id, staff_id, token_hash, now, now + STAFF_SESSION_LIFETIME
        )
        await self.actions.record(login, "staff_sessions", session_id, now, staff_id)
        return token

    async def _second_step(
        self, credentials: StaffCredentials, password: str, code: str, now: datetime
    ) -> str | None:
        if not await self.passwords.verify(credentials.password_hash, password):
            return None
        if self.second_factor.verify(credentials.totp_secret, code, now):
            return "staff.login"
        code_hash = self.recovery_codes.hash(code)
        if await self.logins.spend_recovery_code(credentials.staff_id, code_hash):
            return "staff.login_recovery_code"
        return None


@dataclass(frozen=True)
class AuthenticateStaff:
    sessions: StaffSessions
    tokens: SessionTokens
    clock: Clock

    async def __call__(self, token: str) -> StaffSession | None:
        session = await self.sessions.by_token_hash(self.tokens.hash(token))
        now = self.clock.now()
        if session is None or not session.is_active(now):
            return None
        await self.sessions.touch(session.id, now)
        return session


@dataclass(frozen=True)
class LogStaffOut:
    sessions: StaffSessions
    actions: StaffActions
    clock: Clock

    async def __call__(self, session: StaffSession) -> None:
        now = self.clock.now()
        await self.sessions.revoke(session.id, now)
        await self.actions.record(
            "staff.logout", "staff_sessions", session.id, now, session.staff_id
        )
