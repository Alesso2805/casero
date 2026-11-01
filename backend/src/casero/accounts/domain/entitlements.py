from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from casero.shared.kernel.periods import Period

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
# What a month paid for keeps after the plan lapses (SPEC, "Meses pagados").
MONTH_BOUND_FEATURES: frozenset[Feature] = frozenset({"tax_module", "tax_reminders"})
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

    def allows_month(self, feature: Feature, period: Period) -> bool:
        return self.allows(feature) or (
            feature in MONTH_BOUND_FEATURES and is_paid_month(self.subscription, period)
        )


def is_paid_month(subscription: Subscription | None, period: Period) -> bool:
    """A month starting in the paid part of the subscription; the trial's months never count."""
    if subscription is None or subscription.ends_at is None:
        return False
    paid_from = subscription.trial_ends_at or subscription.starts_at
    return paid_from <= period.first_day() < subscription.ends_at


def is_trial_lapsing(subscription: Subscription, today: date) -> bool:
    """The trial ended with nothing paid, and its days of grace are still running."""
    ended_on = subscription.trial_ends_at
    return (
        ended_on is not None
        and subscription.ends_at == ended_on
        and ended_on <= today < ended_on + GRACE_PERIOD
    )


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
