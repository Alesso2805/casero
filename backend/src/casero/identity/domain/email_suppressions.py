from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

SuppressionReason = Literal["bounce", "complaint", "unsubscribe"]
ScheduledEmailKind = Literal["daily_digest", "tax_reminders"]


@dataclass(frozen=True)
class Suppression:
    email: str
    kind: ScheduledEmailKind | None
    reason: SuppressionReason


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def _recipients(section: Any, key: str) -> list[str]:
    if not isinstance(section, Mapping):
        return []
    recipients = section.get(key)
    if not isinstance(recipients, list):
        return []
    return [
        recipient["emailAddress"]
        for recipient in recipients
        if isinstance(recipient, Mapping) and isinstance(recipient.get("emailAddress"), str)
    ]


def suppressions_from_ses_event(event: Mapping[str, Any]) -> list[Suppression]:
    """Turn an SES bounce or complaint event into suppressions.

    Only permanent bounces suppress: a transient bounce (full mailbox, greylisting) says
    nothing about the address. Identity notifications use `notificationType` and
    configuration-set events use `eventType`; both carry the same payload.
    """
    event_type = event.get("notificationType") or event.get("eventType")
    if event_type == "Bounce":
        bounce = event.get("bounce")
        if not isinstance(bounce, Mapping) or bounce.get("bounceType") != "Permanent":
            return []
        return [
            Suppression(email, None, "bounce") for email in _recipients(bounce, "bouncedRecipients")
        ]
    if event_type == "Complaint":
        complaint = event.get("complaint")
        return [
            Suppression(email, None, "complaint")
            for email in _recipients(complaint, "complainedRecipients")
        ]
    return []
