import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

import pytest

import sns_signing
from casero.identity.application.email_suppressions import RecordEmailEvent
from casero.identity.domain.email_suppressions import (
    ScheduledEmailKind,
    Suppression,
    suppressions_from_ses_event,
)

pytestmark = pytest.mark.anyio

TOPIC = "arn:aws:sns:us-east-1:000000000000:casero-test"
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            sns_signing.permanent_bounce("a@example.com", "b@example.com"),
            [
                Suppression("a@example.com", None, "bounce"),
                Suppression("b@example.com", None, "bounce"),
            ],
        ),
        (
            {
                "eventType": "Bounce",
                "bounce": {
                    "bounceType": "Transient",
                    "bouncedRecipients": [{"emailAddress": "a@example.com"}],
                },
            },
            [],
        ),
        (
            {
                "eventType": "Complaint",
                "complaint": {"complainedRecipients": [{"emailAddress": "a@example.com"}]},
            },
            [Suppression("a@example.com", None, "complaint")],
        ),
        ({"notificationType": "Delivery"}, []),
        ({"notificationType": "Bounce", "bounce": "broken"}, []),
    ],
)
def test_only_permanent_bounces_and_complaints_suppress(
    event: dict[str, Any], expected: list[Suppression]
) -> None:
    assert suppressions_from_ses_event(event) == expected


class FixedClock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> date:
        return NOW.date()


class MemoryStore:
    def __init__(self) -> None:
        self.added: list[Suppression] = []

    async def add(self, suppression: Suppression, now: datetime) -> None:
        self.added.append(suppression)

    async def blocks(self, email: str, kind: ScheduledEmailKind | None) -> bool:
        return any(item.email == email for item in self.added)


class TrustingVerifier:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid
        self.confirmed: list[str] = []

    async def verify(self, message: Mapping[str, Any]) -> bool:
        return self.valid

    async def confirm(self, subscribe_url: str) -> None:
        self.confirmed.append(subscribe_url)


async def test_a_notification_from_the_topic_records_its_suppressions() -> None:
    store = MemoryStore()
    record = RecordEmailEvent(store, TrustingVerifier(), FixedClock(), TOPIC)

    outcome = await record(
        sns_signing.notification(TOPIC, sns_signing.permanent_bounce("a@example.com"))
    )

    assert outcome == "recorded"
    assert store.added == [Suppression("a@example.com", None, "bounce")]


@pytest.mark.parametrize(
    ("topic", "valid"),
    [("arn:aws:sns:us-east-1:000000000000:other", True), (TOPIC, False)],
)
async def test_other_topics_and_bad_signatures_are_rejected(topic: str, valid: bool) -> None:
    store = MemoryStore()
    record = RecordEmailEvent(store, TrustingVerifier(valid), FixedClock(), TOPIC)

    outcome = await record(
        sns_signing.notification(topic, sns_signing.permanent_bounce("a@example.com"))
    )

    assert outcome == "rejected"
    assert store.added == []


async def test_a_subscription_is_confirmed_once_verified() -> None:
    verifier = TrustingVerifier()
    record = RecordEmailEvent(MemoryStore(), verifier, FixedClock(), TOPIC)

    assert await record(sns_signing.subscription_confirmation(TOPIC)) == "confirmed"
    assert verifier.confirmed == [sns_signing.SUBSCRIBE_URL]


async def test_a_notification_that_is_not_json_is_ignored() -> None:
    message = sns_signing.notification(TOPIC, {})
    message["Message"] = "not json"
    record = RecordEmailEvent(MemoryStore(), TrustingVerifier(), FixedClock(), TOPIC)

    assert await record(message) == "ignored"


async def test_a_genuine_signature_verifies_and_the_certificate_is_cached() -> None:
    sns = sns_signing.FakeSns()
    verifier = sns.verifier()
    message = sns_signing.notification(TOPIC, sns_signing.permanent_bounce("a@example.com"))

    assert await verifier.verify(message)
    assert await verifier.verify(message)
    assert sns.requested == [sns_signing.CERT_URL]


@pytest.mark.parametrize(
    "tamper",
    [
        {"Message": json.dumps(sns_signing.permanent_bounce("otro@example.com"))},
        {"SignatureVersion": "1"},
        {"SigningCertURL": "https://sns.us-east-1.amazonaws.com.evil.example/cert.pem"},
        {"SigningCertURL": "http://sns.us-east-1.amazonaws.com/cert.pem"},
        {"Signature": "not base64!"},
    ],
)
async def test_tampered_or_foreign_messages_do_not_verify(tamper: dict[str, str]) -> None:
    sns = sns_signing.FakeSns()
    message = {
        **sns_signing.notification(TOPIC, sns_signing.permanent_bounce("a@example.com")),
        **tamper,
    }

    assert not await sns.verifier().verify(message)


async def test_only_sns_hosts_are_called_to_confirm() -> None:
    sns = sns_signing.FakeSns()
    verifier = sns.verifier()

    await verifier.confirm(sns_signing.SUBSCRIBE_URL)
    with pytest.raises(ValueError, match="SNS"):
        await verifier.confirm("https://evil.example/confirm")

    assert sns.requested == [sns_signing.SUBSCRIBE_URL]
