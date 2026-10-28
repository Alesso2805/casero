from datetime import UTC, date, datetime

import pytest
from structlog.testing import capture_logs

from casero.admin.application.alerts import RaiseAlerts, schedule_years
from casero.shared.kernel.email import Email

pytestmark = pytest.mark.anyio

COMPLETE_YEAR = 84


class Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def today_lima(self) -> date:
        return self._now.date()


class Readings:
    def __init__(
        self,
        stuck: list[tuple[str, str]] | None = None,
        schedules: dict[int, int] | None = None,
        failed: dict[str, int] | None = None,
    ) -> None:
        self.stuck = stuck or []
        self.schedules = schedules or {}
        self.failed = failed or {}

    async def stuck_email_runs(self, started_before: datetime) -> list[tuple[str, str]]:
        return self.stuck

    async def schedule_rows(self, year: int) -> int:
        return self.schedules.get(year, COMPLETE_YEAR)

    async def failed_runs_since(self, since: datetime) -> dict[str, int]:
        return self.failed


class AlertLog:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def claim(self, key: str, now: datetime) -> bool:
        if key in self.keys:
            return False
        self.keys.add(key)
        return True


class Mailer:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)


def raise_alerts(
    readings: Readings, mailer: Mailer, inbox: str | None = "dueno@example.com"
) -> RaiseAlerts:
    clock = Clock(datetime(2026, 10, 28, 15, 0, tzinfo=UTC))
    return RaiseAlerts(readings, AlertLog(), mailer, inbox, clock)


def test_the_next_years_schedule_is_expected_from_november() -> None:
    assert schedule_years(date(2026, 10, 31)) == [2026]
    assert schedule_years(date(2026, 11, 1)) == [2026, 2027]


async def test_a_stuck_complaint_email_alerts_once_by_log_and_email() -> None:
    mailer = Mailer()
    alerts = raise_alerts(Readings(stuck=[("complaint_copy", "c-1")]), mailer)

    with capture_logs() as logs:
        await alerts()
        await alerts()

    assert [entry["event"] for entry in logs] == ["complaint_email.stuck"]
    assert logs[0]["job"] == "complaint_copy"
    [email] = mailer.sent
    assert email.to == "dueno@example.com"
    assert "complaint_copy" in email.text


async def test_a_missing_schedule_and_failed_jobs_are_reported() -> None:
    mailer = Mailer()
    readings = Readings(schedules={2026: 60}, failed={"rent_charges": 2, "close_leases": 1})

    with capture_logs() as logs:
        await raise_alerts(readings, mailer)()

    assert [entry["event"] for entry in logs] == ["tax.schedule_missing", "worker.jobs_failed"]
    assert "2026" in mailer.sent[0].subject
    assert mailer.sent[1].text.startswith("Tareas con fallas: close_leases (1), rent_charges (2)")


async def test_without_an_inbox_alerts_only_go_to_the_logs() -> None:
    mailer = Mailer()

    with capture_logs() as logs:
        await raise_alerts(Readings(failed={"rent_charges": 1}), mailer, inbox=None)()

    assert [entry["event"] for entry in logs] == ["worker.jobs_failed"]
    assert mailer.sent == []


async def test_nothing_to_report_sends_nothing() -> None:
    mailer = Mailer()

    with capture_logs() as logs:
        await raise_alerts(Readings(), mailer)()

    assert (logs, mailer.sent) == ([], [])
