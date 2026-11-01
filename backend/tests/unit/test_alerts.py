from datetime import UTC, date, datetime

import pytest
from structlog.testing import capture_logs

from casero.admin.application.alerts import RaiseAlerts, UnansweredComplaint, schedule_years
from casero.admin.application.retention import years_before
from casero.admin.domain.complaints import add_business_days, business_days_between
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
        stuck_jobs: list[str] | None = None,
        missing_rules: set[int] | None = None,
        unanswered: list[UnansweredComplaint] | None = None,
        holidays: frozenset[date] = frozenset(),
    ) -> None:
        self.unanswered = unanswered or []
        self.holidays = holidays
        self.missing_rules = missing_rules or set()
        self.stuck = stuck or []
        self.stuck_jobs = stuck_jobs or []
        self.schedules = schedules or {}
        self.failed = failed or {}

    async def stuck_email_runs(self, started_before: datetime) -> list[tuple[str, str]]:
        return self.stuck

    async def stuck_job_runs(self, started_before: datetime) -> list[str]:
        return self.stuck_jobs

    async def schedule_rows(self, year: int) -> int:
        return self.schedules.get(year, COMPLETE_YEAR)

    async def has_tax_rules(self, year: int) -> bool:
        return year not in self.missing_rules

    async def failed_runs_since(self, since: datetime) -> dict[str, int]:
        return self.failed

    async def unanswered_complaints(self) -> list[UnansweredComplaint]:
        return self.unanswered

    async def holidays_after(self, day: date) -> frozenset[date]:
        return self.holidays


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
    readings: Readings,
    mailer: Mailer,
    now: datetime = datetime(2026, 10, 28, 15, 0, tzinfo=UTC),
    inbox: str | None = "dueno@example.com",
) -> RaiseAlerts:
    return RaiseAlerts(readings, AlertLog(), mailer, inbox, Clock(now))


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


async def test_a_job_cut_off_mid_run_alerts_once_a_day() -> None:
    mailer = Mailer()
    alerts = raise_alerts(Readings(stuck_jobs=["rent_charges"]), mailer)

    with capture_logs() as logs:
        await alerts()
        await alerts()

    assert [(entry["event"], entry["job"]) for entry in logs] == [
        ("worker.job_stuck", "rent_charges")
    ]
    assert "rent_charges" in mailer.sent[0].text


async def test_a_missing_schedule_and_failed_jobs_are_reported() -> None:
    mailer = Mailer()
    readings = Readings(schedules={2026: 60}, failed={"rent_charges": 2, "close_leases": 1})

    with capture_logs() as logs:
        await raise_alerts(readings, mailer)()

    assert [entry["event"] for entry in logs] == ["tax.schedule_missing", "worker.jobs_failed"]
    assert "2026" in mailer.sent[0].subject
    assert mailer.sent[1].text.startswith("Tareas con fallas: close_leases (1), rent_charges (2)")


async def test_next_years_missing_rules_are_reported_from_november() -> None:
    mailer = Mailer()
    readings = Readings(missing_rules={2027})

    with capture_logs() as october:
        await raise_alerts(readings, mailer, datetime(2026, 10, 31, 15, tzinfo=UTC))()
    with capture_logs() as november:
        await raise_alerts(readings, mailer, datetime(2026, 11, 1, 15, tzinfo=UTC))()

    assert october == []
    assert [entry["event"] for entry in november] == ["tax.rules_missing"]
    assert mailer.sent[0].subject == "Casero: faltan las reglas tributarias de 2027"


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


async def test_an_unanswered_complaint_alerts_once_at_7_and_once_at_12_business_days() -> None:
    complaint = UnansweredComplaint("000000001-2026", date(2026, 10, 16), date(2026, 11, 6))
    readings, alerts, mailer = Readings(unanswered=[complaint]), AlertLog(), Mailer()

    def alerts_on(day: datetime) -> RaiseAlerts:
        return RaiseAlerts(readings, alerts, mailer, "dueno@example.com", Clock(day))

    await alerts_on(datetime(2026, 10, 26, 15, tzinfo=UTC))()
    assert mailer.sent == []

    await alerts_on(datetime(2026, 10, 27, 15, tzinfo=UTC))()
    await alerts_on(datetime(2026, 10, 27, 16, tzinfo=UTC))()
    await alerts_on(datetime(2026, 11, 3, 15, tzinfo=UTC))()

    assert [email.subject for email in mailer.sent] == [
        "Casero: el reclamo 000000001-2026 lleva 7 días hábiles sin respuesta",
        "Casero: el reclamo 000000001-2026 lleva 12 días hábiles sin respuesta",
    ]
    assert "06/11/2026" in mailer.sent[0].text


def test_business_days_count_like_the_deadline() -> None:
    filed_on = date(2026, 10, 16)
    holidays = frozenset({date(2026, 10, 20)})
    deadline = add_business_days(filed_on, 15, holidays)

    assert business_days_between(filed_on, filed_on, holidays) == 0
    assert business_days_between(filed_on, date(2026, 10, 19), holidays) == 1
    assert business_days_between(filed_on, date(2026, 10, 21), holidays) == 2
    assert business_days_between(filed_on, deadline, holidays) == 15


def test_a_leap_day_goes_back_to_the_28th() -> None:
    def at(year: int, month: int, day: int) -> datetime:
        return datetime(year, month, day, 15, tzinfo=UTC)

    assert years_before(at(2028, 2, 29), 1) == at(2027, 2, 28)
    assert years_before(at(2028, 3, 1), 2) == at(2026, 3, 1)
