from datetime import UTC, datetime
from uuid import UUID, uuid7

from casero.accounts.domain.legal import LegalEvent, latest_consent, pending_documents
from casero.accounts.domain.registration import DocumentKind, LegalVersion


def at(day: int) -> datetime:
    return datetime(2026, 10, day, 15, tzinfo=UTC)


def version(kind: DocumentKind, number: str = "0.1") -> LegalVersion:
    return LegalVersion(kind, uuid7(), number, f"/legal/{kind}/{number}")


TERMS, CONSENT = version("terms"), version("sensitive_consent")


def accepted(document: LegalVersion, day: int) -> LegalEvent:
    return LegalEvent(document.document_id, document.kind, at(day), False)


def withdrawn(document_id: UUID, day: int) -> LegalEvent:
    return LegalEvent(document_id, "sensitive_consent", at(day), True)


def test_a_new_version_is_pending_though_the_old_one_was_accepted() -> None:
    newer = version("terms", "0.2")

    assert pending_documents([newer, CONSENT], [accepted(TERMS, 1), accepted(CONSENT, 1)]) == [
        newer
    ]


def test_a_withdrawn_consent_is_pending_until_it_is_given_again() -> None:
    given = accepted(CONSENT, 1)
    gone = withdrawn(CONSENT.document_id, 2)

    assert pending_documents([CONSENT], [given, gone]) == [CONSENT]
    assert pending_documents([CONSENT], [given, gone, accepted(CONSENT, 3)]) == []


def test_withdrawing_one_version_also_undoes_older_acceptances_of_that_kind() -> None:
    newer = version("sensitive_consent", "0.2")

    assert pending_documents([newer], [accepted(newer, 2), withdrawn(CONSENT.document_id, 3)]) == [
        newer
    ]


def test_the_latest_consent_event_decides_and_a_tie_counts_as_withdrawn() -> None:
    given = accepted(CONSENT, 1)
    gone = withdrawn(CONSENT.document_id, 2)
    again = accepted(CONSENT, 3)
    same_moment = accepted(CONSENT, 2)

    assert latest_consent([accepted(TERMS, 9)]) is None
    assert latest_consent([given, gone]) == gone
    assert latest_consent([given, gone, again]) == again
    assert latest_consent([same_moment, gone]) == gone
