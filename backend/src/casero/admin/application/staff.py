from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from casero.admin.application.complaint_commands import StaffActions
from casero.admin.domain.staff import RECOVERY_CODE_COUNT, NewStaff
from casero.identity.application.sessions import PasswordHasher
from casero.identity.application.users import MIN_PASSWORD_LENGTH
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


class StaffDirectory(Protocol):
    async def add(self, staff: NewStaff) -> bool:
        """False, with nothing written, when the email is already taken."""
        ...


class SecondFactor(Protocol):
    def new_secret(self) -> str: ...

    def enrollment_uri(self, secret: str, email: str) -> str: ...

    def verify(self, secret: str, code: str, at: datetime) -> bool: ...


class RecoveryCodes(Protocol):
    def new(self) -> tuple[str, str]:
        """The code to show once, and the hash to keep."""
        ...

    def hash(self, code: str) -> str: ...


@dataclass(frozen=True)
class StaffEnrollment:
    totp_uri: str
    recovery_codes: list[str]


CreateStaffOutcome = StaffEnrollment | Literal["email_taken", "weak_password"]


@dataclass(frozen=True)
class CreateStaff:
    directory: StaffDirectory
    passwords: PasswordHasher
    second_factor: SecondFactor
    recovery_codes: RecoveryCodes
    actions: StaffActions
    clock: Clock

    async def __call__(self, email: str, password: str) -> CreateStaffOutcome:
        if len(password) < MIN_PASSWORD_LENGTH:
            return "weak_password"
        secret = self.second_factor.new_secret()
        codes = [self.recovery_codes.new() for _ in range(RECOVERY_CODE_COUNT)]
        now = self.clock.now()
        staff = NewStaff(
            id=new_id(),
            email=email,
            password_hash=await self.passwords.hash(password),
            totp_secret=secret,
            recovery_code_hashes=[code_hash for _, code_hash in codes],
            created_at=now,
        )
        if not await self.directory.add(staff):
            return "email_taken"
        await self.actions.record("staff.create", "staff_users", staff.id, now)
        return StaffEnrollment(
            self.second_factor.enrollment_uri(secret, email), [code for code, _ in codes]
        )
