from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from casero.accounts.domain.registration import DocumentKind, LegalVersion


@dataclass(frozen=True)
class LegalEvent:
    """One acceptance or withdrawal; both tables are append-only, so this is the whole history."""

    document_id: UUID
    kind: DocumentKind
    at: datetime
    withdrawn: bool


def latest_consent(events: list[LegalEvent]) -> LegalEvent | None:
    """The last word on the sensitive-data consent; a tie counts as withdrawn, the safe side."""
    consent = (event for event in events if event.kind == "sensitive_consent")
    return max(consent, key=lambda event: (event.at, event.withdrawn), default=None)


def pending_documents(current: list[LegalVersion], events: list[LegalEvent]) -> list[LegalVersion]:
    """Current versions never accepted, or whose acceptance a later withdrawal undid."""

    def accepted(document: LegalVersion) -> bool:
        withdrawals = [e.at for e in events if e.withdrawn and e.kind == document.kind]
        return any(
            event.document_id == document.document_id
            and not event.withdrawn
            and all(event.at > withdrawn_at for withdrawn_at in withdrawals)
            for event in events
        )

    return [document for document in current if not accepted(document)]
