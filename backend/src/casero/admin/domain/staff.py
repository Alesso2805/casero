from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

RECOVERY_CODE_COUNT = 10


@dataclass(frozen=True)
class NewStaff:
    id: UUID
    email: str
    password_hash: str
    totp_secret: str
    recovery_code_hashes: list[str]
    created_at: datetime
