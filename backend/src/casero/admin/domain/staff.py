from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

RECOVERY_CODE_COUNT = 10
STAFF_SESSION_LIFETIME = timedelta(hours=8)
STAFF_IDLE_LIMIT = timedelta(minutes=30)


@dataclass(frozen=True)
class NewStaff:
    id: UUID
    email: str
    password_hash: str
    totp_secret: str
    recovery_code_hashes: list[str]
    created_at: datetime


@dataclass(frozen=True)
class StaffSession:
    id: UUID
    staff_id: UUID
    email: str
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None

    def is_active(self, now: datetime) -> bool:
        return (
            self.revoked_at is None
            and now < self.expires_at
            and now - self.last_seen_at < STAFF_IDLE_LIMIT
        )
