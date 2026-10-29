from datetime import UTC, datetime

import pytest

from api_client import FixedClock
from casero.worker import TAX_REMINDERS_FROM_HOUR, from_lima_hour

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
