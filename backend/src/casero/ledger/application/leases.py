from dataclasses import dataclass, fields, replace
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.application.profile import Profiles
from casero.leases.application.leases import (
    Lease,
    LeaseProblem,
    LeaseStore,
    LeaseTerms,
    LeaseView,
    OpeningBalances,
    effective_treatment,
    lease_problem,
    opening_balance_due,
    view,
)
from casero.leases.application.renters import RenterStore
from casero.properties.application.properties import PropertyStore
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id
from casero.shared.kernel.periods import Period

LeaseRefusal = (
    LeaseProblem
    | Literal[
        "conflict",
        "plan_limit",
        "unit_not_found",
        "unit_archived",
        "unit_occupied",
        "renter_not_found",
    ]
)


class OpeningBalanceStore(Protocol):
    async def opening_balances(self, lease_id: UUID) -> OpeningBalances: ...

    async def add_opening_balance(
        self,
        account_id: UUID,
        charge_id: UUID,
        lease_id: UUID,
        amount_cents: int,
        pre_2026: bool,
        due_date: date,
        created_by: UUID,
        created_at: datetime,
    ) -> None: ...


@dataclass(frozen=True)
class NewLease:
    id: UUID
    terms: LeaseTerms
    opening: OpeningBalances


@dataclass(frozen=True)
class Created:
    view: LeaseView
    replayed: bool


@dataclass(frozen=True)
class CreateLease:
    """A lease with its first rent and prior balances, in one transaction (ADR-0001).

    Locks go account, then unit, the same order as editing or archiving a property,
    so the plan limit, the unit's single active lease and its ownership hold.
    """

    profiles: Profiles
    entitlements: GetEntitlements
    properties: PropertyStore
    renters: RenterStore
    leases: LeaseStore
    balances: OpeningBalanceStore
    audit: AuditLog
    clock: Clock

    async def __call__(self, context: AccountContext, new: NewLease) -> Created | LeaseRefusal:
        today = self.clock.today_lima()
        await self.profiles.lock_current()
        unit = await self.properties.lock_unit(new.terms.unit_id)
        if unit is None:
            return "unit_not_found"
        split = await self.properties.ownership_of(unit.property_id) == "conjugal_split"
        terms = replace(
            new.terms, tax_treatment=effective_treatment(new.terms.tax_treatment, split)
        )
        existing = await self.leases.get(new.id, Period.of(today))
        if existing is not None:
            return await self._replay(existing, terms, new, today)
        refusal = await self._refusal(new, terms, unit.archived, today)
        if refusal is not None:
            return refusal
        now = self.clock.now()
        if not await self.leases.add(context.account_id, new.id, terms, now):
            return "conflict"
        await self._record(context, new, terms, now)
        lease = Lease(new.id, terms, ended_at=None, current_rent_cents=terms.monthly_rent_cents)
        return Created(view(lease, today), replayed=False)

    async def _replay(
        self, existing: Lease, terms: LeaseTerms, new: NewLease, today: date
    ) -> Created | Literal["conflict"]:
        same = existing.terms == terms and (
            await self.balances.opening_balances(new.id) == new.opening
        )
        return Created(view(existing, today), replayed=True) if same else "conflict"

    async def _refusal(
        self, new: NewLease, terms: LeaseTerms, unit_archived: bool, today: date
    ) -> LeaseRefusal | None:
        if unit_archived:
            return "unit_archived"
        if await self.leases.active_on_unit(terms.unit_id):
            return "unit_occupied"
        if await self.renters.lock(terms.renter_id) is None:
            return "renter_not_found"
        problem = lease_problem(terms, new.opening, today)
        if problem is not None:
            return problem
        entitlements = await self.entitlements()
        if await self.leases.count_active() >= entitlements.plan.max_active_leases:
            return "plan_limit"
        return None

    async def _record(
        self, context: AccountContext, new: NewLease, terms: LeaseTerms, now: datetime
    ) -> None:
        await self.leases.add_rent_change(
            context.account_id,
            new_id(),
            new.id,
            terms.monthly_rent_cents,
            terms.control_from,
            context.user_id,
            now,
        )
        balances = (
            (True, new.opening.pre_2026_cents),
            (False, new.opening.from_2026_cents),
        )
        for pre_2026, amount in balances:
            if amount:
                await self.balances.add_opening_balance(
                    context.account_id,
                    new_id(),
                    new.id,
                    amount,
                    pre_2026,
                    opening_balance_due(pre_2026, terms.control_from),
                    context.user_id,
                    now,
                )
        changed = [field.name for field in fields(terms)]
        if new.opening.pre_2026_cents:
            changed.append("opening_balance_pre_2026")
        if new.opening.from_2026_cents:
            changed.append("opening_balance_2026")
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "lease.created",
                "leases",
                new.id,
                changed,
                now,
            )
        )
