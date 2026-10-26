import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from casero.identity.domain.email_suppressions import (
    ScheduledEmailKind,
    Suppression,
    suppressions_from_ses_event,
)
from casero.shared.kernel.clock import Clock

EventOutcome = Literal["recorded", "confirmed", "ignored", "rejected"]


class SuppressionStore(Protocol):
    async def add(self, suppression: Suppression, now: datetime) -> None: ...

    async def blocks(self, email: str, kind: ScheduledEmailKind | None) -> bool: ...


class SnsMessageVerifier(Protocol):
    async def verify(self, message: Mapping[str, Any]) -> bool: ...

    async def confirm(self, subscribe_url: str) -> None: ...


@dataclass(frozen=True)
class RecordEmailEvent:
    store: SuppressionStore
    verifier: SnsMessageVerifier
    clock: Clock
    topic_arn: str

    async def __call__(self, message: Mapping[str, Any]) -> EventOutcome:
        if message.get("TopicArn") != self.topic_arn:
            return "rejected"
        if not await self.verifier.verify(message):
            return "rejected"
        match message.get("Type"):
            case "SubscriptionConfirmation":
                await self.verifier.confirm(str(message.get("SubscribeURL", "")))
                return "confirmed"
            case "Notification":
                return await self._record(message.get("Message"))
            case _:
                return "ignored"

    async def _record(self, body: Any) -> EventOutcome:
        try:
            event = json.loads(body) if isinstance(body, str) else None
        except json.JSONDecodeError:
            return "ignored"
        if not isinstance(event, dict):
            return "ignored"
        suppressions = suppressions_from_ses_event(event)
        for suppression in suppressions:
            await self.store.add(suppression, self.clock.now())
        return "recorded" if suppressions else "ignored"
