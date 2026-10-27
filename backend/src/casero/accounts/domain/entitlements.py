from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

Feature = Literal[
    "whatsapp_links",
    "tenant_portal",
    "tax_module",
    "tax_reminders",
    "receipts_pdf",
    "accountant_export",
    "data_export",
]
FEATURES: tuple[Feature, ...] = (
    "whatsapp_links",
    "tenant_portal",
    "tax_module",
    "tax_reminders",
    "receipts_pdf",
    "accountant_export",
    "data_export",
)
SubscriptionStatus = Literal["trial", "active", "grace", "free"]
GRACE_PERIOD = timedelta(days=7)
FREE_PLAN = "free"


@dataclass(frozen=True)
class Subscription:
    plan_code: str
    starts_at: date
    trial_ends_at: date | None
    ends_at: date | None
    ended_at: date | None


@dataclass(frozen=True)
class Plan:
    code: str
    max_active_leases: int
    features: frozenset[Feature]


@dataclass(frozen=True)
class Entitlements:
    plan: Plan
    status: SubscriptionStatus
    subscription: Subscription | None

    def allows(self, feature: Feature) -> bool:
        return feature in self.plan.features


def subscription_status(subscription: Subscription | None, today: date) -> SubscriptionStatus:
    """Derived from dates only (SPEC): trial, active, 7 days of grace after it ends, then free."""
    if subscription is None or (subscription.ended_at and subscription.ended_at <= today):
        return "free"
    if subscription.trial_ends_at and today < subscription.trial_ends_at:
        return "trial"
    if subscription.ends_at is None or today < subscription.ends_at:
        return "active"
    if today < subscription.ends_at + GRACE_PERIOD:
        return "grace"
    return "free"


def effective_plan_code(subscription: Subscription | None, status: SubscriptionStatus) -> str:
    return FREE_PLAN if subscription is None or status == "free" else subscription.plan_code
