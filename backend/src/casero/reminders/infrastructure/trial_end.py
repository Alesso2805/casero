from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from casero.shared.infrastructure.jobs import claim_once, finish_run

TRIAL_EMAIL_JOB = "trial_ended_email"
ONCE = "once"


class SqlTrialEmailLog:
    """In its own transaction, committed before sending, so a crash can't send it twice."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(self, account_id: UUID, now: datetime) -> bool:
        async with self._engine.begin() as connection:
            if not await claim_once(connection, TRIAL_EMAIL_JOB, ONCE, account_id, now):
                return False
            await finish_run(connection, TRIAL_EMAIL_JOB, ONCE, account_id, now)
            return True
