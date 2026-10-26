from datetime import UTC, date, datetime

import pytest

from casero.admin.application.complaints import FileComplaint
from casero.admin.domain.complaints import (
    RESPONSE_BUSINESS_DAYS,
    Complaint,
    ComplaintSheet,
    DocumentType,
    add_business_days,
    complaint_number,
    is_valid_document,
    normalize_document,
)

SHEET = ComplaintSheet(
    full_name="Ana Quispe",
    document_type="dni",
    document_number="12345678",
    address=None,
    email="ana@example.com",
    phone=None,
    guardian=None,
    item_kind="service",
    claimed_amount_cents=None,
    item_description=None,
    kind="claim",
    detail="No me llegó el correo de confirmación.",
    request=None,
    response_channel="email",
)


@pytest.mark.parametrize(
    ("filed_on", "holidays", "due_on"),
    [
        (date(2026, 10, 23), frozenset(), date(2026, 11, 13)),
        (date(2026, 10, 24), frozenset(), date(2026, 11, 13)),
        (date(2026, 10, 25), frozenset(), date(2026, 11, 13)),
        (date(2026, 10, 26), frozenset(), date(2026, 11, 16)),
        (
            date(2026, 10, 23),
            frozenset({date(2026, 11, 2), date(2026, 11, 13)}),
            date(2026, 11, 17),
        ),
        (date(2026, 12, 18), frozenset({date(2026, 12, 25), date(2027, 1, 1)}), date(2027, 1, 12)),
    ],
)
def test_the_answer_is_due_fifteen_business_days_after_filing(
    filed_on: date, holidays: frozenset[date], due_on: date
) -> None:
    assert add_business_days(filed_on, RESPONSE_BUSINESS_DAYS, holidays) == due_on


def test_a_holiday_on_the_filing_day_does_not_move_the_count() -> None:
    filed_on = date(2026, 10, 23)

    assert add_business_days(filed_on, 1, frozenset({filed_on})) == date(2026, 10, 26)


def test_the_number_follows_the_official_sheet() -> None:
    assert complaint_number(1, 2026) == "000000001-2026"
    assert complaint_number(123_456, 2027) == "000123456-2027"


@pytest.mark.parametrize(
    ("document_type", "raw", "valid"),
    [
        ("dni", "12345678", True),
        ("dni", " 1234 5678 ", True),
        ("dni", "1234567", False),
        ("dni", "1234567A", False),
        ("ce", "001234567", True),
        ("passport", "ab-123456", True),
        ("passport", "12", False),
    ],
)
def test_documents_are_checked_after_normalizing(
    document_type: DocumentType, raw: str, valid: bool
) -> None:
    assert is_valid_document(document_type, normalize_document(raw)) is valid


class LimaClock:
    def __init__(self, now: datetime, today: date) -> None:
        self._now = now
        self._today = today

    def now(self) -> datetime:
        return self._now

    def today_lima(self) -> date:
        return self._today


class MemoryRepository:
    def __init__(self, holidays: frozenset[date] = frozenset()) -> None:
        self.holidays = holidays
        self.counters: dict[int, int] = {}
        self.complaints: list[Complaint] = []

    async def next_sequence(self, year: int) -> int:
        self.counters[year] = self.counters.get(year, 0) + 1
        return self.counters[year]

    async def holidays_after(self, day: date) -> frozenset[date]:
        return frozenset(holiday for holiday in self.holidays if holiday > day)

    async def add(self, complaint: Complaint) -> None:
        self.complaints.append(complaint)


class Limiter:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    async def allow(self, client: str) -> bool:
        return self.allowed


@pytest.mark.anyio
async def test_the_number_and_the_deadline_use_the_date_in_lima() -> None:
    now = datetime(2027, 1, 1, 4, 30, tzinfo=UTC)
    repository = MemoryRepository(holidays=frozenset({date(2027, 1, 1)}))
    file = FileComplaint(repository, Limiter(allowed=True), LimaClock(now, date(2026, 12, 31)))

    first = await file(SHEET, "203.0.113.7")
    second = await file(SHEET, "203.0.113.7")

    assert first is not None
    assert second is not None
    assert (first.number, second.number) == ("000000001-2026", "000000002-2026")
    assert first.created_at == now
    assert first.due_on == date(2027, 1, 22)
    assert repository.complaints == [first, second]


@pytest.mark.anyio
async def test_a_limited_client_files_nothing() -> None:
    repository = MemoryRepository()
    clock = LimaClock(datetime(2026, 10, 23, 15, 0, tzinfo=UTC), date(2026, 10, 23))
    file = FileComplaint(repository, Limiter(allowed=False), clock)

    assert await file(SHEET, "203.0.113.7") is None
    assert repository.counters == {}
    assert repository.complaints == []
