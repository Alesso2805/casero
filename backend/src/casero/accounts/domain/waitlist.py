from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

WaitlistSource = Literal["landing", "calculator"]


@dataclass(frozen=True)
class WaitlistEntry:
    id: UUID
    email: str
    source: WaitlistSource
    consented_at: datetime
    created_at: datetime
