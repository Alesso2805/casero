from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from casero.accounts.application.context import AccountContext
from casero.accounts.domain.profile import Profile
from casero.leases.application.renters import CreateRenter, UpdateRenter
from casero.leases.domain.renters import (
    DocType,
    Document,
    Renter,
    RenterDetails,
    normalize_phone,
    parse_document,
)
from casero.shared.kernel.audit import AuditEntry

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CONTEXT = AccountContext(UUID(int=1), UUID(int=2))
ANA = RenterDetails("Ana Quispe", "+51987654321")
DNI = Document("dni", "12345678")


@pytest.mark.parametrize(
    ("doc_type", "raw", "number"),
    [
        ("dni", "12345678", "12345678"),
        ("dni", " 1234-5678 ", "12345678"),
        ("dni", "\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18", "12345678"),
        ("ruc", "20131312955", "20131312955"),
        ("ce", "00123456a", "00123456A"),
        ("passport", "ab.123 456", "AB123456"),
    ],
)
def test_documents_are_normalized(doc_type: DocType, raw: str, number: str) -> None:
    assert parse_document(doc_type, raw) == Document(doc_type, number)


@pytest.mark.parametrize(
    ("doc_type", "raw"),
    [
        ("dni", "1234567"),
        ("dni", "1234567A"),
        ("ruc", "20131312954"),
        ("ce", "1234"),
        ("passport", "ÑANDÚ123"),
        ("passport", "1234567890123"),
    ],
)
def test_invalid_documents_are_refused(doc_type: DocType, raw: str) -> None:
    assert parse_document(doc_type, raw) is None


def test_only_the_last_four_characters_are_shown() -> None:
    assert Document("ruc", "20131312955").last4 == "2955"


@pytest.mark.parametrize(
    ("raw", "phone"),
    [
        ("987 654 321", "+51987654321"),
        ("+51 987-654-321", "+51987654321"),
        ("51987654321", "+51987654321"),
        ("+34 612 345 678", "+34612345678"),
        ("12345", None),
        ("01 4567890", None),
    ],
)
def test_phones_are_kept_in_e164(raw: str, phone: str | None) -> None:
    assert normalize_phone(raw) == phone


class Clock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> date:
        raise AssertionError("not used")


class Store:
    def __init__(self, *renters: tuple[Renter, Document | None]) -> None:
        self.renters = {renter.id: renter for renter, _ in renters}
        self.documents = {document: renter.id for renter, document in renters if document}
        self.writes: list[str] = []
        self.reads: list[str] = []

    async def all(self) -> list[Renter]:
        return list(self.renters.values())

    async def holder_of(self, document: Document) -> UUID | None:
        self.reads.append("holder_of")
        return self.documents.get(document)

    async def lock(self, renter_id: UUID) -> Renter | None:
        return self.renters.get(renter_id)

    async def add(
        self, account_id: UUID, renter_id: UUID, details: RenterDetails, document: Document | None
    ) -> None:
        self.writes.append("add")

    async def update(self, renter_id: UUID, details: RenterDetails) -> None:
        self.writes.append("update")

    async def set_document(self, account_id: UUID, renter_id: UUID, document: Document) -> None:
        self.writes.append("set_document")


class Profiles:
    def __init__(self, store: Store) -> None:
        self._store = store

    async def current(self) -> Profile:
        raise AssertionError("not used")

    async def lock_current(self) -> Profile:
        self._store.reads.append("lock_account")
        return Profile("Casera", "person", None, None, False)

    async def save(self, account_id: UUID, profile: Profile) -> None:
        raise AssertionError("not used")


class Audit:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


def ana(document: Document | None = DNI) -> tuple[Renter, Document | None]:
    renter = Renter(UUID(int=10), ANA, document.doc_type if document else None, None)
    return renter, document


@pytest.mark.anyio
async def test_a_renter_is_created_and_audited_without_values() -> None:
    store, audit = Store(), Audit()

    result = await CreateRenter(Profiles(store), store, audit, Clock())(CONTEXT, ANA, DNI)

    assert isinstance(result, Renter)
    assert (result.doc_type, result.doc_last4) == ("dni", "5678")
    [entry] = audit.entries
    assert (entry.action, entry.changed_fields) == (
        "renter.created",
        ("full_name", "phone_e164", "document"),
    )


@pytest.mark.anyio
async def test_a_document_already_in_the_account_is_refused() -> None:
    store = Store(ana())

    assert (
        await CreateRenter(Profiles(store), store, Audit(), Clock())(CONTEXT, ANA, DNI)
        == "duplicate_document"
    )
    assert store.writes == []


@pytest.mark.anyio
async def test_updating_with_the_same_document_changes_only_the_details() -> None:
    store, audit = Store(ana()), Audit()
    details = RenterDetails("Ana María Quispe", None)

    result = await UpdateRenter(Profiles(store), store, audit, Clock())(
        CONTEXT, UUID(int=10), details, DNI
    )

    assert isinstance(result, Renter)
    assert store.writes == ["update"]
    assert audit.entries[0].changed_fields == ("full_name", "phone_e164")


@pytest.mark.anyio
async def test_a_new_document_replaces_the_stored_one() -> None:
    store, audit = Store(ana(None)), Audit()

    result = await UpdateRenter(Profiles(store), store, audit, Clock())(
        CONTEXT, UUID(int=10), ANA, DNI
    )

    assert isinstance(result, Renter)
    assert (result.doc_type, result.doc_last4) == ("dni", "5678")
    assert store.writes == ["set_document"]
    assert audit.entries[0].changed_fields == ("document",)


@pytest.mark.anyio
async def test_a_document_held_by_another_renter_is_refused() -> None:
    luis = Renter(UUID(int=11), RenterDetails("Luis", None), None, None)
    store = Store(ana(), (luis, None))

    result = await UpdateRenter(Profiles(store), store, Audit(), Clock())(
        CONTEXT, UUID(int=11), ANA, DNI
    )

    assert result == "duplicate_document"
    assert store.writes == []


@pytest.mark.anyio
async def test_an_unknown_renter_is_not_found() -> None:
    result = await UpdateRenter(Profiles(Store()), Store(), Audit(), Clock())(
        CONTEXT, UUID(int=10), ANA, None
    )

    assert result == "not_found"


@pytest.mark.anyio
async def test_the_account_is_locked_before_a_document_is_checked() -> None:
    created, updated = Store(), Store(ana(None))

    await CreateRenter(Profiles(created), created, Audit(), Clock())(CONTEXT, ANA, DNI)
    await UpdateRenter(Profiles(updated), updated, Audit(), Clock())(
        CONTEXT, UUID(int=10), ANA, DNI
    )

    assert created.reads == updated.reads == ["lock_account", "holder_of"]
