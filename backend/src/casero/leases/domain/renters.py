import re
import unicodedata
from dataclasses import dataclass, fields
from typing import Literal
from uuid import UUID

from casero.shared.kernel.ruc import is_valid_ruc

DocType = Literal["dni", "ce", "passport", "ruc"]

# Carné de extranjería and passport numbers vary by issuer; SUNAT's forms take up to 12 characters.
DOCUMENT_PATTERNS: dict[DocType, re.Pattern[str]] = {
    "dni": re.compile(r"[0-9]{8}"),
    "ce": re.compile(r"[0-9A-Z]{5,12}"),
    "passport": re.compile(r"[0-9A-Z]{5,12}"),
    "ruc": re.compile(r"[0-9]{11}"),
}
SEPARATORS = re.compile(r"[\s.\-]")
PERU_MOBILE = re.compile(r"(?:\+?51)?(9[0-9]{8})")
E164 = re.compile(r"\+[1-9][0-9]{6,14}")
LAST_CHARACTERS = 4


def normalize_number(raw: str) -> str:
    """NFKC, then no spaces, dots or hyphens, uppercase (ADR-0007)."""
    return SEPARATORS.sub("", unicodedata.normalize("NFKC", raw)).upper()


@dataclass(frozen=True)
class Document:
    doc_type: DocType
    number: str

    @property
    def last4(self) -> str:
        return self.number[-LAST_CHARACTERS:]


def parse_document(doc_type: DocType, raw: str) -> Document | None:
    number = normalize_number(raw)
    if not number.isascii() or not DOCUMENT_PATTERNS[doc_type].fullmatch(number):
        return None
    if doc_type == "ruc" and not is_valid_ruc(number):
        return None
    return Document(doc_type, number)


def normalize_phone(raw: str) -> str | None:
    """A Peruvian mobile (9 digits starting with 9, with or without +51) or any E.164 number."""
    compact = re.sub(r"[\s()\-]", "", unicodedata.normalize("NFKC", raw))
    if (mobile := PERU_MOBILE.fullmatch(compact)) is not None:
        return f"+51{mobile.group(1)}"
    return compact if E164.fullmatch(compact) else None


@dataclass(frozen=True)
class RenterDetails:
    full_name: str
    phone_e164: str | None

    def changed_fields(self, other: RenterDetails) -> list[str]:
        return [
            field.name
            for field in fields(self)
            if getattr(self, field.name) != getattr(other, field.name)
        ]


@dataclass(frozen=True)
class Renter:
    id: UUID
    details: RenterDetails
    doc_type: DocType | None
    doc_last4: str | None
