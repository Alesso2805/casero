from datetime import UTC, datetime, timedelta

import pytest

from api_client import FixedClock
from casero.worker import (
    TAX_REMINDER_RETRY_EVERY,
    TAX_REMINDERS_FROM_HOUR,
    at_most_every,
    from_lima_hour,
)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(("utc_hour", "runs"), [(12, False), (13, True)])
async def test_tax_reminders_wait_for_eight_in_the_morning_in_lima(
    utc_hour: int, runs: bool
) -> None:
    calls: list[None] = []

    async def job() -> None:
        calls.append(None)

    clock = FixedClock(datetime(2026, 11, 14, utc_hour, 0, tzinfo=UTC))
    await from_lima_hour(TAX_REMINDERS_FROM_HOUR, clock, job)()

    assert bool(calls) == runs


async def test_a_retried_job_runs_at_most_once_an_hour() -> None:
    calls: list[datetime] = []
    clock = FixedClock(datetime(2026, 11, 14, 13, 0, tzinfo=UTC))

    async def job() -> None:
        calls.append(clock.now())

    spaced = at_most_every(TAX_REMINDER_RETRY_EVERY, clock, job)
    for minutes in (0, 1, 59, 1, 60):
        clock.advance(timedelta(minutes=minutes))
        await spaced()

    assert [call.strftime("%H:%M") for call in calls] == ["13:00", "14:00", "15:01"]
