from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

SESSION_LIFETIME = timedelta(days=30)
SESSION_REFRESH_INTERVAL = timedelta(hours=1)
MIN_PASSWORD_LENGTH = 10
FREE_EMAIL_FAILURES = 3
MAX_EMAIL_DELAY_SECONDS = 30


@dataclass(frozen=True)
class Session:
    id: UUID
    user_id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None

    def active(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at

    def needs_refresh(self, now: datetime) -> bool:
        return now - self.last_seen_at >= SESSION_REFRESH_INTERVAL


def email_delay_seconds(recent_failures: int) -> int:
    """Progressive delay per email: never a lockout, so nobody can block someone else's account."""
    if recent_failures < FREE_EMAIL_FAILURES:
        return 0
    return min(1 << (recent_failures - FREE_EMAIL_FAILURES), MAX_EMAIL_DELAY_SECONDS)


def is_acceptable_password(password: str) -> bool:
    return len(password) >= MIN_PASSWORD_LENGTH
