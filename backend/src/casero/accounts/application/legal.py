from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.registration import LegalVersions
from casero.accounts.domain.legal import LegalEvent, latest_consent, pending_documents
from casero.accounts.domain.registration import LegalVersion
from casero.shared.kernel.clock import Clock


class LegalRecords(Protocol):
    async def events(self, user_id: UUID) -> list[LegalEvent]: ...

    async def accept(
        self,
        account_id: UUID,
        user_id: UUID,
        document_ids: Sequence[UUID],
        client: str,
        at: datetime,
    ) -> None: ...

    async def withdraw(
        self, account_id: UUID, user_id: UUID, document_id: UUID, at: datetime
    ) -> None: ...


@dataclass(frozen=True)
class LegalStatus:
    pending: list[LegalVersion]
    consent_withdrawn: bool


def legal_status(current: list[LegalVersion], events: list[LegalEvent]) -> LegalStatus:
    consent = latest_consent(events)
    return LegalStatus(
        pending_documents(current, events), consent is not None and consent.withdrawn
    )


@dataclass(frozen=True)
class GetLegalStatus:
    versions: LegalVersions
    records: LegalRecords
    clock: Clock

    async def __call__(self, context: AccountContext) -> LegalStatus:
        current = await self.versions.current(self.clock.today_lima())
        return legal_status(current, await self.records.events(context.user_id))


@dataclass(frozen=True)
class AcceptLegalDocuments:
    """Accepts current versions; one already accepted is skipped, so repeating changes nothing."""

    versions: LegalVersions
    records: LegalRecords
    clock: Clock

    async def __call__(
        self, context: AccountContext, document_ids: Sequence[UUID], client: str
    ) -> LegalStatus | Literal["document_not_current"]:
        current = await self.versions.current(self.clock.today_lima())
        if set(document_ids) - {document.document_id for document in current}:
            return "document_not_current"
        events = await self.records.events(context.user_id)
        missing = {document.document_id for document in pending_documents(current, events)}
        accepted = sorted(missing & set(document_ids))
        if not accepted:
            return legal_status(current, events)
        await self.records.accept(
            context.account_id, context.user_id, accepted, client, self.clock.now()
        )
        return legal_status(current, await self.records.events(context.user_id))


@dataclass(frozen=True)
class WithdrawConsent:
    """Withdraws the sensitive-data consent; the account stays blocked until it's given again.

    Withdrawing again changes nothing (SPEC, "Datos personales").
    """

    versions: LegalVersions
    records: LegalRecords
    clock: Clock

    async def __call__(self, context: AccountContext) -> LegalStatus:
        current = await self.versions.current(self.clock.today_lima())
        events = await self.records.events(context.user_id)
        consent = latest_consent(events)
        if consent is None or consent.withdrawn:
            return legal_status(current, events)
        await self.records.withdraw(
            context.account_id, context.user_id, consent.document_id, self.clock.now()
        )
        return legal_status(current, await self.records.events(context.user_id))
