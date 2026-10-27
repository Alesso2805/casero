from dataclasses import dataclass
from typing import Protocol

from casero.accounts.domain.entitlements import (
    FEATURES,
    Entitlements,
    Feature,
    Plan,
    Subscription,
    SubscriptionStatus,
    effective_plan_code,
    subscription_status,
)
from casero.shared.kernel.clock import Clock

__all__ = [
    "FEATURES",
    "Entitlements",
    "Feature",
    "GetEntitlements",
    "PlanCatalog",
    "SubscriptionReader",
    "SubscriptionStatus",
]


class SubscriptionReader(Protocol):
    async def current(self) -> Subscription | None: ...


class PlanCatalog(Protocol):
    async def plan(self, code: str) -> Plan: ...


@dataclass(frozen=True)
class GetEntitlements:
    """What the account in context may use; every module checks features here (rule 13)."""

    subscriptions: SubscriptionReader
    plans: PlanCatalog
    clock: Clock

    async def __call__(self) -> Entitlements:
        subscription = await self.subscriptions.current()
        status = subscription_status(subscription, self.clock.today_lima())
        plan = await self.plans.plan(effective_plan_code(subscription, status))
        return Entitlements(plan, status, subscription)
