from datetime import date

import pytest

from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.domain.entitlements import (
    Plan,
    Subscription,
    SubscriptionStatus,
    effective_plan_code,
    subscription_status,
)

TRIAL = Subscription("casero", date(2026, 10, 26), date(2026, 11, 25), date(2026, 11, 25), None)
PAID = Subscription("casero", date(2026, 10, 26), None, date(2027, 10, 26), None)


@pytest.mark.parametrize(
    ("subscription", "today", "status"),
    [
        (None, date(2026, 10, 26), "free"),
        (TRIAL, date(2026, 10, 26), "trial"),
        (TRIAL, date(2026, 11, 24), "trial"),
        (TRIAL, date(2026, 11, 25), "grace"),
        (TRIAL, date(2026, 12, 1), "grace"),
        (TRIAL, date(2026, 12, 2), "free"),
        (PAID, date(2027, 10, 25), "active"),
        (PAID, date(2027, 10, 26), "grace"),
        (PAID, date(2027, 11, 2), "free"),
        (Subscription("casero", date(2026, 10, 1), None, None, None), date(2030, 1, 1), "active"),
        (
            Subscription("casero", date(2026, 10, 1), None, None, date(2026, 10, 20)),
            date(2026, 10, 26),
            "free",
        ),
    ],
)
def test_the_status_comes_from_the_dates(
    subscription: Subscription | None, today: date, status: SubscriptionStatus
) -> None:
    assert subscription_status(subscription, today) == status


def test_a_lapsed_subscription_falls_back_to_the_free_plan() -> None:
    assert effective_plan_code(TRIAL, "trial") == "casero"
    assert effective_plan_code(TRIAL, "grace") == "casero"
    assert effective_plan_code(TRIAL, "free") == "free"
    assert effective_plan_code(None, "free") == "free"


class Clock:
    def __init__(self, today: date) -> None:
        self.today = today

    def now(self) -> None:
        raise AssertionError("not used")

    def today_lima(self) -> date:
        return self.today


class Subscriptions:
    async def current(self) -> Subscription | None:
        return TRIAL


class Plans:
    async def plan(self, code: str) -> Plan:
        features = frozenset({"tax_module", "data_export"}) if code == "casero" else frozenset()
        return Plan(code, 10 if code == "casero" else 1, features)  # type: ignore[arg-type]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("today", "plan", "tax_module"),
    [(date(2026, 11, 1), "casero", True), (date(2026, 12, 5), "free", False)],
)
async def test_features_follow_the_effective_plan(today: date, plan: str, tax_module: bool) -> None:
    entitlements = await GetEntitlements(Subscriptions(), Plans(), Clock(today))()  # type: ignore[arg-type]

    assert entitlements.plan.code == plan
    assert entitlements.allows("tax_module") is tax_module
