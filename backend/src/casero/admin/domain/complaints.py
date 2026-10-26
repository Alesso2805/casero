import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

ComplaintKind = Literal["claim", "complaint"]
DocumentType = Literal["dni", "ce", "passport"]
ItemKind = Literal["product", "service"]
ResponseChannel = Literal["email", "letter"]

RESPONSE_BUSINESS_DAYS = 15
FIRST_WEEKEND_DAY = 5

DOCUMENT_PATTERNS: dict[DocumentType, re.Pattern[str]] = {
    "dni": re.compile(r"[0-9]{8}"),
    "ce": re.compile(r"[A-Z0-9]{4,20}"),
    "passport": re.compile(r"[A-Z0-9]{4,20}"),
}


@dataclass(frozen=True)
class Guardian:
    full_name: str
    address: str | None
    phone: str | None
    email: str | None


@dataclass(frozen=True)
class ComplaintSheet:
    full_name: str
    document_type: DocumentType
    document_number: str
    address: str | None
    email: str | None
    phone: str | None
    guardian: Guardian | None
    item_kind: ItemKind
    claimed_amount_cents: int | None
    item_description: str | None
    kind: ComplaintKind
    detail: str
    request: str | None
    response_channel: ResponseChannel


@dataclass(frozen=True)
class Complaint:
    id: UUID
    number: str
    created_at: datetime
    due_on: date
    sheet: ComplaintSheet


def normalize_document(number: str) -> str:
    return re.sub(r"[\s.-]", "", number).upper()


def is_valid_document(document_type: DocumentType, number: str) -> bool:
    return DOCUMENT_PATTERNS[document_type].fullmatch(number) is not None


def complaint_number(sequence: int, year: int) -> str:
    return f"{sequence:09d}-{year}"


def add_business_days(filed_on: date, days: int, holidays: frozenset[date]) -> date:
    # Counting starts on the next business day and skips weekends and national holidays
    # (TUO de la Ley 27444, arts. 133-134). A missing holiday only makes the date earlier.
    current = filed_on
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < FIRST_WEEKEND_DAY and current not in holidays:
            remaining -= 1
    return current
