from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.profile import Profiles
from casero.leases.domain.renters import Document, Renter, RenterDetails
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id

DETAIL_FIELDS = ("full_name", "phone_e164")


class RenterStore(Protocol):
    """Encrypts the document and keeps only its HMAC and last characters in clear (ADR-0007)."""

    async def all(self) -> list[Renter]: ...

    async def holder_of(self, document: Document) -> UUID | None: ...

    async def lock(self, renter_id: UUID) -> Renter | None: ...

    async def add(
        self, account_id: UUID, renter_id: UUID, details: RenterDetails, document: Document | None
    ) -> None: ...

    async def update(self, renter_id: UUID, details: RenterDetails) -> None: ...

    async def set_document(self, account_id: UUID, renter_id: UUID, document: Document) -> None: ...


@dataclass(frozen=True)
class ListRenters:
    store: RenterStore

    async def __call__(self) -> list[Renter]:
        return await self.store.all()


@dataclass(frozen=True)
class CreateRenter:
    profiles: Profiles
    store: RenterStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, details: RenterDetails, document: Document | None
    ) -> Renter | Literal["duplicate_document"]:
        if document is not None:
            # The account row lock makes concurrent requests with one document wait for each
            # other, so the second gets duplicate_document instead of the unique index's 500.
            await self.profiles.lock_current()
            if await self.store.holder_of(document) is not None:
                return "duplicate_document"
        renter_id = new_id()
        await self.store.add(context.account_id, renter_id, details, document)
        fields = [*DETAIL_FIELDS, *(["document"] if document else [])]
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "renter.created",
                "renters",
                renter_id,
                fields,
                self.clock.now(),
            )
        )
        return Renter(
            renter_id,
            details,
            document.doc_type if document else None,
            document.last4 if document else None,
        )


@dataclass(frozen=True)
class UpdateRenter:
    """Replaces the name and phone; a document, if given, replaces the stored one."""

    profiles: Profiles
    store: RenterStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self,
        context: AccountContext,
        renter_id: UUID,
        details: RenterDetails,
        document: Document | None,
    ) -> Renter | Literal["not_found", "duplicate_document"]:
        if document is not None:
            await self.profiles.lock_current()
        current = await self.store.lock(renter_id)
        if current is None:
            return "not_found"
        holder = None if document is None else await self.store.holder_of(document)
        if holder is not None and holder != renter_id:
            return "duplicate_document"
        changed = current.details.changed_fields(details)
        if changed:
            await self.store.update(renter_id, details)
        updated = Renter(renter_id, details, current.doc_type, current.doc_last4)
        if document is not None and holder is None:
            await self.store.set_document(context.account_id, renter_id, document)
            changed.append("document")
            updated = Renter(renter_id, details, document.doc_type, document.last4)
        if changed:
            await self.audit.record(
                AuditEntry.of(
                    context.account_id,
                    context.user_id,
                    "renter.updated",
                    "renters",
                    renter_id,
                    changed,
                    self.clock.now(),
                )
            )
        return updated
